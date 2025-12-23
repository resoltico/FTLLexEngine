#!/usr/bin/env bash
# ==============================================================================
# release.sh - Release Automation Script
# ==============================================================================
#
# PURPOSE:
#   Automates the release process by:
#   1. Validating version consistency across all sources
#   2. Running comprehensive test suite
#   3. Creating git tag with proper naming
#   4. Providing push commands for release
#
# USAGE:
#   ./scripts/release.sh           # Interactive mode with validation
#   ./scripts/release.sh --help    # Show usage information
#   ./scripts/release.sh --dry-run # Validate only, no git operations
#
# ==============================================================================

set -euo pipefail

# --- ASSUMPTIONS TESTER (Platinum Standard) ---
pre_flight_diagnostics() {
    # Output Architecture Directive (OAD) for cross-agent legibility
    # @FORMAT: [STATUS:8][COMPONENT:20][MESSAGE]
    echo "[  OK  ] Diagnostic Schema  : fixed-width/padded-tags (announcing OAD)"

    # Environment Guard (Enforce uv run context)
    if [[ -z "${VIRTUAL_ENV:-}" ]]; then
        echo "[ FAIL ] Environment         : NOT UV-MANAGED"
        echo "[ INFO ] Policy              : This script must be run via 'uv run'"
        echo "[ INFO ] Command             : uv run scripts/$(basename "$0")"
        exit 1
    fi

    echo "[  OK  ] Environment         : Valid uv context detected"
    echo "[ INFO ] Python Version      : $(python --version)"
}
pre_flight_diagnostics

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper for printing headers
print_header() {
    echo ""
    echo -e "${BLUE}=================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}=================================================================${NC}"
}

# Logging functions
log_info() { echo -e "${BLUE}[ INFO ]${NC} $*"; }
log_success() { echo -e "${GREEN}[  OK  ]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[ WARN ]${NC} $*"; }
log_error() { echo -e "${RED}[ FAIL ]${NC} $*"; }

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Parse command line arguments
DRY_RUN=false
SKIP_TESTS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            cat <<EOF
Release Automation Script

Usage: ./scripts/release.sh [OPTIONS]

OPTIONS:
    --help, -h       Show this help message
    --dry-run        Validate only, no git operations
    --skip-tests     Skip test suite (not recommended)

WORKFLOW:
    1. Validates version in pyproject.toml matches __version__
    2. Checks git working directory is clean
    3. Runs full test suite (unless --skip-tests)
    4. Creates git tag: v{VERSION}
    5. Displays push commands
EOF
            exit 0
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check if running from project root
cd "$PROJECT_ROOT"

print_header "RELEASE AUTOMATION"

# Check required dependencies
log_info "Checking required dependencies..."

if ! command -v python &> /dev/null; then
    log_error "Python not found in PATH"
    exit 1
fi

# Detect package name
PACKAGE_NAME=$(find src -mindepth 1 -maxdepth 1 -type d | head -n 1 | xargs basename)
if [ -z "$PACKAGE_NAME" ]; then
    log_error "Could not detect package in src/"
    exit 1
fi
log_info "Detected package: $PACKAGE_NAME"

# Step 1: Extract version from pyproject.toml
log_info "Extracting version from pyproject.toml..."

PYPROJECT_VERSION=$(python <<EOF
import sys
import tomllib
try:
    with open('pyproject.toml', 'rb') as f:
        data = tomllib.load(f)
        print(data['project']['version'])
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    exit(1)
EOF
)

if [[ -z "$PYPROJECT_VERSION" ]]; then
    log_error "Failed to extract version from pyproject.toml"
    exit 1
fi

log_success "pyproject.toml version: $PYPROJECT_VERSION"

# Step 2: Extract runtime __version__
log_info "Extracting runtime __version__..."

RUNTIME_VERSION=$(python -c "import $PACKAGE_NAME; print($PACKAGE_NAME.__version__)" 2>&1)
exit_code=$?

if [[ $exit_code -ne 0 ]]; then
    log_error "Failed to import $PACKAGE_NAME"
    echo "$RUNTIME_VERSION"
    log_warn "Run 'uv sync' to synchronize environment"
    exit 1
fi

log_success "Runtime __version__: $RUNTIME_VERSION"

# Step 3: Check for development placeholder
if [[ "$RUNTIME_VERSION" == "0.0.0+dev" ]] || [[ "$RUNTIME_VERSION" == "0.0.0+unknown" ]]; then
    log_error "Version is development placeholder: $RUNTIME_VERSION"
    exit 1
fi

# Step 4: Validate version consistency
if [[ "$PYPROJECT_VERSION" != "$RUNTIME_VERSION" ]]; then
    log_error "Version mismatch detected!"
    echo "  pyproject.toml:  $PYPROJECT_VERSION"
    echo "  __version__:     $RUNTIME_VERSION"
    exit 1
