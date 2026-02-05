#!/usr/bin/env bash
# HypoFuzz & Property Testing Interface
# Single entry point for all Hypothesis-based testing.
#
# Usage:
#   ./scripts/fuzz_hypofuzz.sh              Run fast property tests (default)
#   ./scripts/fuzz_hypofuzz.sh --deep       Run continuous HypoFuzz
#   ./scripts/fuzz_hypofuzz.sh --list       Show how to reproduce failures
#   ./scripts/fuzz_hypofuzz.sh --repro TEST Reproduce a specific test failure
#   ./scripts/fuzz_hypofuzz.sh --clean      Remove .hypothesis/ database
#   ./scripts/fuzz_hypofuzz.sh --help       Show this help
#
# Options:
#   --verbose                      Show detailed progress
#   --workers N                    Number of parallel workers (default: 4)
#   --time N                       Run for N seconds (deep mode)
#   --target FILE                  Specific test file (check mode)
#
# Note: This script is for Hypothesis/HypoFuzz testing. For Atheris native
# fuzzing, use ./scripts/fuzz_atheris.sh instead.
#
# Note: uses the standard project environment (.venv-3.13/.venv-3.14) defined by 'dev' group.

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
    --list          Show reproduction info and recent failures
    --clean         Remove .hypothesis/ database (with confirmation)
    --repro TEST    Reproduce a failing test with verbose output
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

    # Reproduce a specific failing test
    ./scripts/fuzz_hypofuzz.sh --repro test_parser_hypothesis::test_roundtrip

    # Reproduce all tests in a module
    ./scripts/fuzz_hypofuzz.sh --repro test_parser_hypothesis

NOTE:
    Hypothesis automatically stores and replays failing examples from
    .hypothesis/examples/. Simply re-running pytest will reproduce failures.
    Use --repro for verbose output and @example extraction.

    For Atheris native fuzzing, use ./scripts/fuzz_atheris.sh instead.
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
                echo -e "${RED}[ERROR] Missing test argument for --repro${NC}"
                echo "Usage: ./scripts/fuzz_hypofuzz.sh --repro <test_module::test_function>"
                exit 1
            fi
            if [[ "$MODE" == "repro" ]]; then
                REPRO_TEST="$2"
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
from datetime import datetime, timezone
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
skipped_match = re.search(r'(\d+) skipped', log_content)
hypo_count = log_content.count('Falsifying example')

tests_passed = int(passed_match.group(1)) if passed_match else 0
tests_failed = int(failed_match.group(1)) if failed_match else 0
tests_skipped = int(skipped_match.group(1)) if skipped_match else 0

# Extract individual test failures with details
failures = []
# Pattern: "FAILED tests/test_foo.py::test_bar" followed by error info
failed_test_pattern = r'FAILED (tests/[\w/]+\.py::\w+)'
failed_tests = re.findall(failed_test_pattern, log_content)

# For each failed test, try to extract error type and falsifying example
for test_path in failed_tests:
    failure_entry = {"test": test_path}

    # Find error type for this test
    # Pattern: "E   AssertionError:" or similar
    test_section_start = log_content.find(test_path)
    if test_section_start != -1:
        test_section = log_content[test_section_start:test_section_start + 2000]
        error_match = re.search(r'E\s+(\w+Error|\w+Exception):', test_section)
        if error_match:
            failure_entry["error_type"] = error_match.group(1)

    # Find falsifying example for this test
    if 'Falsifying example' in log_content:
        # Look for pattern: "Falsifying example: test_name("
        test_func = test_path.split("::")[-1] if "::" in test_path else ""
        example_pattern = rf'Falsifying example:\s*{re.escape(test_func)}\(([^\)]+)\)'
        example_match = re.search(example_pattern, log_content, re.DOTALL)
        if example_match:
            failure_entry["example"] = example_match.group(1).strip()[:500]

    failures.append(failure_entry)

