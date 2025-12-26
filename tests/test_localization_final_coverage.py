"""Final coverage tests for localization.py achieving 100%.

Covers LoadSummary, ResourceLoadResult, and edge cases in PathResourceLoader and FluentLocalization.

Python 3.13+.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from ftllexengine.localization import (
    FluentLocalization,
    LoadStatus,
    LoadSummary,
    PathResourceLoader,
    ResourceLoadResult,
)


class TestResourceLoadResultProperties:
    """Test ResourceLoadResult property methods."""

    def test_is_success_true(self) -> None:
        """is_success returns True when status is SUCCESS."""
        result = ResourceLoadResult(
            locale="en",
            resource_id="main.ftl",
            status=LoadStatus.SUCCESS,
        )
        assert result.is_success is True

    def test_is_success_false(self) -> None:
        """is_success returns False when status is not SUCCESS."""
        result = ResourceLoadResult(
            locale="en",
            resource_id="main.ftl",
            status=LoadStatus.NOT_FOUND,
        )
        assert result.is_success is False

    def test_is_not_found_true(self) -> None:
        """is_not_found returns True when status is NOT_FOUND."""
        result = ResourceLoadResult(
            locale="en",
            resource_id="main.ftl",
            status=LoadStatus.NOT_FOUND,
        )
        assert result.is_not_found is True

    def test_is_not_found_false(self) -> None:
        """is_not_found returns False when status is not NOT_FOUND."""
        result = ResourceLoadResult(
            locale="en",
            resource_id="main.ftl",
            status=LoadStatus.SUCCESS,
        )
        assert result.is_not_found is False

    def test_is_error_true(self) -> None:
        """is_error returns True when status is ERROR."""
        result = ResourceLoadResult(
            locale="en",
            resource_id="main.ftl",
            status=LoadStatus.ERROR,
            error=OSError("Permission denied"),
        )
        assert result.is_error is True

    def test_is_error_false(self) -> None:
        """is_error returns False when status is not ERROR."""
        result = ResourceLoadResult(
            locale="en",
            resource_id="main.ftl",
            status=LoadStatus.SUCCESS,
        )
        assert result.is_error is False


class TestLoadSummary:
    """Test LoadSummary calculation and methods."""

    def test_post_init_calculates_statistics(self) -> None:
        """__post_init__ calculates summary statistics correctly."""
        results = (
            ResourceLoadResult("en", "main.ftl", LoadStatus.SUCCESS),
            ResourceLoadResult("en", "errors.ftl", LoadStatus.SUCCESS),
            ResourceLoadResult("de", "main.ftl", LoadStatus.NOT_FOUND),
            ResourceLoadResult("fr", "main.ftl", LoadStatus.ERROR, error=OSError("fail")),
        )
        summary = LoadSummary(results=results)

        assert summary.total_attempted == 4
        assert summary.successful == 2
        assert summary.not_found == 1
        assert summary.errors == 1

    def test_get_errors(self) -> None:
        """get_errors returns only results with ERROR status."""
        results = (
            ResourceLoadResult("en", "main.ftl", LoadStatus.SUCCESS),
            ResourceLoadResult("de", "main.ftl", LoadStatus.ERROR, error=OSError("fail1")),
            ResourceLoadResult("fr", "main.ftl", LoadStatus.ERROR, error=ValueError("fail2")),
        )
        summary = LoadSummary(results=results)
        errors = summary.get_errors()

        assert len(errors) == 2
        assert all(r.is_error for r in errors)

    def test_get_not_found(self) -> None:
        """get_not_found returns only results with NOT_FOUND status."""
        results = (
            ResourceLoadResult("en", "main.ftl", LoadStatus.SUCCESS),
            ResourceLoadResult("de", "main.ftl", LoadStatus.NOT_FOUND),
            ResourceLoadResult("fr", "main.ftl", LoadStatus.NOT_FOUND),
        )
        summary = LoadSummary(results=results)
        not_found = summary.get_not_found()

        assert len(not_found) == 2
        assert all(r.is_not_found for r in not_found)

    def test_get_successful(self) -> None:
        """get_successful returns only results with SUCCESS status."""
        results = (
            ResourceLoadResult("en", "main.ftl", LoadStatus.SUCCESS),
            ResourceLoadResult("en", "errors.ftl", LoadStatus.SUCCESS),
            ResourceLoadResult("de", "main.ftl", LoadStatus.NOT_FOUND),
        )
        summary = LoadSummary(results=results)
        successful = summary.get_successful()

        assert len(successful) == 2
        assert all(r.is_success for r in successful)

    def test_get_by_locale(self) -> None:
        """get_by_locale returns only results for specified locale."""
        results = (
            ResourceLoadResult("en", "main.ftl", LoadStatus.SUCCESS),
            ResourceLoadResult("en", "errors.ftl", LoadStatus.SUCCESS),
            ResourceLoadResult("de", "main.ftl", LoadStatus.NOT_FOUND),
            ResourceLoadResult("fr", "main.ftl", LoadStatus.ERROR, error=OSError("fail")),
        )
        summary = LoadSummary(results=results)
        en_results = summary.get_by_locale("en")

        assert len(en_results) == 2
        assert all(r.locale == "en" for r in en_results)

    def test_has_errors_true(self) -> None:
        """has_errors returns True when errors > 0."""
        results = (
            ResourceLoadResult("en", "main.ftl", LoadStatus.SUCCESS),
            ResourceLoadResult("de", "main.ftl", LoadStatus.ERROR, error=OSError("fail")),
        )
        summary = LoadSummary(results=results)

        assert summary.has_errors is True

    def test_has_errors_false(self) -> None:
        """has_errors returns False when errors == 0."""
        results = (
            ResourceLoadResult("en", "main.ftl", LoadStatus.SUCCESS),
            ResourceLoadResult("de", "main.ftl", LoadStatus.NOT_FOUND),
        )
        summary = LoadSummary(results=results)

        assert summary.has_errors is False

    def test_all_successful_true(self) -> None:
        """all_successful returns True when all loads succeeded."""
        results = (
            ResourceLoadResult("en", "main.ftl", LoadStatus.SUCCESS),
            ResourceLoadResult("en", "errors.ftl", LoadStatus.SUCCESS),
        )
        summary = LoadSummary(results=results)

        assert summary.all_successful is True

    def test_all_successful_false_with_errors(self) -> None:
        """all_successful returns False when errors exist."""
        results = (
            ResourceLoadResult("en", "main.ftl", LoadStatus.SUCCESS),
            ResourceLoadResult("de", "main.ftl", LoadStatus.ERROR, error=OSError("fail")),
        )
        summary = LoadSummary(results=results)

        assert summary.all_successful is False

    def test_all_successful_false_with_not_found(self) -> None:
        """all_successful returns False when not_found exists."""
        results = (
            ResourceLoadResult("en", "main.ftl", LoadStatus.SUCCESS),
            ResourceLoadResult("de", "main.ftl", LoadStatus.NOT_FOUND),
        )
        summary = LoadSummary(results=results)

        assert summary.all_successful is False


class TestFluentLocalizationGetLoadSummary:
    """Test FluentLocalization.get_load_summary() method."""

    def test_get_load_summary_with_successful_loads(self) -> None:
        """get_load_summary returns LoadSummary with load results."""
        with TemporaryDirectory() as tmpdir:
            # Create test FTL files
            en_dir = Path(tmpdir) / "en"
            en_dir.mkdir()
            (en_dir / "main.ftl").write_text("hello = Hello")

            loader = PathResourceLoader(f"{tmpdir}/{{locale}}")
            l10n = FluentLocalization(["en"], ["main.ftl"], loader)

            summary = l10n.get_load_summary()

            assert isinstance(summary, LoadSummary)
            assert summary.total_attempted >= 1
            assert summary.successful >= 1

    def test_get_load_summary_with_not_found(self) -> None:
        """get_load_summary includes NOT_FOUND results."""
        with TemporaryDirectory() as tmpdir:
            # Create only en locale, de will be not found
            en_dir = Path(tmpdir) / "en"
            en_dir.mkdir()
            (en_dir / "main.ftl").write_text("hello = Hello")

            loader = PathResourceLoader(f"{tmpdir}/{{locale}}")
            l10n = FluentLocalization(["en", "de"], ["main.ftl"], loader)

            summary = l10n.get_load_summary()

            assert summary.not_found >= 1
            not_found = summary.get_not_found()
            assert any(r.locale == "de" for r in not_found)


class TestPathResourceLoaderGetRootDirFallback:
    """Test PathResourceLoader._get_root_dir edge case fallback."""

    def test_get_root_dir_no_static_prefix_fallback(self) -> None:
        """_get_root_dir returns cwd when no static prefix before {locale}."""
        # Edge case: base_path starts with {locale}
        loader = PathResourceLoader("{locale}/messages")

        root_dir = loader._get_root_dir()

        # Should fall back to current working directory
        assert root_dir == Path.cwd().resolve()


class TestFluentLocalizationResourceLoadingErrors:
    """Test error handling during resource loading."""

    def test_resource_loading_oserror_recorded(self) -> None:
        """OSError during resource loading is recorded in load results."""
        # Create a mock loader that raises OSError
        class FailingLoader:
            def load(self, locale: str, _resource_id: str) -> str:
                if locale == "de":
                    msg = "Permission denied"
                    raise OSError(msg)
                return "hello = Hello"

        loader = FailingLoader()
        l10n = FluentLocalization(["en", "de"], ["main.ftl"], loader)

        summary = l10n.get_load_summary()

        assert summary.errors >= 1
        errors = summary.get_errors()
        assert any(r.locale == "de" and isinstance(r.error, OSError) for r in errors)

    def test_resource_loading_valueerror_recorded(self) -> None:
        """ValueError during resource loading is recorded in load results."""
        # Create a mock loader that raises ValueError
        class FailingLoader:
            def load(self, locale: str, _resource_id: str) -> str:
                if locale == "fr":
                    msg = "Path traversal detected"
                    raise ValueError(msg)
                return "hello = Hello"

        loader = FailingLoader()
        l10n = FluentLocalization(["en", "fr"], ["main.ftl"], loader)

        summary = l10n.get_load_summary()

        assert summary.errors >= 1
        errors = summary.get_errors()
        assert any(r.locale == "fr" and isinstance(r.error, ValueError) for r in errors)
