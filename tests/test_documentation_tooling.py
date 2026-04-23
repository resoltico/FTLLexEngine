"""Regression tests for documentation tooling and source docstring policy."""

from __future__ import annotations

import doctest
import importlib
import importlib.util
import inspect
import pkgutil
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
DOCUMENTED_MODULES = (
    "ftllexengine",
    "ftllexengine.runtime",
    "ftllexengine.localization",
    "ftllexengine.syntax",
    "ftllexengine.parsing",
    "ftllexengine.diagnostics",
    "ftllexengine.introspection",
    "ftllexengine.validation",
)
DOCUMENTED_REPO_SCRIPTS = (
    "check.sh",
    "scripts/validate_docs.py",
    "scripts/validate_version.py",
    "scripts/run_examples.py",
    "scripts/lint.sh",
    "scripts/test.sh",
    "scripts/fuzz_hypofuzz.sh",
    "scripts/fuzz_atheris.sh",
)
ROUTE_NAME_OVERRIDES: dict[str, dict[str, str]] = {
    "ftllexengine.syntax": {
        "ParseResult": "ftllexengine.syntax.ParseResult",
    },
}
UNDOCUMENTED_REFERENCE_ALIASES = ("InlineExpression", "VariantKey")
REFERENCE_DOC_LINE_BUDGET = 450


def _load_script_module(name: str, path: Path) -> ModuleType:
    """Load a repository script as an importable module for testing."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _index_routes() -> dict[str, tuple[Path, str]]:
    """Parse the API routing table from docs/DOC_00_Index.md."""
    index_path = REPO_ROOT / "docs" / "DOC_00_Index.md"
    text = index_path.read_text(encoding="utf-8")
    routes: dict[str, tuple[Path, str]] = {}

    row_pattern = re.compile(
        r"^\| `([^`]+)` \| \[([^\]]+)\]\(([^)]+)\) \| `([^`]+)` \|$",
        re.MULTILINE,
    )
    for symbol, _label, rel_target, section in row_pattern.findall(text):
        routes[symbol] = ((index_path.parent / rel_target).resolve(), section)
    return routes


def _symbol_headings(md_path: Path) -> set[str]:
    """Return the set of second-level symbol headings in a markdown file."""
    text = md_path.read_text(encoding="utf-8")
    return set(re.findall(r"^## `([^`]+)`$", text, re.MULTILINE))


def _extract_signature_block(md_path: Path, section: str) -> str | None:
    """Return the python signature block for one AFAD reference entry."""
    text = md_path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^## `{re.escape(section)}`\n\n.*?### Signature\n```python\n(.*?)\n```",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def test_validate_docs_configuration_tracks_runnable_python_docs() -> None:
    """validate_docs should know which markdown files contain runnable Python."""
    validate_docs = _load_script_module(
        "validate_docs_script", REPO_ROOT / "scripts" / "validate_docs.py"
    )

    config = validate_docs.CheckConfig.from_pyproject(REPO_ROOT)

    assert "README.md" in config.scan_globs
    assert "examples/**/*.md" in config.scan_globs
    assert "fuzz_atheris/README.md" in config.scan_globs
    assert "README.md" in config.python_exec_globs
    assert "docs/CUSTOM_FUNCTIONS_GUIDE.md" in config.python_exec_globs
    assert "docs/LOCALE_GUIDE.md" in config.python_exec_globs
    assert "docs/MIGRATION.md" in config.python_exec_globs
    assert "docs/PARSING_GUIDE.md" in config.python_exec_globs
    assert "docs/QUICK_REFERENCE.md" in config.python_exec_globs
    assert "docs/TYPE_HINTS_GUIDE.md" in config.python_exec_globs
    assert "docs/VALIDATION_GUIDE.md" in config.python_exec_globs
    assert (
        validate_docs.validate_python_code("from ftllexengine import __version__", REPO_ROOT)
        is None
    )
    assert validate_docs.validate_python_code("raise RuntimeError('boom')", REPO_ROOT) is not None


def test_run_examples_registers_contracts_for_all_shipped_examples() -> None:
    """Every shipped example should have an explicit output contract."""
    run_examples = _load_script_module(
        "run_examples_script", REPO_ROOT / "scripts" / "run_examples.py"
    )

    shipped_examples = {
        path.name
        for path in (REPO_ROOT / "examples").glob("*.py")
        if path.is_file()
    }

    assert set(run_examples.EXAMPLE_CONTRACTS) == shipped_examples
    assert run_examples.EXAMPLE_CONTRACTS["parser_only.py"](
        "[PASS] Warning-only validation semantics verified\n"
        "[PASS] Invalid syntax semantics verified\n"
        "All examples completed successfully!\n"
    ) is None
    assert run_examples.EXAMPLE_CONTRACTS["parser_only.py"]("incomplete output") is not None


def test_validate_version_uses_afad_frontmatter_version_contract() -> None:
    """validate_version should enforce the AFAD v3.5 `version:` frontmatter key."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    validate_version = _load_script_module(
        "validate_version_script", REPO_ROOT / "scripts" / "validate_version.py"
    )

    assert pyproject["tool"]["validate-version"]["frontmatter_key"] == "version"

    with TemporaryDirectory() as td:
        root = Path(td)
        (root / "doc.md").write_text(
            "---\nversion: 0.0.1\n---\n\nbody\n",
            encoding="utf-8",
        )
        result = validate_version.check_configurable_frontmatter(
            {"project": {"version": "9.9.9"}},
            root,
            ["doc.md"],
            "version",
        )

    assert result.passed is False
    assert result.severity == validate_version.SEVERITY_DOC
    assert "(expected '9.9.9')" in result.message


