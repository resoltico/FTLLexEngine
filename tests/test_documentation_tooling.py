"""Regression tests for documentation tooling and source docstring policy."""

from __future__ import annotations

import doctest
import importlib
import importlib.util
import inspect
import json
import pkgutil
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType

import pytest

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
    "ftllexengine.analysis",
    "ftllexengine.validation",
)
DOCUMENTED_REPO_SCRIPTS = (
    "check.sh",
    "scripts/validate_docs.py",
    "scripts/validate_version.py",
    "scripts/validate-devcontainer.sh",
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


def _documentation_index_targets() -> set[str]:
    """Return the Markdown files listed in the human docs map.

    Premise:
        The root docs index should be a complete inventory of `docs/*.md`, not
        just an API symbol router.

    Reason:
        A dedicated parser here lets tests fail the moment a new guide lands in
        `docs/` without being added to the published navigation map.
    """
    index_path = REPO_ROOT / "docs" / "DOC_00_Index.md"
    text = index_path.read_text(encoding="utf-8")
    start = text.index("## Documentation Map")
    end = text.index("## Routing Table")
    section = text[start:end]

    return {
        Path(target).name
        for target in re.findall(r"\[[^\]]+\]\(([^)#]+\.md)\)", section)
    }


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


def _atheris_targets() -> list[tuple[str, str, str]]:
    """Return the canonical Atheris target registry rows."""
    manifest = REPO_ROOT / "fuzz_atheris" / "targets.tsv"
    rows: list[tuple[str, str, str]] = []

    for raw_line in manifest.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name, module, description = line.split("\t")
        rows.append((name, module, description))

    return rows


def test_validate_docs_configuration_tracks_runnable_python_docs() -> None:
    """validate_docs should know which markdown files contain runnable examples."""
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
    assert "docs/WORKFLOW_TOUR.md" in config.python_exec_globs
    assert "docs/FUZZING_GUIDE.md" in config.shell_exec_globs
    assert "docs/FUZZING_GUIDE_ATHERIS.md" in config.shell_exec_globs
    assert "docs/FUZZING_GUIDE_HYPOFUZZ.md" in config.shell_exec_globs
    assert "fuzz_atheris/README.md" in config.shell_exec_globs
    assert (
        validate_docs.validate_python_code("from ftllexengine import __version__", REPO_ROOT)
        is None
    )
    assert validate_docs.validate_python_code("raise RuntimeError('boom')", REPO_ROOT) is not None
    assert validate_docs.validate_shell_code("printf docs-shell-ok", REPO_ROOT, 5) is None
    assert validate_docs.validate_shell_code("exit 7", REPO_ROOT, 5) is not None


def test_validate_docs_prefers_path_bash_for_shell_snippets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shell snippet validation should prefer the PATH-resolved Bash runtime."""
    validate_docs = _load_script_module(
        "validate_docs_shell_resolution", REPO_ROOT / "scripts" / "validate_docs.py"
    )

    monkeypatch.setenv("BASH", "/bin/bash")
    monkeypatch.setenv("SHELL", "/bin/zsh")
    monkeypatch.setattr(
        validate_docs.shutil,
        "which",
        lambda name: "/opt/homebrew/bin/bash" if name == "bash" else None,
    )

    shell, preamble = validate_docs._resolve_shell_runner()

    assert shell == "/opt/homebrew/bin/bash"
    assert preamble == "set -euo pipefail"


def test_validate_docs_normalizes_devcontainer_wrapper_inside_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Host-side devcontainer wrapper snippets should collapse inside the container."""
    validate_docs = _load_script_module(
        "validate_docs_devcontainer_normalization", REPO_ROOT / "scripts" / "validate_docs.py"
    )

    monkeypatch.setenv("FTLLEXENGINE_DEVCONTAINER", "1")
    code = (
        "npx --yes @devcontainers/cli up --workspace-folder .\n"
        "npx --yes @devcontainers/cli exec --workspace-folder . ./scripts/fuzz_atheris.sh --help\n"
    )

    normalized = validate_docs._normalize_shell_code_for_runtime(code)

    assert normalized.strip() == "./scripts/fuzz_atheris.sh --help"


def test_hypofuzz_deep_mode_declares_and_uses_fuzz_tooling_group() -> None:
    """Deep HypoFuzz runs must provision the fuzz dependency group explicitly."""
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    fuzz_group = pyproject["dependency-groups"]["fuzz"]
    deep_mode = (REPO_ROOT / "scripts" / "lib" / "fuzz_hypofuzz" / "modes_fuzz.sh").read_text(
        encoding="utf-8"
    )

    assert any(dep.startswith("hypothesis[cli]>=") for dep in fuzz_group)
    assert any(dep.startswith("hypofuzz>=") for dep in fuzz_group)
    assert 'uv run --group fuzz --python "$PY_VERSION"' in deep_mode


def test_workflow_tour_runnable_blocks_are_self_contained() -> None:
    """The workflow guide's runnable Python fences should execute independently."""
    validate_docs = _load_script_module(
        "validate_docs_workflow_tour", REPO_ROOT / "scripts" / "validate_docs.py"
    )
    config = validate_docs.CheckConfig.from_pyproject(REPO_ROOT)
    parser = validate_docs.get_parser(config.parser_path)
    assert parser is not None

    report = validate_docs.ValidationReport(status="pass")
    block_pattern = re.compile(
        r"^([ \t]*)```(\S+)\n(.*?)\n\1```", re.DOTALL | re.MULTILINE | re.IGNORECASE
    )
    validate_docs.process_file(
        REPO_ROOT / "docs" / "WORKFLOW_TOUR.md",
        REPO_ROOT,
        config,
        parser,
        report,
        block_pattern,
    )

    assert report.failures == []


def test_run_examples_registers_contracts_for_all_shipped_examples() -> None:
    """Every shipped example should have an explicit output contract."""
    run_examples = _load_script_module(
        "run_examples_script", REPO_ROOT / "scripts" / "run_examples.py"
    )

    shipped_examples = {
        path.name for path in (REPO_ROOT / "examples").glob("*.py") if path.is_file()
    }

    assert set(run_examples.EXAMPLE_CONTRACTS) == shipped_examples
    assert (
        run_examples.EXAMPLE_CONTRACTS["parser_only.py"](
            "[PASS] Critical warning validation semantics verified\n"
            "[PASS] Invalid syntax semantics verified\n"
            "All examples completed successfully!\n"
        )
        is None
    )
    assert run_examples.EXAMPLE_CONTRACTS["parser_only.py"]("incomplete output") is not None


def test_validate_version_uses_configured_frontmatter_version_contract() -> None:
    """validate_version should enforce the configured `version:` frontmatter key."""
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
        "./scripts/validate-devcontainer.sh",
        "scripts/validate_docs.py",
        "scripts/run_examples.py",
        "./scripts/lint.sh",
        "./scripts/test.sh",
        "./scripts/fuzz_hypofuzz.sh --preflight",
        "./scripts/fuzz_atheris.sh --corpus",
        "./scripts/fuzz_atheris.sh --smoke-all --time",
    )

    for command in required_commands:
        assert command in text


