# mypy: ignore-errors
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import ftllexengine
from ftllexengine.core.locale_utils import normalize_locale
from ftllexengine.enums import LoadStatus
from ftllexengine.localization import (
    FallbackInfo,
    FluentLocalization,
    LoadSummary,
    LocalizationBootConfig,
    LocalizationCacheStats,
    PathResourceLoader,
    ResourceLoader,
    ResourceLoadResult,
)
from ftllexengine.syntax.ast import Message


class TestPathResourceLoaderResolvedRoot:
    """PathResourceLoader._resolved_root falls back to cwd when no static prefix."""

    def test_resolved_root_fallback_to_cwd(self) -> None:
        """Pattern with no static path prefix resolves root to current working directory."""
        loader = PathResourceLoader("{locale}")
        expected = Path.cwd().resolve()
        assert loader._resolved_root == expected  # pylint: disable=protected-access

class TestPathResourceLoaderSecurity:
    """PathResourceLoader rejects path traversal and absolute path inputs."""

    def test_load_rejects_absolute_path(self) -> None:
        """Absolute path resource_id raises ValueError."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match="Absolute paths not allowed"):
            loader.load("en", "/etc/passwd")

    def test_load_rejects_absolute_path_posix_style(self) -> None:
        """POSIX absolute path resource_id raises ValueError."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match="Absolute paths not allowed"):
            loader.load("en", "/usr/local/etc/passwd")

    def test_load_rejects_parent_directory_traversal(self) -> None:
        """'..' sequences in resource_id raise ValueError."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match="Path traversal sequences not allowed"):
            loader.load("en", "../../../etc/passwd")

    def test_load_rejects_parent_directory_in_middle(self) -> None:
        """'..' in the middle of a resource_id path raises ValueError."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match="Path traversal sequences not allowed"):
            loader.load("en", "foo/../bar/../secrets.ftl")

    def test_load_rejects_path_starting_with_forward_slash(self) -> None:
        """resource_id starting with '/' is rejected as absolute or separator-prefixed.

        On Unix, /messages.ftl is caught as an absolute path first.
        On Windows with forward slash it may be caught by the separator check.
        """
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match=r"(Absolute|separator)"):
            loader.load("en", "/messages.ftl")

    def test_load_rejects_path_starting_with_backslash(self) -> None:
        """resource_id starting with '\\' is rejected."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match="not allowed in resource_id"):
            loader.load("en", "\\messages.ftl")

    def test_load_detects_symlink_escape_via_is_safe_path(self) -> None:
        """Symlink pointing outside the base directory is rejected by _is_safe_path."""

        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            locale_dir = base_path / "locales" / "en"
            locale_dir.mkdir(parents=True)

            outside_dir = base_path / "outside"
            outside_dir.mkdir()
            secret_file = outside_dir / "secret.ftl"
            secret_file.write_text("secret = Secret data")

            symlink_path = locale_dir / "escape.ftl"
            try:
                symlink_path.symlink_to(secret_file)

                loader = PathResourceLoader(str(base_path / "locales" / "{locale}"))

                with pytest.raises(ValueError, match="Path traversal detected"):
                    loader.load("en", "escape.ftl")
            except OSError:
                pytest.skip("Symlink creation not supported on this system")

class TestPathResourceLoaderValidation:
    """PathResourceLoader accepts valid resource_ids and rejects malformed ones."""

    def test_load_with_valid_resource_id(self) -> None:
        """Valid resource_id loads file content correctly."""

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            locale_dir = base / "locales" / "en"
            locale_dir.mkdir(parents=True)

            test_file = locale_dir / "messages.ftl"
            test_file.write_text("hello = Hello, World!")

            loader = PathResourceLoader(str(base / "locales" / "{locale}"))
            content = loader.load("en", "messages.ftl")

            assert "Hello, World!" in content

    def test_load_with_subdirectory_resource_id(self) -> None:
        """Subdirectory in resource_id resolves to nested path correctly."""

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            locale_dir = base / "locales" / "en" / "ui"
            locale_dir.mkdir(parents=True)

            test_file = locale_dir / "buttons.ftl"
            test_file.write_text("save = Save")

            loader = PathResourceLoader(str(base / "locales" / "{locale}"))
            content = loader.load("en", "ui/buttons.ftl")

            assert "Save" in content

    def test_validate_resource_id_validates_before_path_resolution(self) -> None:
        """Validation rejects malformed resource_ids before any filesystem operations."""
        loader = PathResourceLoader("locales/{locale}")

        invalid_ids = [
            "/absolute/path.ftl",
            "..\\parent\\path.ftl",
            "..\\..\\..\\escape.ftl",
            "\\windows\\path.ftl",
        ]

        for invalid_id in invalid_ids:
            with pytest.raises(ValueError, match=r"(Absolute|traversal|separator)"):
                loader.load("en", invalid_id)

class TestPathResourceLoaderLocaleValidation:
    """PathResourceLoader rejects locale codes containing path traversal sequences."""

    def test_load_rejects_locale_with_parent_traversal(self) -> None:
        """'..' in locale code raises ValueError."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match=r"Invalid locale: '../../../etc'"):
            loader.load("../../../etc", "messages.ftl")

    def test_load_rejects_locale_with_embedded_traversal(self) -> None:
        """'..' embedded within locale code raises ValueError."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match=r"Invalid locale: 'en/\.\./de'"):
            loader.load("en/../de", "messages.ftl")

    def test_load_rejects_locale_with_forward_slash(self) -> None:
        """'/' in locale code raises ValueError."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match=r"Invalid locale: 'en/attack'"):
            loader.load("en/attack", "messages.ftl")

    def test_load_rejects_locale_with_backslash(self) -> None:
        """'\\' in locale code raises ValueError."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match=r"Invalid locale: 'en\\\\attack'"):
            loader.load("en\\attack", "messages.ftl")

    def test_load_rejects_empty_locale(self) -> None:
        """Empty locale code raises ValueError."""
        loader = PathResourceLoader("locales/{locale}")

        with pytest.raises(ValueError, match="locale cannot be blank"):
            loader.load("", "messages.ftl")

    def test_load_accepts_valid_locale_codes(self) -> None:
        """Standard BCP 47-style locale codes are accepted."""

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)

            valid_locales = ["en", "en_US", "de_DE", "lv_LV", "zh_Hans_CN"]

            for locale in valid_locales:
                locale_dir = base / "locales" / normalize_locale(locale)
                locale_dir.mkdir(parents=True, exist_ok=True)
                test_file = locale_dir / "test.ftl"
                test_file.write_text(f"msg = Test for {locale}")

            loader = PathResourceLoader(str(base / "locales" / "{locale}"))

            for locale in valid_locales:
                content = loader.load(locale, "test.ftl")
                assert f"Test for {locale}" in content

    def test_root_dir_parameter_provides_fixed_anchor(self) -> None:
        """root_dir anchors path validation independently of the locale parameter."""

        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            locale_dir = base / "locales" / "en"
            locale_dir.mkdir(parents=True)
            test_file = locale_dir / "test.ftl"
            test_file.write_text("msg = Test")

            loader = PathResourceLoader(
                str(base / "locales" / "{locale}"),
                root_dir=str(base),
            )

            content = loader.load("en", "test.ftl")
            assert "Test" in content

    def test_root_dir_prevents_locale_escape_attempt(self) -> None:
        """root_dir constrains path validation to a fixed boundary.

        When a symlink inside the locale directory resolves to a file
        outside root_dir, the loader raises ValueError even though the
        resource_id itself contains no traversal sequences.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            locale_dir = base / "locales" / "en"
            locale_dir.mkdir(parents=True)
            (locale_dir / "test.ftl").write_text("msg = Test")

            outside = base / "outside"
            outside.mkdir()
            secret = outside / "secret.ftl"
            secret.write_text("secret = Should not access")

            loader = PathResourceLoader(
                str(base / "locales" / "{locale}"),
                root_dir=str(base / "locales"),
            )

            # Normal load within root_dir succeeds
            content = loader.load("en", "test.ftl")
            assert "Test" in content

            # Symlink from within locale dir to a file outside root_dir
            escape_link = locale_dir / "escape.ftl"
            try:
                escape_link.symlink_to(secret)
                # The resource_id has no '..' but the resolved path escapes root_dir
                with pytest.raises(ValueError, match="Path traversal detected"):
                    loader.load("en", "escape.ftl")
            except OSError:
                pytest.skip("Symlink creation not supported on this system")

