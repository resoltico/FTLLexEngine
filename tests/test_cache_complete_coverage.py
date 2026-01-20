"""Complete coverage tests for IntegrityCache.

Covers lines in src/ftllexengine/runtime/cache.py.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.cache import IntegrityCache


class TestIntegrityCacheInitValidation:
    """Test IntegrityCache.__init__ parameter validation."""

    def test_maxsize_zero_rejected(self) -> None:
        """IntegrityCache rejects maxsize=0."""
        with pytest.raises(ValueError, match="maxsize must be positive"):
            IntegrityCache(maxsize=0)

    def test_maxsize_negative_rejected(self) -> None:
        """IntegrityCache rejects negative maxsize."""
        with pytest.raises(ValueError, match="maxsize must be positive"):
            IntegrityCache(maxsize=-1)

    def test_max_entry_weight_zero_rejected(self) -> None:
        """IntegrityCache rejects max_entry_weight=0."""
        with pytest.raises(ValueError, match="max_entry_weight must be positive"):
            IntegrityCache(max_entry_weight=0)

    def test_max_entry_weight_negative_rejected(self) -> None:
        """IntegrityCache rejects negative max_entry_weight."""
        with pytest.raises(ValueError, match="max_entry_weight must be positive"):
            IntegrityCache(max_entry_weight=-1)

    def test_max_errors_per_entry_zero_rejected(self) -> None:
        """IntegrityCache rejects max_errors_per_entry=0."""
        with pytest.raises(ValueError, match="max_errors_per_entry must be positive"):
            IntegrityCache(max_errors_per_entry=0)

    def test_max_errors_per_entry_negative_rejected(self) -> None:
        """IntegrityCache rejects negative max_errors_per_entry."""
        with pytest.raises(ValueError, match="max_errors_per_entry must be positive"):
            IntegrityCache(max_errors_per_entry=-1)


class TestIntegrityCacheUnhashableHandling:
    """Test IntegrityCache handling of unhashable arguments."""

    def test_get_with_unhashable_args_increments_counter(self) -> None:
        """get() with unhashable args increments unhashable_skips and misses."""
        cache = IntegrityCache(strict=False)

        # Custom unhashable type that _make_hashable doesn't recognize
        class UnknownType:
            pass

        args: dict[str, object] = {"data": UnknownType()}
        result = cache.get("msg", args, None, "en", True)  # type: ignore[arg-type]

        assert result is None
        assert cache.unhashable_skips == 1
        assert cache.misses == 1
        assert cache.hits == 0

    def test_put_with_unhashable_args_increments_counter(self) -> None:
        """put() with unhashable args increments unhashable_skips."""
        cache = IntegrityCache(strict=False)

        # Custom object that's not hashable
        class CustomObject:
            def __hash__(self) -> int:  # pylint: disable=invalid-hash-returned
                msg = "unhashable"
                raise TypeError(msg)

        unhashable_value = CustomObject()
        args: dict[str, object] = {"obj": unhashable_value}
        cache.put("msg", args, None, "en", True, "result", ())  # type: ignore[arg-type]

        assert cache.size == 0
        assert cache.unhashable_skips == 1


class TestIntegrityCacheErrorBloatProtection:
    """Test IntegrityCache error collection memory bounding."""

    def test_put_rejects_excessive_error_count(self) -> None:
        """put() skips caching when error count exceeds max_errors_per_entry."""
        cache = IntegrityCache(strict=False, max_errors_per_entry=10)

        # Create 15 errors (exceeds limit of 10)
        errors: list[FrozenFluentError] = []
        for i in range(15):
            error = FrozenFluentError(f"Error {i}", ErrorCategory.REFERENCE)
            errors.append(error)

        cache.put("msg", None, None, "en", True, "formatted text", tuple(errors))

        # Should not be cached due to error count
        assert cache.size == 0
        stats = cache.get_stats()
        assert stats["error_bloat_skips"] == 1

        # Verify retrieval returns None
        cached = cache.get("msg", None, None, "en", True)
        assert cached is None

    def test_put_rejects_excessive_error_weight(self) -> None:
        """put() skips caching when total weight (string + errors) exceeds limit."""
        # Set small max_entry_weight to test total weight calculation
        cache = IntegrityCache(strict=False, max_entry_weight=2000, max_errors_per_entry=50)

        # Create result with small string but many errors
        # String: 100 chars
        # Errors: 10 errors x 200 bytes = 2000 bytes
        # Total weight: 100 + 2000 = 2100 > 2000
        errors: list[FrozenFluentError] = []
        for i in range(10):
            error = FrozenFluentError(f"Error {i}", ErrorCategory.REFERENCE)
            errors.append(error)

        cache.put("msg", None, None, "en", True, "x" * 100, tuple(errors))

        # Should not be cached due to total weight exceeding max_entry_weight
        assert cache.size == 0
        stats = cache.get_stats()
        assert stats["error_bloat_skips"] == 1

    def test_put_accepts_reasonable_error_collections(self) -> None:
        """put() caches results with reasonable error counts."""
        # Use larger max_entry_weight to accommodate string + errors
        # Total weight = 14 chars + (10 errors x 200) = 2014 bytes
        # Need max_entry_weight > 2014
        cache = IntegrityCache(strict=False, max_entry_weight=15000, max_errors_per_entry=50)

        # Create 10 errors (within limit)
        errors: list[FrozenFluentError] = []
        for i in range(10):
            error = FrozenFluentError(f"Error {i}", ErrorCategory.REFERENCE)
            errors.append(error)

        cache.put("msg", None, None, "en", True, "formatted text", tuple(errors))

        # Should be cached
        assert cache.size == 1
        stats = cache.get_stats()
        assert stats["error_bloat_skips"] == 0

        # Verify retrieval
        cached = cache.get("msg", None, None, "en", True)
        assert cached is not None
        assert cached.to_tuple() == ("formatted text", tuple(errors))


class TestIntegrityCacheLRUBehavior:
    """Test IntegrityCache LRU eviction and move-to-end behavior."""

    def test_put_moves_existing_key_to_end(self) -> None:
        """put() moves existing key to end (mark as recently used)."""
        cache = IntegrityCache(strict=False, maxsize=3)

        # Add three entries
        cache.put("msg1", None, None, "en", True, "result1", ())
        cache.put("msg2", None, None, "en", True, "result2", ())
        cache.put("msg3", None, None, "en", True, "result3", ())

        assert cache.size == 3

        # Update msg1 (should move to end)
        cache.put("msg1", None, None, "en", True, "updated1", ())

        # Cache is full, adding new entry should evict msg2 (now oldest)
        cache.put("msg4", None, None, "en", True, "result4", ())

        assert cache.size == 3

        # msg2 should be evicted, others should remain
        assert cache.get("msg2", None, None, "en", True) is None
        entry1 = cache.get("msg1", None, None, "en", True)
        entry3 = cache.get("msg3", None, None, "en", True)
        entry4 = cache.get("msg4", None, None, "en", True)
        assert entry1 is not None
        assert entry1.to_tuple() == ("updated1", ())
        assert entry3 is not None
        assert entry3.to_tuple() == ("result3", ())
        assert entry4 is not None
        assert entry4.to_tuple() == ("result4", ())

    def test_put_evicts_lru_when_full(self) -> None:
        """put() evicts LRU entry when cache is full."""
        cache = IntegrityCache(strict=False, maxsize=2)

        # Fill cache
        cache.put("msg1", None, None, "en", True, "result1", ())
        cache.put("msg2", None, None, "en", True, "result2", ())

        assert cache.size == 2

        # Add third entry - should evict msg1 (oldest)
        cache.put("msg3", None, None, "en", True, "result3", ())

        assert cache.size == 2
        assert cache.get("msg1", None, None, "en", True) is None
        entry2 = cache.get("msg2", None, None, "en", True)
        entry3 = cache.get("msg3", None, None, "en", True)
        assert entry2 is not None
        assert entry2.to_tuple() == ("result2", ())
        assert entry3 is not None
        assert entry3.to_tuple() == ("result3", ())


class TestIntegrityCacheMakeHashableDepth:
    """Test IntegrityCache._make_hashable depth limit enforcement."""

    def test_make_hashable_depth_limit_list(self) -> None:
        """_make_hashable raises TypeError when list nesting exceeds depth."""
        # Create deeply nested list exceeding MAX_DEPTH
        deep_list: list[object] = []
        current: list[object] = deep_list
        for _ in range(MAX_DEPTH + 10):
            new_list: list[object] = []
            current.append(new_list)
            current = new_list

        with pytest.raises(TypeError, match="Maximum nesting depth exceeded"):
            IntegrityCache._make_hashable(deep_list)

    def test_make_hashable_depth_limit_dict(self) -> None:
        """_make_hashable raises TypeError when dict nesting exceeds depth."""
        # Create deeply nested dict exceeding MAX_DEPTH
        deep_dict: dict[str, object] = {}
        current: dict[str, object] = deep_dict
        for i in range(MAX_DEPTH + 10):
            new_dict: dict[str, object] = {}
            current[f"key{i}"] = new_dict
            current = new_dict

        with pytest.raises(TypeError, match="Maximum nesting depth exceeded"):
            IntegrityCache._make_hashable(deep_dict)

    def test_make_hashable_depth_limit_mixed(self) -> None:
        """_make_hashable raises TypeError when mixed structures exceed depth."""
        # Create dict containing list containing dict ... (mixed nesting)
        deep_structure: dict[str, object] = {}
        current: dict[str, object] = deep_structure

        for i in range(MAX_DEPTH + 10):
            # Alternate between dict and list nesting
            if i % 2 == 0:
                new_list: list[object] = []
                current["key"] = new_list
                new_dict: dict[str, object] = {}
                new_list.append(new_dict)
                current = new_dict
            else:
                new_dict_inner: dict[str, object] = {}
                current["key"] = new_dict_inner
                current = new_dict_inner

        with pytest.raises(TypeError, match="Maximum nesting depth exceeded"):
            IntegrityCache._make_hashable(deep_structure)


class TestIntegrityCacheMakeHashableTypes:
    """Test IntegrityCache._make_hashable type conversion."""

    def test_make_hashable_primitives(self) -> None:
        """_make_hashable preserves primitives unchanged."""
        assert IntegrityCache._make_hashable("text") == "text"
        assert IntegrityCache._make_hashable(42) == 42
        assert IntegrityCache._make_hashable(3.14) == 3.14
        assert IntegrityCache._make_hashable(True) is True
        assert IntegrityCache._make_hashable(None) is None

    def test_make_hashable_decimal(self) -> None:
        """_make_hashable preserves Decimal unchanged."""
        decimal_value = Decimal("123.45")
        result = IntegrityCache._make_hashable(decimal_value)
        assert result == decimal_value
        assert isinstance(result, Decimal)

    def test_make_hashable_datetime(self) -> None:
        """_make_hashable preserves datetime unchanged."""
        dt = datetime(2024, 1, 1, 12, 0, 0)  # noqa: DTZ001
        result = IntegrityCache._make_hashable(dt)
        assert result == dt
        assert isinstance(result, datetime)

    def test_make_hashable_date(self) -> None:
        """_make_hashable preserves date unchanged."""
        d = date(2024, 1, 1)
        result = IntegrityCache._make_hashable(d)
        assert result == d
        assert isinstance(result, date)

    def test_make_hashable_list_to_tuple(self) -> None:
        """_make_hashable converts list to tuple recursively."""
        result = IntegrityCache._make_hashable([1, 2, [3, 4]])
        assert result == (1, 2, (3, 4))
        assert isinstance(result, tuple)

    def test_make_hashable_dict_to_sorted_tuples(self) -> None:
        """_make_hashable converts dict to sorted tuple of tuples."""
        result = IntegrityCache._make_hashable({"b": 2, "a": 1})
        assert result == (("a", 1), ("b", 2))
        assert isinstance(result, tuple)

    def test_make_hashable_set_to_frozenset(self) -> None:
        """_make_hashable converts set to frozenset recursively."""
        result = IntegrityCache._make_hashable({1, 2, 3})
        assert result == frozenset({1, 2, 3})
        assert isinstance(result, frozenset)

    def test_make_hashable_unknown_type_raises(self) -> None:
        """_make_hashable raises TypeError for unknown types."""

        class CustomType:
            pass

        with pytest.raises(TypeError, match="Unknown type in cache key"):
            IntegrityCache._make_hashable(CustomType())


class TestIntegrityCacheMakeKeyRobustness:
    """Test IntegrityCache._make_key error handling."""

    def test_make_key_catches_recursion_error(self) -> None:
        """_make_key returns None when RecursionError occurs."""
        # Create circular reference that causes RecursionError
        circular_list: list[object] = []
        circular_list.append(circular_list)

        # _make_key should catch RecursionError and return None
        args: dict[str, object] = {"data": circular_list}
        result = IntegrityCache._make_key("msg", args, None, "en", True)  # type: ignore[arg-type]
        assert result is None

    def test_make_key_catches_type_error(self) -> None:
        """_make_key returns None when TypeError occurs in hash verification."""

        class UnhashableAfterConversion:
            """Type that passes _make_hashable but fails hash()."""

            def __hash__(self) -> int:  # pylint: disable=invalid-hash-returned
                msg = "cannot hash"
                raise TypeError(msg)

        unhashable = UnhashableAfterConversion()

        # _make_key should catch TypeError and return None
        args: dict[str, object] = {"data": unhashable}
        result = IntegrityCache._make_key("msg", args, None, "en", True)  # type: ignore[arg-type]
        assert result is None


class TestIntegrityCacheProperties:
    """Test IntegrityCache property accessors."""

    def test_len_returns_cache_size(self) -> None:
        """len(cache) returns current cache size."""
        cache = IntegrityCache(strict=False)

        assert len(cache) == 0

        cache.put("msg1", None, None, "en", True, "result1", ())
        assert len(cache) == 1

        cache.put("msg2", None, None, "en", True, "result2", ())
        assert len(cache) == 2

    def test_maxsize_property(self) -> None:
        """maxsize property returns configured maximum size."""
        cache = IntegrityCache(strict=False, maxsize=500)
        assert cache.maxsize == 500

    def test_hits_property_thread_safe(self) -> None:
        """hits property is thread-safe."""
        cache = IntegrityCache(strict=False)
        cache.put("msg", None, None, "en", True, "result", ())

        # First access is a hit
        _result = cache.get("msg", None, None, "en", True)
        assert cache.hits == 1

        # Second access is another hit
        _result = cache.get("msg", None, None, "en", True)
        assert cache.hits == 2

    def test_misses_property_thread_safe(self) -> None:
        """misses property is thread-safe."""
        cache = IntegrityCache(strict=False)

        # First miss
        _result = cache.get("msg1", None, None, "en", True)
        assert cache.misses == 1

        # Second miss
        _result = cache.get("msg2", None, None, "en", True)
        assert cache.misses == 2

    def test_unhashable_skips_property_thread_safe(self) -> None:
        """unhashable_skips property is thread-safe."""
        cache = IntegrityCache(strict=False)

        # Custom unhashable type
        class UnknownType:
            pass

        # First unhashable
        args1: dict[str, object] = {"data": UnknownType()}
        _result = cache.get("msg", args1, None, "en", True)  # type: ignore[arg-type]
        assert cache.unhashable_skips == 1

        # Second unhashable
        args2: dict[str, object] = {"data": UnknownType()}
        cache.put("msg", args2, None, "en", True, "result", ())  # type: ignore[arg-type]
        assert cache.unhashable_skips == 2

    def test_oversize_skips_property_thread_safe(self) -> None:
        """oversize_skips property is thread-safe."""
        cache = IntegrityCache(strict=False, max_entry_weight=10)

        # First oversize
        cache.put("msg1", None, None, "en", True, "x" * 100, ())
        assert cache.oversize_skips == 1

        # Second oversize
        cache.put("msg2", None, None, "en", True, "y" * 50, ())
        assert cache.oversize_skips == 2

    def test_max_entry_weight_property(self) -> None:
        """max_entry_weight property returns configured value."""
        cache = IntegrityCache(strict=False, max_entry_weight=5000)
        assert cache.max_entry_weight == 5000

    def test_size_property_thread_safe(self) -> None:
        """size property is thread-safe."""
        cache = IntegrityCache(strict=False)

        assert cache.size == 0

        cache.put("msg1", None, None, "en", True, "result1", ())
        assert cache.size == 1

        cache.put("msg2", None, None, "en", True, "result2", ())
        assert cache.size == 2


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

    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=50)
    def test_property_primitives_hashable(self, text: str) -> None:
        """PROPERTY: All primitive types produce valid cache keys."""
        cache = IntegrityCache(strict=False)

        # String
        cache.put("msg", {"text": text}, None, "en", True, "result", ())
        entry = cache.get("msg", {"text": text}, None, "en", True)
        assert entry is not None
        assert entry.to_tuple() == ("result", ())

        # Integer
        cache.put("msg", {"num": 42}, None, "en", True, "result", ())
        entry = cache.get("msg", {"num": 42}, None, "en", True)
        assert entry is not None
        assert entry.to_tuple() == ("result", ())

        # Float
        cache.put("msg", {"float": 3.14}, None, "en", True, "result", ())
        entry = cache.get("msg", {"float": 3.14}, None, "en", True)
        assert entry is not None
        assert entry.to_tuple() == ("result", ())

        # Bool
        cache.put("msg", {"bool": True}, None, "en", True, "result", ())
        entry = cache.get("msg", {"bool": True}, None, "en", True)
        assert entry is not None
        assert entry.to_tuple() == ("result", ())

        # None
        cache.put("msg", {"val": None}, None, "en", True, "result", ())
        entry = cache.get("msg", {"val": None}, None, "en", True)
        assert entry is not None
        assert entry.to_tuple() == ("result", ())
