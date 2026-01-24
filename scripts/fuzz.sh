#!/usr/bin/env bash
# ==============================================================================
# fuzz.sh — Universal Fuzzing Interface (Agent-Native Edition)
# ==============================================================================
# COMPATIBILITY: Bash 5.0+
# ARCHITECTURAL INTENT:
#   Unifies Property-Based Testing (Hypothesis) and Native Fuzzing (Atheris)
#   under a single, verifiable, agent-friendly protocol.
# ==============================================================================

# Bash Settings
set -o errexit
set -o nounset
set -o pipefail
if [[ "${BASH_VERSINFO[0]}" -ge 5 ]]; then
    shopt -s inherit_errexit 2>/dev/null || true
fi

# [SECTION: ENVIRONMENT]
# Dedicated environment for fuzzing to avoid stomping by other tasks
export UV_PROJECT_ENVIRONMENT=".venv-fuzzing"
unset VIRTUAL_ENV

# Artifacts Directory (Agent-Native Standard)
ARTIFACTS_DIR=".fuzz_artifacts"
mkdir -p "$ARTIFACTS_DIR"

# [SECTION: HELPERS]
log_info() { echo -e "\033[34m[INFO]\033[0m $1"; }
log_pass() { echo -e "\033[32m[PASS]\033[0m $1"; }
log_warn() { echo -e "\033[33m[WARN]\033[0m $1"; }
log_err()  { echo -e "\033[31m[ERROR]\033[0m $1" >&2; }

# [SECTION: ARGUMENT_PARSING]
MODE=""
VERBOSE="false"
JSON_OUTPUT="false"
WORKERS=4
TIME_LIMIT=""
TARGET=""
REPRO_FILE=""
MINIMIZE_FILE=""
CLEAN="false"

usage() {
    cat <<EOF
Usage: ./scripts/fuzz.sh [MODE] [OPTIONS]

Modes (Mutually Exclusive):
  --check        Run fast property tests (Default)
  --deep         Run continuous coverage-guided fuzzing (HypoFuzz)
  --native       Run native structural fuzzing (Atheris)
  --runtime      Run end-to-end runtime fuzzing (Atheris)
  --structured   Run structure-aware fuzzing (Atheris)
  --perf         Run performance fuzzing (ReDoS detection)
  --iso          Run ISO 3166/4217 introspection fuzzing (Atheris)
  --fiscal       Run fiscal calendar arithmetic fuzzing (Atheris)
  --repro FILE   Reproduce a specific crash artifact
  --minimize FILE  Minimize a crash to smallest reproducer
  --list         List known failures
  --corpus       Check seed corpus health
  --clean        Clean corpus and artifacts

Options:
  --verbose      Stream output to console
  --json         Output JSON summary (Quiet by default)
  --time SEC     Stop after SEC seconds (Continuous modes only)
  --workers N    Number of parallel workers (Default: 4)
  --target FILE  Specific target file (Check mode only)
  --help         Show this help

EOF
    exit 1
}

# Strict Argument Parser
while [[ $# -gt 0 ]]; do
    case "$1" in
        --check|--deep|--native|--runtime|--structured|--perf|--iso|--fiscal|--list|--corpus|--clean)
            if [[ -n "$MODE" && "$MODE" != "$1" ]]; then
                log_err "Conflicting modes selected: $MODE vs $1"
                exit 1
            fi
            MODE="${1#--}" # strip leading --
            shift
            ;;
        --repro)
            if [[ -n "$MODE" ]]; then log_err "Conflicting modes selected"; exit 1; fi
            MODE="repro"
            if [[ -z "${2:-}" ]]; then log_err "Missing file argument for --repro"; exit 1; fi
            REPRO_FILE="$2"
            shift 2
            ;;
        --minimize)
            if [[ -n "$MODE" ]]; then log_err "Conflicting modes selected"; exit 1; fi
            MODE="minimize"
            if [[ -z "${2:-}" ]]; then log_err "Missing file argument for --minimize"; exit 1; fi
            MINIMIZE_FILE="$2"
            shift 2
            ;;
        --verbose|-v) VERBOSE="true"; shift ;;
        --json) JSON_OUTPUT="true"; shift ;;
        --time) TIME_LIMIT="$2"; shift 2 ;;
        --workers) WORKERS="$2"; shift 2 ;;
        --target) TARGET="$2"; shift 2 ;;
        --help|-h) usage ;;
        *) log_err "Unknown argument: $1"; usage ;;
    esac