class TestLocalizationBootTypesFacadeExport:
    """Boot evidence types and loaders are accessible from the root facade."""

    def test_load_status_accessible_from_root_facade(self) -> None:
        """LoadStatus enum is exported from ftllexengine root facade."""
        assert ftllexengine.LoadStatus is LoadStatus

    def test_load_status_in_root_all(self) -> None:
        """LoadStatus is listed in ftllexengine.__all__."""
        assert "LoadStatus" in ftllexengine.__all__

    def test_fallback_info_accessible_from_root_facade(self) -> None:
        """FallbackInfo is exported from ftllexengine root facade."""
        assert ftllexengine.FallbackInfo is FallbackInfo

    def test_load_summary_accessible_from_root_facade(self) -> None:
        """LoadSummary is exported from ftllexengine root facade."""
        assert ftllexengine.LoadSummary is LoadSummary

    def test_resource_load_result_accessible_from_root_facade(self) -> None:
        """ResourceLoadResult is exported from ftllexengine root facade."""
        assert ftllexengine.ResourceLoadResult is ResourceLoadResult

    def test_resource_loader_accessible_from_root_facade(self) -> None:
        """ResourceLoader Protocol is exported from ftllexengine root facade."""
        assert ftllexengine.ResourceLoader is ResourceLoader

    def test_path_resource_loader_accessible_from_root_facade(self) -> None:
        """PathResourceLoader is exported from ftllexengine root facade."""
        assert ftllexengine.PathResourceLoader is PathResourceLoader

    def test_localization_boot_config_accessible_from_root_facade(self) -> None:
        """LocalizationBootConfig is exported from ftllexengine root facade."""
        assert ftllexengine.LocalizationBootConfig is LocalizationBootConfig

    def test_localization_cache_stats_accessible_from_root_facade(self) -> None:
        """LocalizationCacheStats is exported from ftllexengine root facade."""
        assert ftllexengine.LocalizationCacheStats is LocalizationCacheStats

    def test_boot_types_in_root_all(self) -> None:
        """All boot evidence types are listed in ftllexengine.__all__."""
        for name in (
            "FallbackInfo",
            "LoadSummary",
            "LocalizationBootConfig",
            "LocalizationCacheStats",
            "PathResourceLoader",
            "ResourceLoadResult",
            "ResourceLoader",
        ):
            assert name in ftllexengine.__all__, f"{name!r} missing from ftllexengine.__all__"

