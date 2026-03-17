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
#
# CONFIGURATION OVERRIDES (Local-First Priority):
#   - Ruff   : Context-aware; uses native discovery (allows nested ruff.toml/pyproject.toml).
#   - MyPy   : Detects $dir/mypy.ini or $dir/.mypy.ini; falls back to root pyproject.toml.
# ==============================================================================

# Guarantee POSIX system binaries (/usr/bin, /bin) survive exec pivots (uv run, sudo, etc.).
# This must be the first statement — before any external command is invoked.
export PATH="/usr/bin:/bin:${PATH:-}"

# Bash 5.0+ is a hard requirement: associative arrays, inherit_errexit, EPOCHREALTIME.
if [[ "${BASH_VERSINFO[0]}" -lt 5 ]]; then
    echo "Error: Bash 5.0+ required (current: ${BASH_VERSION})." >&2
    echo "       Install via Homebrew: brew install bash" >&2
    exit 1
fi

# Bash Settings
set -o errexit
set -o nounset
set -o pipefail
shopt -s inherit_errexit

# [SECTION: ENVIRONMENT_ISOLATION]
PY_VERSION="${PY_VERSION:-3.14}"
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
        exec uv run --python "$PY_VERSION" "${BASH:-bash}" "$0" "$@"
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
# Resolve script directory using Bash built-ins only — no dependency on /usr/bin/dirname.
_script_src="${BASH_SOURCE[0]}"; [[ "$_script_src" != */* ]] && _script_src="./$_script_src"
SCRIPT_DIR="$(cd -- "${_script_src%/*}" && pwd)"
unset _script_src
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
    for tool in ruff mypy; do
        if ! command -v "$tool" >/dev/null 2>&1; then
             # Warn but don't fail immediately, maybe project doesn't use all tools
             echo "[ WARN ] Tool Missing         : $tool"
        else
             echo "[  OK  ] Tool Verified        : $tool"
        fi
    done
    
    echo -e "\n[ INFO ] Config Discovery Protocol:"
    echo "         - Ruff : Hierarchical (native ruff.toml/pyproject.toml discovery)"
    echo "         - MyPy : mypy.ini > .mypy.ini > root pyproject.toml"
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

# Universal Target Detection (Dynamic)
declare -a TARGETS=()
for dir in */; do
    dir=${dir%/}
    [[ "$dir" == .* ]] && continue # Skip hidden directories (.git, .venv, etc.)
    
    # Only include if it contains at least one .py file (recursively)
    if find "$dir" -maxdepth 5 -name "*.py" -print -quit 2>/dev/null | grep -q ".py"; then
        TARGETS+=("$dir")
    fi
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
        
        # Universal parsing: extract filenames from output (handle spaces/quotes)
        sed -nE 's/^([^:]+\.py):[0-9]+:.*/\1/p' "$output_file" >> "$FAILED_ITEMS_FILE"
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
    # Removed explicit --config to allow for nested ruff/pyproject config discovery
    local cmd=(ruff check --fix $format_flag)
    log_info "Discovery: Native/Hierarchical (ruff.toml or pyproject.toml)"
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
        
        # Configuration resolution: local mypy.ini or .mypy.ini has priority over root pyproject.toml
        local config="$PYPROJECT_CONFIG"
        local config_source="root"
        if [[ -f "$target/mypy.ini" ]]; then
            config="$target/mypy.ini"
            config_source="local (mypy.ini)"
        elif [[ -f "$target/.mypy.ini" ]]; then
            config="$target/.mypy.ini"
            config_source="local (.mypy.ini)"
        fi
        log_info "  + Using ${config_source}: ${config}"

        # Flags: --no-color-output (agent), --no-error-summary (quiet)
        # Note: We rely on PYTHONPATH being set correctly above
        local cmd=(mypy --config-file "$config" --python-version "$PY_VERSION" --no-color-output --no-error-summary)
        execute_tool "mypy" "$target" "${cmd[@]}" "$target"
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
        # Use the venv Python explicitly so plugins always run with the correct Python
        # version. Bare `python` resolves to the system Python on GitHub Actions Ubuntu
        # runners (3.12.x), not the venv Python (3.13.x), causing ImportError on any
        # module that uses Python 3.13+ features (e.g. TypeIs from PEP 742).
        if [[ "$file" == *.py ]]; then cmd=("${TARGET_VENV}/bin/python" "$file")
        elif [[ "$file" == *.sh ]]; then cmd=("bash" "$file")
        elif [[ -x "$file" ]]; then cmd=("$file")
        else cmd=("bash" "$file"); fi
        
        execute_tool "plugin:$name" "all" "${cmd[@]}"
    done
    log_group_end
    unset LINT_PLUGIN_MODE
}

# [SECTION: NOQA AUDIT]
# Rationale: A lint suppression without a justification comment is indistinguishable from
# an accidental suppression. Suppressions fall into two categories:
#   (a) Permanent architectural exceptions: the rule fires on code that is CORRECT by
#       design and cannot be changed without breaking the design (e.g. visitor method
#       naming, grammar-derived dispatch complexity). These are permanent and must be
#       documented with the architectural reason.
#   (b) Deferred fixes disguised as suppressions: the rule fires on code that SHOULD be
#       fixed but was silenced to make the build pass. These are technical debt.
# A rationale comment makes (a) visible and auditable, and makes (b) impossible to hide.
# Without enforcement, suppressions accumulate silently and the distinction between
# "this is intentional" and "this was never fixed" disappears entirely.
# Required format: # noqa: RULE - explanation  OR  # noqa: RULE  # explanation
run_noqa_audit() {
    log_group_start "Audit: Bare noqa suppression rationale"

    # Pattern: # noqa: followed by rule code(s) with nothing after (whitespace only to EOL).
    # Matches bare: # noqa: PLC0415
    # Does NOT match: # noqa: PLC0415 - Babel-optional  OR  # noqa: PLC0415  # comment
    local bare_pattern="# noqa: [A-Z][A-Z0-9]+(, ?[A-Z][A-Z0-9]+)*[[:space:]]*$"

    local found=0
    local output_file
    output_file=$(mktemp)

    # Search all detected source targets (same set as ruff/mypy/pylint).
    set +e
    if [[ ${#TARGETS[@]} -gt 0 ]]; then
        grep -rEn --include="*.py" "$bare_pattern" "${TARGETS[@]}" > "$output_file" 2>/dev/null
    fi
    found=$(wc -l < "$output_file" | tr -d '[:space:]')
    set -e

    if [[ "$found" -gt 0 ]]; then
        log_fail "Bare # noqa suppressions found ($found). Each must include a rationale."
        log_fail "Required format: # noqa: RULE - explanation  OR  # noqa: RULE  # explanation"
        cat "$output_file"
        rm -f "$output_file"
        record_result "noqa-audit" "src" "fail" "0" "$found"
        return 1
    else
        log_pass "noqa-audit: all suppression comments include rationale."
        rm -f "$output_file"
        record_result "noqa-audit" "src" "pass" "0" "0"
        return 0
    fi
}

# Execution
run_ruff || true
run_mypy || true
run_noqa_audit || true
run_plugins || true

# [SECTION: REPORT]
log_group_start "Final Report"

declare -a FAILED_FILE_LIST=()
if [[ -f "$FAILED_ITEMS_FILE" ]]; then
    mapfile -t FAILED_FILE_LIST < <(sort -u "$FAILED_ITEMS_FILE")
fi
# rm -f "$FAILED_ITEMS_FILE" (Deferred deletion)

echo "[SUMMARY-JSON-BEGIN]"
# Use Python for reliable JSON generation (handles escaping, utf-8, etc.)
PYTHON_JSON_SCRIPT="
import json, sys, os

data = {}
# Read results from temporary file
try:
    with open(sys.argv[1], 'r') as f:
        for line in f:
            if '|' not in line: continue
            # Split from right to handle keys containing pipes (e.g. 'tool|target')
            parts = line.strip().rsplit('|', 3)
            if len(parts) != 4: continue
            key, status, duration, files = parts
            data[key] = {
                'status': status, 
                'duration_sec': duration, 
                'files': files
            }
except FileNotFoundError:
    pass

# Read failed files
failed_files = []
try:
    with open(sys.argv[2], 'r') as f:
        failed_files = sorted(list(set(line.strip() for line in f if line.strip())))
except FileNotFoundError:
    pass

# Construct final object
final_obj = data.copy()
final_obj['failed_files'] = failed_files
final_obj['exit_code'] = int(sys.argv[3])

print(json.dumps(final_obj, separators=(',', ':')))
"

# Dump results to a temp file for Python to read
RESULTS_FILE=$(mktemp)
for key in "${!STATUS[@]}"; do
    echo "${key}|${STATUS[$key]}|${TIMING[$key]}|${METRICS[$key]}" >> "$RESULTS_FILE"
done

exit_code_val=0
if [[ "$FAILED" == "true" ]]; then exit_code_val=1; fi

python -c "$PYTHON_JSON_SCRIPT" "$RESULTS_FILE" "$FAILED_ITEMS_FILE" "$exit_code_val"
rm -f "$RESULTS_FILE"
rm -f "$FAILED_ITEMS_FILE"
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