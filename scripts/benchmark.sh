#!/usr/bin/env bash
# ==============================================================================
# benchmark.sh — Universal Performance Benchmark Runner
# ==============================================================================
# COMPATIBILITY: Bash 5.0+
# ARCHITECTURAL INTENT:
#   Project-agnostic benchmark runner that adapts to project structure.
#   Wraps pytest-benchmark with ergonomic CLI flags, baseline management,
#   and structured output for AI agents and CI systems.
#
# AGENT PROTOCOL:
#   - Silence on Success (unless --verbose)
#   - Full Log on Failure
#   - [SUMMARY-JSON-BEGIN] ... [SUMMARY-JSON-END]
#   - [EXIT-CODE] N
#   - [DEBUG-SUGGESTION]
#
# USAGE:
#   ./scripts/benchmark.sh                       # Run benchmarks
#   ./scripts/benchmark.sh --save baseline       # Save baseline
#   ./scripts/benchmark.sh --compare 0001        # Compare vs baseline
#   ./scripts/benchmark.sh --histogram           # Generate histogram
#   ./scripts/benchmark.sh --json FILE           # Export JSON to FILE
#   ./scripts/benchmark.sh --ci                  # CI mode (non-interactive)
#   ./scripts/benchmark.sh --verbose             # Stream output
#   ./scripts/benchmark.sh --help                # Show this help
#
# OUTPUTS:
#   - Benchmark results (min/max/mean/median/stddev)
#   - Statistical analysis (IQR, outliers)
#   - Operations per second (OPS)
#
# DATA CONSUMED:
#   - tests/benchmarks/*.py   (default discovery path)
#   - benchmark/*.py          (fallback discovery path)
#   - .benchmarks/            Saved baseline data (optional)
#
# DATA PRODUCED:
#   - .benchmarks/            Saved benchmark results (--save)
#   - <FILE>                  JSON export (--json FILE)
#   - benchmark_histogram.svg Histogram SVG (--histogram)
#
# REGRESSION THRESHOLD:
#   20% slowdown triggers investigation
#
# ECOSYSTEM:
#   1. lint.sh      — Code quality
#   2. test.sh      — Correctness
#   3. benchmark.sh — Performance (this script)
#
# CI/CD:
#   GitHub Actions can run benchmarks with --ci flag for regression detection.
#   Use --json for CI artifact storage and --compare for regression gating.
#
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
set -o errexit
set -o nounset
set -o pipefail
shopt -s inherit_errexit

# [SECTION: ENVIRONMENT_ISOLATION]
PY_VERSION="${PY_VERSION:-3.14}"
TARGET_VENV=".venv-${PY_VERSION}"

if [[ "${UV_PROJECT_ENVIRONMENT:-}" != "$TARGET_VENV" ]]; then
    if [[ "${BENCHMARK_ALREADY_PIVOTED:-}" == "1" ]]; then
        echo "Error: Recursive pivot detected. Check your environment configuration." >&2
        exit 1
    fi
    if [[ -f "uv.lock" || -f "pyproject.toml" ]]; then
        echo -e "\033[34m[INFO]\033[0m Pivoting to isolated environment: ${TARGET_VENV}"
        export UV_PROJECT_ENVIRONMENT="$TARGET_VENV"
        export BENCHMARK_ALREADY_PIVOTED=1
        unset VIRTUAL_ENV
        exec uv run --python "$PY_VERSION" "${BASH:-bash}" "$0" "$@"
    fi
else
    unset BENCHMARK_ALREADY_PIVOTED
fi

# [SECTION: SETUP]
CI_MODE=false
VERBOSE=false
SAVE_BASELINE=""
COMPARE_BASELINE=""
GENERATE_HISTOGRAM=false
EXPORT_JSON=""
IS_GHA="${GITHUB_ACTIONS:-false}"

if [[ "${NO_COLOR:-}" == "1" ]]; then
    RED=""; GREEN=""; YELLOW=""; BLUE=""; CYAN=""; BOLD=""; RESET=""
else
    RED="\033[31m"; GREEN="\033[32m"; YELLOW="\033[33m"
    BLUE="\033[34m"; CYAN="\033[36m"; BOLD="\033[1m"; RESET="\033[0m"
