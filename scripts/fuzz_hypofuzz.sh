#!/usr/bin/env bash
# HypoFuzz & Property Testing Interface
# Single entry point for all Hypothesis-based testing.
#
# Usage:
#   ./scripts/fuzz_hypofuzz.sh              Run fast property tests (default)
#   ./scripts/fuzz_hypofuzz.sh --deep       Run continuous HypoFuzz
#   ./scripts/fuzz_hypofuzz.sh --list       List captured failures
#   ./scripts/fuzz_hypofuzz.sh --repro FILE Generate @example from failure
#   ./scripts/fuzz_hypofuzz.sh --clean      Remove captured failures
#   ./scripts/fuzz_hypofuzz.sh --help       Show this help
#
# Options:
#   --verbose                      Show detailed progress
#   --workers N                    Number of parallel workers (default: 4)
#   --time N                       Run for N seconds (deep mode)
#   --target FILE                  Specific test file (check mode)
#
# Note: uses the standard proejct environment (.venv-3.13/.venv-3.14) defined by 'dev' group.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# REQUIRED: Force TMPDIR to /tmp to avoid "AF_UNIX path too long" on macOS with HypoFuzz
export TMPDIR="/tmp"

# Defaults
MODE="check"
VERBOSE=false
WORKERS=4
TIME_LIMIT=""
TARGET=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

disable_colors() {
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    BOLD=''
    NC=''
}

# Disable colors if not a terminal
if [[ ! -t 1 ]]; then
    disable_colors
fi

show_help() {
    cat << EOF
HypoFuzz & Property Testing Interface for FTLLexEngine

USAGE:
    ./scripts/fuzz_hypofuzz.sh [MODE] [OPTIONS]

MODES:
    (default)       Fast property tests (pytest with Hypothesis)
    --deep          Continuous coverage-guided fuzzing (HypoFuzz)
    --list          List all captured failures (.hypothesis/failures)
    --clean         Remove all captured failures
    --repro FILE    Reproduce a failure and generate @example decorator
    --help          Show this help message

OPTIONS:
    --verbose       Show detailed progress during tests
    --workers N     Number of parallel workers (default: 4)
    --time N        Time limit in seconds (for --deep)
    --target FILE   Specific test file to run (check mode only)

EXAMPLES:
    # Quick check before committing (recommended)
    ./scripts/fuzz_hypofuzz.sh

    # Deep fuzzing for 5 minutes
    ./scripts/fuzz_hypofuzz.sh --deep --time 300

    # Reproduce a failure
    ./scripts/fuzz_hypofuzz.sh --repro .hypothesis/failures/failures_20260120.txt
EOF
}

# Strict Argument Parser
while [[ $# -gt 0 ]]; do
    case "$1" in
        --deep|--list|--clean|--repro)
            if [[ "$MODE" != "check" && "$MODE" != "${1#--}" ]]; then
                echo -e "${RED}[ERROR] Conflicting modes selected: $MODE vs ${1#--}${NC}"
                exit 1
            fi
            MODE="${1#--}" # strip leading --
            if [[ "$MODE" == "repro" && -z "${2:-}" ]]; then
                echo -e "${RED}[ERROR] Missing file argument for --repro${NC}"
                exit 1
            fi
            if [[ "$MODE" == "repro" ]]; then
                REPRO_FILE="$2"
                shift
            fi
            shift
            ;;
        --verbose|-v) VERBOSE=true; shift ;;
        --workers) WORKERS="$2"; shift 2 ;;
        --time) TIME_LIMIT="$2"; shift 2 ;;
        --target) TARGET="$2"; shift 2 ;;
        --help|-h) show_help; exit 0 ;;
        *)
            echo "Unknown option: $1"
            echo "Run './scripts/fuzz_hypofuzz.sh --help' for usage."
            exit 2
            ;;
    esac
done

