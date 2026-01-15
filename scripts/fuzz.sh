#!/usr/bin/env bash
# Unified Fuzzing Interface
# Single entry point for all fuzzing operations.
#
# Usage:
#   ./scripts/fuzz.sh              Run fast property tests (default)
#   ./scripts/fuzz.sh --deep       Run continuous HypoFuzz
#   ./scripts/fuzz.sh --native     Run Atheris native fuzzing
#   ./scripts/fuzz.sh --perf       Run performance fuzzing (Atheris)
#   ./scripts/fuzz.sh --list       List captured failures
#   ./scripts/fuzz.sh --corpus     Check corpus health
#   ./scripts/fuzz.sh --help       Show this help
#
# Options:
#   --json                         Output JSON summary (for CI)
#   --verbose                      Show detailed progress
#   --workers N                    Number of parallel workers (default: 4)
#   --time N                       Run for N seconds (deep/native modes)
#
# See docs/FUZZING_GUIDE.md for detailed documentation.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Defaults
MODE="check"
JSON_OUTPUT=false
VERBOSE=false
WORKERS=4
TIME_LIMIT=""
TARGET=""

# Colors (disabled if not a terminal or if --json)
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

# Check Python version for Atheris compatibility (requires Python 3.11-3.13)
check_atheris_python_version() {
    local py_version
    py_version=$(uv run python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)

    # Compare version - 3.14 and higher are not supported
    if [[ "$py_version" == "3.14" ]] || [[ "$py_version" > "3.14" ]]; then
        if [[ "$JSON_OUTPUT" == "true" ]]; then
            echo '{"mode":"'"$MODE"'","status":"error","error":"python_version_unsupported","python_version":"'"$py_version"'"}'
            exit 3
        else
            echo -e "${RED}[ERROR]${NC} Python $py_version is not supported by Atheris."
            echo ""
            echo "Atheris native fuzzing requires Python 3.11-3.13."
            echo "Python 3.14+ is not yet supported by the Atheris project."
            echo ""
            echo "Options:"
            echo "  1. Switch to Python 3.13:"
            echo "     uv run --python 3.13 ./scripts/fuzz.sh $MODE"
            echo ""
            echo "  2. Use property-based fuzzing (works on Python 3.14):"
            echo "     ./scripts/fuzz.sh          # Hypothesis tests"
            echo "     ./scripts/fuzz.sh --deep   # HypoFuzz coverage"
            echo ""
            echo "See docs/FUZZING_GUIDE.md for Python version requirements."
            exit 3
        fi
    fi
}

# Disable colors if not a terminal
if [[ ! -t 1 ]]; then
    disable_colors
fi

show_help() {
    cat << 'EOF'
Unified Fuzzing Interface for FTLLexEngine

USAGE:
    ./scripts/fuzz.sh [MODE] [OPTIONS]

MODES:
    (default)       Fast property tests (500 examples, ~2 min)
    --deep          Continuous coverage-guided fuzzing (HypoFuzz)
    --native        Native fuzzing with Atheris (requires setup)
    --structured    Structure-aware fuzzing with Atheris (requires setup)
    --perf          Performance fuzzing to detect ReDoS (Atheris)
    --minimize FILE Minimize a crash file to smallest reproducer (libFuzzer)
    --list          List all captured failures
    --clean         Remove all captured failures and crash artifacts
    --corpus        Check seed corpus health
    --repro FILE    Reproduce a crash and generate @example decorator
    --help          Show this help message

OPTIONS:
    --json          Output JSON summary instead of human-readable
    --verbose       Show detailed progress during tests
    --workers N     Number of parallel workers (default: 4)
    --time N        Time limit in seconds (for --deep, --native, --perf)
    --target FILE   Specific test file to run (check mode only)

EXAMPLES:
    # Quick check before committing (recommended)
    ./scripts/fuzz.sh

    # Verbose mode to see what's being tested
    ./scripts/fuzz.sh --verbose

    # Deep fuzzing for 5 minutes
    ./scripts/fuzz.sh --deep --time 300

    # Native fuzzing for security audit
    ./scripts/fuzz.sh --native --time 60

    # Structure-aware fuzzing (better coverage)
    ./scripts/fuzz.sh --structured --time 60

    # Reproduce a crash and get @example decorator
    ./scripts/fuzz.sh --repro .fuzz_corpus/crash_xxx

    # Minimize a crash to smallest reproducer
    ./scripts/fuzz.sh --minimize .fuzz_corpus/crash_xxx

    # Check for any captured failures
    ./scripts/fuzz.sh --list

EXIT CODES:
    0   All tests passed, no findings
    1   Findings detected (failures or crashes)
    2   Error (script or environment failure)
    3   Python version incompatible (Atheris requires 3.11-3.13)

See docs/FUZZING_GUIDE.md for detailed documentation.
EOF
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --deep)
            MODE="deep"
            shift
            ;;
        --native)
            MODE="native"
            shift
            ;;
        --perf)
            MODE="perf"
            shift
            ;;
        --structured)
            MODE="structured"
            shift
            ;;
        --repro)
            MODE="repro"
            REPRO_FILE="$2"
            shift 2
            ;;
        --minimize)
            MODE="minimize"
            MINIMIZE_FILE="$2"
            shift 2
            ;;
        --list)
            MODE="list"
            shift
            ;;
        --clean)
            MODE="clean"
            shift
            ;;
        --corpus)
            MODE="corpus"
            shift
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        --json)
            JSON_OUTPUT=true
            disable_colors
            shift
            ;;
        --verbose|-v)
            VERBOSE=true
            shift
            ;;
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        --time)
            TIME_LIMIT="$2"
            shift 2
            ;;
        --target)
            TARGET="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            echo "Run './scripts/fuzz.sh --help' for usage."
            exit 2
            ;;
    esac
