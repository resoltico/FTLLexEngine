#!/usr/bin/env python3
# @lint-plugin: VersionSync
"""Validate version consistency across all project artifacts.

Ensures pyproject.toml is the single source of truth for version information,
and that all documentation and metadata stay synchronized.

CHECKS PERFORMED:
    CRITICAL (fail build):
    1. Package __version__ matches pyproject.toml
    2. Version follows semantic versioning (MAJOR.MINOR.PATCH)
    3. Version is not a development placeholder
    4. Version components are non-negative integers

    DOCUMENTATION (fail build):
    5. All docs/DOC_*.md frontmatter has correct project_version
    6. docs/QUICK_REFERENCE.md footer has correct version

    INFORMATIONAL (warn only):
    7. CHANGELOG.md mentions current version
    8. CHANGELOG.md has version link at bottom

Architecture:
    - Uses tomllib (Python 3.11+) for pyproject.toml parsing
    - Uses importlib.metadata for installed package version
    - Scans documentation files for version references
    - Provides detailed error messages with resolution steps

Exit Codes:
    0: All checks passed
    1: Critical version mismatch or invalid version
    2: Documentation version mismatch
    3: Configuration error (missing files/dependencies)

Python 3.13+. No external dependencies.
"""

from __future__ import annotations

import re
import sys
import tomllib
from pathlib import Path
from typing import NamedTuple

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# ANSI color codes (disabled if NO_COLOR environment variable is set)
import os

NO_COLOR = os.environ.get("NO_COLOR", "") == "1"

class Colors:
    """ANSI color codes for terminal output."""
    RED = "" if NO_COLOR else "\033[31m"
    GREEN = "" if NO_COLOR else "\033[32m"
    YELLOW = "" if NO_COLOR else "\033[33m"
    BLUE = "" if NO_COLOR else "\033[34m"
    CYAN = "" if NO_COLOR else "\033[36m"
    BOLD = "" if NO_COLOR else "\033[1m"
    RESET = "" if NO_COLOR else "\033[0m"


class CheckResult(NamedTuple):
    """Result of a single validation check."""
    name: str
    passed: bool
    message: str
    is_critical: bool = True  # If False, only warns


# ==============================================================================
# VERSION EXTRACTION
# ==============================================================================

def get_pyproject_version(root: Path) -> str | None:
    """Extract version from pyproject.toml (single source of truth).

    Args:
        root: Project root directory

    Returns:
        Version string or None if not found
    """
    pyproject_path = root / "pyproject.toml"
    if not pyproject_path.exists():
        return None

    try:
        with pyproject_path.open("rb") as f:
            data = tomllib.load(f)
        return data.get("project", {}).get("version")
    except Exception:
        return None


def get_package_version() -> str | None:
    """Get installed package version via importlib.metadata.

    Returns:
        Version string or None if package not installed
    """
    try:
        from importlib.metadata import version
        return version("ftllexengine")
    except Exception:
        return None


def get_runtime_version() -> str | None:
    """Get version by importing the package directly.

    Returns:
        Version string or None if import fails
    """
    try:
        import ftllexengine
        return ftllexengine.__version__
    except Exception:
        return None


# ==============================================================================
# VALIDATION CHECKS
# ==============================================================================

def check_version_matches_pyproject(root: Path) -> CheckResult:
    """CRITICAL: __version__ must match pyproject.toml."""
    pyproject_version = get_pyproject_version(root)
    runtime_version = get_runtime_version()

    if pyproject_version is None:
        return CheckResult(
            name="version_matches_pyproject",
            passed=False,
            message="Cannot read version from pyproject.toml",
            is_critical=True,
        )

    if runtime_version is None:
        return CheckResult(
            name="version_matches_pyproject",
            passed=False,
            message=(
                f"Package not installed or import failed.\n"
                f"  pyproject.toml: {pyproject_version}\n"
                f"  __version__:    <not available>\n"
                f"  Resolution: Run 'pip install -e .'"
            ),
            is_critical=True,
        )

    if runtime_version != pyproject_version:
        return CheckResult(
            name="version_matches_pyproject",
            passed=False,
            message=(
                f"Version mismatch detected!\n"
                f"  pyproject.toml: {pyproject_version}\n"
                f"  __version__:    {runtime_version}\n"
                f"  Resolution: Run 'pip install -e .' to refresh metadata"
            ),
            is_critical=True,
        )

    return CheckResult(
        name="version_matches_pyproject",
        passed=True,
        message=f"Version {pyproject_version} synchronized",
        is_critical=True,
    )


