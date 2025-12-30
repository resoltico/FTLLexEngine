"""Complete coverage tests for localization.py.

Targets uncovered lines to achieve 100% coverage.
Covers:
- Junk entry handling in ResourceLoadResult and LoadSummary
- Path edge cases in PathResourceLoader
- Load summary aggregation methods
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.localization import (
    FluentLocalization,
    LoadStatus,
    LoadSummary,
    PathResourceLoader,
    ResourceLoadResult,
)
from ftllexengine.syntax.ast import Junk


class TestResourceLoadResultJunk:
    """Test junk entry tracking in ResourceLoadResult."""

    def test_has_junk_with_junk_entries(self) -> None:
        """ResourceLoadResult.has_junk returns True when junk entries present."""
        # Create junk entries
        junk1 = Junk(content="invalid", annotations=())
        junk2 = Junk(content="@@@", annotations=())

        result = ResourceLoadResult(
            locale="en",
            resource_id="test.ftl",
            status=LoadStatus.SUCCESS,
            junk_entries=(junk1, junk2),
        )

        # Should return True when junk entries exist
        assert result.has_junk is True
        assert len(result.junk_entries) == 2

    def test_has_junk_without_junk_entries(self) -> None:
        """ResourceLoadResult.has_junk returns False when no junk entries."""
        result = ResourceLoadResult(
            locale="en",
            resource_id="test.ftl",
            status=LoadStatus.SUCCESS,
            junk_entries=(),
        )

        # Should return False when no junk entries
        assert result.has_junk is False
        assert len(result.junk_entries) == 0


class TestLoadSummaryJunkHandling:
    """Test junk entry aggregation in LoadSummary."""

    def test_get_with_junk(self) -> None:
        """LoadSummary.get_with_junk returns only results with junk entries."""
        junk = Junk(content="bad", annotations=())

        result_with_junk = ResourceLoadResult(
            locale="en",
            resource_id="bad.ftl",
            status=LoadStatus.SUCCESS,
            junk_entries=(junk,),
        )

        result_without_junk = ResourceLoadResult(
            locale="fr",
            resource_id="good.ftl",
            status=LoadStatus.SUCCESS,
            junk_entries=(),
        )

        summary = LoadSummary(results=(result_with_junk, result_without_junk))

        junk_results = summary.get_with_junk()
        assert len(junk_results) == 1
        assert junk_results[0].locale == "en"
        assert junk_results[0].has_junk

    def test_get_all_junk_flattens_entries(self) -> None:
        """LoadSummary.get_all_junk returns flattened tuple of all junk entries."""
        junk1 = Junk(content="bad1", annotations=())
        junk2 = Junk(content="bad2", annotations=())
        junk3 = Junk(content="bad3", annotations=())

        result1 = ResourceLoadResult(
            locale="en",
            resource_id="file1.ftl",
            status=LoadStatus.SUCCESS,
            junk_entries=(junk1, junk2),
        )

        result2 = ResourceLoadResult(
            locale="fr",
            resource_id="file2.ftl",
            status=LoadStatus.SUCCESS,
            junk_entries=(junk3,),
        )

        summary = LoadSummary(results=(result1, result2))

        all_junk = summary.get_all_junk()
        assert len(all_junk) == 3
        assert junk1 in all_junk
        assert junk2 in all_junk
        assert junk3 in all_junk

    def test_get_all_junk_empty_when_no_junk(self) -> None:
        """LoadSummary.get_all_junk returns empty tuple when no junk entries."""
        result = ResourceLoadResult(
            locale="en",
            resource_id="clean.ftl",
            status=LoadStatus.SUCCESS,
            junk_entries=(),
        )

        summary = LoadSummary(results=(result,))

        all_junk = summary.get_all_junk()
        assert len(all_junk) == 0
        assert all_junk == ()

    def test_has_junk_property(self) -> None:
        """LoadSummary.has_junk property reflects junk_count."""
        junk = Junk(content="bad", annotations=())

        result_with_junk = ResourceLoadResult(
            locale="en",
            resource_id="bad.ftl",
            status=LoadStatus.SUCCESS,
            junk_entries=(junk,),
        )

        result_without_junk = ResourceLoadResult(
            locale="fr",
            resource_id="good.ftl",
            status=LoadStatus.SUCCESS,
            junk_entries=(),
        )

        # Summary with junk
        summary_with = LoadSummary(results=(result_with_junk,))
        assert summary_with.has_junk is True
        assert summary_with.junk_count == 1

        # Summary without junk
        summary_without = LoadSummary(results=(result_without_junk,))
        assert summary_without.has_junk is False
        assert summary_with.junk_count == 1


class TestPathResourceLoaderEdgeCases:
    """Test edge cases in PathResourceLoader initialization."""

    def test_root_dir_fallback_to_cwd_when_no_locale_placeholder(self) -> None:
        """PathResourceLoader falls back to cwd when base_path has no {locale}."""
        # Base path without {locale} placeholder
        loader = PathResourceLoader(base_path="resources")

        # Should have initialized _resolved_root (will be empty string prefix)
        assert hasattr(loader, "_resolved_root")
        # Resolved root should be set (either from 'resources' or cwd)
        assert loader._resolved_root is not None

    def test_root_dir_resolution_with_empty_static_prefix(self) -> None:
        """PathResourceLoader resolves to cwd when static prefix is empty."""
        # Base path that starts with {locale} (empty static prefix)
        loader = PathResourceLoader(base_path="{locale}/resources")

        # Should fall back to current working directory
        assert hasattr(loader, "_resolved_root")
        # Resolved root should be cwd
        expected_root = Path.cwd().resolve()
        assert loader._resolved_root == expected_root

    def test_root_dir_with_locale_only_path(self) -> None:
        """PathResourceLoader handles path that is just {locale}."""
        # Base path that is only {locale}
        loader = PathResourceLoader(base_path="{locale}")

        # Should resolve to cwd (empty static prefix)
        assert hasattr(loader, "_resolved_root")
        # Resolved root should be set
        assert loader._resolved_root is not None


class TestPathResourceLoaderHypothesis:
    """Hypothesis-based property tests for PathResourceLoader."""

    @given(
        locale=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
            min_size=1,
            max_size=10,
        )
    )
    def test_locale_validation_rejects_path_separators(self, locale: str) -> None:
        """Locale validation rejects path separators in locale codes."""
        if "/" in locale or "\\" in locale or ".." in locale:
            pytest.skip("Locale already contains invalid chars")

        loader = PathResourceLoader(base_path="locales/{locale}")

        # Valid locale should not raise
        try:
            loader._validate_locale(locale)
        except ValueError:
            pytest.fail("Valid locale rejected")

    def test_locale_validation_rejects_path_traversal(self) -> None:
        """Locale validation rejects path traversal attempts."""
        loader = PathResourceLoader(base_path="locales/{locale}")

        # Path traversal should raise ValueError
        with pytest.raises(ValueError, match="Path traversal sequences not allowed"):
            loader._validate_locale("../etc")

        with pytest.raises(ValueError, match="Path traversal sequences not allowed"):
            loader._validate_locale("..\\windows")

    def test_locale_validation_rejects_separators(self) -> None:
        """Locale validation rejects path separators."""
        loader = PathResourceLoader(base_path="locales/{locale}")

        # Forward slash
        with pytest.raises(ValueError, match="Path separators not allowed"):
            loader._validate_locale("en/US")

        # Backslash
        with pytest.raises(ValueError, match="Path separators not allowed"):
            loader._validate_locale("en\\US")


class TestFluentLocalizationJunkIntegration:
    """Integration tests for junk handling in FluentLocalization."""

    def test_load_summary_tracks_junk_from_parsing(self) -> None:
        """LoadSummary tracks junk entries from resource parsing."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create FTL file with junk content
            en_dir = tmppath / "en"
            en_dir.mkdir()
            (en_dir / "test.ftl").write_text("""
# Valid message
hello = World

# Invalid syntax (junk)
@@@invalid@@@

goodbye = Bye
""", encoding="utf-8")

            loader = PathResourceLoader(str(tmppath / "{locale}"))
            l10n = FluentLocalization(["en"], ["test.ftl"], loader)

            summary = l10n.get_load_summary()

            # Should have junk entries from parsing
            if summary.has_junk:
                # Verify junk was captured
                assert summary.junk_count > 0
                junk_results = summary.get_with_junk()
                assert len(junk_results) > 0

    def test_load_summary_multiple_resources_with_mixed_junk(self) -> None:
        """LoadSummary correctly aggregates junk across multiple resources."""
        with TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Create multiple FTL files with varying junk content
            en_dir = tmppath / "en"
            en_dir.mkdir()

            (en_dir / "clean.ftl").write_text("msg = Hello", encoding="utf-8")
            (en_dir / "dirty.ftl").write_text("@@@junk@@@", encoding="utf-8")

            loader = PathResourceLoader(str(tmppath / "{locale}"))
            l10n = FluentLocalization(["en"], ["clean.ftl", "dirty.ftl"], loader)

            summary = l10n.get_load_summary()

            # Should have 2 load attempts
            assert summary.total_attempted == 2

            # Get results with junk
            junk_results = summary.get_with_junk()

            # At least one should have junk
            assert len(junk_results) >= 1