done

# Header (human-readable mode only)
print_header() {
    if [[ "$JSON_OUTPUT" == "false" ]]; then
        echo ""
        echo -e "${BOLD}============================================================${NC}"
        echo -e "${BOLD}FTLLexEngine Fuzzing${NC}"
        echo -e "${BOLD}============================================================${NC}"
        echo ""
    fi
}

# Status indicators
print_pass() {
    if [[ "$JSON_OUTPUT" == "false" ]]; then
        echo -e "${GREEN}[PASS]${NC} $1"
    fi
}

print_finding() {
    if [[ "$JSON_OUTPUT" == "false" ]]; then
        echo -e "${RED}[FINDING]${NC} $1"
    fi
}

print_info() {
    if [[ "$JSON_OUTPUT" == "false" ]]; then
        echo -e "${BLUE}[INFO]${NC} $1"
    fi
}

print_warn() {
    if [[ "$JSON_OUTPUT" == "false" ]]; then
        echo -e "${YELLOW}[WARN]${NC} $1"
    fi
}

# Mode: check (default) - Fast property tests
run_check() {
    print_header

    if [[ "$JSON_OUTPUT" == "false" ]]; then
        echo -e "Mode:    ${BOLD}Fast Property Tests${NC}"
        if [[ -n "$TARGET" ]]; then
            echo "Target:  $TARGET"
        else
            echo "Target:  tests/test_grammar_based_fuzzing.py"
        fi
        if [[ "$VERBOSE" == "true" ]]; then
            echo "Profile: verbose (shows progress)"
        else
            echo "Profile: dev (500 examples, silent)"
        fi
        echo ""
        echo -e "${BLUE}Running...${NC} (use --verbose for detailed output)"
        echo ""
    fi

    # Set profile based on verbose flag
    if [[ "$VERBOSE" == "true" ]]; then
        export HYPOTHESIS_PROFILE="verbose"
    fi

    # Determine target
    TEST_TARGET="${TARGET:-tests/test_grammar_based_fuzzing.py}"

    # Start progress indicator in non-verbose, non-JSON mode
    PROGRESS_PID=""
    if [[ "$VERBOSE" == "false" && "$JSON_OUTPUT" == "false" ]]; then
        (while true; do sleep 10; echo -n "."; done) &
        PROGRESS_PID=$!
    fi

    # Run pytest
    set +e
    if [[ "$JSON_OUTPUT" == "true" ]]; then
        OUTPUT=$(uv run pytest "$TEST_TARGET" -v --tb=short 2>&1)
        EXIT_CODE=$?
    else
        OUTPUT=$(uv run pytest "$TEST_TARGET" -v --tb=short 2>&1 | tee /dev/stderr)
        EXIT_CODE=${PIPESTATUS[0]}
    fi
    set -e

    # Stop progress indicator
    if [[ -n "$PROGRESS_PID" ]]; then
        kill "$PROGRESS_PID" 2>/dev/null || true
        wait "$PROGRESS_PID" 2>/dev/null || true
        echo ""  # Newline after dots
    fi

    # Parse results (use head -1 to ensure single value, || true to avoid exit on no match)
    TESTS_PASSED=$(echo "$OUTPUT" | grep -oE '[0-9]+ passed' | head -1 | grep -oE '[0-9]+' || echo "0")
    TESTS_FAILED=$(echo "$OUTPUT" | grep -oE '[0-9]+ failed' | head -1 | grep -oE '[0-9]+' || echo "0")
    # grep -c outputs "0" with exit code 1 when no match; || true prevents double output
    HYPOTHESIS_FAILURES=$(echo "$OUTPUT" | grep -c "Falsifying example:" 2>/dev/null || true)
    HYPOTHESIS_FAILURES=${HYPOTHESIS_FAILURES:-0}

    TESTS_PASSED=${TESTS_PASSED:-0}
    TESTS_FAILED=${TESTS_FAILED:-0}
    HYPOTHESIS_FAILURES=${HYPOTHESIS_FAILURES:-0}

    # Extract first failure details for JSON output
    FIRST_FAILURE_TEST=""
    FIRST_FAILURE_INPUT=""
    FIRST_FAILURE_ERROR=""
    if [[ $TESTS_FAILED -gt 0 ]] || [[ $HYPOTHESIS_FAILURES -gt 0 ]]; then
        # Extract failing test name (e.g., "test_parser_handles_input")
        FIRST_FAILURE_TEST=$(echo "$OUTPUT" | grep -oE 'FAILED [^:]+::[^[ ]+' | head -1 | sed 's/FAILED //' || echo "")
        # Extract falsifying example input (line after "Falsifying example:")
        FIRST_FAILURE_INPUT=$(echo "$OUTPUT" | grep -A1 "Falsifying example:" | tail -1 | sed 's/^[[:space:]]*//' | head -c 200 || echo "")
        # Extract error type (e.g., "AssertionError", "ValueError")
        FIRST_FAILURE_ERROR=$(echo "$OUTPUT" | grep -oE '(AssertionError|ValueError|TypeError|RecursionError|Exception)[^:]*' | head -1 || echo "")
    fi

    # Determine status
    if [[ $EXIT_CODE -eq 0 ]]; then
        STATUS="pass"
    elif [[ $TESTS_FAILED -gt 0 ]] || [[ $HYPOTHESIS_FAILURES -gt 0 ]]; then
        STATUS="finding"
    else
        STATUS="error"
    fi

    # Output
    if [[ "$JSON_OUTPUT" == "true" ]]; then
        # Escape special characters for JSON using Python's json.dumps for correctness
        # This handles newlines, carriage returns, control characters, and Unicode properly
        FIRST_FAILURE_INPUT_ESCAPED=$(printf '%s' "$FIRST_FAILURE_INPUT" | python3 -c "import json,sys; print(json.dumps(sys.stdin.read())[1:-1])" 2>/dev/null || echo "")
        FIRST_FAILURE_ERROR_ESCAPED=$(printf '%s' "$FIRST_FAILURE_ERROR" | python3 -c "import json,sys; print(json.dumps(sys.stdin.read())[1:-1])" 2>/dev/null || echo "")

        if [[ -n "$FIRST_FAILURE_TEST" ]]; then
            echo '{"mode":"check","status":"'"$STATUS"'","tests_passed":"'"$TESTS_PASSED"'","tests_failed":"'"$TESTS_FAILED"'","hypothesis_failures":"'"$HYPOTHESIS_FAILURES"'","first_failure":{"test":"'"$FIRST_FAILURE_TEST"'","input":"'"$FIRST_FAILURE_INPUT_ESCAPED"'","error":"'"$FIRST_FAILURE_ERROR_ESCAPED"'"}}'
        else
            echo '{"mode":"check","status":"'"$STATUS"'","tests_passed":"'"$TESTS_PASSED"'","tests_failed":"'"$TESTS_FAILED"'","hypothesis_failures":"'"$HYPOTHESIS_FAILURES"'"}'
        fi
    else
        echo ""
        echo -e "${BOLD}============================================================${NC}"
        if [[ "$STATUS" == "pass" ]]; then
            print_pass "All property tests passed."
            echo ""
            echo "Tests passed: $TESTS_PASSED"
            echo ""
            echo "Next: Run './scripts/fuzz.sh --deep' for deeper testing."
        elif [[ "$STATUS" == "finding" ]]; then
            print_finding "Failures detected!"
            echo ""
            echo "Hypothesis failures: $HYPOTHESIS_FAILURES"
            echo ""
            echo "Next steps:"
            echo "  1. Review the 'Falsifying example:' output above"
            echo "  2. Add @example(failing_input) decorator to the test"
            echo "  3. Fix the bug in the parser code"
            echo "  4. Run: ./scripts/fuzz.sh (to verify fix)"
        else
            echo -e "${RED}[ERROR]${NC} Test execution failed."
        fi
        echo -e "${BOLD}============================================================${NC}"
    fi

    exit $EXIT_CODE
}

