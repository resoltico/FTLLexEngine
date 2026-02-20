#!/usr/bin/env bash
# ==============================================================================
# fuzz_hypofuzz.sh -- HypoFuzz & Property Testing Interface
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
set -o errexit
set -o nounset
set -o pipefail
if [[ "${BASH_VERSINFO[0]}" -ge 5 ]]; then
    shopt -s inherit_errexit 2>/dev/null || true
fi

# [SECTION: ENVIRONMENT_ISOLATION]
PY_VERSION="${PY_VERSION:-3.13}"
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
WORKERS=4
TIME_LIMIT=""
TARGET=""
REPRO_TEST=""

# Colors (respects NO_COLOR standard and non-terminal detection)
if [[ "${NO_COLOR:-}" == "1" ]]; then
    RED=""; GREEN=""; YELLOW=""; BLUE=""; CYAN=""; BOLD=""; RESET=""
elif [[ ! -t 1 ]]; then
    RED=""; GREEN=""; YELLOW=""; BLUE=""; CYAN=""; BOLD=""; RESET=""
else
    RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"; BLUE="\033[34m"; CYAN="\033[36m"; BOLD="\033[1m"; RESET="\033[0m"
fi

# Logging (consistent with lint.sh and test.sh)
log_group_start() { [[ "$IS_GHA" == "true" ]] && echo "::group::$1"; echo -e "\n${BOLD}${CYAN}=== $1 ===${RESET}"; }
log_group_end()   { [[ "$IS_GHA" == "true" ]] && echo "::endgroup::"; return 0; }
log_info() { echo -e "${BLUE}[INFO]${RESET} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${RESET} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${RESET} $1"; }
log_fail() { echo -e "${RED}[FAIL]${RESET} $1"; }
log_err()  { echo -e "${RED}[ERROR]${RESET} $1" >&2; }

show_help() {
    cat << 'HELPEOF'
HypoFuzz & Property Testing Interface for FTLLexEngine

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
    --workers N     Number of parallel workers (default: 4)
    --time N        Time limit in seconds (for --deep)
    --target FILE   Specific test file to run (check mode only)

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

    --deep --metrics uses pytest (single-pass) instead of HypoFuzz
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

NOTE:
    Hypothesis automatically stores and replays failing examples from
    .hypothesis/examples/. Simply re-running pytest will reproduce failures.
    Use --repro for verbose output and @example extraction.

    For Atheris native fuzzing, use ./scripts/fuzz_atheris.sh instead.
HELPEOF
}

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
    local exit_code=$?
    if [[ ${#PID_LIST[@]} -gt 0 ]]; then
        for pid in "${PID_LIST[@]}"; do
            kill -TERM "$pid" 2>/dev/null || true
        done
        wait
    fi
    echo "[EXIT-CODE] $exit_code" >&2
}
trap cleanup EXIT INT TERM

# =============================================================================
# Subroutines
# =============================================================================

# [SECTION: DIAGNOSTICS]
run_diagnostics() {
    log_group_start "Pre-Flight Diagnostics"

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

    # AST-based per-test event checking via Python
    python << PREFLIGHT_EOF
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

# ---- Pass 3: Per-test event checking (AST-based) ----
tests_without_events = []
for py_file in tests_dir.rglob("*.py"):
    try:
        content = py_file.read_text()
        if "pytest.mark.fuzz" not in content:
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
strategy_coverage = {}
if strategies_dir.exists():
    for strat_file in strategies_dir.glob("*.py"):
        try:
            content = strat_file.read_text()
            events = len(re.findall(r'(?<![a-zA-Z_])event\(', content))
            strategy_coverage[strat_file.name] = events
        except Exception:
            pass

# ---- Report ----
print(f"Test Files:          {len(list(tests_dir.rglob('*.py')))}")
print(f"@given Tests:        {given_count}")
print(f"event() Calls:       {event_count}")
print(f"Fuzz Modules:        {len(fuzz_modules)}")
print()

if strategy_coverage:
    print("Strategy Coverage:")
    for name, count in sorted(strategy_coverage.items()):
        status = "[  OK  ]" if count > 0 else "[ WARN ]"
        print(f"  {status} {name:<20} {count} events")
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
    print("[WARN] @given Tests in Fuzz Modules WITHOUT event() Calls:")
    for test_id in sorted(tests_without_events):
        print(f"  [ WARN ] {test_id}")
    print()
else:
    print("[  OK  ] All @given tests in fuzz modules emit events (per-test)")
    print()

# Non-fuzz files with @given but no events (informational)
no_event_files = [(f, c) for f, c in given_by_file.items() if f not in event_by_file]
top_files = sorted(no_event_files, key=lambda x: x[1], reverse=True)
if top_files:
    print("Non-Fuzz Files with @given but no events:")
    for f, count in top_files:
        print(f"  [ INFO ] {f}: {count} @given tests, 0 events")
    print()

# Summary
gaps = len(fuzz_modules_without_events) + len(tests_without_events)
if gaps > 0:
    print(f"[WARN] {gaps} gap(s) detected. Add hypothesis.event() calls for semantic guidance.")
    sys.exit(1)
else:
    print("[  OK  ] Infrastructure audit passed. Run --deep for coverage-guided fuzzing.")
PREFLIGHT_EOF

    log_group_end
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
    if [[ "$VERBOSE" == "true" ]]; then
        "${cmd[@]}" 2>&1 | tee "$temp_log"
        exit_code=${PIPESTATUS[0]}
    else
        "${cmd[@]}" > "$temp_log" 2>&1
        exit_code=$?
    fi
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

# Parse metrics
passed_match = re.search(r'(\d+) passed', log_content)
failed_match = re.search(r'(\d+) failed', log_content)
skipped_match = re.search(r'(\d+) skipped', log_content)
hypo_count = log_content.count('Falsifying example')

tests_passed = int(passed_match.group(1)) if passed_match else 0
tests_failed = int(failed_match.group(1)) if failed_match else 0
tests_skipped = int(skipped_match.group(1)) if skipped_match else 0

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

    # Enable strategy metrics collection
    export STRATEGY_METRICS="1"

    # Log file for this session (append to preserve history)
    local log_file="$PROJECT_ROOT/.hypothesis/hypofuzz.log"
    mkdir -p "$PROJECT_ROOT/.hypothesis"

    # When --metrics is enabled, use pytest instead of HypoFuzz
    # HypoFuzz uses multiprocessing where metrics aren't shared across workers
    if [[ "$METRICS" == "true" ]]; then
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
        uv run pytest tests/ -m fuzz -v --tb=short 2>&1 | tee -a "$log_file"
        exit_code=${PIPESTATUS[0]}
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

    # Session header
    {
        echo ""
        echo "================================================================================"
        echo "HypoFuzz Session: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "Workers: $WORKERS"
        echo "Profile: hypofuzz"
        echo "================================================================================"
    } >> "$log_file"

    local exit_code=0
    set +e
    uv run hypothesis fuzz --no-dashboard -n "$WORKERS" tests/ 2>&1 | tee -a "$log_file"
    exit_code=${PIPESTATUS[0]}
    set -e

    # Count failures
    local failure_count=0
    failure_count=$(grep -c "Falsifying example" "$log_file" 2>/dev/null) || failure_count=0

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
        python << PYEOF
import json, re
from datetime import datetime, timezone
from pathlib import Path

log_path = Path("$log_file")
exit_code = $exit_code
failure_count = $failure_count

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

report = {
    "mode": "deep",
    "status": "pass",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "failures_count": failure_count,
    "failures": failures[:50],
    "exit_code": exit_code,
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
    return 0
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
