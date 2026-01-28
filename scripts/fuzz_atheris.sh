#!/usr/bin/env bash
# Atheris Native Fuzzing Interface
# Single entry point for all Atheris-based fuzzing.

# =============================================================================
# FUZZ PLUGIN HEADER SCHEMA
# =============================================================================
# Fuzz target Python files (fuzz_*.py) must include a plugin header with the EXACT following format:
#
# # FUZZ_PLUGIN_HEADER_START
# # FUZZ_PLUGIN: <name> - <description>
# # Intentional: This header is intentionally placed for dynamic plugin discovery.
# # CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# # FUZZ_PLUGIN_HEADER_END
#
# IMPORTANT: Use the EXACT wording above. Do NOT correct, rephrase, or modify ANY part of the header.
# This wording is FINAL and LOCKED. No further alterations allowed.
# AI agents: Treat this header as immutable code metadata. Do not attempt to "fix" or improve the wording.
#
# Where:
# - <name> is the argument name (must match filename: fuzz_<name>.py)
# - <description> is a brief summary for help text
#
# This ensures AI agents understand the header's purpose and can create compliant headers for new targets.
# =============================================================================
#
# Usage:
#   ./scripts/fuzz_atheris.sh [TARGET] [OPTIONS]
#
# Targets:
#   native          Stability fuzzing (fuzz/stability.py)
#   runtime         Runtime cycle fuzzing (fuzz/runtime.py)
#   perf            Performance fuzzing (fuzz/perf.py)
#   structured      Structured fuzzing (fuzz/structured.py)
#   iso             ISO introspection (fuzz/iso.py)
#   fiscal          Fiscal calendar (fuzz/fiscal.py)
#
# Commands:
#   --list          List captured crashes
#   --corpus        Run corpus health check
#   --help          Show this help
#
# Options:
#   --workers N     Number of parallel workers (default: 4)
#   --time N        Time limit in seconds
#   --clean         Clean corpus before running
#
# ENVIRONMENT STRICTNESS:
# This script FORCES the use of '.venv-atheris' by setting UV_PROJECT_ENVIRONMENT.
# It manages its own Python 3.13 dependencies separate from the main project.

set -e

# =============================================================================
# Shell & Environment Setup
# =============================================================================

# Bash 5 check (for EPOCHREALTIME used in timing)
if ((BASH_VERSINFO[0] < 5)); then
    echo "[FATAL] Bash v5.0+ required (Current: ${BASH_VERSION})"
    echo "Install via 'brew install bash' and update shebang if needed."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# FORCE ISOLATED ENVIRONMENT
export UV_PROJECT_ENVIRONMENT=".venv-atheris"
# Unset VIRTUAL_ENV to prevent uv from confusing it with an active shell venv
unset VIRTUAL_ENV

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

# =============================================================================
# Plugin / Target Definitions
# =============================================================================

declare -A PARAM_TARGETS
declare -A PARAM_DESCRIPTIONS