# Mode: deep - Continuous HypoFuzz
run_deep() {
    print_header

    # Build args
    EXTRA_ARGS=""
    if [[ -n "$TIME_LIMIT" ]]; then
        EXTRA_ARGS="--max-examples=$((TIME_LIMIT * 100))"
    fi

    if [[ "$JSON_OUTPUT" == "false" ]]; then
        echo -e "Mode:    ${BOLD}Continuous Coverage-Guided Fuzzing${NC}"
        echo "Engine:  HypoFuzz"
        echo "Workers: $WORKERS"
        if [[ -n "$TIME_LIMIT" ]]; then
            echo "Time:    ${TIME_LIMIT}s"
        else
            echo "Time:    Until Ctrl+C"
        fi
        echo ""
        echo "Starting HypoFuzz... (press Ctrl+C to stop)"
        echo ""
    fi

    # Force TMPDIR to avoid macOS socket path issues
    export TMPDIR="/tmp"

    # Use temp file to capture output while displaying in real-time
    DEEP_OUTPUT_FILE=$(mktemp)
    trap "rm -f '$DEEP_OUTPUT_FILE'" EXIT

    # Track if user interrupted
    USER_STOPPED="false"
    trap 'USER_STOPPED="true"' INT

    set +e
    uv run hypothesis fuzz --no-dashboard -n "$WORKERS" $EXTRA_ARGS -- tests/ 2>&1 | tee "$DEEP_OUTPUT_FILE"
    EXIT_CODE=${PIPESTATUS[0]}
    set -e

    # Restore default INT handler
    trap - INT

    # Analyze output for findings
    # Note: grep -c outputs "0" and exits 1 when no matches, so use || true
    FAILURE_COUNT=$(grep -c "Falsifying example:" "$DEEP_OUTPUT_FILE" 2>/dev/null) || true
    FAILURE_COUNT=${FAILURE_COUNT:-0}
    INTERRUPTED=$(grep -c "KeyboardInterrupt" "$DEEP_OUTPUT_FILE" 2>/dev/null) || true
    INTERRUPTED=${INTERRUPTED:-0}

    # User stopped if we caught SIGINT or output shows KeyboardInterrupt
    if [[ "$INTERRUPTED" -gt 0 ]] || [[ $EXIT_CODE -eq 130 ]]; then
        USER_STOPPED="true"
    fi

    # Display summary
    if [[ "$JSON_OUTPUT" == "true" ]]; then
        if [[ $EXIT_CODE -eq 0 ]] || [[ "$USER_STOPPED" == "true" ]]; then
            if [[ "$FAILURE_COUNT" -gt 0 ]]; then
                STATUS="finding"
            else
                STATUS="pass"
            fi
        elif [[ "$FAILURE_COUNT" -gt 0 ]]; then
            STATUS="finding"
        else
            STATUS="error"
        fi
        echo '{"mode":"deep","status":"'"$STATUS"'","finding_count":"'"$FAILURE_COUNT"'"}'
    else
        echo ""
        echo -e "${BOLD}============================================================${NC}"
        if [[ "$FAILURE_COUNT" -gt 0 ]]; then
            print_finding "$FAILURE_COUNT property violation(s) found!"
            echo ""
            echo "Findings saved to: .hypothesis/failures/"
            echo "View with: ./scripts/fuzz.sh --list"
            echo ""
            echo "Next steps:"
            echo "  1. Look for 'Falsifying example:' in output above"
            echo "  2. Add @example(failing_input) to the test"
            echo "  3. Fix the bug and re-run ./scripts/fuzz.sh"
        elif [[ "$USER_STOPPED" == "true" ]]; then
            print_pass "Stopped by user. No violations detected."
            echo ""
            echo "Tip: Run longer with --time 300 (5 min) for deeper coverage."
        elif [[ $EXIT_CODE -eq 0 ]]; then
            print_pass "Fuzzing completed. No violations detected."
        else
            echo -e "${RED}[ERROR]${NC} Fuzzing failed unexpectedly (exit code: $EXIT_CODE)"
        fi
        echo -e "${BOLD}============================================================${NC}"
    fi

    # Clean up temp file
    rm -f "$DEEP_OUTPUT_FILE"
    trap - EXIT

    # Exit success if user stopped cleanly with no findings
    if [[ "$USER_STOPPED" == "true" ]] && [[ "$FAILURE_COUNT" -eq 0 ]]; then
        exit 0
    fi
    exit $EXIT_CODE
}

