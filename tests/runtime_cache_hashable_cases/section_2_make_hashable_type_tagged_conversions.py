# mypy: ignore-errors
"""Split test cases from tests/test_runtime_cache_hashable.py."""

from tests.runtime_cache_hashable_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# SECTION 2: MAKE HASHABLE - TYPE-TAGGED CONVERSIONS
# ============================================================================


class TestMakeHashableTypes:
    """Test IntegrityCache._make_hashable type-tagged conversions.

    Python's hash equality (hash(1) == hash(True)) would cause cache collisions.
    Type-tagging ensures distinct cache keys per type.
    """

    def test_make_hashable_primitives(self) -> None:
        """_make_hashable type-tags bool/int to prevent hash collisions.

        str and None are not tagged (no collision risk).
        bool/int are type-tagged so hash(1) == hash(True) does not cause
        cache key collisions.
        """
        assert IntegrityCache._make_hashable("text") == "text"
        assert IntegrityCache._make_hashable(None) is None
        assert IntegrityCache._make_hashable(42) == ("__int__", 42)
        assert IntegrityCache._make_hashable(True) == ("__bool__", True)
        assert IntegrityCache._make_hashable(False) == ("__bool__", False)

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
        dt = datetime(2024, 1, 1, 12, 0, 0)
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
