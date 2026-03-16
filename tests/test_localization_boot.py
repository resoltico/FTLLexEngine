"""Tests for localization/boot.py (LocalizationBootConfig).

Covers:
- __post_init__ validation (empty locales, resource_ids, missing loader/base_path,
  both loader and base_path provided)
- _resolve_loader (loader passthrough, base_path -> PathResourceLoader)
- boot() success path with an in-memory loader
- boot() raises IntegrityCheckFailedError on load failures (require_clean)
- boot() raises IntegrityCheckFailedError on schema mismatches
- boot_with_summary() returns (FluentLocalization, LoadSummary, schema_results)
- from_path() factory with str and Path inputs
- boot() with message_schemas=None skips schema validation

Python 3.13+.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ftllexengine.integrity import IntegrityCheckFailedError
from ftllexengine.localization import (
    FluentLocalization,
    LoadSummary,
    LocalizationBootConfig,
    PathResourceLoader,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class DictLoader:
    """In-memory ResourceLoader backed by a dict for testing."""

    def __init__(self, resources: dict[tuple[str, str], str]) -> None:
        self._resources = resources

    def load(self, locale: str, resource_id: str) -> str:
        """Return FTL source or raise FileNotFoundError."""
        result = self._resources.get((locale, resource_id))
        if result is None:
            msg = f"No resource for ({locale!r}, {resource_id!r})"
            raise FileNotFoundError(msg)
        return result

    def describe_path(self, locale: str, resource_id: str) -> str:
        """Return a synthetic path for diagnostics."""
        return f"memory://{locale}/{resource_id}"


def _make_loader(
    locales: tuple[str, ...],
    resource_ids: tuple[str, ...],
    ftl: str = "greeting = Hello",
) -> DictLoader:
    """Build a DictLoader where every locale/resource pair maps to ftl."""
    resources = {(loc, rid): ftl for loc in locales for rid in resource_ids}
    return DictLoader(resources)


# ===========================================================================
# __post_init__ validation
# ===========================================================================


class TestLocalizationBootConfigValidation:
    """LocalizationBootConfig enforces invariants at construction time."""

    def test_empty_locales_raises(self) -> None:
        """Empty locales tuple raises ValueError."""
        loader = DictLoader({})
        with pytest.raises(ValueError, match="locales"):
            LocalizationBootConfig(
                locales=(),
                resource_ids=("ui.ftl",),
                loader=loader,
            )

    def test_empty_resource_ids_raises(self) -> None:
        """Empty resource_ids tuple raises ValueError."""
        loader = DictLoader({})
        with pytest.raises(ValueError, match="resource_ids"):
            LocalizationBootConfig(
                locales=("en",),
                resource_ids=(),
                loader=loader,
            )

    def test_neither_loader_nor_base_path_raises(self) -> None:
        """Providing neither loader nor base_path raises ValueError."""
        with pytest.raises(ValueError, match=r"loader.*base_path|base_path.*loader"):
            LocalizationBootConfig(
                locales=("en",),
                resource_ids=("ui.ftl",),
            )

    def test_both_loader_and_base_path_raises(self) -> None:
        """Providing both loader and base_path raises ValueError."""
        loader = DictLoader({})
        with pytest.raises(ValueError, match="not both"):
            LocalizationBootConfig(
                locales=("en",),
                resource_ids=("ui.ftl",),
                loader=loader,
                base_path="locales/{locale}",
            )

    def test_valid_config_with_loader(self) -> None:
        """Valid config with loader constructs without error."""
        loader = DictLoader({})
        cfg = LocalizationBootConfig(
            locales=("en",),
            resource_ids=("ui.ftl",),
            loader=loader,
        )
        assert cfg.locales == ("en",)
        assert cfg.resource_ids == ("ui.ftl",)

    def test_valid_config_with_base_path(self) -> None:
        """Valid config with base_path constructs without error."""
        cfg = LocalizationBootConfig(
            locales=("en",),
            resource_ids=("ui.ftl",),
            base_path="locales/{locale}",
        )
        assert cfg.base_path == "locales/{locale}"
        assert cfg.loader is None

    def test_config_is_frozen(self) -> None:
        """LocalizationBootConfig is immutable (frozen dataclass)."""
        loader = DictLoader({})
        cfg = LocalizationBootConfig(
            locales=("en",),
            resource_ids=("ui.ftl",),
            loader=loader,
        )
        with pytest.raises((AttributeError, TypeError)):
            cfg.locales = ("fr",)  # type: ignore[misc]


# ===========================================================================
# _resolve_loader
# ===========================================================================


class TestResolveLoader:
    """_resolve_loader returns the correct effective loader."""

    def test_loader_passthrough(self) -> None:
        """When loader is provided, _resolve_loader returns it directly."""
        loader = DictLoader({})
        cfg = LocalizationBootConfig(
            locales=("en",),
            resource_ids=("ui.ftl",),
            loader=loader,
        )
        assert cfg._resolve_loader() is loader

    def test_base_path_creates_path_resource_loader(self) -> None:
        """When base_path is provided, _resolve_loader returns a PathResourceLoader."""
        cfg = LocalizationBootConfig(
            locales=("en",),
            resource_ids=("ui.ftl",),
            base_path="locales/{locale}",
        )
        resolved = cfg._resolve_loader()
        assert isinstance(resolved, PathResourceLoader)
        assert resolved.base_path == "locales/{locale}"

    def test_base_path_without_locale_placeholder_fails_at_boot(self) -> None:
        """base_path without {locale} raises ValueError when PathResourceLoader is created."""
        cfg = LocalizationBootConfig(
            locales=("en",),
            resource_ids=("ui.ftl",),
            base_path="locales/static",
        )
        with pytest.raises(ValueError, match="locale"):
            cfg._resolve_loader()


# ===========================================================================
# boot() success path
# ===========================================================================


class TestLocalizationBootConfigBoot:
    """boot() assembles and validates a FluentLocalization."""

    def test_boot_returns_fluent_localization(self) -> None:
        """boot() returns a FluentLocalization instance on success."""
        locales = ("en",)
        resource_ids = ("ui.ftl",)
        loader = _make_loader(locales, resource_ids, "greeting = Hello")
        cfg = LocalizationBootConfig(
            locales=locales,
            resource_ids=resource_ids,
            loader=loader,
        )
        l10n = cfg.boot()
        assert isinstance(l10n, FluentLocalization)

    def test_boot_passes_strict_setting(self) -> None:
        """boot() forwards the strict setting to FluentLocalization."""
        locales = ("en",)
        resource_ids = ("ui.ftl",)
        loader = _make_loader(locales, resource_ids)
        cfg = LocalizationBootConfig(
            locales=locales,
            resource_ids=resource_ids,
            loader=loader,
            strict=False,
        )
        l10n = cfg.boot()
        assert l10n.strict is False

    def test_boot_multi_locale(self) -> None:
        """boot() supports multiple locales in fallback order."""
        locales = ("lv", "en")
        resource_ids = ("ui.ftl",)
        resources = {
            ("lv", "ui.ftl"): "greeting = Sveiki",
            ("en", "ui.ftl"): "greeting = Hello",
        }
        cfg = LocalizationBootConfig(
            locales=locales,
            resource_ids=resource_ids,
            loader=DictLoader(resources),
        )
        l10n = cfg.boot()
        assert l10n.locales == ("lv", "en")

    def test_boot_with_message_schemas_matching(self) -> None:
        """boot() succeeds when declared schemas match the actual messages."""
        locales = ("en",)
        resource_ids = ("ui.ftl",)
        ftl = "greeting = Hello, { $name }!"
        loader = _make_loader(locales, resource_ids, ftl)
        cfg = LocalizationBootConfig(
            locales=locales,
            resource_ids=resource_ids,
            loader=loader,
            message_schemas={"greeting": frozenset({"name"})},
        )
        l10n = cfg.boot()
        assert isinstance(l10n, FluentLocalization)

    def test_boot_without_message_schemas_skips_validation(self) -> None:
        """boot() with message_schemas=None does not call validate_message_schemas."""
        locales = ("en",)
        resource_ids = ("ui.ftl",)
        loader = _make_loader(locales, resource_ids, "msg = No variables")
        cfg = LocalizationBootConfig(
            locales=locales,
            resource_ids=resource_ids,
            loader=loader,
            message_schemas=None,
        )
        # Should not raise even if the message has no variables declared
        l10n = cfg.boot()
        assert isinstance(l10n, FluentLocalization)


# ===========================================================================
# boot() failure paths
# ===========================================================================


class TestLocalizationBootConfigBootFailures:
    """boot() raises IntegrityCheckFailedError on load or schema failures."""

    def test_boot_raises_on_missing_resource(self) -> None:
        """boot() raises IntegrityCheckFailedError when a resource file is missing."""
        loader = DictLoader({})  # no resources at all
        cfg = LocalizationBootConfig(
            locales=("en",),
            resource_ids=("ui.ftl",),
            loader=loader,
        )
        with pytest.raises(IntegrityCheckFailedError):
            cfg.boot()

    def test_boot_raises_on_schema_mismatch(self) -> None:
        """boot() raises IntegrityCheckFailedError when schemas do not match."""
        locales = ("en",)
        resource_ids = ("ui.ftl",)
        ftl = "greeting = Hello"  # no $name variable
        loader = _make_loader(locales, resource_ids, ftl)
        cfg = LocalizationBootConfig(
            locales=locales,
            resource_ids=resource_ids,
            loader=loader,
            message_schemas={"greeting": frozenset({"name"})},  # mismatch
        )
        with pytest.raises(IntegrityCheckFailedError):
            cfg.boot()

    def test_boot_raises_on_junk_syntax_error(self) -> None:
        """boot() raises IntegrityCheckFailedError when FTL resource has syntax errors.

        strict=False so syntax errors are captured as junk rather than raised as
        SyntaxIntegrityError during FluentLocalization.__init__(). require_clean()
        then raises IntegrityCheckFailedError on the captured junk.
        """
        locales = ("en",)
        resource_ids = ("ui.ftl",)
        ftl = "not valid ftl syntax !!!"
        loader = _make_loader(locales, resource_ids, ftl)
        cfg = LocalizationBootConfig(
            locales=locales,
            resource_ids=resource_ids,
            loader=loader,
            strict=False,
        )
        with pytest.raises(IntegrityCheckFailedError):
            cfg.boot()


# ===========================================================================
# boot_with_summary
# ===========================================================================


class TestLocalizationBootConfigBootWithSummary:
    """boot_with_summary() returns (FluentLocalization, LoadSummary, schema_results)."""

    def test_boot_with_summary_returns_three_tuple(self) -> None:
        """boot_with_summary() returns a 3-tuple on success."""
        locales = ("en",)
        resource_ids = ("ui.ftl",)
        ftl = "greeting = Hello, { $name }!"
        loader = _make_loader(locales, resource_ids, ftl)
        cfg = LocalizationBootConfig(
            locales=locales,
            resource_ids=resource_ids,
            loader=loader,
            message_schemas={"greeting": frozenset({"name"})},
        )
        l10n, summary, schema_results = cfg.boot_with_summary()

        assert isinstance(l10n, FluentLocalization)
        assert isinstance(summary, LoadSummary)
        assert isinstance(schema_results, tuple)
        assert len(schema_results) == 1

    def test_boot_with_summary_no_schemas_returns_empty_tuple(self) -> None:
        """boot_with_summary() returns empty schema_results when no schemas declared."""
        locales = ("en",)
        resource_ids = ("ui.ftl",)
        loader = _make_loader(locales, resource_ids)
        cfg = LocalizationBootConfig(
            locales=locales,
            resource_ids=resource_ids,
            loader=loader,
        )
        _, _, schema_results = cfg.boot_with_summary()
        assert schema_results == ()

    def test_boot_with_summary_load_summary_is_clean(self) -> None:
        """boot_with_summary() returns a LoadSummary with no errors on clean boot."""
        locales = ("en",)
        resource_ids = ("ui.ftl",)
        loader = _make_loader(locales, resource_ids, "msg = OK")
        cfg = LocalizationBootConfig(
            locales=locales,
            resource_ids=resource_ids,
            loader=loader,
        )
        _, summary, _ = cfg.boot_with_summary()
        assert summary.errors == 0
        assert summary.total_attempted > 0

    def test_boot_with_summary_raises_on_load_failure(self) -> None:
        """boot_with_summary() raises IntegrityCheckFailedError on load failure."""
        cfg = LocalizationBootConfig(
            locales=("en",),
            resource_ids=("missing.ftl",),
            loader=DictLoader({}),
        )
        with pytest.raises(IntegrityCheckFailedError):
            cfg.boot_with_summary()


# ===========================================================================
# from_path() factory
# ===========================================================================


class TestLocalizationBootConfigFromPath:
    """from_path() is a convenience factory for disk-based resources."""

    def test_from_path_with_string(self) -> None:
        """from_path() accepts a string path template."""
        cfg = LocalizationBootConfig.from_path(
            locales=("en",),
            resource_ids=("ui.ftl",),
            base_path="locales/{locale}",
        )
        assert cfg.base_path == "locales/{locale}"
        assert cfg.loader is None

    def test_from_path_with_path_object(self) -> None:
        """from_path() accepts a pathlib.Path and converts to POSIX string."""
        cfg = LocalizationBootConfig.from_path(
            locales=("en",),
            resource_ids=("ui.ftl",),
            base_path=Path("locales") / "{locale}",
        )
        assert "{locale}" in cfg.base_path  # type: ignore[operator]

    def test_from_path_forwards_optional_args(self) -> None:
        """from_path() forwards all optional arguments to LocalizationBootConfig."""
        cfg = LocalizationBootConfig.from_path(
            locales=("en",),
            resource_ids=("ui.ftl",),
            base_path="locales/{locale}",
            strict=False,
            use_isolating=False,
            message_schemas={"key": frozenset({"var"})},
        )
        assert cfg.strict is False
        assert cfg.use_isolating is False
        assert cfg.message_schemas == {"key": frozenset({"var"})}

    def test_from_path_empty_locales_raises(self) -> None:
        """from_path() propagates ValueError for empty locales."""
        with pytest.raises(ValueError, match="locales"):
            LocalizationBootConfig.from_path(
                locales=(),
                resource_ids=("ui.ftl",),
                base_path="locales/{locale}",
            )
