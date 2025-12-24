#!/usr/bin/env bash
# Changelog extraction script for FTLLexEngine
#
# Extracts changelog section for a specific version from CHANGELOG.md
# Useful for creating GitHub release descriptions
#
# Usage:
#   ./scripts/extract-changelog.sh [VERSION]
#   ./scripts/extract-changelog.sh          # Uses current package version
#   ./scripts/extract-changelog.sh 0.2.0    # Specific version

set -euo pipefail

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
    echo -e "${BLUE}[INFO]${NC} $*" >&2
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $*" >&2
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $*" >&2
}

log_error() {
    echo -e "${RED}[FAIL]${NC} $*" >&2
}

# Change to project root
cd "$PROJECT_ROOT"

# Determine version to extract
if [[ $# -eq 0 ]]; then
    # No argument provided - use current package version
    log_info "No version specified, using current package version..."

    VERSION=$(python -c "import ftllexengine; print(ftllexengine.__version__)" 2>/dev/null)

    if [[ -z "$VERSION" || "$VERSION" == "0.0.0+dev" || "$VERSION" == "0.0.0+unknown" ]]; then
        log_error "Failed to determine package version"
        log_warn "Run 'uv sync' or specify version explicitly"
        echo ""
        echo "Usage: $0 [VERSION]"
        exit 1
    fi

    log_info "Using version: $VERSION"
else
    VERSION="$1"
    log_info "Extracting changelog for version: $VERSION"
fi

# Check if CHANGELOG.md exists
if [[ ! -f "CHANGELOG.md" ]]; then
    log_error "CHANGELOG.md not found"
    exit 1
fi

# Extract changelog section for the specified version
# Accepts multiple heading formats:
# - ## [0.1.0] - 2024-01-01
# - ## 0.1.0 - 2024-01-01
# - ## [0.1.0]
# - ## 0.1.0

log_info "Extracting changelog section..." >&2

# Use awk to extract content between version heading and next heading
CHANGELOG=$(awk -v version="$VERSION" '
    # Match various version heading formats
    /^## \['"$VERSION"'\]/ || /^## '"$VERSION"'/ {
        found=1
        # Skip the heading line itself
        next
    }
    # Stop when we hit the next heading
    found && /^## / {
        exit
    }
    # Print lines while in the version section
    found {
        print
    }
' CHANGELOG.md)

# Check if anything was found
if [[ -z "$CHANGELOG" ]]; then
    log_error "Version $VERSION not found in CHANGELOG.md"
    echo "" >&2
    log_warn "Available versions:" >&2
    grep -E "^## " CHANGELOG.md | head -10 >&2
    echo "" >&2
    exit 1
fi

# Remove leading/trailing blank lines
CHANGELOG=$(echo "$CHANGELOG" | sed -e :a -e '/./,$!d;/^\n*$/{$d;N;};/\n$/ba')

log_success "Changelog extracted for version $VERSION" >&2

# Output changelog to stdout (without color codes for piping)
echo "$CHANGELOG"

# Provide helpful commands
echo "" >&2
echo "========================================" >&2
echo "Changelog for version $VERSION" >&2
echo "========================================" >&2
echo "" >&2
log_info "To copy to clipboard (macOS):" >&2
echo "  $0 $VERSION | pbcopy" >&2
echo "" >&2
log_info "To create GitHub release:" >&2
echo "  https://github.com/resoltico/ftllexengine/releases/new?tag=v$VERSION" >&2
echo "" >&2
log_info "To save to file:" >&2
echo "  $0 $VERSION > release-notes-$VERSION.md" >&2
echo "" >&2
