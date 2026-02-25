"""Tests for FluentValue collection type support.

Validates that FluentValue type alias correctly includes Sequence and Mapping types,
allowing list and dict arguments to pass static type checking while being handled
correctly at runtime.

Type System Context:
    The FluentValue type alias is the canonical type for values that can be:
    - Passed as arguments to format_pattern()
    - Used in custom function parameters
    - Cached in IntegrityCache keys

    Python 3.13+ recursive type aliases (PEP 695) enable:
    type FluentValue = ... | Sequence["FluentValue"] | Mapping[str, "FluentValue"]

    This allows arbitrarily nested structures like:
    {"items": [1, 2, {"nested": "value"}]}
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle
from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.runtime.function_bridge import FluentNumber, FluentValue


class TestFluentValueTypeAnnotation:
    """Test that FluentValue type annotation accepts collections."""

    def test_list_is_valid_fluentvalue(self) -> None:
        """List[FluentValue] is accepted by type system.

        This test verifies static type checking (via TYPE_CHECKING guard).
        At runtime, the annotation is evaluated but not enforced.
        """
        # This should pass type checking (mypy/pyright)
        items: FluentValue = [1, 2, 3]
        assert items == [1, 2, 3]

    def test_dict_is_valid_fluentvalue(self) -> None:
        """Mapping[str, FluentValue] is accepted by type system."""
        data: FluentValue = {"key": "value", "number": 42}
        assert data == {"key": "value", "number": 42}

    def test_nested_list_is_valid_fluentvalue(self) -> None:
        """Nested lists are valid FluentValue (recursive type)."""
        nested: FluentValue = [[1, 2], [3, 4], [[5, 6]]]
        assert nested == [[1, 2], [3, 4], [[5, 6]]]

    def test_nested_dict_is_valid_fluentvalue(self) -> None:
        """Nested dicts are valid FluentValue (recursive type)."""
        nested: FluentValue = {
            "outer": {
                "inner": {
                    "deep": "value"
                }
            }
        }
        # FluentValue is a union type; narrow to Mapping for nested access
        assert isinstance(nested, dict)
        outer = nested["outer"]
        assert isinstance(outer, dict)
        inner = outer["inner"]
        assert isinstance(inner, dict)
        assert inner["deep"] == "value"

    def test_mixed_nested_structure_is_valid_fluentvalue(self) -> None:
        """Mixed lists and dicts are valid FluentValue."""
        mixed: FluentValue = {
            "items": [1, 2, 3],
            "data": {"a": 1, "b": [4, 5, 6]},
            "nested": [{"x": 1}, {"y": 2}],
        }
        assert isinstance(mixed, dict)

    def test_all_primitive_types_still_valid(self) -> None:
        """Primitive FluentValue types remain valid after collection addition."""
        # All original types should still work
        str_val: FluentValue = "hello"
        int_val: FluentValue = 42
        bool_val: FluentValue = True
        decimal_val: FluentValue = Decimal("1.50")
        decimal_pi: FluentValue = Decimal("3.14")
        datetime_val: FluentValue = datetime.now(tz=UTC)
        date_val: FluentValue = datetime.now(tz=UTC).date()
        none_val: FluentValue = None
        fn_val: FluentValue = FluentNumber(1, "1.00", precision=2)

        # All should be accepted
        assert str_val == "hello"
        assert int_val == 42
        assert bool_val is True
        assert decimal_val == Decimal("1.50")
        assert decimal_pi == Decimal("3.14")
        assert isinstance(datetime_val, datetime)
        assert isinstance(date_val, date)
        assert none_val is None
        assert isinstance(fn_val, FluentNumber)


class TestFluentValueCollectionsRuntime:
    """Test runtime handling of FluentValue collections."""

    def test_bundle_accepts_list_argument(self) -> None:
        """FluentBundle.format_pattern accepts list arguments."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("msg = Items: { $items }")

        # List argument should work at runtime
        result, errors = bundle.format_pattern("msg", {"items": [1, 2, 3]})

        # Collections produce type-name placeholders (not str() expansion)
        # to prevent exponential expansion of deeply nested/shared structures
        assert "[list]" in result
        assert errors == ()

    def test_bundle_accepts_dict_argument(self) -> None:
        """FluentBundle.format_pattern accepts dict arguments."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("msg = Data: { $data }")

        result, errors = bundle.format_pattern("msg", {"data": {"key": "value"}})

        # Collections produce type-name placeholders (not str() expansion)
        assert "[dict]" in result
        assert errors == ()

    def test_bundle_accepts_nested_collections(self) -> None:
        """FluentBundle.format_pattern accepts nested collections."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("msg = Nested: { $nested }")

        nested_data: FluentValue = {
            "items": [1, 2, 3],
            "metadata": {"count": 3},
        }

        _, errors = bundle.format_pattern("msg", {"nested": nested_data})
        assert errors == ()


