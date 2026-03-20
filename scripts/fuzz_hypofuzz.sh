#!/usr/bin/env bash
# ==============================================================================
# fuzz_hypofuzz.sh -- HypoFuzz & Property Testing Interface
# Version: 1.0.0
# ==============================================================================
# COMPATIBILITY: Bash 5.0+
#
# Single entry point for Hypothesis property testing and HypoFuzz coverage-
# guided fuzzing. Run --help for usage, modes, and profile details.
#
# AGENT PROTOCOL:
#   - Silence on Success (unless --verbose)
#   - Full Log on Failure
#   - [SUMMARY-JSON-BEGIN] ... [SUMMARY-JSON-END]
#   - [EXIT-CODE] N
# ==============================================================================

# Bash Settings
SCRIPT_VERSION="1.0.0"
SCRIPT_NAME="fuzz_hypofuzz.sh"

set -o errexit
set -o nounset
set -o pipefail
if [[ "${BASH_VERSINFO[0]}" -ge 5 ]]; then
    shopt -s inherit_errexit 2>/dev/null || true
fi

# [SECTION: ENVIRONMENT_ISOLATION]
PY_VERSION="${PY_VERSION:-3.14}"
TARGET_VENV=".venv-${PY_VERSION}"

if [[ "${UV_PROJECT_ENVIRONMENT:-}" != "$TARGET_VENV" ]]; then
    if [[ "${FUZZ_ALREADY_PIVOTED:-}" == "1" ]]; then
        echo "Error: Recursive pivot detected. Check your environment configuration." >&2
        exit 1
    fi
    if [[ -f "uv.lock" || -f "pyproject.toml" ]]; then
        echo -e "\033[34m[INFO]\033[0m Pivoting to isolated environment: ${TARGET_VENV}"
        export UV_PROJECT_ENVIRONMENT="$TARGET_VENV"
        export FUZZ_ALREADY_PIVOTED=1
        unset VIRTUAL_ENV
        exec uv run --python "$PY_VERSION" bash "$0" "$@"
    fi
else
    unset FUZZ_ALREADY_PIVOTED
fi

# [SECTION: SETUP]
# REQUIRED: Force TMPDIR to /tmp to avoid "AF_UNIX path too long" on macOS with HypoFuzz
export TMPDIR="/tmp"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
IS_GHA="${GITHUB_ACTIONS:-false}"

# Defaults
MODE="check"
VERBOSE=false
METRICS=false
WORKERS=1
TIME_LIMIT=""
TARGET=""
REPRO_TEST=""
HEARTBEAT_ENABLED=true
HEARTBEAT_INTERVAL_SEC="${FUZZ_HEARTBEAT_INTERVAL_SEC:-30}"

# Colors (respects NO_COLOR standard and non-terminal detection)
if [[ "${NO_COLOR:-}" == "1" ]]; then
    RED=""; GREEN=""; YELLOW=""; BLUE=""; CYAN=""; BOLD=""; RESET=""
elif [[ ! -t 1 ]]; then
    RED=""; GREEN=""; YELLOW=""; BLUE=""; CYAN=""; BOLD=""; RESET=""