# Extract first falsifying example (legacy field for backwards compatibility)
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
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'tests_passed': tests_passed,
    'tests_failed': tests_failed,
    'tests_skipped': tests_skipped,
    'hypothesis_failures': hypo_count,
    'falsifying_example': fail_ex,
    'failures': failures,
    'exit_code': exit_code
}
print('[SUMMARY-JSON-BEGIN]')
print(json.dumps(report, indent=2))
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

    if [[ -n "$TIME_LIMIT" ]]; then
        echo "Time Limit: ${TIME_LIMIT}s"
        echo "(Time limit enforcement relies on Ctrl+C or internal engine termination)"
    else
        echo "Time Limit: Until Ctrl+C"
    fi

    echo "Workers:    $WORKERS"
    echo ""

    # Log file for this session - append to preserve history
    LOG_FILE="$PROJECT_ROOT/.hypothesis/hypofuzz.log"
    mkdir -p "$PROJECT_ROOT/.hypothesis"

    # Add session header
    echo "" >> "$LOG_FILE"
    echo "================================================================================" >> "$LOG_FILE"
    echo "HypoFuzz Session: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG_FILE"
    echo "Workers: $WORKERS" >> "$LOG_FILE"
    echo "================================================================================" >> "$LOG_FILE"

    # Use tee to see output and save it
    set +e
    uv run hypothesis fuzz --no-dashboard -n "$WORKERS" tests/ 2>&1 | tee -a "$LOG_FILE"
    EXIT_CODE=${PIPESTATUS[0]}
    set -e

    # Count failures in this session
    # Note: grep -c outputs "0" on no match but exits 1, so we handle the exit code separately
    FAILURE_COUNT=$(grep -c "Falsifying example" "$LOG_FILE" 2>/dev/null) || FAILURE_COUNT=0

    if [[ $EXIT_CODE -eq 0 ]] || [[ $EXIT_CODE -eq 130 ]] || [[ $EXIT_CODE -eq 120 ]]; then
        # 0 = Done, 130 = SIGINT (Ctrl+C), 120 = HypoFuzz Interrupted
        echo -e "\n${GREEN}[STOPPED] Fuzzing session ended.${NC}"

        if [[ "$FAILURE_COUNT" -gt 0 ]]; then
            echo -e "${YELLOW}[FINDING]${NC} $FAILURE_COUNT falsifying example(s) found in this session."
            echo "  View log: cat $LOG_FILE"
            echo "  List failures: ./scripts/fuzz_hypofuzz.sh --list"
        fi

        # Event diversity analysis
        echo -e "\n${BLUE}[EVENT DIVERSITY]${NC}"
        python3 << EVENTEOF
import re
from pathlib import Path
from collections import Counter

log_path = Path("$LOG_FILE")
if not log_path.exists():
    print("  No log file found")
    exit(0)

try:
    log_content = log_path.read_text()
except Exception:
    print("  Could not read log file")
    exit(0)

# Extract all hypothesis.event() calls from log
# Events appear in various formats in Hypothesis/HypoFuzz output
event_patterns = [
    r"event\(['\"]([^'\"]+)['\"]\)",  # event('name')
    r"Observing: ([^\n]+)",  # HypoFuzz observation format
]

events = []
for pattern in event_patterns:
    events.extend(re.findall(pattern, log_content))

if events:
    counter = Counter(events)
    print(f"  Unique events discovered: {len(counter)}")
    print("  Top events:")
    for event_name, count in counter.most_common(15):
        print(f"    {event_name}: {count}")
    if len(counter) > 15:
        print(f"    ... and {len(counter) - 15} more")
else:
    print("  No hypothesis.event() calls detected in log")
    print("  Consider adding events to strategies and tests for better fuzzer guidance")
    print("  See: docs/FUZZING_GUIDE_HYPOFUZZ.md#semantic-coverage-with-events")
EVENTEOF

        # Rich JSON summary with failure details
        python3 << PYEOF
import json, re
from datetime import datetime, timezone
from pathlib import Path

log_path = Path("$LOG_FILE")
exit_code = $EXIT_CODE
failure_count = $FAILURE_COUNT

try:
    log_content = log_path.read_text() if log_path.exists() else ""
except Exception:
    log_content = ""

# Extract individual failures from log
failures = []
# Pattern: "Falsifying example: test_name(" with surrounding context
if failure_count > 0:
    # Find all falsifying example blocks
    example_pattern = r'Falsifying example:\s*(\w+)\(([^)]+)\)'
    for match in re.finditer(example_pattern, log_content):
        test_name = match.group(1)
        example_args = match.group(2).strip()[:500]
        failures.append({
            "test": test_name,
            "example": example_args
        })

report = {
    "mode": "deep",
    "status": "stopped",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "failures_count": failure_count,
    "failures": failures[:50],  # Limit to first 50 failures
    "exit_code": exit_code,
    "log_file": "$LOG_FILE"
}
print("[SUMMARY-JSON-BEGIN]")
print(json.dumps(report, indent=2))
print("[SUMMARY-JSON-END]")
PYEOF
    else
        echo -e "\n${RED}[ERROR] HypoFuzz exited with error code $EXIT_CODE${NC}"

        # Check for Common Mac Issue
        if grep -q "AF_UNIX path too long" "$LOG_FILE"; then
            echo -e "${YELLOW}Hint: 'AF_UNIX path too long' detected. TMPDIR is set to $TMPDIR.${NC}"
        fi

        python3 << PYEOF
import json
from datetime import datetime, timezone

report = {
    "mode": "deep",
    "status": "error",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "failures_count": $FAILURE_COUNT,
    "exit_code": $EXIT_CODE,
    "log_file": "$LOG_FILE"
}
print("[SUMMARY-JSON-BEGIN]")
print(json.dumps(report, indent=2))
print("[SUMMARY-JSON-END]")
PYEOF
        exit $EXIT_CODE
    fi
}