# Mode: native - Atheris stability fuzzing
run_native() {
    print_header

    # Check Python version compatibility (Atheris requires 3.11-3.13)
    check_atheris_python_version

    # Check if Atheris is available
    if ! uv run python -c "import atheris" 2>/dev/null; then
        if [[ "$JSON_OUTPUT" == "true" ]]; then
            echo '{"mode":"native","status":"error","error":"atheris_not_installed"}'
            exit 2
        else
            echo -e "${RED}[ERROR]${NC} Atheris is not installed."
            echo ""
            echo "Atheris requires special setup on macOS:"
            echo "  1. Install LLVM: brew install llvm"
            echo "  2. Run: ./scripts/check-atheris.sh"
            echo ""
            echo "See docs/FUZZING_GUIDE.md for detailed instructions."
            exit 2
        fi
    fi

    # Build args
    EXTRA_ARGS=""
    if [[ -n "$TIME_LIMIT" ]]; then
        EXTRA_ARGS="-max_total_time=$TIME_LIMIT"
    fi

    if [[ "$JSON_OUTPUT" == "false" ]]; then
        echo -e "Mode:    ${BOLD}Native Stability Fuzzing${NC}"
        echo "Engine:  Atheris (libFuzzer)"
        echo "Workers: $WORKERS"
        if [[ -n "$TIME_LIMIT" ]]; then
            echo "Time:    ${TIME_LIMIT}s"
        else
            echo "Time:    Until Ctrl+C"
        fi
        echo ""
    fi

    # Delegate to existing script
    exec "$SCRIPT_DIR/fuzz-atheris.sh" "$WORKERS" "fuzz/stability.py" $EXTRA_ARGS
}