def test_lint_script_uses_explicit_validator_registry() -> None:
    """lint.sh should declare its validator surface instead of discovering it by comments."""
    text = (REPO_ROOT / "scripts" / "lint.sh").read_text(encoding="utf-8")

    assert "SCRIPT_VALIDATORS=(" in text
    assert "validate_pyi_sync.py" in text
    assert "verify_iso4217.py" in text
    assert "validate_docs.py" not in text
    assert "validate_version.py" not in text
    assert "@lint-plugin:" not in text


def test_atheris_launcher_uses_explicit_target_manifest() -> None:
    """Atheris target discovery should come from one manifest, not magic headers."""
    text = (
        REPO_ROOT / "scripts" / "lib" / "fuzz_atheris" / "common.sh"
    ).read_text(encoding="utf-8")
    manifest_rows = _atheris_targets()

    assert "targets.tsv" in text
    assert "FUZZ_PLUGIN" not in text
    assert manifest_rows != []

    for name, module, description in manifest_rows:
        assert name
        assert module.endswith(".py")
        assert description


def test_atheris_launcher_pivots_into_uv_managed_atheris_env() -> None:
    """Atheris native runs should use the dedicated uv-managed environment contract."""
    entrypoint = (REPO_ROOT / "scripts" / "fuzz_atheris.sh").read_text(encoding="utf-8")
    common = (REPO_ROOT / "scripts" / "lib" / "fuzz_atheris" / "common.sh").read_text(
        encoding="utf-8"
    )

    assert 'UV_PROJECT_ENVIRONMENT="$TARGET_VENV"' in common
    assert "--group dev --group atheris --locked" in common
    assert "FTLLEXENGINE_DEVCONTAINER" in common
    assert ".venv-devcontainer-atheris" in common
    assert ".venv-atheris" not in common
    assert 'ORIGINAL_ARGS=("$@")' in entrypoint
    assert 'pivot_to_atheris_env "${ORIGINAL_ARGS[@]}"' in entrypoint


