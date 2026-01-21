#!/bin/bash
# Atheris Installation Checker
# Verifies that Atheris is properly installed and configured.
#
# Usage:
#   ./scripts/check-atheris.sh
#
# Exit codes:
#   0: Atheris is ready
#   1: Atheris not installed or not working
#   2: LLVM not installed (macOS)
#   3: Python version incompatible (requires 3.11-3.13)

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo -e "${BOLD}============================================================${NC}"
echo -e "${BOLD}Atheris Installation Check${NC}"
echo -e "${BOLD}============================================================${NC}"
echo ""

# Check 1: Python version
echo -n "Python version... "
PYTHON_VERSION=$(uv run --group fuzzing python --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
echo -e "${GREEN}$PYTHON_VERSION${NC}"

# Check 1b: Python version compatibility
if [[ "$PYTHON_VERSION" == "3.14" ]] || [[ "$PYTHON_VERSION" > "3.14" ]]; then
    echo ""
    echo -e "${YELLOW}[WARN]${NC} Python $PYTHON_VERSION is not supported by Atheris."
    echo ""
    echo "Atheris native fuzzing requires Python 3.11-3.13."
    echo "Python 3.14+ is not yet supported by the Atheris project."
    echo ""
    echo "Options:"
    echo -e "${BOLD}1. Switch to Python 3.13:${NC}"
    echo "   uv run --python 3.13 ./scripts/check-atheris.sh"
    echo ""
    echo -e "${BOLD}2. Use property-based fuzzing (works on Python 3.14):${NC}"
    echo "   ./scripts/fuzz.sh          # Hypothesis tests"
    echo "   ./scripts/fuzz.sh --deep   # HypoFuzz coverage"
    echo ""
    echo "See docs/FUZZING_GUIDE.md for Python version requirements."
    exit 3
fi

# Check 2: Atheris import
echo -n "Atheris import... "
if uv run --group fuzzing python -c "import atheris" 2>/dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    echo ""
    echo -e "${YELLOW}Atheris is not installed or not working.${NC}"
    echo ""

    # Check if this is macOS
    if [[ "$(uname)" == "Darwin" ]]; then
        echo "On macOS, Atheris requires LLVM Clang (not Apple Clang)."
        echo ""

        # Check for LLVM
        if command -v brew &> /dev/null; then
            if brew list llvm &> /dev/null; then
                echo -e "${GREEN}LLVM is installed via Homebrew.${NC}"
                LLVM_PREFIX=$(brew --prefix llvm)
                echo "LLVM location: $LLVM_PREFIX"
                echo ""
                echo "To install Atheris with LLVM, run:"
                echo ""
                echo -e "${BOLD}CLANG_BIN=\"$LLVM_PREFIX/bin/clang\" \\"
                echo "CC=\"$LLVM_PREFIX/bin/clang\" \\"
                echo "CXX=\"$LLVM_PREFIX/bin/clang++\" \\"
                echo "LDFLAGS=\"-L$LLVM_PREFIX/lib/c++ -L$LLVM_PREFIX/lib -Wl,-rpath,$LLVM_PREFIX/lib/c++\" \\"
                echo "CPPFLAGS=\"-I$LLVM_PREFIX/include\" \\"
                echo -e "uv pip install --reinstall --no-cache-dir --no-binary :all: atheris${NC}"
                echo ""
                echo "The -Wl,-rpath flag ensures LLVM's libc++ is used at runtime."
            else
                echo -e "${YELLOW}LLVM is not installed.${NC}"
                echo ""
                echo "Install LLVM first:"
                echo -e "${BOLD}brew install llvm${NC}"
                echo ""
                echo "Then re-run this script for installation instructions."
                exit 2
            fi
        else
            echo "Homebrew not found. Install LLVM manually and set CC/CXX environment variables."
        fi
    else
        # Linux
        echo "On Linux, install Atheris directly:"
        echo -e "${BOLD}uv pip install atheris${NC}"
    fi

    exit 1
fi

# Check 3: Atheris version
echo -n "Atheris version... "
ATHERIS_VERSION=$(uv run --group fuzzing python -c "import importlib.metadata; print(importlib.metadata.version('atheris'))" 2>/dev/null || echo "unknown")
echo -e "${GREEN}$ATHERIS_VERSION${NC}"

# Check 3b: deep ABI compatibility check (macOS)
if [[ "$(uname)" == "Darwin" ]]; then
    echo -n "ABI compatibility... "
    # Try importing the core module that has the ABI-sensitive code
    # This is where the symbol lookup error occurs
    # Note: use || true to prevent set -e from exiting on Python failure
    ABI_TEST=$(uv run --group fuzzing python -c "
import atheris
import atheris.core_with_libfuzzer
print('OK')
" 2>&1) || true

    if [[ "$ABI_TEST" == *"OK"* ]]; then
        echo -e "${GREEN}OK${NC}"
    elif [[ "$ABI_TEST" == *"symbol not found"* ]]; then
        echo -e "${RED}FAILED${NC}"
        echo ""
        echo -e "${YELLOW}[ERROR] C++ ABI mismatch detected.${NC}"
        echo "Atheris expects symbols found in LLVM libc++ but is loading Apple's system libc++."
        echo ""
        echo -e "${BOLD}Quick Fix:${NC}"
        if command -v brew &>/dev/null && brew --prefix llvm &>/dev/null; then
            LLVM_PREFIX=$(brew --prefix llvm)
            echo "  export DYLD_LIBRARY_PATH=\"$LLVM_PREFIX/lib/c++\""
        else
            echo "  # Find your LLVM installation and set DYLD_LIBRARY_PATH"
        fi
        echo ""
        echo -e "${BOLD}Permanent Fix (Recommended):${NC}"
        echo "Rebuild Atheris with rpath. Follow the instructions in docs/FUZZING_GUIDE.md."
        exit 1
    else
        echo -e "${YELLOW}Warning: ABI check skipped${NC}"
        if [[ "$VERBOSE" == "true" ]]; then
            echo "$ABI_TEST"
        fi
    fi
fi

# Check 4: Basic fuzzing capability
echo -n "Fuzzing capability... "
FUZZ_TEST=$(uv run --group fuzzing python -c "
import atheris
import sys
def TestOneInput(data):
    pass
# Just verify we can set up fuzzing
atheris.Setup(['test'], TestOneInput)
print('OK')
" 2>&1)

if [[ "$FUZZ_TEST" == "OK" ]]; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    echo "Atheris is installed but cannot initialize fuzzing."
    exit 1
fi

echo ""
echo -e "${BOLD}============================================================${NC}"
echo -e "${GREEN}[OK]${NC} Atheris is ready for fuzzing."
echo ""
echo "Run fuzzing with:"
echo "  ./scripts/fuzz.sh --native"
echo "  ./scripts/fuzz.sh --native --time 60"
echo -e "${BOLD}============================================================${NC}"

exit 0