# Mode: perf - Atheris performance fuzzing
run_perf() {
    print_header

    # Check Python version compatibility (Atheris requires 3.11-3.13)
    check_atheris_python_version

    # Check if Atheris is available
    if ! uv run python -c "import atheris" 2>/dev/null; then
        if [[ "$JSON_OUTPUT" == "true" ]]; then
            echo '{"mode":"perf","status":"error","error":"atheris_not_installed"}'
            exit 2
        else
            echo -e "${RED}[ERROR]${NC} Atheris is not installed."
            echo ""
            echo "See docs/FUZZING_GUIDE.md for setup instructions."
            exit 2
        fi
    fi

    # Build args
    EXTRA_ARGS=""
    if [[ -n "$TIME_LIMIT" ]]; then
        EXTRA_ARGS="-max_total_time=$TIME_LIMIT"
    fi

    if [[ "$JSON_OUTPUT" == "false" ]]; then
        echo -e "Mode:    ${BOLD}Performance Fuzzing (ReDoS Detection)${NC}"
        echo "Engine:  Atheris (libFuzzer)"
        echo "Workers: $WORKERS"
        if [[ -n "$TIME_LIMIT" ]]; then
            echo "Time:    ${TIME_LIMIT}s"
        else
            echo "Time:    Until Ctrl+C"
        fi
        echo ""
    fi

    # Delegate to existing script
    exec "$SCRIPT_DIR/fuzz-atheris.sh" "$WORKERS" "fuzz/perf.py" $EXTRA_ARGS
}

