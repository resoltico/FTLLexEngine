#!/usr/bin/env bash
# Version bump automation for FTLLexEngine
#
# Automates version bumping to reduce manual errors:
# 1. Validates current version format
# 2. Calculates new version based on bump type
# 3. Updates pyproject.toml
# 4. Refreshes package metadata
# 5. Verifies version propagation
#
# Usage:
#   ./scripts/bump-version.sh [major|minor|patch] [--prerelease LABEL]
#   ./scripts/bump-version.sh patch                    # 0.1.0 -> 0.1.1
#   ./scripts/bump-version.sh minor                    # 0.1.0 -> 0.2.0
#   ./scripts/bump-version.sh major                    # 0.1.0 -> 1.0.0
#   ./scripts/bump-version.sh minor --prerelease alpha # 0.1.0 -> 0.2.0-alpha
#   ./scripts/bump-version.sh patch --prerelease beta  # 0.1.0 -> 0.1.1-beta
#   ./scripts/bump-version.sh patch --finalize         # 0.1.1-beta -> 0.1.1

set -euo pipefail

# --- ASSUMPTIONS TESTER ---
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
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Script configuration
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Logging functions
log_info() {
    echo -e "${BLUE}[ INFO ]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[  OK  ]${NC} $*"
}

log_warn() {
    echo -e "${YELLOW}[ WARN ]${NC} $*"
}

log_error() {
    echo -e "${RED}[ FAIL ]${NC} $*"
}

# Change to project root
cd "$PROJECT_ROOT"

# Validate arguments
BUMP_TYPE="${1:-}"
PRERELEASE=""
FINALIZE=false

# Parse arguments
shift || true
while [[ $# -gt 0 ]]; do
    case $1 in
        --prerelease)
            if [[ -z "${2:-}" ]]; then
                log_error "--prerelease requires a label (e.g., alpha, beta, rc)"
                exit 1
            fi
            PRERELEASE="$2"
            shift 2
            ;;
        --finalize)
            FINALIZE=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

if [[ ! "$BUMP_TYPE" =~ ^(major|minor|patch)$ ]]; then
    log_error "Invalid or missing bump type"
    echo ""
    echo "Usage: $0 [major|minor|patch] [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --prerelease LABEL    Create pre-release version (alpha, beta, rc, etc.)"
    echo "  --finalize            Remove pre-release label"
    echo ""
    echo "Examples:"
    echo "  $0 patch              # Bug fixes (0.1.0 -> 0.1.1)"
    echo "  $0 minor              # New features (0.1.0 -> 0.2.0)"
    echo "  $0 major              # Breaking changes (0.1.0 -> 1.0.0)"
    echo "  $0 minor --prerelease alpha  # Pre-release (0.1.0 -> 0.2.0-alpha)"
    echo "  $0 patch --finalize   # Finalize (0.1.1-beta -> 0.1.1)"
    echo ""
    exit 1
fi

echo "=========================================="
echo "FTLLexEngine Version Bump Automation"
echo "=========================================="
echo ""

# Step 0: Check required dependencies
log_info "Validating required dependencies..."

if ! command -v python &> /dev/null; then
    log_error "Python not found in PATH"
    exit 1
fi

log_success "Required dependencies available: python"

# Step 0b: Check Python version (FTLLexEngine requires Python 3.13+)
log_info "Validating Python version..."

PYTHON_VERSION=$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')

if ! python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)' 2>/dev/null; then
    log_error "Python $PYTHON_VERSION detected. FTLLexEngine requires Python 3.13+"
    log_warn "Current Python: $PYTHON_VERSION"
    log_warn "Required: 3.13 or newer"
    exit 1
fi

log_success "Python version valid: $PYTHON_VERSION"

# Step 1: Extract current version from pyproject.toml
log_info "Extracting current version from pyproject.toml..."

CURRENT_VERSION=$(python <<EOF
import tomllib
from pathlib import Path

try:
    with open('pyproject.toml', 'rb') as f:
        data = tomllib.load(f)
        print(data['project']['version'])
except Exception as e:
    import sys
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
EOF
)

if [[ -z "$CURRENT_VERSION" ]]; then
    log_error "Failed to extract version from pyproject.toml"
    exit 1
fi

log_success "Current version: $CURRENT_VERSION"

# Step 2: Validate current version format
log_info "Validating current version format..."

