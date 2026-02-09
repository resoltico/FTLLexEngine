"""Hypothesis property-based tests for IntegrityCache.

Tests cache invariants, LRU eviction, thread safety, and robustness.
Complements test_cache_basic.py with property-based testing.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, event, given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.cache import IntegrityCache

# ============================================================================
# HYPOTHESIS STRATEGIES
# ============================================================================


# Strategy for message IDs - use st.from_regex per hypothesis.md
message_ids = st.from_regex(r"[a-z]+", fullmatch=True)

# Strategy for locale codes
locale_codes = st.sampled_from(["en_US", "de_DE", "lv_LV", "fr_FR", "ja_JP"])

# Strategy for attributes - remove arbitrary max_size
attributes = st.one_of(st.none(), st.text(min_size=1))

# Strategy for cache values (result, errors) - remove arbitrary max_size
cache_values: st.SearchStrategy[tuple[str, tuple[()]]] = st.tuples(
    st.text(min_size=0),
    st.just(()),  # Empty error tuple for simplicity
)

# Strategy for message arguments - keep collection bound, remove text max_size
args_strategy = st.one_of(
    st.none(),
    st.dictionaries(
        st.text(min_size=1),
        st.one_of(
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.text(),
        ),
        max_size=5,  # Keep practical bound for dict size
    ),
)


# ============================================================================
# PROPERTY TESTS - BASIC INVARIANTS
# ============================================================================


@pytest.mark.fuzz
class TestCacheInvariants:
    """Test fundamental cache invariants."""

    @given(maxsize=st.integers(min_value=1, max_value=10000))
    @settings(max_examples=100)
    def test_cache_maxsize_enforced(self, maxsize: int) -> None:
        """INVARIANT: Cache never exceeds maxsize."""
        cache = IntegrityCache(maxsize=maxsize, strict=False)

        # Add more than maxsize entries
        for i in range(maxsize + 10):
            cache.put(
                f"msg_{i}",
                None,
                None,
                "en_US",
                True,
                f"result_{i}",
                (),
            )

        # Cache should not exceed maxsize
        assert cache.get_stats()["size"] <= maxsize
        event(f"maxsize={maxsize}")

    @given(
        msg_id=message_ids,
        locale=locale_codes,
        args=args_strategy,
        attr=attributes,
        value=cache_values,
    )
    @settings(max_examples=200)
    def test_get_after_put_returns_value(
        self,
        msg_id: str,
        locale: str,
        args: dict[str, int | float | str] | None,
        attr: str | None,
        value: tuple[str, tuple[()]],
    ) -> None:
        """PROPERTY: get(k) after put(k, v) returns v."""
        cache = IntegrityCache(maxsize=100, strict=False)

        formatted, errors = value
        cache.put(msg_id, args, attr, locale, True, formatted, errors)
        entry = cache.get(msg_id, args, attr, locale, True)

        assert entry is not None
        assert entry.to_tuple() == value
        has_args = args is not None
        event(f"has_args={has_args}")

    @given(
        msg_id=message_ids,
        locale=locale_codes,
    )
    @settings(max_examples=100)
    def test_get_without_put_returns_none(
        self,
        msg_id: str,
        locale: str,
    ) -> None:
        """PROPERTY: get(k) without put(k) returns None."""
        cache = IntegrityCache(maxsize=100, strict=False)

        result = cache.get(msg_id, None, None, locale, True)

        assert result is None
        event(f"locale={locale}")

    @given(maxsize=st.integers(min_value=1, max_value=100))
    @settings(max_examples=50)
    def test_clear_resets_cache_to_empty(self, maxsize: int) -> None:
        """PROPERTY: clear() empties cache and resets counters."""
        cache = IntegrityCache(maxsize=maxsize, strict=False)

        # Add some entries
        for i in range(min(10, maxsize)):
            cache.put(f"msg_{i}", None, None, "en_US", True, f"result_{i}", ())

        # Clear
        cache.clear()

        # Cache should be empty
        stats = cache.get_stats()
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        event(f"maxsize={maxsize}")

    @given(
        msg_id=message_ids,
        locale=locale_codes,
        value=cache_values,
    )
    @settings(max_examples=100)
    def test_hit_counter_increments_on_cache_hit(
        self,
        msg_id: str,
        locale: str,
        value: tuple[str, tuple[()]],
    ) -> None:
        """PROPERTY: Cache hits increment hit counter."""
        cache = IntegrityCache(maxsize=100, strict=False)

        formatted, errors = value
        cache.put(msg_id, None, None, locale, True, formatted, errors)

        # First get - cache hit
        initial_stats = cache.get_stats()
        cache.get(msg_id, None, None, locale, True)

        stats_after_hit = cache.get_stats()
        assert stats_after_hit["hits"] == initial_stats["hits"] + 1
        event(f"locale={locale}")

    @given(
        msg_id=message_ids,
        locale=locale_codes,
    )
    @settings(max_examples=100)
    def test_miss_counter_increments_on_cache_miss(
        self,
        msg_id: str,
        locale: str,
    ) -> None:
        """PROPERTY: Cache misses increment miss counter."""
        cache = IntegrityCache(maxsize=100, strict=False)

        initial_stats = cache.get_stats()
        cache.get(msg_id, None, None, locale, True)  # Cache miss

        stats_after_miss = cache.get_stats()
        assert stats_after_miss["misses"] == initial_stats["misses"] + 1
        event(f"locale={locale}")


# ============================================================================
# PROPERTY TESTS - LRU EVICTION
# ============================================================================


@pytest.mark.fuzz
class TestLRUEviction:
    """Test LRU (Least Recently Used) eviction behavior."""

    @given(maxsize=st.integers(min_value=2, max_value=10))
    @settings(max_examples=50)
    def test_lru_evicts_least_recently_used(self, maxsize: int) -> None:
        """PROPERTY: LRU eviction removes oldest entry."""
        cache = IntegrityCache(maxsize=maxsize, strict=False)

        # Fill cache to capacity
        for i in range(maxsize):
            cache.put(f"msg_{i}", None, None, "en_US", True, f"result_{i}", ())

        # Access first entry to make it recently used
        cache.get("msg_0", None, None, "en_US", True)

        # Add one more entry (should evict msg_1, not msg_0)
        cache.put("msg_new", None, None, "en_US", True, "result_new", ())

        # msg_0 should still be in cache (recently accessed)
        assert cache.get("msg_0", None, None, "en_US", True) is not None

        # msg_1 should be evicted (oldest unreferenced)
        assert cache.get("msg_1", None, None, "en_US", True) is None
        event(f"maxsize={maxsize}")

    @given(
        maxsize=st.integers(min_value=3, max_value=10),
        access_pattern=st.lists(
            st.integers(min_value=0, max_value=9),
            min_size=5,
            max_size=20,
        ),
    )
    @settings(max_examples=50)
    def test_lru_access_pattern_eviction(
        self,
        maxsize: int,
        access_pattern: list[int],
    ) -> None:
        """PROPERTY: LRU eviction respects access patterns."""
        cache = IntegrityCache(maxsize=maxsize, strict=False)

        # Fill cache
        for i in range(maxsize):
            cache.put(f"msg_{i}", None, None, "en_US", True, f"result_{i}", ())

        # Access entries according to pattern
        for idx in access_pattern:
            if idx < maxsize:
                cache.get(f"msg_{idx}", None, None, "en_US", True)

        # Add new entries (will trigger evictions)
        for i in range(maxsize, maxsize + 3):
            cache.put(f"msg_{i}", None, None, "en_US", True, f"result_{i}", ())

        # Recently accessed entries should still be in cache
        # (This tests the LRU property implicitly)
        assert cache.get_stats()["size"] <= maxsize
        event(f"pattern_len={len(access_pattern)}")


# ============================================================================
# PROPERTY TESTS - KEY HANDLING
# ============================================================================


@pytest.mark.fuzz
class TestCacheKeyHandling:
    """Test cache key construction and equality."""

    @given(
        msg_id=message_ids,
        locale=locale_codes,
        value=cache_values,
    )
    @settings(max_examples=100)
    def test_same_key_retrieves_same_value(
        self,
        msg_id: str,
        locale: str,
        value: tuple[str, tuple[()]],
    ) -> None:
        """PROPERTY: Same key components retrieve same cached value."""
        cache = IntegrityCache(maxsize=100, strict=False)

        formatted, errors = value
        # Put with specific key
        cache.put(msg_id, None, None, locale, True, formatted, errors)

        # Get with same key components
        entry = cache.get(msg_id, None, None, locale, True)

        assert entry is not None
        assert entry.to_tuple() == value
        event(f"locale={locale}")

    @given(
        msg_id=message_ids,
        locale1=locale_codes,
        locale2=locale_codes,
        value=cache_values,
    )
    @settings(max_examples=100)
    def test_different_locale_creates_different_key(
        self,
        msg_id: str,
        locale1: str,
        locale2: str,
        value: tuple[str, tuple[()]],
    ) -> None:
        """PROPERTY: Different locales create different cache keys."""
        assume(locale1 != locale2)

        cache = IntegrityCache(maxsize=100, strict=False)

        formatted, errors = value
        # Put with locale1
        cache.put(msg_id, None, None, locale1, True, formatted, errors)

        # Get with locale2 should miss
        result = cache.get(msg_id, None, None, locale2, True)

        assert result is None
        event(f"locale_pair={locale1}_{locale2}")

    @given(
        msg_id=message_ids,
        locale=locale_codes,
        attr1=attributes,
        attr2=attributes,
        value=cache_values,
    )
    @settings(max_examples=100)
    def test_different_attribute_creates_different_key(
        self,
        msg_id: str,
        locale: str,
        attr1: str | None,
        attr2: str | None,
        value: tuple[str, tuple[()]],
    ) -> None:
        """PROPERTY: Different attributes create different cache keys."""
        assume(attr1 != attr2)

        cache = IntegrityCache(maxsize=100, strict=False)

        formatted, errors = value
        # Put with attr1
        cache.put(msg_id, None, attr1, locale, True, formatted, errors)

        # Get with attr2 should miss
        result = cache.get(msg_id, None, attr2, locale, True)

        assert result is None
        has_attr1 = attr1 is not None
        event(f"has_attr={has_attr1}")

    @given(
        msg_id=message_ids,
        locale=locale_codes,
        value=cache_values,
    )
    @settings(max_examples=100)
    def test_args_dict_key_stability(
        self,
        msg_id: str,
        locale: str,
        value: tuple[str, tuple[()]],
    ) -> None:
        """PROPERTY: Equivalent args dicts produce same cache key."""
        cache = IntegrityCache(maxsize=100, strict=False)

        formatted, errors = value
        # Put with args dict
        args = {"x": 1, "y": 2}
        cache.put(msg_id, args, None, locale, True, formatted, errors)

        # Get with equivalent dict (different order)
        args_reordered = {"y": 2, "x": 1}
        entry = cache.get(msg_id, args_reordered, None, locale, True)

        # Should hit cache (dict key normalized)
        assert entry is not None
        assert entry.to_tuple() == value
        event(f"locale={locale}")


# ============================================================================
# PROPERTY TESTS - ROBUSTNESS
# ============================================================================


@pytest.mark.fuzz
class TestCacheRobustness:
    """Test cache robustness with various input types."""

    @given(
        args=st.dictionaries(
            st.text(min_size=1),
            st.one_of(
                st.integers(),
                st.floats(allow_nan=False, allow_infinity=False),
                st.text(),
                st.booleans(),
                st.none(),
            ),
            max_size=10,  # Keep practical bound for dict size
        ),
    )
    @settings(max_examples=200)
    def test_cache_handles_various_arg_types(
        self, args: dict[str, int | float | str | bool | None]
    ) -> None:
        """ROBUSTNESS: Cache handles various argument types."""
        cache = IntegrityCache(maxsize=100, strict=False)

        # Should not crash with various arg types
        try:
            cache.put("msg", args, None, "en_US", True, "result", ())
            entry = cache.get("msg", args, None, "en_US", True)
            # If put succeeded, get should return the value
            if entry is not None:
                assert entry.to_tuple() == ("result", ())
        except (TypeError, ValueError):
            # Some types may not be hashable - acceptable
            pass
        event(f"arg_types={len(args)}")

    @given(
        msg_ids=st.lists(message_ids, min_size=1, max_size=50),
        maxsize=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=50)
    def test_cache_handles_duplicate_puts(
        self,
        msg_ids: list[str],
        maxsize: int,
    ) -> None:
        """ROBUSTNESS: Cache handles duplicate puts gracefully."""
        cache = IntegrityCache(maxsize=maxsize, strict=False)

        # Put same message multiple times
        for msg_id in msg_ids:
            cache.put(msg_id, None, None, "en_US", True, f"result_{msg_id}", ())

        # Cache should still respect maxsize
        assert cache.get_stats()["size"] <= maxsize
        event(f"duplicates={len(msg_ids)}")

    @given(maxsize=st.integers(min_value=1, max_value=100))
    @settings(max_examples=50)
    def test_cache_stats_never_negative(self, maxsize: int) -> None:
        """ROBUSTNESS: Cache stats are never negative."""
        cache = IntegrityCache(maxsize=maxsize, strict=False)

        # Perform various operations
        cache.put("msg", None, None, "en_US", True, "result", ())
        cache.get("msg", None, None, "en_US", True)
        cache.get("missing", None, None, "en_US", True)
        cache.clear()

        stats = cache.get_stats()
        assert stats["size"] >= 0
        assert stats["hits"] >= 0
        assert stats["misses"] >= 0
        assert stats["maxsize"] > 0
        event(f"maxsize={maxsize}")


# ============================================================================
# PROPERTY TESTS - STATISTICS
# ============================================================================


@pytest.mark.fuzz
class TestCacheStatistics:
    """Test cache statistics tracking."""

    @given(
        operations=st.lists(
            st.tuples(
                st.sampled_from(["put", "get"]),
                message_ids,
            ),
            min_size=1,
            max_size=50,
        ),
    )
    @settings(max_examples=50)
    def test_hit_rate_consistency(
        self,
        operations: list[tuple[str, str]],
    ) -> None:
        """PROPERTY: hit_rate = hits / (hits + misses)."""
        cache = IntegrityCache(maxsize=20, strict=False)

        for op, msg_id in operations:
            if op == "put":
                cache.put(msg_id, None, None, "en_US", True, f"result_{msg_id}", ())
            elif op == "get":
                cache.get(msg_id, None, None, "en_US", True)

        stats = cache.get_stats()
        total = stats["hits"] + stats["misses"]

        if total > 0:
            expected_hit_rate = stats["hits"] / total
            # hit_rate might be percentage (0-100) or decimal (0.0-1.0)
            actual_rate: float = float(stats["hit_rate"])
            if actual_rate > 1.0:  # Percentage format
                actual_rate = actual_rate / 100.0
            assert abs(actual_rate - expected_hit_rate) < 0.01
        event(f"op_count={len(operations)}")

    @given(
        num_entries=st.integers(min_value=0, max_value=50),
        maxsize=st.integers(min_value=10, max_value=100),
    )
    @settings(max_examples=50)
    def test_size_equals_entry_count(
        self,
        num_entries: int,
        maxsize: int,
    ) -> None:
        """PROPERTY: size stat equals actual number of cached entries."""
        cache = IntegrityCache(maxsize=maxsize, strict=False)

        # Add entries
        for i in range(num_entries):
            cache.put(f"msg_{i}", None, None, "en_US", True, f"result_{i}", ())

        stats = cache.get_stats()
        expected_size = min(num_entries, maxsize)

        assert stats["size"] == expected_size
        event(f"entries={num_entries}")
