# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_localization_property.py."""

from tests.fuzz_localization_property_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# Cache stats aggregation branch coverage
# ---------------------------------------------------------------------------


class TestCacheStatsAggregation:
    """Tests for get_cache_stats aggregation (branch 1327->1325)."""

    @given(
        locales=locale_chains(min_size=2, max_size=4),
    )
    def test_cache_stats_aggregates_across_bundles(
        self, locales: list[str],
    ) -> None:
        """get_cache_stats sums metrics across all initialized bundles."""
        event(f"bundle_count={len(locales)}")
        l10n = FluentLocalization(
            locales, cache=CacheConfig(),
        )
        # Initialize all bundles with resources
        for locale in locales:
            l10n.add_resource(locale, f"msg = {locale}\n")

        # Format to create cache entries
        l10n.format_value("msg")

        stats = l10n.get_cache_stats()
        assert stats is not None
        assert stats["bundle_count"] == len(locales)
        assert l10n.cache_config is not None
        assert stats["maxsize"] == l10n.cache_config.size * len(locales)

    @given(
        locales=locale_chains(min_size=1, max_size=2),
    )
    def test_cache_stats_none_when_disabled(
        self, locales: list[str],
    ) -> None:
        """get_cache_stats returns None when caching disabled."""
        event("outcome=cache_disabled")
        l10n = FluentLocalization(locales)
        assert l10n.get_cache_stats() is None