class TestFluentLocalizationAddResourceStream:
    """FluentLocalization.add_resource_stream incremental resource loading."""

    def test_loads_message_from_line_list(self) -> None:
        """add_resource_stream registers messages for a locale."""
        l10n = FluentLocalization(
            locales=("en",),
            resource_ids=(),
        )
        l10n.add_resource_stream("en", ["greeting = Hello\n"])
        result, errors = l10n.format_pattern("greeting")
        assert errors == ()
        assert result == "Hello"

    def test_invalid_locale_raises(self) -> None:
        """Locale not in fallback chain raises ValueError."""
        l10n = FluentLocalization(locales=("en",), resource_ids=())
        with pytest.raises(ValueError, match="not in fallback chain"):
            l10n.add_resource_stream("de", ["msg = Value\n"])

    def test_returns_empty_junk_on_clean_source(self) -> None:
        """Clean stream returns empty junk tuple."""
        l10n = FluentLocalization(locales=("en",), resource_ids=())
        junk = l10n.add_resource_stream("en", ["msg = Value\n"])
        assert junk == ()

    def test_source_path_accepted(self) -> None:
        """source_path kwarg threads through without error."""
        l10n = FluentLocalization(locales=("en",), resource_ids=())
        l10n.add_resource_stream(
            "en", ["msg = Value\n"], source_path="locales/en/ui.ftl"
        )
        result, _ = l10n.format_pattern("msg")
        assert result == "Value"

    def test_multiple_messages_from_stream(self) -> None:
        """Multiple messages from a stream are all registered."""
        l10n = FluentLocalization(locales=("en",), resource_ids=())
        l10n.add_resource_stream("en", ["msg1 = One\n", "\n", "msg2 = Two\n"])
        r1, _ = l10n.format_pattern("msg1")
        r2, _ = l10n.format_pattern("msg2")
        assert r1 == "One"
        assert r2 == "Two"

    def test_equivalence_with_add_resource(self) -> None:
        """add_resource_stream produces same result as add_resource for same content."""
        source = "msg = Hello\n"
        l1 = FluentLocalization(locales=("en",), resource_ids=())
        l1.add_resource("en", source)
        l2 = FluentLocalization(locales=("en",), resource_ids=())
        l2.add_resource_stream("en", source.splitlines(keepends=True))
        r1, e1 = l1.format_pattern("msg")
        r2, e2 = l2.format_pattern("msg")
        assert r1 == r2
        assert e1 == e2

    def test_second_call_reuses_existing_bundle(self) -> None:
        """Second add_resource_stream call for same locale reuses the existing bundle.

        The first call creates the bundle lazily; the second call must take the
        branch where the bundle already exists in _bundles (line 734->736 coverage).
        """
        l10n = FluentLocalization(locales=("en",), resource_ids=())
        l10n.add_resource_stream("en", ["msg1 = First\n"])
        l10n.add_resource_stream("en", ["msg2 = Second\n"])
        r1, e1 = l10n.format_pattern("msg1")
        r2, e2 = l10n.format_pattern("msg2")
        assert r1 == "First"
        assert r2 == "Second"
        assert e1 == ()
        assert e2 == ()

class TestParseStreamFtlFacade:
    """parse_stream_ftl is accessible from root facade."""

    def test_accessible_from_root(self) -> None:
        """parse_stream_ftl is importable from ftllexengine."""
        assert hasattr(ftllexengine, "parse_stream_ftl")
        assert callable(ftllexengine.parse_stream_ftl)

    def test_in_root_all(self) -> None:
        """parse_stream_ftl is listed in ftllexengine.__all__."""
        assert "parse_stream_ftl" in ftllexengine.__all__

    def test_yields_entries_from_lines(self) -> None:
        """parse_stream_ftl yields Message entries from line list."""
        entries = list(ftllexengine.parse_stream_ftl(["greeting = Hello\n"]))
        assert len(entries) == 1
        assert isinstance(entries[0], Message)
        assert entries[0].id.name == "greeting"
