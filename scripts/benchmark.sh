#!/usr/bin/env bash
# ==============================================================================
# benchmark.sh - FTLLexEngine Performance Benchmark Runner
# ==============================================================================
#
# PURPOSE:
#   Run pytest-benchmark suite to measure performance of critical operations
#   and detect regressions. Tracks parser, bundle formatting, and localization
#   fallback performance.
#
# USAGE:
#   ./scripts/benchmark.sh                  # Run benchmarks
#   ./scripts/benchmark.sh --save baseline  # Save baseline
#   ./scripts/benchmark.sh --compare 0001   # Compare vs baseline
#   ./scripts/benchmark.sh --histogram      # Generate histogram
#   ./scripts/benchmark.sh --ci             # CI mode (non-interactive)
#
# OUTPUTS:
#   - Benchmark results (min/max/mean/median/stddev)
#   - Statistical analysis (IQR, outliers)
#   - Operations per second (OPS)
#
# DATA CONSUMED:
#   - tests/benchmarks/*.py - Benchmark test files
#   - .benchmarks/ - Saved baseline data (optional)
#
# DATA PRODUCED:
#   - .benchmarks/ - Saved benchmark results
#   - benchmark_results.json - JSON export (if --json specified)
#   - benchmark_histogram.svg - Histogram (if --histogram specified)
#
# PERFORMANCE TARGETS (per BENCHMARK_PLAN.md):
#   Parser:
#     - Simple message: < 100 μs
#     - Select expression: < 500 μs
#     - Large resource (100 msgs): < 10 ms
#   Bundle Formatting:
#     - Simple message: < 50 μs
#     - Variable interpolation: < 100 μs
#     - Select expression: < 200 μs
#   Localization Fallback:
#     - Single locale: < 60 μs
#     - Two-locale fallback: < 120 μs
#     - Three-locale fallback: < 180 μs
#
# REGRESSION THRESHOLD:
#   20% slowdown triggers investigation
#
# ECOSYSTEM:
#   1. lint.sh - Code quality
#   2. test.sh - Correctness
#   3. benchmark.sh - Performance (this script)
#
# CI/CD:
#   GitHub Actions can run benchmarks with --ci flag for regression detection.
#   Use --benchmark-json for CI artifact storage.
#
# ==============================================================================

set -e  # Exit on error

# Check if running in project root
if [ ! -f "pyproject.toml" ]; then
    echo "[ERROR] Must run from project root directory"
    exit 1
fi

# Activate virtual environment if available
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Parse command line arguments
BENCHMARK_ARGS=""
CI_MODE=false
SAVE_BASELINE=""
COMPARE_BASELINE=""
GENERATE_HISTOGRAM=false
EXPORT_JSON=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --ci)
            CI_MODE=true
            shift
            ;;
        --save)
            SAVE_BASELINE="$2"
            shift 2
            ;;
        --compare)
            COMPARE_BASELINE="$2"
            shift 2
            ;;
        --histogram)
            GENERATE_HISTOGRAM=true
            shift
            ;;
        --json)
            EXPORT_JSON="$2"
            shift 2
            ;;
        --help)
            echo "FTLLexEngine Performance Benchmark Runner"
            echo ""
            echo "Usage:"
            echo "  ./scripts/benchmark.sh                  Run benchmarks"
            echo "  ./scripts/benchmark.sh --save NAME      Save baseline as NAME"
            echo "  ./scripts/benchmark.sh --compare ID     Compare vs baseline ID"
            echo "  ./scripts/benchmark.sh --histogram      Generate histogram"
            echo "  ./scripts/benchmark.sh --json FILE      Export JSON to FILE"
            echo "  ./scripts/benchmark.sh --ci             CI mode (non-interactive)"
            echo "  ./scripts/benchmark.sh --help           Show this help"
            echo ""
            echo "Examples:"
            echo "  ./scripts/benchmark.sh --save baseline"
            echo "  ./scripts/benchmark.sh --compare 0001"
            echo "  ./scripts/benchmark.sh --histogram --json benchmark_results.json"
            exit 0
            ;;
        *)
            echo "[ERROR] Unknown option: $1"
            echo "Run './scripts/benchmark.sh --help' for usage"
            exit 1
            ;;
    esac
done

# Build pytest-benchmark command
PYTEST_CMD="pytest tests/benchmarks/ --benchmark-only -v"

if [ "$SAVE_BASELINE" != "" ]; then
    PYTEST_CMD="$PYTEST_CMD --benchmark-save=$SAVE_BASELINE"
fi

if [ "$COMPARE_BASELINE" != "" ]; then
    PYTEST_CMD="$PYTEST_CMD --benchmark-compare=$COMPARE_BASELINE"
fi

if [ "$GENERATE_HISTOGRAM" = true ]; then
    PYTEST_CMD="$PYTEST_CMD --benchmark-histogram"
fi

if [ "$EXPORT_JSON" != "" ]; then
    PYTEST_CMD="$PYTEST_CMD --benchmark-json=$EXPORT_JSON"
fi

# Display header
if [ "$CI_MODE" = false ]; then
    echo "========================================="
    echo "FTLLexEngine Performance Benchmarks"
    echo "========================================="
    echo ""
fi

# Display configuration
if [ "$CI_MODE" = false ]; then
    echo "Configuration:"
    if [ "$SAVE_BASELINE" != "" ]; then
        echo "  - Saving baseline as: $SAVE_BASELINE"
    fi
    if [ "$COMPARE_BASELINE" != "" ]; then
        echo "  - Comparing vs baseline: $COMPARE_BASELINE"
    fi
    if [ "$GENERATE_HISTOGRAM" = true ]; then
        echo "  - Generating histogram"
    fi
    if [ "$EXPORT_JSON" != "" ]; then
        echo "  - Exporting JSON to: $EXPORT_JSON"
    fi
    echo ""
    echo "========================================="
    echo "RUNNING BENCHMARKS"
    echo "========================================="
    echo "[CMD] $PYTEST_CMD"
    echo ""
fi

# Run benchmarks
eval "$PYTEST_CMD"

# Display success message
if [ "$CI_MODE" = false ]; then
    echo ""
    echo "========================================="
    echo "[PASS] Benchmarks completed successfully"
    echo ""
    if [ "$SAVE_BASELINE" != "" ]; then
        echo "Baseline saved: $SAVE_BASELINE"
        echo "Compare with: ./scripts/benchmark.sh --compare <ID>"
    fi
    if [ "$GENERATE_HISTOGRAM" = true ]; then
        echo "Histogram generated: benchmark_histogram.svg"
    fi
    if [ "$EXPORT_JSON" != "" ]; then
        echo "JSON exported: $EXPORT_JSON"
    fi
    echo ""
    echo "Next steps:"
    echo "  - Review performance metrics above"
    echo "  - Check for regressions (>20% slowdown)"
    echo "  - Save baseline: ./scripts/benchmark.sh --save baseline"
    echo "========================================="
fi
