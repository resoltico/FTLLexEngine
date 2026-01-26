"""Tests for NaN cache key normalization.

Validates that NaN values are normalized to prevent cache pollution.

Security Context:
    NaN (Not a Number) values violate Python's equality contract:
    float("nan") != float("nan") due to IEEE 754 semantics.

    Without normalization:
    - Cache keys containing NaN are unretrievable
    - Each put() with NaN creates a NEW entry (keys never match)
    - Attacker can fill cache with junk entries, evicting valid ones
    - This constitutes a DoS vector via cache thrashing

    With normalization:
    - NaN values are canonicalized to "__NaN__" string
    - Cache keys containing NaN are retrievable
    - Multiple puts with NaN update the SAME entry
    - Cache pollution prevented
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import example, given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.runtime.function_bridge import FluentValue


class TestNaNFloatNormalization:
    """Test that float NaN values are normalized in cache keys."""

    def test_float_nan_cache_key_consistency(self) -> None:
        """Float NaN produces consistent cache key across calls.

        float("nan") != float("nan") in Python, but _make_hashable
        must normalize to a canonical representation for cache consistency.
        """
        cache = IntegrityCache(strict=False)

        # Create NaN-containing args
        args_with_nan = {"val": float("nan")}

        # Put entry with NaN arg
        cache.put("msg", args_with_nan, None, "en", True, "Result", ())

        # Get should find the entry (NaN normalized to same key)
        entry = cache.get("msg", {"val": float("nan")}, None, "en", True)
        assert entry is not None
        assert entry.formatted == "Result"

    def test_float_nan_does_not_pollute_cache(self) -> None:
        """Multiple puts with float NaN update same entry, not create new ones.

        Without NaN normalization, each put creates a new entry because
        the keys never match (nan != nan). This would cause cache pollution.
        """
        cache = IntegrityCache(strict=False, maxsize=100)

        # Put multiple times with NaN - should all be the same cache key
        for i in range(10):
            cache.put("msg", {"val": float("nan")}, None, "en", True, f"Value {i}", ())

        # Cache should have only ONE entry, not 10
        stats = cache.get_stats()
        assert stats["size"] == 1, (
            f"Expected 1 entry but got {stats['size']}. "
            "NaN normalization may not be working - cache pollution detected."
        )

    def test_float_nan_different_from_regular_float(self) -> None:
        """Float NaN has different cache key from regular floats."""
        cache = IntegrityCache(strict=False)

        # Put with NaN
        cache.put("msg", {"val": float("nan")}, None, "en", True, "NaN Result", ())

        # Put with regular float - should be separate entry
        cache.put("msg", {"val": 1.0}, None, "en", True, "Float Result", ())

        # Both should be retrievable
        nan_entry = cache.get("msg", {"val": float("nan")}, None, "en", True)
        float_entry = cache.get("msg", {"val": 1.0}, None, "en", True)

        assert nan_entry is not None
        assert nan_entry.formatted == "NaN Result"
        assert float_entry is not None
        assert float_entry.formatted == "Float Result"

        # Cache should have exactly 2 entries
        stats = cache.get_stats()
        assert stats["size"] == 2


class TestNaNDecimalNormalization:
    """Test that Decimal NaN values are normalized in cache keys."""

    def test_decimal_nan_cache_key_consistency(self) -> None:
        """Decimal NaN produces consistent cache key across calls.

        Decimal("NaN") has the same equality issue as float NaN.
        """
        cache = IntegrityCache(strict=False)

        # Create NaN-containing args with Decimal
        args_with_nan = {"val": Decimal("NaN")}

        # Put entry with NaN arg
        cache.put("msg", args_with_nan, None, "en", True, "Decimal Result", ())

        # Get should find the entry
        entry = cache.get("msg", {"val": Decimal("NaN")}, None, "en", True)
        assert entry is not None
        assert entry.formatted == "Decimal Result"

    def test_decimal_nan_does_not_pollute_cache(self) -> None:
        """Multiple puts with Decimal NaN update same entry."""
        cache = IntegrityCache(strict=False, maxsize=100)

        for i in range(10):
            cache.put("msg", {"val": Decimal("NaN")}, None, "en", True, f"Value {i}", ())

        stats = cache.get_stats()
        assert stats["size"] == 1, (
            f"Expected 1 entry but got {stats['size']}. "
            "Decimal NaN normalization may not be working."
        )

    def test_decimal_snan_normalized_same_as_qnan(self) -> None:
        """Both signaling NaN and quiet NaN are normalized consistently.

        Decimal supports both sNaN (signaling) and qNaN (quiet).
        Both should produce the same cache key for simplicity.
        """
        cache = IntegrityCache(strict=False)

        # Quiet NaN (default)
        cache.put("msg", {"val": Decimal("NaN")}, None, "en", True, "QNaN", ())

        # Signaling NaN - should resolve to same cache key
        entry = cache.get("msg", {"val": Decimal("sNaN")}, None, "en", True)

        # Note: Both should work the same way since both are normalized
        # The entry should exist (from qNaN put)
        assert entry is not None

    def test_decimal_nan_different_from_regular_decimal(self) -> None:
        """Decimal NaN has different cache key from regular Decimals."""
        cache = IntegrityCache(strict=False)

        cache.put("msg", {"val": Decimal("NaN")}, None, "en", True, "NaN Result", ())
        cache.put("msg", {"val": Decimal("1.0")}, None, "en", True, "Regular Result", ())

        nan_entry = cache.get("msg", {"val": Decimal("NaN")}, None, "en", True)
        regular_entry = cache.get("msg", {"val": Decimal("1.0")}, None, "en", True)

        assert nan_entry is not None
        assert nan_entry.formatted == "NaN Result"
        assert regular_entry is not None
        assert regular_entry.formatted == "Regular Result"

        stats = cache.get_stats()
        assert stats["size"] == 2


class TestNaNMixedTypes:
    """Test NaN handling with mixed float and Decimal types."""

    def test_float_nan_and_decimal_nan_are_separate_keys(self) -> None:
        """Float NaN and Decimal NaN produce different cache keys.

        Even though both are "NaN", they're different types and should
        be cached separately (type-tagging ensures this).
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

        # Should be 2 separate entries
        stats = cache.get_stats()
        assert stats["size"] == 2


