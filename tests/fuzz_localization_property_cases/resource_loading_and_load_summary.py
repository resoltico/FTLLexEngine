# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_localization_property.py."""

from tests.fuzz_localization_property_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# Resource loading and load summary
# ---------------------------------------------------------------------------


class TestFluentLocalizationResourceLoading:
    """Tests for resource loading and load summary."""

    @given(
        loader_tuple=resource_loaders(),
    )
    def test_load_summary_tracks_all_attempts(
        self,
        loader_tuple: tuple[
            DictResourceLoader | FailingResourceLoader,
            list[str],
            list[str],
        ],
    ) -> None:
        """get_load_summary reflects all load attempts from init."""
        loader, locales, resource_ids = loader_tuple
        event(f"locale_count={len(locales)}")
        l10n = FluentLocalization(
            locales, resource_ids, loader,
        )
        summary = l10n.get_load_summary()
        assert summary.total_attempted == len(locales) * len(resource_ids)

    @given(locales=locale_chains(min_size=1, max_size=3))
    def test_custom_loader_source_path_format(
        self, locales: list[str],
    ) -> None:
        """Non-PathResourceLoader uses locale/resource_id as source_path."""
        event("outcome=custom_loader_path")
        resources = {
            loc: {"main.ftl": f"msg = {loc}\n"}
            for loc in locales
        }
        loader = DictResourceLoader(resources)
        l10n = FluentLocalization(locales, ["main.ftl"], loader)
        summary = l10n.get_load_summary()
        for result in summary.results:
            # Custom loader uses "locale/resource_id" format
            assert "/" in result.source_path  # type: ignore[operator]

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_oserror_during_load_recorded_as_error(
        self, locales: list[str],
    ) -> None:
        """OSError during resource loading recorded with ERROR status."""
        event("outcome=oserror_recorded")
        loader = FailingResourceLoader(OSError, "Permission denied")
        l10n = FluentLocalization(locales, ["main.ftl"], loader)
        summary = l10n.get_load_summary()
        assert summary.errors > 0
        for result in summary.get_errors():
            assert isinstance(result.error, OSError)

    @given(locales=locale_chains(min_size=1, max_size=2))
    def test_valueerror_during_load_recorded_as_error(
        self, locales: list[str],
    ) -> None:
        """ValueError during resource loading recorded with ERROR status."""
        event("outcome=valueerror_recorded")
        loader = FailingResourceLoader(ValueError, "Path traversal")
        l10n = FluentLocalization(locales, ["main.ftl"], loader)
        summary = l10n.get_load_summary()
        assert summary.errors > 0
        for result in summary.get_errors():
            assert isinstance(result.error, ValueError)