else
    RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"; BLUE="\033[34m"; CYAN="\033[36m"; BOLD="\033[1m"; RESET="\033[0m"
fi

# psutil availability: cached once for heartbeat CPU/memory stats.
HAS_PSUTIL=false
python -c "import psutil" 2>/dev/null && HAS_PSUTIL=true || true

# Logging (consistent with lint.sh and test.sh)
log_group_start() { [[ "$IS_GHA" == "true" ]] && echo "::group::$1"; echo -e "\n${BOLD}${CYAN}=== $1 ===${RESET}"; }
log_group_end()   { [[ "$IS_GHA" == "true" ]] && echo "::endgroup::"; return 0; }
log_info() { echo -e "${BLUE}[INFO]${RESET} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${RESET} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${RESET} $1"; }
log_fail() { echo -e "${RED}[FAIL]${RESET} $1"; }
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
    last_line=$(awk 'NF { line = $0 } END { print line }' "$log_file" 2>/dev/null || true)
    last_line=${last_line//$'\r'/}
    if [[ -z "$last_line" ]]; then
        echo "awaiting first output"
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
    # shows "(no new output, Xs)" instead of repeating the stale line. This prevents
    # expected-but-frequent log messages (e.g., soft-error warnings from test iterations)
    # from making the heartbeat appear stuck.
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
_run_with_heartbeat() {
    # Run a command with FIFO capture and heartbeat.
    # Usage: _run_with_heartbeat LOG_FILE APPEND -- CMD [ARGS...]
    #   APPEND: "true" to append to log, "false" to overwrite
    # [HEARTBEAT] lines go to stderr; command output goes to log and
    # optionally to stdout (when VERBOSE=true).
    local log_file="$1" append="$2"; shift 2
    if [[ "$1" == "--" ]]; then shift; fi
    local fifo
    fifo=$(mktemp -u)
    mkfifo "$fifo"

    "$@" > "$fifo" 2>&1 &
    local cmd_pid=$!
    PID_LIST+=("$cmd_pid")

    local hb_pid=0
    if [[ "$HEARTBEAT_ENABLED" == "true" && "$HEARTBEAT_INTERVAL_SEC" -gt 0 ]]; then
        _heartbeat_daemon "$cmd_pid" "$log_file" "$SECONDS" &
        hb_pid=$!
        PID_LIST+=("$hb_pid")
    fi

    if [[ "$VERBOSE" == "true" ]]; then
        if [[ "$append" == "true" ]]; then
            tee -a "$log_file" < "$fifo" || true
        else
            tee "$log_file" < "$fifo" || true
        fi
    else
        if [[ "$append" == "true" ]]; then
            cat < "$fifo" >> "$log_file" || true
        else
            cat < "$fifo" > "$log_file" || true
        fi
    fi

    # wait returns the exit code of the process; 2>/dev/null suppresses
    # "no such process" if _on_signal already killed cmd_pid.
    wait "$cmd_pid" 2>/dev/null
    local exit_code=$?

    if [[ "$hb_pid" -gt 0 ]]; then
        kill "$hb_pid" 2>/dev/null || true
        wait "$hb_pid" 2>/dev/null || true
    fi

    # All managed processes are done; clear PID_LIST.
    # (_on_signal may have already cleared it; this is a no-op in that case.)
    PID_LIST=()

    rm -f "$fifo"
    return "$exit_code"
}

show_help() {
    local project_name="Project"
    if [[ -f "$PROJECT_ROOT/pyproject.toml" ]]; then
        project_name=$(python -c 'import sys; sys.path.append(sys.argv[1]); import tomllib; print(tomllib.load(open(sys.argv[2], "rb")).get("project", {}).get("name", "Project").capitalize())' "$PROJECT_ROOT" "$PROJECT_ROOT/pyproject.toml" 2>/dev/null || echo "Project")
    fi

    cat << HELPEOF
HypoFuzz & Property Testing Interface for $project_name

USAGE:
    ./scripts/fuzz_hypofuzz.sh [MODE] [OPTIONS]

MODES:
    (default)       Fast property tests (pytest with Hypothesis)
    --deep          Continuous coverage-guided fuzzing (HypoFuzz)
    --preflight     Audit test infrastructure (events, strategies, gaps)
    --list          Show reproduction info and recent failures
    --clean         Remove .hypothesis/ database (with confirmation)
    --repro TEST    Reproduce a failing test with verbose output
    --help          Show this help message

OPTIONS:
    --verbose       Show detailed progress during tests
    --metrics       Enable periodic per-strategy metrics (for --deep)
    --workers N     Number of parallel workers (default: 1; see NOTE below)
    --time N        Time limit in seconds (for --deep)
    --target FILE   Specific test file to run (check mode only)
    --no-heartbeat  Disable periodic [HEARTBEAT] status lines on stderr

    --force         Bypass confirmation prompts (e.g., for --clean)

HYPOTHESIS PROFILES:
    Each mode uses a different Hypothesis profile controlling iteration
    counts and timeouts. Profiles are defined in tests/conftest.py.

    Mode             Profile      Examples/test  Deadline  Notes
    ---------------  -----------  -------------  --------  -------------------
    (default)        dev          500            200ms     Fuzz tests skipped
    --deep           hypofuzz     continuous     None      HypoFuzz fuzzer
    --deep --metrics hypofuzz     10,000         None      Pytest with -m fuzz

    The default mode runs ALL tests but skips @pytest.mark.fuzz tests.
    This is why it completes quickly. Use --deep for intensive fuzzing.

    --deep targets tests/fuzz/ exclusively, concentrating all workers on
    high-value fuzz targets (state machines, grammar fuzzers, oracle tests)
    rather than diluting effort across all 1500+ @given tests in the suite.

    --deep --metrics uses pytest (single process) instead of HypoFuzz
    (continuous) because HypoFuzz multiprocessing prevents metrics
    collection across worker processes. Results are saved to
    .hypothesis/strategy_metrics.json. A human-readable summary is
    written to .hypothesis/strategy_metrics_summary.txt when weight
    skew or coverage gaps are detected.

EXAMPLES:
    # Quick check before committing (recommended)
    ./scripts/fuzz_hypofuzz.sh

    # Deep fuzzing for 5 minutes
    ./scripts/fuzz_hypofuzz.sh --deep --time 300

    # Deep fuzzing with per-strategy metrics every 10s
    ./scripts/fuzz_hypofuzz.sh --deep --metrics

    # Reproduce a specific failing test
    ./scripts/fuzz_hypofuzz.sh --repro tests/fuzz/test_syntax_parser_property.py::test_roundtrip

    # Reproduce all tests in a module
    ./scripts/fuzz_hypofuzz.sh --repro tests/fuzz/test_syntax_parser_property.py

    # Clean database without prompting
    ./scripts/fuzz_hypofuzz.sh --clean --force

NOTE:
    Hypothesis automatically stores and replays failing examples from
    .hypothesis/examples/. Simply re-running pytest will reproduce failures.
    Use --repro for verbose output and @example extraction.

    For Atheris native fuzzing, use ./scripts/fuzz_atheris.sh instead.

NOTE:
    --workers defaults to 1. HypoFuzz has a teardown race (hypofuzz.py
    FuzzWorkerHub.start) where worker processes are not terminated before
    the multiprocessing Manager exits, causing workers to crash on their next
    proxy access (BrokenPipeError on Python 3.13; FileNotFoundError on
    Python 3.14). In continuous --deep mode (no --time), this is handled
    automatically: the script detects the race and restarts HypoFuzz (up to
    20 times). The Hypothesis database is preserved across restarts so
    exploration continues seamlessly. With --time N, restarts are not
    attempted (session is bounded). The race occurs on any Python version.

    All modes emit periodic [HEARTBEAT] lines to stderr (T+5s first beat,
    then every 30s). Each line shows elapsed time, CPU%, memory, log size,
    and the last log line — letting agents distinguish working from hung.
    Suppress with --no-heartbeat or set FUZZ_HEARTBEAT_INTERVAL_SEC=0.
HELPEOF
}

# Global state modifications
FORCE=false

# Strict Argument Parser
while [[ $# -gt 0 ]]; do
    case "$1" in
        --deep|--list|--clean|--repro|--preflight)
            if [[ "$MODE" != "check" && "$MODE" != "${1#--}" ]]; then
                log_err "Conflicting modes selected: $MODE vs ${1#--}"
                exit 1
            fi
            MODE="${1#--}"
            if [[ "$MODE" == "repro" && -z "${2:-}" ]]; then
                log_err "Missing test argument for --repro"
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
        --metrics) METRICS=true; shift ;;
        --no-heartbeat) HEARTBEAT_ENABLED=false; shift ;;
        --workers) WORKERS="$2"; shift 2 ;;
        --time) TIME_LIMIT="$2"; shift 2 ;;
        --target) TARGET="$2"; shift 2 ;;
        --force|-f) FORCE=true; shift ;;
        --help|-h) show_help; exit 0 ;;
        *)
            echo "Unknown option: $1"
            echo "Run './scripts/fuzz_hypofuzz.sh --help' for usage."
            exit 2
            ;;
    esac