class TestNaNInNestedStructures:
    """Test NaN normalization in nested data structures."""

    def test_nan_in_list_normalized(self) -> None:
        """NaN values within lists are normalized."""
        cache = IntegrityCache(strict=False)

        # List containing NaN
        args_with_nan_list = {"items": [1.0, float("nan"), 3.0]}

        cache.put("msg", args_with_nan_list, None, "en", True, "List Result", ())

        # Should be retrievable with fresh NaN instance
        entry = cache.get("msg", {"items": [1.0, float("nan"), 3.0]}, None, "en", True)
        assert entry is not None
        assert entry.formatted == "List Result"

    def test_nan_in_dict_normalized(self) -> None:
        """NaN values within dicts are normalized."""
        cache = IntegrityCache(strict=False)

        # Dict containing NaN
        args_with_nan_dict = {"data": {"a": 1.0, "b": float("nan")}}

        cache.put("msg", args_with_nan_dict, None, "en", True, "Dict Result", ())

        entry = cache.get("msg", {"data": {"a": 1.0, "b": float("nan")}}, None, "en", True)
        assert entry is not None
        assert entry.formatted == "Dict Result"

    def test_deeply_nested_nan_normalized(self) -> None:
        """NaN values in deeply nested structures are normalized."""
        cache = IntegrityCache(strict=False)

        # Deeply nested structure - type annotation for static analysis
        deep_args: dict[str, FluentValue] = {
            "outer": {
                "inner": [
                    {"value": float("nan")},
                    {"value": Decimal("NaN")},
                ]
            }
        }

        cache.put("msg", deep_args, None, "en", True, "Deep Result", ())

        # Fresh nested structure with new NaN instances
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
        """Verify that NaN-based cache pollution attack is prevented.

        Attack scenario:
        1. Attacker sends many requests with NaN values
        2. Without normalization, each creates new unretrievable entry
        3. Cache fills with junk, evicting valid entries
        4. Legitimate cache misses increase (DoS via cache thrashing)

        With normalization, all NaN entries collapse to single key.
        """
        cache = IntegrityCache(strict=False, maxsize=10)

        # First, populate cache with legitimate entries
        for i in range(5):
            cache.put(f"legit{i}", None, None, "en", True, f"Legit {i}", ())

        # Attacker attempts pollution with 100 NaN-containing requests
        for i in range(100):
            cache.put("attack", {"val": float("nan")}, None, "en", True, f"Attack {i}", ())

        # All legitimate entries should still be cached (not evicted)
        # The 100 "attack" entries should collapse to 1 entry
        stats = cache.get_stats()

        # Cache should have: 5 legit + 1 attack = 6 entries, not 10+ (evictions)
        assert stats["size"] == 6

        # Verify legitimate entries are retrievable
        for i in range(5):
            entry = cache.get(f"legit{i}", None, None, "en", True)
            assert entry is not None, f"Legitimate entry legit{i} was evicted!"

    @given(st.floats(allow_nan=True))
    @settings(max_examples=100)
    @example(float("nan"))
    @example(float("-nan"))
    @example(float("inf"))
    @example(float("-inf"))
    def test_all_float_special_values_handled(self, value: float) -> None:
        """All float special values (NaN, Inf) produce retrievable cache keys.

        PROPERTY: For any float value, put followed by get returns the entry.
        """
        cache = IntegrityCache(strict=False)
        args = {"val": value}

        cache.put("msg", args, None, "en", True, f"Value: {value}", ())
        entry = cache.get("msg", args, None, "en", True)

        assert entry is not None, f"Entry for value {value!r} was not retrievable"

    @given(st.decimals(allow_nan=True))
    @settings(max_examples=100)
    @example(Decimal("NaN"))
    @example(Decimal("sNaN"))
    @example(Decimal("Inf"))
    @example(Decimal("-Inf"))
    def test_all_decimal_special_values_handled(self, value: Decimal) -> None:
        """All Decimal special values produce retrievable cache keys.

        PROPERTY: For any Decimal value, put followed by get returns the entry.
        """
        cache = IntegrityCache(strict=False)
        args = {"val": value}

        cache.put("msg", args, None, "en", True, f"Value: {value}", ())
        entry = cache.get("msg", args, None, "en", True)

        assert entry is not None, f"Entry for value {value!r} was not retrievable"


