#!/usr/bin/env bash
# ==============================================================================
# lint.sh — Universal Agent-Native Linter
# ==============================================================================
# COMPATIBILITY: Bash 5.0+
# ARCHITECTURAL INTENT: 
#   Project-agnostic linter that adapts to tool versions and project structure.
#   Provides JSON reporting and debug suggestions for AI Agents.
#
# AGENT PROTOCOL:
#   - Silence on Success (unless --verbose)
#   - Full Log on Failure
#   - [SUMMARY-JSON-BEGIN] ... [SUMMARY-JSON-END]
#   - [EXIT-CODE] N
# ==============================================================================

# Bash Settings
set -o errexit
set -o nounset
set -o pipefail
if [[ "${BASH_VERSINFO[0]}" -ge 5 ]]; then
    shopt -s inherit_errexit 2>/dev/null || true
fi

# [SECTION: ENVIRONMENT_ISOLATION]
PY_VERSION="${PY_VERSION:-3.13}"
TARGET_VENV=".venv-${PY_VERSION}"

# Universal Pivot: Works with uv, or standard venvs
if [[ "${UV_PROJECT_ENVIRONMENT:-}" != "$TARGET_VENV" ]]; then
    if [[ "${LINT_ALREADY_PIVOTED:-}" == "1" ]]; then
        echo "Error: Recursive pivot detected. Check your environment configuration." >&2
        exit 1
    fi
    # Only pivot if we are in a UV project
    if [[ -f "uv.lock" || -f "pyproject.toml" ]]; then
        echo -e "\033[34m[INFO]\033[0m Pivoting to isolated environment: ${TARGET_VENV}"
        export UV_PROJECT_ENVIRONMENT="$TARGET_VENV"
        export LINT_ALREADY_PIVOTED=1
        unset VIRTUAL_ENV
        exec uv run --python "$PY_VERSION" bash "$0" "$@"
    fi
else
    unset LINT_ALREADY_PIVOTED
fi

# [SECTION: SETUP]
CLEAN_CACHE=true
VERBOSE=false
declare -A STATUS
declare -A TIMING
declare -A METRICS
FAILED=false
IS_GHA="${GITHUB_ACTIONS:-false}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_VERSION_NODOT="${PY_VERSION//./}"
FAILED_ITEMS_FILE=$(mktemp)

# Auto-configure PYTHONPATH to include 'src' if it exists
# This solves 'Module not found' in examples/tests for 99% of projects
if [[ -d "src" ]]; then
    export PYTHONPATH="${PWD}/src:${PYTHONPATH:-}"
else
    export PYTHONPATH="${PWD}:${PYTHONPATH:-}"
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-clean) CLEAN_CACHE=false; shift ;;
        --verbose)  VERBOSE=true; shift ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

if [[ "${NO_COLOR:-}" == "1" ]]; then
    RED=""; GREEN=""; YELLOW=""; BLUE=""; CYAN=""; BOLD=""; RESET=""
