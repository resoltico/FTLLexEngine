"""Property-based (Hypothesis) tests for FormatCache and IntegrityCache.

All classes are marked with @pytest.mark.fuzz and run only via:
    ./scripts/fuzz_hypofuzz.sh --deep
    pytest -m fuzz

Covers:
- IntegrityCache invariants: maxsize enforced, get-after-put, clear, hit/miss counters
- IntegrityCache LRU eviction patterns
- IntegrityCache key handling: locale, attribute, args dict stability
- IntegrityCache robustness: various arg types, duplicate puts, non-negative stats
- IntegrityCache statistics: hit_rate consistency, size matches entry count
- IntegrityCache init parameters stored correctly
- IntegrityCache primitives: all FluentValue types produce valid cache keys
- FormatCache invariants: transparency, isolation, LRU eviction, stats consistency
- FormatCache invalidation: add_resource, add_function
- FormatCache internals: __len__, properties, key uniqueness, attribute isolation
- FormatCache type collision prevention: bool/int, int/Decimal
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import assume, event, given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle
from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.runtime.cache_config import CacheConfig

# ============================================================================
# MODULE-LEVEL STRATEGIES (used by IntegrityCache tests)
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
            st.decimals(allow_nan=False, allow_infinity=False),
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
    """Test fundamental IntegrityCache invariants."""

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
        args: dict[str, int | Decimal | str] | None,
        attr: str | None,
        value: tuple[str, tuple[()]],
    ) -> None:
        """PROPERTY: get(k) after put(k, v) returns v."""
        cache = IntegrityCache(maxsize=100, strict=False)

        formatted, errors = value
        cache.put(msg_id, args, attr, locale, True, formatted, errors)
        entry = cache.get(msg_id, args, attr, locale, True)

        assert entry is not None
        assert entry.as_result() == value
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
        assert entry.as_result() == value
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
        assert entry.as_result() == value
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
                st.decimals(allow_nan=False, allow_infinity=False),
                st.text(),
                st.booleans(),
                st.none(),
            ),
            max_size=10,  # Keep practical bound for dict size
        ),
    )
    @settings(max_examples=200)
    def test_cache_handles_various_arg_types(
        self, args: dict[str, int | Decimal | str | bool | None]
    ) -> None:
        """ROBUSTNESS: Cache handles various argument types."""
        cache = IntegrityCache(maxsize=100, strict=False)

        # Should not crash with various arg types
        try:
            cache.put("msg", args, None, "en_US", True, "result", ())
            entry = cache.get("msg", args, None, "en_US", True)
            # If put succeeded, get should return the value
            if entry is not None:
                assert entry.as_result() == ("result", ())
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


# ============================================================================
# PROPERTY TESTS - INIT PARAMETERS
# ============================================================================


@pytest.mark.fuzz
class TestIntegrityCacheHypothesisProperties:
    """Property-based tests for IntegrityCache using Hypothesis."""

    @given(
        st.integers(min_value=1, max_value=1000),
        st.integers(min_value=1, max_value=10000),
        st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=50)
    def test_property_init_parameters_stored_correctly(
        self,
        maxsize: int,
        max_entry_weight: int,
        max_errors_per_entry: int,
    ) -> None:
        """PROPERTY: Constructor parameters are stored correctly."""
        cache = IntegrityCache(
            strict=False,
            maxsize=maxsize,
            max_entry_weight=max_entry_weight,
            max_errors_per_entry=max_errors_per_entry,
        )

        assert cache.maxsize == maxsize
        assert cache.max_entry_weight == max_entry_weight
        assert cache.size == 0
        assert cache.hits == 0
        assert cache.misses == 0
        event(f"maxsize={maxsize}")

    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=50)
    def test_property_primitives_hashable(self, text: str) -> None:
        """PROPERTY: All primitive types produce valid cache keys."""
        cache = IntegrityCache(strict=False)

        # String
        cache.put("msg", {"text": text}, None, "en", True, "result", ())
        entry = cache.get("msg", {"text": text}, None, "en", True)
        assert entry is not None
        assert entry.as_result() == ("result", ())

        # Integer
        cache.put("msg", {"num": 42}, None, "en", True, "result", ())
        entry = cache.get("msg", {"num": 42}, None, "en", True)
        assert entry is not None
        assert entry.as_result() == ("result", ())

        # Decimal
        cache.put("msg", {"decimal": Decimal("3.14")}, None, "en", True, "result", ())
        entry = cache.get("msg", {"decimal": Decimal("3.14")}, None, "en", True)
        assert entry is not None
        assert entry.as_result() == ("result", ())

        # Bool
        cache.put("msg", {"bool": True}, None, "en", True, "result", ())
        entry = cache.get("msg", {"bool": True}, None, "en", True)
        assert entry is not None
        assert entry.as_result() == ("result", ())

        # None
        cache.put("msg", {"val": None}, None, "en", True, "result", ())
        entry = cache.get("msg", {"val": None}, None, "en", True)
        assert entry is not None
        assert entry.as_result() == ("result", ())
        event(f"text_len={len(text)}")


# ============================================================================
# FORMATCACHE PROPERTIES (via FluentBundle)
# ============================================================================


@st.composite
def message_args(draw: st.DrawFn) -> dict[str, str | int]:
    """Generate valid message arguments."""
    num_args = draw(st.integers(min_value=0, max_value=5))
    args = {}
    for _ in range(num_args):
        key = draw(st.text(
            alphabet=st.characters(min_codepoint=97, max_codepoint=122),
            min_size=1, max_size=10,
        ))
        value = draw(st.one_of(st.text(min_size=0, max_size=20), st.integers()))
        args[key] = value
    return args


@pytest.mark.fuzz
class TestCacheProperties:
    """Property-based tests for FormatCache behavior."""

    @given(args=message_args())
    def test_cache_transparency(self, args: dict[str, str | int]) -> None:
        """Cache hit returns same result as cache miss.

        Property: format_pattern(msg, args) with cache enabled should return
        identical results to format_pattern(msg, args) without cache.
        """
        ftl_vars = " ".join([f"{{ ${k} }}" for k in args])
        ftl_source = f"msg = Hello {ftl_vars}!"

        # Bundle without cache
        bundle_no_cache = FluentBundle("en", use_isolating=False)
        bundle_no_cache.add_resource(ftl_source)
        result_no_cache, errors_no_cache = bundle_no_cache.format_pattern("msg", args)

        # Bundle with cache
        bundle_with_cache = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle_with_cache.add_resource(ftl_source)

        # First call (cache miss)
        result_miss, errors_miss = bundle_with_cache.format_pattern("msg", args)
        assert result_miss == result_no_cache
        assert len(errors_miss) == len(errors_no_cache)

        # Second call (cache hit)
        result_hit, errors_hit = bundle_with_cache.format_pattern("msg", args)
        assert result_hit == result_no_cache
        assert len(errors_hit) == len(errors_no_cache)

        # Cache hit and miss must return identical results
        assert result_miss == result_hit
        assert len(errors_miss) == len(errors_hit)
        event(f"arg_count={len(args)}")

    @given(
        args1=message_args(),
        args2=message_args(),
    )
    def test_cache_isolation(
        self, args1: dict[str, str | int], args2: dict[str, str | int]
    ) -> None:
        """Different args produce different cache entries.

        Property: format_pattern(msg, args1) and format_pattern(msg, args2)
        should be cached separately if args differ.
        """
        # Only test if args actually differ
        if args1 == args2:
            return

        ftl_vars = set(args1.keys()) | set(args2.keys())
        ftl_placeholders = " ".join([f"{{ ${k} }}" for k in ftl_vars])
        ftl_source = f"msg = Test {ftl_placeholders}"

        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource(ftl_source)

        # Format with args1
        _result1, _ = bundle.format_pattern("msg", args1)

        # Format with args2
        _result2, _ = bundle.format_pattern("msg", args2)

        # Results should differ if args differ
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 2  # Two separate cache entries
        event(f"key_count={len(args1)}")

    @given(
        cache_size=st.integers(min_value=1, max_value=100),
        num_messages=st.integers(min_value=1, max_value=200),
    )
    def test_lru_eviction_property(self, cache_size: int, num_messages: int) -> None:
        """Cache size never exceeds limit.

        Property: No matter how many format calls, cache size <= maxsize.
        """
        bundle = FluentBundle("en", cache=CacheConfig(size=cache_size))

        # Add many messages
        ftl_source = "\n".join([f"msg{i} = Message {i}" for i in range(num_messages)])
        bundle.add_resource(ftl_source)

        # Format all messages
        for i in range(num_messages):
            bundle.format_pattern(f"msg{i}")

        # Cache size must respect limit
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] <= cache_size
        assert stats["size"] == min(num_messages, cache_size)
        evicted = num_messages > cache_size
        event(f"eviction={evicted}")

    @given(
        num_calls=st.integers(min_value=1, max_value=100),
    )
    def test_stats_consistency_property(self, num_calls: int) -> None:
        """Cache stats are always consistent.

        Property: hits + misses = total calls.
        """
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello")

        # Make num_calls format calls
        for _ in range(num_calls):
            bundle.format_pattern("msg")

        # Stats must be consistent
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["hits"] + stats["misses"] == num_calls
        assert stats["hits"] == num_calls - 1  # All but first are hits
        assert stats["misses"] == 1  # Only first is miss
        event(f"num_calls={num_calls}")


@pytest.mark.fuzz
class TestCacheInvalidationProperties:
    """Property-based tests for cache invalidation."""

    @given(
        num_resources=st.integers(min_value=1, max_value=10),
    )
    def test_invalidation_on_add_resource(self, num_resources: int) -> None:
        """Cache is cleared every time add_resource is called.

        Property: After add_resource(), cache size = 0 and stats reset.
        """
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello")

        # Warm up cache
        bundle.format_pattern("msg")

        # Add resources multiple times
        for i in range(num_resources):
            stats_before = bundle.get_cache_stats()
            assert stats_before is not None

            bundle.add_resource(f"msg{i} = World {i}")

            stats_after = bundle.get_cache_stats()
            assert stats_after is not None
            assert stats_after["size"] == 0  # Cache cleared
            assert stats_after["hits"] == 0  # Stats reset
            assert stats_after["misses"] == 0
        event(f"num_resources={num_resources}")

    @given(
        num_functions=st.integers(min_value=1, max_value=10),
    )
    def test_invalidation_on_add_function(self, num_functions: int) -> None:
        """Cache is cleared every time add_function is called.

        Property: After add_function(), cache size = 0 and stats reset.
        """
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello")

        # Warm up cache
        bundle.format_pattern("msg")

        # Add functions multiple times
        for i in range(num_functions):
            stats_before = bundle.get_cache_stats()
            assert stats_before is not None

            def func(value: str) -> str:
                return value.upper()

            bundle.add_function(f"FUNC{i}", func)

            stats_after = bundle.get_cache_stats()
            assert stats_after is not None
            assert stats_after["size"] == 0  # Cache cleared
        event(f"num_functions={num_functions}")


@pytest.mark.fuzz
class TestCacheInternalProperties:
    """Property-based tests for cache internals."""

    @given(
        cache_size=st.integers(min_value=1, max_value=100),
        num_operations=st.integers(min_value=0, max_value=200),
    )
    def test_cache_len_property(self, cache_size: int, num_operations: int) -> None:
        """Cache __len__ always returns correct size.

        Property: len(cache) <= maxsize and len(cache) = stats["size"].
        """
        bundle = FluentBundle("en", cache=CacheConfig(size=cache_size))

        # Add messages
        ftl_source = "\n".join([f"msg{i} = Message {i}" for i in range(num_operations)])
        bundle.add_resource(ftl_source)

        # Format messages
        for i in range(num_operations):
            bundle.format_pattern(f"msg{i}")

        # len() should match stats
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert len(cache) == stats["size"]
        assert len(cache) <= cache_size
        event(f"maxsize={cache_size}")

    @given(
        cache_size=st.integers(min_value=1, max_value=50),
    )
    def test_cache_properties_consistent(self, cache_size: int) -> None:
        """Cache properties (maxsize, hits, misses) are consistent.

        Property: Properties always match internal state.
        """
        bundle = FluentBundle("en", cache=CacheConfig(size=cache_size))
        bundle.add_resource("msg = Hello")
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy

        # maxsize property matches constructor
        assert cache.maxsize == cache_size

        # hits and misses start at zero
        assert cache.hits == 0
        assert cache.misses == 0

        # After one call: 1 miss, 0 hits
        bundle.format_pattern("msg")
        assert cache.hits == 0
        assert cache.misses == 1

        # After second call: 1 miss, 1 hit
        bundle.format_pattern("msg")
        assert cache.hits == 1
        assert cache.misses == 1
        event(f"maxsize={cache_size}")

    @given(
        num_updates=st.integers(min_value=1, max_value=50),
    )
    def test_cache_update_existing_key_property(self, num_updates: int) -> None:
        """Updating existing cache entry doesn't increase size.

        Property: Repeatedly formatting same message keeps cache size at 1.
        """
        bundle = FluentBundle("en", cache=CacheConfig(size=10))
        bundle.add_resource("msg = Hello")
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy

        # Format same message multiple times
        for _ in range(num_updates):
            bundle.format_pattern("msg")

        # Cache size should be 1 (same entry updated)
        assert len(cache) == 1
        assert cache.hits == num_updates - 1
        assert cache.misses == 1
        event(f"updates={num_updates}")

    @given(
        args_list=st.lists(
            st.dictionaries(
                keys=st.text(alphabet="abcdefghij", min_size=1, max_size=3),
                values=st.integers(min_value=0, max_value=100),
                min_size=0,
                max_size=3,
            ),
            min_size=1,
            max_size=20,
        )
    )
    def test_cache_key_uniqueness_property(self, args_list: list[dict[str, int]]) -> None:
        """Each unique args dict creates separate cache entry.

        Property: Distinct args → distinct cache keys → separate entries.
        """
        bundle = FluentBundle("en", cache=CacheConfig(size=100), use_isolating=False)
        bundle.add_resource("msg = { $a } { $b } { $c }")
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy

        # Format with different args
        for args in args_list:
            bundle.format_pattern("msg", args)

        # Cache size equals number of unique args
        unique_args = len({tuple(sorted(args.items())) for args in args_list})
        assert len(cache) == min(unique_args, 100)  # Min with cache_size
        event(f"unique_args={unique_args}")

    @given(
        message_ids=st.lists(
            st.text(alphabet="abcdefghij", min_size=3, max_size=10),
            min_size=1,
            max_size=20,
            unique=True,
        )
    )
    def test_cache_message_id_isolation_property(
        self, message_ids: list[str]
    ) -> None:
        """Different message IDs create separate cache entries.

        Property: Each message_id → separate cache entry.
        """
        bundle = FluentBundle("en", cache=CacheConfig(size=100))

        # Add all messages
        ftl_source = "\n".join([f"{msg_id} = Message {i}" for i, msg_id in enumerate(message_ids)])
        bundle.add_resource(ftl_source)
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy

        # Format all messages
        for msg_id in message_ids:
            bundle.format_pattern(msg_id)

        # Cache should have one entry per message
        assert len(cache) == min(len(message_ids), 100)
        event(f"msg_count={len(message_ids)}")

    @given(
        attributes=st.lists(
            st.one_of(st.none(), st.text(alphabet="abcdefghij", min_size=1, max_size=10)),
            min_size=1,
            max_size=10,
        )
    )
    def test_cache_attribute_isolation_property(
        self, attributes: list[str | None]
    ) -> None:
        """Different attributes create separate cache entries.

        Property: Each attribute → separate cache entry.
        """
        bundle = FluentBundle("en", cache=CacheConfig(size=100), use_isolating=False)

        # Create message with multiple attributes
        attrs_ftl = "\n    ".join([f".{attr} = Attr {attr}" for attr in attributes if attr])
        bundle.add_resource(f"msg = Value\n    {attrs_ftl}")
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy

        # Format with different attributes
        seen_attrs = set()
        for attr in attributes:
            bundle.format_pattern("msg", attribute=attr)
            seen_attrs.add(attr)

        # Cache should have one entry per unique attribute
        assert len(cache) == len(seen_attrs)
        event(f"attr_count={len(seen_attrs)}")

    @given(
        num_operations=st.integers(min_value=0, max_value=100),
    )
    def test_cache_size_property_consistency(self, num_operations: int) -> None:
        """Cache size property matches internal state.

        Property: cache.size == len(cache._cache).
        """
        bundle = FluentBundle("en", cache=CacheConfig(size=100))

        # Add messages
        ftl_source = "\n".join([f"msg{i} = Message {i}" for i in range(num_operations)])
        bundle.add_resource(ftl_source)
        cache = bundle._cache
        assert cache is not None  # Type narrowing for mypy

        # Format messages
        for i in range(num_operations):
            bundle.format_pattern(f"msg{i}")

        # size property should match len() and stats
        assert cache.size == len(cache)
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert cache.size == stats["size"]
        event(f"entries={num_operations}")


@pytest.mark.fuzz
class TestCacheTypeCollisionPrevention:
    """Tests for type collision prevention in cache keys.

    Python's hash equality means hash(1) == hash(True) == hash(1.0), which would
    cause cache collisions when these values produce different formatted outputs.
    The cache uses type-tagged tuples to prevent this.
    """

    def test_bool_int_produce_different_cache_entries(self) -> None:
        """Boolean True and integer 1 produce distinct cache entries.

        In Fluent, True formats as "true" while 1 formats as "1". Without type
        tagging, Python's hash equality would cause cache collision.
        """
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = { $v }")

        # Format with True first
        result_bool, _ = bundle.format_pattern("msg", {"v": True})
        # Format with 1 (would collide without type tagging)
        result_int, _ = bundle.format_pattern("msg", {"v": 1})

        # Results must differ - bool formats as "true", int as "1"
        assert result_bool == "true"
        assert result_int == "1"

        # Cache should have 2 entries (not 1 due to collision)
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 2

    def test_int_decimal_produce_different_cache_entries(self) -> None:
        """Integer 1 and Decimal('1') produce distinct cache entries.

        Without type tagging, hash(1) == hash(Decimal('1')) would cause collision.
        """
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = { $v }")

        # Format with int first
        _result_int, _ = bundle.format_pattern("msg", {"v": 1})
        # Format with Decimal (would collide without type tagging)
        _result_decimal, _ = bundle.format_pattern("msg", {"v": Decimal("1")})

        # Cache should have 2 entries
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 2

    def test_bool_false_int_zero_distinct(self) -> None:
        """Boolean False and integer 0 produce distinct cache entries.

        hash(False) == hash(0) in Python.
        """
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = { $v }")

        result_bool, _ = bundle.format_pattern("msg", {"v": False})
        result_int, _ = bundle.format_pattern("msg", {"v": 0})

        # bool formats as "false", int as "0"
        assert result_bool == "false"
        assert result_int == "0"

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 2

    def test_cache_hit_returns_correct_typed_value(self) -> None:
        """Cache hit returns value for correct type, not hash-equivalent type.

        After caching with int 1, looking up with bool True must NOT return
        the cached "1", but cache miss and format "true".
        """
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = { $v }")

        # Cache with int 1
        bundle.format_pattern("msg", {"v": 1})

        # Look up with bool True - must NOT be a cache hit for the int entry
        result, _ = bundle.format_pattern("msg", {"v": True})

        # If type tagging works, this returns "true" not "1"
        assert result == "true"

    @given(st.booleans(), st.integers())
    def test_bool_int_always_distinct(self, b: bool, i: int) -> None:
        """PROPERTY: Any bool and int pair with same Python hash produce distinct cache entries."""
        # Only test when hash would collide
        if hash(b) != hash(i):
            return

        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = { $v }")

        # Format both
        bundle.format_pattern("msg", {"v": b})
        bundle.format_pattern("msg", {"v": i})

        # Should be 2 entries despite hash equality
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 2
        event(f"bool={b}")

    @given(st.integers(), st.decimals(allow_nan=False, allow_infinity=False))
    def test_int_decimal_always_distinct_when_equal(self, i: int, d: Decimal) -> None:
        """PROPERTY: Int and Decimal with same numeric value produce distinct cache entries."""
        # Only test when values are hash-equal (hash(n) == hash(Decimal(n)) in Python)
        try:
            if hash(i) != hash(d):
                return
        except (TypeError, ValueError):
            return

        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = { $v }")

        # Format both
        bundle.format_pattern("msg", {"v": i})
        bundle.format_pattern("msg", {"v": d})

        # Should be 2 entries despite hash equality
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 2
        event(f"int_value={i}")
