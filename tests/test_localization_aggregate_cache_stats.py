"""Tests for FluentLocalization.get_cache_stats() aggregate cache statistics.

Tests the API-BUNDLE-STATS-AGGREGATION-001 implementation: aggregate cache
statistics across multiple FluentBundle instances within a FluentLocalization.
"""

import threading

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine import FluentLocalization


class TestGetCacheStatsBasic:
    """Basic functionality tests for get_cache_stats()."""

    def test_returns_none_when_caching_disabled(self) -> None:
        """get_cache_stats() returns None when caching is disabled."""
        l10n = FluentLocalization(["en"], enable_cache=False)
        l10n.add_resource("en", "msg = Hello")
        l10n.format_value("msg")

        assert l10n.get_cache_stats() is None

    def test_returns_dict_when_caching_enabled(self) -> None:
        """get_cache_stats() returns dict when caching is enabled."""
        l10n = FluentLocalization(["en"], enable_cache=True)
        l10n.add_resource("en", "msg = Hello")

        stats = l10n.get_cache_stats()
        assert isinstance(stats, dict)

    def test_returns_all_expected_keys(self) -> None:
        """get_cache_stats() returns all documented keys."""
        l10n = FluentLocalization(["en"], enable_cache=True)
        l10n.add_resource("en", "msg = Hello")

        stats = l10n.get_cache_stats()
        assert stats is not None

        expected_keys = {
            "size",
            "maxsize",
            "hits",
            "misses",
            "hit_rate",
            "unhashable_skips",
            "bundle_count",
        }
        assert set(stats.keys()) == expected_keys

    def test_correct_types_for_all_keys(self) -> None:
        """All returned values have correct types."""
        l10n = FluentLocalization(["en"], enable_cache=True)
        l10n.add_resource("en", "msg = Hello")
        l10n.format_value("msg")

        stats = l10n.get_cache_stats()
        assert stats is not None

        assert isinstance(stats["size"], int)
        assert isinstance(stats["maxsize"], int)
        assert isinstance(stats["hits"], int)
        assert isinstance(stats["misses"], int)
        assert isinstance(stats["hit_rate"], float)
        assert isinstance(stats["unhashable_skips"], int)
        assert isinstance(stats["bundle_count"], int)


class TestGetCacheStatsAggregation:
    """Tests for correct aggregation across multiple bundles."""

    def test_aggregates_size_across_bundles(self) -> None:
        """Total size is sum of all bundle cache sizes."""
        l10n = FluentLocalization(["en", "de", "fr"], enable_cache=True)
        l10n.add_resource("en", "msg = Hello")
        l10n.add_resource("de", "msg = Hallo")
        l10n.add_resource("fr", "msg = Bonjour")

        # Format in each locale by manipulating which has the message
        l10n.add_resource("en", "en_only = English")
        l10n.add_resource("de", "de_only = German")
        l10n.add_resource("fr", "fr_only = French")

        l10n.format_value("en_only")  # en bundle: 1 miss
        l10n.format_value("de_only")  # en miss, de miss
        l10n.format_value("fr_only")  # en miss, de miss, fr miss

        stats = l10n.get_cache_stats()
        assert stats is not None

        # Each format creates at least one cache entry in the bundle that has it
        assert stats["size"] >= 3

    def test_aggregates_hits_and_misses(self) -> None:
        """Total hits and misses are sums across all bundles."""
        l10n = FluentLocalization(["en", "de"], enable_cache=True)
        l10n.add_resource("en", "msg = Hello")
        l10n.add_resource("de", "msg = Hallo")

        # First format: miss on en
        l10n.format_value("msg")
        # Second format: hit on en
        l10n.format_value("msg")

        stats = l10n.get_cache_stats()
        assert stats is not None

        # 1 miss + 1 hit on 'en' bundle
        assert stats["misses"] == 1
        assert stats["hits"] == 1

    def test_aggregates_maxsize_across_bundles(self) -> None:
        """Total maxsize is sum of all bundle maxsizes."""
        cache_size = 500
        locales = ["en", "de", "fr"]
        l10n = FluentLocalization(
            locales, enable_cache=True, cache_size=cache_size
        )

        # Initialize all bundles
        for locale in locales:
            l10n.add_resource(locale, "msg = test")

        stats = l10n.get_cache_stats()
        assert stats is not None

        # Each bundle has cache_size max
        assert stats["maxsize"] == cache_size * len(locales)

    def test_bundle_count_reflects_initialized_bundles(self) -> None:
        """bundle_count shows only initialized (not lazy) bundles."""
        l10n = FluentLocalization(["en", "de", "fr"], enable_cache=True)

        # Only initialize 'en' bundle
        l10n.add_resource("en", "msg = Hello")

        stats = l10n.get_cache_stats()
        assert stats is not None

        # Only 'en' bundle initialized
        assert stats["bundle_count"] == 1

        # Now initialize 'de'
        l10n.add_resource("de", "msg = Hallo")
        stats = l10n.get_cache_stats()
        assert stats is not None
        assert stats["bundle_count"] == 2