def check_valid_semver(root: Path) -> CheckResult:
    """Version must follow semantic versioning specification."""
    version = get_pyproject_version(root)

    if version is None:
        return CheckResult(
            name="valid_semver",
            passed=False,
            message="Cannot read version from pyproject.toml",
            is_critical=True,
        )

    # Semantic versioning pattern: MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]
    semver_pattern = (
        r"^\d+\.\d+\.\d+"  # MAJOR.MINOR.PATCH (required)
        r"(?:-[a-zA-Z0-9.]+)?"  # -PRERELEASE (optional)
        r"(?:\+[a-zA-Z0-9.]+)?$"  # +BUILD (optional)
    )

    if not re.match(semver_pattern, version):
        return CheckResult(
            name="valid_semver",
            passed=False,
            message=(
                f"Invalid version format: {version!r}\n"
                f"  Expected: MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]\n"
                f"  Examples: 1.0.0, 2.3.4-alpha, 1.0.0+build.123"
            ),
            is_critical=True,
        )

    return CheckResult(
        name="valid_semver",
        passed=True,
        message=f"Version {version} is valid semver",
        is_critical=True,
    )


def check_not_placeholder(root: Path) -> CheckResult:
    """Version must not be a development placeholder."""
    version = get_pyproject_version(root)

    if version is None:
        return CheckResult(
            name="not_placeholder",
            passed=False,
            message="Cannot read version from pyproject.toml",
            is_critical=True,
        )

    invalid_placeholders = [
        "0.0.0+dev",
        "0.0.0+unknown",
        "0.0.0.dev0",
        "unknown",
        "dev",
    ]

    if version in invalid_placeholders:
        return CheckResult(
            name="not_placeholder",
            passed=False,
            message=(
                f"Development placeholder detected: {version!r}\n"
                f"  Set a real version in pyproject.toml before release"
            ),
            is_critical=True,
        )

    return CheckResult(
        name="not_placeholder",
        passed=True,
        message="Version is not a placeholder",
        is_critical=True,
    )


def check_version_components(root: Path) -> CheckResult:
    """Version MAJOR.MINOR.PATCH components must be non-negative integers."""
    version = get_pyproject_version(root)

    if version is None:
        return CheckResult(
            name="version_components",
            passed=False,
            message="Cannot read version from pyproject.toml",
            is_critical=True,
        )

    # Extract base version (before - or +)
    base_version = version.split("-")[0].split("+")[0]
    parts = base_version.split(".")

    if len(parts) != 3:
        return CheckResult(
            name="version_components",
            passed=False,
            message=(
                f"Version must have exactly 3 components (MAJOR.MINOR.PATCH)\n"
                f"  Got {len(parts)} components: {version!r}"
            ),
            is_critical=True,
        )

    for i, (name, value) in enumerate(zip(["MAJOR", "MINOR", "PATCH"], parts)):
        if not value.isdigit():
            return CheckResult(
                name="version_components",
                passed=False,
                message=f"{name} component must be integer, got {value!r}",
                is_critical=True,
            )
        if int(value) < 0:
            return CheckResult(
                name="version_components",
                passed=False,
                message=f"{name} component must be non-negative, got {value}",
                is_critical=True,
            )

    return CheckResult(
        name="version_components",
        passed=True,
        message=f"Version components valid: {'.'.join(parts)}",
        is_critical=True,
    )


def check_doc_frontmatter_versions(root: Path) -> CheckResult:
    """All docs/DOC_*.md files must have correct project_version in frontmatter."""
    version = get_pyproject_version(root)

    if version is None:
        return CheckResult(
            name="doc_frontmatter_versions",
            passed=False,
            message="Cannot read version from pyproject.toml",
            is_critical=True,
        )

    docs_dir = root / "docs"
    if not docs_dir.exists():
        return CheckResult(
            name="doc_frontmatter_versions",
            passed=True,
            message="No docs/ directory found (skipped)",
            is_critical=True,
        )

    doc_files = list(docs_dir.glob("DOC_*.md"))
    if not doc_files:
        return CheckResult(
            name="doc_frontmatter_versions",
            passed=True,
            message="No DOC_*.md files found (skipped)",
            is_critical=True,
        )

    mismatched = []
    checked = 0

    # Pattern to extract project_version from YAML frontmatter
    frontmatter_pattern = re.compile(
        r"^---\s*\n(.*?)\n---",
        re.DOTALL
    )
    version_pattern = re.compile(r"project_version:\s*(\S+)")

    for doc_file in doc_files:
        try:
            content = doc_file.read_text(encoding="utf-8")
            frontmatter_match = frontmatter_pattern.match(content)

            if frontmatter_match:
                frontmatter = frontmatter_match.group(1)
                version_match = version_pattern.search(frontmatter)

                if version_match:
                    doc_version = version_match.group(1)
                    checked += 1

                    if doc_version != version:
                        mismatched.append(
                            f"  {doc_file.name}: {doc_version} (expected {version})"
                        )
        except Exception as e:
            mismatched.append(f"  {doc_file.name}: Error reading file - {e}")

    if mismatched:
        return CheckResult(
            name="doc_frontmatter_versions",
            passed=False,
            message=(
                f"Documentation version mismatch:\n" + "\n".join(mismatched) +
                f"\n  Resolution: Update project_version in frontmatter"
            ),
            is_critical=True,  # Documentation sync is critical
        )

    return CheckResult(
        name="doc_frontmatter_versions",
        passed=True,
        message=f"All {checked} DOC_*.md files have version {version}",
        is_critical=True,
    )