class TestFluentValueCollectionsCache:
    """Test IntegrityCache handling of FluentValue collections."""

    def test_cache_handles_list_args(self) -> None:
        """IntegrityCache correctly handles list arguments."""
        cache = IntegrityCache(strict=False)

        args = {"items": [1, 2, 3]}
        cache.put("msg", args, None, "en", True, "List Result", ())

        entry = cache.get("msg", args, None, "en", True)
        assert entry is not None
        assert entry.formatted == "List Result"

    def test_cache_handles_dict_args(self) -> None:
        """IntegrityCache correctly handles dict arguments."""
        cache = IntegrityCache(strict=False)

        args = {"data": {"key": "value"}}
        cache.put("msg", args, None, "en", True, "Dict Result", ())

        entry = cache.get("msg", args, None, "en", True)
        assert entry is not None
        assert entry.formatted == "Dict Result"

    def test_cache_handles_nested_mixed_args(self) -> None:
        """IntegrityCache correctly handles nested mixed arguments."""
        cache = IntegrityCache(strict=False)

        # Type annotation for complex nested structure
        args: dict[str, FluentValue] = {
            "outer": {
                "list": [1, 2, 3],
                "nested": {"a": "b"},
            }
        }
        cache.put("msg", args, None, "en", True, "Nested Result", ())

        entry = cache.get("msg", args, None, "en", True)
        assert entry is not None
        assert entry.formatted == "Nested Result"

    def test_cache_distinguishes_list_from_tuple(self) -> None:
        """IntegrityCache correctly distinguishes list from tuple.

        [1, 2, 3] and (1, 2, 3) should be different cache keys.
        """
        cache = IntegrityCache(strict=False)

        cache.put("msg", {"items": [1, 2, 3]}, None, "en", True, "List", ())
        cache.put("msg", {"items": (1, 2, 3)}, None, "en", True, "Tuple", ())

        list_entry = cache.get("msg", {"items": [1, 2, 3]}, None, "en", True)
        tuple_entry = cache.get("msg", {"items": (1, 2, 3)}, None, "en", True)

        assert list_entry is not None
        assert list_entry.formatted == "List"
        assert tuple_entry is not None
        assert tuple_entry.formatted == "Tuple"

    def test_cache_handles_empty_collections(self) -> None:
        """IntegrityCache handles empty collections correctly."""
        cache = IntegrityCache(strict=False)

        cache.put("msg", {"list": [], "dict": {}}, None, "en", True, "Empty", ())

        entry = cache.get("msg", {"list": [], "dict": {}}, None, "en", True)
        assert entry is not None
        assert entry.formatted == "Empty"


class TestFluentValueMakeHashable:
    """Test _make_hashable handling of FluentValue collections."""

    def test_make_hashable_list(self) -> None:
        """_make_hashable converts list to tagged tuple."""
        result = IntegrityCache._make_hashable([1, 2, 3])

        # Return type is complex union - use isinstance checks for type narrowing
        assert isinstance(result, tuple)
        assert result[0] == "__list__"
        assert isinstance(result[1], tuple)
        # Elements are also type-tagged
        assert result[1] == (("__int__", 1), ("__int__", 2), ("__int__", 3))

    def test_make_hashable_tuple(self) -> None:
        """_make_hashable converts tuple to tagged tuple."""
        result = IntegrityCache._make_hashable((1, 2, 3))

        assert isinstance(result, tuple)
        assert result[0] == "__tuple__"
        assert isinstance(result[1], tuple)
        assert result[1] == (("__int__", 1), ("__int__", 2), ("__int__", 3))

    def test_make_hashable_dict(self) -> None:
        """_make_hashable type-tags dict and converts to sorted tuple of pairs."""
        result = IntegrityCache._make_hashable({"b": 2, "a": 1})

        # Dict is type-tagged with "__dict__" prefix
        assert isinstance(result, tuple)
        assert result[0] == "__dict__"
        inner = result[1]
        assert isinstance(inner, tuple)
        # Sorted by key
        assert inner == (("a", ("__int__", 1)), ("b", ("__int__", 2)))

    def test_make_hashable_nested_list_in_dict(self) -> None:
        """_make_hashable handles nested list inside dict."""
        result = IntegrityCache._make_hashable({"items": [1, 2]})

        # Dict is type-tagged with "__dict__" prefix
        assert isinstance(result, tuple)
        assert result[0] == "__dict__"
        inner = result[1]
        assert isinstance(inner, tuple)
        # items key maps to list - complex nested type access
        first = inner[0]
        assert isinstance(first, tuple)
        assert first[0] == "items"
        assert isinstance(first[1], tuple)
        assert first[1][0] == "__list__"

    def test_make_hashable_set(self) -> None:
        """_make_hashable type-tags set and converts to frozenset."""
        result = IntegrityCache._make_hashable({1, 2, 3})

        # Set is type-tagged with "__set__" prefix
        assert isinstance(result, tuple)
        assert result[0] == "__set__"
        inner = result[1]
        assert isinstance(inner, frozenset)