# [SECTION: SIGNAL_HANDLING]
PID_LIST=()
cleanup() {
    if [[ ${#PID_LIST[@]} -gt 0 ]]; then
        for pid in "${PID_LIST[@]}"; do
            kill -TERM "$pid" 2>/dev/null || true
        done
        wait
    fi
}
trap cleanup EXIT INT TERM

# =============================================================================
# Subroutines
# =============================================================================

# =============================================================================
# Pre-Flight Diagnostics
# =============================================================================

run_diagnostics() {
    echo -e "\n${BOLD}============================================================${NC}"
    echo -e "${BOLD}Hypothesis Diagnostic Check${NC}"
    echo -e "Env: ${BLUE}Default (dev)${NC}"
    echo -e "${BOLD}============================================================${NC}\n"

    local python_bin
    python_bin=$(uv run python -c "import sys; print(sys.executable)" 2>/dev/null)
    local python_version
    python_version=$("$python_bin" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)

    echo -n "Python Version... "
    echo -e "${GREEN}$python_version${NC}"

    echo -n "Hypothesis Spec... "
    if "$python_bin" -c "import hypothesis; print(hypothesis.__version__)" &>/dev/null; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}MISSING${NC}"
        echo "Run 'uv sync' to install dependencies."
        exit 1
    fi
    
    echo -e "\n${BOLD}============================================================${NC}"
    echo -e "${GREEN}[OK]${NC} System is ready."
    echo -e "${BOLD}============================================================${NC}\n"
}

run_check() {
    run_diagnostics
    echo -e "${BOLD}Running Property Tests...${NC}"
    
    # Set profile based on verbose flag
    if [[ "$VERBOSE" == "true" ]]; then
        export HYPOTHESIS_PROFILE="verbose"
    fi

    # Determine target
    TEST_TARGET="${TARGET:-tests/}"

    # Verify target exists
    if [[ ! -e "$TEST_TARGET" ]]; then
        echo -e "${RED}[ERROR] Target not found: $TEST_TARGET${NC}"
        exit 1
    fi

    echo "Target: $TEST_TARGET"
    if [[ "$VERBOSE" == "true" ]]; then
        echo "Profile: verbose"
    else
        echo "Profile: default (silent)"
    fi
    echo ""

    # Log Capture Setup
    TEMP_LOG="/tmp/fuzz_check_$$.log"
    # Ensure log is cleared on return
    # Note: Global trap handles exit, this local one handles function return hygiene if needed,
    # but strictly traps are global in bash. We'll handle cleanup manually at end of function.
    
    CMD=(uv run pytest "$TEST_TARGET" -v --tb=short)
    
    set +e
    if [[ "$VERBOSE" == "true" ]]; then
         "${CMD[@]}" 2>&1 | tee "$TEMP_LOG"
         EXIT_CODE=${PIPESTATUS[0]}
    else
         # Quick mode: Capture output silently
         "${CMD[@]}" > "$TEMP_LOG" 2>&1
         EXIT_CODE=$?
    fi
    set -e

    # Robust Log Parsing via Python (Backported and Hardened)
    python3 << PYEOF
import sys, json, re
from pathlib import Path

log_path = Path("$TEMP_LOG")
exit_code = $EXIT_CODE

try:
    log_content = log_path.read_text() if log_path.exists() else ""
except Exception:
    log_content = ""

# Parse metrics safely
passed_match = re.search(r'(\d+) passed', log_content)
failed_match = re.search(r'(\d+) failed', log_content)
hypo_count = log_content.count('Falsifying example')

tests_passed = int(passed_match.group(1)) if passed_match else 0
tests_failed = int(failed_match.group(1)) if failed_match else 0

# Extract first falsifying example
fail_ex = ""
if 'Falsifying example' in log_content:
    try:
        # Robust extraction
        fail_ex = log_content.split('Falsifying example')[1].split('\n')[0][:200].strip()
    except IndexError:
        pass

# Determine correct status
# 0 = Pass
# 1 = Failure (Tests failed)
# 130 = SIGINT/Ctrl+C
# 2 = Interrupted/KeyboardInterrupt (Pytest specific)
if exit_code == 0:
    status = 'pass'
elif exit_code in (130, 2):
    status = 'stopped'
elif tests_failed > 0 or hypo_count > 0:
    status = 'finding'
else:
    status = 'error'

report = {
    'mode': 'check',
    'status': status,
    'tests_passed': tests_passed,
    'tests_failed': tests_failed,
    'hypothesis_failures': hypo_count,
    'falsifying_example': fail_ex,
    'exit_code': exit_code
}
print('[SUMMARY-JSON-BEGIN]')
print(json.dumps(report))
print('[SUMMARY-JSON-END]')
PYEOF

    # Visual Feedback
    if [[ $EXIT_CODE -eq 0 ]]; then
        echo -e "\n${GREEN}[PASS] All property tests passed.${NC}"
    elif [[ $EXIT_CODE -eq 130 ]] || [[ $EXIT_CODE -eq 2 ]]; then
        echo -e "\n${YELLOW}[STOPPED] Run interrupted by user.${NC}"
    elif [[ $EXIT_CODE -eq 1 ]]; then
        echo -e "\n${RED}[FAIL] Failures detected!${NC}"
        echo "See JSON summary above for details."
        if [[ "$VERBOSE" == "false" ]]; then
            echo -e "${YELLOW}Failure output:${NC}"
            # Only grep if file exists and has content
            if [[ -s "$TEMP_LOG" ]]; then
                grep -A 20 "Falsifying example" "$TEMP_LOG" || head -n 20 "$TEMP_LOG"
            fi
        fi
    else
        echo -e "\n${RED}[ERROR] Test execution failed (code $EXIT_CODE).${NC}"
    fi

    rm -f "$TEMP_LOG"
    return $EXIT_CODE
}

run_deep() {
    run_diagnostics
    echo -e "${BOLD}Running Continuous HypoFuzz...${NC}"
    
    # Build args
    EXTRA_ARGS=""
    if [[ -n "$TIME_LIMIT" ]]; then
        echo "Time Limit: ${TIME_LIMIT}s"
        echo "(Time limit enforcement relies on Ctrl+C or internal engine termination)"
    else
        echo "Time Limit: Until Ctrl+C"
    fi

    echo "Workers:    $WORKERS"
    echo ""

    LOG_FILE=".hypothesis/fuzz.log"
    mkdir -p ".hypothesis"

    # Use tee to see output and save it
    # We use 'uv run hypothesis fuzz'
    set +e
    uv run hypothesis fuzz --no-dashboard -n "$WORKERS" tests/ 2>&1 | tee "$LOG_FILE"
    EXIT_CODE=${PIPESTATUS[0]}
    set -e

    if [[ $EXIT_CODE -eq 0 ]] || [[ $EXIT_CODE -eq 130 ]] || [[ $EXIT_CODE -eq 120 ]]; then
        # 0 = Done, 130 = SIGINT (Ctrl+C), 120 = HypoFuzz Interrupted
        echo -e "\n${GREEN}[STOPPED] Fuzzing session ended by user.${NC}"
        
        # Simple JSON summary for agents
        echo '[SUMMARY-JSON-BEGIN]{"mode":"deep", "status":"stopped", "exit_code":'"$EXIT_CODE"'}[SUMMARY-JSON-END]'
    else
        echo -e "\n${RED}[ERROR] HypoFuzz exited with error code $EXIT_CODE${NC}"
        
        # Check for Common Mac Issue
        if grep -q "AF_UNIX path too long" "$LOG_FILE"; then
            echo -e "${YELLOW}Hint: 'AF_UNIX path too long' detected. TMPDIR is set to $TMPDIR.${NC}"
        fi
        
        echo '[SUMMARY-JSON-BEGIN]{"mode":"deep", "status":"error", "exit_code":'"$EXIT_CODE"'}[SUMMARY-JSON-END]'
        exit $EXIT_CODE
    fi
}

run_list() {
    FAILURES_DIR="$PROJECT_ROOT/.hypothesis/failures"
    
    echo -e "${BOLD}Captured Failures (Hypothesis/HypoFuzz)${NC}"
    
    if [[ -d "$FAILURES_DIR" ]]; then
        COUNT=$(find "$FAILURES_DIR" -name "failures_*.txt" -type f 2>/dev/null | wc -l | tr -d ' ')
        if [[ $COUNT -gt 0 ]]; then
            echo "Found $COUNT failure file(s) in $FAILURES_DIR:"
            echo ""
            ls -lt "$FAILURES_DIR"/failures_*.txt | head -10 | awk '{print "  " $NF}'
            echo ""
            echo "View latest:"
            echo "  cat $(ls -t "$FAILURES_DIR"/failures_*.txt | head -1)"
            echo "Reproduce:"
            echo "  ./scripts/fuzz_hypofuzz.sh --repro $(ls -t "$FAILURES_DIR"/failures_*.txt | head -1)"
        else
            echo "No failures found."
        fi
    else
        echo "No .hypothesis/failures directory found."
    fi
}

run_clean() {
    FAILURES_DIR="$PROJECT_ROOT/.hypothesis/failures"
    if [[ -d "$FAILURES_DIR" ]]; then
        rm -rf "$FAILURES_DIR"
        echo -e "${GREEN}Cleaned up failures directory.${NC}"
    else
        echo "Nothing to clean."
    fi
}

run_repro() {
    if [[ -z "$REPRO_FILE" ]]; then
        echo -e "${RED}[ERROR] Missing file argument for --repro${NC}"
        echo "Usage: ./scripts/fuzz_hypofuzz.sh --repro <path_to_failure_file>"
        exit 1
    fi

    if [[ ! -f "$REPRO_FILE" ]]; then
        echo -e "${RED}[ERROR] File not found: $REPRO_FILE${NC}"
        exit 1
    fi

    echo -e "${BOLD}Reproducing Failure...${NC}"
    # Use the existing repro.py script, but run it in the standard environment
    uv run python scripts/repro.py "$REPRO_FILE"
    
    # Generate Helper
    if command -v xxd >/dev/null; then
        CRASH_CONTENT=$(xxd -p "$REPRO_FILE" | tr -d '\n')
        echo ""
        echo -e "${YELLOW}To add as @example decorator:${NC}"
        echo "  @example(bytes.fromhex('$CRASH_CONTENT'))"
        echo ""
    fi
}

# =============================================================================
# Main Dispatch
# =============================================================================

case "$MODE" in
    check)
        run_check
        ;;
    deep)
        run_deep
        ;;
    list)
        run_list
        ;;
    clean)
        run_clean
        ;;
    repro)
        run_repro
        ;;
    *)
        echo "Invalid mode"
        exit 1
        ;;
esac