# Helper: Calculate human-readable file age
file_age() {
    local file="$1"
    local now
    local file_time
    local age_sec
    now=$(date +%s)
    file_time=$(stat -f %m "$file" 2>/dev/null || stat -c %Y "$file" 2>/dev/null)
    age_sec=$((now - file_time))

    if [[ $age_sec -lt 60 ]]; then
        echo "${age_sec}s ago"
    elif [[ $age_sec -lt 3600 ]]; then
        echo "$((age_sec / 60))m ago"
    elif [[ $age_sec -lt 86400 ]]; then
        echo "$((age_sec / 3600))h ago"
    else
        echo "$((age_sec / 86400))d ago"
    fi
}

# Mode: list - Show captured failures
run_list() {
    FAILURES_DIR="$PROJECT_ROOT/.hypothesis/failures"
    CRASH_DIR="$PROJECT_ROOT/.fuzz_corpus"

    # Count failures
    HYPOTHESIS_COUNT=0
    CRASH_COUNT=0

    if [[ -d "$FAILURES_DIR" ]]; then
        HYPOTHESIS_COUNT=$(find "$FAILURES_DIR" -name "failures_*.txt" -type f 2>/dev/null | wc -l | tr -d ' ')
    fi

    if [[ -d "$CRASH_DIR" ]]; then
        CRASH_COUNT=$(find "$CRASH_DIR" -name "crash_*" -type f 2>/dev/null | wc -l | tr -d ' ')
    fi

    TOTAL=$((HYPOTHESIS_COUNT + CRASH_COUNT))

    if [[ "$JSON_OUTPUT" == "true" ]]; then
        echo '{"mode":"list","hypothesis_failures":"'"$HYPOTHESIS_COUNT"'","atheris_crashes":"'"$CRASH_COUNT"'","total":"'"$TOTAL"'"}'
    else
        print_header

        if [[ $TOTAL -eq 0 ]]; then
            print_pass "No captured failures."
            echo ""
            echo "Run './scripts/fuzz.sh' to start fuzzing."
        else
            print_info "Found $TOTAL captured failure(s)."
            echo ""

            if [[ $HYPOTHESIS_COUNT -gt 0 ]]; then
                echo -e "${BOLD}Hypothesis/HypoFuzz Failures:${NC} $HYPOTHESIS_COUNT"
                echo "  Location: .hypothesis/failures/"
                # Show files with ages, newest first
                ls -t "$FAILURES_DIR"/failures_*.txt 2>/dev/null | head -5 | while read -r f; do
                    echo "  - $(basename "$f") ($(file_age "$f"))"
                done
                echo ""
            fi

            if [[ $CRASH_COUNT -gt 0 ]]; then
                echo -e "${BOLD}Atheris Crashes:${NC} $CRASH_COUNT"
                echo "  Location: .fuzz_corpus/"
                # Show files with ages, newest first
                ls -t "$CRASH_DIR"/crash_* 2>/dev/null | head -5 | while read -r f; do
                    echo "  - $(basename "$f") ($(file_age "$f"))"
                done
                echo ""
            fi

            echo "Next steps:"
            echo "  1. Review the failure input"
            echo "  2. Add @example() decorator or create unit test"
            echo "  3. Fix the bug and verify with ./scripts/fuzz.sh"
        fi
        echo ""
    fi
}

# Mode: clean - Remove failure artifacts
run_clean() {
    FAILURES_DIR="$PROJECT_ROOT/.hypothesis/failures"
    CRASH_DIR="$PROJECT_ROOT/.fuzz_corpus"

    # Count before cleaning
    HYPOTHESIS_COUNT=0
    CRASH_COUNT=0

    if [[ -d "$FAILURES_DIR" ]]; then
        HYPOTHESIS_COUNT=$(find "$FAILURES_DIR" -name "failures_*.txt" -type f 2>/dev/null | wc -l | tr -d ' ')
    fi

    if [[ -d "$CRASH_DIR" ]]; then
        CRASH_COUNT=$(find "$CRASH_DIR" -name "crash_*" -type f 2>/dev/null | wc -l | tr -d ' ')
    fi

    # Clean
    rm -f "$FAILURES_DIR"/failures_*.txt 2>/dev/null || true
    rm -f "$CRASH_DIR"/crash_* 2>/dev/null || true

    if [[ "$JSON_OUTPUT" == "true" ]]; then
        echo '{"mode":"clean","status":"ok","hypothesis_removed":"'"$HYPOTHESIS_COUNT"'","crashes_removed":"'"$CRASH_COUNT"'"}'
    else
        print_header
        print_pass "Cleaned failure artifacts."
        echo ""
        echo "Removed: $HYPOTHESIS_COUNT Hypothesis failures, $CRASH_COUNT crash files"
        echo ""
    fi
}