else
    RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"; BLUE="\033[34m"; CYAN="\033[36m"; BOLD="\033[1m"; RESET="\033[0m"
fi

log_group_start() { [[ "$IS_GHA" == "true" ]] && echo "::group::$1"; echo -e "\n${BOLD}${CYAN}=== $1 ===${RESET}"; }
log_group_end() { [[ "$IS_GHA" == "true" ]] && echo "::endgroup::"; return 0; }
log_info() { echo -e "${BLUE}[INFO]${RESET} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${RESET} $1"; }
log_fail() { echo -e "${RED}[FAIL]${RESET} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${RESET} $1"; }
log_err()  { echo -e "${RED}[ERROR]${RESET} $1" >&2; }

# [SECTION: DIAGNOSTICS]
pre_flight_diagnostics() {
    log_group_start "Pre-Flight Diagnostics"
    echo "[  OK  ] Schema               : universal-agent-v1"
    
    if [[ "${UV_PROJECT_ENVIRONMENT:-}" == "$TARGET_VENV" ]]; then
       echo "[  OK  ] Environment          : Isolated ($TARGET_VENV)"
    else
       echo "[ INFO ] Environment          : System/User ($VIRTUAL_ENV)"
    fi
    echo "[ INFO ] Python               : $(python --version)"
    echo "[ INFO ] PYTHONPATH           : ${PYTHONPATH:-<empty>}"
    
    # Tool Availability Check
    local tool_status=0
    for tool in ruff mypy pylint; do
        if ! command -v "$tool" >/dev/null 2>&1; then
             # Warn but don't fail immediately, maybe project doesn't use all tools
             echo "[ WARN ] Tool Missing         : $tool"
        else
             echo "[  OK  ] Tool Verified        : $tool"
        fi
    done
    log_group_end
}
pre_flight_diagnostics

# Navigation
PROJECT_ROOT="$PWD"
while [[ "$PROJECT_ROOT" != "/" && ! -f "$PROJECT_ROOT/pyproject.toml" ]]; do
    PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
done
cd "$PROJECT_ROOT"
PYPROJECT_CONFIG="$PROJECT_ROOT/pyproject.toml"

# Cleaning
if [[ "$CLEAN_CACHE" == "true" ]]; then
    log_group_start "Housekeeping"
    # Universal cleanup: remove common cache dirs found in current dir
    find . -type d \( -name ".mypy_cache" -o -name ".pylint.d" -o -name ".ruff_cache" -o -name "__pycache__" \) -prune -exec rm -rf {} + 2>/dev/null || true
    log_info "Caches cleared."
    log_group_end
fi

# Universal Target Detection
declare -a TARGETS=()
for dir in "src" "tests" "test" "examples" "scripts"; do
    if [[ -d "$dir" ]]; then TARGETS+=("$dir"); fi
done

record_result() {
    local tool="$1" target="$2" status="$3"
    local duration="${4:-0}" files="${5:-0}"
    STATUS["${tool}|${target}"]="$status"
    TIMING["${tool}|${target}"]="$duration"
    METRICS["${tool}|${target}"]="$files"
    if [[ "$status" == "fail" ]]; then FAILED=true; fi
}

execute_tool() {
    local tool_name="$1"
    local target_name="$2"
    shift 2
    local output_file
    output_file=$(mktemp)
    
    local start_time="${EPOCHREALTIME}"
    
    set +e
    "$@" > "$output_file" 2>&1
    local exit_code=$?
    set -e
    
    local duration=$(printf "%.3f" "$(echo "${EPOCHREALTIME} - $start_time" | bc)")
    
    # Universal file counting (Pre-calc instead of parsing output)
    local file_count="0"
    if [[ "$target_name" == "all" ]]; then
        # Sum of all targets
        local total=0
        for t in "${TARGETS[@]}"; do
             if [[ -d "$t" ]]; then
                 local c
                 c=$(find "$t" -name "*.py" 2>/dev/null | wc -l | tr -d '[:space:]')
                 total=$((total + c))
             fi
        done
        file_count="$total"
    elif [[ -d "$target_name" ]]; then
        file_count=$(find "$target_name" -name "*.py" 2>/dev/null | wc -l | tr -d '[:space:]')
    fi

    if [[ $exit_code -eq 0 ]]; then
        log_pass "${tool_name} passed (${target_name})."
        record_result "$tool_name" "$target_name" "pass" "$duration" "$file_count"
        if [[ "$VERBOSE" == "true" ]]; then cat "$output_file"; fi
    else
        log_fail "${tool_name} failed on ${target_name}."
        record_result "$tool_name" "$target_name" "fail" "$duration" "$file_count"
        cat "$output_file"
        
        # Universal parsing: extract filenames from output
        grep -E "^[^: ]+\.py:[0-9]+:" "$output_file" | cut -d: -f1 | sed 's/^[[:space:]]*//' >> "$FAILED_ITEMS_FILE"
    fi
    rm -f "$output_file"
    return $exit_code
}

# [SECTION: LINTERS]

run_ruff() {
    log_group_start "Lint: Ruff"
    
    # Feature Detection: Check if 'concise' format is supported (newer ruff)
    local format_flag="--output-format=text" # default fallback
    if ruff check --help 2>&1 | grep -q "concise"; then
        format_flag="--output-format=concise"
    fi

    # Run on all targets at once (Ruff is safe for this)
    local cmd=(ruff check --fix --config "$PYPROJECT_CONFIG" $format_flag)
    # Append target version if we can determine it, otherwise let ruff read pyproject.toml
    if [[ -n "${PY_VERSION_NODOT}" ]]; then
        cmd+=(--target-version "py${PY_VERSION_NODOT}")
    fi
    
    execute_tool "ruff" "all" "${cmd[@]}" "${TARGETS[@]}"
    log_group_end
}

run_mypy() {
    log_group_start "Lint: MyPy"
    
    # Iterate targets individually to prevent module-clashing (the 'threading' bug)
    for target in "${TARGETS[@]}"; do
        log_info "Analyzing $target..."
        # Flags: --no-color-output (agent), --no-error-summary (quiet)
        # Note: We rely on PYTHONPATH being set correctly above
        local cmd=(mypy --config-file "$PYPROJECT_CONFIG" --python-version "$PY_VERSION" --no-color-output --no-error-summary)
        execute_tool "mypy" "$target" "${cmd[@]}" "$target"
    done
    log_group_end
}

run_pylint() {
    log_group_start "Lint: Pylint"
    
    # Iterate targets individually
    for target in "${TARGETS[@]}"; do
        log_info "Analyzing $target..."
        local cmd=(pylint --rcfile "$PYPROJECT_CONFIG" --py-version "$PY_VERSION" --output-format=text --msg-template='{path}:{line}: [{msg_id}({symbol}), {obj}] {msg}')
        if [[ -f "$target/.pylintrc" ]]; then
             cmd=(pylint --rcfile "$target/.pylintrc" --py-version "$PY_VERSION" --output-format=text --msg-template='{path}:{line}: [{msg_id}({symbol}), {obj}] {msg}')
        fi
        
        execute_tool "pylint" "$target" "${cmd[@]}" "$target"
    done
    log_group_end
}

# [SECTION: PLUGINS]
run_plugins() {
    if [[ -n "${LINT_PLUGIN_MODE:-}" ]]; then return 0; fi
    export LINT_PLUGIN_MODE=1
    
    declare -a plugin_files=()
    set +e
    while IFS= read -r file; do
        if grep -q "# @lint-plugin:" "$file"; then
            plugin_files+=("$file")
        fi
    done < <(find "$SCRIPT_DIR" -maxdepth 1 -type f ! -name "lint.sh" ! -name "for_testing_lint.sh" 2>/dev/null)
    set -e
    
    if [[ ${#plugin_files[@]} -eq 0 ]]; then return 0; fi
    
    log_group_start "Plugins"
    for file in "${plugin_files[@]}"; do
        local name
        # Extract name: Header format "# @lint-plugin: Name" (Strict start of line)
        name=$(grep -m 1 "^# @lint-plugin:" "$file" | sed "s/^# @lint-plugin:[[:space:]]*//" | tr -d '\r\n')
        
        # Skip placeholders, invalid names, or empty strings
        if [[ -z "$name" || "$name" == "<Name>" ]]; then continue; fi
        
        local cmd=()
        if [[ "$file" == *.py ]]; then cmd=("python" "$file")
        elif [[ "$file" == *.sh ]]; then cmd=("bash" "$file")
        elif [[ -x "$file" ]]; then cmd=("$file")
        else cmd=("bash" "$file"); fi
        
        execute_tool "plugin:$name" "all" "${cmd[@]}"
    done
    log_group_end
    unset LINT_PLUGIN_MODE
}

# Execution
run_ruff || true
run_mypy || true
run_pylint || true
run_plugins || true

# [SECTION: REPORT]
log_group_start "Final Report"

declare -a FAILED_FILE_LIST=()
if [[ -f "$FAILED_ITEMS_FILE" ]]; then
    mapfile -t FAILED_FILE_LIST < <(sort -u "$FAILED_ITEMS_FILE")
fi
rm -f "$FAILED_ITEMS_FILE"

echo "[SUMMARY-JSON-BEGIN]"
printf "{"
first=1
if [[ ${#STATUS[@]} -gt 0 ]]; then
    declare -a sorted_keys
    set +e
    readarray -t sorted_keys < <(printf '%s\n' "${!STATUS[@]}" | sort 2>/dev/null)
    set -e
    for key in "${sorted_keys[@]}"; do
        [[ $first -eq 0 ]] && printf ","
        printf "\"%s\":{" "$key"
        printf "\"status\":\"%s\"," "${STATUS[$key]:-unknown}"
        printf "\"duration_sec\":\"%s\"," "${TIMING[$key]:-0}"
        printf "\"files\":\"%s\"" "${METRICS[$key]:-0}"
        printf "}"
        first=0
    done
fi

printf ",\"failed_files\":["
item_first=1
for item in "${FAILED_FILE_LIST[@]}"; do
    [[ $item_first -eq 0 ]] && printf ","
    printf "\"%s\"" "$item"
    item_first=0
done
printf "]"

exit_code_val=0
if [[ "$FAILED" == "true" ]]; then exit_code_val=1; fi
printf ",\"exit_code\":%d}\n" "$exit_code_val"
echo "[SUMMARY-JSON-END]"

if [[ "$FAILED" == "true" ]]; then
    if [[ ${#FAILED_FILE_LIST[@]} -gt 0 ]]; then
        echo -e "\n${YELLOW}[DEBUG-SUGGESTION]${RESET}"
        echo "The following files failed linting. Run these specific commands to debug:"
        echo "  uv run ruff check ${FAILED_FILE_LIST[*]}"
        echo "  uv run mypy ${FAILED_FILE_LIST[*]}"
    fi
    log_err "Build FAILED. See logs above for details."
    echo "[EXIT-CODE] 1" >&2
    exit 1
else
    log_pass "All checks passed in $TARGET_VENV."
    echo "[EXIT-CODE] 0" >&2
    exit 0
fi