class TestNaNHashableValue:
    """Test _make_hashable NaN handling directly."""

    def test_make_hashable_float_nan_returns_canonical(self) -> None:
        """_make_hashable returns canonical representation for float NaN."""
        result = IntegrityCache._make_hashable(float("nan"))
        assert result == ("__float__", "__NaN__")

    def test_make_hashable_decimal_nan_returns_canonical(self) -> None:
        """_make_hashable returns canonical representation for Decimal NaN."""
        result = IntegrityCache._make_hashable(Decimal("NaN"))
        assert result == ("__decimal__", "__NaN__")

    def test_make_hashable_decimal_snan_returns_canonical(self) -> None:
        """_make_hashable returns canonical representation for Decimal sNaN."""
        result = IntegrityCache._make_hashable(Decimal("sNaN"))
        assert result == ("__decimal__", "__NaN__")

    def test_make_hashable_regular_float_unchanged(self) -> None:
        """_make_hashable returns tagged str for regular floats."""
        result = IntegrityCache._make_hashable(1.5)
        assert result == ("__float__", "1.5")

    def test_make_hashable_regular_decimal_unchanged(self) -> None:
        """_make_hashable returns tagged str for regular Decimals."""
        result = IntegrityCache._make_hashable(Decimal("1.50"))
        assert result == ("__decimal__", "1.50")

    def test_make_hashable_infinity_not_normalized(self) -> None:
        """Infinity is NOT normalized (unlike NaN, Inf == Inf is True)."""
        pos_inf = IntegrityCache._make_hashable(float("inf"))
        neg_inf = IntegrityCache._make_hashable(float("-inf"))

        # Infinity uses str() representation
        assert pos_inf == ("__float__", "inf")
        assert neg_inf == ("__float__", "-inf")

        # Verify they're distinct from NaN
        nan_result = IntegrityCache._make_hashable(float("nan"))
        assert pos_inf != nan_result
        assert neg_inf != nan_result
