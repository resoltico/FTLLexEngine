# mypy: ignore-errors
"""Split test cases from tests/test_runtime_cache_hashable.py."""

from tests.runtime_cache_hashable_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# SECTION 5: NaN NORMALIZATION
# ============================================================================


class TestNaNDecimalNormalization:
    """Test that Decimal NaN values are normalized in cache keys."""

    def test_decimal_nan_cache_key_consistency(self) -> None:
        """Decimal NaN produces consistent cache key across independent instances."""
        cache = IntegrityCache()
        cache.put("msg", {"val": Decimal("NaN")}, None, "en", use_isolating=True, formatted="Decimal Result", errors=())
        entry = cache.get("msg", {"val": Decimal("NaN")}, None, "en", use_isolating=True)
        assert entry is not None
        assert entry.formatted == "Decimal Result"

    def test_decimal_nan_does_not_pollute_cache(self) -> None:
        """Multiple puts with Decimal NaN update the same entry."""
        cache = IntegrityCache(maxsize=100)
        for i in range(10):
            cache.put("msg", {"val": Decimal("NaN")}, None, "en", use_isolating=True, formatted=f"Value {i}", errors=())
        stats = cache.get_stats()
        assert stats["size"] == 1, (
            f"Expected 1 entry but got {stats['size']}. "
            "Decimal NaN normalization may not be working."
        )

    def test_decimal_snan_normalized_same_as_qnan(self) -> None:
        """Signaling NaN and quiet NaN both normalize to the same canonical key."""
        cache = IntegrityCache()
        cache.put("msg", {"val": Decimal("NaN")}, None, "en", use_isolating=True, formatted="QNaN", errors=())
        # sNaN should resolve to same cache key as qNaN
        entry = cache.get("msg", {"val": Decimal("sNaN")}, None, "en", use_isolating=True)
        assert entry is not None

    def test_decimal_nan_different_from_regular_decimal(self) -> None:
        """Decimal NaN has different cache key from regular Decimal values."""
        cache = IntegrityCache()
        cache.put("msg", {"val": Decimal("NaN")}, None, "en", use_isolating=True, formatted="NaN Result", errors=())
        cache.put("msg", {"val": Decimal("1.0")}, None, "en", use_isolating=True, formatted="Regular Result", errors=())

        nan_entry = cache.get("msg", {"val": Decimal("NaN")}, None, "en", use_isolating=True)
        regular_entry = cache.get("msg", {"val": Decimal("1.0")}, None, "en", use_isolating=True)

        assert nan_entry is not None
        assert nan_entry.formatted == "NaN Result"
        assert regular_entry is not None
        assert regular_entry.formatted == "Regular Result"
        assert cache.get_stats()["size"] == 2


class TestNaNInNestedStructures:
    """Test NaN normalization in nested data structures."""

    def test_nan_in_list_normalized(self) -> None:
        """NaN values within lists are normalized for cache key consistency."""
        cache = IntegrityCache()
        items = [Decimal(1), Decimal("NaN"), Decimal(3)]
        cache.put("msg", {"items": items}, None, "en", use_isolating=True, formatted="List Result", errors=())
        entry = cache.get("msg", {"items": items}, None, "en", use_isolating=True)
        assert entry is not None
        assert entry.formatted == "List Result"

    def test_nan_in_dict_normalized(self) -> None:
        """NaN values within dicts are normalized for cache key consistency."""
        cache = IntegrityCache()
        args: dict[str, FluentValue] = {"data": {"a": Decimal(1), "b": Decimal("NaN")}}
        cache.put("msg", args, None, "en", use_isolating=True, formatted="Dict Result", errors=())
        data = {"a": Decimal(1), "b": Decimal("NaN")}
        entry = cache.get("msg", {"data": data}, None, "en", use_isolating=True)
        assert entry is not None
        assert entry.formatted == "Dict Result"

    def test_deeply_nested_nan_normalized(self) -> None:
        """NaN values in deeply nested structures are normalized consistently."""
        cache = IntegrityCache()
        deep_args: dict[str, FluentValue] = {
            "outer": {
                "inner": [
                    {"value": Decimal("NaN")},
                    {"value": Decimal("sNaN")},
                ]
            }
        }
        cache.put("msg", deep_args, None, "en", use_isolating=True, formatted="Deep Result", errors=())
        fresh_args: dict[str, FluentValue] = {
            "outer": {
                "inner": [
                    {"value": Decimal("NaN")},
                    {"value": Decimal("sNaN")},
                ]
            }
        }
        entry = cache.get("msg", fresh_args, None, "en", use_isolating=True)
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
        cache = IntegrityCache(maxsize=10)
        for i in range(5):
            cache.put(f"legit{i}", None, None, "en", use_isolating=True, formatted=f"Legit {i}", errors=())
        for i in range(100):
            cache.put("attack", {"val": Decimal("NaN")}, None, "en", use_isolating=True, formatted=f"Attack {i}", errors=())

        # 5 legit + 1 attack = 6 entries (attack collapses to 1 due to normalization)
        assert cache.get_stats()["size"] == 6
        for i in range(5):
            entry = cache.get(f"legit{i}", None, None, "en", use_isolating=True)
            assert entry is not None, f"Legitimate entry legit{i} was evicted!"

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
        cache = IntegrityCache()
        args = {"val": value}
        cache.put("msg", args, None, "en", use_isolating=True, formatted=f"Value: {value}", errors=())
        entry = cache.get("msg", args, None, "en", use_isolating=True)
        assert entry is not None, f"Entry for value {value!r} was not retrievable"
        is_nan = value.is_nan() or value.is_snan()
        event(f"is_nan={is_nan}")


class TestNaNHashableValue:
    """Test _make_hashable NaN handling directly."""

    def test_make_hashable_decimal_nan_returns_canonical(self) -> None:
        """_make_hashable returns canonical ('__decimal__', '__NaN__') for Decimal NaN."""
        result = IntegrityCache._make_hashable(Decimal("NaN"))
        assert result == ("__decimal__", "__NaN__")

    def test_make_hashable_decimal_snan_returns_canonical(self) -> None:
        """_make_hashable returns canonical ('__decimal__', '__NaN__') for Decimal sNaN."""
        result = IntegrityCache._make_hashable(Decimal("sNaN"))
        assert result == ("__decimal__", "__NaN__")

    def test_make_hashable_regular_decimal_uses_str(self) -> None:
        """_make_hashable returns tagged str for regular Decimal values."""
        result = IntegrityCache._make_hashable(Decimal("1.50"))
        assert result == ("__decimal__", "1.50")

    def test_make_hashable_decimal_infinity_uses_str_not_nan_sentinel(self) -> None:
        """Decimal Infinity uses str() representation, not the NaN sentinel.

        Infinity satisfies Inf == Inf (unlike NaN), so no special normalization
        is needed. Both +Inf and -Inf produce distinct, retrievable keys.
        """
        pos_inf = IntegrityCache._make_hashable(Decimal("Inf"))
        neg_inf = IntegrityCache._make_hashable(Decimal("-Inf"))
        nan_result = IntegrityCache._make_hashable(Decimal("NaN"))

        assert pos_inf == ("__decimal__", "Infinity")
        assert neg_inf == ("__decimal__", "-Infinity")
        assert pos_inf != nan_result
        assert neg_inf != nan_result
