#!/usr/bin/env bash
# ==============================================================================
# test.sh — Isolated Test Runner (Agent-Native Edition)
# Version: 1.0.0
# ==============================================================================
# COMPATIBILITY: Bash 5.0+ (Optimized for 5.3)
# ARCHITECTURAL INTENT: 
#   Strict environment isolation using versioned virtual environments.
#
# AI AGENT OPTIMIZATION:
#   - Quiet by default (Log-on-Fail)
#   - Periodic heartbeat in all modes (prevents long silent hangs)
#   - Focused failure digest with persisted full log path
#   - Structured markers: [SECTION-NAME] for navigation
#   - JSON output: [SUMMARY-JSON-BEGIN/END] with "failed_tests"
#   - Debug suggestions: [DEBUG-SUGGESTION] blocks
#   - Exit codes: [EXIT-CODE] N for CI integration
#   - No ANSI/Progress noise: Forced monochrome and no-progress bars
# ==============================================================================

# Guarantee POSIX system binaries (/usr/bin, /bin) survive exec pivots (uv run, sudo, etc.).
# This must be the first statement — before any external command is invoked.
export PATH="/usr/bin:/bin:${PATH:-}"

# Bash 5.0+ is a hard requirement: associative arrays, inherit_errexit, EPOCHREALTIME.
if [[ "${BASH_VERSINFO[0]}" -lt 5 ]]; then
    echo "Error: Bash 5.0+ required (current: ${BASH_VERSION})." >&2
    echo "       Install via Homebrew: brew install bash" >&2
    exit 1
fi

# Bash Settings
SCRIPT_VERSION="1.0.0"
SCRIPT_NAME="test.sh"

set -o errexit
set -o nounset
set -o pipefail
shopt -s inherit_errexit

# [SECTION: ENVIRONMENT_ISOLATION]
PY_VERSION="${PY_VERSION:-3.14}"
TARGET_VENV=".venv-${PY_VERSION}"

if [[ "${UV_PROJECT_ENVIRONMENT:-}" != "$TARGET_VENV" ]]; then
    if [[ "${TEST_ALREADY_PIVOTED:-}" == "1" ]]; then
        echo "Error: Detected re-execution loop. Aborting." >&2
        exit 1
    fi
    echo -e "\033[34m[INFO]\033[0m Pivoting to isolated environment: ${TARGET_VENV}"
    export UV_PROJECT_ENVIRONMENT="$TARGET_VENV"
    export TEST_ALREADY_PIVOTED=1
    unset VIRTUAL_ENV
    exec uv run --python "$PY_VERSION" "${BASH:-bash}" "$0" "$@"
else
    unset TEST_ALREADY_PIVOTED
fi

# [SECTION: SETUP]
DEFAULT_COV_LIMIT=95
QUICK_MODE=false
CI_MODE=false
CLEAN_CACHE=true
VERBOSE=false
SHOW_FULL_LOG_ON_FAIL=false
HEARTBEAT_ENABLED=true
PYTEST_EXTRA_ARGS=()
IS_GHA="${GITHUB_ACTIONS:-false}"
HEARTBEAT_INTERVAL_SEC="${TEST_HEARTBEAT_INTERVAL_SEC:-30}"
FAILURE_TAIL_LINES="${TEST_FAILURE_TAIL_LINES:-80}"
FAILURE_LOG_PATH="${TEST_FAILURE_LOG_PATH:-tmp/test-last-failure.log}"

if [[ "${NO_COLOR:-}" == "1" ]]; then
    RED=""; GREEN=""; YELLOW=""; BLUE=""; CYAN=""; BOLD=""; RESET=""