def check_quick_reference_version(root: Path) -> CheckResult:
    """docs/QUICK_REFERENCE.md footer must have correct version."""
    version = get_pyproject_version(root)

    if version is None:
        return CheckResult(
            name="quick_reference_version",
            passed=False,
            message="Cannot read version from pyproject.toml",
            is_critical=True,
        )

    qr_path = root / "docs" / "QUICK_REFERENCE.md"
    if not qr_path.exists():
        return CheckResult(
            name="quick_reference_version",
            passed=True,
            message="QUICK_REFERENCE.md not found (skipped)",
            is_critical=True,
        )

    try:
        content = qr_path.read_text(encoding="utf-8")

        # Look for version in footer pattern: **FTLLexEngine Version**: X.Y.Z
        version_pattern = re.compile(
            r"\*\*FTLLexEngine Version\*\*:\s*(\S+)"
        )
        match = version_pattern.search(content)

        if not match:
            return CheckResult(
                name="quick_reference_version",
                passed=True,  # No version footer is OK
                message="No version footer in QUICK_REFERENCE.md (skipped)",
                is_critical=True,
            )

        qr_version = match.group(1)
        if qr_version != version:
            return CheckResult(
                name="quick_reference_version",
                passed=False,
                message=(
                    f"QUICK_REFERENCE.md version mismatch:\n"
                    f"  Found: {qr_version}\n"
                    f"  Expected: {version}\n"
                    f"  Resolution: Update footer in QUICK_REFERENCE.md"
                ),
                is_critical=True,
            )

        return CheckResult(
            name="quick_reference_version",
            passed=True,
            message=f"QUICK_REFERENCE.md has version {version}",
            is_critical=True,
        )

    except Exception as e:
        return CheckResult(
            name="quick_reference_version",
            passed=False,
            message=f"Error reading QUICK_REFERENCE.md: {e}",
            is_critical=True,
        )


def check_changelog_mentions_version(root: Path) -> CheckResult:
    """CHANGELOG.md should document current version (informational)."""
    version = get_pyproject_version(root)

    if version is None:
        return CheckResult(
            name="changelog_mentions_version",
            passed=True,
            message="Cannot read version from pyproject.toml (skipped)",
            is_critical=False,
        )

    # Skip for development placeholders
    if "+dev" in version or "+unknown" in version:
        return CheckResult(
            name="changelog_mentions_version",
            passed=True,
            message="Development version, CHANGELOG check skipped",
            is_critical=False,
        )

    changelog_path = root / "CHANGELOG.md"
    if not changelog_path.exists():
        return CheckResult(
            name="changelog_mentions_version",
            passed=True,
            message="CHANGELOG.md not found (skipped)",
            is_critical=False,
        )

    try:
        content = changelog_path.read_text(encoding="utf-8")

        # Look for version in various formats
        version_patterns = [
            f"## [{version}]",  # Markdown heading with link
            f"## {version}",  # Markdown heading
            f"[{version}]:",  # Version link at bottom
        ]

        if any(pattern in content for pattern in version_patterns):
            return CheckResult(
                name="changelog_mentions_version",
                passed=True,
                message=f"CHANGELOG.md documents version {version}",
                is_critical=False,
            )

        return CheckResult(
            name="changelog_mentions_version",
            passed=False,
            message=(
                f"CHANGELOG.md does not mention version {version}\n"
                f"  Consider adding a ## [{version}] section before release"
            ),
            is_critical=False,  # Warning only
        )

    except Exception as e:
        return CheckResult(
            name="changelog_mentions_version",
            passed=True,
            message=f"Error reading CHANGELOG.md: {e} (skipped)",
            is_critical=False,
        )


