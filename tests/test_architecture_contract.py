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

VERSION_PROVENANCE_PATTERN = re.compile(
    r"\b(?:Added|Pre|Post|Prior to)\s+v\d+\.\d+\.\d+\b|v\d+\.\d+\.\d+\+"
)
LARGE_OWNER_BUDGET_THRESHOLD = 1000

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
    "src/ftllexengine/syntax/serializer.py": 450,
    "src/ftllexengine/syntax/serializer_engine.py": 350,
    "src/ftllexengine/diagnostics/templates.py": 80,
    "src/ftllexengine/diagnostics/template_reference.py": 220,
    "src/ftllexengine/diagnostics/template_runtime.py": 190,
    "src/ftllexengine/diagnostics/template_parsing.py": 150,
    "src/ftllexengine/validation/resource.py": 240,
    "src/ftllexengine/validation/resource_common.py": 60,
    "src/ftllexengine/validation/resource_entries.py": 260,
    "src/ftllexengine/validation/resource_syntax.py": 100,
    "src/ftllexengine/syntax/visitor.py": 750,
    "src/ftllexengine/syntax/cursor.py": 700,
    "tests/test_runtime_bundle_property_core.py": 800,
    "tests/test_runtime_bundle_property_references.py": 900,
    "tests/test_runtime_bundle_property_advanced.py": 1000,
    "tests/test_runtime_bundle_property_state.py": 750,
    "tests/test_introspection_iso.py": 20,
    "tests/introspection_iso_cases/lookup.py": 560,
    "tests/introspection_iso_cases/cache_and_babel.py": 640,
    "tests/introspection_iso_cases/error_paths.py": 320,
    "tests/introspection_iso_cases/defensive_branches.py": 560,
    "tests/introspection_iso_cases/requirements.py": 360,
    "tests/test_runtime_cache_integrity.py": 20,
    "tests/runtime_cache_integrity_cases/checksums.py": 320,
    "tests/runtime_cache_integrity_cases/write_once_audit.py": 460,
    "tests/runtime_cache_integrity_cases/idempotence_and_hashes.py": 400,
    "tests/runtime_cache_integrity_cases/integrity_edges.py": 620,
    "tests/runtime_cache_integrity_cases/limits_and_timing.py": 320,
    "tests/test_introspection_message.py": 20,
    "tests/introspection_message_cases/extraction_and_references.py": 580,
    "tests/introspection_message_cases/contracts_and_spans.py": 540,
    "tests/introspection_message_cases/properties_and_branches.py": 520,
    "tests/introspection_message_cases/cache_and_validation.py": 360,
    "tests/test_diagnostics_frozen_error.py": 20,
    "tests/diagnostics_frozen_error_cases/core_behavior.py": 580,
    "tests/diagnostics_frozen_error_cases/branch_coverage.py": 600,
    "tests/diagnostics_frozen_error_cases/formatting_and_hashes.py": 620,
    "tests/test_runtime_locale_context.py": 20,
    "tests/runtime_locale_context_cases/construction_and_cache.py": 480,
    "tests/runtime_locale_context_cases/number_formatting.py": 280,
    "tests/runtime_locale_context_cases/datetime_and_currency.py": 440,
    "tests/runtime_locale_context_cases/boundaries_and_extras.py": 500,
    "tests/test_runtime_resolver_selection.py": 20,
    "tests/runtime_resolver_selection_cases/pattern_resolution.py": 420,
    "tests/runtime_resolver_selection_cases/numeric_matching.py": 480,
    "tests/runtime_resolver_selection_cases/number_literal_edges.py": 460,
    "tests/runtime_resolver_selection_cases/fallback_and_errors.py": 340,
    "tests/test_localization_orchestration.py": 20,
    "tests/localization_orchestration_cases/load_and_lookup.py": 420,
    "tests/localization_orchestration_cases/strict_and_boot.py": 420,
    "tests/localization_orchestration_cases/cache_and_properties.py": 420,
    "tests/localization_orchestration_cases/ast_and_cleanup.py": 460,
    "tests/test_localization.py": 20,
    "tests/localization_cases/basics_and_fallback.py": 340,
    "tests/localization_cases/loaders_and_cache.py": 360,
    "tests/localization_cases/multilocale_and_callbacks.py": 560,
    "tests/localization_cases/validation_and_streams.py": 480,
    "tests/test_syntax_serializer_core.py": 950,
    "tests/test_syntax_serializer_text_validation.py": 800,
    "tests/test_syntax_serializer_patterns.py": 550,
    "tests/test_syntax_serializer_helpers.py": 550,
    "tests/test_syntax_serializer_branches.py": 700,
    "tests/test_runtime_bundle.py": 20,
    "tests/runtime_bundle_cases/__init__.py": 40,
    "tests/runtime_bundle_cases/basic.py": 820,
    "tests/runtime_bundle_cases/state.py": 820,
    "tests/runtime_bundle_cases/introspection.py": 320,
    "tests/runtime_bundle_cases/properties.py": 700,
    "tests/test_syntax_validator.py": 20,
    "tests/syntax_validator_cases/__init__.py": 60,
    "tests/syntax_validator_cases/entries.py": 620,
    "tests/syntax_validator_cases/results.py": 620,
    "tests/syntax_validator_cases/high_level.py": 500,
    "tests/syntax_validator_cases/regressions.py": 620,
    "tests/test_syntax_parser_property.py": 20,
    "tests/syntax_parser_property_cases/__init__.py": 60,
    "tests/syntax_parser_property_cases/core.py": 700,
    "tests/syntax_parser_property_cases/syntax_elements.py": 760,
    "tests/syntax_parser_property_cases/grammar_boundaries.py": 780,
    "tests/syntax_parser_property_cases/roundtrip_and_malformed.py": 700,
    "tests/strategies/ftl.py": 20,
    "tests/strategies/ftl_shared.py": 80,
    "tests/strategies/ftl_strings.py": 620,
    "tests/strategies/ftl_ast.py": 780,
    "tests/strategies/ftl_structural.py": 500,
    "tests/strategies/ftl_whitespace.py": 440,
    "tests/strategies/ftl_negative.py": 500,
    "tests/fuzz/test_syntax_serializer_property.py": 40,
    "tests/test_syntax_parser_core.py": 40,
    "tests/test_syntax_parser_expressions.py": 40,
    "tests/test_syntax_parser_patterns.py": 40,
    "tests/test_validation_resource.py": 40,
    "tests/test_syntax_visitor_transformer.py": 40,
    "tests/test_runtime_resolver_depth_cycles.py": 40,
    "tests/test_parsing_currency.py": 40,
    "tests/test_parsing_dates.py": 40,
    "tests/test_runtime_cache_hashable.py": 40,
    "tests/fuzz/test_runtime_resolver_state_machine.py": 40,
    "tests/strategy_metrics.py": 1260,
    "tests/fuzz/test_localization_property.py": 40,
    "tests/test_runtime_cache_property.py": 40,
    "tests/test_runtime_function_bridge.py": 40,
    "tests/test_syntax_visitor.py": 40,
    "tests/test_syntax_parser_error_recovery.py": 40,
    "tests/test_runtime_plural_rules.py": 40,
    "tests/test_integration_e2e.py": 40,
    "tests/test_validation_resource_dependency_graph.py": 40,
    "tests/test_syntax_cursor_property.py": 40,
    "tests/test_syntax_serializer_roundtrip.py": 40,
    "tests/test_syntax_cursor.py": 40,
    "fuzz_atheris/fuzz_localization.py": 40,
    "fuzz_atheris/fuzz_localization_entry.py": 200,
    "fuzz_atheris/fuzz_localization_support.py": 380,
    "fuzz_atheris/fuzz_localization_patterns_basic.py": 560,
    "fuzz_atheris/fuzz_localization_patterns_validation.py": 380,
    "fuzz_atheris/fuzz_localization_patterns_introspection.py": 420,
    "fuzz_atheris/fuzz_localization_patterns_loader.py": 360,
    "fuzz_atheris/fuzz_localization_patterns_boot.py": 280,
    "fuzz_atheris/fuzz_runtime.py": 40,
    "fuzz_atheris/fuzz_runtime_entry.py": 300,
    "fuzz_atheris/fuzz_runtime_support.py": 420,
    "fuzz_atheris/fuzz_runtime_builders.py": 420,
    "fuzz_atheris/fuzz_runtime_scenarios.py": 460,
    "fuzz_atheris/fuzz_bridge.py": 40,
    "fuzz_atheris/fuzz_bridge_entry.py": 200,
    "fuzz_atheris/fuzz_bridge_support.py": 420,
    "fuzz_atheris/fuzz_bridge_patterns_registration.py": 260,
    "fuzz_atheris/fuzz_bridge_patterns_numbers.py": 320,
    "fuzz_atheris/fuzz_bridge_patterns_dispatch.py": 480,
    "fuzz_atheris/fuzz_serializer.py": 40,
    "fuzz_atheris/fuzz_serializer_entry.py": 200,
    "fuzz_atheris/fuzz_serializer_support.py": 440,
    "fuzz_atheris/fuzz_serializer_patterns_text.py": 320,
    "fuzz_atheris/fuzz_serializer_patterns_transform.py": 240,
    "fuzz_atheris/fuzz_serializer_mutators.py": 220,
    "fuzz_atheris/fuzz_builtins.py": 40,
    "fuzz_atheris/fuzz_builtins_entry.py": 180,
    "fuzz_atheris/fuzz_builtins_support.py": 420,
    "fuzz_atheris/fuzz_builtins_patterns_number.py": 220,
    "fuzz_atheris/fuzz_builtins_patterns_datetime.py": 180,
    "fuzz_atheris/fuzz_builtins_patterns_currency.py": 340,
    "scripts/fuzz_hypofuzz.sh": 300,
    "scripts/lib/fuzz_hypofuzz/common.sh": 220,
    "scripts/lib/fuzz_hypofuzz/modes_check.sh": 320,
    "scripts/lib/fuzz_hypofuzz/modes_fuzz.sh": 500,
    "scripts/fuzz_atheris.sh": 220,
    "scripts/lib/fuzz_atheris/common.sh": 180,
    "scripts/lib/fuzz_atheris/commands.sh": 320,
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


