#!/usr/bin/env bash
# ==============================================================================
# test.sh — Deterministic Hybrid (AI/Human) Test Runner
# ==============================================================================
# COMPATIBILITY: Bash v5.0+
# ==============================================================================

# --- 0. PRE-FLIGHT CHECKS & SAFETY ---
if ((BASH_VERSINFO[0] < 5)); then
    echo "::error::[FATAL] Bash v5.0+ required. Found: ${BASH_VERSION}"
    exit 1
fi

# Strict Modes (Guaranteed ON)
set -o errexit
set -o nounset
set -o pipefail

# --- 1. SETUP & UTILS ---
DEFAULT_COV_LIMIT=95
QUICK_MODE=false
CI_MODE=false
CLEAN_CACHE=true
PYTEST_EXTRA_ARGS=()
IS_GHA="${GITHUB_ACTIONS:-false}"

# Colors
if [[ "${NO_COLOR:-}" == "1" ]]; then
    RED=""; GREEN=""; YELLOW=""; BLUE=""; CYAN=""; BOLD=""; RESET=""
else
    RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"
    BLUE="\033[34m"; CYAN="\033[36m"; BOLD="\033[1m"; RESET="\033[0m"
fi

log_group_start() { [[ "$IS_GHA" == "true" ]] && echo "::group::$1"; echo -e "\n${BOLD}${CYAN}=== $1 ===${RESET}"; }
log_group_end() { [[ "$IS_GHA" == "true" ]] && echo "::endgroup::"; return 0; }
log_info() { echo -e "${BLUE}[INFO]${RESET} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${RESET} $1"; }
log_err()  { echo -e "${RED}[ERROR]${RESET} $1" >&2; }
log_pass() { echo -e "${GREEN}[PASS]${RESET} $1"; }

# CLI Args Parsing
while [[ $# -gt 0 ]]; do
    case "$1" in
        --quick)    QUICK_MODE=true; shift ;;
        --ci)       CI_MODE=true; shift ;;
        --no-clean) CLEAN_CACHE=false; shift ;;
        --)         shift; PYTEST_EXTRA_ARGS+=("$@"); break ;;
        *)          PYTEST_EXTRA_ARGS+=("$1"); shift ;;
    esac
done

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
    
    # Direct tool verification
    if ! pytest --version >/dev/null 2>&1; then
        echo "[ FAIL ] Tooling             : Pytest missing (Execute 'uv sync')"
        exit 1
    fi
    echo "[  OK  ] Tooling             : Pytest verified"
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
    rm -rf .pytest_cache .hypothesis
    set +e # Guard against find failing on permissions or non-existent files
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
    set -e
    log_info "Test caches cleared."
    log_group_end
fi

# Safe Package Detection
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
if [[ -d "tests" ]]; then CMD+=("tests"); fi
if [[ -d "test" ]]; then CMD+=("test"); fi

if [[ "$CI_MODE" == "true" ]]; then
    CMD+=("--verbose")
else
    CMD+=("--hypothesis-show-statistics")
fi

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

log_group_start "Pytest Execution"
log_info "Command: ${CMD[*]@Q}"

LOG_FILE=$(mktemp)
trap 'rm -f "$LOG_FILE"' EXIT

START_TIME="${EPOCHREALTIME}"

# Run Pytest: Disable errexit for the actual command execution
set +e
# The 'tee' ensures output is displayed AND written to the log file.
"${CMD[@]}" 2>&1 | tee "$LOG_FILE"
EXIT_CODE=${PIPESTATUS[0]}
set -e

END_TIME="${EPOCHREALTIME}"
DURATION=$(printf "%.3f" "$(echo "$END_TIME - $START_TIME" | bc)")

log_group_end

# --- 3. ANALYSIS & REPORT ---
log_group_start "Analysis"
HYPOTHESIS_FAILURE="false"
FALSIFYING_EXAMPLE=""

# Extract test statistics from pytest output
set +e
TESTS_PASSED=$(grep -o '[0-9]* passed' "$LOG_FILE" | tail -1 | grep -o '[0-9]*' || echo "0")
TESTS_FAILED=$(grep -o '[0-9]* failed' "$LOG_FILE" | tail -1 | grep -o '[0-9]*' || echo "0")
TESTS_SKIPPED=$(grep -o '[0-9]* skipped' "$LOG_FILE" | tail -1 | grep -o '[0-9]*' || echo "0")
COVERAGE_PCT=$(grep 'TOTAL' "$LOG_FILE" | tail -1 | awk '{print $NF}' | tr -d '%')
[[ -z "$TESTS_PASSED" ]] && TESTS_PASSED=0
[[ -z "$TESTS_FAILED" ]] && TESTS_FAILED=0
[[ -z "$TESTS_SKIPPED" ]] && TESTS_SKIPPED=0
[[ -z "$COVERAGE_PCT" ]] && COVERAGE_PCT=0
set -e

# Disable errexit for grep, as non-match returns exit 1
set +e
if grep -q "Falsifying example" "$LOG_FILE"; then
    HYPOTHESIS_FAILURE="true"
    FALSIFYING_EXAMPLE=$(grep -A 5 "Falsifying example" "$LOG_FILE")
fi
set -e

if [[ "$HYPOTHESIS_FAILURE" == "true" ]]; then
    echo -e "\n${BOLD}${RED}╔════════════════════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${RED}║            HYPOTHESIS DETECTED A LOGIC FLAW                ║${RESET}"
    echo -e "${BOLD}${RED}╚════════════════════════════════════════════════════════════╝${RESET}"
    echo -e "${YELLOW}AI Agent: analyze this specific input:${RESET}"
    echo -e "$FALSIFYING_EXAMPLE"
fi

STATUS_STR="pass"
[[ $EXIT_CODE -ne 0 ]] && STATUS_STR="fail"

echo "[SUMMARY-JSON-BEGIN]"
printf "{"
printf "\"result\":\"%s\"," "$STATUS_STR"
printf "\"exit_code\":\"%d\"," "$EXIT_CODE"
printf "\"duration_sec\":\"%s\"," "$DURATION"
printf "\"tests_passed\":\"%s\"," "$TESTS_PASSED"
printf "\"tests_failed\":\"%s\"," "$TESTS_FAILED"
printf "\"tests_skipped\":\"%s\"," "$TESTS_SKIPPED"
printf "\"coverage_pct\":\"%s\"," "$COVERAGE_PCT"
printf "\"hypothesis_fail\":\"%s\"" "$HYPOTHESIS_FAILURE"
printf "}\n"
echo "[SUMMARY-JSON-END]"

echo "[END-TEST]"
exit $EXIT_CODE