done

# [SECTION: SIGNAL_HANDLING]
# Two-handler design: _on_exit fires only on EXIT (prints [EXIT-CODE] once);
# _on_signal fires on INT/TERM (kills managed PIDs, sets flag, returns without
# printing or exiting so bash resumes execution naturally).
PID_LIST=()
_SIGNAL_RECEIVED=false

_on_exit() {
    local exit_code=$?
    local pid
    for pid in "${PID_LIST[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    [[ ${#PID_LIST[@]} -gt 0 ]] && wait "${PID_LIST[@]}" 2>/dev/null || true
    echo "[EXIT-CODE] $exit_code" >&2
}

_on_signal() {
    _SIGNAL_RECEIVED=true
    local pid
    for pid in "${PID_LIST[@]}"; do
        kill -TERM "$pid" 2>/dev/null || true
    done
    PID_LIST=()
}

trap '_on_exit' EXIT
trap '_on_signal' INT TERM

# =============================================================================
# Subroutines
# =============================================================================

# [SECTION: DIAGNOSTICS]
run_diagnostics() {
    log_group_start "Pre-Flight Diagnostics"

    echo "[ INFO ] Script               : $SCRIPT_NAME v$SCRIPT_VERSION"

    local python_version
    python_version=$(python --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)
    echo "[  OK  ] Python               : $python_version"

    if python -c "import hypothesis" &>/dev/null; then
        local hypo_version
        hypo_version=$(python -c "import hypothesis; print(hypothesis.__version__)")
        echo "[  OK  ] Hypothesis           : $hypo_version"
    else
        echo "[ FAIL ] Hypothesis           : MISSING"
        log_err "Hypothesis not installed. Run 'uv sync' to install dependencies."
        exit 1
    fi

    log_pass "System is ready."
    log_group_end
}

# =============================================================================
# Preflight Infrastructure Audit
# =============================================================================

run_preflight() {
    log_group_start "Preflight Infrastructure Audit"

    # Capture the Python audit exit code separately: the heredoc subprocess exits 0 or 1
    # but 'set +e' (active from main dispatch) prevents it from aborting the function.
    # Without explicit capture, log_group_end's exit 0 overwrites the audit result.
    local audit_exit=0

    # AST-based per-test event checking via Python
    python << PREFLIGHT_EOF || audit_exit=$?
import ast
import re
import sys
from pathlib import Path
from collections import defaultdict

tests_dir = Path("$PROJECT_ROOT/tests")
strategies_dir = tests_dir / "strategies"

# ---- Pass 1: File-level metrics ----
given_count = 0
given_by_file = defaultdict(int)
event_count = 0
event_by_file = defaultdict(int)

for py_file in tests_dir.rglob("*.py"):
    try:
        content = py_file.read_text()
        g_matches = len(re.findall(r'@given\(', content))
        if g_matches > 0:
            given_count += g_matches
            given_by_file[py_file.relative_to(tests_dir)] = g_matches
        e_matches = len(re.findall(r'(?<![a-zA-Z_])event\(', content))
        if e_matches > 0:
            event_count += e_matches
            event_by_file[py_file.relative_to(tests_dir)] = e_matches
    except Exception:
        pass

# ---- Pass 2: Fuzz module identification ----
fuzz_modules = []
fuzz_modules_without_events = []
for py_file in tests_dir.rglob("*.py"):
    try:
        # Skip infrastructure files (conftest contains marker registration, not tests)
        if py_file.name == "conftest.py":
            continue
        content = py_file.read_text()
        if "pytest.mark.fuzz" in content or "pytestmark = pytest.mark.fuzz" in content:
            rel_path = py_file.relative_to(tests_dir)
            fuzz_modules.append(str(rel_path))
            # Only flag as gap if the module has @given tests but no events
            has_given = given_by_file.get(rel_path, 0) > 0
            has_events = rel_path in event_by_file
            if has_given and not has_events:
                fuzz_modules_without_events.append(str(rel_path))
    except Exception:
        pass

# ---- Pass 3: Per-test event checking (AST-based, ALL @given tests) ----
# Every @given test discovered by HypoFuzz must emit event() for semantic guidance.
tests_without_events = []
for py_file in tests_dir.rglob("*.py"):
    try:
        content = py_file.read_text()
        if "@given" not in content:
            continue
        tree = ast.parse(content, filename=str(py_file))
        rel_path = str(py_file.relative_to(tests_dir))

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # Check for @given decorator (direct or via attribute)
            has_given = any(
                isinstance(dec, ast.Call)
                and (
                    (isinstance(dec.func, ast.Name) and dec.func.id == "given")
                    or (
                        isinstance(dec.func, ast.Attribute)
                        and dec.func.attr == "given"
                    )
                )
                for dec in node.decorator_list
            )
            if not has_given:
                continue
            # Check if function body contains event() call
            has_event = any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "event"
                for child in ast.walk(node)
            )
            if not has_event:
                tests_without_events.append(f"{rel_path}::{node.name}")
    except Exception:
        pass

