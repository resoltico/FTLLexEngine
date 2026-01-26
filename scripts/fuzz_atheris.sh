#!/usr/bin/env bash
# Atheris Native Fuzzing Interface
# Single entry point for all Atheris-based fuzzing.
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

# PLUGIN REGISTRY
# To add a new fuzzing target, add it here.
PARAM_TARGETS["native"]="fuzz/stability.py"
PARAM_DESCRIPTIONS["native"]="Core parser stability (Finding crashes/panics)"

PARAM_TARGETS["runtime"]="fuzz/runtime.py"
PARAM_DESCRIPTIONS["runtime"]="End-to-End Runtime & strict mode validation"

PARAM_TARGETS["perf"]="fuzz/perf.py"
PARAM_DESCRIPTIONS["perf"]="Performance & ReDoS detection"

PARAM_TARGETS["structured"]="fuzz/structured.py"
PARAM_DESCRIPTIONS["structured"]="Structure-aware fuzzing (Deep AST)"

PARAM_TARGETS["iso"]="fuzz/iso.py"
PARAM_DESCRIPTIONS["iso"]="ISO 3166/4217 Introspection"

PARAM_TARGETS["fiscal"]="fuzz/fiscal.py"
PARAM_DESCRIPTIONS["fiscal"]="Fiscal Calendar arithmetic"

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
    --corpus        Run corpus health check (corpus-health.py)
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
    uv run --group atheris python scripts/corpus-health.py
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
    if [[ -d "fuzz/seeds" ]]; then
        args="$args fuzz/seeds"
        # The first directory passed to libFuzzer is the output corpus (read/write),
        # subsequent directories are input seeds (read-only).
        # We already pass '$corpus_dir' as the first positional arg in the exec line below.
    fi

    # Run
    # Note: We use 'exec' to replace the shell, letting the python process handle signals
    exec uv run --group atheris python "$target_script" \
        -workers="$WORKERS" \
        -jobs=0 \
        -artifact_prefix="$corpus_dir/crash_" \
        "$corpus_dir" \
        $args
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
