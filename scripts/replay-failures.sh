#!/bin/bash
# DEPRECATED: Use './scripts/fuzz.sh' instead.
#
# This script is deprecated. Its functionality is covered by:
#   - pytest with cached examples: uv run pytest tests/ -x
#   - The unified fuzz.sh: ./scripts/fuzz.sh
#
# This script remains for backward compatibility but will be removed
# in a future release.
#
# Original description:
# Replay Saved Failures - Quickly checks for saved failures using CI profile.

echo ""
echo "[DEPRECATED] This script is deprecated."
echo "Use './scripts/fuzz.sh' instead for all fuzzing operations."
echo ""

TARGET=${1:-"tests/test_grammar_based_fuzzing.py"}
PROJECT_ROOT=$(pwd)
FAILURES_DIR="$PROJECT_ROOT/.hypothesis/failures"

echo ""
echo "=============================================================================="
echo "Replay Saved Failures (Fast Check)"
echo "=============================================================================="
echo "Target:  $TARGET"
echo "Profile: ci (50 examples, fast)"
echo "Mode:    Replays saved examples first, then minimal generation"
echo "=============================================================================="
echo ""

set +e
OUTPUT=$(HYPOTHESIS_PROFILE=ci uv run pytest "$TARGET" -x -v --tb=short 2>&1)
EXIT_CODE=$?
echo "$OUTPUT"

# Extract and save failures if any found
FAILURE_COUNT=$(echo "$OUTPUT" | grep -c "Falsifying example:" 2>/dev/null || echo "0")
FAILURE_FILE=""
if [[ $FAILURE_COUNT -gt 0 ]]; then
    mkdir -p "$FAILURES_DIR"
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    FAILURE_FILE="$FAILURES_DIR/failures_${TIMESTAMP}.txt"
    echo "$OUTPUT" | grep -A 10 "Falsifying example:" > "$FAILURE_FILE" 2>/dev/null || true
fi
set -e

echo ""
echo "=============================================================================="
if [[ $EXIT_CODE -eq 0 ]]; then
    echo "[PASS] No failures detected."
else
    echo "[FINDING] Failures detected!"
    if [[ -n "$FAILURE_FILE" ]]; then
        echo ""
        echo "Failures saved: $FAILURE_FILE"
    fi
    echo ""
    echo "Next steps:"
    if [[ -n "$FAILURE_FILE" ]]; then
        echo "  1. Review failures: cat $FAILURE_FILE"
    else
        echo "  1. Review the 'Falsifying example:' output above"
    fi
    echo "  2. Add @example(failing_input) decorator to preserve"
    echo "  3. Fix the bug"
    echo "  4. See: docs/FUZZING_GUIDE.md (Bug Preservation Workflow)"
fi
echo "=============================================================================="

exit $EXIT_CODE
