"""Architecture contract tests for import direction and workflow hygiene."""

from __future__ import annotations

import ast
import re
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src" / "ftllexengine"

LAYER_ORDER = {
    "core": 0,
    "diagnostics": 1,
    "syntax": 2,
    "validation": 3,
    "analysis": 4,
    "introspection": 4,
    "parsing": 5,
    "runtime": 6,
    "localization": 7,
}

PATH_HACK_PATTERNS = (
    re.compile(r"\bsys\.path\.(?:insert|append)\("),
    re.compile(r"\bPYTHONPATH=src\b"),
    re.compile(r'PYTHONPATH"\]\s*='),
    re.compile(r"\bexport\s+PYTHONPATH=.*\bsrc\b"),
)
LIVE_NETWORK_TEST_PATTERNS = (
    re.compile(r"\burllib\.request\b"),
    re.compile(r"\burlopen\("),
    re.compile(r"raw\.githubusercontent\.com"),
)

VERSION_PROVENANCE_PATTERN = re.compile(r"\b(?:Added|Pre|Post|Prior to)\s+v\d+\.\d+\.\d+\b|v\d+\.\d+\.\d+\+")

FILE_LINE_BUDGETS = {
    "src/ftllexengine/runtime/bundle.py": 120,
    "src/ftllexengine/runtime/bundle_lifecycle.py": 260,
    "src/ftllexengine/runtime/bundle_mutation.py": 180,
    "src/ftllexengine/runtime/cache.py": 500,
    "src/ftllexengine/runtime/cache_audit.py": 80,
    "src/ftllexengine/runtime/cache_introspection.py": 220,
    "src/ftllexengine/runtime/cache_protocols.py": 80,
    "src/ftllexengine/runtime/locale_context.py": 500,
    "src/ftllexengine/runtime/locale_formatting.py": 400,
    "src/ftllexengine/runtime/resolver.py": 600,
    "src/ftllexengine/runtime/function_bridge.py": 250,
    "src/ftllexengine/runtime/function_decorator.py": 80,
    "src/ftllexengine/runtime/function_registry_helpers.py": 160,
    "src/ftllexengine/runtime/function_registry_introspection.py": 140,
    "src/ftllexengine/introspection/iso.py": 200,
    "src/ftllexengine/localization/orchestrator.py": 400,
    "src/ftllexengine/parsing/currency.py": 650,
    "src/ftllexengine/parsing/dates.py": 350,
    "src/ftllexengine/syntax/serializer.py": 700,
    "src/ftllexengine/diagnostics/templates.py": 80,
    "src/ftllexengine/diagnostics/template_reference.py": 220,
    "src/ftllexengine/diagnostics/template_runtime.py": 190,
    "src/ftllexengine/diagnostics/template_parsing.py": 150,
    "src/ftllexengine/syntax/visitor.py": 750,
    "src/ftllexengine/syntax/cursor.py": 700,
    "tests/test_runtime_bundle_property_core.py": 800,
    "tests/test_runtime_bundle_property_references.py": 900,
    "tests/test_runtime_bundle_property_advanced.py": 1000,
    "tests/test_runtime_bundle_property_state.py": 750,
    "tests/test_syntax_serializer.py": 3100,
    "tests/test_syntax_parser_property.py": 2850,
    "tests/strategies/ftl.py": 2700,
    "fuzz_atheris/fuzz_localization.py": 2300,
    "fuzz_atheris/fuzz_runtime.py": 1500,
    "scripts/fuzz_hypofuzz.sh": 1300,
    "scripts/fuzz_atheris.sh": 1100,
}


def _module_name(path: Path) -> str:
    relative = path.relative_to(REPO_ROOT / "src").with_suffix("")
    return ".".join(relative.parts)


def _layer_name(module_name: str) -> str | None:
    parts = module_name.split(".")
    if len(parts) < 2 or parts[0] != "ftllexengine":
        return None
    return parts[1] if parts[1] in LAYER_ORDER else None


def _resolve_import(importer: str, node: ast.ImportFrom) -> str | None:
    package_parts = importer.split(".")[:-1]
    if node.level:
        package_parts = package_parts[: len(package_parts) - node.level + 1]
    if node.module:
        return ".".join([*package_parts, node.module])
    return ".".join(package_parts) if package_parts else None


