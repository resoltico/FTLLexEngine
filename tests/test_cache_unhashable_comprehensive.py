"""Comprehensive tests for runtime.cache argument handling.

Tests FormatCache behavior with various argument types including hashable
conversions (lists, dicts, sets) and truly unhashable objects.

v0.13.0: Updated to test new behavior where lists/dicts/sets are converted
to hashable equivalents (tuples/frozensets) for caching.
"""

from typing import NoReturn

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.runtime.cache import FormatCache


class TestCacheBasicOperations:
    """Tests for basic cache operations to achieve full coverage."""

    def test_init_with_zero_maxsize_raises(self) -> None:
        """Verify __init__ raises ValueError for maxsize <= 0 (lines 65-66)."""
        with pytest.raises(ValueError, match="maxsize must be positive"):
            FormatCache(maxsize=0)

    def test_init_with_negative_maxsize_raises(self) -> None:
        """Verify __init__ raises ValueError for negative maxsize."""
        with pytest.raises(ValueError, match="maxsize must be positive"):
            FormatCache(maxsize=-1)

    def test_get_cache_hit_path(self) -> None:
        """Verify cache hit path in get() (lines 106-108)."""
        cache = FormatCache(maxsize=100)

        # Put a value in cache
        args = {"key": "value"}
        result = ("formatted_text", ())
        cache.put("msg-id", args, None, "en-US", result)

        # Get should hit cache
        cached = cache.get("msg-id", args, None, "en-US")

        assert cached == result
        assert cache.hits == 1
        assert cache.misses == 0

    def test_put_updates_existing_key(self) -> None:
        """Verify put() updates existing key and moves to end (line 143)."""
        cache = FormatCache(maxsize=100)

        args = {"key": "value"}
        result1 = ("text1", ())
        result2 = ("text2", ())

        # Put initial value
        cache.put("msg-id", args, None, "en-US", result1)
        assert len(cache) == 1

        # Put updated value for same key
        cache.put("msg-id", args, None, "en-US", result2)
        assert len(cache) == 1  # Still one entry

        # Get should return updated value
        cached = cache.get("msg-id", args, None, "en-US")
        assert cached == result2

    def test_put_evicts_lru_when_full(self) -> None:
        """Verify put() evicts LRU entry when cache is full (line 146)."""
        cache = FormatCache(maxsize=2)

        # Fill cache to capacity
        cache.put("msg1", {"k": "v1"}, None, "en-US", ("text1", ()))
        cache.put("msg2", {"k": "v2"}, None, "en-US", ("text2", ()))
        assert len(cache) == 2

        # Add third entry - should evict first (LRU)
        cache.put("msg3", {"k": "v3"}, None, "en-US", ("text3", ()))
        assert len(cache) == 2

        # First entry should be gone
        result1 = cache.get("msg1", {"k": "v1"}, None, "en-US")
        assert result1 is None

        # Second and third should be present
        result2 = cache.get("msg2", {"k": "v2"}, None, "en-US")
        result3 = cache.get("msg3", {"k": "v3"}, None, "en-US")
        assert result2 is not None
        assert result3 is not None

    def test_make_key_with_none_args(self) -> None:
        """Verify _make_key handles None args correctly (line 205)."""
        key = FormatCache._make_key("msg-id", None, None, "en-US")

        assert key is not None
        assert key == ("msg-id", (), None, "en-US")

    def test_maxsize_property(self) -> None:
        """Verify maxsize property returns correct value (line 231)."""
        cache = FormatCache(maxsize=500)

        assert cache.maxsize == 500