# Dynamic Plugin Discovery
discover_plugins() {
    local fuzz_dir="$PROJECT_ROOT/fuzz"
    for file in "$fuzz_dir"/fuzz_*.py; do
        if [ -f "$file" ]; then
            # Find the FUZZ_PLUGIN line
            local header
            if header=$(grep -m1 '^# FUZZ_PLUGIN:' "$file" 2>/dev/null); then
                # Validate header structure with start and end tags
                local start_line plugin_line end_line
                start_line=$(grep -n '^# FUZZ_PLUGIN_HEADER_START' "$file" 2>/dev/null | head -1 | cut -d: -f1)
                plugin_line=$(grep -n '^# FUZZ_PLUGIN:' "$file" 2>/dev/null | head -1 | cut -d: -f1)
                end_line=$(grep -n '^# FUZZ_PLUGIN_HEADER_END' "$file" 2>/dev/null | head -1 | cut -d: -f1)
                if [ -n "$start_line" ] && [ -n "$plugin_line" ] && [ -n "$end_line" ] && [ "$start_line" -lt "$plugin_line" ] && [ "$plugin_line" -lt "$end_line" ]; then
                    if [[ $header =~ ^#\ FUZZ_PLUGIN:\ (.+)\ -\ (.+)$ ]]; then
                        local name="${BASH_REMATCH[1]}"
                        local desc="${BASH_REMATCH[2]}"
                        local filename
                        filename=$(basename "$file" .py)
                        local expected_name="fuzz_${name}"
                        if [ "$filename" = "$expected_name" ]; then
                            PARAM_TARGETS["$name"]="$file"
                            PARAM_DESCRIPTIONS["$name"]="$desc"
                        else
                            echo "Warning: Plugin name '$name' does not match filename '$filename'" >&2
                        fi
                    fi
                fi
            fi
        fi
    done
}

# Discover plugins
discover_plugins

# =============================================================================
# Pre-Flight Diagnostics & "Binary Surgery" (macOS Fix)
# =============================================================================

# This function ensures Atheris is installed, linked correctly, and running 
# on the correct Python version. It auto-heals macOS dynamic linking issues.
run_diagnostics() {
    echo -e "\n${BOLD}============================================================${NC}"
    echo -e "${BOLD}Atheris Diagnostic Check${NC}"
    echo -e "Env: ${BLUE}.venv-atheris${NC}"
    echo -e "${BOLD}============================================================${NC}\n"

    # 1. Check Python Version (Must be < 3.14)
    local python_bin
    python_bin=$(uv run --group atheris python -c "import sys; print(sys.executable)" 2>/dev/null)
    local python_version
    python_version=$("$python_bin" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+' | head -1)

    echo -n "Python Version... "
    if [[ "$python_version" == "3.14" ]] || [[ "$python_version" > "3.14" ]]; then
        echo -e "${RED}$python_version (Unsupported)${NC}"
        echo -e "${RED}[FATAL] Python $python_version is not supported by Atheris (Requires 3.11-3.13).${NC}"
        exit 3
    else
        echo -e "${GREEN}$python_version${NC}"
    fi

    # 2. Check ABI / Importability
    echo -n "ABI Compatibility... "
    if "$python_bin" -c "import atheris.core_with_libfuzzer" 2>/dev/null; then
        echo -e "${GREEN}OK${NC}"
        
        echo -n "Fuzzing Capability... "
        if "$python_bin" -c "import atheris; f=lambda d:None; atheris.Setup(['test'],f); print('OK')" 2>/dev/null | grep -q "OK"; then
            echo -e "${GREEN}OK${NC}"
        else
            echo -e "${RED}FAILED${NC}"
            exit 1
        fi
        
        echo -e "\n${BOLD}============================================================${NC}"
        echo -e "${GREEN}[OK]${NC} Atheris is ready."
        echo -e "${BOLD}============================================================${NC}\n"
        return 0
    fi

    echo -e "${RED}FAILED${NC}"
    echo -e "${YELLOW}[WARN] Atheris ABI check failed. Attempting Auto-Heal...${NC}"

    # 3. macOS Auto-Heal (Binary Surgery)
    if [[ "$(uname)" == "Darwin" ]]; then
        heal_macos_atheris "$python_bin"
        
        # Verify after healing
        echo -n "ABI Compatibility (Post-Fix)... "
        if "$python_bin" -c "import atheris.core_with_libfuzzer" 2>/dev/null; then
             echo -e "${GREEN}OK${NC}"
             echo -e "\n${BOLD}============================================================${NC}"
             echo -e "${GREEN}[OK]${NC} Atheris was repaired and is ready."
             echo -e "${BOLD}============================================================${NC}\n"
        else
             echo -e "${RED}STILL FAILING${NC}"
             exit 1
        fi
    else
        echo -e "${RED}[FATAL] Atheris setup is broken and this is not macOS (cannot auto-heal).${NC}"
        echo "Try: uv cache clean atheris && uv sync --group atheris --reinstall"
        exit 1
    fi
}


heal_macos_atheris() {
    local python_bin="$1"
    
    # Locate LLVM
    local llvm_prefix
    llvm_prefix=$(brew --prefix llvm 2>/dev/null || echo "/opt/homebrew/opt/llvm")
    
    if [[ ! -d "$llvm_prefix" ]]; then
        echo -e "${RED}[ERROR] LLVM not found. Please run: brew install llvm${NC}"
        exit 2
    fi

    echo -e "${BLUE}[SURGERY] Re-installing Atheris with custom flags...${NC}"
    
    # Reinstall with special flags
    (
        export CLANG_BIN="$llvm_prefix/bin/clang"
        export CC="$llvm_prefix/bin/clang"
        export CXX="$llvm_prefix/bin/clang++"
        export LDFLAGS="-L$llvm_prefix/lib/c++ -L$llvm_prefix/lib -Wl,-rpath,$llvm_prefix/lib/c++"
        export CPPFLAGS="-I$llvm_prefix/include"
        
        # Force reinstall in the specific environment
        uv pip install --python "$python_bin" --reinstall --no-cache-dir --no-binary :all: atheris
    )

    # Validate again
    if "$python_bin" -c "import atheris.core_with_libfuzzer" 2>/dev/null; then
        echo -e "${GREEN}[SUCCESS] Atheris repaired successfully.${NC}"
    else
        echo -e "${RED}[FATAL] Surgery failed. Could not fix Atheris ABI.${NC}"
        exit 1
    fi
}

# =============================================================================
# Subroutines
# =============================================================================

show_help() {
    cat << EOF
Atheris Fuzzing Interface

USAGE:
    ./scripts/fuzz_atheris.sh [TARGET] [OPTIONS]

TARGETS:
EOF
    for key in "${!PARAM_TARGETS[@]}"; do
        printf "    %-15s %s\n" "$key" "${PARAM_DESCRIPTIONS[$key]}"
    done
    cat << EOF

OPTIONS:
    --list          List all crashes in corpus
    --corpus        Run corpus health check (fuzz_corpus_health.py)
    --minimize FILE Minimize a crash input
    --workers N     Number of workers (default: 4)
    --time N        Max time in seconds
    --clean         Clean corpus before run
    --help          Show this help

EXAMPLES:
    ./scripts/fuzz_atheris.sh native --time 60
    ./scripts/fuzz_atheris.sh perf
EOF
}

run_list() {
    echo -e "${BOLD}Atheris Crashes (.fuzz_corpus)${NC}"
    local corpus_dir="$PROJECT_ROOT/.fuzz_corpus"
    
    if [[ -d "$corpus_dir" ]]; then
        local count
        count=$(find "$corpus_dir" -name "crash_*" -type f 2>/dev/null | wc -l | tr -d ' ')
        if [[ $count -gt 0 ]]; then
             echo "Found $count crash(es):"
             ls -lt "$corpus_dir"/crash_* | head -10 | awk '{print "  " $NF}'
             echo ""
             echo "Inspect: xxd $(ls -t "$corpus_dir"/crash_* | head -1) | head -20"
        else
             echo "No crashes found."
        fi
    else
        echo "No corpus directory found."
    fi
}

run_corpus_health() {
    echo -e "${BOLD}Checking Corpus Health...${NC}"
    uv run --group atheris python scripts/fuzz_corpus_health.py
}

parse_and_display_report() {
    local target_key="$1"
    local corpus_dir="$PROJECT_ROOT/.fuzz_corpus"

    # Try to read JSON report from file (written during fuzzing)
    local report_file="$corpus_dir/fuzz_${target_key}_report.json"
    local json_report=""

    if [[ -f "$report_file" ]]; then
        json_report=$(cat "$report_file" 2>/dev/null)
    fi

    if [[ -z "$json_report" ]]; then
        echo -e "\n${YELLOW}[WARN] No JSON summary found (fuzzer may not have completed enough iterations)${NC}" >&2
        return 0
    fi

    # Check for jq availability
    if ! command -v jq &> /dev/null; then
        echo -e "\n${YELLOW}[WARN] jq not found - install for detailed reporting${NC}" >&2
        echo "$json_report" | grep -o '"findings":[0-9]*' >&2
        return 0
    fi

    # Parse key metrics
    local status iterations findings
    status=$(echo "$json_report" | jq -r '.status // "unknown"')
    iterations=$(echo "$json_report" | jq -r '.iterations // 0')
    findings=$(echo "$json_report" | jq -r '.findings // 0')

    # Display summary header
    echo -e "\n${BOLD}============================================================${NC}"
    echo -e "${BOLD}Fuzzing Campaign Summary${NC}"
    echo -e "${BOLD}============================================================${NC}"
    echo "Status:     $status"
    echo "Iterations: $(printf "%'d" "$iterations")"
    echo "Findings:   $(printf "%'d" "$findings")"

    # Performance metrics (if available)
    local perf_mean perf_p95 perf_p99
    perf_mean=$(echo "$json_report" | jq -r '.perf_mean_ms // empty')
    perf_p95=$(echo "$json_report" | jq -r '.perf_p95_ms // empty')
    perf_p99=$(echo "$json_report" | jq -r '.perf_p99_ms // empty')

    if [[ -n "$perf_mean" ]]; then
        echo ""
        echo "Performance:"
        echo "  Mean:     ${perf_mean}ms"
        if [[ -n "$perf_p95" ]]; then
            echo "  P95:      ${perf_p95}ms"
        fi
        if [[ -n "$perf_p99" ]]; then
            echo "  P99:      ${perf_p99}ms"
        fi
    fi

    # Memory metrics (if available)
    local mem_peak mem_delta
    mem_peak=$(echo "$json_report" | jq -r '.memory_peak_mb // empty')
    mem_delta=$(echo "$json_report" | jq -r '.memory_delta_mb // empty')

    if [[ -n "$mem_peak" ]]; then
        echo ""
        echo "Memory:"
        echo "  Peak:     ${mem_peak}MB"
        if [[ -n "$mem_delta" ]]; then
            echo "  Delta:    ${mem_delta}MB"
        fi
    fi

    # CRITICAL: Alert on findings
    if [[ "$findings" -gt 0 ]]; then
        echo -e "\n${RED}${BOLD}[WARNING] API Contract Violations Detected${NC}"
        echo -e "${RED}Found $findings violations during fuzzing campaign${NC}"
        echo ""

        # Extract and display top error patterns
        echo "Top Error Patterns:"
        echo "$json_report" | jq -r 'to_entries | map(select(.key | startswith("error_") or startswith("contract_"))) | sort_by(-.value) | limit(10; .[]) | "  \(.key): \(.value)"' 2>/dev/null || true

        echo ""
        echo -e "${YELLOW}Action Required:${NC}"
        echo "  1. Review error patterns above"
        echo "  2. Inspect full JSON report in fuzzer stderr"
        echo "  3. Fix API contract violations in source code"
        echo "  4. Re-run fuzzer to verify fixes"

        echo -e "${BOLD}============================================================${NC}"
        return 1
    else
        echo -e "\n${GREEN}[OK] No API contract violations detected${NC}"
        echo -e "${BOLD}============================================================${NC}"
        return 0
    fi
}

run_fuzz_target() {
    local target_key="$1"
    local target_script="${PARAM_TARGETS[$target_key]}"

    if [[ -z "$target_script" ]]; then
        echo -e "${RED}[ERROR] Unknown target: $target_key${NC}"
        show_help
        exit 1
    fi

    echo -e "${BOLD}Starting Fuzzing Campaign${NC}"
    echo "Target:  $target_key ($target_script)"
    echo "Workers: $WORKERS"
    if [[ -n "$TIME_LIMIT" ]]; then
        echo "Time:    ${TIME_LIMIT}s"
    else
        echo "Time:    Indefinite (Ctrl+C to stop)"
    fi
    echo ""

    # Ensure Setup
    run_diagnostics

    local corpus_dir="$PROJECT_ROOT/.fuzz_corpus"
    mkdir -p "$corpus_dir"

    # Construct args
    if [[ -n "$TIME_LIMIT" ]]; then
        args="-max_total_time=$TIME_LIMIT"
    fi

    # Explicitly add seed corpus to arguments if it exists
    # Prefer target-specific seeds (fuzz/seeds/<target>) over generic seeds
    local seed_dir=""
    if [[ -d "fuzz/seeds/$target_key" ]]; then
        seed_dir="fuzz/seeds/$target_key"
    elif [[ -d "fuzz/seeds" ]]; then
        seed_dir="fuzz/seeds"
    fi

    if [[ -n "$seed_dir" ]]; then
        args="$args $seed_dir"
        # The first directory passed to libFuzzer is the output corpus (read/write),
        # subsequent directories are input seeds (read-only).
        # We already pass '$corpus_dir' as the first positional arg below.
    fi

    # Run fuzzer (report will be written to .fuzz_corpus/fuzz_<target>_report.json)
    local exit_code=0
    uv run --group atheris python "$target_script" \
        -workers="$WORKERS" \
        -jobs=0 \
        -artifact_prefix="$corpus_dir/crash_" \
        "$corpus_dir" \
        $args \
        || exit_code=$?

    # Parse and display report from file
    if ! parse_and_display_report "$target_key"; then
        echo -e "\n${RED}[FAIL] Fuzzer detected API contract violations${NC}" >&2
        exit 1
    fi

    # Return fuzzer exit code if non-zero
    if [[ $exit_code -ne 0 ]]; then
        exit $exit_code
    fi
}


# =============================================================================
# Main Dispatch
# =============================================================================

# Defaults
WORKERS=4
TIME_LIMIT=""
TARGET=""
MODE="fuzz"

# Strict Argument Parser
while [[ $# -gt 0 ]]; do
    case "$1" in
        --list|--corpus|--clean)
            if [[ "$MODE" != "fuzz" && "$MODE" != "${1#--}" ]]; then
                echo -e "${RED}[ERROR] Conflicting modes selected: $MODE vs ${1#--}${NC}"
                exit 1
            fi
            MODE="${1#--}"
            shift
            ;;
        --minimize)
            MODE="minimize"
            MINIMIZE_FILE="$2"
            shift 2
            ;;
        --workers) WORKERS="$2"; shift 2 ;;
        --time) TIME_LIMIT="$2"; shift 2 ;;
        --help|-h) show_help; exit 0 ;;
        -*)
            echo "Unknown option: $1"
            echo "Run './scripts/fuzz_atheris.sh --help' for usage."
            exit 1
            ;;
        *)
            if [[ -n "$TARGET" ]]; then
                echo -e "${RED}[ERROR] Multiple targets specified: $TARGET and $1${NC}"
                exit 1
            fi
            TARGET="$1"
            shift
            ;;
    esac