def _git_tracked_repo_files() -> list[Path]:
    """List files present in the git index for the current worktree state."""
    git = shutil.which("git")
    assert git is not None
    result = subprocess.run(
        [git, "ls-files", "--cached", "-z"],
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


def test_large_python_and_shell_owners_have_explicit_budgets() -> None:
    """Any very large owner must opt into an explicit architecture budget."""
    offenders: list[str] = []
    scan_roots = (
        REPO_ROOT / "src",
        REPO_ROOT / "tests",
        REPO_ROOT / "fuzz_atheris",
        REPO_ROOT / "scripts",
    )

    for root in scan_roots:
        for path in sorted(root.rglob("*")):
            if path.suffix not in {".py", ".sh"} or path.name == "__init__.py":
                continue
            relative = path.relative_to(REPO_ROOT).as_posix()
            line_count = len(path.read_text(encoding="utf-8").splitlines())
            if (
                line_count >= LARGE_OWNER_BUDGET_THRESHOLD
                and relative not in FILE_LINE_BUDGETS
            ):
                offenders.append(f"{relative}: {line_count}")

    assert offenders == []


def test_hypofuzz_entrypoint_delegates_to_split_libraries() -> None:
    """HypoFuzz entrypoint should stay a thin dispatcher over focused shell libs."""
    entrypoint = (REPO_ROOT / "scripts" / "fuzz_hypofuzz.sh").read_text(encoding="utf-8")

    expected_libraries = (
        REPO_ROOT / "scripts" / "lib" / "fuzz_hypofuzz" / "common.sh",
        REPO_ROOT / "scripts" / "lib" / "fuzz_hypofuzz" / "modes_check.sh",
        REPO_ROOT / "scripts" / "lib" / "fuzz_hypofuzz" / "modes_fuzz.sh",
    )

    for lib_path in expected_libraries:
        assert lib_path.exists()
        assert f'source "$FUZZ_LIB_DIR/{lib_path.name}"' in entrypoint


def test_hypofuzz_helper_libraries_are_git_tracked() -> None:
    """Split HypoFuzz helper libraries must be part of tracked repository state."""
    tracked_paths = {
        path.relative_to(REPO_ROOT).as_posix() for path in _git_tracked_repo_files()
    }
    expected = {
        "scripts/lib/fuzz_hypofuzz/common.sh",
        "scripts/lib/fuzz_hypofuzz/modes_check.sh",
        "scripts/lib/fuzz_hypofuzz/modes_fuzz.sh",
    }

    assert expected <= tracked_paths


def test_atheris_entrypoint_delegates_to_split_libraries() -> None:
    """Atheris entrypoint should stay a thin dispatcher over focused shell libs."""
    entrypoint = (REPO_ROOT / "scripts" / "fuzz_atheris.sh").read_text(encoding="utf-8")

    expected_libraries = (
        REPO_ROOT / "scripts" / "lib" / "fuzz_atheris" / "common.sh",
        REPO_ROOT / "scripts" / "lib" / "fuzz_atheris" / "commands.sh",
    )

    for lib_path in expected_libraries:
        assert lib_path.exists()
        assert f'source "$FUZZ_LIB_DIR/{lib_path.name}"' in entrypoint

    assert "fuzz_atheris/targets.tsv" in (
        REPO_ROOT / "scripts" / "lib" / "fuzz_atheris" / "common.sh"
    ).read_text(encoding="utf-8")


def test_canonical_split_surfaces_are_git_tracked() -> None:
    """Canonical split surfaces and devcontainer workflow files must be tracked."""
    tracked_paths = {
        path.relative_to(REPO_ROOT).as_posix() for path in _git_tracked_repo_files()
    }
    expected: set[str] = set()
    patterns = (
        ".devcontainer/*",
        "docs/DEVELOPER_DEVCONTAINER.md",
        "scripts/devcontainer-prepare-user-home.sh",
        "scripts/validate-devcontainer.sh",
        "scripts/lib/fuzz_atheris/*.sh",
        "scripts/lib/fuzz_hypofuzz/*.sh",
        "fuzz_atheris/targets.tsv",
        "fuzz_atheris/fuzz_*_entry.py",
        "fuzz_atheris/fuzz_*_support.py",
        "fuzz_atheris/fuzz_*_patterns*.py",
        "fuzz_atheris/fuzz_*_builders.py",
        "fuzz_atheris/fuzz_*_scenarios.py",
        "fuzz_atheris/fuzz_*_mutators.py",
        "tests/*_cases/__init__.py",
        "tests/*_cases/*.py",
        "src/ftllexengine/parsing/text_normalization.py",
        "src/ftllexengine/runtime/locale_resolution.py",
        "src/ftllexengine/validation/resource_*.py",
        "src/ftllexengine/syntax/serializer_engine.py",
    )

    for pattern in patterns:
        expected.update(
            path.relative_to(REPO_ROOT).as_posix()
            for path in REPO_ROOT.glob(pattern)
            if path.is_file()
        )

    assert expected <= tracked_paths


def test_release_workflows_do_not_depend_on_node20_compatibility_shims() -> None:
    """Workflow pins must be natively Node 24-capable, not forced through overrides."""
    publish_workflow = (REPO_ROOT / ".github" / "workflows" / "publish.yml").read_text(
        encoding="utf-8"
    )
    test_workflow = (REPO_ROOT / ".github" / "workflows" / "test.yml").read_text(
        encoding="utf-8"
    )

    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24" not in publish_workflow
    assert "FORCE_JAVASCRIPT_ACTIONS_TO_NODE24" not in test_workflow

    assert (
        "codecov/codecov-action@75cd11691c0faa626561e295848008c8a7dddffe"
        not in publish_workflow
    )
    assert (
        "actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093"
        not in publish_workflow
    )

    assert (
        "codecov/codecov-action@57e3a136b779b570ffcdbf80b3bdc90e7fab3de2"
        in publish_workflow
    )
    assert publish_workflow.count(
        "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c"
    ) >= 3


def test_publish_workflow_requires_annotated_tags_without_signature_verification_gate() -> None:
    """The publish workflow should require annotated tags but not an external signing setup."""
    publish_workflow = (REPO_ROOT / ".github" / "workflows" / "publish.yml").read_text(
        encoding="utf-8"
    )

    assert "Resolve immutable annotated release tag" in publish_workflow
    assert "/git/ref/tags/" in publish_workflow
    assert "/git/tags/" in publish_workflow
    assert "Release tags must be annotated tag objects" in publish_workflow
    assert 'ref_object.get("type") != "tag"' in publish_workflow
    assert "Release tag must point to a commit object" in publish_workflow
    assert "Release tag signature is not verified by GitHub" not in publish_workflow
    assert 'verification = tag_object.get("verification")' not in publish_workflow
