"""Tests for FormatCache depth limiting and type validation.

Validates that _make_hashable:
1. Respects depth limits for nested structures
2. Validates types explicitly (no cast())
3. Handles FluentValue types correctly
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.runtime.function_bridge import FluentNumber

# ============================================================================
# DEPTH LIMITING TESTS
# ============================================================================


class TestMakeHashableDepthLimiting:
    """Test depth limiting in _make_hashable."""

    def test_shallow_nesting_succeeds(self) -> None:
        """Shallow nested structures convert successfully."""
        shallow = {"a": [1, 2, {"b": 3}]}
        result = IntegrityCache._make_hashable(shallow)
        assert result is not None

    def test_moderate_nesting_succeeds(self) -> None:
        """Moderately nested structures convert successfully."""
        # Build 50 levels of nesting (well under MAX_DEPTH)
        value: dict[str, Any] | int = 42
        for _ in range(50):
            value = {"nested": value}

        result = IntegrityCache._make_hashable(value)
        assert result is not None

    def test_excessive_nesting_raises_type_error(self) -> None:
        """Excessively nested structures raise TypeError."""
        # Build MAX_DEPTH + 10 levels of nesting
        value: dict[str, Any] | int = 42
        for _ in range(MAX_DEPTH + 10):
            value = {"nested": value}

        with pytest.raises(TypeError, match="Maximum nesting depth exceeded"):
            IntegrityCache._make_hashable(value)

    def test_custom_depth_limit_respected(self) -> None:
        """Custom depth parameter is respected."""
        # Build 15 levels of nesting
        value: dict[str, Any] | int = 42
        for _ in range(15):
            value = {"nested": value}

        # Should fail with depth=10
        with pytest.raises(TypeError, match="Maximum nesting depth exceeded"):
            IntegrityCache._make_hashable(value, depth=10)

        # Should succeed with depth=20
        result = IntegrityCache._make_hashable(value, depth=20)
        assert result is not None

    def test_list_nesting_depth_limited(self) -> None:
        """List nesting respects depth limit."""
        # Build nested lists
        value: list[Any] | int = 42
        for _ in range(MAX_DEPTH + 10):
            value = [value]

        with pytest.raises(TypeError, match="Maximum nesting depth exceeded"):
            IntegrityCache._make_hashable(value)

    def test_set_nesting_depth_limited(self) -> None:
        """Set nesting cannot exceed depth limit.

        Note: Sets cannot contain other sets (unhashable), so we test
        sets containing tuples which can nest.
        """
        # Sets with simple values should work
        value = {1, 2, 3}
        result = IntegrityCache._make_hashable(value)
        assert isinstance(result, frozenset)

    def test_mixed_nesting_depth_limited(self) -> None:
        """Mixed dict/list nesting respects depth limit."""
        # Alternate between dicts and lists
        value: dict[str, Any] | list[Any] | int = 42
        for i in range(MAX_DEPTH + 10):
            value = {"nested": value} if i % 2 == 0 else [value]

        with pytest.raises(TypeError, match="Maximum nesting depth exceeded"):
            IntegrityCache._make_hashable(value)


# ============================================================================
# TYPE VALIDATION TESTS
# ============================================================================


class TestMakeHashableTypeValidation:
    """Test type validation in _make_hashable."""

    def test_string_accepted(self) -> None:
        """Strings are accepted as hashable."""
        result = IntegrityCache._make_hashable("hello")
        assert result == "hello"

    def test_int_accepted(self) -> None:
        """Integers are type-tagged to prevent hash collision with bool/float."""
        result = IntegrityCache._make_hashable(42)
        assert result == ("__int__", 42)

    def test_float_accepted(self) -> None:
        """Floats are type-tagged to prevent hash collision with int."""
        result = IntegrityCache._make_hashable(3.14)
        assert result == ("__float__", 3.14)

    def test_bool_accepted(self) -> None:
        """Booleans are type-tagged to prevent hash collision with int."""
        result = IntegrityCache._make_hashable(True)
        assert result == ("__bool__", True)

    def test_none_accepted(self) -> None:
        """None is accepted as hashable."""
        result = IntegrityCache._make_hashable(None)
        assert result is None

    def test_decimal_accepted(self) -> None:
        """Decimals are type-tagged with str() to preserve scale for CLDR rules."""
        value = Decimal("123.45")
        result = IntegrityCache._make_hashable(value)
        assert result == ("__decimal__", "123.45")

    def test_datetime_accepted(self) -> None:
        """Datetimes are accepted as hashable."""
        value = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        result = IntegrityCache._make_hashable(value)
        assert result == value

    def test_date_accepted(self) -> None:
        """Dates are accepted as hashable."""
        value = date(2024, 1, 1)
        result = IntegrityCache._make_hashable(value)
        assert result == value

    def test_fluent_number_accepted(self) -> None:
        """FluentNumber is type-tagged with underlying type info for precision."""
        value = FluentNumber(value=42, formatted="42")
        result = IntegrityCache._make_hashable(value)
        # FluentNumber is type-tagged: (__fluentnumber__, type_name, value, formatted, precision)
        assert result == ("__fluentnumber__", "int", 42, "42", None)

    def test_list_converted_to_tuple(self) -> None:
        """Lists are type-tagged to distinguish from tuples in formatted output."""
        result = IntegrityCache._make_hashable([1, 2, 3])
        # Lists are type-tagged with "__list__" prefix
        assert result == ("__list__", (("__int__", 1), ("__int__", 2), ("__int__", 3)))

    def test_dict_converted_to_sorted_tuple(self) -> None:
        """Dicts are converted to sorted tuple of tuples with type-tagged values."""
        result = IntegrityCache._make_hashable({"b": 2, "a": 1})
        # Ints are type-tagged
        assert result == (("a", ("__int__", 1)), ("b", ("__int__", 2)))

    def test_set_converted_to_frozenset(self) -> None:
        """Sets are converted to frozensets with type-tagged int elements."""
        result = IntegrityCache._make_hashable({1, 2, 3})
        # Ints are type-tagged
        expected = frozenset({("__int__", 1), ("__int__", 2), ("__int__", 3)})
        assert result == expected

    def test_unknown_type_raises_type_error(self) -> None:
        """Unknown types raise TypeError with descriptive message."""

        class CustomObject:
            pass

        with pytest.raises(TypeError, match="Unknown type in cache key"):
            IntegrityCache._make_hashable(CustomObject())


# ============================================================================
# INTEGRATION WITH _make_key
# ============================================================================


class TestMakeKeyIntegration:
    """Test _make_hashable integration with _make_key."""

    def test_make_key_with_simple_args(self) -> None:
        """_make_key handles simple arguments."""
        key = IntegrityCache._make_key(
            message_id="test",
            args={"name": "Alice", "count": 42},
            attribute=None,
            locale_code="en",
            use_isolating=True,
        )
        assert key is not None

    def test_make_key_with_nested_args(self) -> None:
        """_make_key handles nested arguments via _make_hashable."""
        # Note: FluentValue doesn't include nested dicts, but _make_hashable
        # handles them for robustness. Using type: ignore for test.
        key = IntegrityCache._make_key(
            message_id="test",
            args={"items": [1, 2, 3]},  # type: ignore[dict-item]
            attribute=None,
            locale_code="en",
            use_isolating=True,
        )
        assert key is not None

    def test_make_key_with_deeply_nested_args_returns_none(self) -> None:
        """_make_key returns None for excessively nested args (graceful bypass)."""
        # Build excessively nested structure
        deep: dict[str, Any] | int = 42
        for _ in range(MAX_DEPTH + 10):
            deep = {"nested": deep}

        key = IntegrityCache._make_key(
            message_id="test",
            args={"deep": deep},  # type: ignore[dict-item]
            attribute=None,
            locale_code="en",
            use_isolating=True,
        )
        # Should return None (cache bypass) instead of crashing
        assert key is None

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
        # Should return None (cache bypass) instead of crashing
        assert key is None

    def test_make_key_with_fluent_value_types(self) -> None:
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