done

# [SECTION: SIGNAL_HANDLING]
PID_LIST=()
cleanup() {
    if [[ ${#PID_LIST[@]} -gt 0 ]]; then
        for pid in "${PID_LIST[@]}"; do
            kill -TERM "$pid" 2>/dev/null || true
        done
        wait
    fi
}
trap cleanup EXIT INT TERM

run_minimize() {
    if [[ -z "$MINIMIZE_FILE" ]]; then
        echo -e "${RED}[ERROR] Missing file argument for --minimize${NC}"
        exit 1
    fi
    
    if [[ ! -f "$MINIMIZE_FILE" ]]; then
        echo -e "${RED}[ERROR] Crash file not found: $MINIMIZE_FILE${NC}"
        exit 1
    fi

    run_diagnostics
    echo -e "${BOLD}Minimizing Crash: $MINIMIZE_FILE${NC}"
    
    MINIMIZED="${MINIMIZE_FILE}.minimized"
    local stability_script="fuzz/stability.py"
    
    # Run Atheris with -minimize_crash=1
    # We use 'uv run' here instead of exec because we need to post-process the result
    uv run --group atheris python "$stability_script" \
        -minimize_crash=1 \
        -exact_artifact_path="$MINIMIZED" \
        "$MINIMIZE_FILE"
        
    if [[ -f "$MINIMIZED" ]]; then
        ORIG_SIZE=$(stat -f%z "$MINIMIZE_FILE" 2>/dev/null || stat -c%s "$MINIMIZE_FILE")
        NEW_SIZE=$(stat -f%z "$MINIMIZED" 2>/dev/null || stat -c%s "$MINIMIZED")
        
        echo -e "\n${BOLD}============================================================${NC}"
        echo -e "${GREEN}[SUCCESS] Crash minimized.${NC}"
        echo "Original size:  $ORIG_SIZE bytes"
        echo "Minimized size: $NEW_SIZE bytes"
        echo "Saved to:       $MINIMIZED"
        echo -e "${BOLD}============================================================${NC}"
        
        echo -e "\n${YELLOW}Next Step (Reproduce):${NC}"
        echo "  ./scripts/fuzz_hypofuzz.sh --repro $MINIMIZED"
    else
        echo -e "${RED}[ERROR] Minimization failed (no output file generated).${NC}"
        exit 1
    fi
}

case "$MODE" in
    list)
        run_list
        ;;
    corpus)
        run_corpus_health
        ;;
    minimize)
        run_minimize
        ;;
    fuzz)
        if [[ -z "$TARGET" ]]; then
            run_diagnostics
            show_help
            exit 0
        fi
        run_fuzz_target "$TARGET"
        ;;
esac