class TestCacheHashableConversion:
    """Tests for FormatCache automatic conversion of unhashable types to hashable.

    v0.13.0: Lists, dicts, and sets are now converted to tuples, sorted tuples,
    and frozensets respectively, enabling caching for these types.
    """

    def test_get_with_list_value_now_cacheable(self) -> None:
        """Verify get() converts lists to tuples for caching (v0.13.0)."""
        cache = FormatCache(maxsize=100)

        # Args contain a list (now converted to tuple)
        args = {"key": [1, 2, 3]}
        result = ("formatted", ())

        # Put with list value
        cache.put("msg-id", args, None, "en-US", result)  # type: ignore[arg-type]

        # Get should find cached value (list converted to same tuple)
        cached = cache.get("msg-id", args, None, "en-US")  # type: ignore[arg-type]

        assert cached == result
        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    def test_get_with_dict_value_now_cacheable(self) -> None:
        """Verify get() converts dicts to sorted tuples for caching (v0.13.0)."""
        cache = FormatCache(maxsize=100)

        # Args contain a nested dict (now converted to sorted tuple)
        args = {"key": {"nested": "value"}}
        result = ("formatted", ())

        cache.put("msg-id", args, None, "en-US", result)  # type: ignore[arg-type]
        cached = cache.get("msg-id", args, None, "en-US")  # type: ignore[arg-type]

        assert cached == result
        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    def test_get_with_set_value_now_cacheable(self) -> None:
        """Verify get() converts sets to frozensets for caching (v0.13.0)."""
        cache = FormatCache(maxsize=100)

        # Args contain a set (now converted to frozenset)
        args = {"key": {1, 2, 3}}
        result = ("formatted", ())

        cache.put("msg-id", args, None, "en-US", result)  # type: ignore[arg-type]
        cached = cache.get("msg-id", args, None, "en-US")  # type: ignore[arg-type]

        assert cached == result
        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    def test_put_with_list_value_now_caches(self) -> None:
        """Verify put() caches list values by converting to tuples (v0.13.0)."""
        cache = FormatCache(maxsize=100)

        # Args contain a list (now converted to tuple)
        args = {"items": [1, 2, 3]}
        result = ("formatted", ())

        cache.put("msg-id", args, None, "en-US", result)  # type: ignore[arg-type]

        assert len(cache) == 1  # Now cached
        assert cache.unhashable_skips == 0

    def test_put_with_dict_value_now_caches(self) -> None:
        """Verify put() caches dict values by converting to tuples (v0.13.0)."""
        cache = FormatCache(maxsize=100)

        args = {"config": {"option": "value"}}
        result = ("formatted", ())

        cache.put("msg-id", args, None, "en-US", result)  # type: ignore[arg-type]

        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    def test_make_key_converts_list_to_tuple(self) -> None:
        """Verify _make_key converts lists to tuples (v0.13.0)."""
        args = {"list_value": [1, 2, 3]}

        key = FormatCache._make_key("msg-id", args, None, "en-US")  # type: ignore[arg-type]

        assert key is not None  # Now returns valid key

    def test_make_key_converts_nested_structures(self) -> None:
        """Verify _make_key converts nested unhashable values (v0.13.0)."""
        args: dict[str, object] = {
            "list": [1, 2],
            "dict": {"nested": "value"},
        }

        key = FormatCache._make_key("msg-id", args, None, "en-US")  # type: ignore[arg-type]

        assert key is not None  # Now returns valid key

    def test_make_hashable_list(self) -> None:
        """Verify _make_hashable converts lists to tuples."""
        result = FormatCache._make_hashable([1, 2, 3])
        assert result == (1, 2, 3)

    def test_make_hashable_dict(self) -> None:
        """Verify _make_hashable converts dicts to sorted tuples."""
        result = FormatCache._make_hashable({"b": 2, "a": 1})
        assert result == (("a", 1), ("b", 2))

    def test_make_hashable_set(self) -> None:
        """Verify _make_hashable converts sets to frozensets."""
        result = FormatCache._make_hashable({1, 2, 3})
        assert result == frozenset({1, 2, 3})

    def test_make_hashable_nested(self) -> None:
        """Verify _make_hashable handles nested structures."""
        result = FormatCache._make_hashable([{"a": [1, 2]}, {3, 4}])
        # List -> tuple, dict -> sorted tuple, nested list -> tuple, set -> frozenset
        assert isinstance(result, tuple)

    @given(
        st.lists(st.integers(), min_size=1, max_size=10),
    )
    def test_get_with_various_lists_cacheable(self, list_value: list[int]) -> None:
        """Property: get() now caches list-valued args (v0.13.0)."""
        cache = FormatCache(maxsize=100)
        args = {"list_arg": list_value}
        result = ("formatted", ())

        cache.put("msg-id", args, None, "en-US", result)  # type: ignore[arg-type]
        cached = cache.get("msg-id", args, None, "en-US")  # type: ignore[arg-type]

        assert cached == result
        assert cache.unhashable_skips == 0

    @given(
        st.dictionaries(st.text(min_size=1, max_size=10), st.integers(), min_size=1, max_size=5),
    )
    def test_put_with_various_dicts_cacheable(self, dict_value: dict[str, int]) -> None:
        """Property: put() now caches dict-valued args (v0.13.0)."""
        cache = FormatCache(maxsize=100)
        args = {"dict_arg": dict_value}
        result = ("formatted", ())

        cache.put("msg-id", args, None, "en-US", result)  # type: ignore[arg-type]

        assert len(cache) == 1  # Now cached
        assert cache.unhashable_skips == 0

    def test_mixed_hashable_and_converted_args(self) -> None:
        """Verify cache handles mixed hashable/convertible args correctly."""
        cache = FormatCache(maxsize=100)

        # Some hashable, some convertible
        args: dict[str, object] = {
            "str_arg": "value",
            "int_arg": 42,
            "list_arg": [1, 2, 3],  # Converted to tuple
        }
        result = ("formatted", ())

        cache.put("msg-id", args, None, "en-US", result)  # type: ignore[arg-type]
        cached = cache.get("msg-id", args, None, "en-US")  # type: ignore[arg-type]

        assert cached == result
        assert cache.unhashable_skips == 0

    def test_empty_list_cacheable(self) -> None:
        """Verify empty lists are converted and cached (v0.13.0)."""
        cache = FormatCache(maxsize=100)

        args: dict[str, list[object]] = {"empty_list": []}
        result = ("formatted", ())

        cache.put("msg-id", args, None, "en-US", result)  # type: ignore[arg-type]
        cached = cache.get("msg-id", args, None, "en-US")  # type: ignore[arg-type]

        assert cached == result
        assert len(cache) == 1

    def test_empty_dict_cacheable(self) -> None:
        """Verify empty dicts are converted and cached (v0.13.0)."""
        cache = FormatCache(maxsize=100)

        args: dict[str, dict[object, object]] = {"empty_dict": {}}
        result = ("formatted", ())

        cache.put("msg-id", args, None, "en-US", result)  # type: ignore[arg-type]
        cached = cache.get("msg-id", args, None, "en-US")  # type: ignore[arg-type]

        assert cached == result
        assert len(cache) == 1