# Mode: corpus - Check corpus health
run_corpus() {
    if [[ "$JSON_OUTPUT" == "false" ]]; then
        print_header
        echo -e "Mode:    ${BOLD}Corpus Health Check${NC}"
        echo ""
    fi

    exec uv run python "$SCRIPT_DIR/corpus-health.py" $(if [[ "$JSON_OUTPUT" == "true" ]]; then echo "--json"; fi)
}

# Mode: structured - Atheris structure-aware fuzzing
run_structured() {
    print_header

    # Check Python version compatibility (Atheris requires 3.11-3.13)
    check_atheris_python_version

    # Check if Atheris is available
    if ! uv run python -c "import atheris" 2>/dev/null; then
        if [[ "$JSON_OUTPUT" == "true" ]]; then
            echo '{"mode":"structured","status":"error","error":"atheris_not_installed"}'
            exit 2
        else
            echo -e "${RED}[ERROR]${NC} Atheris is not installed."
            echo ""
            echo "Atheris requires special setup on macOS:"
            echo "  1. Install LLVM: brew install llvm"
            echo "  2. Run: ./scripts/check-atheris.sh"
            echo ""
            echo "See docs/FUZZING_GUIDE.md for detailed instructions."
            exit 2
        fi
    fi

    # Build args
    EXTRA_ARGS=""
    if [[ -n "$TIME_LIMIT" ]]; then
        EXTRA_ARGS="-max_total_time=$TIME_LIMIT"
    fi

    if [[ "$JSON_OUTPUT" == "false" ]]; then
        echo -e "Mode:    ${BOLD}Structure-Aware Fuzzing${NC}"
        echo "Engine:  Atheris (libFuzzer) + Grammar-Aware Generation"
        echo "Target:  fuzz/structured.py"
        echo "Workers: $WORKERS"
        if [[ -n "$TIME_LIMIT" ]]; then
            echo "Time:    ${TIME_LIMIT}s"
        else
            echo "Time:    Until Ctrl+C"
        fi
        echo ""
        echo "This mode generates syntactically plausible FTL for better coverage."
        echo ""
    fi

    # Delegate to existing script
    exec "$SCRIPT_DIR/fuzz-atheris.sh" "$WORKERS" "fuzz/structured.py" $EXTRA_ARGS
}

# Mode: repro - Reproduce a crash file
run_repro() {
    if [[ -z "$REPRO_FILE" ]]; then
        echo -e "${RED}[ERROR]${NC} --repro requires a file path."
        echo "Usage: ./scripts/fuzz.sh --repro .fuzz_corpus/crash_xxx"
        exit 2
    fi

    if [[ "$JSON_OUTPUT" == "false" ]]; then
        print_header
        echo -e "Mode:    ${BOLD}Crash Reproduction${NC}"
        echo "File:    $REPRO_FILE"
        echo ""
    fi

    exec uv run python "$SCRIPT_DIR/repro.py" "$REPRO_FILE"
}

