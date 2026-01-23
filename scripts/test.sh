#!/usr/bin/env bash
# ==============================================================================
# test.sh — Isolated Test Runner (Agent-Native Edition)
# ==============================================================================
# COMPATIBILITY: Bash 5.0+ (Optimized for 5.3)
# ARCHITECTURAL INTENT: 
#   Strict environment isolation using versioned virtual environments.
#
# AI AGENT OPTIMIZATION:
#   - Quiet by default (Log-on-Fail)
#   - Structured markers: [SECTION-NAME] for navigation
#   - JSON output: [SUMMARY-JSON-BEGIN/END] with "failed_tests"
#   - Debug suggestions: [DEBUG-SUGGESTION] blocks
#   - Exit codes: [EXIT-CODE] N for CI integration
#   - No ANSI/Progress noise: Forced monochrome and no-progress bars
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

if [[ "${UV_PROJECT_ENVIRONMENT:-}" != "$TARGET_VENV" ]]; then
    if [[ "${TEST_ALREADY_PIVOTED:-}" == "1" ]]; then
        echo "Error: Detected re-execution loop. Aborting." >&2
        exit 1
    fi
    echo -e "\033[34m[INFO]\033[0m Pivoting to isolated environment: ${TARGET_VENV}"
    export UV_PROJECT_ENVIRONMENT="$TARGET_VENV"
    export TEST_ALREADY_PIVOTED=1
    unset VIRTUAL_ENV
    exec uv run --python "$PY_VERSION" bash "$0" "$@"
else
    unset TEST_ALREADY_PIVOTED
fi

# [SECTION: SETUP]
DEFAULT_COV_LIMIT=95
QUICK_MODE=false
CI_MODE=false
CLEAN_CACHE=true
VERBOSE=false
PYTEST_EXTRA_ARGS=()
IS_GHA="${GITHUB_ACTIONS:-false}"

if [[ "${NO_COLOR:-}" == "1" ]]; then
    RED=""; GREEN=""; YELLOW=""; BLUE=""; CYAN=""; BOLD=""; RESET=""
else
    RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"; BLUE="\033[34m"; CYAN="\033[36m"; BOLD="\033[1m"; RESET="\033[0m"
fi

log_group_start() { [[ "$IS_GHA" == "true" ]] && echo "::group::$1"; echo -e "\n${BOLD}${CYAN}=== $1 ===${RESET}"; }
log_group_end() { [[ "$IS_GHA" == "true" ]] && echo "::endgroup::"; return 0; }
log_info() { echo -e "${BLUE}[INFO]${RESET} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${RESET} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${RESET} $1"; }
log_err()  { echo -e "${RED}[ERROR]${RESET} $1" >&2; }

# CLI Args Parsing
while [[ $# -gt 0 ]]; do
    case "$1" in
        --quick)    QUICK_MODE=true; shift ;;
        --ci)       CI_MODE=true; shift ;;
        --no-clean) CLEAN_CACHE=false; shift ;;
        --verbose)  VERBOSE=true; shift ;;
        --)         shift; PYTEST_EXTRA_ARGS+=("$@"); break ;;
        *)          PYTEST_EXTRA_ARGS+=("$1"); shift ;;
    esac
done

# Auto-configure PYTHONPATH to include 'src' if it exists (Parity with lint.sh)
if [[ -d "src" ]]; then
    export PYTHONPATH="${PWD}/src:${PYTHONPATH:-}"
else
    export PYTHONPATH="${PWD}:${PYTHONPATH:-}"
fi

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
    
    if ! command -v pytest >/dev/null 2>&1; then
        echo "[ FAIL ] Tooling             : Pytest missing (uv sync required)"
        exit 1
    fi
    echo "[  OK  ] Tool Verified        : pytest"
    log_group_end
}
pre_flight_diagnostics

# Navigation
PROJECT_ROOT="$PWD"
while [[ "$PROJECT_ROOT" != "/" && ! -f "$PROJECT_ROOT/pyproject.toml" ]]; do
    PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
done
cd "$PROJECT_ROOT"

# Clean Caches
if [[ "$CLEAN_CACHE" == "true" ]]; then
    log_group_start "Housekeeping"
    rm -rf .pytest_cache
    rm -rf .hypothesis/unicode_data .hypothesis/constants
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    log_info "Test caches cleared."
    log_group_end
fi

