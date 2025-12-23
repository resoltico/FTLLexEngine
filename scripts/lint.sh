#!/usr/bin/env bash
# ==============================================================================
# lint.sh — Deterministic Hybrid (AI/Human) Linter
# ==============================================================================
# COMPATIBILITY: Bash v5.0+
#
# ARCHITECTURAL INTENT (PLUGIN SYSTEM):
# This script is designed as a closed, deterministic Host environment. However,
# distinct projects possess unique constraints requiring bespoke validation.
# To bridge this gap without destabilizing the Core, we employ a 'Marker-Based'
# Discovery System.
#
# 1. DISCOVERY: The Host scans its own directory for files containing the
#    marker: "# @lint-plugin: <Name>".
# 2. ISOLATION: Plugins run in subprocesses. They inherit the Environment
#    but cannot mutate the Host's internal state.
# 3. CONTRACT: Plugins communicate success via Exit Code 0. Any other code
#    signals failure. The Host aggregates these signals into the final JSON.
# ==============================================================================

if ((BASH_VERSINFO[0] < 5)); then
    echo "::error::[FATAL] Bash v5.0+ required. Found: ${BASH_VERSION}"
    exit 1
fi

# Strict Modes (Guaranteed ON)
set -o errexit
set -o nounset
set -o pipefail

# --- 1. SETUP & UTILS ---
CLEAN_CACHE=true
declare -A STATUS
declare -A TIMING
declare -A METRICS
FAILED=false
IS_GHA="${GITHUB_ACTIONS:-false}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --no-clean) CLEAN_CACHE=false; shift ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

# Colors
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

# --- ASSUMPTIONS TESTER (Platinum Standard) ---
pre_flight_diagnostics() {
    log_group_start "Pre-Flight Diagnostics"
    
    # Output Architecture Directive (OAD) for cross-agent legibility
    # @FORMAT: [STATUS:8][COMPONENT:20][MESSAGE]
    echo "[  OK  ] Diagnostic Schema  : fixed-width/padded-tags (announcing OAD)"

    # Environment Guard (Enforce uv run context)
    if [[ -z "${VIRTUAL_ENV:-}" ]]; then
        echo "[ FAIL ] Environment         : NOT UV-MANAGED"
        echo "[ INFO ] Policy              : This script must be run via 'uv run'"
        echo "[ INFO ] Command             : uv run scripts/$(basename "$0")"
        exit 1
    fi

    echo "[  OK  ] Environment         : Valid uv context detected"
    echo "[ INFO ] Python Version      : $(python --version)"
    
    # Direct internal tool verification
    local status=0
    if ! ruff --version >/dev/null 2>&1; then status=1; echo "[ FAIL ] Tooling             : Ruff missing (Execute 'uv sync')" ; else echo "[  OK  ] Tooling             : Ruff verified" ; fi
    if ! mypy --version >/dev/null 2>&1; then status=1; echo "[ FAIL ] Tooling             : MyPy missing (Execute 'uv sync')" ; else echo "[  OK  ] Tooling             : MyPy verified" ; fi
    if ! pylint --version >/dev/null 2>&1; then status=1; echo "[ FAIL ] Tooling             : Pylint missing (Execute 'uv sync')" ; else echo "[  OK  ] Tooling             : Pylint verified" ; fi
    
    if [[ $status -ne 0 ]]; then exit 1 ; fi
    log_group_end
}
pre_flight_diagnostics

# Navigation
PROJECT_ROOT="$PWD"
while [[ "$PROJECT_ROOT" != "/" && ! -f "$PROJECT_ROOT/pyproject.toml" ]]; do
    PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
done
if [[ ! -f "$PROJECT_ROOT/pyproject.toml" ]]; then
    log_err "pyproject.toml not found."
    exit 1
fi
cd "$PROJECT_ROOT"
PYPROJECT_CONFIG="$PROJECT_ROOT/pyproject.toml"

# Cleaning
if [[ "$CLEAN_CACHE" == "true" ]]; then
    log_group_start "Housekeeping"
    log_info "Cleaning caches..."
    rm -rf .mypy_cache .pylint.d .ruff_cache
    set +e
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
    set -e
    log_info "Caches cleared."
    log_group_end
fi