fi

log_success "Version consistency validated"

# Step 5: Validate semantic versioning format
if ! echo "$RUNTIME_VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)*)?(\+[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)*)?$'; then
    log_error "Invalid semantic version format: $RUNTIME_VERSION"
    exit 1
fi

log_success "Semantic versioning format valid"

# Step 6: Check git working directory status
log_info "Checking git working directory..."

if ! git diff-index --quiet HEAD -- 2>/dev/null; then
    log_error "Git working directory is not clean"
    git status --short
    exit 1
fi

log_success "Git working directory is clean"

# Step 7: Validate CHANGELOG.md
log_info "Validating CHANGELOG.md..."

if [[ ! -f "CHANGELOG.md" ]]; then
    log_error "CHANGELOG.md not found"
    exit 1
fi

RUNTIME_VERSION_ESCAPED=$(printf '%s\n' "$RUNTIME_VERSION" | sed 's/[.+]/\\&/g')

if ! grep -qE "^## (\[$RUNTIME_VERSION_ESCAPED\]|$RUNTIME_VERSION_ESCAPED)" CHANGELOG.md; then
    log_error "CHANGELOG.md does not document version $RUNTIME_VERSION"
    exit 1
fi

log_success "CHANGELOG.md documents version $RUNTIME_VERSION"

# Step 8: Check PyPI (if curl available)
if command -v curl &> /dev/null; then
    log_info "Checking PyPI..."
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://pypi.org/pypi/$PACKAGE_NAME/$RUNTIME_VERSION/json" 2>/dev/null || echo "000")

    if [[ "$HTTP_CODE" == "200" ]]; then
        log_error "Version $RUNTIME_VERSION already exists on PyPI"
        exit 1
    elif [[ "$HTTP_CODE" == "404" ]]; then
        log_success "Version $RUNTIME_VERSION not found on PyPI (ready to publish)"
    else
        log_warn "Could not check PyPI (HTTP $HTTP_CODE). Proceeding..."
    fi
fi

# Step 9: Validate git tag format
TAG_NAME="v$RUNTIME_VERSION"
if [[ ! "$TAG_NAME" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9.]+)?(\+[a-zA-Z0-9.]+)?$ ]]; then
    log_error "Invalid tag format: $TAG_NAME"
    exit 1
fi

if git rev-parse "$TAG_NAME" >/dev/null 2>&1; then
    log_error "Git tag $TAG_NAME already exists"
    exit 1
fi

log_success "Tag $TAG_NAME is valid and unique"

# Step 10: Run test suite
if [[ "$SKIP_TESTS" == "false" ]]; then
    print_header "RUNNING QUALITY CHECKS"
    
    log_info "Running lint.sh..."
    if ! uv run scripts/lint.sh --ci; then
        log_error "Linting failed"
        exit 1
    fi
    
    log_info "Running test.sh..."
    if ! uv run scripts/test.sh --ci; then
        log_error "Tests failed"
        exit 1
    fi
    
    log_success "All checks passed"
else
    log_warn "Skipping test suite"
fi

# Step 11: Create git tag
print_header "RELEASE SUMMARY"
echo "Version:  $RUNTIME_VERSION"
echo "Tag name: $TAG_NAME"
echo ""

if [[ "$DRY_RUN" == "true" ]]; then
    log_info "Dry run mode - no git operations performed"
    exit 0
fi

read -p "Create release tag $TAG_NAME? [y/N] " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_warn "Release cancelled by user"
    exit 0
fi

log_info "Creating git tag $TAG_NAME..."
if ! git tag -a "$TAG_NAME" -m "Release version $RUNTIME_VERSION"; then
    log_error "Failed to create git tag"
    exit 1
fi

log_success "Git tag $TAG_NAME created successfully"

print_header "NEXT STEPS"

REPO_URL=$(git config --get remote.origin.url 2>/dev/null || echo "")
if [[ -n "$REPO_URL" ]]; then
    REPO_PATH=$(echo "$REPO_URL" | sed -E 's#^(https?://|git@)##' | sed -E 's#:#/#' | sed 's#\.git$##' | sed 's#github\.com/##')
    GITHUB_BASE="https://github.com/$REPO_PATH"
else
    GITHUB_BASE="https://github.com/resoltico/$PACKAGE_NAME"
fi

echo "1. Push tag to remote:"
echo -e "   ${GREEN}git push origin main --tags${NC}"
echo ""
echo "2. Create GitHub Release to trigger automatic PyPI publishing:"
echo -e "   ${GREEN}$GITHUB_BASE/releases/new?tag=$TAG_NAME${NC}"
echo ""
echo "3. Verify publication at:"
echo "   https://pypi.org/project/$PACKAGE_NAME/"
echo ""