class TestCacheTrulyUnhashableObjects:
    """Tests for handling truly unhashable objects that cannot be converted."""

    def test_unhashable_custom_object_skipped(self) -> None:
        """Verify cache skips custom unhashable objects that cannot be converted."""
        cache = FormatCache(maxsize=100)

        class UnhashableClass:
            """Custom class that's not hashable and not convertible."""

            def __init__(self) -> None:
                self.data = [1, 2, 3]

            def __hash__(self) -> NoReturn:  # pylint: disable=invalid-hash-returned
                msg = "unhashable type"
                raise TypeError(msg)

        args = {"custom": UnhashableClass()}

        result = cache.get("msg-id", args, None, "en-US")  # type: ignore[arg-type]

        assert result is None
        assert cache.unhashable_skips == 1

    def test_unhashable_skips_property(self) -> None:
        """Verify unhashable_skips only counts truly unhashable objects."""
        cache = FormatCache(maxsize=100)

        # Initial value
        assert cache.unhashable_skips == 0

        # Lists/dicts/sets are now convertible, should NOT increment
        cache.get("msg1", {"list": [1]}, None, "en-US")  # type: ignore[dict-item]
        assert cache.unhashable_skips == 0  # Not skipped anymore

        cache.put("msg2", {"dict": {}}, None, "en-US", ("result", ()))  # type: ignore[dict-item]
        assert cache.unhashable_skips == 0  # Not skipped anymore

    def test_unhashable_skips_resets_on_clear(self) -> None:
        """Verify unhashable_skips resets to 0 after clear()."""
        cache = FormatCache(maxsize=100)

        class UnhashableClass:
            """Custom class that's not hashable."""

            def __hash__(self) -> NoReturn:  # pylint: disable=invalid-hash-returned
                msg = "unhashable type"
                raise TypeError(msg)

        # Generate unhashable skips with truly unhashable objects
        cache.get("msg", {"obj": UnhashableClass()}, None, "en-US")  # type: ignore[dict-item]
        assert cache.unhashable_skips == 1

        # Clear should reset
        cache.clear()
        assert cache.unhashable_skips == 0

    def test_get_stats_includes_unhashable_skips(self) -> None:
        """Verify get_stats() includes unhashable_skips count."""
        cache = FormatCache(maxsize=100)

        class UnhashableClass:
            """Custom class that's not hashable."""

            def __hash__(self) -> NoReturn:  # pylint: disable=invalid-hash-returned
                msg = "unhashable type"
                raise TypeError(msg)

        # Generate unhashable operations with truly unhashable objects
        cache.get("msg", {"obj": UnhashableClass()}, None, "en-US")  # type: ignore[dict-item]

        stats = cache.get_stats()

        assert "unhashable_skips" in stats
        assert stats["unhashable_skips"] == 1
        assert stats["misses"] == 1  # get increments misses

    def test_hashable_args_do_not_increment_unhashable_skips(self) -> None:
        """Verify hashable args don't increment unhashable_skips counter."""
        cache = FormatCache(maxsize=100)

        # Fully hashable args
        args: dict[str, object] = {"str": "value", "int": 42, "float": 3.14}

        cache.get("msg1", args, None, "en-US")  # type: ignore[arg-type]
        cache.put("msg2", args, None, "en-US", ("result", ()))  # type: ignore[arg-type]

        # Should not increment unhashable_skips
        assert cache.unhashable_skips == 0
        assert cache.misses == 1  # get miss