# ---- Pass 4: Strategy analysis ----
# __init__.py is a pure re-export aggregator; event() calls belong in domain modules.
_STRATEGY_REEXPORT_FILES = {"__init__.py"}
strategy_coverage = {}
strategy_gaps = []
has_strategies_dir = strategies_dir.exists()

if has_strategies_dir:
    for strat_file in strategies_dir.glob("*.py"):
        try:
            if strat_file.name in _STRATEGY_REEXPORT_FILES:
                continue
            content = strat_file.read_text()
            events = len(re.findall(r'(?<![a-zA-Z_])event\(', content))
            strategy_coverage[strat_file.name] = events
            if events == 0:
                strategy_gaps.append(strat_file.name)
        except Exception:
            pass

# ---- Report ----
print(f"Test Files:          {len(list(tests_dir.rglob('*.py')))}")
print(f"@given Tests:        {given_count}")
print(f"event() Calls:       {event_count}")
print(f"Fuzz Modules:        {len(fuzz_modules)}")
print()

if has_strategies_dir:
    if strategy_coverage:
        print("Strategy Coverage:")
        for name, count in sorted(strategy_coverage.items()):
            status = "[  OK  ]" if count > 0 else "[ FAIL ]"
            print(f"  {status} {name:<20} {count} events")
        print()

    if strategy_gaps:
        print("[FAIL] Strategy files without event() calls (HypoFuzz guidance gap):")
        for name in sorted(strategy_gaps):
            print(f"  [ FAIL ] {name}")
        print()
else:
    print("[ INFO ] No tests/strategies directory found (skipped strategy audit)")
    print()

if fuzz_modules_without_events:
    print("[WARN] Fuzz Modules WITHOUT Events (File-Level Gap):")
    for mod in sorted(fuzz_modules_without_events):
        given = given_by_file.get(Path(mod), 0)
        print(f"  [ WARN ] {mod} ({given} @given tests, 0 events)")
    print()
else:
    print("[  OK  ] All fuzz modules have events (file-level)")
    print()

if tests_without_events:
    print("[FAIL] @given Tests WITHOUT event() Calls (ALL test files):")
    for test_id in sorted(tests_without_events):
        print(f"  [ FAIL ] {test_id}")
    print()
else:
    print("[  OK  ] All @given tests emit events (per-test, all files)")
    print()

# Summary
gaps = len(fuzz_modules_without_events) + len(tests_without_events) + len(strategy_gaps)
if gaps > 0:
    print(f"[FAIL] {gaps} gap(s) detected. Add hypothesis.event() calls for semantic guidance.")
    sys.exit(1)
else:
    print("[  OK  ] Infrastructure audit passed. Run --deep for coverage-guided fuzzing.")
PREFLIGHT_EOF

    log_group_end
    return "$audit_exit"
}

# =============================================================================
# Property Test Runner (check mode)
# =============================================================================

