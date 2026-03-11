#!/usr/bin/env python3
# @lint-plugin: VersionSync
"""Validate version consistency across all project artifacts.

Ensures pyproject.toml is the single source of truth for version information,
and that all documentation and metadata stay synchronized.

PHILOSOPHY:
    One source of truth (pyproject.toml) should deterministically propagate
    to every artifact that embeds a version string.  Any divergence is a bug
    waiting to mislead a user.  This script makes divergence loud, not silent.

CHECKS PERFORMED:
    CRITICAL (exit 1 — fail build):
    1. Runtime __version__ matches pyproject.toml                [version_sync]
    2. Version follows semantic versioning (MAJOR.MINOR.PATCH)   [semver]
    3. Version is not a development placeholder                  [not_placeholder]

    DOCUMENTATION (exit 2 — fail build):
    4. All docs/DOC_*.md frontmatter has correct project_version [doc_frontmatter]
    5. docs/QUICK_REFERENCE.md footer has correct version        [quick_reference]
    6. docs/TERMINOLOGY.md footer has correct version            [terminology]

    INFORMATIONAL (exit 0 — warn only):
    7. CHANGELOG.md mentions current version                     [changelog_entry]
    8. CHANGELOG.md has version link at bottom                   [changelog_link]

NOTES ON VACUOUS PASSES:
    Checks 4-6 are "if present, must be correct."  If a doc file does not
    exist, or does not contain the version field/footer, the check passes and
    reports "(skipped)".  This is intentional: the checks activate as the
    project grows, without requiring maintenance of this script.

ARCHITECTURE:
    - tomllib (Python 3.11+ stdlib) for pyproject.toml parsing
    - importlib.metadata for installed package version
    - pathlib for all file I/O
    - Project-agnostic: project name is read from pyproject.toml [project].name

EXIT CODES:
    0: All checks passed (warnings do not block)
    1: Critical version mismatch or invalid version format
    2: Documentation version mismatch
    3: Configuration error (missing pyproject.toml or unreadable)

Python 3.13+.  No external dependencies.
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path
from typing import Any, NamedTuple

# ==============================================================================
# CONFIGURATION
# ==============================================================================

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


# Severity levels — explicit enum avoids the bool-confusion of the old is_critical field.
SEVERITY_CRITICAL = "critical"  # exit 1
SEVERITY_DOC = "doc"  # exit 2
SEVERITY_WARNING = "warning"  # exit 0 (informational)


class CheckResult(NamedTuple):
    """Result of a single validation check."""

    name: str
    passed: bool
    message: str
    severity: str = SEVERITY_CRITICAL  # "critical" | "doc" | "warning"


# ==============================================================================
# PROJECT METADATA EXTRACTION
# ==============================================================================


def load_pyproject(root: Path) -> dict:  # type: ignore[type-arg]
    """Load and return the pyproject.toml data dict.

    Raises SystemExit(3) if the file is missing or malformed.
    """
    path = root / "pyproject.toml"
    if not path.exists():
        print(
            f"{Colors.RED}[ERROR]{Colors.RESET} pyproject.toml not found at {root}",
            file=sys.stderr,
        )
        sys.exit(3)
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        print(
            f"{Colors.RED}[ERROR]{Colors.RESET} Failed to parse pyproject.toml: {exc}",
            file=sys.stderr,
        )
        sys.exit(3)


def get_pyproject_version(data: dict) -> str | None:  # type: ignore[type-arg]
    """Extract version from already-loaded pyproject.toml data."""
    raw = data.get("project", {}).get("version")
    return str(raw) if raw is not None else None


def get_project_name(data: dict) -> str:  # type: ignore[type-arg]
    """Extract [project].name from already-loaded pyproject.toml data."""
    return str(data.get("project", {}).get("name", "unknown"))


def get_runtime_version(package_name: str) -> str | None:
    """Get version by importing the package via importlib.metadata.

    This is the canonical runtime check — importlib.metadata reflects what
    was installed by 'uv sync', not what is on the filesystem.
    """
    try:
        from importlib.metadata import (  # noqa: PLC0415 - lazy import by design
            PackageNotFoundError,
            version,
        )

        return version(package_name)
    except (ImportError, PackageNotFoundError):
        return None


# ==============================================================================
# VALIDATION CHECKS
# ==============================================================================


def check_version_sync(data: dict, package_name: str) -> CheckResult:  # type: ignore[type-arg]
    """CRITICAL: installed package version must match pyproject.toml."""
    pyproject_version = get_pyproject_version(data)

    if pyproject_version is None:
        return CheckResult(
            name="version_sync",
            passed=False,
            message="[project].version not found in pyproject.toml",
        )

    runtime_version = get_runtime_version(package_name)

    if runtime_version is None:
        return CheckResult(
            name="version_sync",
            passed=False,
            message=(
                f"Package '{package_name}' not installed or importlib.metadata lookup failed.\n"
                f"  pyproject.toml : {pyproject_version}\n"
                f"  installed      : <not found>\n"
                f"  Resolution     : uv sync"
            ),
        )

    if runtime_version != pyproject_version:
        return CheckResult(
            name="version_sync",
            passed=False,
            message=(
                f"Version mismatch!\n"
                f"  pyproject.toml : {pyproject_version}\n"
                f"  installed      : {runtime_version}\n"
                f"  Resolution     : uv sync"
            ),
        )

    return CheckResult(
        name="version_sync",
        passed=True,
        message=f"Version {pyproject_version} synchronized (pyproject.toml == installed)",
    )


def check_semver(data: dict) -> CheckResult:  # type: ignore[type-arg]
    """CRITICAL: version must be valid semantic versioning (MAJOR.MINOR.PATCH)
    with non-negative integer components.

    Absorbs the old check_version_components check — the regex + component
    loop together enforce both shape and value constraints.
    """
    version = get_pyproject_version(data)

    if version is None:
        return CheckResult(
            name="semver",
            passed=False,
            message="Cannot read version from pyproject.toml",
        )

    semver_pattern = (
        r"^\d+\.\d+\.\d+"  # MAJOR.MINOR.PATCH (required)
        r"(?:-[a-zA-Z0-9.]+)?"  # -PRERELEASE (optional)
        r"(?:\+[a-zA-Z0-9.]+)?$"  # +BUILD (optional)
    )
    if not re.match(semver_pattern, version):
        return CheckResult(
            name="semver",
            passed=False,
            message=(
                f"Invalid version format: {version!r}\n"
                f"  Expected: MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]\n"
                f"  Examples: 1.0.0,  2.3.4-alpha,  1.0.0+build.123"
            ),
        )

    # Additional: components must be non-negative integers
    base = version.split("-", maxsplit=1)[0].split("+", maxsplit=1)[0]
    parts = base.split(".")
    for label, value in zip(["MAJOR", "MINOR", "PATCH"], parts, strict=True):
        if not value.isdigit() or int(value) < 0:
            return CheckResult(
                name="semver",
                passed=False,
                message=f"{label} component must be a non-negative integer, got {value!r}",
            )

    return CheckResult(
        name="semver",
        passed=True,
        message=f"Version {version} is valid semver",
    )


def check_not_placeholder(data: dict) -> CheckResult:  # type: ignore[type-arg]
    """CRITICAL: version must not be a development placeholder."""
    version = get_pyproject_version(data)

    if version is None:
        return CheckResult(
            name="not_placeholder",
            passed=False,
            message="Cannot read version from pyproject.toml",
        )

    placeholders = {"0.0.0+dev", "0.0.0+unknown", "0.0.0.dev0", "0.0.0", "unknown", "dev"}

    if version in placeholders:
        return CheckResult(
            name="not_placeholder",
            passed=False,
            message=(
                f"Development placeholder detected: {version!r}\n"
                f"  Set a real version in pyproject.toml before release."
            ),
        )

    return CheckResult(
        name="not_placeholder",
        passed=True,
        message=f"Version {version!r} is not a placeholder",
    )


def check_configurable_frontmatter(
    data: dict[str, Any], root: Path, globs: list[str], key: str
) -> CheckResult:
    """DOCUMENTATION: specified markdown files must declare matching version in YAML frontmatter.

    Only activates if files are found and the frontmatter key exists.
    """
    version = get_pyproject_version(data)
    if version is None:
        return CheckResult(
            name="configurable_frontmatter",
            passed=False,
            message="Cannot read version from pyproject.toml",
            severity=SEVERITY_DOC,
        )

    frontmatter_re = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
    version_re = re.compile(re.escape(key) + r":\s*(\S+)")

    doc_files: list[Path] = []
    for pattern in globs:
        doc_files.extend(root.glob(pattern))

    # Deduplicate in case overlapping globs
    doc_files = sorted(set(doc_files))

    if not doc_files:
        return CheckResult(
            name="configurable_frontmatter",
            passed=True,
            message="No matching frontmatter files found (skipped)",
            severity=SEVERITY_DOC,
        )

    mismatched: list[str] = []
    checked = 0

    for doc_file in doc_files:
        try:
            content = doc_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            mismatched.append(f"  {doc_file.name}: read error — {exc}")
            continue

        fm_match = frontmatter_re.match(content)
        if not fm_match:
            continue  # No frontmatter

        v_match = version_re.search(fm_match.group(1))
        if not v_match:
            continue  # No target field

        checked += 1
        doc_version = v_match.group(1).strip("'\"")
        if doc_version != version:
            mismatched.append(f"  {doc_file.name}: {doc_version!r} (expected {version!r})")

    if mismatched:
        return CheckResult(
            name="configurable_frontmatter",
            passed=False,
            message="Documentation frontmatter version mismatch:\n"
            + "\n".join(mismatched)
            + f"\n  Resolution: update {key} in YAML frontmatter",
            severity=SEVERITY_DOC,
        )

    msg = (
        f"All {checked} files with {key} field match {version!r}"
        if checked > 0
        else f"No files declare {key} (skipped)"
    )
    return CheckResult(
        name="configurable_frontmatter", passed=True, message=msg, severity=SEVERITY_DOC
    )


def check_configurable_footers(
    data: dict[str, Any], root: Path, project_display_name: str, footer_files: list[str]
) -> list[CheckResult]:
    """DOCUMENTATION: specified files must contain **ProjectName Version**: X.Y.Z footer."""
    version = get_pyproject_version(data)
    results: list[CheckResult] = []

    if version is None:
        return [
            CheckResult(
                name="configurable_footers",
                passed=False,
                message="Cannot read version from pyproject.toml",
                severity=SEVERITY_DOC,
            )
        ]

    if not footer_files:
        return []

    footer_re = re.compile(r"\*\*" + re.escape(project_display_name) + r" Version\*\*:\s*(\S+)")

    for rel_path in footer_files:
        target = root / rel_path
        if not target.exists():
            results.append(
                CheckResult(
                    name=f"footer_{Path(rel_path).name}",
                    passed=True,
                    message=f"{rel_path} not found (skipped)",
                    severity=SEVERITY_DOC,
                )
            )
            continue

        try:
            content = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            results.append(
                CheckResult(
                    name=f"footer_{Path(rel_path).name}",
                    passed=False,
                    message=f"Error reading {rel_path}: {exc}",
                    severity=SEVERITY_DOC,
                )
            )
            continue

        match = footer_re.search(content)
        if not match:
            results.append(
                CheckResult(
                    name=f"footer_{Path(rel_path).name}",
                    passed=True,
                    message=f"No version footer in {rel_path} (skipped)",
                    severity=SEVERITY_DOC,
                )
            )
            continue

        found_version = match.group(1).strip("'\"")
        if found_version != version:
            results.append(
                CheckResult(
                    name=f"footer_{Path(rel_path).name}",
                    passed=False,
                    message=(
                        f"{rel_path} version mismatch:\n"
                        f"  Found    : {found_version!r}\n"
                        f"  Expected : {version!r}\n"
                        f"  Resolution: update the footer in {rel_path}"
                    ),
                    severity=SEVERITY_DOC,
                )
            )
        else:
            results.append(
                CheckResult(
                    name=f"footer_{Path(rel_path).name}",
                    passed=True,
                    message=f"{rel_path} footer matches {version!r}",
                    severity=SEVERITY_DOC,
                )
            )

    return results


def check_changelog_entry(data: dict, root: Path) -> CheckResult:  # type: ignore[type-arg]
    """INFORMATIONAL: CHANGELOG.md should document the current version."""
    version = get_pyproject_version(data)
    if version is None:
        return CheckResult(
            name="changelog_entry",
            passed=True,
            message="Cannot read version from pyproject.toml (skipped)",
            severity=SEVERITY_WARNING,
        )

    if "+dev" in version or "+unknown" in version:
        return CheckResult(
            name="changelog_entry",
            passed=True,
            message="Development version — changelog check skipped",
            severity=SEVERITY_WARNING,
        )

    changelog = root / "CHANGELOG.md"
    if not changelog.exists():
        return CheckResult(
            name="changelog_entry",
            passed=True,
            message="CHANGELOG.md not found (skipped)",
            severity=SEVERITY_WARNING,
        )

    try:
        content = changelog.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return CheckResult(
            name="changelog_entry",
            passed=True,
            message=f"Error reading CHANGELOG.md: {exc} (skipped)",
            severity=SEVERITY_WARNING,
        )

    patterns = [f"## [{version}]", f"## {version}", f"[{version}]:"]
    if any(p in content for p in patterns):
        return CheckResult(
            name="changelog_entry",
            passed=True,
            message=f"CHANGELOG.md documents version {version!r}",
            severity=SEVERITY_WARNING,
        )

    return CheckResult(
        name="changelog_entry",
        passed=False,
        message=(
            f"CHANGELOG.md does not mention version {version!r}\n"
            f"  Consider adding a '## [{version}]' section"
        ),
        severity=SEVERITY_WARNING,
    )


def check_changelog_link(data: dict, root: Path) -> CheckResult:  # type: ignore[type-arg]
    """INFORMATIONAL: CHANGELOG.md should have a hyperlink for the current version."""
    version = get_pyproject_version(data)
    if version is None:
        return CheckResult(
            name="changelog_link",
            passed=True,
            message="Cannot read version from pyproject.toml (skipped)",
            severity=SEVERITY_WARNING,
        )

    if "+dev" in version or "+unknown" in version:
        return CheckResult(
            name="changelog_link",
            passed=True,
            message="Development version — link check skipped",
            severity=SEVERITY_WARNING,
        )

    changelog = root / "CHANGELOG.md"
    if not changelog.exists():
        return CheckResult(
            name="changelog_link",
            passed=True,
            message="CHANGELOG.md not found (skipped)",
            severity=SEVERITY_WARNING,
        )

    try:
        content = changelog.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return CheckResult(
            name="changelog_link",
            passed=True,
            message="Error reading CHANGELOG.md (skipped)",
            severity=SEVERITY_WARNING,
        )

    link_marker = f"[{version}]:"
    if link_marker in content:
        return CheckResult(
            name="changelog_link",
            passed=True,
            message=f"CHANGELOG.md has hyperlink for {version!r}",
            severity=SEVERITY_WARNING,
        )

    return CheckResult(
        name="changelog_link",
        passed=False,
        message=(
            f"CHANGELOG.md missing hyperlink for {version!r}\n"
            f"  Add: [{version}]: https://github.com/.../releases/tag/v{version}"
        ),
        severity=SEVERITY_WARNING,
    )


# ==============================================================================
# RESULT PRESENTATION
# ==============================================================================


def _status_str(result: CheckResult) -> str:
    if result.passed:
        return f"{Colors.GREEN}[PASS]{Colors.RESET}"
    if result.severity == SEVERITY_WARNING:
        return f"{Colors.YELLOW}[WARN]{Colors.RESET}"
    return f"{Colors.RED}[FAIL]{Colors.RESET}"


def print_results(checks: list[CheckResult]) -> None:
    """Print each check result with a coloured status prefix."""
    print(f"{Colors.BOLD}Checks:{Colors.RESET}")
    for result in checks:
        print(f"  {_status_str(result)} {result.name}")
        if not result.passed:
            for line in result.message.split("\n"):
                print(f"         {line}")


def summarise(checks: list[CheckResult]) -> int:
    """Print a one-line summary and return the process exit code."""
    total = len(checks)
    passed_count = sum(1 for c in checks if c.passed)

    critical_failures = [c for c in checks if not c.passed and c.severity == SEVERITY_CRITICAL]
    doc_failures = [c for c in checks if not c.passed and c.severity == SEVERITY_DOC]
    warnings = [c for c in checks if not c.passed and c.severity == SEVERITY_WARNING]

    print()
    if critical_failures:
        print(
            f"{Colors.RED}{Colors.BOLD}[FAIL]{Colors.RESET} "
            f"{len(critical_failures)} critical failure(s) — "
            f"{passed_count}/{total} checks passed"
        )
        return 1

    if doc_failures:
        print(
            f"{Colors.RED}{Colors.BOLD}[FAIL]{Colors.RESET} "
            f"{len(doc_failures)} documentation sync failure(s) — "
            f"{passed_count}/{total} checks passed"
        )
        return 2

    if warnings:
        print(
            f"{Colors.YELLOW}{Colors.BOLD}[WARN]{Colors.RESET} "
            f"{len(warnings)} informational warning(s) — "
            f"{passed_count}/{total} checks passed"
        )
        return 0

    print(f"{Colors.GREEN}{Colors.BOLD}[OK]{Colors.RESET} All {total} version checks passed")
    return 0


# ==============================================================================
# MAIN
# ==============================================================================


def main() -> int:
    """Run all version consistency checks and return an exit code."""
    root = Path(__file__).parent.parent

    # Load pyproject.toml once — exit 3 if unreadable (see load_pyproject)
    data = load_pyproject(root)

    # Derive project identity dynamically — no hardcoded strings
    package_name = get_project_name(data)  # e.g. "ftllexengine"
    project_display_name = package_name.capitalize()  # e.g. "Ftllexengine"
    # Better: if the project name uses title-casing hints, derive it properly
    # e.g. "ftllexengine" → "FTLLexEngine" via pyproject [tool.project-display-name]
    # Fallback: capitalise first letter only (safe for any project name)
    canonical_version = get_pyproject_version(data) or "unknown"

    print(f"{Colors.BOLD}{Colors.CYAN}=== Version Consistency Check ==={Colors.RESET}")
    print(f"Project  : {Colors.BOLD}{package_name}{Colors.RESET}")
    print(f"Version  : {Colors.BOLD}{canonical_version}{Colors.RESET}\n")

    checks: list[CheckResult] = [
        # CRITICAL
        check_version_sync(data, package_name),
        check_semver(data),
        check_not_placeholder(data),
        # INFORMATIONAL
        check_changelog_entry(data, root),
        check_changelog_link(data, root),
    ]

    # Configurable documentation checks
    val_config = data.get("tool", {}).get("validate-version", {})
    if val_config:
        frontmatter_globs = val_config.get("frontmatter_globs", [])
        frontmatter_key = val_config.get("frontmatter_key", "")
        if frontmatter_globs and frontmatter_key:
            checks.append(
                check_configurable_frontmatter(data, root, frontmatter_globs, frontmatter_key)
            )

        footer_files = val_config.get("footer_files", [])
        if footer_files:
            checks.extend(
                check_configurable_footers(data, root, project_display_name, footer_files)
            )

    print_results(checks)
    return summarise(checks)


if __name__ == "__main__":
    sys.exit(main())