fi

log_group_start() { [[ "$IS_GHA" == "true" ]] && echo "::group::$1"; echo -e "\n${BOLD}${CYAN}=== $1 ===${RESET}"; }
log_group_end()   { [[ "$IS_GHA" == "true" ]] && echo "::endgroup::"; return 0; }
log_info()        { echo -e "${BLUE}[INFO]${RESET} $1"; }
log_warn()        { echo -e "${YELLOW}[WARN]${RESET} $1"; }
log_pass()        { echo -e "${GREEN}[PASS]${RESET} $1"; }
log_fail()        { echo -e "${RED}[FAIL]${RESET} $1"; }
log_err()         { echo -e "${RED}[ERROR]${RESET} $1" >&2; }

# [SECTION: CLI ARGS]
while [[ $# -gt 0 ]]; do
    case "$1" in
        --ci)        CI_MODE=true; shift ;;
        --verbose)   VERBOSE=true; shift ;;
        --save)      SAVE_BASELINE="$2"; shift 2 ;;
        --compare)   COMPARE_BASELINE="$2"; shift 2 ;;
        --histogram) GENERATE_HISTOGRAM=true; shift ;;
        --json)      EXPORT_JSON="$2"; shift 2 ;;
        --help)
            echo "Universal Performance Benchmark Runner"
            echo ""
            echo "Usage:"
            echo "  ./scripts/benchmark.sh                   Run benchmarks"
            echo "  ./scripts/benchmark.sh --save NAME       Save baseline as NAME"
            echo "  ./scripts/benchmark.sh --compare ID      Compare vs baseline ID"
            echo "  ./scripts/benchmark.sh --histogram       Generate histogram SVG"
            echo "  ./scripts/benchmark.sh --json FILE       Export JSON to FILE"
            echo "  ./scripts/benchmark.sh --ci              CI mode (non-interactive)"
            echo "  ./scripts/benchmark.sh --verbose         Stream output"
            echo "  ./scripts/benchmark.sh --help            Show this help"
            echo ""
            echo "Examples:"
            echo "  ./scripts/benchmark.sh --save baseline"
            echo "  ./scripts/benchmark.sh --compare 0001"
            echo "  ./scripts/benchmark.sh --histogram --json benchmark_results.json"
            echo ""
            echo "Environment:"
            echo "  PY_VERSION   Python version for the isolated venv (default: 3.14)"
            echo "  NO_COLOR=1   Disable colored output"
            exit 0
            ;;
        *)
            log_err "Unknown option: $1"
            echo "Run './scripts/benchmark.sh --help' for usage" >&2
            exit 1
            ;;
    esac
done

# [SECTION: DIAGNOSTICS]
pre_flight_diagnostics() {
    log_group_start "Pre-Flight Diagnostics"
    echo "[  OK  ] Schema               : universal-agent-v1"

    if [[ "${UV_PROJECT_ENVIRONMENT:-}" == "$TARGET_VENV" ]]; then
        echo "[  OK  ] Environment          : Isolated ($TARGET_VENV)"
    else
        echo "[ INFO ] Environment          : System/User (${VIRTUAL_ENV:-<none>})"
    fi
    echo "[ INFO ] Python               : $(python --version)"
    echo "[ INFO ] PY_VERSION           : ${PY_VERSION}"

    if ! command -v pytest >/dev/null 2>&1; then
        echo "[ FAIL ] Tooling              : pytest missing (uv sync required)"
        exit 1
    fi
    echo "[  OK  ] Tool Verified        : pytest"

    if ! python -c "import pytest_benchmark" >/dev/null 2>&1; then
        echo "[ FAIL ] Tooling              : pytest-benchmark missing (uv sync required)"
        exit 1
    fi
    echo "[  OK  ] Tool Verified        : pytest-benchmark"

    log_group_end
}
pre_flight_diagnostics

# [SECTION: PROJECT ROOT]
PROJECT_ROOT="$PWD"
while [[ "$PROJECT_ROOT" != "/" && ! -f "$PROJECT_ROOT/pyproject.toml" ]]; do
    PROJECT_ROOT="$(dirname "$PROJECT_ROOT")"
