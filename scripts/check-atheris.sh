#!/usr/bin/env bash
# ==============================================================================
# Atheris Installation Checker & Installer
# ==============================================================================
# COMPATIBILITY: Bash 5.0+ (Optimized for 5.3)
# FEATURES: Binary Surgery, RPATH Injection, Deterministic Extraction
# ==============================================================================

set -o errexit
set -o nounset
set -o pipefail
shopt -s inherit_errexit 2>/dev/null || true

# --- CONFIGURATION ---
# Dedicated environment for fuzzing to avoid stomping by other tasks (e.g., linting)
export UV_PROJECT_ENVIRONMENT=".venv-fuzzing"
unset VIRTUAL_ENV

# Standard Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

DO_INSTALL=false
[[ "${1:-}" == "--install" ]] && DO_INSTALL=true

echo -e "\n${BOLD}============================================================${NC}"
echo -e "${BOLD}Atheris Check${NC}"
echo -e "Env: ${BLUE}$UV_PROJECT_ENVIRONMENT${NC}"
echo -e "${BOLD}============================================================${NC}\n"

# --- 1. CORE DIAGNOSTICS ---
PYTHON_BIN=$(uv run --group fuzzing python -c "import sys; print(sys.executable)" 2>/dev/null)
PYTHON_VERSION=$("$PYTHON_BIN" --version 2> /dev/null | grep -oE '[0-9]+\.[0-9]+' | head -1)

echo -n "Python Version... "
echo -e "${GREEN}$PYTHON_VERSION${NC}"

# --- 2. SURGERY ENGINE ---
perform_surgery() {
    local SO_FILE=$1
    local LLVM_LIB_PATH=$2

    echo -e "${BLUE}[SURGERY] Injecting RPATH into binary...${NC}"
    
    # 1. Add RPATH to the LLVM lib/c++ directory
    # We use || true because it might already exist, and we don't want to fail if it does
    install_name_tool -add_rpath "$LLVM_LIB_PATH" "$SO_FILE" 2>/dev/null || true
    
    # 2. Verify with otool
    if otool -l "$SO_FILE" | grep -q "$LLVM_LIB_PATH"; then
        echo -e "${GREEN}[SUCCESS] Surgery successful. RPATH embedded.${NC}"
    else
        echo -e "${RED}[ERROR] Surgery failed to embed RPATH.${NC}"
    fi
}

install_atheris() {
    local LLVM_PREFIX
    LLVM_PREFIX=$(brew --prefix llvm 2>/dev/null || echo "/opt/homebrew/opt/llvm")
    
    if [[ ! -d "$LLVM_PREFIX" ]]; then
        echo -e "${RED}[ERROR] LLVM not found. Run: brew install llvm${NC}"
        exit 2
    fi

    echo -e "${YELLOW}Purging caches & performing custom build...${NC}"
    uv cache clean atheris 2>/dev/null || true

    (
        export CLANG_BIN="$LLVM_PREFIX/bin/clang"
        export CC="$LLVM_PREFIX/bin/clang"
        export CXX="$LLVM_PREFIX/bin/clang++"
        export LDFLAGS="-L$LLVM_PREFIX/lib/c++ -L$LLVM_PREFIX/lib -Wl,-rpath,$LLVM_PREFIX/lib/c++"
        export CPPFLAGS="-I$LLVM_PREFIX/include"
        
        uv pip install --python "$PYTHON_BIN" --reinstall --no-cache-dir --no-binary :all: atheris
    )

    # Find the binary
    local SITE_PACKAGES
    SITE_PACKAGES=$("$PYTHON_BIN" -c "import site; print(site.getsitepackages()[0])")
    local SO_FILE
    SO_FILE=$(find "$SITE_PACKAGES/atheris" -name "core_with_libfuzzer*.so" | head -1)

    if [[ -z "$SO_FILE" ]]; then
        echo -e "${RED}[ERROR] Could not locate atheris binary for surgery.${NC}"
        exit 1
    fi

    perform_surgery "$SO_FILE" "$LLVM_PREFIX/lib/c++"
}

# --- 3. THE LOGIC LOOP ---
# Check ABI Compatibility FIRST (The true test)
ABI_STATUS="FAIL"
echo -n "ABI Compatibility... "
if "$PYTHON_BIN" -c "import atheris.core_with_libfuzzer" 2>/dev/null; then
    ABI_STATUS="OK"
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
fi

# Determine if we need to install
if [[ "$ABI_STATUS" == "FAIL" ]]; then
    if [[ "$DO_INSTALL" == "true" ]]; then
        install_atheris
        # Re-check
        echo -n "ABI Compatibility (after surgery)... "
        if "$PYTHON_BIN" -c "import atheris.core_with_libfuzzer" 2>/dev/null; then
            echo -e "${GREEN}OK${NC}"
        else
            echo -e "${RED}STILL FAILING${NC}"
            echo -e "${YELLOW}Attempting DYLD_LIBRARY_PATH fallback for verification...${NC}"
            LLVM_PREFIX=$(brew --prefix llvm 2>/dev/null || echo "/opt/homebrew/opt/llvm")
            export DYLD_LIBRARY_PATH="$LLVM_PREFIX/lib/c++"
            if "$PYTHON_BIN" -c "import atheris.core_with_libfuzzer" 2>/dev/null; then
                echo -e "${GREEN}Works with DYLD_LIBRARY_PATH.${NC}"
                echo -e "${YELLOW}[IMPORTANT] Add this to your ~/.zshrc:${NC}"
                echo "  export DYLD_LIBRARY_PATH=\"$LLVM_PREFIX/lib/c++\""
            fi
        fi
    else
        echo -e "\n${YELLOW}[!] Atheris is broken. Fix it with:${NC}"
        echo -e "    ./scripts/check-atheris.sh --install\n"
        exit 1
    fi
fi

echo -n "Fuzzing Capability... "
if "$PYTHON_BIN" -c "import atheris; f=lambda d:None; atheris.Setup(['test'],f); print('OK')" 2>/dev/null | grep -q "OK"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    exit 1
fi

echo -e "\n${BOLD}============================================================${NC}"
echo -e "${GREEN}[OK]${NC} Atheris is ready in .venv-fuzzing."
echo -e "${BOLD}============================================================${NC}\n"
