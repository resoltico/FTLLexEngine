#!/bin/bash
# Property Test Runner
# Runs Hypothesis property tests with JSON summary output.
# See docs/FUZZING_GUIDE.md for usage.
#
# Fuzz-marked tests are excluded from normal test runs (uv run scripts/test.sh)
# but are explicitly run by this script since we target specific files.

set -e

PROJECT_ROOT=$(pwd)
EXAMPLES_DIR="$PROJECT_ROOT/.hypothesis/examples"
FAILURES_DIR="$PROJECT_ROOT/.hypothesis/failures"
LOG_FILE="$PROJECT_ROOT/.hypothesis/property-tests.log"

# Default to grammar-based fuzzing test, allow override
TARGET=${1:-"tests/test_grammar_based_fuzzing.py"}
PROFILE=${HYPOTHESIS_PROFILE:-"dev"}

# Ensure hypothesis directory exists
mkdir -p "$PROJECT_ROOT/.hypothesis"

echo ""
echo "=============================================================================="
echo "Property Test Runner"
echo "=============================================================================="
echo "Target:     $TARGET"
echo "Profile:    $PROFILE (max_examples varies by profile)"
echo "Examples:   $EXAMPLES_DIR"
echo "Log:        $LOG_FILE"
echo "=============================================================================="
echo ""

# Count existing examples before testing
if [[ -d "$EXAMPLES_DIR" ]]; then
    EXAMPLES_BEFORE=$(find "$EXAMPLES_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')
else
    EXAMPLES_BEFORE=0
fi

# Progress indicator for silent profiles
if [[ "$PROFILE" != "verbose" ]]; then
    echo "Running... (use HYPOTHESIS_PROFILE=verbose for detailed output)"
    echo ""
fi

START_TIME=$(date +%s.%N)

# Run pytest with Hypothesis, capturing to log and variable
set +e
OUTPUT=$(uv run pytest "$TARGET" -v --tb=short 2>&1 | tee "$LOG_FILE")
EXIT_CODE=${PIPESTATUS[0]}
set -e

END_TIME=$(date +%s.%N)
DURATION=$(echo "$END_TIME - $START_TIME" | bc 2>/dev/null | xargs printf "%.2f" 2>/dev/null || echo "0.00")

# Parse pytest output for counts
TESTS_PASSED=$(echo "$OUTPUT" | grep -oE '[0-9]+ passed' | grep -oE '[0-9]+' || echo "0")
TESTS_FAILED=$(echo "$OUTPUT" | grep -oE '[0-9]+ failed' | grep -oE '[0-9]+' || echo "0")
TESTS_SKIPPED=$(echo "$OUTPUT" | grep -oE '[0-9]+ skipped' | grep -oE '[0-9]+' || echo "0")

# Handle empty values
TESTS_PASSED=${TESTS_PASSED:-0}
TESTS_FAILED=${TESTS_FAILED:-0}
TESTS_SKIPPED=${TESTS_SKIPPED:-0}

# Count examples after testing
if [[ -d "$EXAMPLES_DIR" ]]; then
    EXAMPLES_AFTER=$(find "$EXAMPLES_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')
else
    EXAMPLES_AFTER=0
fi
NEW_EXAMPLES=$((EXAMPLES_AFTER - EXAMPLES_BEFORE))

# Detect Hypothesis failures (from captured output, not log - already shown by tee)
set +e
HYPOTHESIS_FAILURES=$(echo "$OUTPUT" | grep -c "Falsifying example:" 2>/dev/null | tr -d '\n' || echo "0")
HYPOTHESIS_FAILURES=${HYPOTHESIS_FAILURES:-0}

# Extract and save failures to dedicated directory
FAILURE_FILE=""
if [[ $HYPOTHESIS_FAILURES -gt 0 ]]; then
    mkdir -p "$FAILURES_DIR"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    FAILURE_FILE="$FAILURES_DIR/failures_${TIMESTAMP}.txt"

    # Extract complete falsifying example blocks (test name + example)
    echo "$OUTPUT" | grep -A 10 "Falsifying example:" > "$FAILURE_FILE" 2>/dev/null || true

    echo ""
    echo "[INFO] Failures saved to: $FAILURE_FILE"
fi
set -e

echo ""

# Determine result status
if [[ $EXIT_CODE -eq 0 ]]; then
    STATUS_STR="pass"
elif [[ $TESTS_FAILED -gt 0 ]] || [[ $HYPOTHESIS_FAILURES -gt 0 ]]; then
    STATUS_STR="finding"
else
    STATUS_STR="error"
fi

echo "=============================================================================="
if [[ "$STATUS_STR" == "pass" ]]; then
    echo "[PASS] All property tests passed."
elif [[ "$STATUS_STR" == "finding" ]]; then
    echo "[FINDING] Property test failures detected!"
    echo ""
    echo "Failures found: $HYPOTHESIS_FAILURES"
    if [[ -n "$FAILURE_FILE" ]]; then
        echo "Failures saved: $FAILURE_FILE"
    fi
    echo ""
    echo "Next steps:"
    if [[ -n "$FAILURE_FILE" ]]; then
        echo "  1. Review failures: cat $FAILURE_FILE"
    else
        echo "  1. Review the 'Falsifying example:' output above"
    fi
    echo "  2. Add @example(failing_input) decorator to preserve the bug"
    echo "  3. Fix the bug in the parser code"
    echo "  4. Run: uv run pytest tests/ -x (replay and confirm fix)"
    echo "  5. See: docs/FUZZING_GUIDE.md (Bug Preservation Workflow)"
else
    echo "[ERROR] Test execution failed."
fi
echo "=============================================================================="

# JSON summary for automation
echo "[SUMMARY-JSON-BEGIN]"
printf "{"
printf "\"result\":\"%s\"," "$STATUS_STR"
printf "\"exit_code\":\"%d\"," "$EXIT_CODE"
printf "\"duration_sec\":\"%s\"," "$DURATION"
printf "\"target\":\"%s\"," "$TARGET"
printf "\"profile\":\"%s\"," "$PROFILE"
printf "\"log_file\":\"%s\"," "$LOG_FILE"
printf "\"tests_passed\":\"%s\"," "$TESTS_PASSED"
printf "\"tests_failed\":\"%s\"," "$TESTS_FAILED"
printf "\"tests_skipped\":\"%s\"," "$TESTS_SKIPPED"
printf "\"hypothesis_failures\":\"%s\"," "$HYPOTHESIS_FAILURES"
printf "\"failure_file\":\"%s\"," "${FAILURE_FILE:-}"
printf "\"examples_before\":\"%s\"," "$EXAMPLES_BEFORE"
printf "\"examples_after\":\"%s\"," "$EXAMPLES_AFTER"
printf "\"new_examples\":\"%s\"" "$NEW_EXAMPLES"
printf "}\n"
echo "[SUMMARY-JSON-END]"

echo "[END-PROPERTY-TESTS]"
exit $EXIT_CODE