run_list() {
    EXAMPLES_DIR="$PROJECT_ROOT/.hypothesis/examples"
    FUZZ_LOG="$PROJECT_ROOT/.hypothesis/hypofuzz.log"

    echo -e "${BOLD}Hypothesis Failure Reproduction Info${NC}"
    echo ""

    echo -e "${BLUE}How Hypothesis failures work:${NC}"
    echo "  1. When a property test fails, Hypothesis shrinks to a minimal example"
    echo "  2. The shrunk example is stored in .hypothesis/examples/ (SHA-384 hashed)"
    echo "  3. On re-run, Hypothesis AUTOMATICALLY replays the stored failure"
    echo "  4. Simply running 'uv run pytest tests/' will reproduce all known failures"
    echo ""

    # Check if examples database exists
    if [[ -d "$EXAMPLES_DIR" ]]; then
        COUNT=$(find "$EXAMPLES_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')
        echo -e "${GREEN}[OK]${NC} .hypothesis/examples/ exists with $COUNT entries"
    else
        echo -e "${YELLOW}[WARN]${NC} No .hypothesis/examples/ directory found"
        echo "     Run some Hypothesis tests first to populate the database."
    fi
    echo ""

    # Check for HypoFuzz log
    if [[ -f "$FUZZ_LOG" ]]; then
        echo -e "${BLUE}Recent HypoFuzz session log:${NC} $FUZZ_LOG"
        # Check for failures in log
        # Note: grep -c outputs "0" on no match but exits 1, so we handle the exit code separately
        FAILURE_COUNT=$(grep -c "Falsifying example" "$FUZZ_LOG" 2>/dev/null) || FAILURE_COUNT=0
        if [[ "$FAILURE_COUNT" -gt 0 ]]; then
            echo -e "${YELLOW}[FINDING]${NC} Found $FAILURE_COUNT falsifying example(s) in log"
            echo ""
            echo "Recent failures:"
            grep -B2 "Falsifying example" "$FUZZ_LOG" | tail -20
        else
            echo "  No failures recorded in latest session."
        fi
    else
        echo -e "${BLUE}HypoFuzz log:${NC} Not found (run --deep to create)"
    fi
    echo ""

    echo -e "${BOLD}To reproduce a specific failing test:${NC}"
    echo "  ./scripts/fuzz_hypofuzz.sh --repro test_module::test_function"
    echo ""
    echo -e "${BOLD}To reproduce all failures:${NC}"
    echo "  uv run pytest tests/ -x -v"
    echo ""
    echo -e "${BOLD}To extract @example decorator:${NC}"
    echo "  uv run python scripts/fuzz_hypofuzz_repro.py --example test_module::test_function"
}

run_clean() {
    HYPOTHESIS_DIR="$PROJECT_ROOT/.hypothesis"
    FUZZ_LOG="$HYPOTHESIS_DIR/hypofuzz.log"

    if [[ ! -d "$HYPOTHESIS_DIR" ]]; then
        echo "No .hypothesis/ directory found. Nothing to clean."
        return 0
    fi

    # Count entries
    EXAMPLE_COUNT=$(find "$HYPOTHESIS_DIR/examples" -type f 2>/dev/null | wc -l | tr -d ' ')

    echo -e "${BOLD}Hypothesis Database Cleanup${NC}"
    echo ""
    echo "Directory: $HYPOTHESIS_DIR"
    echo "Examples:  $EXAMPLE_COUNT cached entries"
    if [[ -f "$FUZZ_LOG" ]]; then
        echo "Log:       $(wc -l < "$FUZZ_LOG" | tr -d ' ') lines"
    fi
    echo ""
    echo -e "${YELLOW}WARNING:${NC} Removing .hypothesis/ will:"
    echo "  - Delete all cached examples (regression database)"
    echo "  - Delete any shrunk failure examples"
    echo "  - Require tests to rediscover edge cases"
    echo ""

    # Prompt for confirmation
    read -r -p "Remove .hypothesis/ directory? (y/N): " response
    case "$response" in
        [yY][eE][sS]|[yY])
            rm -rf "$HYPOTHESIS_DIR"
            echo -e "${GREEN}[OK]${NC} Removed .hypothesis/ directory"
            ;;
        *)
            echo "Cancelled."
            ;;
    esac
}

run_repro() {
    if [[ -z "$REPRO_TEST" ]]; then
        echo -e "${RED}[ERROR] Missing test argument for --repro${NC}"
        echo "Usage: ./scripts/fuzz_hypofuzz.sh --repro <test_module::test_function>"
        echo ""
        echo "Examples:"
        echo "  ./scripts/fuzz_hypofuzz.sh --repro test_parser_hypothesis::test_roundtrip"
        echo "  ./scripts/fuzz_hypofuzz.sh --repro test_parser_hypothesis"
        exit 1
    fi

    echo -e "${BOLD}Reproducing Hypothesis Failure...${NC}"
    echo "Test: $REPRO_TEST"
    echo ""

    # Use the fuzz_hypofuzz_repro.py script
    uv run python scripts/fuzz_hypofuzz_repro.py --verbose --example "$REPRO_TEST"
    EXIT_CODE=$?

    if [[ $EXIT_CODE -eq 0 ]]; then
        echo ""
        echo -e "${GREEN}[PASS]${NC} Test passed - no failure to reproduce."
        echo "If you expected a failure, the bug may have been fixed or the"
        echo ".hypothesis/examples/ database may need to be cleared."
    fi

    return $EXIT_CODE
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