run_check() {
    run_diagnostics
    log_group_start "Property Tests"

    # Set profile based on verbose flag
    if [[ "$VERBOSE" == "true" ]]; then
        export HYPOTHESIS_PROFILE="verbose"
    fi

    # Determine target
    local test_target="${TARGET:-tests/}"

    # Verify target exists
    if [[ ! -e "$test_target" ]]; then
        log_err "Target not found: $test_target"
        log_group_end
        return 1
    fi

    log_info "Target: $test_target"
    if [[ "$VERBOSE" == "true" ]]; then
        log_info "Profile: verbose"
    else
        log_info "Profile: default (dev)"
    fi

    # Log Capture
    local temp_log
    temp_log=$(mktemp)

    local cmd=(uv run pytest "$test_target" -v --tb=short)

    local exit_code=0
    set +e
    _run_with_heartbeat "$temp_log" false -- "${cmd[@]}"
    exit_code=$?
    set -e

    # Log Parsing via Python
    python << PYEOF
import json, re
from datetime import datetime, timezone
from pathlib import Path

log_path = Path("$temp_log")
exit_code = $exit_code

try:
    log_content = log_path.read_text() if log_path.exists() else ""
except Exception:
    log_content = ""

# Parse metrics from the definitive summary line
# Example: "=== 1 failed, 123 passed, 2 skipped in 1.12s ==="
summary_match = re.search(r'=+ (.*?) =+', log_content)
summary_text = summary_match.group(1) if summary_match else ""

passed_match = re.search(r'(\d+) passed', summary_text)
failed_match = re.search(r'(\d+) failed', summary_text)
skipped_match = re.search(r'(\d+) skipped', summary_text)

tests_passed = int(passed_match.group(1)) if passed_match else 0
tests_failed = int(failed_match.group(1)) if failed_match else 0
tests_skipped = int(skipped_match.group(1)) if skipped_match else 0

hypo_count = log_content.count('Falsifying example')

# Extract individual test failures
failures = []
failed_test_pattern = r'FAILED (tests/.+?)(?: - |$)'
failed_tests = sorted(list(set(re.findall(failed_test_pattern, log_content))))

for test_path in failed_tests:
    failure_entry = {"test": test_path}
    test_section_start = log_content.find(test_path)
    if test_section_start != -1:
        test_section = log_content[test_section_start:test_section_start + 2000]
        error_match = re.search(r'E\s+(\w+Error|\w+Exception):', test_section)
        if error_match:
            failure_entry["error_type"] = error_match.group(1)
    if 'Falsifying example' in log_content:
        test_func = test_path.split("::")[-1] if "::" in test_path else ""
        example_pattern = rf'Falsifying example:\s*{re.escape(test_func)}\(([^\)]+)\)'
        example_match = re.search(example_pattern, log_content, re.DOTALL)
        if example_match:
            failure_entry["example"] = example_match.group(1).strip()[:500]
    failures.append(failure_entry)

# Legacy field
fail_ex = ""
if 'Falsifying example' in log_content:
    try:
        fail_ex = log_content.split('Falsifying example')[1].split('\n')[0][:200].strip()
    except IndexError:
        pass

# Status determination
if exit_code == 0:
    status = 'pass'
elif exit_code in (130, 2):
    status = 'stopped'
elif tests_failed > 0 or hypo_count > 0:
    status = 'finding'
else:
    status = 'error'

report = {
    'script': '$SCRIPT_NAME',
    'script_version': '$SCRIPT_VERSION',
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
    if [[ $exit_code -eq 0 ]]; then
        log_pass "All property tests passed."
    elif [[ $exit_code -eq 130 || $exit_code -eq 2 ]]; then
        log_info "Run interrupted by user."
    elif [[ $exit_code -eq 1 ]]; then
        log_fail "Failures detected. See JSON summary above."
        if [[ "$VERBOSE" == "false" ]]; then
            log_warn "Failure output:"
            if [[ -s "$temp_log" ]]; then
                grep -A 20 "Falsifying example" "$temp_log" || head -n 20 "$temp_log"
            fi
        fi
    else
        log_err "Test execution failed (code $exit_code)."
    fi

    rm -f "$temp_log"
    log_group_end
    return "$exit_code"
}

# =============================================================================
# Continuous HypoFuzz (deep mode)
# =============================================================================

run_deep() {
    run_diagnostics

    # Determine mode title: --metrics uses pytest (single-pass), else HypoFuzz (continuous)
    if [[ "$METRICS" == "true" ]]; then
        log_group_start "Deep Fuzzing (pytest with metrics)"
    else
        log_group_start "Continuous HypoFuzz"
    fi

    # Activate hypofuzz profile: deadline=None, suppress health checks
    export HYPOTHESIS_PROFILE="hypofuzz"

    # Log file for this session (append to preserve history)
    local log_file="$PROJECT_ROOT/.hypothesis/hypofuzz.log"
    mkdir -p "$PROJECT_ROOT/.hypothesis"

    # When --metrics is enabled, use pytest instead of HypoFuzz.
    # HypoFuzz uses multiprocessing; STRATEGY_METRICS is only exported here,
    # so each worker does not independently print zero-event summaries.
    if [[ "$METRICS" == "true" ]]; then
        export STRATEGY_METRICS="1"
        export STRATEGY_METRICS_DETAILED="1"
        export STRATEGY_METRICS_LIVE="1"
        export STRATEGY_METRICS_INTERVAL="10"
        log_info "Metrics: Per-strategy breakdown enabled (10s interval)"
        log_info "Metrics: Using pytest (HypoFuzz multiprocessing incompatible with metrics)"
        log_info "Profile: hypofuzz (deadline=None)"

        # Session header
        {
            echo ""
            echo "================================================================================"
            echo "Metrics Session (pytest -m fuzz): $(date '+%Y-%m-%d %H:%M:%S')"
            echo "Profile: hypofuzz"
            echo "================================================================================"
        } >> "$log_file"

        local exit_code=0
        set +e
        _run_with_heartbeat "$log_file" true -- uv run pytest tests/ -m fuzz -v --tb=short
        exit_code=$?
        set -e

        log_group_end
        return "$exit_code"
    fi

    if [[ -n "$TIME_LIMIT" ]]; then
        log_info "Time Limit: ${TIME_LIMIT}s"
    else
        log_info "Time Limit: Until Ctrl+C"
    fi
    log_info "Workers: $WORKERS"
    log_info "Profile: hypofuzz (deadline=None)"

    # session_log_start: byte offset at the start of this --deep invocation.
    # Used to count failures across ALL restarts in the session without
    # double-counting evidence from prior sessions in the append-only log.
    local session_log_start=0
    [[ -f "$log_file" ]] && session_log_start=$(wc -c < "$log_file" | tr -d ' ')

    local exit_code=0
    local teardown_race_detected=false
    local restart_count=0
    local max_teardown_restarts=20

    # Teardown race detection (HypoFuzz bug — hypofuzz.py FuzzWorkerHub.start):
    # When HypoFuzz completes a full exploration pass, FuzzWorkerHub.start()
    # breaks out of its poll loop and exits the `with Manager()` block without
    # first terminating worker processes. Manager.__exit__() closes the IPC
    # socket; workers crash on their next proxy access. This is a HypoFuzz bug,
    # not a test failure. Failure mode differs by Python version:
    #   Python 3.13: BrokenPipeError (socket open at connect, write fails)
    #   Python 3.14: FileNotFoundError (Manager deletes socket file before
    #                worker _incref() reconnect; managers.py:863)
    #
    # Resolution: auto-restart. The Hypothesis database is preserved between
    # restarts so exploration continues exactly where it left off. For --time N,
    # single run only (user wants bounded total time; restarts would exceed it).
    # For continuous --deep (no --time): loop until Ctrl+C, restarting on race.
    #
    # run_log_start is captured before each individual HypoFuzz invocation so
    # teardown detection is scoped to that run's log window only — avoids
    # false positives from prior runs' BrokenPipeError evidence.

    if [[ -n "$TIME_LIMIT" ]]; then
        # Time-limited single run: no auto-restart (user wants bounded session).
        {
            echo ""
            echo "================================================================================"
            echo "HypoFuzz Session: $(date '+%Y-%m-%d %H:%M:%S')"
            echo "Script: $SCRIPT_NAME v$SCRIPT_VERSION"
            echo "Workers: $WORKERS"
            echo "Profile: hypofuzz"
            echo "================================================================================"
        } >> "$log_file"

        local run_log_start=0
        [[ -f "$log_file" ]] && run_log_start=$(wc -c < "$log_file" | tr -d ' ')

        set +e
        # timeout(1) sends SIGTERM after TIME_LIMIT seconds; exit 124 = time limit reached
        _run_with_heartbeat "$log_file" true -- timeout "$TIME_LIMIT" uv run hypothesis fuzz --no-dashboard -n "$WORKERS" tests/fuzz/
        exit_code=$?
        set -e
        [[ $exit_code -eq 124 ]] && exit_code=0  # time limit reached is a clean stop

        if [[ "$_SIGNAL_RECEIVED" == "true" && $exit_code -ne 0 ]]; then exit_code=130; fi

        # Teardown race check (time-limited: report but don't restart).
        # Detection: worker subprocess crash (_start_worker in traceback) that
        # went through the multiprocessing.managers proxy layer (managers.py in
        # traceback). The exception class varies by timing and Python version:
        #   BrokenPipeError  — write to closed Manager socket (3.13 typical)
        #   FileNotFoundError — socket file deleted before connect (3.14)
        #   EOFError          — Manager closed auth challenge mid-recv (3.14)
        # Matching on exception class is fragile; _start_worker + managers.py
        # is the invariant that covers all variants.
        local _log_window
        _log_window=$(tail -c "+$((run_log_start + 1))" "$log_file" 2>/dev/null || true)
        if [[ $exit_code -ne 0 && $exit_code -ne 130 && $exit_code -ne 120 ]] \
            && [[ -f "$log_file" ]] \
            && echo "$_log_window" | grep -qF "_start_worker" 2>/dev/null \
            && echo "$_log_window" | grep -qF "managers.py" 2>/dev/null; then
            log_warn "Worker teardown race detected (HypoFuzz bug, exit $exit_code)."
            log_warn "Worker crashed on Manager proxy access after shutdown — no test failures."
            log_warn "Re-run ./scripts/fuzz_hypofuzz.sh --deep to continue (database is preserved)."
            teardown_race_detected=true
            exit_code=0
        fi
    else
        # Continuous mode: auto-restart on teardown race until Ctrl+C.
        while true; do
            local run_log_start=0
            [[ -f "$log_file" ]] && run_log_start=$(wc -c < "$log_file" | tr -d ' ')

            {
                echo ""
                echo "================================================================================"
                if [[ $restart_count -eq 0 ]]; then
                    echo "HypoFuzz Session: $(date '+%Y-%m-%d %H:%M:%S')"
                else
                    echo "HypoFuzz Restart #${restart_count}: $(date '+%Y-%m-%d %H:%M:%S')"
                fi
                echo "Script: $SCRIPT_NAME v$SCRIPT_VERSION"
                echo "Workers: $WORKERS"
                echo "Profile: hypofuzz"
                echo "================================================================================"
            } >> "$log_file"

            set +e
            _run_with_heartbeat "$log_file" true -- uv run hypothesis fuzz --no-dashboard -n "$WORKERS" tests/fuzz/
            exit_code=$?
            set -e

            if [[ "$_SIGNAL_RECEIVED" == "true" ]]; then
                [[ $exit_code -ne 0 ]] && exit_code=130
                break
            fi

            [[ $exit_code -eq 0 || $exit_code -eq 120 ]] && break

            # Check teardown race scoped to THIS run's log window.
            # Invariant: worker subprocess crash (_start_worker in traceback)
            # via the multiprocessing.managers proxy (managers.py in traceback).
            # Exception class varies by timing: BrokenPipeError (3.13 typical),
            # FileNotFoundError (3.14, socket deleted before connect), EOFError
            # (3.14, Manager closes auth challenge mid-recv). Matching on
            # _start_worker + managers.py covers all variants.
            local _log_window
            _log_window=$(tail -c "+$((run_log_start + 1))" "$log_file" 2>/dev/null || true)
            if [[ $exit_code -ne 130 ]] \
                && [[ -f "$log_file" ]] \
                && echo "$_log_window" | grep -qF "_start_worker" 2>/dev/null \
                && echo "$_log_window" | grep -qF "managers.py" 2>/dev/null; then

                teardown_race_detected=true
                (( restart_count++ )) || true

                if [[ $restart_count -gt $max_teardown_restarts ]]; then
                    log_warn "Teardown race repeated $restart_count times — giving up (max $max_teardown_restarts)."
                    exit_code=1
                    break
                fi

                log_info "Teardown race (${restart_count}/${max_teardown_restarts}) — restarting automatically (database preserved)."
                sleep 1
                continue
            fi

            # Non-race error exit — don't restart
            break
        done
    fi

    # Count failures across ALL runs in this session (from session_log_start)
    local failure_count=0
    if [[ -f "$log_file" ]]; then
        failure_count=$(tail -c "+$((session_log_start + 1))" "$log_file" | grep -c "Falsifying example" 2>/dev/null) || failure_count=0
    fi

    if [[ $exit_code -eq 0 || $exit_code -eq 130 || $exit_code -eq 120 ]]; then
        # 0 = Done, 130 = SIGINT (Ctrl+C), 120 = HypoFuzz Interrupted
        log_pass "Fuzzing session ended."

        if [[ "$failure_count" -gt 0 ]]; then
            log_warn "$failure_count falsifying example(s) found in this session."
            echo "  View log: cat $log_file"
            echo "  List failures: ./scripts/fuzz_hypofuzz.sh --list"
        fi

        # Event diversity summary
        log_group_start "Event Infrastructure"
        python << EVENTEOF
import re
from pathlib import Path

tests_dir = Path("$PROJECT_ROOT/tests")

event_count = 0
for py_file in tests_dir.rglob("*.py"):
    try:
        content = py_file.read_text()
        event_count += len(re.findall(r'(?<![a-zA-Z_])event\(', content))
    except Exception:
        pass

print("  HypoFuzz captures hypothesis.event() internally for coverage guidance.")
print("  Events are not echoed to stdout but guide path selection.")
print()
print(f"  Infrastructure: {event_count} event() calls in test suite")
print()
print("  For detailed infrastructure audit:")
print("    ./scripts/fuzz_hypofuzz.sh --preflight")
EVENTEOF
        log_group_end

        # JSON summary
        # Status semantics:
        #   "pass"          — clean stop: Ctrl+C (130), time limit (0), or natural end (0)
        #   "teardown_race" — final exit was HypoFuzz teardown race after max
        #                     auto-restarts exhausted; teardown_restarts shows how many
        #                     transparent auto-restarts occurred before giving up
        #   "interrupted"   — HypoFuzz internal interrupt (exit 120)
        python << PYEOF
import json, re
from datetime import datetime, timezone
from pathlib import Path

log_path = Path("$log_file")
exit_code = $exit_code
failure_count = $failure_count
teardown_race = "${teardown_race_detected}" == "true"
restart_count = $restart_count

try:
    log_content = log_path.read_text() if log_path.exists() else ""
except Exception:
    log_content = ""

failures = []
if failure_count > 0:
    example_pattern = r'Falsifying example:\s*(\w+)\(([^)]+)\)'
    for match in re.finditer(example_pattern, log_content):
        test_name = match.group(1)
        example_args = match.group(2).strip()[:500]
        failures.append({"test": test_name, "example": example_args})

# teardown_race in status only when the FINAL exit was a race (max restarts
# exhausted). Transparent restarts show up in teardown_restarts only.
if teardown_race and exit_code != 0:
    status = "teardown_race"
elif exit_code == 120:
    status = "interrupted"
else:
    status = "pass"

report = {
    "script": "$SCRIPT_NAME",
    "script_version": "$SCRIPT_VERSION",
    "mode": "deep",
    "status": status,
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "failures_count": failure_count,
    "failures": failures[:50],
    "exit_code": exit_code,
    "teardown_restarts": restart_count,
    "log_file": "$log_file"
}
print("[SUMMARY-JSON-BEGIN]")
print(json.dumps(report, indent=2))
print("[SUMMARY-JSON-END]")
PYEOF
    else
        log_err "HypoFuzz exited with error code $exit_code."

        # Check for common macOS issue
        if grep -q "AF_UNIX path too long" "$log_file"; then
            log_warn "AF_UNIX path too long detected. TMPDIR is set to $TMPDIR."
        fi

        python << PYEOF
import json
from datetime import datetime, timezone

report = {
    "script": "$SCRIPT_NAME",
    "script_version": "$SCRIPT_VERSION",
    "mode": "deep",
    "status": "error",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "failures_count": $failure_count,
    "exit_code": $exit_code,
    "log_file": "$log_file"
}
print("[SUMMARY-JSON-BEGIN]")
print(json.dumps(report, indent=2))
print("[SUMMARY-JSON-END]")
PYEOF
        log_group_end
        return "$exit_code"
    fi

    log_group_end
    return "$exit_code"
}

# =============================================================================
# List Failures
# =============================================================================

run_list() {
    local examples_dir="$PROJECT_ROOT/.hypothesis/examples"
    local fuzz_log="$PROJECT_ROOT/.hypothesis/hypofuzz.log"

    log_group_start "Hypothesis Failure Reproduction Info"

    log_info "How Hypothesis failures work:"
    echo "  1. When a property test fails, Hypothesis shrinks to a minimal example"
    echo "  2. The shrunk example is stored in .hypothesis/examples/ (SHA-384 hashed)"
    echo "  3. On re-run, Hypothesis AUTOMATICALLY replays the stored failure"
    echo "  4. Simply running 'uv run pytest tests/' will reproduce all known failures"
    echo ""

    # Check if examples database exists
    if [[ -d "$examples_dir" ]]; then
        local count
        count=$(find "$examples_dir" -type f 2>/dev/null | wc -l | tr -d ' ')
        log_pass ".hypothesis/examples/ exists with $count entries"
    else
        log_warn "No .hypothesis/examples/ directory found."
        echo "     Run some Hypothesis tests first to populate the database."
    fi
    echo ""

    # Check for HypoFuzz log
    if [[ -f "$fuzz_log" ]]; then
        log_info "Recent HypoFuzz session log: $fuzz_log"
        local failure_count=0
        failure_count=$(grep -c "Falsifying example" "$fuzz_log" 2>/dev/null) || failure_count=0
        if [[ "$failure_count" -gt 0 ]]; then
            log_warn "Found $failure_count falsifying example(s) in log."
            echo ""
            echo "Recent failures:"
            grep -B2 "Falsifying example" "$fuzz_log" | tail -20
        else
            echo "  No failures recorded in latest session."
        fi
    else
        log_info "HypoFuzz log: Not found (run --deep to create)"
    fi
    echo ""

    echo "To reproduce a specific failing test:"
    echo "  ./scripts/fuzz_hypofuzz.sh --repro test_module::test_function"
    echo ""
    echo "To reproduce all failures:"
    echo "  uv run pytest tests/ -x -v"
    echo ""
    echo "To extract @example decorator:"
    echo "  uv run python scripts/fuzz_hypofuzz_repro.py --example test_module::test_function"

    log_group_end
}

# =============================================================================
# Clean Hypothesis Database
# =============================================================================

run_clean() {
    local hypothesis_dir="$PROJECT_ROOT/.hypothesis"
    local fuzz_log="$hypothesis_dir/hypofuzz.log"

    if [[ ! -d "$hypothesis_dir" ]]; then
        log_info "No .hypothesis/ directory found. Nothing to clean."
        return 0
    fi

    local example_count
    example_count=$(find "$hypothesis_dir/examples" -type f 2>/dev/null | wc -l | tr -d ' ')

    log_group_start "Hypothesis Database Cleanup"
    echo "Directory: $hypothesis_dir"
    echo "Examples:  $example_count cached entries"
    if [[ -f "$fuzz_log" ]]; then
        echo "Log:       $(wc -l < "$fuzz_log" | tr -d ' ') lines"
    fi
    echo ""
    if [[ "$FORCE" == "true" ]]; then
        rm -rf "$hypothesis_dir"
        log_pass "Removed .hypothesis/ directory (forced)."
    else
        # Prevent hanging in non-interactive CI environments
        if [[ ! -t 0 ]]; then
            log_err "Non-interactive environment detected. You must use --force to clean the database."
            exit 1
        fi

        log_warn "Removing .hypothesis/ will:"
        echo "  - Delete all cached examples (regression database)"
        echo "  - Delete any shrunk failure examples"
        echo "  - Require tests to rediscover edge cases"
        echo ""
        read -r -p "Remove .hypothesis/ directory? (y/N): " response
        case "$response" in
            [yY][eE][sS]|[yY])
                rm -rf "$hypothesis_dir"
                log_pass "Removed .hypothesis/ directory."
                ;;
            *)
                log_info "Cancelled."
                ;;
        esac
    fi
    log_group_end
}