class TestFluentValueCollectionsHypothesis:
    """Property-based tests for FluentValue collection handling."""

    @given(st.lists(st.integers(), max_size=10))
    @settings(max_examples=50)
    def test_integer_lists_are_cacheable(self, items: list[int]) -> None:
        """PROPERTY: Any integer list can be cached and retrieved."""
        event(f"size={len(items)}")
        cache = IntegrityCache(strict=False)
        args = {"items": items}

        cache.put("msg", args, None, "en", True, f"List: {items}", ())
        entry = cache.get("msg", args, None, "en", True)

        assert entry is not None

    @given(st.dictionaries(st.text(min_size=1, max_size=10), st.integers(), max_size=5))
    @settings(max_examples=50)
    def test_string_int_dicts_are_cacheable(self, data: dict[str, int]) -> None:
        """PROPERTY: Any str->int dict can be cached and retrieved."""
        event(f"size={len(data)}")
        cache = IntegrityCache(strict=False)
        args = {"data": data}

        cache.put("msg", args, None, "en", True, f"Dict: {data}", ())
        entry = cache.get("msg", args, None, "en", True)

        assert entry is not None

    @given(
        st.recursive(
            st.one_of(st.integers(), st.text(max_size=10), st.none()),
            lambda children: st.one_of(
                st.lists(children, max_size=3),
                st.dictionaries(st.text(min_size=1, max_size=5), children, max_size=3),
            ),
            max_leaves=10,
        )
    )
    @settings(max_examples=50)
    def test_nested_structures_are_cacheable(self, structure: object) -> None:
        """PROPERTY: Arbitrarily nested structures can be cached and retrieved."""
        is_collection = isinstance(structure, (list, dict))
        event(f"valid={is_collection}")
        cache = IntegrityCache(strict=False)
        # Hypothesis generates complex nested structures; type cast for static analysis
        args: dict[str, FluentValue] = {"nested": structure}  # type: ignore[dict-item]

        try:
            cache.put("msg", args, None, "en", True, "Nested", ())
            entry = cache.get("msg", args, None, "en", True)
            # If put succeeded, get should succeed
            assert entry is not None
        except TypeError:
            # Some structures may exceed depth limit - that's OK
            pass