def test_source_doctest_prompts_are_explicitly_non_executable() -> None:
    """Raw doctest prompts in source docstrings must be explicitly skipped."""
    offenders: list[str] = []

    for path in sorted((SRC_ROOT / "ftllexengine").rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ">>>" in line and "+SKIP" not in line:
                offenders.append(f"{path}:{lineno}:{line}")

    assert offenders == []


def test_doctest_sweep_is_clean_under_repo_docstring_policy() -> None:
    """A package-wide doctest sweep should pass under the repository policy."""
    package = importlib.import_module("ftllexengine")
    module_names = ["ftllexengine"] + [
        m.name for m in pkgutil.walk_packages(package.__path__, prefix="ftllexengine.")
    ]

    failures: list[str] = []
    for name in module_names:
        module = importlib.import_module(name)
        result = doctest.testmod(module, optionflags=doctest.ELLIPSIS, report=False)
        if result.failed:
            failures.append(f"{name}: failed={result.failed} attempted={result.attempted}")

    assert failures == []


def test_api_index_covers_public_root_exports_and_existing_sections() -> None:
    """Public root exports should always be routed to a real API reference section."""
    package = importlib.import_module("ftllexengine")
    routes = _index_routes()
    public_exports = set(package.__all__)

    missing = sorted(public_exports - set(routes))
    assert missing == []

    for symbol, (target_path, section) in routes.items():
        assert target_path.exists(), symbol
        assert section in _symbol_headings(target_path), symbol


def test_api_index_covers_documented_module_exports() -> None:
    """Reference index should cover the exported surfaces the docs claim to cover."""
    routes = _index_routes()

    expected_routes: set[str] = set()
    for module_name in DOCUMENTED_MODULES:
        module = importlib.import_module(module_name)
        overrides = ROUTE_NAME_OVERRIDES.get(module_name, {})
        for symbol in getattr(module, "__all__", []):
            expected_routes.add(overrides.get(symbol, symbol))

    missing = sorted(expected_routes - set(routes))
    assert missing == []

    for symbol in expected_routes:
        target_path, section = routes[symbol]
        assert target_path.exists(), symbol
        assert section in _symbol_headings(target_path), symbol


def test_api_index_covers_documented_repo_scripts() -> None:
    """Reference index should route the repo's supported operational scripts."""
    routes = _index_routes()

    missing = sorted(set(DOCUMENTED_REPO_SCRIPTS) - set(routes))
    assert missing == []

    for symbol in DOCUMENTED_REPO_SCRIPTS:
        target_path, section = routes[symbol]
        assert target_path.exists(), symbol
        assert section in _symbol_headings(target_path), symbol


def test_reference_doc_import_statements_resolve() -> None:
    """Reference-doc import examples should stay copy-paste correct."""
    import_pattern = re.compile(r"- Import: `([^`]+)`")
    doc_paths = sorted((REPO_ROOT / "docs").glob("DOC_*.md"))

    failures: list[str] = []
    for path in doc_paths:
        for statement in import_pattern.findall(path.read_text(encoding="utf-8")):
            result = subprocess.run(
                [sys.executable, "-c", f"{statement}\nprint('OK')\n"],
                cwd=SRC_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                stderr = result.stderr.strip() or result.stdout.strip()
                failures.append(f"{path.name}: {statement} -> {stderr}")

    assert failures == []


def test_reference_doc_signatures_avoid_undocumented_internal_aliases() -> None:
    """Reference docs should not leak undocumented submodule-only alias names."""
    doc_paths = sorted((REPO_ROOT / "docs").glob("DOC_*.md"))
    offenders: list[str] = []

    for path in doc_paths:
        text = path.read_text(encoding="utf-8")
        for alias in UNDOCUMENTED_REFERENCE_ALIASES:
            if alias in text:
                offenders.append(f"{path.name}: {alias}")

    assert offenders == []


def test_reference_docs_stay_split_under_line_budget() -> None:
    """Reference docs should stay partitioned instead of regressing into god files."""
    offenders: list[str] = []

    for path in sorted((REPO_ROOT / "docs").glob("DOC_*.md")):
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > REFERENCE_DOC_LINE_BUDGET:
            offenders.append(f"{path.name}: {line_count}")

    assert offenders == []


def test_check_script_covers_full_quality_surface() -> None:
    """Top-level check.sh should orchestrate the repo's supported validation gates."""
    text = (REPO_ROOT / "check.sh").read_text(encoding="utf-8")

    required_commands = (
        "scripts/validate_version.py",
        "scripts/validate_docs.py",
        "scripts/run_examples.py",
        "./scripts/lint.sh",
        "./scripts/test.sh",
        "./scripts/fuzz_hypofuzz.sh --preflight",
        "./scripts/fuzz_atheris.sh --corpus",
        "./scripts/fuzz_atheris.sh graph --time",
        "./scripts/fuzz_atheris.sh introspection --time",
    )

    for command in required_commands:
        assert command in text


def test_atheris_corpus_health_bootstraps_its_venv() -> None:
    """Atheris corpus health should create its dedicated venv before execution."""
    text = (REPO_ROOT / "scripts" / "fuzz_atheris.sh").read_text(encoding="utf-8")
    marker = "run_corpus_health() {"
    assert marker in text
    body = text.split(marker, 1)[1].split("}", 1)[0]

    assert "ensure_atheris_venv" in body or "run_diagnostics" in body


def test_atheris_bootstrap_discovers_uv_managed_python_313() -> None:
    """Atheris bootstrap should recognize uv-managed Python 3.13 interpreters."""
    text = (REPO_ROOT / "scripts" / "fuzz_atheris.sh").read_text(encoding="utf-8")

    assert "uv python find 3.13" in text


def test_atheris_bootstrap_recreates_broken_venv_dirs() -> None:
    """Atheris bootstrap should discard stale venv directories with broken Python links."""
    text = (REPO_ROOT / "scripts" / "fuzz_atheris.sh").read_text(encoding="utf-8")

    assert '[[ -d "$ATHERIS_VENV" ]] && [[ ! -x "$ATHERIS_PYTHON" ]]' in text


def test_reference_signature_parameter_names_match_live_exports() -> None:
    """AFAD reference signatures should keep parameter names aligned with live exports."""
    routes = _index_routes()
    issues: list[str] = []

    for module_name in DOCUMENTED_MODULES:
        module = importlib.import_module(module_name)
        overrides = ROUTE_NAME_OVERRIDES.get(module_name, {})
        for symbol in getattr(module, "__all__", []):
            route_name = overrides.get(symbol, symbol)
            if route_name not in routes:
                continue

            target_path, section = routes[route_name]
            signature_block = _extract_signature_block(target_path, section)
            if signature_block is None or (
                "def " not in signature_block and "class " not in signature_block
            ):
                continue

            obj = getattr(module, symbol)
            try:
                signature = inspect.signature(obj)
            except (TypeError, ValueError):
                continue

            if "def __init__(" in signature_block:
                params_source = signature_block.split("def __init__(", 1)[1].split(") ->", 1)[0]
            elif signature_block.lstrip().startswith("def "):
                params_source = signature_block.split("(", 1)[1].rsplit(")", 1)[0]
            else:
                continue

            doc_params = [
                name
                for name in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*:", params_source)
                if name != "self"
            ]
            live_params = [
                param.name
                for param in signature.parameters.values()
                if param.name != "self"
            ]
            if live_params != doc_params:
                issues.append(
                    f"{route_name}: live={live_params!r} doc={doc_params!r}"
                )

    assert issues == []


def test_diagnostics_reference_documents_parser_annotation_contract() -> None:
    """Diagnostics reference should document the structural parser annotation API."""
    diagnostics_doc = REPO_ROOT / "docs" / "DOC_05_Diagnostics.md"

    parser_annotation_signature = _extract_signature_block(diagnostics_doc, "ParserAnnotation")
    validation_result_signature = _extract_signature_block(diagnostics_doc, "ValidationResult")

    assert parser_annotation_signature is not None
    assert "class ParserAnnotation(Protocol):" in parser_annotation_signature
    assert "annotations: tuple[ParserAnnotation, ...]" in (validation_result_signature or "")


def test_sdist_includes_root_frontmatter_docs_and_readme() -> None:
    """Root markdown docs with frontmatter should ship in the source distribution."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    only_include = set(pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]["only-include"])

    expected = {"README.md"}
    for path in REPO_ROOT.glob("*.md"):
        if path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8")
        if text.startswith("---\n") and "\nafad:" in text:
            expected.add(path.name)

    missing = sorted(expected - only_include)
    assert missing == []


def test_release_protocol_lives_under_docs_and_repo_links_follow_it() -> None:
    """Release protocol should live under docs/ and repo surfaces should link there."""
    release_doc = REPO_ROOT / "docs" / "RELEASE_PROTOCOL.md"
    assert release_doc.exists()
    assert not (REPO_ROOT / "RELEASE_PROTOCOL.md").exists()

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "(docs/RELEASE_PROTOCOL.md)" in readme
    assert "(docs/RELEASE_PROTOCOL.md)" in contributing

    frontmatter_globs = set(pyproject["tool"]["validate-version"]["frontmatter_globs"])
    only_include = set(pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]["only-include"])

    assert "RELEASE_PROTOCOL.md" not in frontmatter_globs
    assert "RELEASE_PROTOCOL.md" not in only_include


def test_public_docs_and_examples_avoid_fix_later_markers() -> None:
    """Public-facing docs and examples should not ship TODO/FIXME/HACK markers."""
    offenders: list[str] = []
    scan_paths = [REPO_ROOT / "README.md", *sorted((REPO_ROOT / "docs").glob("*.md"))]
    scan_paths.extend(sorted((REPO_ROOT / "examples").rglob("*.py")))
    scan_paths.extend(sorted((REPO_ROOT / "examples").glob("*.md")))

    marker_re = re.compile(r"\b(TODO|FIXME|HACK)\b")

    for path in scan_paths:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if marker_re.search(line):
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}:{line.strip()}")

    assert offenders == []