def test_atheris_docs_make_devcontainer_context_explicit() -> None:
    """Published Atheris commands should state the required execution context."""
    guide = (REPO_ROOT / "docs" / "FUZZING_GUIDE_ATHERIS.md").read_text(encoding="utf-8")
    inventory = (REPO_ROOT / "fuzz_atheris" / "README.md").read_text(encoding="utf-8")
    contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")

    assert "Inside a contributor devcontainer terminal" in guide
    assert "From the host, run the same entrypoint through the devcontainer wrapper" in guide
    assert "Inside a contributor devcontainer terminal" in inventory
    assert "Inside a devcontainer terminal: `./scripts/fuzz_atheris.sh" in contributing


def test_devcontainer_declares_atheris_toolchain_contract() -> None:
    """Contributor container must ship the native toolchain Atheris setup needs."""
    dockerfile = (REPO_ROOT / ".devcontainer" / "Dockerfile").read_text(encoding="utf-8")
    config_json = json.loads(
        (REPO_ROOT / ".devcontainer" / "devcontainer.json").read_text(encoding="utf-8")
    )

    assert "clang-19" in dockerfile
    assert "libclang-rt-19-dev" in dockerfile
    assert 'find "$(clang --print-resource-dir)"/lib/linux' in dockerfile
    assert config_json["containerEnv"]["CLANG_BIN"] == "/usr/local/bin/clang"
    assert config_json["containerEnv"]["UV_LINK_MODE"] == "copy"


def test_release_protocol_keeps_verification_commands_inside_devcontainer() -> None:
    """Release instructions should not blur host and in-container verification steps."""
    text = (REPO_ROOT / "docs" / "RELEASE_PROTOCOL.md").read_text(encoding="utf-8")

    required_exec_commands = (
        "npx --yes @devcontainers/cli exec --workspace-folder . ./check.sh",
        "npx --yes @devcontainers/cli exec --workspace-folder . bash -lc '",
        "PY_VERSION=3.14 ./scripts/lint.sh",
        "PY_VERSION=3.14 ./scripts/test.sh",
        "uv run --group dev --python 3.14 python scripts/validate_docs.py",
        "uv run --group dev --python 3.14 python scripts/validate_version.py",
        "uv build",
    )

    for command in required_exec_commands:
        assert command in text


def test_release_protocol_uses_clean_clone_for_container_verified_preflight() -> None:
    """Release instructions should use a clone topology the devcontainer can verify."""
    text = (REPO_ROOT / "docs" / "RELEASE_PROTOCOL.md").read_text(encoding="utf-8")

    assert "Do not use `git worktree` for release pre-flight in this repository." in text
    assert 'git clone --branch main "$PRIMARY_CHECKOUT" "$RELEASE_CLONE"' in text
    assert (
        'git clone --branch codex/release-bootstrap-X.Y.Z "$PRIMARY_CHECKOUT" "$RELEASE_CLONE"'
        in text
    )
    assert 'git remote set-url origin "$PRIMARY_ORIGIN_URL"' in text
    assert "git worktree add" not in text


def test_release_protocol_artifact_leak_check_uses_base_tooling() -> None:
    """Release instructions should not depend on undeclared grep replacements."""
    text = (REPO_ROOT / "docs" / "RELEASE_PROTOCOL.md").read_text(encoding="utf-8")

    assert 'tar -tzf "dist/ftllexengine-X.Y.Z.tar.gz" | grep -E ' in text
    assert "tar -tzf" in text
    assert "| rg " not in text


def test_release_protocol_requires_annotated_tags_and_documents_prepublication_retag_recovery() -> None:
    """Release instructions should bound the wrong-tag recovery path before any public release exists."""
    text = (REPO_ROOT / "docs" / "RELEASE_PROTOCOL.md").read_text(encoding="utf-8")

    assert 'git tag -a vX.Y.Z -m "Release X.Y.Z"' in text
    assert "wrong object type" in text
    assert "git push --delete origin vX.Y.Z" in text
    assert "the failed publish run exited before any public release object or assets were created" in text
    assert "any release-blocking corrective fix has already been merged through the normal PR path" in text
    assert "the intended release commit you most recently re-verified in Step 5" in text
    assert "the same intended release commit you already verified in Step 5" not in text


