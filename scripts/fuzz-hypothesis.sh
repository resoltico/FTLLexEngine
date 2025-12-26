#!/bin/bash
# HypoFuzz Runner
# Coverage-guided fuzzing for Hypothesis property tests.
# Outputs JSON summary for automation.
# See docs/FUZZING_GUIDE.md for usage.

set -e

# REQUIRED: Force TMPDIR to /tmp to avoid "AF_UNIX path too long" on macOS.
# macOS limits Unix socket paths to ~104 chars. HypoFuzz multiprocessing
# creates sockets in TMPDIR, so long project paths cause failures.
export TMPDIR="/tmp"

PROJECT_ROOT=$(pwd)
EXAMPLES_DIR="$PROJECT_ROOT/.hypothesis/examples"
FAILURES_DIR="$PROJECT_ROOT/.hypothesis/failures"
LOG_FILE="$PROJECT_ROOT/.hypothesis/fuzz.log"
WORKERS=${1:-4}
shift 1 2>/dev/null || true
EXTRA_ARGS="$@"

# Ensure hypothesis directory exists
mkdir -p "$PROJECT_ROOT/.hypothesis"

# Count existing examples before fuzzing
if [[ -d "$EXAMPLES_DIR" ]]; then
    EXAMPLES_BEFORE=$(find "$EXAMPLES_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')
else
    EXAMPLES_BEFORE=0
fi

echo ""
echo "=============================================================================="
echo "HypoFuzz Campaign"
echo "=============================================================================="
echo "Workers:    $WORKERS"
echo "Tests:      tests/"
echo "Examples:   $EXAMPLES_DIR ($EXAMPLES_BEFORE existing)"
echo "Log:        $LOG_FILE"
echo "Duration:   Until Ctrl+C (or pass -max_total_time=60 for timed run)"
echo "Dashboard:  Pass --dashboard to enable (http://localhost:9999)"
echo "=============================================================================="
echo ""

START_TIME=$(date +%s.%N)

# Run HypoFuzz, capturing output
set +e
uv run hypothesis fuzz \
    --no-dashboard \
    -n "$WORKERS" \
    $EXTRA_ARGS \
    -- tests/ 2>&1 | tee "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}
set -e

END_TIME=$(date +%s.%N)
DURATION=$(echo "$END_TIME - $START_TIME" | bc 2>/dev/null | xargs printf "%.2f" 2>/dev/null || echo "0.00")

# Count examples after fuzzing
if [[ -d "$EXAMPLES_DIR" ]]; then
    EXAMPLES_AFTER=$(find "$EXAMPLES_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')
else
    EXAMPLES_AFTER=0
fi
NEW_EXAMPLES=$((EXAMPLES_AFTER - EXAMPLES_BEFORE))

# Detect findings from log (actual property violations)
set +e
FAILURE_COUNT=$(grep -c "Falsifying example:" "$LOG_FILE" 2>/dev/null | tr -d '\n' || echo "0")
FAILURE_COUNT=${FAILURE_COUNT:-0}

# Extract and save failures to dedicated directory
if [[ $FAILURE_COUNT -gt 0 ]]; then
    mkdir -p "$FAILURES_DIR"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    FAILURE_FILE="$FAILURES_DIR/failures_${TIMESTAMP}.txt"

    # Extract complete falsifying example blocks (test name + example)
    # Pattern: "Falsifying example:" followed by the input until blank line
    grep -A 10 "Falsifying example:" "$LOG_FILE" > "$FAILURE_FILE" 2>/dev/null || true

    echo ""
    echo "[INFO] Failures saved to: $FAILURE_FILE"
fi

# Detect known crash patterns
CRASH_DETECTED=false
CRASH_REASON=""
if grep -q "AF_UNIX path too long" "$LOG_FILE" 2>/dev/null; then
    CRASH_DETECTED=true
    CRASH_REASON="AF_UNIX path too long (TMPDIR issue)"
elif grep -q "Aborted!" "$LOG_FILE" 2>/dev/null; then
    CRASH_DETECTED=true
    CRASH_REASON="Process aborted"
fi
set -e

# Determine result status
# Priority: 1) Crash errors, 2) Property violations, 3) Clean exit
if [[ "$CRASH_DETECTED" == "true" ]]; then
    STATUS_STR="error"
    FINDING_TYPE="crash"
elif [[ $EXIT_CODE -ne 0 ]] && [[ $EXIT_CODE -ne 130 ]]; then
    # Non-zero exit (not Ctrl+C) without known crash = unknown error
    STATUS_STR="error"
    FINDING_TYPE="unknown_error"
elif [[ $FAILURE_COUNT -gt 0 ]]; then
    # Actual property violations found
    STATUS_STR="finding"
    FINDING_TYPE="property_violation"
elif [[ $EXIT_CODE -eq 130 ]]; then
    # Ctrl+C (normal stop)
    STATUS_STR="pass"
    FINDING_TYPE="none"
else
    # Clean exit
    STATUS_STR="pass"
    FINDING_TYPE="none"
fi

echo ""
echo "=============================================================================="
if [[ "$STATUS_STR" == "error" ]]; then
    echo "[ERROR] Fuzzing failed to run properly."
    echo ""
    echo "Reason: $CRASH_REASON"
    echo "Exit code: $EXIT_CODE"
    echo ""
    echo "Next steps:"
    echo "  1. Check: docs/FUZZING_GUIDE.md (Troubleshooting section)"
    echo "  2. Review: $LOG_FILE"
elif [[ "$STATUS_STR" == "finding" ]]; then
    echo "[FINDING] Property violations detected!"
    echo ""
    echo "Violations found: $FAILURE_COUNT"
    echo "Failures saved:   $FAILURE_FILE"
    echo ""
    echo "Next steps:"
    echo "  1. Review failures: cat $FAILURE_FILE"
    echo "  2. Add @example(failing_input) decorator to preserve the bug"
    echo "  3. Fix the bug in the parser code"
    echo "  4. Run: uv run pytest tests/ -x (replay and confirm fix)"
    echo "  5. See: docs/FUZZING_GUIDE.md (Bug Preservation Workflow)"
else
    echo "[PASS] Fuzzing completed. No violations detected."
    echo ""
    echo "Examples in database: $EXAMPLES_AFTER"
fi
echo "=============================================================================="

# JSON summary for automation
echo "[SUMMARY-JSON-BEGIN]"
printf "{"
printf "\"result\":\"%s\"," "$STATUS_STR"
printf "\"exit_code\":\"%d\"," "$EXIT_CODE"
printf "\"duration_sec\":\"%s\"," "$DURATION"
printf "\"target\":\"tests/\","
printf "\"workers\":\"%s\"," "$WORKERS"
printf "\"finding_count\":\"%s\"," "$FAILURE_COUNT"
printf "\"finding_type\":\"%s\"," "$FINDING_TYPE"
printf "\"failure_file\":\"%s\"," "${FAILURE_FILE:-}"
printf "\"crash_reason\":\"%s\"," "$CRASH_REASON"
printf "\"examples_before\":\"%s\"," "$EXAMPLES_BEFORE"
printf "\"examples_after\":\"%s\"," "$EXAMPLES_AFTER"
printf "\"new_examples\":\"%s\"" "$NEW_EXAMPLES"
printf "}\n"
echo "[SUMMARY-JSON-END]"

# Exit with appropriate status for CI
if [[ "$STATUS_STR" == "finding" ]]; then
    exit 1
elif [[ "$STATUS_STR" == "error" ]]; then
    exit 2
else
    exit 0
fi