done
cd "$PROJECT_ROOT"

# [SECTION: BENCHMARK DISCOVERY]
# Auto-discover the benchmark directory (prefer tests/benchmarks, then benchmarks, then tests)
BENCH_DIR=""
for candidate in "tests/benchmarks" "benchmarks" "tests"; do
    if [[ -d "$candidate" ]] && find "$candidate" -maxdepth 2 -name "bench_*.py" -o -name "*_bench.py" -o -name "test_*.py" 2>/dev/null | grep -q .; then
        BENCH_DIR="$candidate"
        break
    fi
done

if [[ -z "$BENCH_DIR" ]]; then
    log_err "No benchmark directory found. Expected one of: tests/benchmarks/, benchmarks/, tests/"
    echo "[EXIT-CODE] 1" >&2
    exit 1
fi

# [SECTION: BUILD COMMAND]
declare -a PYTEST_CMD=(
    "pytest"
    "$BENCH_DIR"
    "--benchmark-only"
)

if [[ "$VERBOSE" == "true" || "$CI_MODE" == "true" ]]; then
    PYTEST_CMD+=("-v")
fi

[[ -n "$SAVE_BASELINE"    ]] && PYTEST_CMD+=("--benchmark-save=$SAVE_BASELINE")
[[ -n "$COMPARE_BASELINE" ]] && PYTEST_CMD+=("--benchmark-compare=$COMPARE_BASELINE")
[[ "$GENERATE_HISTOGRAM" == "true" ]] && PYTEST_CMD+=("--benchmark-histogram")
[[ -n "$EXPORT_JSON"      ]] && PYTEST_CMD+=("--benchmark-json=$EXPORT_JSON")

# Agent/CI: force no ANSI noise from pytest itself
export NO_COLOR=1

# [SECTION: EXECUTION]
log_group_start "Benchmark Execution"
log_info "Target directory : $BENCH_DIR"
log_info "Command          : ${PYTEST_CMD[*]@Q}"

if [[ -n "$SAVE_BASELINE"    ]]; then log_info "Saving baseline  : $SAVE_BASELINE"; fi
if [[ -n "$COMPARE_BASELINE" ]]; then log_info "Comparing vs     : $COMPARE_BASELINE"; fi
if [[ "$GENERATE_HISTOGRAM" == "true" ]]; then log_info "Histogram        : enabled"; fi
if [[ -n "$EXPORT_JSON"      ]]; then log_info "JSON export      : $EXPORT_JSON"; fi

LOG_FILE=$(mktemp)
trap 'rm -f "$LOG_FILE"' EXIT

START_TIME="${EPOCHREALTIME}"

set +e
if [[ "$VERBOSE" == "true" ]]; then
    "${PYTEST_CMD[@]}" 2>&1 | tee "$LOG_FILE"
    EXIT_CODE=${PIPESTATUS[0]}
else
    "${PYTEST_CMD[@]}" >"$LOG_FILE" 2>&1
    EXIT_CODE=$?
fi
set -e

END_TIME="${EPOCHREALTIME}"
DURATION=$(printf "%.3f" "$(echo "$END_TIME - $START_TIME" | bc)")
log_group_end

# [SECTION: ANALYSIS]
set +e
TESTS_PASSED=$(grep -o '[0-9]* passed' "$LOG_FILE" | tail -1 | grep -o '[0-9]*' || echo "0")
TESTS_FAILED=$(grep -o '[0-9]* failed' "$LOG_FILE" | tail -1 | grep -o '[0-9]*' || echo "0")
TESTS_ERROR=$(grep  -o '[0-9]* error'  "$LOG_FILE" | tail -1 | grep -o '[0-9]*' || echo "0")
[[ -z "$TESTS_PASSED" ]] && TESTS_PASSED=0
[[ -z "$TESTS_FAILED" ]] && TESTS_FAILED=0
[[ -z "$TESTS_ERROR"  ]] && TESTS_ERROR=0

# Count benchmarks run (pytest-benchmark reports "X benchmarks")
BENCH_COUNT=$(grep -o '[0-9]* benchmark' "$LOG_FILE" | tail -1 | grep -o '[0-9]*' || echo "0")
[[ -z "$BENCH_COUNT" ]] && BENCH_COUNT=0