else
    RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"; BLUE="\033[34m"; CYAN="\033[36m"; BOLD="\033[1m"; RESET="\033[0m"
fi

# psutil availability: cached once for heartbeat CPU/memory stats.
# psutil is a dev dependency — available in the test venv.
HAS_PSUTIL=false
python -c "import psutil" 2>/dev/null && HAS_PSUTIL=true || true

log_group_start() { [[ "$IS_GHA" == "true" ]] && echo "::group::$1"; echo -e "\n${BOLD}${CYAN}=== $1 ===${RESET}"; }
log_group_end() { [[ "$IS_GHA" == "true" ]] && echo "::endgroup::"; return 0; }
log_info() { echo -e "${BLUE}[INFO]${RESET} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${RESET} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${RESET} $1"; }
log_err()  { echo -e "${RED}[ERROR]${RESET} $1" >&2; }
format_bytes() {
    local bytes="$1"
    if (( bytes >= 1048576 )); then
        printf "%d MiB" $((bytes / 1048576))
    elif (( bytes >= 1024 )); then
        printf "%d KiB" $((bytes / 1024))
    else
        printf "%d B" "$bytes"
    fi
}
last_nonempty_log_line() {
    local log_file="$1"
    local last_line
    last_line=$(awk 'NF { line = $0 } END { print line }' "$log_file")
    last_line=${last_line//$'\r'/}
    if [[ -z "$last_line" ]]; then
        echo "awaiting first pytest output"
        return 0
    fi
    if (( ${#last_line} > 160 )); then
        echo "${last_line:0:157}..."
        return 0
    fi
    echo "$last_line"
}
_heartbeat_daemon() {
    # Background subshell: emits [HEARTBEAT] lines to stderr while watched_pid is alive.
    # First beat fires at T+5s (short runs stay silent); subsequent beats every
    # HEARTBEAT_INTERVAL_SEC seconds. Uses psutil for CPU/memory when available.
    #
    # Delta tracking: if the last log line has not changed since the previous beat,
    # shows "(no new output, Xs)" instead of repeating the stale line. Indicates
    # whether the process is making progress or genuinely stuck.
    local watched_pid="$1" log_file="$2" start_sec="$3"
    local prev_last_line="" prev_change_sec=$SECONDS
    sleep 5
    while kill -0 "$watched_pid" 2>/dev/null; do
        local elapsed=$(( SECONDS - start_sec ))
        local log_bytes=0
        [[ -f "$log_file" ]] && log_bytes=$(wc -c < "$log_file" | tr -d '[:space:]')
        local raw_last_line last_display
        raw_last_line=$(last_nonempty_log_line "$log_file")
        if [[ "$raw_last_line" == "$prev_last_line" ]]; then
            local unchanged_sec=$(( SECONDS - prev_change_sec ))
            last_display="(no new output, ${unchanged_sec}s)"
        else
            last_display="$raw_last_line"
            prev_last_line="$raw_last_line"
            prev_change_sec=$SECONDS
        fi
        if [[ "$HAS_PSUTIL" == "true" ]]; then
            local stats
            stats=$(python -c "
import psutil
try:
    p = psutil.Process(${watched_pid})
    all_procs = [p] + p.children(recursive=True)
    cpu = sum(x.cpu_percent(interval=0.2) for x in all_procs)
    mem_mb = sum(x.memory_info().rss for x in all_procs) // 1048576
    print(f'CPU={cpu:.0f}% MEM={mem_mb}MB procs={len(all_procs)}')
except Exception:
    print('CPU=? MEM=? procs=?')
" 2>/dev/null || echo "CPU=? MEM=? procs=?")
            echo "[HEARTBEAT] T+${elapsed}s | ${stats} | log=$(format_bytes "$log_bytes") | last: ${last_display}" >&2
        else
            echo "[HEARTBEAT] T+${elapsed}s | log=$(format_bytes "$log_bytes") | last: ${last_display}" >&2
        fi
        sleep "$HEARTBEAT_INTERVAL_SEC"
    done
}
run_and_capture() {
    # FIFO-based runner: captures pytest output to log_file and emits [HEARTBEAT]
    # to stderr in all modes. In verbose mode, output is also streamed to stdout.
    #
    # Using a FIFO gives an exact pytest PID for psutil monitoring and a reliable
    # exit code via "wait $cmd_pid" — avoids PIPESTATUS fragility with background pipes.
    local log_file="$1"
    local fifo
    fifo=$(mktemp -u)
    mkfifo "$fifo"

    "${CMD[@]}" > "$fifo" 2>&1 &
    local cmd_pid=$!

    local hb_pid=0
    if [[ "$HEARTBEAT_ENABLED" == "true" && "$HEARTBEAT_INTERVAL_SEC" -gt 0 ]]; then
        _heartbeat_daemon "$cmd_pid" "$log_file" "$SECONDS" &
        hb_pid=$!
    fi

    if [[ "$VERBOSE" == "true" ]]; then
        tee "$log_file" < "$fifo"
    else
        cat < "$fifo" > "$log_file"
    fi

    wait "$cmd_pid"
    local exit_code=$?

    if [[ "$hb_pid" -gt 0 ]]; then
        kill "$hb_pid" 2>/dev/null || true
        wait "$hb_pid" 2>/dev/null || true
    fi

    rm -f "$fifo"
    return "$exit_code"
}
persist_failure_log() {
    local log_file="$1"
    local failure_dir
    failure_dir=$(dirname "$FAILURE_LOG_PATH")
    mkdir -p "$failure_dir"
    cp "$log_file" "$FAILURE_LOG_PATH"
}
emit_failure_digest() {
    local log_file="$1"
    local failure_section summary_section
    failure_section=$(mktemp)
    summary_section=$(mktemp)

    awk '
        /^=+ FAILURES =+$/ { capture = 1 }
        capture { print }
        capture && /^=+ short test summary info =+$/ { exit }
    ' "$log_file" > "$failure_section"

    awk '
        /^=+ short test summary info =+$/ { capture = 1 }
        capture { print }
    ' "$log_file" > "$summary_section"

    if [[ -s "$failure_section" ]]; then
        echo "[FAILURE-EXCERPT]"
        cat "$failure_section"
    fi

    if [[ -s "$summary_section" ]]; then
        if [[ -s "$failure_section" ]]; then
            echo
        fi
        echo "[SUMMARY-EXCERPT]"
        cat "$summary_section"
    elif [[ ! -s "$failure_section" ]]; then
        echo "[SUMMARY-EXCERPT]"
        tail -n "$FAILURE_TAIL_LINES" "$log_file"
    fi

    rm -f "$failure_section" "$summary_section"
}

# CLI Args Parsing
while [[ $# -gt 0 ]]; do
    case "$1" in
        --quick)    QUICK_MODE=true; shift ;;
        --ci)       CI_MODE=true; shift ;;
        --no-clean) CLEAN_CACHE=false; shift ;;
        --verbose)  VERBOSE=true; shift ;;
        --show-full-log-on-fail) SHOW_FULL_LOG_ON_FAIL=true; shift ;;
        --no-heartbeat) HEARTBEAT_ENABLED=false; shift ;;
        --)         shift; PYTEST_EXTRA_ARGS+=("$@"); break ;;
        *)          PYTEST_EXTRA_ARGS+=("$1"); shift ;;
    esac
done

if ! [[ "$HEARTBEAT_INTERVAL_SEC" =~ ^[0-9]+$ ]]; then
    log_err "TEST_HEARTBEAT_INTERVAL_SEC must be an integer (got: $HEARTBEAT_INTERVAL_SEC)"
    exit 1
fi

if ! [[ "$FAILURE_TAIL_LINES" =~ ^[0-9]+$ ]]; then
    log_err "TEST_FAILURE_TAIL_LINES must be an integer (got: $FAILURE_TAIL_LINES)"
    exit 1
fi

# Auto-configure PYTHONPATH to include 'src' if it exists (Parity with lint.sh)
if [[ -d "src" ]]; then
    export PYTHONPATH="${PWD}/src:${PYTHONPATH:-}"
else
    export PYTHONPATH="${PWD}:${PYTHONPATH:-}"
fi

# [SECTION: DIAGNOSTICS]
pre_flight_diagnostics() {
    log_group_start "Pre-Flight Diagnostics"
    echo "[ INFO ] Script               : $SCRIPT_NAME v$SCRIPT_VERSION"
    echo "[  OK  ] Schema               : universal-agent-v1"

    if [[ "${UV_PROJECT_ENVIRONMENT:-}" == "$TARGET_VENV" ]]; then
       echo "[  OK  ] Environment          : Isolated ($TARGET_VENV)"
    else
       echo "[ INFO ] Environment          : System/User ($VIRTUAL_ENV)"
    fi
    echo "[ INFO ] Python               : $(python --version)"
    echo "[ INFO ] PYTHONPATH           : ${PYTHONPATH:-<empty>}"
    
    if ! command -v pytest >/dev/null 2>&1; then
        echo "[ FAIL ] Tooling             : Pytest missing (uv sync required)"
        exit 1
    fi
    echo "[  OK  ] Tool Verified        : pytest"
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
    rm -rf .pytest_cache
    rm -rf .hypothesis/unicode_data .hypothesis/constants
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    log_info "Test caches cleared."
    log_group_end
fi

# [SECTION: TARGETS]
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

# forced agent-friendly defaults handled via env vars where possible
export NO_COLOR=1

if [[ "$CI_MODE" == "true" || "$VERBOSE" == "true" ]]; then
    CMD+=("-vv")
fi

# Always show hypothesis statistics (valuable for both Agents and Humans)
CMD+=("--hypothesis-show-statistics")

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

# Targets (Positional Args) Last
if [[ -d "tests" ]]; then CMD+=("tests"); fi
if [[ -d "test" ]]; then CMD+=("test"); fi

# [SECTION: EXECUTION]
log_group_start "Pytest Execution"
log_info "Command: ${CMD[*]@Q}"

LOG_FILE=$(mktemp)
trap 'rm -f "$LOG_FILE"' EXIT

START_TIME="${EPOCHREALTIME}"
RUN_START_SECONDS=$SECONDS

# Execution: FIFO-based capture with heartbeat in all modes.
# The FIFO gives an exact pytest PID for psutil monitoring and a reliable
# exit code (wait $cmd_pid, not PIPESTATUS). Heartbeat fires on stderr so
# it does not pollute the captured log or the agent's stdout stream.
set +e
run_and_capture "$LOG_FILE"
EXIT_CODE=$?
set -e

END_TIME="${EPOCHREALTIME}"
DURATION=$(printf "%.3f" "$(echo "$END_TIME - $START_TIME" | bc)")

# [SECTION: ANALYSIS]
HYPOTHESIS_FAILURE="false"
FALSIFYING_EXAMPLE=""
declare -a FAILED_TEST_LIST=()

# Extract test statistics
set +e
TESTS_PASSED=$(grep -o '[0-9]* passed' "$LOG_FILE" | tail -1 | grep -o '[0-9]*' || echo "0")
TESTS_FAILED=$(grep -o '[0-9]* failed' "$LOG_FILE" | tail -1 | grep -o '[0-9]*' || echo "0")
TESTS_SKIPPED=$(grep -o '[0-9]* skipped' "$LOG_FILE" | tail -1 | grep -o '[0-9]*' || echo "0")
COVERAGE_PCT=$(grep 'TOTAL' "$LOG_FILE" | tail -1 | awk '{print $NF}' | tr -d '%')
[[ -z "$TESTS_PASSED" ]] && TESTS_PASSED=0
[[ -z "$TESTS_FAILED" ]] && TESTS_FAILED=0
[[ -z "$TESTS_SKIPPED" ]] && TESTS_SKIPPED=0
[[ -z "$COVERAGE_PCT" ]] && COVERAGE_PCT=0

# Extract fuzz vs non-fuzz skip breakdown (emitted by conftest.py)
SKIPPED_FUZZ=$(grep -o '\[SKIP-BREAKDOWN\] fuzz=[0-9]* other=[0-9]*' "$LOG_FILE" | grep -o 'fuzz=[0-9]*' | cut -d= -f2 || echo "0")
SKIPPED_OTHER=$(grep -o '\[SKIP-BREAKDOWN\] fuzz=[0-9]* other=[0-9]*' "$LOG_FILE" | grep -o 'other=[0-9]*' | cut -d= -f2 || echo "0")
[[ -z "$SKIPPED_FUZZ" ]] && SKIPPED_FUZZ=0
[[ -z "$SKIPPED_OTHER" ]] && SKIPPED_OTHER=0

# Extract Failed Test IDs (for Debug Suggestion)
# Pattern: "FAILED tests/test_module.py::test_case - ..."
# We look for lines starting with FAILED (standard pytest without -p no:terminal might differ, but with -p no:terminal it's clean)
# With -p no:terminal, output is simpler. "FAILED test_path::test_name"
# Universal parsing: extract test IDs from output (handle spaces/quotes)
# Support: "FAILED tests/test_foo.py::test_bar[param with spaces] - AssertionError: ..."
# We look for "FAILED <id> - " and capture <id>.
# Use Perl-compatible regex in grep if available, or just use sed to strip the prefix and suffix.
# Sed logic:
# 1. s/^FAILED //  -> Remove leading FAILED
# 2. s/ - .*//     -> Remove trailing " - <Error>"
# 3. s/ FAILED.*// -> Remove trailing " FAILED" (verbose mode)
mapfile -t FAILED_TEST_LIST < <(grep -E "^FAILED | FAILED " "$LOG_FILE" | sed -E 's/^FAILED //' | sed -E 's/ - .*//' | sed -E 's/ FAILED.*//' | sort -u)

# Hypothesis Check
if grep -q "Falsifying example" "$LOG_FILE"; then
    HYPOTHESIS_FAILURE="true"
    FALSIFYING_EXAMPLE=$(grep -A 5 "Falsifying example" "$LOG_FILE")
fi
set -e

# Output Logic
log_group_end

if [[ $EXIT_CODE -eq 0 ]]; then
    log_pass "All tests passed in $TARGET_VENV ($DURATION sec)."
    if [[ "$SKIPPED_OTHER" -gt 0 ]]; then
        log_warn "Non-fuzz skipped tests detected: $SKIPPED_OTHER (investigate these — only fuzz tests should be skipped)"
    fi
else
    persist_failure_log "$LOG_FILE"
    log_group_start "Failure Details"
    if [[ "$SHOW_FULL_LOG_ON_FAIL" == "true" ]]; then
        cat "$LOG_FILE"
    else
        emit_failure_digest "$LOG_FILE"
    fi
    echo
    log_info "Full pytest log saved to: $FAILURE_LOG_PATH"
    log_group_end
    
    if [[ "$HYPOTHESIS_FAILURE" == "true" ]]; then
        echo -e "\n${BOLD}${RED}[HYPOTHESIS FLAGGED LOGIC FLAW]${RESET}"
        echo -e "${YELLOW}Analyze this specific input:${RESET}"
        echo -e "$FALSIFYING_EXAMPLE"
    fi
fi

# [SECTION: REPORT]
log_group_start "Final Report"

# Emit human-readable failed test list BEFORE the JSON block so agents
# and humans can read failure names without parsing JSON.
if [[ $EXIT_CODE -ne 0 && ${#FAILED_TEST_LIST[@]} -gt 0 ]]; then
    echo -e "\n${RED}[FAILED TESTS] ${#FAILED_TEST_LIST[@]} test(s) failed:${RESET}"
    for t in "${FAILED_TEST_LIST[@]}"; do
        echo "  $t"
    done
fi

echo "[SUMMARY-JSON-BEGIN]"
PYTHON_JSON_SCRIPT="
import json, sys, os

try:
    with open(sys.argv[1], 'r') as f:
        failed_tests = sorted(list(set(line.strip() for line in f if line.strip())))
except FileNotFoundError:
    failed_tests = []

final_obj = {
    'script': sys.argv[11],
    'script_version': sys.argv[12],
    'result': 'pass' if int(sys.argv[2]) == 0 else 'fail',
    'duration_sec': sys.argv[3],
    'tests_passed': int(sys.argv[4]),
    'tests_failed': int(sys.argv[5]),
    'tests_skipped': int(sys.argv[6]),
    'skipped_fuzz': int(sys.argv[7]),
    'skipped_other': int(sys.argv[8]),
    'coverage_pct': float(sys.argv[9]),
    'hypothesis_fail': sys.argv[10].lower() == 'true',
    'failed_tests': failed_tests,
    'exit_code': int(sys.argv[2])
}

print(json.dumps(final_obj, separators=(',', ':')))
"

# Dump failed tests to a temp file for Python to read
FAILED_TESTS_FILE=$(mktemp)
for item in "${FAILED_TEST_LIST[@]}"; do
    echo "$item" >> "$FAILED_TESTS_FILE"
done

python -c "$PYTHON_JSON_SCRIPT" "$FAILED_TESTS_FILE" "$EXIT_CODE" "$DURATION" "$TESTS_PASSED" "$TESTS_FAILED" "$TESTS_SKIPPED" "$SKIPPED_FUZZ" "$SKIPPED_OTHER" "$COVERAGE_PCT" "$HYPOTHESIS_FAILURE" "$SCRIPT_NAME" "$SCRIPT_VERSION"
rm -f "$FAILED_TESTS_FILE"
echo "[SUMMARY-JSON-END]"

# Debug Suggestions
if [[ $EXIT_CODE -ne 0 && ${#FAILED_TEST_LIST[@]} -gt 0 ]]; then
    echo -e "\n${YELLOW}[DEBUG-SUGGESTION]${RESET}"
    echo "The following tests failed. Run this command to debug the first failure:"
    echo "  uv run pytest ${FAILED_TEST_LIST[0]} --pdb"
fi

if [[ $EXIT_CODE -ne 0 ]]; then
    log_err "Tests FAILED."
    echo "[EXIT-CODE] 1" >&2
    exit 1
else
    echo "[EXIT-CODE] 0" >&2
    exit 0
fi