done

# Default Mode
if [[ -z "$MODE" ]]; then MODE="check"; fi

# Validate Logic
if [[ "$MODE" == "native" && -n "$TARGET" ]]; then
    log_warn "--target is ignored in native mode (uses fuzz/stability.py)"
fi

# [SECTION: PREFLIGHT]
# All modes requiring python execution need environment validation
preflight_checks() {
    if ! command -v uv >/dev/null; then
        log_err "uv is required but not found."
        exit 1
    fi
    
    # Check if .venv-fuzzing needs creation
    if [[ ! -d ".venv-fuzzing" ]]; then
        if [[ "$JSON_OUTPUT" == "false" ]]; then
            log_info "Creating dedicated fuzzing environment..."
        fi
        uv sync --group fuzzing --quiet
    fi
}

preflight_atheris() {
    # Check for Atheris installation
    if ! uv run --group fuzzing python -c "import atheris" >/dev/null 2>&1; then
        if [[ "$JSON_OUTPUT" == "true" ]]; then
            echo '{"status":"error","message":"Atheris not installed"}'
            exit 1
        else
            log_err "Atheris is not installed or broken."
            log_info "Running diagnosis..."
            ./scripts/check-atheris.sh
            exit 1
        fi
    fi
}

# [SECTION: SIGNAL_HANDLING]
# Ensures we kill child processes (fuzzers) when the script is killed
PID_LIST=()
cleanup() {
    if [[ ${#PID_LIST[@]} -gt 0 ]]; then
        # log_info "Cleaning up child processes..."
        for pid in "${PID_LIST[@]}"; do
            kill -TERM "$pid" 2>/dev/null || true
        done
        wait
    fi
}
trap cleanup EXIT INT TERM

# [SECTION: EXECUTION_LOGIC]

# 1. RUN CHECK (Pytest Property Tests)
run_check() {
    TEST_TARGET="${TARGET:-tests/test_grammar_based_fuzzing.py}"
    CMD=(uv run pytest "$TEST_TARGET")
    
    if [[ "$VERBOSE" == "true" ]]; then
        CMD+=("-v")
    else
        CMD+=("-q" "--no-header" "--no-summary")
    fi
    
    # Run with output capture
    TEMP_LOG="/tmp/fuzz_output_$$.log"
    trap "rm -f '$TEMP_LOG'" RETURN

    set +e
    if [[ "$VERBOSE" == "true" ]]; then
        # Verbose: Stream to terminal AND capture for parsing
        "${CMD[@]}" 2>&1 | tee "$TEMP_LOG"
        EXIT_CODE=${PIPESTATUS[0]}
    else
        # Quiet: Capture only
        "${CMD[@]}" > "$TEMP_LOG" 2>&1
        EXIT_CODE=$?
    fi
    set -e
    
    # Report Construction: ALL parsing done in Python for robustness
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
        fail_ex = log_content.split('Falsifying example')[1].split('\n')[0][:200].strip()
    except IndexError:
        pass

report = {
    'mode': 'check',
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
    
    # Human Output
    if [[ "$JSON_OUTPUT" == "false" && $EXIT_CODE -eq 0 ]]; then
        log_pass "Property tests passed (see JSON for counts)."
    elif [[ "$JSON_OUTPUT" == "false" ]]; then
        log_err "Property tests failed. See JSON or use --verbose."
    fi
    
    # Proper exit code
    echo "[EXIT-CODE] $EXIT_CODE"
}

# 2. RUN DEEP (HypoFuzz)
run_deep() {
    CMD=(uv run --group fuzzing hypothesis fuzz --no-dashboard -n "$WORKERS")
    [[ -n "$TIME_LIMIT" ]] && CMD+=("--max-examples=$((TIME_LIMIT * 100))")
    CMD+=("tests/")
    
    # Execution
    TEMP_LOG="/tmp/fuzz_output_$$.log"
    trap "rm -f '$TEMP_LOG'" RETURN
    log_info "Starting HypoFuzz (Deep Mode)..."
    
    # Run with verbose streaming support
    set +e
    if [[ "$VERBOSE" == "true" ]]; then
        # Verbose: Stream to terminal AND capture for parsing
        "${CMD[@]}" 2>&1 | tee "$TEMP_LOG"
        EXIT_CODE=${PIPESTATUS[0]}
    else
        # Quiet: Run in background, capture only
        "${CMD[@]}" > "$TEMP_LOG" 2>&1 &
        PID=$!
        PID_LIST+=("$PID")
        wait "$PID" || true
        EXIT_CODE=$?
    fi
    set -e
    
    # Analysis
    FINDINGS=$(grep -c "Falsifying example" "$TEMP_LOG" || true)
    
    # Build Report
    python3 -c "
import json
print('[SUMMARY-JSON-BEGIN]')
print(json.dumps({
    'mode': 'deep',
    'findings': int('$FINDINGS'),
    'duration_limit': '$TIME_LIMIT',
    'exit_code': int('$EXIT_CODE')
}))
print('[SUMMARY-JSON-END]')
"
    # Artifact Collection (Hypothesis stores in internal DB, but we can check failure dir)
    if [[ -d ".hypothesis/failures" ]]; then
        count=$(find .hypothesis/failures -type f | wc -l)
        if [[ $count -gt 0 ]]; then
            log_warn "Found $count failure artifacts in .hypothesis/failures"
        fi
    fi

    echo "[EXIT-CODE] $EXIT_CODE"
}

# 3. RUN NATIVE (Atheris) - Absorbed Logic
run_native_logic() {
    local TARGET_SCRIPT="$1"
    local CORPUS_DIR=".fuzz_corpus"
    mkdir -p "$CORPUS_DIR"
    
    CMD=(uv run --group fuzzing python "$TARGET_SCRIPT")
    CMD+=("-workers=$WORKERS")
    CMD+=("-artifact_prefix=$ARTIFACTS_DIR/crash_")
    [[ -n "$TIME_LIMIT" ]] && CMD+=("-max_total_time=$TIME_LIMIT")
    CMD+=("$CORPUS_DIR")
    # Add seeds if exist
    [[ -d "fuzz/seeds" ]] && CMD+=("fuzz/seeds")
    
    if [[ "$JSON_OUTPUT" == "false" ]]; then
        log_info "Starting Atheris ($TARGET_SCRIPT)..."
        log_info "Artifacts will be saved to: $ARTIFACTS_DIR"
    fi
    
    TEMP_LOG="/tmp/fuzz_output_$$.log"
    trap "rm -f '$TEMP_LOG'" RETURN
    
    # Run with verbose streaming support
    set +e
    if [[ "$VERBOSE" == "true" ]]; then
        # Verbose: Stream to terminal AND capture for parsing
        "${CMD[@]}" 2>&1 | tee "$TEMP_LOG"
        EXIT_CODE=${PIPESTATUS[0]}
    else
        # Quiet: Run in background, capture only
        "${CMD[@]}" > "$TEMP_LOG" 2>&1 &
        PID=$!
        PID_LIST+=("$PID")
        wait "$PID" || true
        EXIT_CODE=$?
    fi
    set -e
    
    # Collect Artifacts
    CRASHES=$(find "$ARTIFACTS_DIR" -name "crash_*" 2>/dev/null | wc -l | tr -d ' ')
    
    # Parse Coverage/Speed
    STATS=$(tail -n 50 "$TEMP_LOG" | grep "cov:" | tail -1 || echo "")
    
    python3 -c "
import json
print('[SUMMARY-JSON-BEGIN]')
print(json.dumps({
    'mode': 'native',
    'crash_count': int('$CRASHES'),
    'last_stats': '$STATS',
    'exit_code': int('$EXIT_CODE')
}))
print('[SUMMARY-JSON-END]')
"

    echo "[EXIT-CODE] $EXIT_CODE"
}


# [SECTION: DISPATCHER]
preflight_checks

case "$MODE" in
    check)
        run_check
        ;;
    deep)
        run_deep
        ;;
    native)
        preflight_atheris
        run_native_logic "fuzz/stability.py"
        ;;
    runtime)
        preflight_atheris
        run_native_logic "fuzz/runtime.py"
        ;;
    structured)
        preflight_atheris
        run_native_logic "fuzz/structured.py"
        ;;
    perf)
        preflight_atheris
        run_native_logic "fuzz/perf.py"
        ;;
    iso)
        preflight_atheris
        run_native_logic "fuzz/iso.py"
        ;;
    fiscal)
        preflight_atheris
        run_native_logic "fuzz/fiscal.py"
        ;;
    repro)
        if [[ ! -f "$REPRO_FILE" ]]; then
            log_err "Crash file not found: $REPRO_FILE"
            exit 1
        fi
        log_info "Reproducing crash: $REPRO_FILE"
        CRASH_CONTENT=$(xxd -p "$REPRO_FILE" | tr -d '\n')
        echo ""
        echo "To add as @example decorator, use:"
        echo "  @example(bytes.fromhex('$CRASH_CONTENT'))"
        echo ""
        echo "[EXIT-CODE] 0"
        ;;
    minimize)
        if [[ ! -f "$MINIMIZE_FILE" ]]; then
            log_err "Crash file not found: $MINIMIZE_FILE"
            exit 1
        fi
        preflight_atheris
        log_info "Minimizing crash: $MINIMIZE_FILE"
        MINIMIZED="${MINIMIZE_FILE}.minimized"
        # Run with -minimize_crash=1 and the crash file
        uv run --group fuzzing python fuzz/stability.py \
            -minimize_crash=1 \
            -exact_artifact_path="$MINIMIZED" \
            "$MINIMIZE_FILE"
        if [[ -f "$MINIMIZED" ]]; then
            ORIG_SIZE=$(stat -f%z "$MINIMIZE_FILE" 2>/dev/null || stat -c%s "$MINIMIZE_FILE")
            NEW_SIZE=$(stat -f%z "$MINIMIZED" 2>/dev/null || stat -c%s "$MINIMIZED")
            log_pass "Minimized: $ORIG_SIZE -> $NEW_SIZE bytes"
            echo "Minimized crash saved to: $MINIMIZED"
        else
            log_err "Minimization failed."
            exit 1
        fi
        echo "[EXIT-CODE] 0"
        ;;
    corpus)
        log_info "Checking seed corpus health..."
        if [[ -f "scripts/corpus-health.py" ]]; then
            uv run python scripts/corpus-health.py
        else
            # Fallback: simple count
            SEED_COUNT=$(find fuzz/seeds -type f 2>/dev/null | wc -l | tr -d ' ')
            log_pass "Seed corpus: $SEED_COUNT files"
        fi
        echo "[EXIT-CODE] 0"
        ;;
    clean)
        log_info "Cleaning artifacts..."
        rm -rf "$ARTIFACTS_DIR" .fuzz_corpus .hypothesis/failures
        log_pass "Cleaned."
        echo "[EXIT-CODE] 0"
        ;;
    list)
        log_info "Known failures:"
        find "$ARTIFACTS_DIR" -name "crash_*" 2>/dev/null || true
        find .hypothesis/failures -type f 2>/dev/null || true
        echo "[EXIT-CODE] 0"
        ;;
esac
