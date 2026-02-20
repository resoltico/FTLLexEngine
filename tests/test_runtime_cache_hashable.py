"""Tests for IntegrityCache hashable key construction, NaN normalization, and
unhashable argument handling.

Covers:
- __init__ parameter validation
- _make_hashable type-tagged conversions (bool/int/float/Decimal/datetime/date/
  FluentNumber/list/dict/set/tuple) for collision-free cache keys
- Depth limiting to prevent O(N) key computation on adversarial inputs
- _make_key integration and error recovery (RecursionError, TypeError)
- NaN normalization (float/Decimal) to prevent cache pollution DoS vectors
- Hashable conversion of list/dict/set/tuple args for full cache coverage
- Unhashable argument graceful bypass (skips caching, increments counter)
- Error bloat protection (max_entry_weight, max_errors_per_entry)
- LRU eviction and move-to-end behavior
- Property accessors (size, hits, misses, unhashable_skips, oversize_skips)
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, NoReturn

import pytest
from hypothesis import event, example, given, settings
from hypothesis import strategies as st

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.runtime.function_bridge import FluentNumber, FluentValue

# ============================================================================
# SECTION 1: INITIALIZATION VALIDATION
# ============================================================================


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


# ============================================================================
# SECTION 2: MAKE HASHABLE - TYPE-TAGGED CONVERSIONS
# ============================================================================


class TestMakeHashableTypes:
    """Test IntegrityCache._make_hashable type-tagged conversions.

    Python's hash equality (hash(1) == hash(True) == hash(1.0)) would cause
    cache collisions. Type-tagging ensures distinct cache keys per type.
    """

    def test_make_hashable_primitives(self) -> None:
        """_make_hashable type-tags bool/int/float to prevent hash collisions.

        str and None are not tagged (no collision risk).
        bool/int/float are type-tagged so hash(1) == hash(True) == hash(1.0)
        does not cause cache key collisions.
        """
        assert IntegrityCache._make_hashable("text") == "text"
        assert IntegrityCache._make_hashable(None) is None
        assert IntegrityCache._make_hashable(42) == ("__int__", 42)
        assert IntegrityCache._make_hashable(True) == ("__bool__", True)
        assert IntegrityCache._make_hashable(False) == ("__bool__", False)
        # float uses str() to distinguish -0.0 from 0.0
        assert IntegrityCache._make_hashable(3.14) == ("__float__", "3.14")

    def test_make_hashable_decimal(self) -> None:
        """_make_hashable type-tags Decimal with str() to preserve scale.

        Decimal("1.0") and Decimal("1") are equal in Python but produce
        different plural forms in CLDR (visible fraction digits differ).
        Type-tagging with str() preserves scale for correct cache keys.
        """
        result = IntegrityCache._make_hashable(Decimal("123.45"))
        assert result == ("__decimal__", "123.45")
        assert isinstance(result, tuple)

    def test_make_hashable_datetime_naive(self) -> None:
        """_make_hashable type-tags naive datetime with isoformat and '__naive__'.

        Two datetimes representing the same UTC instant with different tzinfo
        compare equal but format differently. Including tz_key prevents collision.
        Naive datetime gets '__naive__' sentinel as tz_key.
        """
        dt = datetime(2024, 1, 1, 12, 0, 0)  # noqa: DTZ001
        result = IntegrityCache._make_hashable(dt)
        assert result == ("__datetime__", "2024-01-01T12:00:00", "__naive__")
        assert isinstance(result, tuple)

    def test_make_hashable_datetime_aware(self) -> None:
        """_make_hashable type-tags aware datetime with UTC timezone string.

        Aware datetime includes the tzinfo string to prevent collisions between
        identical times expressed in different timezones.
        """
        dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = IntegrityCache._make_hashable(dt)
        assert result == ("__datetime__", "2024-01-01T12:00:00+00:00", "UTC")
        assert isinstance(result, tuple)

    def test_make_hashable_date(self) -> None:
        """_make_hashable type-tags date with isoformat."""
        d = date(2024, 1, 1)
        result = IntegrityCache._make_hashable(d)
        assert result == ("__date__", "2024-01-01")
        assert isinstance(result, tuple)

    def test_make_hashable_fluent_number(self) -> None:
        """_make_hashable type-tags FluentNumber with underlying type info for precision.

        FluentNumber wraps numeric values with formatting options. The inner value
        is recursively normalized to handle NaN consistency.
        """
        value = FluentNumber(value=42, formatted="42")
        result = IntegrityCache._make_hashable(value)
        assert result == ("__fluentnumber__", "int", ("__int__", 42), "42", None)

    def test_make_hashable_list_to_tuple(self) -> None:
        """_make_hashable type-tags list distinctly from tuple.

        str([1,2]) = "[1, 2]" but str((1,2)) = "(1, 2)". Type-tagging with
        '__list__' ensures lists and tuples produce different cache keys even
        after both are converted to tuples internally.
        """
        result = IntegrityCache._make_hashable([1, 2, [3, 4]])
        inner_list = ("__list__", (("__int__", 3), ("__int__", 4)))
        expected = ("__list__", (("__int__", 1), ("__int__", 2), inner_list))
        assert result == expected
        assert isinstance(result, tuple)

    def test_make_hashable_dict_to_sorted_tuples(self) -> None:
        """_make_hashable converts dict to type-tagged sorted tuple of tuples."""
        result = IntegrityCache._make_hashable({"b": 2, "a": 1})
        assert isinstance(result, tuple)
        assert result[0] == "__dict__"
        inner = result[1]
        assert isinstance(inner, tuple)
        assert inner == (("a", ("__int__", 1)), ("b", ("__int__", 2)))

    def test_make_hashable_set_to_frozenset(self) -> None:
        """_make_hashable converts set to type-tagged frozenset with type-tagged ints."""
        result = IntegrityCache._make_hashable({1, 2, 3})
        assert isinstance(result, tuple)
        assert result[0] == "__set__"
        inner = result[1]
        expected_inner = frozenset({("__int__", 1), ("__int__", 2), ("__int__", 3)})
        assert inner == expected_inner

    def test_make_hashable_tuple_simple(self) -> None:
        """_make_hashable type-tags tuples to distinguish from lists."""
        result = IntegrityCache._make_hashable((1, 2, 3))
        expected = ("__tuple__", (("__int__", 1), ("__int__", 2), ("__int__", 3)))
        assert result == expected
        assert isinstance(result, tuple)

    def test_make_hashable_tuple_with_nested_list(self) -> None:
        """_make_hashable type-tags nested lists within tuples distinctly."""
        result = IntegrityCache._make_hashable((1, [2, 3], 4))
        inner_list = ("__list__", (("__int__", 2), ("__int__", 3)))
        expected = ("__tuple__", (("__int__", 1), inner_list, ("__int__", 4)))
        assert result == expected
        assert isinstance(result, tuple)
        hash(result)  # Must be hashable end-to-end

    def test_make_hashable_tuple_with_nested_dict(self) -> None:
        """_make_hashable type-tags tuples with nested dicts."""
        result = IntegrityCache._make_hashable((1, {"b": 2, "a": 1}, 3))
        inner_dict = ("__dict__", (("a", ("__int__", 1)), ("b", ("__int__", 2))))
        expected = ("__tuple__", (("__int__", 1), inner_dict, ("__int__", 3)))
        assert result == expected
        hash(result)

    def test_make_hashable_tuple_with_nested_set(self) -> None:
        """_make_hashable type-tags tuples with nested sets."""
        result = IntegrityCache._make_hashable((1, {2, 3}, 4))
        inner_set = ("__set__", frozenset({("__int__", 2), ("__int__", 3)}))
        expected = ("__tuple__", (("__int__", 1), inner_set, ("__int__", 4)))
        assert result == expected
        hash(result)

    def test_make_hashable_deeply_nested_tuple(self) -> None:
        """_make_hashable type-tags all nested tuples, lists, and dicts."""
        result = IntegrityCache._make_hashable((1, (2, [3, {"a": 4}]), 5))
        inner_dict = ("__dict__", (("a", ("__int__", 4)),))
        inner_list = ("__list__", (("__int__", 3), inner_dict))
        inner_tuple = ("__tuple__", (("__int__", 2), inner_list))
        expected = ("__tuple__", (("__int__", 1), inner_tuple, ("__int__", 5)))
        assert result == expected
        hash(result)

    def test_make_hashable_nested_mixed_structures(self) -> None:
        """_make_hashable handles mixed nested list/dict/set structures."""
        result = IntegrityCache._make_hashable([{"a": [1, 2]}, {3, 4}])
        assert isinstance(result, tuple)
        assert result[0] == "__list__"
        # Result must be fully hashable
        hash(result)

    def test_make_hashable_unknown_type_raises(self) -> None:
        """_make_hashable raises TypeError for unrecognized types."""

        class CustomType:
            pass

        with pytest.raises(TypeError, match="Unknown type in cache key"):
            IntegrityCache._make_hashable(CustomType())


# ============================================================================
# SECTION 3: MAKE HASHABLE - DEPTH LIMITING
# ============================================================================


class TestMakeHashableDepth:
    """Test depth limiting in _make_hashable.

    Prevents O(N) key computation on adversarially nested inputs and guards
    against stack overflow via RecursionError transformation.
    """

    def test_shallow_nesting_succeeds(self) -> None:
        """Shallow nested structures convert successfully."""
        shallow = {"a": [1, 2, {"b": 3}]}
        result = IntegrityCache._make_hashable(shallow)
        assert result is not None

    def test_moderate_nesting_succeeds(self) -> None:
        """Moderately nested structures (50 levels) convert successfully."""
        # 50 levels well under MAX_DEPTH
        value: dict[str, Any] | int = 42
        for _ in range(50):
            value = {"nested": value}
        result = IntegrityCache._make_hashable(value)
        assert result is not None

    def test_excessive_nesting_raises_type_error(self) -> None:
        """Excessively nested structures raise TypeError with descriptive message."""
        value: dict[str, Any] | int = 42
        for _ in range(MAX_DEPTH + 10):
            value = {"nested": value}
        with pytest.raises(TypeError, match="Maximum nesting depth exceeded"):
            IntegrityCache._make_hashable(value)

    def test_custom_depth_parameter_respected(self) -> None:
        """Custom depth parameter overrides default MAX_DEPTH."""
        value: dict[str, Any] | int = 42
        for _ in range(15):
            value = {"nested": value}

        # Should fail at depth=10
        with pytest.raises(TypeError, match="Maximum nesting depth exceeded"):
            IntegrityCache._make_hashable(value, depth=10)

        # Should succeed at depth=20
        result = IntegrityCache._make_hashable(value, depth=20)
        assert result is not None

    def test_list_nesting_depth_limited(self) -> None:
        """List nesting respects depth limit."""
        value: list[Any] | int = 42
        for _ in range(MAX_DEPTH + 10):
            value = [value]
        with pytest.raises(TypeError, match="Maximum nesting depth exceeded"):
            IntegrityCache._make_hashable(value)

    def test_set_nesting_handled(self) -> None:
        """Sets with simple values are converted; they cannot nest further.

        Sets cannot contain other sets (sets are unhashable), so depth is
        naturally bounded. Simple sets should convert correctly.
        """
        result = IntegrityCache._make_hashable({1, 2, 3})
        assert isinstance(result, tuple)
        assert result[0] == "__set__"
        assert isinstance(result[1], frozenset)

    def test_mixed_nesting_depth_limited(self) -> None:
        """Mixed dict/list alternating nesting respects depth limit."""
        value: dict[str, Any] | list[Any] | int = 42
        for i in range(MAX_DEPTH + 10):
            value = {"nested": value} if i % 2 == 0 else [value]
        with pytest.raises(TypeError, match="Maximum nesting depth exceeded"):
            IntegrityCache._make_hashable(value)


# ============================================================================
# SECTION 4: MAKE KEY INTEGRATION
# ============================================================================


class TestMakeKey:
    """Test _make_key integration with _make_hashable.

    _make_key builds a cache key tuple from (message_id, args, attribute,
    locale_code, use_isolating). Returns None on any hashing failure,
    allowing cache bypass without raising to the caller.
    """

    def test_make_key_with_none_args(self) -> None:
        """_make_key with None args returns key with empty tuple for args component."""
        key = IntegrityCache._make_key("msg-id", None, None, "en-US", True)
        assert key is not None
        assert key == ("msg-id", (), None, "en-US", True)

    def test_make_key_with_simple_args(self) -> None:
        """_make_key handles simple string/int arguments."""
        key = IntegrityCache._make_key(
            message_id="test",
            args={"name": "Alice", "count": 42},
            attribute=None,
            locale_code="en",
            use_isolating=True,
        )
        assert key is not None

    def test_make_key_with_nested_args(self) -> None:
        """_make_key handles nested list arguments via _make_hashable."""
        key = IntegrityCache._make_key(
            message_id="test",
            args={"items": [1, 2, 3]},
            attribute=None,
            locale_code="en",
            use_isolating=True,
        )
        assert key is not None

    def test_make_key_with_all_fluent_value_types(self) -> None:
        """_make_key accepts all valid FluentValue types."""
        key = IntegrityCache._make_key(
            message_id="test",
            args={
                "string": "hello",
                "int": 42,
                "float": 3.14,
                "decimal": Decimal("99.99"),
                "datetime": datetime(2024, 1, 1, tzinfo=UTC),
                "date": date(2024, 1, 1),
                "fluent_number": FluentNumber(value=100, formatted="100"),
            },
            attribute=None,
            locale_code="en",
            use_isolating=True,
        )
        assert key is not None

    def test_make_key_with_deeply_nested_returns_none(self) -> None:
        """_make_key returns None for excessively nested args (graceful bypass)."""
        deep: dict[str, Any] | int = 42
        for _ in range(MAX_DEPTH + 10):
            deep = {"nested": deep}
        key = IntegrityCache._make_key(
            message_id="test",
            args={"deep": deep},
            attribute=None,
            locale_code="en",
            use_isolating=True,
        )
        assert key is None  # Cache bypass, not a crash

    def test_make_key_with_unknown_type_returns_none(self) -> None:
        """_make_key returns None for unknown types (graceful bypass)."""

        class CustomObject:
            pass

        key = IntegrityCache._make_key(
            message_id="test",
            args={"custom": CustomObject()},  # type: ignore[dict-item]
            attribute=None,
            locale_code="en",
            use_isolating=True,
        )
        assert key is None

    def test_make_key_catches_recursion_error(self) -> None:
        """_make_key returns None when RecursionError occurs (circular reference)."""
        circular_list: list[object] = []
        circular_list.append(circular_list)
        args: dict[str, object] = {"data": circular_list}
        result = IntegrityCache._make_key(
            "msg", args, None, "en", True  # type: ignore[arg-type]
        )
        assert result is None

    def test_make_key_catches_type_error_in_hash(self) -> None:
        """_make_key returns None when TypeError occurs during hash verification."""

        class UnhashableAfterConversion:
            """Passes _make_hashable type dispatch but fails hash()."""

            def __hash__(self) -> int:  # pylint: disable=invalid-hash-returned
                msg = "cannot hash"
                raise TypeError(msg)

        args: dict[str, object] = {"data": UnhashableAfterConversion()}
        result = IntegrityCache._make_key(
            "msg", args, None, "en", True  # type: ignore[arg-type]
        )
        assert result is None


# ============================================================================
# SECTION 5: NaN NORMALIZATION
# ============================================================================


class TestNaNFloatNormalization:
    """Test that float NaN values are normalized in cache keys.

    Security context: float NaN violates Python's equality contract
    (float("nan") != float("nan")). Without normalization each put() with NaN
    creates an unretrievable entry, enabling cache pollution DoS.
    """

    def test_float_nan_cache_key_consistency(self) -> None:
        """Float NaN produces consistent cache key across independent instances."""
        cache = IntegrityCache(strict=False)
        cache.put("msg", {"val": float("nan")}, None, "en", True, "Result", ())
        entry = cache.get("msg", {"val": float("nan")}, None, "en", True)
        assert entry is not None
        assert entry.formatted == "Result"

    def test_float_nan_does_not_pollute_cache(self) -> None:
        """Multiple puts with float NaN update the same entry, not create new ones."""
        cache = IntegrityCache(strict=False, maxsize=100)
        for i in range(10):
            cache.put("msg", {"val": float("nan")}, None, "en", True, f"Value {i}", ())
        stats = cache.get_stats()
        assert stats["size"] == 1, (
            f"Expected 1 entry but got {stats['size']}. "
            "NaN normalization may not be working - cache pollution detected."
        )

    def test_float_nan_different_from_regular_float(self) -> None:
        """Float NaN has different cache key from regular floats."""
        cache = IntegrityCache(strict=False)
        cache.put("msg", {"val": float("nan")}, None, "en", True, "NaN Result", ())
        cache.put("msg", {"val": 1.0}, None, "en", True, "Float Result", ())

        nan_entry = cache.get("msg", {"val": float("nan")}, None, "en", True)
        float_entry = cache.get("msg", {"val": 1.0}, None, "en", True)

        assert nan_entry is not None
        assert nan_entry.formatted == "NaN Result"
        assert float_entry is not None
        assert float_entry.formatted == "Float Result"
        assert cache.get_stats()["size"] == 2


class TestNaNDecimalNormalization:
    """Test that Decimal NaN values are normalized in cache keys."""

    def test_decimal_nan_cache_key_consistency(self) -> None:
        """Decimal NaN produces consistent cache key across independent instances."""
        cache = IntegrityCache(strict=False)
        cache.put("msg", {"val": Decimal("NaN")}, None, "en", True, "Decimal Result", ())
        entry = cache.get("msg", {"val": Decimal("NaN")}, None, "en", True)
        assert entry is not None
        assert entry.formatted == "Decimal Result"

    def test_decimal_nan_does_not_pollute_cache(self) -> None:
        """Multiple puts with Decimal NaN update the same entry."""
        cache = IntegrityCache(strict=False, maxsize=100)
        for i in range(10):
            cache.put("msg", {"val": Decimal("NaN")}, None, "en", True, f"Value {i}", ())
        stats = cache.get_stats()
        assert stats["size"] == 1, (
            f"Expected 1 entry but got {stats['size']}. "
            "Decimal NaN normalization may not be working."
        )

    def test_decimal_snan_normalized_same_as_qnan(self) -> None:
        """Signaling NaN and quiet NaN both normalize to the same canonical key."""
        cache = IntegrityCache(strict=False)
        cache.put("msg", {"val": Decimal("NaN")}, None, "en", True, "QNaN", ())
        # sNaN should resolve to same cache key as qNaN
        entry = cache.get("msg", {"val": Decimal("sNaN")}, None, "en", True)
        assert entry is not None

    def test_decimal_nan_different_from_regular_decimal(self) -> None:
        """Decimal NaN has different cache key from regular Decimal values."""
        cache = IntegrityCache(strict=False)
        cache.put("msg", {"val": Decimal("NaN")}, None, "en", True, "NaN Result", ())
        cache.put("msg", {"val": Decimal("1.0")}, None, "en", True, "Regular Result", ())

        nan_entry = cache.get("msg", {"val": Decimal("NaN")}, None, "en", True)
        regular_entry = cache.get("msg", {"val": Decimal("1.0")}, None, "en", True)

        assert nan_entry is not None
        assert nan_entry.formatted == "NaN Result"
        assert regular_entry is not None
        assert regular_entry.formatted == "Regular Result"
        assert cache.get_stats()["size"] == 2


class TestNaNMixedTypes:
    """Test NaN handling with mixed float and Decimal types."""

    def test_float_nan_and_decimal_nan_are_separate_keys(self) -> None:
        """Float NaN and Decimal NaN produce different cache keys.

        Both are "NaN" semantically but are different types. Type-tagging
        (__float__ vs __decimal__) ensures they cache separately.
        """
        cache = IntegrityCache(strict=False)
        cache.put("msg", {"val": float("nan")}, None, "en", True, "Float NaN", ())
        cache.put("msg", {"val": Decimal("NaN")}, None, "en", True, "Decimal NaN", ())

        float_entry = cache.get("msg", {"val": float("nan")}, None, "en", True)
        decimal_entry = cache.get("msg", {"val": Decimal("NaN")}, None, "en", True)

        assert float_entry is not None
        assert float_entry.formatted == "Float NaN"
        assert decimal_entry is not None
        assert decimal_entry.formatted == "Decimal NaN"
        assert cache.get_stats()["size"] == 2


class TestNaNInNestedStructures:
    """Test NaN normalization in nested data structures."""

    def test_nan_in_list_normalized(self) -> None:
        """NaN values within lists are normalized for cache key consistency."""
        cache = IntegrityCache(strict=False)
        cache.put(
            "msg", {"items": [1.0, float("nan"), 3.0]}, None, "en", True, "List Result", ()
        )
        entry = cache.get(
            "msg", {"items": [1.0, float("nan"), 3.0]}, None, "en", True
        )
        assert entry is not None
        assert entry.formatted == "List Result"

    def test_nan_in_dict_normalized(self) -> None:
        """NaN values within dicts are normalized for cache key consistency."""
        cache = IntegrityCache(strict=False)
        args = {"data": {"a": 1.0, "b": float("nan")}}
        cache.put("msg", args, None, "en", True, "Dict Result", ())
        entry = cache.get("msg", {"data": {"a": 1.0, "b": float("nan")}}, None, "en", True)
        assert entry is not None
        assert entry.formatted == "Dict Result"

    def test_deeply_nested_nan_normalized(self) -> None:
        """NaN values in deeply nested structures are normalized consistently."""
        cache = IntegrityCache(strict=False)
        deep_args: dict[str, FluentValue] = {
            "outer": {
                "inner": [
                    {"value": float("nan")},
                    {"value": Decimal("NaN")},
                ]
            }
        }
        cache.put("msg", deep_args, None, "en", True, "Deep Result", ())
        fresh_args: dict[str, FluentValue] = {
            "outer": {
                "inner": [
                    {"value": float("nan")},
                    {"value": Decimal("NaN")},
                ]
            }
        }
        entry = cache.get("msg", fresh_args, None, "en", True)
        assert entry is not None
        assert entry.formatted == "Deep Result"


class TestNaNSecurityProperties:
    """Test security properties of NaN normalization."""

    def test_nan_cache_pollution_prevented(self) -> None:
        """NaN-based cache pollution attack is prevented by normalization.

        Attack scenario: 100 NaN-containing requests without normalization would
        create 100 unique, unretrievable entries, evicting all legitimate entries.
        With normalization all NaN entries collapse to a single key.
        """
        cache = IntegrityCache(strict=False, maxsize=10)
        for i in range(5):
            cache.put(f"legit{i}", None, None, "en", True, f"Legit {i}", ())
        for i in range(100):
            cache.put("attack", {"val": float("nan")}, None, "en", True, f"Attack {i}", ())

        # 5 legit + 1 attack = 6 entries (attack collapses to 1 due to normalization)
        assert cache.get_stats()["size"] == 6
        for i in range(5):
            entry = cache.get(f"legit{i}", None, None, "en", True)
            assert entry is not None, f"Legitimate entry legit{i} was evicted!"

    @given(st.floats(allow_nan=True))
    @settings(max_examples=100)
    @example(float("nan"))
    @example(float("-nan"))
    @example(float("inf"))
    @example(float("-inf"))
    def test_all_float_special_values_produce_retrievable_keys(self, value: float) -> None:
        """PROPERTY: For any float value, put followed by get returns the entry."""
        cache = IntegrityCache(strict=False)
        args = {"val": value}
        cache.put("msg", args, None, "en", True, f"Value: {value}", ())
        entry = cache.get("msg", args, None, "en", True)
        assert entry is not None, f"Entry for value {value!r} was not retrievable"
        is_nan = math.isnan(value)
        event(f"is_nan={is_nan}")

    @given(st.decimals(allow_nan=True))
    @settings(max_examples=100)
    @example(Decimal("NaN"))
    @example(Decimal("sNaN"))
    @example(Decimal("Inf"))
    @example(Decimal("-Inf"))
    def test_all_decimal_special_values_produce_retrievable_keys(
        self, value: Decimal
    ) -> None:
        """PROPERTY: For any Decimal value, put followed by get returns the entry."""
        cache = IntegrityCache(strict=False)
        args = {"val": value}
        cache.put("msg", args, None, "en", True, f"Value: {value}", ())
        entry = cache.get("msg", args, None, "en", True)
        assert entry is not None, f"Entry for value {value!r} was not retrievable"
        is_nan = value.is_nan() or value.is_snan()
        event(f"is_nan={is_nan}")


class TestNaNHashableValue:
    """Test _make_hashable NaN handling directly."""

    def test_make_hashable_float_nan_returns_canonical(self) -> None:
        """_make_hashable returns canonical ('__float__', '__NaN__') for float NaN."""
        result = IntegrityCache._make_hashable(float("nan"))
        assert result == ("__float__", "__NaN__")

    def test_make_hashable_decimal_nan_returns_canonical(self) -> None:
        """_make_hashable returns canonical ('__decimal__', '__NaN__') for Decimal NaN."""
        result = IntegrityCache._make_hashable(Decimal("NaN"))
        assert result == ("__decimal__", "__NaN__")

    def test_make_hashable_decimal_snan_returns_canonical(self) -> None:
        """_make_hashable returns canonical ('__decimal__', '__NaN__') for Decimal sNaN."""
        result = IntegrityCache._make_hashable(Decimal("sNaN"))
        assert result == ("__decimal__", "__NaN__")

    def test_make_hashable_regular_float_uses_str(self) -> None:
        """_make_hashable returns tagged str for regular floats (non-NaN)."""
        result = IntegrityCache._make_hashable(1.5)
        assert result == ("__float__", "1.5")

    def test_make_hashable_regular_decimal_uses_str(self) -> None:
        """_make_hashable returns tagged str for regular Decimal values."""
        result = IntegrityCache._make_hashable(Decimal("1.50"))
        assert result == ("__decimal__", "1.50")

    def test_make_hashable_infinity_uses_str_not_nan_sentinel(self) -> None:
        """Infinity uses str() representation, not the NaN sentinel.

        Infinity satisfies Inf == Inf (unlike NaN), so no special normalization
        is needed. Both +Inf and -Inf produce distinct, retrievable keys.
        """
        pos_inf = IntegrityCache._make_hashable(float("inf"))
        neg_inf = IntegrityCache._make_hashable(float("-inf"))
        nan_result = IntegrityCache._make_hashable(float("nan"))

        assert pos_inf == ("__float__", "inf")
        assert neg_inf == ("__float__", "-inf")
        assert pos_inf != nan_result
        assert neg_inf != nan_result


# ============================================================================
# SECTION 6: HASHABLE CONVERSION - CACHE ROUNDTRIP TESTS
# ============================================================================


class TestCacheHashableConversion:  # pylint: disable=too-many-public-methods
    """Test IntegrityCache automatic conversion of unhashable args to hashable keys.

    Lists, dicts, sets, and tuples are converted to hashable equivalents
    (type-tagged tuples, sorted tuples, frozensets) enabling caching for these
    types without requiring callers to pre-convert their arguments.
    """

    def test_get_with_list_value_now_cacheable(self) -> None:
        """get() with list args succeeds: lists are converted to type-tagged tuples."""
        cache = IntegrityCache(strict=False, maxsize=100)
        args = {"key": [1, 2, 3]}
        cache.put("msg-id", args, None, "en-US", True, "formatted", ())
        cached = cache.get("msg-id", args, None, "en-US", True)
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    def test_get_with_dict_value_now_cacheable(self) -> None:
        """get() with nested dict args succeeds: dicts are converted to sorted tuples."""
        cache = IntegrityCache(strict=False, maxsize=100)
        args = {"key": {"nested": "value"}}
        cache.put("msg-id", args, None, "en-US", True, "formatted", ())
        cached = cache.get("msg-id", args, None, "en-US", True)
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    def test_get_with_set_value_now_cacheable(self) -> None:
        """get() with set args succeeds: sets are converted to type-tagged frozensets."""
        cache = IntegrityCache(strict=False, maxsize=100)
        args: dict[str, object] = {"key": {1, 2, 3}}
        cache.put("msg-id", args, None, "en-US", True, "formatted", ())  # type: ignore[arg-type]
        cached = cache.get("msg-id", args, None, "en-US", True)  # type: ignore[arg-type]
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    def test_put_with_list_value_now_caches(self) -> None:
        """put() with list args stores entry: lists are converted at key build time."""
        cache = IntegrityCache(strict=False, maxsize=100)
        cache.put("msg-id", {"items": [1, 2, 3]}, None, "en-US", True, "formatted", ())
        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    def test_put_with_dict_value_now_caches(self) -> None:
        """put() with nested dict args stores entry: dicts are converted at key build."""
        cache = IntegrityCache(strict=False, maxsize=100)
        cache.put("msg-id", {"config": {"option": "value"}}, None, "en-US", True, "fmt", ())
        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    def test_make_key_converts_list_to_valid_key(self) -> None:
        """_make_key returns a non-None key when args contain lists."""
        args: dict[str, object] = {"list_value": [1, 2, 3]}
        key = IntegrityCache._make_key(
            "msg-id", args, None, "en-US", True  # type: ignore[arg-type]
        )
        assert key is not None

    def test_make_key_converts_nested_structures_to_valid_key(self) -> None:
        """_make_key returns a non-None key when args contain nested structures."""
        args: dict[str, object] = {"list": [1, 2], "dict": {"nested": "value"}}
        key = IntegrityCache._make_key(
            "msg-id", args, None, "en-US", True  # type: ignore[arg-type]
        )
        assert key is not None

    def test_get_with_tuple_value_cacheable(self) -> None:
        """get() caches tuple-valued args correctly via type-tagged conversion."""
        cache = IntegrityCache(strict=False, maxsize=100)
        args = {"coords": (10, 20, 30)}
        cache.put("msg-id", args, None, "en-US", True, "formatted", ())
        cached = cache.get("msg-id", args, None, "en-US", True)
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    def test_get_with_tuple_containing_list_cacheable(self) -> None:
        """get() caches tuple-with-nested-list args: nested list is converted."""
        cache = IntegrityCache(strict=False, maxsize=100)
        args: dict[str, object] = {"data": (1, [2, 3], 4)}
        cache.put("msg-id", args, None, "en-US", True, "formatted", ())  # type: ignore[arg-type]
        cached = cache.get("msg-id", args, None, "en-US", True)  # type: ignore[arg-type]
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert len(cache) == 1
        assert cache.unhashable_skips == 0

    @given(st.tuples(st.integers(), st.integers(), st.integers()))
    def test_get_with_various_tuples_cacheable(
        self, tuple_value: tuple[int, int, int]
    ) -> None:
        """PROPERTY: Tuple-valued args cache and retrieve correctly."""
        cache = IntegrityCache(strict=False, maxsize=100)
        args = {"tuple_arg": tuple_value}
        cache.put("msg-id", args, None, "en-US", True, "formatted", ())
        cached = cache.get("msg-id", args, None, "en-US", True)
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert cache.unhashable_skips == 0
        event(f"tuple_len={len(tuple_value)}")

    @given(st.lists(st.integers(), min_size=1, max_size=10))
    def test_get_with_various_lists_cacheable(self, list_value: list[int]) -> None:
        """PROPERTY: List-valued args cache and retrieve correctly."""
        cache = IntegrityCache(strict=False, maxsize=100)
        args = {"list_arg": list_value}
        cache.put("msg-id", args, None, "en-US", True, "formatted", ())
        cached = cache.get("msg-id", args, None, "en-US", True)
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert cache.unhashable_skips == 0
        event(f"list_len={len(list_value)}")

    @given(
        st.dictionaries(
            st.text(min_size=1, max_size=10), st.integers(), min_size=1, max_size=5
        )
    )
    def test_put_with_various_dicts_cacheable(self, dict_value: dict[str, int]) -> None:
        """PROPERTY: Dict-valued args cache correctly."""
        cache = IntegrityCache(strict=False, maxsize=100)
        args = {"dict_arg": dict_value}
        cache.put("msg-id", args, None, "en-US", True, "formatted", ())
        assert len(cache) == 1
        assert cache.unhashable_skips == 0
        event(f"dict_len={len(dict_value)}")

    def test_mixed_hashable_and_convertible_args(self) -> None:
        """Cache handles mixed hashable/convertible args in the same call."""
        cache = IntegrityCache(strict=False, maxsize=100)
        args: dict[str, object] = {
            "str_arg": "value",
            "int_arg": 42,
            "list_arg": [1, 2, 3],
        }
        cache.put("msg-id", args, None, "en-US", True, "formatted", ())  # type: ignore[arg-type]
        cached = cache.get("msg-id", args, None, "en-US", True)  # type: ignore[arg-type]
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert cache.unhashable_skips == 0

    def test_empty_list_cacheable(self) -> None:
        """Empty lists are converted and cached correctly."""
        cache = IntegrityCache(strict=False, maxsize=100)
        args: dict[str, list[object]] = {"empty_list": []}
        cache.put("msg-id", args, None, "en-US", True, "formatted", ())  # type: ignore[arg-type]
        cached = cache.get("msg-id", args, None, "en-US", True)  # type: ignore[arg-type]
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert len(cache) == 1

    def test_empty_dict_cacheable(self) -> None:
        """Empty dicts are converted and cached correctly."""
        cache = IntegrityCache(strict=False, maxsize=100)
        args: dict[str, dict[object, object]] = {"empty_dict": {}}
        cache.put("msg-id", args, None, "en-US", True, "formatted", ())  # type: ignore[arg-type]
        cached = cache.get("msg-id", args, None, "en-US", True)  # type: ignore[arg-type]
        assert cached is not None
        assert cached.as_result() == ("formatted", ())
        assert len(cache) == 1


# ============================================================================
# SECTION 7: UNHASHABLE ARGUMENT HANDLING
# ============================================================================


class TestUnhashableHandling:
    """Test graceful bypass for arguments that cannot be hashed.

    Covers three bypass mechanisms:
    1. Unknown type in _make_hashable (case _ branch)
    2. Python's hash() raising TypeError
    3. RecursionError from circular references
    In all cases: entry is not cached, unhashable_skips increments.
    """

    def test_get_with_unknown_type_skips_cache(self) -> None:
        """get() with unknown type arg skips cache and increments unhashable_skips.

        UnknownType is not recognized by _make_hashable's match/case dispatch,
        triggering TypeError("Unknown type in cache key") → _make_key returns None.
        """
        cache = IntegrityCache(strict=False)

        class UnknownType:
            pass

        args: dict[str, object] = {"data": UnknownType()}
        result = cache.get("msg", args, None, "en", True)  # type: ignore[arg-type]
        assert result is None
        assert cache.unhashable_skips == 1
        assert cache.misses == 1
        assert cache.hits == 0

    def test_put_with_unhashable_hash_raises_skips_cache(self) -> None:
        """put() with arg whose __hash__ raises TypeError skips caching."""
        cache = IntegrityCache(strict=False)

        class CustomObject:
            def __hash__(self) -> int:  # pylint: disable=invalid-hash-returned
                msg = "unhashable"
                raise TypeError(msg)

        args: dict[str, object] = {"obj": CustomObject()}
        cache.put("msg", args, None, "en", True, "result", ())  # type: ignore[arg-type]
        assert cache.size == 0
        assert cache.unhashable_skips == 1

    def test_unhashable_custom_object_in_get_skipped(self) -> None:
        """Custom unhashable objects in get() args bypass caching gracefully."""
        cache = IntegrityCache(strict=False, maxsize=100)

        class UnhashableClass:
            def __init__(self) -> None:
                self.data = [1, 2, 3]

            def __hash__(self) -> NoReturn:  # pylint: disable=invalid-hash-returned
                msg = "unhashable type"
                raise TypeError(msg)

        custom_args: dict[str, object] = {"custom": UnhashableClass()}
        result = cache.get("msg-id", custom_args, None, "en-US", True)  # type: ignore[arg-type]
        assert result is None
        assert cache.unhashable_skips == 1

    def test_unhashable_skips_not_incremented_for_convertible_types(self) -> None:
        """unhashable_skips only counts truly unhashable objects; lists/dicts do not."""
        cache = IntegrityCache(strict=False, maxsize=100)
        assert cache.unhashable_skips == 0

        cache.get("msg1", {"list": [1]}, None, "en-US", True)
        assert cache.unhashable_skips == 0  # Lists are convertible, not skipped

        cache.put("msg2", {"dict": {}}, None, "en-US", True, "result", ())
        assert cache.unhashable_skips == 0  # Dicts are convertible, not skipped

    def test_unhashable_skips_resets_on_clear(self) -> None:
        """clear() resets unhashable_skips to 0."""
        cache = IntegrityCache(strict=False, maxsize=100)

        class UnhashableClass:
            def __hash__(self) -> NoReturn:  # pylint: disable=invalid-hash-returned
                msg = "unhashable type"
                raise TypeError(msg)

        cache.get("msg", {"obj": UnhashableClass()}, None, "en-US", True)  # type: ignore[dict-item]
        assert cache.unhashable_skips == 1
        cache.clear()
        assert cache.unhashable_skips == 0

    def test_get_stats_includes_unhashable_skips(self) -> None:
        """get_stats() includes accurate unhashable_skips count."""
        cache = IntegrityCache(strict=False, maxsize=100)

        class UnhashableClass:
            def __hash__(self) -> NoReturn:  # pylint: disable=invalid-hash-returned
                msg = "unhashable type"
                raise TypeError(msg)

        cache.get("msg", {"obj": UnhashableClass()}, None, "en-US", True)  # type: ignore[dict-item]
        stats = cache.get_stats()
        assert "unhashable_skips" in stats
        assert stats["unhashable_skips"] == 1
        assert stats["misses"] == 1

    def test_hashable_args_do_not_increment_unhashable_skips(self) -> None:
        """Fully hashable primitive args never increment unhashable_skips."""
        cache = IntegrityCache(strict=False, maxsize=100)
        args: dict[str, object] = {"str": "value", "int": 42, "float": 3.14}
        cache.get("msg1", args, None, "en-US", True)  # type: ignore[arg-type]
        cache.put("msg2", args, None, "en-US", True, "result", ())  # type: ignore[arg-type]
        assert cache.unhashable_skips == 0

    def test_put_with_circular_reference_increments_skip_counter(self) -> None:
        """Circular reference in args increments unhashable_skips and skips storage."""
        cache = IntegrityCache(strict=False, maxsize=100)
        circular: dict[str, object] = {}
        circular["self"] = circular  # Circular reference
        assert cache.unhashable_skips == 0
        cache.put(
            message_id="test",
            args=circular,  # type: ignore[arg-type]
            attribute=None,
            locale_code="en",
            use_isolating=True,
            formatted="output",
            errors=(),
        )
        assert cache.unhashable_skips == 1
        assert len(cache) == 0

    def test_put_with_nested_circular_reference_increments_skip(self) -> None:
        """Nested circular reference also triggers unhashable_skips increment."""
        cache = IntegrityCache(strict=False, maxsize=50)
        nested: dict[str, object] = {"level1": {}}
        nested["level1"]["back"] = nested  # type: ignore[index]
        initial_skips = cache.unhashable_skips
        cache.put(
            message_id="nested_test",
            args=nested,  # type: ignore[arg-type]
            attribute=None,
            locale_code="lv",
            use_isolating=True,
            formatted="result",
            errors=(),
        )
        assert cache.unhashable_skips == initial_skips + 1
        assert len(cache) == 0

    def test_put_with_custom_unhashable_in_args_dict(self) -> None:
        """Custom unhashable object as a dict value triggers skip."""
        cache = IntegrityCache(strict=False, maxsize=100)

        class UnhashableObject:
            __hash__ = None  # type: ignore[assignment]

        unhashable_args = {"obj": UnhashableObject()}
        initial_skips = cache.unhashable_skips
        cache.put(
            message_id="custom_obj",
            args=unhashable_args,  # type: ignore[arg-type]
            attribute="attr",
            locale_code="en_US",
            use_isolating=True,
            formatted="value",
            errors=(),
        )
        assert cache.unhashable_skips == initial_skips + 1
        assert len(cache) == 0


# ============================================================================
# SECTION 8: ERROR BLOAT PROTECTION
# ============================================================================


class TestIntegrityCacheErrorBloatProtection:
    """Test IntegrityCache error collection memory bounding.

    Prevents unbounded memory use when a single message generates many errors.
    Two limits: max_errors_per_entry (count) and max_entry_weight (bytes).
    """

    def test_put_rejects_excessive_error_count(self) -> None:
        """put() skips caching when error count exceeds max_errors_per_entry."""
        cache = IntegrityCache(strict=False, max_errors_per_entry=10)
        errors = tuple(
            FrozenFluentError(f"Error {i}", ErrorCategory.REFERENCE) for i in range(15)
        )
        cache.put("msg", None, None, "en", True, "formatted text", errors)
        assert cache.size == 0
        assert cache.get_stats()["error_bloat_skips"] == 1
        assert cache.get("msg", None, None, "en", True) is None

    def test_put_rejects_excessive_error_weight(self) -> None:
        """put() skips caching when total weight exceeds max_entry_weight.

        Dynamic weight: base (100) + string len + per-error weights.
        10 errors with 100-char messages + 100-char formatted string exceeds 2000.
        """
        cache = IntegrityCache(strict=False, max_entry_weight=2000, max_errors_per_entry=50)
        errors = tuple(
            FrozenFluentError("E" * 100, ErrorCategory.REFERENCE) for _ in range(10)
        )
        cache.put("msg", None, None, "en", True, "x" * 100, errors)
        assert cache.size == 0
        assert cache.get_stats()["error_bloat_skips"] == 1

    def test_put_accepts_reasonable_error_collections(self) -> None:
        """put() caches results with error counts and weights within limits."""
        cache = IntegrityCache(strict=False, max_entry_weight=15000, max_errors_per_entry=50)
        errors = tuple(
            FrozenFluentError(f"Error {i}", ErrorCategory.REFERENCE) for i in range(10)
        )
        cache.put("msg", None, None, "en", True, "formatted text", errors)
        assert cache.size == 1
        assert cache.get_stats()["error_bloat_skips"] == 0
        cached = cache.get("msg", None, None, "en", True)
        assert cached is not None
        assert cached.as_result() == ("formatted text", errors)


# ============================================================================
# SECTION 9: LRU EVICTION BEHAVIOR
# ============================================================================


class TestIntegrityCacheLRUBehavior:
    """Test IntegrityCache LRU eviction and move-to-end behavior."""

    def test_put_moves_existing_key_to_end_of_lru(self) -> None:
        """put() on existing key marks it as recently used (moves to LRU tail)."""
        cache = IntegrityCache(strict=False, maxsize=3)
        cache.put("msg1", None, None, "en", True, "result1", ())
        cache.put("msg2", None, None, "en", True, "result2", ())
        cache.put("msg3", None, None, "en", True, "result3", ())
        assert cache.size == 3

        # Updating msg1 moves it to the LRU tail (recently used)
        cache.put("msg1", None, None, "en", True, "updated1", ())

        # Adding msg4 should evict msg2 (now the oldest)
        cache.put("msg4", None, None, "en", True, "result4", ())
        assert cache.size == 3

        assert cache.get("msg2", None, None, "en", True) is None
        entry1 = cache.get("msg1", None, None, "en", True)
        assert entry1 is not None
        assert entry1.as_result() == ("updated1", ())
        assert cache.get("msg3", None, None, "en", True) is not None
        assert cache.get("msg4", None, None, "en", True) is not None

    def test_put_evicts_lru_entry_when_cache_full(self) -> None:
        """put() evicts the least recently used entry when capacity is reached."""
        cache = IntegrityCache(strict=False, maxsize=2)
        cache.put("msg1", None, None, "en", True, "result1", ())
        cache.put("msg2", None, None, "en", True, "result2", ())
        assert cache.size == 2

        cache.put("msg3", None, None, "en", True, "result3", ())
        assert cache.size == 2
        assert cache.get("msg1", None, None, "en", True) is None
        assert cache.get("msg2", None, None, "en", True) is not None
        assert cache.get("msg3", None, None, "en", True) is not None


# ============================================================================
# SECTION 10: PROPERTY ACCESSORS
# ============================================================================


class TestIntegrityCacheProperties:
    """Test IntegrityCache property accessors for size, hit/miss counters, and limits."""

    def test_len_and_size_consistent(self) -> None:
        """len(cache) and cache.size return the same current entry count."""
        cache = IntegrityCache(strict=False)
        assert len(cache) == 0
        cache.put("msg1", None, None, "en", True, "result1", ())
        assert len(cache) == 1
        assert cache.size == 1
        cache.put("msg2", None, None, "en", True, "result2", ())
        assert len(cache) == 2
        assert cache.size == 2

    def test_maxsize_property(self) -> None:
        """maxsize property returns the configured maximum size."""
        cache = IntegrityCache(strict=False, maxsize=500)
        assert cache.maxsize == 500

    def test_max_entry_weight_property(self) -> None:
        """max_entry_weight property returns the configured weight limit."""
        cache = IntegrityCache(strict=False, max_entry_weight=5000)
        assert cache.max_entry_weight == 5000

    def test_hits_increments_on_cache_hit(self) -> None:
        """hits property increments each time get() finds an entry."""
        cache = IntegrityCache(strict=False)
        cache.put("msg", None, None, "en", True, "result", ())
        cache.get("msg", None, None, "en", True)
        assert cache.hits == 1
        cache.get("msg", None, None, "en", True)
        assert cache.hits == 2

    def test_misses_increments_on_cache_miss(self) -> None:
        """misses property increments each time get() finds no entry."""
        cache = IntegrityCache(strict=False)
        cache.get("msg1", None, None, "en", True)
        assert cache.misses == 1
        cache.get("msg2", None, None, "en", True)
        assert cache.misses == 2

    def test_unhashable_skips_increments_on_skip(self) -> None:
        """unhashable_skips increments for both get() and put() skips."""
        cache = IntegrityCache(strict=False)

        class UnknownType:
            pass

        get_args: dict[str, object] = {"data": UnknownType()}
        cache.get("msg", get_args, None, "en", True)  # type: ignore[arg-type]
        assert cache.unhashable_skips == 1
        put_args: dict[str, object] = {"data": UnknownType()}
        cache.put("msg", put_args, None, "en", True, "result", ())  # type: ignore[arg-type]
        assert cache.unhashable_skips == 2

    def test_oversize_skips_increments_on_oversize_entry(self) -> None:
        """oversize_skips increments when formatted string exceeds max_entry_weight."""
        cache = IntegrityCache(strict=False, max_entry_weight=10)
        cache.put("msg1", None, None, "en", True, "x" * 100, ())
        assert cache.oversize_skips == 1
        cache.put("msg2", None, None, "en", True, "y" * 50, ())
        assert cache.oversize_skips == 2

    @given(
        st.integers(min_value=1, max_value=1000),
        st.integers(min_value=1, max_value=10000),
        st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=50)
    def test_property_constructor_parameters_stored_correctly(
        self,
        maxsize: int,
        max_entry_weight: int,
        max_errors_per_entry: int,
    ) -> None:
        """PROPERTY: Constructor parameters are stored and reflected by properties."""
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
    def test_property_primitive_args_always_cacheable(self, text: str) -> None:
        """PROPERTY: All primitive FluentValue types produce valid, retrievable entries."""
        cache = IntegrityCache(strict=False)

        for args in [
            {"text": text},
            {"num": 42},
            {"float": 3.14},
            {"flag": True},
            {"val": None},
        ]:
            cache.put("msg", args, None, "en", True, "result", ())  # type: ignore[arg-type]
            entry = cache.get("msg", args, None, "en", True)  # type: ignore[arg-type]
            assert entry is not None
            assert entry.as_result() == ("result", ())

        event(f"text_len={len(text)}")