def test_release_protocol_keeps_public_verification_workspace_until_after_floor_check() -> None:
    """The release verifier must not delete its temp workspace before the negative floor check runs."""
    text = (REPO_ROOT / "docs" / "RELEASE_PROTOCOL.md").read_text(encoding="utf-8")

    py313_install = text.index('uv venv --python 3.13 --seed "$TMP_DIR/py313"')
    py312_install = text.index('uv venv --python 3.12 --seed "$TMP_DIR/py312"')
    cleanup = text.index('rm -rf "$TMP_DIR"')

    assert py313_install < py312_install < cleanup


def test_atheris_inventory_readme_matches_target_manifest() -> None:
    """The published Atheris inventory should stay aligned with the live target registry."""
    readme = (REPO_ROOT / "fuzz_atheris" / "README.md").read_text(encoding="utf-8")
    for name, module, description in _atheris_targets():
        assert f"| `{name}` | `{module}` | {description} |" in readme


def test_shell_gates_use_devcontainer_scoped_venv_names() -> None:
    """Container-run shell gates should not reuse host `.venv-*` paths."""
    script_paths = (
        REPO_ROOT / "check.sh",
        REPO_ROOT / "scripts" / "lint.sh",
        REPO_ROOT / "scripts" / "test.sh",
        REPO_ROOT / "scripts" / "fuzz_hypofuzz.sh",
        REPO_ROOT / "scripts" / "benchmark.sh",
    )

    for path in script_paths:
        text = path.read_text(encoding="utf-8")
        assert "FTLLEXENGINE_DEVCONTAINER" in text
        assert ".venv-devcontainer-" in text


def test_shell_gates_default_uv_link_mode_for_devcontainer_reuse() -> None:
    """Container-owned shell gates should force copy mode for reused devcontainers."""
    script_paths = (
        REPO_ROOT / "check.sh",
        REPO_ROOT / "scripts" / "lint.sh",
        REPO_ROOT / "scripts" / "test.sh",
        REPO_ROOT / "scripts" / "fuzz_hypofuzz.sh",
        REPO_ROOT / "scripts" / "benchmark.sh",
        REPO_ROOT / "scripts" / "lib" / "fuzz_atheris" / "common.sh",
    )

    for path in script_paths:
        text = path.read_text(encoding="utf-8")
        assert 'FTLLEXENGINE_DEVCONTAINER:-}" == "1"' in text
        assert 'export UV_LINK_MODE="copy"' in text


def test_test_sh_executes_pytest_via_explicit_uv_command() -> None:
    """test.sh should run pytest through the explicit uv execution path."""
    text = (REPO_ROOT / "scripts" / "test.sh").read_text(encoding="utf-8")

    assert 'declare -a CMD=("uv" "run" "--python" "$PY_VERSION" "pytest")' in text
    assert 'exec uv run --python "$PY_VERSION" "${BASH:-bash}" "$0" "$@"' not in text


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
                param.name for param in signature.parameters.values() if param.name != "self"
            ]
            if live_params != doc_params:
                issues.append(f"{route_name}: live={live_params!r} doc={doc_params!r}")

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


def test_root_readme_remains_plain_storefront_markdown() -> None:
    """The root README should stay human-first and avoid AFAD-style wrapper markup."""
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert not readme.startswith("---\n")
    assert not readme.lstrip().startswith("<!--")
    assert "\nafad:" not in readme


def test_repo_agent_guidance_is_git_trackable_but_not_in_sdist() -> None:
    """Agent instructions should be committable without becoming package payload."""
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    only_include = set(pyproject["tool"]["hatch"]["build"]["targets"]["sdist"]["only-include"])

    assert "!/AGENTS.md" in gitignore
    assert "!/.codex/" in gitignore
    assert "!/.codex/**" in gitignore

    assert "AGENTS.md" not in only_include
    assert "/AGENTS.md" not in only_include
    assert "/.codex" not in only_include
    assert "/.codex/" not in only_include


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


def test_changelog_uses_plain_changelog_conventions_not_afad_frontmatter() -> None:
    """CHANGELOG.md should use changelog conventions without AFAD frontmatter."""
    changelog = (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    frontmatter_globs = set(pyproject["tool"]["validate-version"]["frontmatter_globs"])

    assert not changelog.startswith("---\n")
    assert "\nafad:" not in changelog
    assert "CHANGELOG.md" not in frontmatter_globs


def test_docs_index_lists_every_top_level_markdown_doc() -> None:
    """The published docs index should enumerate every Markdown file under docs/."""
    documented = _documentation_index_targets()
    expected = {path.name for path in (REPO_ROOT / "docs").glob("*.md")}

    assert documented == expected


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