# Extract failed test IDs
declare -a FAILED_TEST_LIST=()
mapfile -t FAILED_TEST_LIST < <(grep -E "^FAILED | FAILED " "$LOG_FILE" | sed -E 's/^FAILED //' | sed -E 's/ - .*//' | sed -E 's/ FAILED.*//' | sort -u || true)
set -e

# [SECTION: OUTPUT]
if [[ $EXIT_CODE -eq 0 ]]; then
    log_pass "Benchmarks completed in $TARGET_VENV ($DURATION sec)."
else
    log_group_start "Failure Details"
    if [[ "$VERBOSE" != "true" ]]; then
        cat "$LOG_FILE"
    else
        echo "(See stream above for details)"
    fi
    log_group_end
fi

# [SECTION: REPORT]
log_group_start "Final Report"
echo "[SUMMARY-JSON-BEGIN]"

PYTHON_JSON_SCRIPT="
import json, sys

try:
    with open(sys.argv[1], 'r') as f:
        failed_tests = sorted(list(set(line.strip() for line in f if line.strip())))
except FileNotFoundError:
    failed_tests = []

final_obj = {
    'result':        'pass' if int(sys.argv[2]) == 0 else 'fail',
    'duration_sec':  sys.argv[3],
    'bench_count':   int(sys.argv[4]),
    'tests_passed':  int(sys.argv[5]),
    'tests_failed':  int(sys.argv[6]),
    'tests_error':   int(sys.argv[7]),
    'bench_dir':     sys.argv[8],
    'save_baseline': sys.argv[9] or None,
    'compare_base':  sys.argv[10] or None,
    'json_export':   sys.argv[11] or None,
    'failed_tests':  failed_tests,
    'exit_code':     int(sys.argv[2]),
}
print(json.dumps(final_obj, separators=(',', ':')))
"

FAILED_TESTS_FILE=$(mktemp)
for item in "${FAILED_TEST_LIST[@]:-}"; do
    [[ -n "$item" ]] && echo "$item" >> "$FAILED_TESTS_FILE"
done

python3 -c "$PYTHON_JSON_SCRIPT" \
    "$FAILED_TESTS_FILE" \
    "$EXIT_CODE" \
    "$DURATION" \
    "$BENCH_COUNT" \
    "$TESTS_PASSED" \
    "$TESTS_FAILED" \
    "$TESTS_ERROR" \
    "$BENCH_DIR" \
    "${SAVE_BASELINE:-}" \
    "${COMPARE_BASELINE:-}" \
    "${EXPORT_JSON:-}"

rm -f "$FAILED_TESTS_FILE"
echo "[SUMMARY-JSON-END]"

# Post-run hints
if [[ $EXIT_CODE -eq 0 ]]; then
    if [[ -n "$SAVE_BASELINE" ]]; then
        log_info "Baseline saved: $SAVE_BASELINE"
        log_info "Compare with  : ./scripts/benchmark.sh --compare <ID>"
    fi
    if [[ "$GENERATE_HISTOGRAM" == "true" ]]; then
        log_info "Histogram     : benchmark_histogram.svg"
    fi
    if [[ -n "$EXPORT_JSON" ]]; then
        log_info "JSON export   : $EXPORT_JSON"
    fi
fi

# [DEBUG-SUGGESTION]
if [[ $EXIT_CODE -ne 0 && ${#FAILED_TEST_LIST[@]:-0} -gt 0 ]]; then
    echo -e "\n${YELLOW}[DEBUG-SUGGESTION]${RESET}"
    echo "The following benchmarks failed. Run this command to debug the first failure:"
    echo "  uv run pytest ${FAILED_TEST_LIST[0]} -v --benchmark-only"
fi

log_group_end

if [[ $EXIT_CODE -ne 0 ]]; then
    log_err "Benchmarks FAILED."
    echo "[EXIT-CODE] 1" >&2
    exit 1
else
    log_pass "All benchmarks passed in $TARGET_VENV."
    echo "[EXIT-CODE] 0" >&2
    exit 0
fi