class TestFluentValueTypeDictAnnotation:
    """Test that dict[str, FluentValue] annotation works correctly."""

    def test_dict_annotation_accepts_collections(self) -> None:
        """dict[str, FluentValue] accepts collection values."""
        # This pattern is common in format_pattern() calls
        args: dict[str, FluentValue] = {
            "name": "Alice",
            "count": 42,
            "items": [1, 2, 3],
            "metadata": {"key": "value"},
        }

        assert args["name"] == "Alice"
        assert args["count"] == 42
        assert args["items"] == [1, 2, 3]
        assert args["metadata"] == {"key": "value"}

    def test_bundle_format_with_typed_args(self) -> None:
        """FluentBundle.format_pattern works with typed args dict."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("msg = Hello { $name }!")

        # Explicitly typed args dict
        args: dict[str, FluentValue] = {"name": "World"}
        result, errors = bundle.format_pattern("msg", args)

        assert result == "Hello World!"
        assert errors == ()


# ============================================================================
# FluentNumber.__post_init__ invariant enforcement
# ============================================================================


class TestFluentNumberValidation:
    """Tests for FluentNumber construction invariants."""

    # --- Unit tests (exact, regression-anchored) ---

    def test_bool_true_raises_type_error(self) -> None:
        """True is bool; NUMBER(True) would silently yield "1" instead of a
        locale-formatted number — reject early with a clear message."""
        with pytest.raises(TypeError, match="not bool"):
            FluentNumber(True, "1", precision=0)

    def test_bool_false_raises_type_error(self) -> None:
        """False is bool; same misuse vector as True."""
        with pytest.raises(TypeError, match="not bool"):
            FluentNumber(False, "0", precision=0)

    def test_negative_precision_raises_value_error(self) -> None:
        """CLDR v operand counts visible fraction digits — always non-negative."""
        with pytest.raises(ValueError, match="precision must be >= 0"):
            FluentNumber(1, "1", precision=-1)

    def test_large_negative_precision_raises_value_error(self) -> None:
        """Highly negative precision is also rejected."""
        with pytest.raises(ValueError, match="precision must be >= 0"):
            FluentNumber(1, "1", precision=-1_000_000)

    def test_valid_int_zero_precision(self) -> None:
        """int value with precision=0 constructs without error."""
        fn = FluentNumber(42, "42", precision=0)
        assert fn.value == 42
        assert fn.precision == 0

    def test_valid_decimal_with_precision(self) -> None:
        """Decimal value with positive precision constructs without error."""
        fn = FluentNumber(Decimal("1.23"), "1.23", precision=2)
        assert fn.value == Decimal("1.23")
        assert fn.precision == 2

    def test_none_precision_accepted(self) -> None:
        """precision=None signals raw variable interpolation (not NUMBER())."""
        fn = FluentNumber(1, "1")
        assert fn.precision is None

    def test_zero_int_accepted(self) -> None:
        """Zero is a valid int value for NUMBER()."""
        fn = FluentNumber(0, "0", precision=0)
        assert fn.value == 0

    def test_negative_int_accepted(self) -> None:
        """Negative integers are valid values for NUMBER()."""
        fn = FluentNumber(-42, "-42", precision=0)
        assert fn.value == -42

    # --- Property-based tests ---

    @given(st.booleans())
    @settings(max_examples=2)
    def test_property_any_bool_raises_type_error(self, value: bool) -> None:
        """PROPERTY: Any bool value is always rejected (True and False)."""
        event(f"bool_value={value}")
        with pytest.raises(TypeError):
            FluentNumber(value, str(int(value)), precision=0)

    @given(st.integers(max_value=-1))
    @settings(max_examples=200)
    def test_property_negative_precision_always_raises(self, precision: int) -> None:
        """PROPERTY: Any negative precision always raises ValueError."""
        event(f"precision_magnitude={'small' if precision >= -10 else 'large'}")
        with pytest.raises(ValueError, match="precision must be >= 0"):
            FluentNumber(1, "1", precision=precision)

    @given(
        value=st.integers(),
        precision=st.one_of(st.none(), st.integers(min_value=0, max_value=20)),
    )
    @settings(max_examples=200)
    def test_property_int_valid_inputs_always_construct(
        self, value: int, precision: int | None
    ) -> None:
        """PROPERTY: Any int value with non-negative or None precision constructs."""
        event(f"precision_type={'none' if precision is None else 'set'}")
        event(f"value_sign={'neg' if value < 0 else 'nonneg'}")
        fn = FluentNumber(value, str(value), precision=precision)
        assert fn.value == value
        assert fn.precision == precision

    @given(
        dvalue=st.decimals(
            allow_nan=False,
            allow_infinity=False,
            min_value=Decimal("-1e15"),
            max_value=Decimal("1e15"),
        ),
        precision=st.one_of(st.none(), st.integers(min_value=0, max_value=20)),
    )
    @settings(max_examples=200)
    def test_property_decimal_valid_inputs_always_construct(
        self, dvalue: Decimal, precision: int | None
    ) -> None:
        """PROPERTY: Any finite Decimal with non-negative or None precision constructs."""
        event(f"precision_type={'none' if precision is None else 'set'}")
        event(f"value_sign={'neg' if dvalue < 0 else 'nonneg'}")
        fn = FluentNumber(dvalue, str(dvalue), precision=precision)
        assert fn.value == dvalue
        assert fn.precision == precision