# [SECTION: TARGETS]
TARGET_PKG=""
if [[ "$QUICK_MODE" == "false" && -d "src" ]]; then
    shopt -s nullglob
    dirs=(src/*/)
    shopt -u nullglob
    for d in "${dirs[@]}"; do
        base=$(basename "$d")
        if [[ "$base" != "__pycache__" && "$base" != *.egg-info ]]; then
            TARGET_PKG="$base"
            break
        fi
    done
fi

declare -a CMD=("pytest")

# forced agent-friendly defaults handled via env vars where possible
export NO_COLOR=1

if [[ "$CI_MODE" == "true" || "$VERBOSE" == "true" ]]; then
    CMD+=("-vv")
fi

# Always show hypothesis statistics (valuable for both Agents and Humans)
CMD+=("--hypothesis-show-statistics")

if [[ "$QUICK_MODE" == "true" ]]; then
    CMD+=("-q")
    log_info "Mode: QUICK (No Coverage)"
elif [[ -n "$TARGET_PKG" ]]; then
    CMD+=("--cov=src/$TARGET_PKG" "--cov-report=term-missing" "--cov-report=xml" "--cov-fail-under=$DEFAULT_COV_LIMIT")
    log_info "Mode: FULL (Coverage for '$TARGET_PKG' >= $DEFAULT_COV_LIMIT%)"
else
    log_warn "No package found in src/. Skipping coverage."
fi

CMD+=("${PYTEST_EXTRA_ARGS[@]}")

# Targets (Positional Args) Last
if [[ -d "tests" ]]; then CMD+=("tests"); fi
if [[ -d "test" ]]; then CMD+=("test"); fi

# [SECTION: EXECUTION]
log_group_start "Pytest Execution"
log_info "Command: ${CMD[*]@Q}"

LOG_FILE=$(mktemp)
trap 'rm -f "$LOG_FILE"' EXIT

START_TIME="${EPOCHREALTIME}"

# Execution Logic: Capture vs Stream
set +e
if [[ "$VERBOSE" == "true" ]]; then
    # Verbose: Stream to stdout using tee (agent sees everything as it happens)
    "${CMD[@]}" 2>&1 | tee "$LOG_FILE"
    EXIT_CODE=${PIPESTATUS[0]}
else
    # Quiet: Capture to file (agent sees nothing yet)
    "${CMD[@]}" > "$LOG_FILE" 2>&1
    EXIT_CODE=$?
fi
set -e

END_TIME="${EPOCHREALTIME}"
DURATION=$(printf "%.3f" "$(echo "$END_TIME - $START_TIME" | bc)")

# [SECTION: ANALYSIS]
HYPOTHESIS_FAILURE="false"
FALSIFYING_EXAMPLE=""
declare -a FAILED_TEST_LIST=()

# Extract test statistics
set +e
TESTS_PASSED=$(grep -o '[0-9]* passed' "$LOG_FILE" | tail -1 | grep -o '[0-9]*' || echo "0")
TESTS_FAILED=$(grep -o '[0-9]* failed' "$LOG_FILE" | tail -1 | grep -o '[0-9]*' || echo "0")
TESTS_SKIPPED=$(grep -o '[0-9]* skipped' "$LOG_FILE" | tail -1 | grep -o '[0-9]*' || echo "0")
COVERAGE_PCT=$(grep 'TOTAL' "$LOG_FILE" | tail -1 | awk '{print $NF}' | tr -d '%')
[[ -z "$TESTS_PASSED" ]] && TESTS_PASSED=0
[[ -z "$TESTS_FAILED" ]] && TESTS_FAILED=0
[[ -z "$TESTS_SKIPPED" ]] && TESTS_SKIPPED=0
[[ -z "$COVERAGE_PCT" ]] && COVERAGE_PCT=0

# Extract Failed Test IDs (for Debug Suggestion)
# Pattern: "FAILED tests/test_module.py::test_case - ..."
# We look for lines starting with FAILED (standard pytest without -p no:terminal might differ, but with -p no:terminal it's clean)
# With -p no:terminal, output is simpler. "FAILED test_path::test_name"
mapfile -t FAILED_TEST_LIST < <(grep -E "^FAILED " "$LOG_FILE" | cut -d' ' -f2 | sort -u)

# Hypothesis Check
if grep -q "Falsifying example" "$LOG_FILE"; then
    HYPOTHESIS_FAILURE="true"
    FALSIFYING_EXAMPLE=$(grep -A 5 "Falsifying example" "$LOG_FILE")
fi
set -e

# Output Logic
log_group_end

if [[ $EXIT_CODE -eq 0 ]]; then
    log_pass "All tests passed in $TARGET_VENV ($DURATION sec)."
else
    # On failure (if not verbose), we must now Dump the log for the agent
    log_group_start "Failure Details"
    if [[ "$VERBOSE" != "true" ]]; then
        cat "$LOG_FILE"
    else
        echo "(See stream above for details)"
    fi
    log_group_end
    
    if [[ "$HYPOTHESIS_FAILURE" == "true" ]]; then
        echo -e "\n${BOLD}${RED}[HYPOTHESIS FLAGGED LOGIC FLAW]${RESET}"
        echo -e "${YELLOW}Analyze this specific input:${RESET}"
        echo -e "$FALSIFYING_EXAMPLE"
    fi
fi

# [SECTION: REPORT]
# JSON Summary
log_group_start "Final Report"
echo "[SUMMARY-JSON-BEGIN]"
printf "{"
printf "\"result\":\"%s\"," "$([[ $EXIT_CODE -eq 0 ]] && echo pass || echo fail)"
printf "\"duration_sec\":\"%s\"," "$DURATION"
printf "\"tests_passed\":\"%s\"," "$TESTS_PASSED"
printf "\"tests_failed\":\"%s\"," "$TESTS_FAILED"
printf "\"tests_skipped\":\"%s\"," "$TESTS_SKIPPED"
printf "\"coverage_pct\":\"%s\"," "$COVERAGE_PCT"
printf "\"hypothesis_fail\":\"%s\"," "$HYPOTHESIS_FAILURE"
# Failed Tests Array
printf "\"failed_tests\":["
item_first=1
for item in "${FAILED_TEST_LIST[@]}"; do
    [[ $item_first -eq 0 ]] && printf ","
    printf "\"%s\"" "$item"
    item_first=0
done
printf "]"

printf ",\"exit_code\":%d}\n" "$EXIT_CODE"
echo "[SUMMARY-JSON-END]"

# Debug Suggestions
if [[ $EXIT_CODE -ne 0 && ${#FAILED_TEST_LIST[@]} -gt 0 ]]; then
    echo -e "\n${YELLOW}[DEBUG-SUGGESTION]${RESET}"
    echo "The following tests failed. Run this command to debug the first failure:"
    echo "  uv run pytest ${FAILED_TEST_LIST[0]} --pdb"
fi

if [[ $EXIT_CODE -ne 0 ]]; then
    log_err "Tests FAILED."
    echo "[EXIT-CODE] 1" >&2
    exit 1
else
    echo "[EXIT-CODE] 0" >&2
    exit 0
fi