def check_changelog_has_version_link(root: Path) -> CheckResult:
    """CHANGELOG.md should have version link at bottom (informational)."""
    version = get_pyproject_version(root)

    if version is None:
        return CheckResult(
            name="changelog_version_link",
            passed=True,
            message="Cannot read version from pyproject.toml (skipped)",
            is_critical=False,
        )

    # Skip for development placeholders
    if "+dev" in version or "+unknown" in version:
        return CheckResult(
            name="changelog_version_link",
            passed=True,
            message="Development version, link check skipped",
            is_critical=False,
        )

    changelog_path = root / "CHANGELOG.md"
    if not changelog_path.exists():
        return CheckResult(
            name="changelog_version_link",
            passed=True,
            message="CHANGELOG.md not found (skipped)",
            is_critical=False,
        )

    try:
        content = changelog_path.read_text(encoding="utf-8")

        # Look for version link: [X.Y.Z]: https://...
        link_pattern = f"[{version}]:"

        if link_pattern in content:
            return CheckResult(
                name="changelog_version_link",
                passed=True,
                message=f"CHANGELOG.md has link for version {version}",
                is_critical=False,
            )

        return CheckResult(
            name="changelog_version_link",
            passed=False,
            message=(
                f"CHANGELOG.md missing link for version {version}\n"
                f"  Add: [{version}]: https://github.com/.../releases/tag/v{version}"
            ),
            is_critical=False,  # Warning only
        )

    except Exception:
        return CheckResult(
            name="changelog_version_link",
            passed=True,
            message="Error reading CHANGELOG.md (skipped)",
            is_critical=False,
        )


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

def detect_project_context(root: Path) -> tuple[bool, str]:
    """Detect if we're running in FTLLexEngine project.

    Returns:
        (is_ftllexengine, project_name)
    """
    # Check for other project markers first
    if (root / "src" / "finso2000").exists():
        return (False, "finso2000")

    # Check for FTLLexEngine markers
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text(encoding="utf-8")
        if 'name = "ftllexengine"' in content or 'name="ftllexengine"' in content:
            return (True, "ftllexengine")

    if (root / "src" / "ftllexengine").exists():
        return (True, "ftllexengine")

    return (False, "unknown")


def main() -> int:
    """Run all version consistency checks.

    Returns:
        0: All checks passed
        1: Critical failure
        2: Documentation failure
        3: Configuration error
    """
    root = Path(__file__).parent.parent

    # Context detection
    is_ftllexengine, project_name = detect_project_context(root)

    if not is_ftllexengine:
        print("[SKIP] validate_version.py is for FTLLexEngine project")
        print(f"       Current project: {project_name}")
        return 0

    # Get canonical version for header
    canonical_version = get_pyproject_version(root) or "unknown"

    print(f"{Colors.BOLD}{Colors.CYAN}=== Version Consistency Check ==={Colors.RESET}")
    print(f"Canonical version (pyproject.toml): {Colors.BOLD}{canonical_version}{Colors.RESET}\n")

    # Run all checks
    checks = [
        # Critical checks
        check_version_matches_pyproject(root),
        check_valid_semver(root),
        check_not_placeholder(root),
        check_version_components(root),
        # Documentation checks
        check_doc_frontmatter_versions(root),
        check_quick_reference_version(root),
        # Informational checks
        check_changelog_mentions_version(root),
        check_changelog_has_version_link(root),
    ]

    # Categorize results
    critical_failures = []
    doc_failures = []
    warnings = []
    passed = []

    for result in checks:
        if result.passed:
            passed.append(result)
        elif result.is_critical:
            # Distinguish between critical and documentation failures
            if "doc" in result.name or "quick_reference" in result.name:
                doc_failures.append(result)
            else:
                critical_failures.append(result)
        else:
            warnings.append(result)

    # Print results
    print(f"{Colors.BOLD}Checks:{Colors.RESET}")

    for result in checks:
        if result.passed:
            status = f"{Colors.GREEN}[PASS]{Colors.RESET}"
        elif result.is_critical:
            status = f"{Colors.RED}[FAIL]{Colors.RESET}"
        else:
            status = f"{Colors.YELLOW}[WARN]{Colors.RESET}"

        print(f"  {status} {result.name}")

        # Show details for failures/warnings
        if not result.passed:
            for line in result.message.split("\n"):
                print(f"         {line}")

    # Summary
    print()
    total = len(checks)
    passed_count = len(passed)

    if critical_failures:
        print(f"{Colors.RED}{Colors.BOLD}[FAIL]{Colors.RESET} "
              f"{len(critical_failures)} critical failure(s), "
              f"{passed_count}/{total} checks passed")
        return 1

    if doc_failures:
        print(f"{Colors.RED}{Colors.BOLD}[FAIL]{Colors.RESET} "
              f"{len(doc_failures)} documentation sync failure(s), "
              f"{passed_count}/{total} checks passed")
        return 2

    if warnings:
        print(f"{Colors.YELLOW}{Colors.BOLD}[WARN]{Colors.RESET} "
              f"{len(warnings)} warning(s), "
              f"{passed_count}/{total} checks passed")
        # Warnings don't fail the build
        return 0

    print(f"{Colors.GREEN}{Colors.BOLD}[OK]{Colors.RESET} "
          f"All {total} version checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