# Improved regex: prevents trailing separators like "0.1.0-" or "0.1.0+"
# Pre-release: one or more alphanumeric identifiers separated by dots
# Build metadata: one or more alphanumeric identifiers separated by dots
if [[ ! "$CURRENT_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)*)?(\+[a-zA-Z0-9]+(\.[a-zA-Z0-9]+)*)?$ ]]; then
    log_error "Invalid semantic version format: $CURRENT_VERSION"
    log_warn "Expected: MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]"
    log_warn "Examples: 0.1.0, 1.0.0-alpha.1, 2.3.4+build.123"
    exit 1
fi

log_success "Version format valid"

# Step 3: Parse version and calculate new version
log_info "Calculating new version..."

# Extract base version (strip prerelease and build metadata)
BASE_VERSION="${CURRENT_VERSION%%-*}"
BASE_VERSION="${BASE_VERSION%%+*}"

IFS='.' read -r MAJOR MINOR PATCH <<< "$BASE_VERSION"

# Handle finalize mode (remove pre-release label)
if [[ "$FINALIZE" == true ]]; then
    if [[ "$CURRENT_VERSION" == "$BASE_VERSION" ]]; then
        log_error "Current version $CURRENT_VERSION has no pre-release label to remove"
        exit 1
    fi
    NEW_VERSION="$BASE_VERSION"
    echo ""
    echo "Finalizing version: $CURRENT_VERSION -> $NEW_VERSION"
    echo ""
else
    # Calculate new version based on bump type
    case "$BUMP_TYPE" in
        major)
            NEW_VERSION="$((MAJOR + 1)).0.0"
            ;;
        minor)
            NEW_VERSION="$MAJOR.$((MINOR + 1)).0"
            ;;
        patch)
            NEW_VERSION="$MAJOR.$MINOR.$((PATCH + 1))"
            ;;
    esac

    # Add pre-release label if specified
    if [[ -n "$PRERELEASE" ]]; then
        # Validate pre-release label format
        if [[ ! "$PRERELEASE" =~ ^[a-zA-Z0-9.]+$ ]]; then
            log_error "Invalid pre-release label: $PRERELEASE"
            log_warn "Pre-release label must contain only alphanumeric characters and dots"
            exit 1
        fi
        NEW_VERSION="$NEW_VERSION-$PRERELEASE"
    fi

    echo ""
    echo "Version bump: $CURRENT_VERSION -> $NEW_VERSION"
    echo ""
fi

# Step 4: Confirm with user
read -p "Proceed with version bump? [y/N] " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_warn "Version bump cancelled by user"
    exit 0
fi

# Step 5: Update pyproject.toml
log_info "Updating pyproject.toml..."

# Use Python (already a hard dependency) for cross-platform in-place file editing (no backup files)
if ! python <<EOF
import sys
from pathlib import Path

current = "$CURRENT_VERSION"
new = "$NEW_VERSION"
pyproject = Path("pyproject.toml")

try:
    content = pyproject.read_text(encoding="utf-8")
    # Simple string replacement - no regex needed, exact match
    updated = content.replace(f'version = "{current}"', f'version = "{new}"')

    if content == updated:
        print(f"ERROR: Version string 'version = \"{current}\"' not found in pyproject.toml", file=sys.stderr)
        sys.exit(1)

    pyproject.write_text(updated, encoding="utf-8")
    sys.exit(0)
except Exception as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
EOF
then
    log_error "Failed to update pyproject.toml"
    exit 1
fi

# Verify that the version was actually updated in pyproject.toml
if ! grep -q "version = \"$NEW_VERSION\"" pyproject.toml; then
    log_error "Version update verification failed!"
    echo ""
    echo "  Expected to find: version = \"$NEW_VERSION\""
    echo "  In file: pyproject.toml"
    echo ""
    log_warn "The perl substitution may have failed silently"
    log_warn "Manual inspection required"
    exit 1
fi

log_success "pyproject.toml updated (verified)"

log_info "Refreshing package metadata (uv sync)..."

# Refresh environment
if ! uv sync > /dev/null 2>&1; then
    log_error "Failed to refresh package metadata"
    log_warn "Reverting pyproject.toml..."

    # Revert changes using Python (cross-platform, no backup files)
    python <<EOF
import sys
from pathlib import Path

current = "$CURRENT_VERSION"
new = "$NEW_VERSION"
pyproject = Path("pyproject.toml")

try:
    content = pyproject.read_text(encoding="utf-8")
    # Revert: new -> current
    reverted = content.replace(f'version = "{new}"', f'version = "{current}"')
    pyproject.write_text(reverted, encoding="utf-8")
except Exception as e:
    print(f"ERROR during revert: {e}", file=sys.stderr)
    sys.exit(1)
EOF

    exit 1
fi

log_success "Package metadata refreshed"

# Step 7: Verify version propagation
log_info "Verifying version propagation..."

RUNTIME_VERSION=$(python -c "import ftllexengine; print(ftllexengine.__version__)" 2>&1)

if [[ "$RUNTIME_VERSION" != "$NEW_VERSION" ]]; then
    log_error "Version mismatch after update!"
    echo ""
    echo "  Expected: $NEW_VERSION"
    echo "  Got:      $RUNTIME_VERSION"
    echo ""
    log_warn "This indicates metadata refresh failed"
    exit 1
fi

log_success "Version successfully propagated to __version__"

# Step 8: Display next steps
echo ""
echo "=========================================="
echo "Version Bump Complete"
echo "=========================================="
echo ""
echo "Old version: $CURRENT_VERSION"
echo "New version: $NEW_VERSION"
echo ""
echo "Next steps:"
echo ""
echo "1. Update CHANGELOG.md:"
echo "   ${GREEN}vim CHANGELOG.md${NC}"
echo ""
echo "   Add section:"
echo "   ## [$NEW_VERSION] - $(date +%Y-%m-%d)"
echo "   ### Added"
echo "   - New feature descriptions..."
echo "   ### Fixed"
echo "   - Bug fix descriptions..."
echo ""
echo "2. Review changes:"
echo "   ${GREEN}git diff pyproject.toml${NC}"
echo ""
echo "3. Commit changes:"
echo "   ${GREEN}git add pyproject.toml CHANGELOG.md${NC}"
echo "   ${GREEN}git commit -m \"Bump version to $NEW_VERSION\"${NC}"
echo ""
echo "4. Run release script:"
echo "   ${GREEN}uv run scripts/release.sh${NC}"
echo ""

log_success "Version bump automation complete!"