def _git_visible_repo_files() -> list[Path]:
    """List tracked and unignored files that currently exist in the worktree."""
    git = shutil.which("git")
    assert git is not None
    result = subprocess.run(
        [git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=True,
        capture_output=True,
        cwd=REPO_ROOT,
    )
    files: list[Path] = []
    for raw_path in result.stdout.split(b"\0"):
        if not raw_path:
            continue
        path = REPO_ROOT / raw_path.decode("utf-8")
        if path.is_file():
            files.append(path)
    return files


def test_internal_modules_do_not_reverse_layer_dependencies() -> None:
    """Non-facade modules should only import within or below their own layer."""
    violations: list[str] = []

    for path in sorted(SRC_ROOT.rglob("*.py")):
        if path.name == "__init__.py":
            continue

        importer = _module_name(path)
        importer_layer = _layer_name(importer)
        if importer_layer is None:
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if not alias.name.startswith("ftllexengine."):
                        continue
                    imported_layer = _layer_name(alias.name)
                    if imported_layer and LAYER_ORDER[imported_layer] > LAYER_ORDER[importer_layer]:
                        violations.append(
                            f"{importer} ({importer_layer}) imports {alias.name} ({imported_layer})"
                        )
            elif isinstance(node, ast.ImportFrom):
                imported = _resolve_import(importer, node)
                if imported is None or not imported.startswith("ftllexengine."):
                    continue
                imported_layer = _layer_name(imported)
                if imported_layer and LAYER_ORDER[imported_layer] > LAYER_ORDER[importer_layer]:
                    violations.append(
                        f"{importer} ({importer_layer}) imports {imported} ({imported_layer})"
                    )

    assert violations == []


def test_repo_avoids_legacy_import_path_hacks() -> None:
    """Code and docs should not rely on sys.path or PYTHONPATH src injection."""
    offenders: list[str] = []
    scan_roots = (
        REPO_ROOT / "src",
        REPO_ROOT / "tests",
        REPO_ROOT / "scripts",
        REPO_ROOT / "docs",
        REPO_ROOT / "examples",
        REPO_ROOT / "README.md",
    )

    paths: list[Path] = []
    for root in scan_roots:
        if root.is_file():
            paths.append(root)
        elif root.exists():
            paths.extend(p for p in root.rglob("*") if p.suffix in {".py", ".sh", ".md"})

    for path in sorted(paths):
        if path == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in PATH_HACK_PATTERNS:
            if pattern.search(text):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {pattern.pattern}")

    assert offenders == []


def test_tests_do_not_depend_on_live_network_fixture_fetches() -> None:
    """Test fixtures should be vendored instead of fetched over the live network."""
    offenders: list[str] = []

    for path in sorted((REPO_ROOT / "tests").rglob("*.py")):
        if path == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in LIVE_NETWORK_TEST_PATTERNS:
            if pattern.search(text):
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {pattern.pattern}")

    assert offenders == []


def test_docs_avoid_deep_localization_types_imports() -> None:
    """Public docs should reference stable facades, not helper submodules."""
    offenders: list[str] = []
    doc_paths = [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs").glob("*.md"))]

    for path in doc_paths:
        text = path.read_text(encoding="utf-8")
        if "ftllexengine.localization.types" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == []


def test_parser_grammar_modules_stay_split() -> None:
    """Parser grammar implementation should remain partitioned instead of collapsing back."""
    parser_root = SRC_ROOT / "syntax" / "parser"
    expected_modules = (
        parser_root / "context.py",
        parser_root / "patterns.py",
        parser_root / "expressions.py",
        parser_root / "entries.py",
    )

    missing = [str(path.relative_to(REPO_ROOT)) for path in expected_modules if not path.exists()]
    assert missing == []

    rules_path = parser_root / "rules.py"
    assert rules_path.exists()
    assert len(rules_path.read_text(encoding="utf-8").splitlines()) <= 80


def test_repo_has_no_generated_cover_artifacts_in_tree() -> None:
    """Generated coverage/cache artifacts should not live in the repository tree."""
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in _git_visible_repo_files()
        if re.search(r"(^|/)__pycache__/|\.pyc$|,cover$|\.cover$", str(path))
    ]
    assert offenders == []


def test_repo_avoids_version_provenance_annotations_outside_changelog() -> None:
    """Historical version provenance belongs in CHANGELOG.md, not code or examples."""
    offenders: list[str] = []
    for root in (REPO_ROOT / "src", REPO_ROOT / "tests", REPO_ROOT / "examples"):
        for path in sorted(root.rglob("*")):
            if path.suffix not in {".py", ".md", ".ini", ".pyi"}:
                continue
            text = path.read_text(encoding="utf-8")
            if VERSION_PROVENANCE_PATTERN.search(text):
                offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == []


def test_public_examples_avoid_thread_local_storage_patterns() -> None:
    """Examples should model explicit ownership instead of threading.local()."""
    offenders: list[str] = []
    for path in (
        REPO_ROOT / "examples" / "thread_safety.py",
        REPO_ROOT / "examples" / "README_TYPE_CHECKING.md",
    ):
        if "threading.local" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == []


def test_large_repo_files_stay_under_line_budgets() -> None:
    """Large source, test, fuzz, and script files should remain split by responsibility."""
    offenders: list[str] = []
    for relative_path, max_lines in FILE_LINE_BUDGETS.items():
        path = REPO_ROOT / relative_path
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > max_lines:
            offenders.append(f"{relative_path}: {line_count} > {max_lines}")

    assert offenders == []