# Mode: minimize - Minimize a crash file using libFuzzer
run_minimize() {
    if [[ -z "$MINIMIZE_FILE" ]]; then
        echo -e "${RED}[ERROR]${NC} --minimize requires a crash file path."
        echo "Usage: ./scripts/fuzz.sh --minimize .fuzz_corpus/crash_xxx"
        exit 2
    fi

    if [[ ! -f "$MINIMIZE_FILE" ]]; then
        echo -e "${RED}[ERROR]${NC} Crash file not found: $MINIMIZE_FILE"
        exit 2
    fi

    # Check Python version compatibility (Atheris requires 3.11-3.13)
    check_atheris_python_version

    # Check if Atheris is available
    if ! uv run python -c "import atheris" 2>/dev/null; then
        if [[ "$JSON_OUTPUT" == "true" ]]; then
            echo '{"mode":"minimize","status":"error","error":"atheris_not_installed"}'
            exit 2
        else
            echo -e "${RED}[ERROR]${NC} Atheris is not installed."
            echo ""
            echo "Atheris requires special setup on macOS:"
            echo "  1. Install LLVM: brew install llvm"
            echo "  2. Run: ./scripts/check-atheris.sh"
            echo ""
            echo "See docs/FUZZING_GUIDE.md for detailed instructions."
            exit 2
        fi
    fi

    # Determine which fuzzer script to use based on crash file location/name
    # Default to structured.py since it covers more code paths
    FUZZER_SCRIPT="fuzz/structured.py"
    if [[ "$MINIMIZE_FILE" == *"perf"* ]]; then
        FUZZER_SCRIPT="fuzz/perf.py"
    elif [[ "$MINIMIZE_FILE" == *"stability"* ]]; then
        FUZZER_SCRIPT="fuzz/stability.py"
    fi

    # Create output file for minimized crash
    MINIMIZE_OUTPUT="${MINIMIZE_FILE}.minimized"

    if [[ "$JSON_OUTPUT" == "false" ]]; then
        print_header
        echo -e "Mode:    ${BOLD}Crash Minimization${NC}"
        echo "Engine:  libFuzzer (-minimize_crash=1)"
        echo "Input:   $MINIMIZE_FILE"
        echo "Output:  $MINIMIZE_OUTPUT"
        echo "Fuzzer:  $FUZZER_SCRIPT"
        echo ""
        echo "Minimizing crash input... (this may take a while)"
        echo ""
    fi

    # Run libFuzzer minimization
    # -minimize_crash=1: Enable crash minimization mode
    # -exact_artifact_path: Write minimized crash to specific file
    # -runs=0: Don't do additional fuzzing, just minimize
    # -max_total_time: Limit minimization time (default 60s)
    TIME_LIMIT=${TIME_LIMIT:-60}

    set +e
    uv run python "$FUZZER_SCRIPT" \
        -minimize_crash=1 \
        -exact_artifact_path="$MINIMIZE_OUTPUT" \
        -max_total_time="$TIME_LIMIT" \
        "$MINIMIZE_FILE" 2>&1
    EXIT_CODE=$?
    set -e

    if [[ "$JSON_OUTPUT" == "true" ]]; then
        if [[ -f "$MINIMIZE_OUTPUT" ]]; then
            ORIGINAL_SIZE=$(wc -c < "$MINIMIZE_FILE" | tr -d ' ')
            MINIMIZED_SIZE=$(wc -c < "$MINIMIZE_OUTPUT" | tr -d ' ')
            echo '{"mode":"minimize","status":"ok","original_size":"'"$ORIGINAL_SIZE"'","minimized_size":"'"$MINIMIZED_SIZE"'","output_file":"'"$MINIMIZE_OUTPUT"'"}'
        else
            echo '{"mode":"minimize","status":"error","error":"minimization_failed"}'
        fi
    else
        echo ""
        echo -e "${BOLD}============================================================${NC}"
        if [[ -f "$MINIMIZE_OUTPUT" ]]; then
            ORIGINAL_SIZE=$(wc -c < "$MINIMIZE_FILE" | tr -d ' ')
            MINIMIZED_SIZE=$(wc -c < "$MINIMIZE_OUTPUT" | tr -d ' ')
            print_pass "Crash minimized successfully."
            echo ""
            echo "Original size:  $ORIGINAL_SIZE bytes"
            echo "Minimized size: $MINIMIZED_SIZE bytes"
            echo "Reduction:      $((100 - (MINIMIZED_SIZE * 100 / ORIGINAL_SIZE)))%"
            echo ""
            echo "Minimized crash saved to: $MINIMIZE_OUTPUT"
            echo ""
            echo "Next steps:"
            echo "  1. Reproduce: ./scripts/fuzz.sh --repro $MINIMIZE_OUTPUT"
            echo "  2. Add @example() to test and fix the bug"
        else
            echo -e "${RED}[ERROR]${NC} Minimization failed."
            echo ""
            echo "The crash may already be minimal, or the fuzzer script"
            echo "may not reproduce the crash consistently."
        fi
        echo -e "${BOLD}============================================================${NC}"
    fi

    exit $EXIT_CODE
}

# Dispatch to mode
case $MODE in
    check)
        run_check
        ;;
    deep)
        run_deep
        ;;
    native)
        run_native
        ;;
    perf)
        run_perf
        ;;
    structured)
        run_structured
        ;;
    repro)
        run_repro
        ;;
    minimize)
        run_minimize
        ;;
    list)
        run_list
        ;;
    clean)
        run_clean
        ;;
    corpus)
        run_corpus
        ;;
    *)
        echo "Unknown mode: $MODE"
        exit 2
        ;;
esac
