#!/usr/bin/env bash
# ==============================================================================
# fuzz_hypofuzz.sh -- HypoFuzz & Property Testing Interface
# Version: 1.0.1
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

SCRIPT_VERSION="1.0.1"
SCRIPT_NAME="fuzz_hypofuzz.sh"

set -o errexit
set -o nounset
set -o pipefail
if [[ "${BASH_VERSINFO[0]}" -ge 5 ]]; then
    shopt -s inherit_errexit 2>/dev/null || true
fi

PY_VERSION="${PY_VERSION:-3.13}"
if [[ "${FTLLEXENGINE_DEVCONTAINER:-}" == "1" ]]; then
    TARGET_VENV=".venv-devcontainer-${PY_VERSION}"
else
    TARGET_VENV=".venv-${PY_VERSION}"
fi
if [[ "${FTLLEXENGINE_DEVCONTAINER:-}" == "1" && -z "${UV_LINK_MODE:-}" ]]; then
    export UV_LINK_MODE="copy"
fi

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
        exec uv run --python "$PY_VERSION" "${BASH:-bash}" "$0" "$@"
    fi
else
    unset FUZZ_ALREADY_PIVOTED
fi

export TMPDIR="/tmp"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
IS_GHA="${GITHUB_ACTIONS:-false}"
readonly FUZZ_LIB_DIR="$SCRIPT_DIR/lib/fuzz_hypofuzz"

MODE="check"
VERBOSE=false
METRICS=false
WORKERS=1
TIME_LIMIT=""
TARGET=""
REPRO_TEST=""
HEARTBEAT_ENABLED=true
HEARTBEAT_INTERVAL_SEC="${FUZZ_HEARTBEAT_INTERVAL_SEC:-30}"
FORCE=false

require_fuzz_lib() {
    local path="$1"
    if [[ ! -f "$path" ]]; then
        echo "[ERROR] Missing HypoFuzz helper library: $path" >&2
        exit 1
    fi
}

require_fuzz_lib "$FUZZ_LIB_DIR/common.sh"
require_fuzz_lib "$FUZZ_LIB_DIR/modes_check.sh"
require_fuzz_lib "$FUZZ_LIB_DIR/modes_fuzz.sh"

# shellcheck source=scripts/lib/fuzz_hypofuzz/common.sh
source "$FUZZ_LIB_DIR/common.sh"
# shellcheck source=scripts/lib/fuzz_hypofuzz/modes_check.sh
source "$FUZZ_LIB_DIR/modes_check.sh"
# shellcheck source=scripts/lib/fuzz_hypofuzz/modes_fuzz.sh
source "$FUZZ_LIB_DIR/modes_fuzz.sh"

show_help() {
    local project_name="Project"
    if [[ -f "$PROJECT_ROOT/pyproject.toml" ]]; then
        project_name=$(python -c 'import pathlib, tomllib; pyproject = pathlib.Path(__import__("sys").argv[1]); print(tomllib.loads(pyproject.read_text(encoding="utf-8")).get("project", {}).get("name", "Project").capitalize())' "$PROJECT_ROOT/pyproject.toml" 2>/dev/null || echo "Project")
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
    and the last log line - letting agents distinguish working from hung.
    Suppress with --no-heartbeat or set FUZZ_HEARTBEAT_INTERVAL_SEC=0.
HELPEOF
}

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

PID_LIST=()
_SIGNAL_RECEIVED=false

trap '_on_exit' EXIT
trap '_on_signal' INT TERM

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
