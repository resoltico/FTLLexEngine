#!/bin/bash
# List Captured Failures
# Shows all saved falsifying examples from fuzzing sessions.

PROJECT_ROOT=$(pwd)
FAILURES_DIR="$PROJECT_ROOT/.hypothesis/failures"
CRASH_DIR="$PROJECT_ROOT/.fuzz_corpus"

echo ""
echo "=============================================================================="
echo "Captured Failures"
echo "=============================================================================="

# Hypothesis/HypoFuzz failures
if [[ -d "$FAILURES_DIR" ]]; then
    HYPOTHESIS_COUNT=$(find "$FAILURES_DIR" -name "failures_*.txt" -type f 2>/dev/null | wc -l | tr -d ' ')
    echo ""
    echo "Hypothesis/HypoFuzz Failures: $HYPOTHESIS_COUNT file(s)"
    echo "Location: $FAILURES_DIR"
    echo ""
    if [[ $HYPOTHESIS_COUNT -gt 0 ]]; then
        echo "Files:"
        ls -lt "$FAILURES_DIR"/failures_*.txt 2>/dev/null | head -10 | awk '{print "  " $NF}'
        echo ""
        echo "To view latest: cat $(ls -t "$FAILURES_DIR"/failures_*.txt 2>/dev/null | head -1)"
    fi
else
    echo ""
    echo "Hypothesis/HypoFuzz Failures: None (no failures captured yet)"
fi

# Atheris crashes
echo ""
echo "------------------------------------------------------------------------------"
if [[ -d "$CRASH_DIR" ]]; then
    CRASH_COUNT=$(find "$CRASH_DIR" -name "crash_*" -type f 2>/dev/null | wc -l | tr -d ' ')
    echo ""
    echo "Atheris Crashes: $CRASH_COUNT file(s)"
    echo "Location: $CRASH_DIR"
    echo ""
    if [[ $CRASH_COUNT -gt 0 ]]; then
        echo "Crash files:"
        ls -lt "$CRASH_DIR"/crash_* 2>/dev/null | head -10 | awk '{print "  " $NF}'
        echo ""
        echo "To inspect: xxd $(ls -t "$CRASH_DIR"/crash_* 2>/dev/null | head -1) | head -20"
    fi
else
    echo ""
    echo "Atheris Crashes: None (no crashes found)"
fi

echo ""
echo "=============================================================================="
echo ""
echo "Next steps when failures exist:"
echo "  1. Review the failure/crash input"
echo "  2. Add @example() decorator or create unit test to preserve"
echo "  3. Fix the bug"
echo "  4. See: docs/FUZZING_GUIDE.md (Bug Preservation Workflow)"
echo "=============================================================================="