class TestGetCacheStatsHitRate:
    """Tests for hit rate calculation."""

    def test_hit_rate_zero_when_no_requests(self) -> None:
        """hit_rate is 0.0 when no format calls made."""
        l10n = FluentLocalization(["en"], enable_cache=True)
        l10n.add_resource("en", "msg = Hello")

        stats = l10n.get_cache_stats()
        assert stats is not None
        assert stats["hit_rate"] == 0.0

    def test_hit_rate_zero_on_first_request(self) -> None:
        """hit_rate is 0.0 after first request (all misses)."""
        l10n = FluentLocalization(["en"], enable_cache=True)
        l10n.add_resource("en", "msg = Hello")
        l10n.format_value("msg")

        stats = l10n.get_cache_stats()
        assert stats is not None
        assert stats["hit_rate"] == 0.0

    def test_hit_rate_fifty_percent(self) -> None:
        """hit_rate is 50% when half hits, half misses."""
        l10n = FluentLocalization(["en"], enable_cache=True)
        l10n.add_resource("en", "msg = Hello")

        l10n.format_value("msg")  # miss
        l10n.format_value("msg")  # hit

        stats = l10n.get_cache_stats()
        assert stats is not None
        assert stats["hit_rate"] == 50.0

    def test_hit_rate_rounded_to_two_decimals(self) -> None:
        """hit_rate is rounded to 2 decimal places."""
        l10n = FluentLocalization(["en"], enable_cache=True)
        l10n.add_resource("en", "msg = Hello")

        # 1 miss + 2 hits = 66.666...%
        l10n.format_value("msg")  # miss
        l10n.format_value("msg")  # hit
        l10n.format_value("msg")  # hit

        stats = l10n.get_cache_stats()
        assert stats is not None
        assert stats["hit_rate"] == 66.67


class TestGetCacheStatsEdgeCases:
    """Edge cases and boundary conditions."""

    def test_empty_bundles_dict(self) -> None:
        """Returns valid stats even with no initialized bundles."""
        l10n = FluentLocalization(["en"], enable_cache=True)
        # Don't add any resources - no bundles created yet

        stats = l10n.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 0
        assert stats["maxsize"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["hit_rate"] == 0.0
        assert stats["bundle_count"] == 0

    def test_after_clear_cache(self) -> None:
        """Stats reflect state after clear_cache() called."""
        l10n = FluentLocalization(["en"], enable_cache=True)
        l10n.add_resource("en", "msg = Hello")

        # Build up cache
        l10n.format_value("msg")
        l10n.format_value("msg")

        # Clear
        l10n.clear_cache()

        # Format again
        l10n.format_value("msg")

        stats = l10n.get_cache_stats()
        assert stats is not None

        # After clear, we have 1 miss from the new format
        # Note: hits/misses counters are NOT cleared, only cache entries
        # This matches FluentBundle behavior


class TestGetCacheStatsThreadSafety:
    """Thread safety tests for get_cache_stats()."""

    def test_concurrent_stats_reads(self) -> None:
        """Multiple threads can safely read stats concurrently."""
        l10n = FluentLocalization(["en", "de"], enable_cache=True)
        l10n.add_resource("en", "msg = Hello")
        l10n.add_resource("de", "msg = Hallo")

        # Populate cache
        for _ in range(10):
            l10n.format_value("msg")

        results: list[dict[str, int | float] | None] = []
        errors: list[Exception] = []

        def read_stats() -> None:
            try:
                for _ in range(100):
                    stats = l10n.get_cache_stats()
                    results.append(stats)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_stats) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert all(r is not None for r in results)

    def test_concurrent_stats_during_format(self) -> None:
        """Stats can be read while format calls are happening."""
        l10n = FluentLocalization(["en"], enable_cache=True)
        l10n.add_resource("en", "msg = Hello { $name }")

        errors: list[Exception] = []
        stop_event = threading.Event()

        def format_messages() -> None:
            try:
                while not stop_event.is_set():
                    l10n.format_value("msg", {"name": "World"})
            except Exception as e:
                errors.append(e)

        def read_stats() -> None:
            try:
                for _ in range(50):
                    stats = l10n.get_cache_stats()
                    assert stats is not None
            except Exception as e:
                errors.append(e)

        format_thread = threading.Thread(target=format_messages)
        stats_thread = threading.Thread(target=read_stats)

        format_thread.start()
        stats_thread.start()

        stats_thread.join()
        stop_event.set()
        format_thread.join()

        assert not errors


@pytest.mark.fuzz
class TestGetCacheStatsProperty:
    """Test property-based invariants using Hypothesis."""

    @given(st.integers(min_value=1, max_value=5))
    @settings(max_examples=20)
    def test_bundle_count_never_exceeds_locale_count(self, num_locales: int) -> None:
        """bundle_count is always <= number of locales."""
        locales = [f"locale{i}" for i in range(num_locales)]
        l10n = FluentLocalization(locales, enable_cache=True)

        # Initialize some bundles
        for i in range(num_locales):
            if i % 2 == 0:
                l10n.add_resource(locales[i], "msg = test")

        stats = l10n.get_cache_stats()
        assert stats is not None
        assert stats["bundle_count"] <= num_locales
        event(f"num_locales={num_locales}")

    @given(st.integers(min_value=100, max_value=1000))
    @settings(max_examples=10)
    def test_maxsize_matches_configuration(self, cache_size: int) -> None:
        """maxsize is deterministic based on cache_size config."""
        l10n = FluentLocalization(["en"], enable_cache=True, cache_size=cache_size)
        l10n.add_resource("en", "msg = test")

        stats = l10n.get_cache_stats()
        assert stats is not None
        assert stats["maxsize"] == cache_size
        event(f"cache_size={cache_size}")

    @given(st.integers(min_value=1, max_value=20))
    @settings(max_examples=20)
    def test_hits_plus_misses_equals_total_requests(self, num_requests: int) -> None:
        """hits + misses always equals total format calls on unique keys."""
        l10n = FluentLocalization(["en"], enable_cache=True)

        # Create unique messages
        for i in range(num_requests):
            l10n.add_resource("en", f"msg{i} = Message {i}")

        # Format each once (all misses)
        for i in range(num_requests):
            l10n.format_value(f"msg{i}")

        stats = l10n.get_cache_stats()
        assert stats is not None
        assert stats["hits"] + stats["misses"] == num_requests
        event(f"num_requests={num_requests}")
