#!/usr/bin/env bash
# Fuzzing Orchestrator (Atheris)
# Manages multi-worker fuzzing campaigns. Outputs JSON summary.
# See docs/FUZZING_GUIDE.md for usage.
#
# Note: Atheris is optional. Use ./scripts/fuzz.sh for the unified interface.

set -e

# =============================================================================
# Bash Version Check (EPOCHREALTIME requires bash 5.0+)
# =============================================================================

if ((BASH_VERSINFO[0] < 5)); then
    echo ""
    echo "=============================================================================="
    echo "[FATAL] Bash v5.0+ required. Found: ${BASH_VERSION}"
    echo "=============================================================================="
    echo ""
    echo "This script uses EPOCHREALTIME which requires bash 5.0+."
    echo ""
    echo "On macOS, install modern bash:"
    echo "  brew install bash"
    echo ""
    echo "Then run with:"
    echo "  /opt/homebrew/bin/bash ./scripts/fuzz-atheris.sh"
    echo ""
    exit 1
fi

# =============================================================================
# Environment Auto-Detection
# =============================================================================

# Check Python version compatibility (Atheris requires 3.11-3.13)
PY_VERSION=$(uv run python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)

if [[ "$PY_VERSION" == "3.14" ]] || [[ "$PY_VERSION" > "3.14" ]]; then
    echo ""
    echo "=============================================================================="
    echo "[ERROR] Python $PY_VERSION is not supported by Atheris."
    echo "=============================================================================="
    echo ""
    echo "Atheris native fuzzing requires Python 3.11-3.13."
    echo "Python 3.14+ is not yet supported by the Atheris project."
    echo ""
    echo "Options:"
    echo "  1. Switch to Python 3.13:"
    echo "     uv run --python 3.13 ./scripts/fuzz.sh --native"
    echo ""
    echo "  2. Use property-based fuzzing (works on Python 3.14):"
    echo "     ./scripts/fuzz.sh          # Hypothesis tests"
    echo "     ./scripts/fuzz.sh --deep   # HypoFuzz coverage"
    echo ""
    echo "See docs/FUZZING_GUIDE.md for Python version requirements."
    echo "=============================================================================="
    exit 3
fi

# Check if Atheris is available
if ! uv run python -c "import atheris" 2>/dev/null; then
    echo ""
    echo "=============================================================================="
    echo "[ERROR] Atheris is not installed."
    echo "=============================================================================="
    echo ""
    echo "Atheris requires special setup, especially on macOS."
    echo ""
    echo "To check your setup and get installation instructions:"
    echo "  ./scripts/check-atheris.sh"
    echo ""
    echo "Alternatively, use Hypothesis-based fuzzing (no setup required):"
    echo "  ./scripts/fuzz.sh"
    echo "  ./scripts/fuzz.sh --deep"
    echo ""
    echo "=============================================================================="
    exit 2
fi

PROJECT_ROOT=$(pwd)
CORPUS_DIR="$PROJECT_ROOT/.fuzz_corpus"
LOG_FILE="$PROJECT_ROOT/.fuzz_corpus/fuzz.log"
JOBS=${1:-4}
TARGET_FILE=${2:-"fuzz/stability.py"}

# Pass through additional arguments to the fuzzer (e.g., -max_total_time=60)
shift 2 2>/dev/null || true
EXTRA_ARGS="$@"

mkdir -p "$CORPUS_DIR"

echo ""
echo "=============================================================================="
echo "Fuzzing Campaign"
echo "=============================================================================="
echo "Target:  $TARGET_FILE"
echo "Workers: $JOBS"
echo "Corpus:  $CORPUS_DIR"
echo "Log:     $LOG_FILE"
echo "Args:    ${EXTRA_ARGS:-'(none - runs indefinitely, Ctrl+C to stop)'}"
echo "=============================================================================="
echo ""

START_TIME="${EPOCHREALTIME}"

set +e
uv run python "$TARGET_FILE" \
    -workers="$JOBS" \
    -jobs=0 \
    -artifact_prefix="$CORPUS_DIR/crash_" \
    "$CORPUS_DIR" \
    $EXTRA_ARGS 2>&1 | tee "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}
set -e

END_TIME="${EPOCHREALTIME}"
# Use Python for duration calculation (avoids bc dependency)
DURATION=$(python3 -c "print(f'{$END_TIME - $START_TIME:.3f}')" 2>/dev/null || echo "0.000")

# Count crash artifacts
CRASH_COUNT=$(find "$CORPUS_DIR" -name 'crash_*' -type f 2>/dev/null | wc -l | tr -d ' ')

# Extract metrics from log
set +e
COVERAGE=$(grep -o 'cov: [0-9]*' "$LOG_FILE" | tail -1 | grep -o '[0-9]*' || echo "0")
CORPUS_SIZE=$(grep -o 'corp: [0-9]*/[0-9KMb]*' "$LOG_FILE" | tail -1 || echo "0/0")
EXEC_SPEED=$(grep -o 'exec/s: [0-9]*' "$LOG_FILE" | tail -1 | grep -o '[0-9]*' || echo "0")
set -e

# Determine result status
if [[ $EXIT_CODE -eq 0 ]]; then
    STATUS_STR="pass"
    FINDING_TYPE="none"
elif [[ $CRASH_COUNT -gt 0 ]]; then
    STATUS_STR="finding"
    if grep -q "PERFORMANCE BREACH" "$LOG_FILE"; then
        FINDING_TYPE="performance"
    elif grep -q "STABILITY BREACH" "$LOG_FILE"; then
        FINDING_TYPE="stability"
    else
        FINDING_TYPE="unknown"
    fi
else
    STATUS_STR="error"
    FINDING_TYPE="script_error"
fi

echo ""
echo "=============================================================================="
if [[ "$STATUS_STR" == "pass" ]]; then
    echo "Completed: No findings."
elif [[ "$STATUS_STR" == "finding" ]]; then
    echo "Findings: $CRASH_COUNT crash(es) detected."
    echo ""
    echo "Next steps:"
    echo "  1. Review crash input: xxd $CORPUS_DIR/crash_* | head -20"
    echo "  2. Reproduce: python -c \"from ftllexengine.syntax.parser import FluentParserV1; ..."
    echo "  3. Create unit test in tests/ with the crash input as a literal"
    echo "  4. Fix the bug in the parser code"
    echo "  5. See: docs/FUZZING_GUIDE.md (Bug Preservation Workflow)"
    echo ""
    echo "Crash files:"
    find "$CORPUS_DIR" -name 'crash_*' -type f -exec basename {} \; | head -5
else
    echo "Error: Script or environment failure."
fi
echo "=============================================================================="

# JSON summary for automation
echo "[SUMMARY-JSON-BEGIN]"
printf "{"
printf "\"result\":\"%s\"," "$STATUS_STR"
printf "\"exit_code\":\"%d\"," "$EXIT_CODE"
printf "\"duration_sec\":\"%s\"," "$DURATION"
printf "\"target\":\"%s\"," "$TARGET_FILE"
printf "\"workers\":\"%s\"," "$JOBS"
printf "\"crash_count\":\"%s\"," "$CRASH_COUNT"
printf "\"finding_type\":\"%s\"," "$FINDING_TYPE"
printf "\"coverage\":\"%s\"," "$COVERAGE"
printf "\"corpus_size\":\"%s\"," "$CORPUS_SIZE"
printf "\"exec_per_sec\":\"%s\"" "$EXEC_SPEED"
printf "}\n"
echo "[SUMMARY-JSON-END]"

echo "[END-FUZZ]"
exit $EXIT_CODE