# Define Targets
declare -a TARGETS=()
[[ -d "src" ]] && TARGETS+=("src")
[[ -d "tests" ]] && TARGETS+=("tests")
[[ -d "test" ]] && TARGETS+=("test")
[[ -d "examples" ]] && TARGETS+=("examples")

record_result() {
    local tool="$1" target="$2" status="$3"
    local duration="${4:-0}" files="${5:-0}"
    STATUS["${tool}|${target}"]="$status"
    TIMING["${tool}|${target}"]="$duration"
    METRICS["${tool}|${target}"]="$files"
    [[ "$status" == "fail" ]] && FAILED=true
    return 0
}

# --- 3. RUNNERS (Wrapped with set +e for robustness) ---
run_ruff() {
    log_group_start "Lint: Ruff"
    log_info "Running Ruff on: ${TARGETS[*]}"

    local start_time="${EPOCHREALTIME}"
    local file_count=0

    set +e
    for target in "${TARGETS[@]}"; do
        local count=$(find "$target" -name "*.py" 2>/dev/null | wc -l | tr -d ' ')
        file_count=$((file_count + count))
    done
    set -e

    set +e
    ruff check --config "$PYPROJECT_CONFIG" "${TARGETS[@]}"
    local ruff_exit_code=$?
    set -e

    local end_time="${EPOCHREALTIME}"
    local duration=$(printf "%.3f" "$(echo "$end_time - $start_time" | bc)")

    if [[ $ruff_exit_code -eq 0 ]]; then
        log_pass "Ruff passed."
        record_result "ruff" "all" "pass" "$duration" "$file_count"
    else
        log_fail "Ruff found issues (Exit Code: $ruff_exit_code)."
        record_result "ruff" "all" "fail" "$duration" "$file_count"
    fi
    log_group_end
}

run_mypy() {
    log_group_start "Lint: MyPy"
    local mypy_global_status=0

    for dir in "${TARGETS[@]}"; do
        local conf_args=("--config-file" "$PYPROJECT_CONFIG")
        if [[ "$dir" != "src" && -f "$dir/mypy.ini" ]]; then
            conf_args=("--config-file" "$dir/mypy.ini")
        fi
        log_info "Checking $dir..."

        local start_time="${EPOCHREALTIME}"
        local output_file=$(mktemp)

        set +e
        mypy "${conf_args[@]}" "$dir" 2>&1 | tee "$output_file"
        local mypy_exit_code=$?
        set -e

        local end_time="${EPOCHREALTIME}"
        local duration=$(printf "%.3f" "$(echo "$end_time - $start_time" | bc)")

        local file_count=0
        set +e
        file_count=$(grep -o 'no issues found in [0-9]* source files' "$output_file" 2>/dev/null | grep -o '[0-9]*' | head -1 || echo "0")
        [[ -z "$file_count" ]] && file_count=0
        set -e
        rm -f "$output_file"

        if [[ $mypy_exit_code -eq 0 ]]; then
             record_result "mypy" "$dir" "pass" "$duration" "$file_count"
        else
             mypy_global_status=1
             record_result "mypy" "$dir" "fail" "$duration" "$file_count"
        fi
    done

    if [[ $mypy_global_status -eq 0 ]]; then
        log_pass "MyPy passed all targets."
    else
        log_fail "MyPy found issues in one or more targets."
    fi
    log_group_end
}

run_pylint() {
    log_group_start "Lint: Pylint"
    local pylint_global_status=0

    for dir in "${TARGETS[@]}"; do
        local conf_args=("--rcfile" "$PYPROJECT_CONFIG")
        if [[ "$dir" != "src" && -f "$dir/.pylintrc" ]]; then
            conf_args=("--rcfile" "$dir/.pylintrc")
        fi
        log_info "Analyzing $dir..."

        local start_time="${EPOCHREALTIME}"
        local file_count=0

        set +e
        file_count=$(find "$dir" -name "*.py" 2>/dev/null | wc -l | tr -d ' ')
        set -e

        set +e
        pylint "${conf_args[@]}" "$dir"
        local pylint_exit_code=$?
        set -e

        local end_time="${EPOCHREALTIME}"
        local duration=$(printf "%.3f" "$(echo "$end_time - $start_time" | bc)")

        if [[ $pylint_exit_code -eq 0 ]]; then
            record_result "pylint" "$dir" "pass" "$duration" "$file_count"
        else
            pylint_global_status=1
            record_result "pylint" "$dir" "fail" "$duration" "$file_count"
        fi
    done

    if [[ $pylint_global_status -eq 0 ]]; then
        log_pass "Pylint passed all targets."
    else
        log_fail "Pylint found issues in one or more targets."
    fi
    log_group_end
}