# =============================================================================
# Reproduce Failures
# =============================================================================

run_repro() {
    if [[ -z "$REPRO_TEST" ]]; then
        log_err "Missing test argument for --repro"
        echo "Usage: ./scripts/fuzz_hypofuzz.sh --repro <test_module::test_function>"
        echo ""
        echo "Examples:"
        echo "  ./scripts/fuzz_hypofuzz.sh --repro tests/fuzz/test_syntax_parser_property.py::test_roundtrip"
        echo "  ./scripts/fuzz_hypofuzz.sh --repro tests/fuzz/test_syntax_parser_property.py"
        return 1
    fi

    log_group_start "Reproduce Hypothesis Failure"
    log_info "Test: $REPRO_TEST"

    local exit_code=0
    set +e
    uv run python scripts/fuzz_hypofuzz_repro.py --verbose --example "$REPRO_TEST"
    exit_code=$?
    set -e

    if [[ $exit_code -eq 0 ]]; then
        log_pass "Test passed - no failure to reproduce."
        echo "If you expected a failure, the bug may have been fixed or the"
        echo ".hypothesis/examples/ database may need to be cleared."
    fi

    log_group_end
    return "$exit_code"
}

# =============================================================================
# Main Dispatch
# =============================================================================

set +e
case "$MODE" in
    check)     run_check ;;
    deep)      run_deep ;;
    list)      run_list ;;
    clean)     run_clean ;;
    repro)     run_repro ;;
    preflight) run_preflight ;;
    *)         log_err "Invalid mode"; exit 1 ;;
esac
exit $?