# --- 4. PLUGIN SYSTEM ---
run_plugins() {
    # Marker format: # @lint-plugin: <PluginName>
    local marker="# @lint-plugin:"
    
    # Discovery Phase
    # We use find to avoid parsing ls output, looking only in SCRIPT_DIR
    # We exclude lint.sh itself from the grep to avoid self-discovery
    declare -A discovered_plugins
    declare -a plugin_files=()

    while IFS= read -r file; do
        # Extract name using grep/sed
        # Disable errexit temporarily: grep returns 1 when no match found
        local name
        set +e
        name=$(grep -m 1 "$marker" "$file" 2>/dev/null | sed "s/.*$marker[[:space:]]*//")
        set -e
        if [[ -n "$name" ]]; then
            plugin_files+=("$file")
            discovered_plugins["$file"]="$name"
        fi
    done < <(find "$SCRIPT_DIR" -maxdepth 1 -type f ! -name "lint.sh" ! -name "for_testing_lint.sh")

    if [[ ${#plugin_files[@]} -eq 0 ]]; then
        return 0
    fi

    log_group_start "Plugin Discovery"
    log_info "Scanning ${SCRIPT_DIR} for custom checks..."
    for file in "${plugin_files[@]}"; do
        log_info "Found Plugin: ${discovered_plugins[$file]} ($(basename "$file"))"
    done
    log_group_end

    # Execution Phase
    for file in "${plugin_files[@]}"; do
        local name="${discovered_plugins[$file]}"
        local basename=$(basename "$file")
        
        log_group_start "Plugin: $name"
        log_info "Executing custom check: $basename"

        local start_time="${EPOCHREALTIME}"
        local exit_code=0
        
        # Interpreter Resolution
        set +e
        if [[ "$file" == *.py ]]; then
            # Python: Use VENV python if available, else python3
            local python_cmd="python3"
            [[ -n "${VIRTUAL_ENV:-}" ]] && python_cmd="$VIRTUAL_ENV/bin/python"
            log_info "Interpreter: Python ($python_cmd)"
            "$python_cmd" "$file"
            exit_code=$?
        elif [[ "$file" == *.sh ]]; then
            # Bash: Force bash execution
            log_info "Interpreter: Bash"
            bash "$file"
            exit_code=$?
        else
            # Fallback: Direct execution (requires chmod +x)
            log_info "Interpreter: Direct"
            if [[ -x "$file" ]]; then
                "$file"
                exit_code=$?
            else
                log_err "Plugin is not executable and has no known extension."
                exit_code=126
            fi
        fi
        set -e

        local end_time="${EPOCHREALTIME}"
        local duration=$(printf "%.3f" "$(echo "$end_time - $start_time" | bc)")

        if [[ $exit_code -eq 0 ]]; then
            log_pass "Plugin '$name' passed."
            record_result "plugin" "$name" "pass" "$duration" "1"
        else
            log_fail "Plugin '$name' failed (Exit Code: $exit_code)."
            record_result "plugin" "$name" "fail" "$duration" "1"
        fi
        log_group_end
    done
}

run_ruff
run_mypy
run_pylint
run_plugins

# --- REPORT ---
log_group_start "Final Report"
echo "[SUMMARY-JSON-BEGIN]"
printf "{"
first=1
for key in "${!STATUS[@]}"; do
    [[ $first -eq 0 ]] && printf ","
    printf "\"%s\":{" "$key"
    printf "\"status\":\"%s\"," "${STATUS[$key]}"
    printf "\"duration_sec\":\"%s\"," "${TIMING[$key]}"
    printf "\"files\":\"%s\"" "${METRICS[$key]}"
    printf "}"
    first=0
done
printf "}\n"
echo "[SUMMARY-JSON-END]"

if [[ "$FAILED" == "true" ]]; then
    log_err "Build FAILED. See logs above for details."
    exit 1
else
    log_pass "All checks passed."
    exit 0
fi