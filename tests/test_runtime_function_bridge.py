"""Tests for runtime.function_bridge: FunctionRegistry, FunctionSignature, edge cases."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.function_bridge import (
    _FTL_REQUIRES_LOCALE_ATTR,
    FluentValue,
    FunctionRegistry,
    FunctionSignature,
    fluent_function,
)

# ============================================================================
# HELPER FUNCTIONS FOR TESTING
# ============================================================================


def sample_function(value: int, *, minimum_fraction_digits: int = 0) -> str:
    """Sample function with snake_case parameters."""
    return f"{value:.{minimum_fraction_digits}f}"


def simple_function(text: str) -> str:
    """Simple function with single parameter."""
    return text.upper()


def positional_only_function(value: int, /) -> str:
    """Function with positional-only parameter."""
    return str(value * 2)


def mixed_params_function(
    value: int, /, *, use_grouping: bool = False, date_style: str = "short"
) -> str:
    """Function with mixed parameter types."""
    result = str(value)
    if use_grouping:
        result = f"{value:,}"
    return f"{result} ({date_style})"


# ============================================================================
# FUNCTION SIGNATURE TESTS
# ============================================================================


class TestFunctionSignature:
    """Test FunctionSignature dataclass."""

    def test_create_function_signature(self) -> None:
        """Create FunctionSignature with all fields."""
        sig = FunctionSignature(
            python_name="test_func",
            ftl_name="TEST",
            param_mapping=(("minimumValue", "minimum_value"),),
            callable=str,
        )

        assert sig.python_name == "test_func"
        assert sig.ftl_name == "TEST"
        assert sig.param_mapping == (("minimumValue", "minimum_value"),)

    def test_function_signature_immutable(self) -> None:
        """FunctionSignature is immutable."""
        sig = FunctionSignature(
            python_name="test",
            ftl_name="TEST",
            param_mapping=(),
            callable=lambda: "test",
        )

        with pytest.raises(AttributeError):
            sig.python_name = "new_name"  # type: ignore[misc]


# ============================================================================
# FUNCTION REGISTRY BASIC TESTS
# ============================================================================


class TestFunctionRegistryBasic:
    """Test basic FunctionRegistry functionality."""

    def test_create_registry(self) -> None:
        """Create empty function registry."""
        registry = FunctionRegistry()

        assert not registry.has_function("NUMBER")

    def test_register_function_with_default_name(self) -> None:
        """Register function with auto-generated FTL name."""
        registry = FunctionRegistry()

        def number(value: int) -> str:
            return str(value)

        registry.register(number)

        assert registry.has_function("NUMBER")
        assert registry.get_python_name("NUMBER") == "number"

    def test_register_function_with_custom_ftl_name(self) -> None:
        """Register function with custom FTL name."""
        registry = FunctionRegistry()

        registry.register(sample_function, ftl_name="NUM_FORMAT")

        assert registry.has_function("NUM_FORMAT")
        assert not registry.has_function("SAMPLE_FUNCTION")

    def test_register_function_with_custom_param_map(self) -> None:
        """Register function with custom parameter mappings."""
        registry = FunctionRegistry()

        def custom_func(arg1: int, *, special_arg: str = "") -> str:
            return f"{arg1}:{special_arg}"

        registry.register(
            custom_func,
            ftl_name="CUSTOM",
            param_map={"customArg": "special_arg"},
        )

        result = registry.call("CUSTOM", [42], {"customArg": "test"})
        assert result == "42:test"

    def test_register_inject_locale_function_with_incompatible_signature(self) -> None:
        """Register function with inject_locale=True but wrong signature raises TypeError.

        Regression test for API-REGISTRY-SIG-MISMATCH-001.
        Functions marked with inject_locale=True must have at least 2 positional
        parameters to receive (value, locale_code). Registration should fail-fast
        rather than allowing runtime errors.
        """
        from ftllexengine.runtime.function_bridge import fluent_function  # noqa: PLC0415

        @fluent_function(inject_locale=True)
        def bad_func(value: int) -> str:
            """Only 1 positional param - incompatible with locale injection."""
            return str(value)

        registry = FunctionRegistry()

        with pytest.raises(TypeError, match="inject_locale=True requires at least 2 positional"):
            registry.register(bad_func, ftl_name="BAD")

    def test_register_inject_locale_function_with_compatible_signature(self) -> None:
        """Register function with inject_locale=True and correct signature succeeds."""
        from ftllexengine.runtime.function_bridge import fluent_function  # noqa: PLC0415

        @fluent_function(inject_locale=True)
        def good_func(value: int, locale_code: str) -> str:
            """2 positional params - compatible with locale injection."""
            return f"{value}@{locale_code}"

        registry = FunctionRegistry()
        registry.register(good_func, ftl_name="GOOD")

        assert registry.has_function("GOOD")


# ============================================================================
# PARAMETER NAME CONVERSION TESTS
# ============================================================================


class TestParameterNameConversion:
    """Test snake_case <-> camelCase conversion."""

    def test_to_camel_case_single_word(self) -> None:
        """Convert single word (no change)."""
        result = FunctionRegistry._to_camel_case("value")

        assert result == "value"

    def test_to_camel_case_two_words(self) -> None:
        """Convert two_words to twoWords."""
        result = FunctionRegistry._to_camel_case("minimum_value")

        assert result == "minimumValue"

    def test_to_camel_case_multiple_words(self) -> None:
        """Convert multiple_word_name to multipleWordName."""
        result = FunctionRegistry._to_camel_case("minimum_fraction_digits")

        assert result == "minimumFractionDigits"

    def test_to_camel_case_already_camel(self) -> None:
        """Convert camelCase (no underscores) stays same."""
        result = FunctionRegistry._to_camel_case("alreadyCamel")

        assert result == "alreadyCamel"



# ============================================================================
# FUNCTION CALLING TESTS
# ============================================================================


class TestFunctionCalling:
    """Test calling registered functions."""

    def test_call_function_with_positional_args(self) -> None:
        """Call function with only positional arguments."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="UPPER")

        result = registry.call("UPPER", ["hello"], {})

        assert result == "HELLO"

    def test_call_function_with_named_args(self) -> None:
        """Call function with named arguments."""
        registry = FunctionRegistry()
        registry.register(sample_function, ftl_name="FORMAT")

        # FTL: FORMAT($value, minimumFractionDigits: 2)
        result = registry.call("FORMAT", [42], {"minimumFractionDigits": 2})

        assert result == "42.00"

    def test_call_function_with_mixed_args(self) -> None:
        """Call function with both positional and named arguments."""
        registry = FunctionRegistry()
        registry.register(mixed_params_function, ftl_name="MIX")

        result = registry.call("MIX", [1000], {"useGrouping": True, "dateStyle": "long"})
        assert isinstance(result, str)
        assert "1,000" in result
        assert "long" in result

    def test_call_function_auto_converts_camel_to_snake(self) -> None:
        """Function call auto-converts FTL camelCase to Python snake_case."""
        registry = FunctionRegistry()

        def test_func(*, minimum_value: int = 0, maximum_value: int = 100) -> str:
            return f"{minimum_value}-{maximum_value}"

        registry.register(test_func, ftl_name="RANGE")

        # FTL uses camelCase: minimumValue, maximumValue
        result = registry.call("RANGE", [], {"minimumValue": 5, "maximumValue": 50})

        assert result == "5-50"

    def test_call_nonexistent_function_raises_error(self) -> None:
        """Calling non-existent function raises FrozenFluentError with RESOLUTION category."""
        registry = FunctionRegistry()

        with pytest.raises(FrozenFluentError, match="Function 'NONEXISTENT' not found") as exc_info:
            registry.call("NONEXISTENT", [], {})
        assert exc_info.value.category == ErrorCategory.RESOLUTION

    def test_call_function_that_raises_exception(self) -> None:
        """Function that raises exception is wrapped in FrozenFluentError."""
        registry = FunctionRegistry()

        def failing_func(_value: int) -> str:
            msg = "Something went wrong"
            raise ValueError(msg)

        registry.register(failing_func, ftl_name="FAIL")

        with pytest.raises(FrozenFluentError, match="Function 'FAIL' failed") as exc_info:
            registry.call("FAIL", [42], {})
        assert exc_info.value.category == ErrorCategory.RESOLUTION


# ============================================================================
# AUTO-GENERATION PARAMETER MAPPING TESTS
# ============================================================================


class TestAutoParameterMapping:
    """Test automatic parameter mapping generation."""

    def test_auto_map_snake_case_params(self) -> None:
        """Auto-generate mappings for snake_case parameters."""
        registry = FunctionRegistry()

        def func(*, minimum_value: int = 0, maximum_value: int = 100) -> str:
            return f"{minimum_value}:{maximum_value}"

        registry.register(func, ftl_name="FUNC")

        # Should auto-map: minimumValue -> minimum_value, maximumValue -> maximum_value
        result = registry.call("FUNC", [], {"minimumValue": 1, "maximumValue": 10})
        assert result == "1:10"

    def test_auto_map_skips_self_parameter(self) -> None:
        """Auto-mapping skips 'self' parameter."""

        class TestClass:
            def method(self, value: int) -> str:
                return str(value)

        registry = FunctionRegistry()
        obj = TestClass()
        registry.register(obj.method, ftl_name="METHOD")

        result = registry.call("METHOD", [42], {})
        assert result == "42"

    def test_auto_map_with_positional_only_marker(self) -> None:
        """Auto-mapping skips positional-only marker '/'."""
        registry = FunctionRegistry()

        registry.register(positional_only_function, ftl_name="POS")

        result = registry.call("POS", [21], {})
        assert result == "42"

    def test_custom_param_map_overrides_auto_map(self) -> None:
        """Custom parameter mapping overrides auto-generated mapping."""
        registry = FunctionRegistry()

        def func(*, minimum_value: int = 0) -> str:
            return str(minimum_value)

        # Auto would create: minimumValue -> minimum_value
        # Custom override: minVal -> minimum_value
        registry.register(
            func,
            ftl_name="FUNC",
            param_map={"minVal": "minimum_value"},
        )

        result = registry.call("FUNC", [], {"minVal": 42})
        assert result == "42"


# ============================================================================
# REGISTRY QUERY TESTS
# ============================================================================


class TestRegistryQueries:
    """Test registry query methods."""

    def test_has_function_returns_true_when_registered(self) -> None:
        """has_function returns True for registered function."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="UPPER")

        assert registry.has_function("UPPER")

    def test_has_function_returns_false_when_not_registered(self) -> None:
        """has_function returns False for unregistered function."""
        registry = FunctionRegistry()

        assert not registry.has_function("UNKNOWN")

    def test_get_python_name_returns_name_when_registered(self) -> None:
        """get_python_name returns Python function name."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="UPPER")

        python_name = registry.get_python_name("UPPER")

        assert python_name == "simple_function"

    def test_get_python_name_returns_none_when_not_registered(self) -> None:
        """get_python_name returns None for unregistered function."""
        registry = FunctionRegistry()

        python_name = registry.get_python_name("UNKNOWN")

        assert python_name is None


# ============================================================================
# INTROSPECTION API TESTS
# ============================================================================


class TestFunctionRegistryIntrospection:
    """Test FunctionRegistry introspection methods."""

    def test_list_functions_empty_registry(self) -> None:
        """list_functions returns empty list for empty registry."""
        registry = FunctionRegistry()

        functions = registry.list_functions()

        assert functions == []

    def test_list_functions_single_function(self) -> None:
        """list_functions returns single function name."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="UPPER")

        functions = registry.list_functions()

        assert functions == ["UPPER"]

    def test_list_functions_multiple_functions(self) -> None:
        """list_functions returns all registered function names."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="FUNC1")
        registry.register(sample_function, ftl_name="FUNC2")
        registry.register(positional_only_function, ftl_name="FUNC3")

        functions = registry.list_functions()

        assert set(functions) == {"FUNC1", "FUNC2", "FUNC3"}
        assert len(functions) == 3

    def test_get_function_info_existing_function(self) -> None:
        """get_function_info returns metadata for registered function."""
        registry = FunctionRegistry()
        registry.register(sample_function, ftl_name="FORMAT")

        info = registry.get_function_info("FORMAT")

        assert info is not None
        assert info.python_name == "sample_function"
        assert info.ftl_name == "FORMAT"
        assert isinstance(info.param_mapping, tuple)
        assert "minimumFractionDigits" in info.param_dict
        assert info.param_dict["minimumFractionDigits"] == "minimum_fraction_digits"
        assert callable(info.callable)

    def test_get_function_info_nonexistent_function(self) -> None:
        """get_function_info returns None for unregistered function."""
        registry = FunctionRegistry()

        info = registry.get_function_info("NONEXISTENT")

        assert info is None

    def test_iter_empty_registry(self) -> None:
        """Iterating empty registry yields no names."""
        registry = FunctionRegistry()

        names = list(registry)

        assert names == []

    def test_iter_single_function(self) -> None:
        """Iterating registry yields function names."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="UPPER")

        names = list(registry)

        assert names == ["UPPER"]

    def test_iter_multiple_functions(self) -> None:
        """Iterating registry yields all function names."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="FUNC1")
        registry.register(sample_function, ftl_name="FUNC2")
        registry.register(positional_only_function, ftl_name="FUNC3")

        names = list(registry)

        assert set(names) == {"FUNC1", "FUNC2", "FUNC3"}

    def test_iter_for_loop(self) -> None:
        """Can iterate registry in for loop."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="A")
        registry.register(sample_function, ftl_name="B")

        collected_names = []
        for name in registry:
            collected_names.append(name)

        assert set(collected_names) == {"A", "B"}

    def test_len_empty_registry(self) -> None:
        """len() returns 0 for empty registry."""
        registry = FunctionRegistry()

        assert len(registry) == 0

    def test_len_single_function(self) -> None:
        """len() returns 1 for registry with one function."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="FUNC")

        assert len(registry) == 1

    def test_len_multiple_functions(self) -> None:
        """len() returns correct count for multiple functions."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="F1")
        registry.register(sample_function, ftl_name="F2")
        registry.register(positional_only_function, ftl_name="F3")

        assert len(registry) == 3

    def test_len_after_overwrite(self) -> None:
        """len() doesn't double-count after overwriting function."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="FUNC")
        registry.register(sample_function, ftl_name="FUNC")

        assert len(registry) == 1

    def test_contains_registered_function(self) -> None:
        """'in' operator returns True for registered function."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="UPPER")

        assert "UPPER" in registry

    def test_contains_unregistered_function(self) -> None:
        """'in' operator returns False for unregistered function."""
        registry = FunctionRegistry()

        assert "NONEXISTENT" not in registry

    def test_contains_case_sensitive(self) -> None:
        """'in' operator is case-sensitive."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="UPPER")

        assert "UPPER" in registry
        assert "upper" not in registry
        assert "Upper" not in registry

    def test_introspection_integration(self) -> None:
        """Combine introspection methods for function discovery."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="FUNC1")
        registry.register(sample_function, ftl_name="FUNC2")

        # Check count
        assert len(registry) == 2

        # List all functions
        functions = registry.list_functions()
        assert len(functions) == 2

        # Iterate and inspect each function
        for name in registry:
            assert name in registry
            info = registry.get_function_info(name)
            assert info is not None
            assert info.ftl_name == name

    def test_copy_preserves_introspection(self) -> None:
        """Copied registry preserves introspection capabilities."""
        original = FunctionRegistry()
        original.register(simple_function, ftl_name="FUNC1")
        original.register(sample_function, ftl_name="FUNC2")

        copied = original.copy()

        # Both registries have same functions
        assert len(original) == len(copied)
        assert set(original) == set(copied)
        assert original.list_functions() == copied.list_functions()

        # Modifying copy doesn't affect original
        copied.register(positional_only_function, ftl_name="FUNC3")
        assert len(copied) == 3
        assert len(original) == 2


# ============================================================================
# EDGE CASES AND INTEGRATION TESTS
# ============================================================================


class TestFunctionBridgeEdgeCases:
    """Test edge cases and corner scenarios."""

    def test_register_multiple_functions(self) -> None:
        """Register multiple functions in same registry."""
        registry = FunctionRegistry()

        def func1(x: int) -> str:
            return str(x)

        def func2(x: int) -> str:
            return str(x * 2)

        registry.register(func1, ftl_name="F1")
        registry.register(func2, ftl_name="F2")

        assert registry.has_function("F1")
        assert registry.has_function("F2")
        assert registry.call("F1", [5], {}) == "5"
        assert registry.call("F2", [5], {}) == "10"

    def test_overwrite_registered_function(self) -> None:
        """Registering same FTL name twice overwrites previous."""
        registry = FunctionRegistry()

        def func1(_x: int) -> str:
            return "first"

        def func2(_x: int) -> str:
            return "second"

        registry.register(func1, ftl_name="FUNC")
        registry.register(func2, ftl_name="FUNC")

        result = registry.call("FUNC", [1], {})
        assert result == "second"

    def test_empty_parameter_name(self) -> None:
        """Handle empty parameter names gracefully."""
        result = FunctionRegistry._to_camel_case("")
        assert result == ""

    def test_parameter_with_numbers(self) -> None:
        """Handle parameter names with numbers."""
        result = FunctionRegistry._to_camel_case("param_123_test")
        assert result == "param123Test"

    def test_call_with_unmapped_parameter(self) -> None:
        """Call with parameter not in mapping passes through unchanged."""
        registry = FunctionRegistry()

        def func(**kwargs: Any) -> str:
            return str(kwargs.get("unknownParam", "default"))

        registry.register(func, ftl_name="FUNC")

        # unknownParam not in auto-mapping, but should pass through
        result = registry.call("FUNC", [], {"unknownParam": "custom"})
        assert result == "custom"


# ============================================================================
# REAL-WORLD USAGE TESTS
# ============================================================================


class TestRealWorldUsage:
    """Test realistic usage scenarios."""

    def test_number_formatting_function(self) -> None:
        """Test NUMBER-like function with real parameters."""
        registry = FunctionRegistry()

        def number_format(
            value: object,
            *,
            minimum_fraction_digits: int = 0,  # noqa: ARG001
            maximum_fraction_digits: int = 3,
            use_grouping: bool = False,
        ) -> str:
            formatted = f"{Decimal(str(value)):.{maximum_fraction_digits}f}"
            if use_grouping:
                # Simple grouping simulation
                parts = formatted.split(".")
                parts[0] = f"{int(parts[0]):,}"
                formatted = ".".join(parts)
            return formatted

        registry.register(number_format, ftl_name="NUMBER")

        # FTL: { NUMBER($price, minimumFractionDigits: 2, useGrouping: true) }
        result = registry.call(
            "NUMBER",
            [Decimal("1234.5")],
            {"minimumFractionDigits": 2, "useGrouping": True},
        )
        assert isinstance(result, str)
        assert "1,234" in result

    def test_datetime_formatting_function(self) -> None:
        """Test DATETIME-like function with style parameters."""
        registry = FunctionRegistry()

        def datetime_format(
            value: str, *, date_style: str = "short", time_style: str = "short"
        ) -> str:
            return f"{value} ({date_style}/{time_style})"

        registry.register(datetime_format, ftl_name="DATETIME")

        # FTL: { DATETIME($date, dateStyle: "long", timeStyle: "medium") }
        result = registry.call(
            "DATETIME",
            ["2024-01-15"],
            {"dateStyle": "long", "timeStyle": "medium"},
        )

        assert result == "2024-01-15 (long/medium)"


# ============================================================================
# EDGE CASES (from test_function_bridge_edge_cases.py)
# ============================================================================


class TestFrozenRegistryLines160To164:
    """Test lines 160-164: TypeError when registering on frozen registry."""

    def test_register_on_frozen_registry_raises_type_error(self) -> None:
        """Test register() raises TypeError on frozen registry (lines 160-164)."""
        registry = FunctionRegistry()

        # Freeze the registry
        registry.freeze()

        # Try to register a function on frozen registry
        def my_func(value: str, locale_code: str, /) -> str:  # noqa: ARG001
            return value

        # Should raise TypeError with specific message
        with pytest.raises(
            TypeError,
            match=r"Cannot modify frozen registry.*create_default_registry",
        ):
            registry.register(my_func, ftl_name="MYFUNC")


class TestParameterCollisionLines188To193:
    """Test lines 188-193: ValueError on parameter name collision."""

    def test_register_with_parameter_collision_raises_value_error(self) -> None:
        """Test register() raises ValueError on parameter collision (lines 188-193)."""
        registry = FunctionRegistry()

        # Create a function with parameters that will collide after stripping underscores
        # Both `_value` and `value` would map to camelCase `value`
        def colliding_func(
            val: str,
            locale_code: str,  # noqa: ARG001
            /,
            _test_param: int = 0,  # Will strip to `test_param` -> `testParam`
            test_param: int = 0,  # Also maps to `testParam`  # noqa: ARG001
        ) -> str:
            return val

        # Should raise ValueError about parameter collision
        with pytest.raises(ValueError, match=r"Parameter name collision.*testParam"):
            registry.register(colliding_func, ftl_name="COLLIDE")


class TestFreezeMethodLine285:
    """Test line 285: freeze() method."""

    def test_freeze_sets_frozen_flag(self) -> None:
        """Test freeze() sets _frozen = True (line 285)."""
        registry = FunctionRegistry()

        # Initially not frozen
        assert not registry.frozen

        # Freeze it
        registry.freeze()

        # Should now be frozen
        assert registry.frozen

    def test_freeze_prevents_registration(self) -> None:
        """Test freeze() actually prevents further registration."""
        registry = FunctionRegistry()

        # Register a function before freezing
        def func1(value: str, locale_code: str, /) -> str:  # noqa: ARG001
            return value

        registry.register(func1, ftl_name="FUNC1")
        assert "FUNC1" in registry

        # Freeze the registry
        registry.freeze()

        # Try to register another function
        def func2(value: str, locale_code: str, /) -> str:  # noqa: ARG001
            return value

        # Should fail
        with pytest.raises(TypeError):
            registry.register(func2, ftl_name="FUNC2")

        # Original function still there
        assert "FUNC1" in registry
        # New function not added
        assert "FUNC2" not in registry


class TestFrozenPropertyLine294:
    """Test line 294: frozen property getter."""

    def test_frozen_property_returns_false_initially(self) -> None:
        """Test frozen property returns False for new registry (line 294)."""
        registry = FunctionRegistry()

        # Should not be frozen initially
        result = registry.frozen

        assert result is False

    def test_frozen_property_returns_true_after_freeze(self) -> None:
        """Test frozen property returns True after freeze() (line 294)."""
        registry = FunctionRegistry()

        # Freeze it
        registry.freeze()

        # Property should return True
        result = registry.frozen

        assert result is True

    def test_frozen_property_is_readonly(self) -> None:
        """Test frozen property cannot be set directly."""
        registry = FunctionRegistry()

        # Should not be able to set frozen property
        with pytest.raises(AttributeError):
            registry.frozen = True  # type: ignore[misc]


class TestFrozenRegistryCopyIntegration:
    """Integration tests for frozen registry and copy()."""

    def test_copy_of_frozen_registry_is_mutable(self) -> None:
        """Test copy() of frozen registry creates mutable copy."""
        registry = FunctionRegistry()

        # Register and freeze
        def func1(value: str, locale_code: str, /) -> str:  # noqa: ARG001
            return value

        registry.register(func1, ftl_name="FUNC1")
        registry.freeze()

        # Create copy
        copy = registry.copy()

        # Copy should not be frozen
        assert not copy.frozen

        # Should be able to register on copy
        def func2(value: str, locale_code: str, /) -> str:  # noqa: ARG001
            return value

        copy.register(func2, ftl_name="FUNC2")

        # Copy has both functions
        assert "FUNC1" in copy
        assert "FUNC2" in copy

        # Original only has first function
        assert "FUNC1" in registry
        assert "FUNC2" not in registry


class TestFluentFunctionDecoratorWithParentheses:
    """Test lines 134-148: fluent_function decorator WITH parentheses."""

    def test_fluent_function_decorator_with_inject_locale_true(self) -> None:
        """Test @fluent_function(inject_locale=True) decorator path (lines 134-148)."""
        from ftllexengine.runtime.function_bridge import fluent_function  # noqa: PLC0415

        # Use decorator WITH parentheses
        @fluent_function(inject_locale=True)
        def my_format(value: str, locale_code: str, /) -> str:
            return f"{value}_{locale_code}"

        # Verify the function works
        result = my_format("test", "en_US")
        assert result == "test_en_US"

        # Verify the locale injection marker was set
        assert hasattr(my_format, "_ftl_requires_locale")
        assert my_format._ftl_requires_locale is True

    def test_fluent_function_decorator_with_inject_locale_false(self) -> None:
        """Test @fluent_function(inject_locale=False) decorator path."""
        from ftllexengine.runtime.function_bridge import fluent_function  # noqa: PLC0415

        # Use decorator WITH parentheses but inject_locale=False
        @fluent_function(inject_locale=False)
        def my_upper(value: str) -> str:
            return value.upper()

        # Verify the function works
        result = my_upper("test")
        assert result == "TEST"

        # Verify the locale injection marker was NOT set
        assert not getattr(my_upper, "_ftl_requires_locale", False)

    def test_fluent_function_decorator_without_parentheses(self) -> None:
        """Test @fluent_function decorator WITHOUT parentheses (line 147)."""
        from ftllexengine.runtime.function_bridge import fluent_function  # noqa: PLC0415

        # Use decorator WITHOUT parentheses
        @fluent_function
        def my_simple(value: str) -> str:
            return value.lower()

        # Verify the function works
        result = my_simple("TEST")
        assert result == "test"

        # When used without parentheses and without inject_locale, should not set marker
        assert not getattr(my_simple, "_ftl_requires_locale", False)


class TestRegisterWithUninspectableCallable:
    """Test lines 258-264: ValueError when callable has no inspectable signature."""

    def test_register_uninspectable_callable_raises_type_error(self) -> None:
        """Test register() raises TypeError for callables without signatures (lines 258-264)."""
        registry = FunctionRegistry()

        # Create a mock callable that signature() cannot inspect
        class UninspectableCallable:
            def __call__(self, *args: object, **kwargs: object) -> str:  # noqa: ARG002
                return "test"

        # Manually break signature inspection by making it raise ValueError
        from unittest.mock import patch  # noqa: PLC0415

        uninspectable = UninspectableCallable()

        with (
            patch(
                "ftllexengine.runtime.function_bridge.signature",
                side_effect=ValueError("No signature"),
            ),
            pytest.raises(
                TypeError,
                match=r"Cannot register.*no inspectable signature.*param_mapping",
            ),
        ):
            registry.register(uninspectable, ftl_name="UNINSPECTABLE")


class TestShouldInjectLocaleWithMissingFunction:
    """Test lines 575-579: should_inject_locale when function not in registry."""

    def test_should_inject_locale_returns_false_for_missing_function(self) -> None:
        """Test should_inject_locale returns False for non-existent function (lines 575-576)."""
        registry = FunctionRegistry()

        # Function doesn't exist in registry
        result = registry.should_inject_locale("NONEXISTENT")

        # Should return False (not raise)
        assert result is False

    def test_should_inject_locale_returns_false_for_function_without_marker(self) -> None:
        """Test should_inject_locale when function has no marker.

        Returns False when function exists but has no marker (lines 578-579).
        """
        registry = FunctionRegistry()

        # Register a function without locale injection marker
        def my_func(value: str, locale_code: str, /) -> str:  # noqa: ARG001
            return value

        registry.register(my_func, ftl_name="CUSTOM")

        # Function exists, but doesn't have _ftl_requires_locale marker
        result = registry.should_inject_locale("CUSTOM")

        # Should return False (lines 578-579: getattr returns False)
        assert result is False

    def test_should_inject_locale_returns_true_for_function_with_marker(self) -> None:
        """Test should_inject_locale returns True when function has marker set."""
        from ftllexengine.runtime.function_bridge import fluent_function  # noqa: PLC0415

        registry = FunctionRegistry()

        # Register a function with locale injection marker
        @fluent_function(inject_locale=True)
        def my_format(value: str, locale_code: str, /) -> str:
            return f"{value}_{locale_code}"

        registry.register(my_format, ftl_name="MYFORMAT")

        # Function has marker, should return True
        result = registry.should_inject_locale("MYFORMAT")

        assert result is True


class TestGetExpectedPositionalArgs:
    """Test lines 605-608: get_expected_positional_args method."""

    def test_get_expected_positional_args_for_builtin_function(self) -> None:
        """Test get_expected_positional_args returns count for built-in (lines 605-608)."""
        from ftllexengine.runtime.functions import create_default_registry  # noqa: PLC0415

        registry = create_default_registry()

        # NUMBER is a built-in function with 1 positional arg
        result = registry.get_expected_positional_args("NUMBER")

        assert result == 1

    def test_get_expected_positional_args_for_custom_function(self) -> None:
        """Test get_expected_positional_args returns None for custom function."""
        registry = FunctionRegistry()

        # Register a custom function
        def my_func(value: str, locale_code: str, /) -> str:  # noqa: ARG001
            return value

        registry.register(my_func, ftl_name="CUSTOM")

        # Custom function should return None (not in BUILTIN_FUNCTIONS)
        result = registry.get_expected_positional_args("CUSTOM")

        assert result is None


class TestGetBuiltinMetadata:
    """Test lines 626-628: get_builtin_metadata method."""

    def test_get_builtin_metadata_for_builtin_function(self) -> None:
        """Test get_builtin_metadata returns metadata for built-in (lines 626-628)."""
        from ftllexengine.runtime.functions import create_default_registry  # noqa: PLC0415

        registry = create_default_registry()

        # NUMBER is a built-in function
        metadata = registry.get_builtin_metadata("NUMBER")

        # Should return metadata object
        assert metadata is not None
        assert metadata.requires_locale is True

    def test_get_builtin_metadata_for_custom_function(self) -> None:
        """Test get_builtin_metadata returns None for custom function."""
        registry = FunctionRegistry()

        # Register a custom function
        def my_func(value: str, locale_code: str, /) -> str:  # noqa: ARG001
            return value

        registry.register(my_func, ftl_name="CUSTOM")

        # Custom function should return None
        metadata = registry.get_builtin_metadata("CUSTOM")

        assert metadata is None


# ============================================================================
# DECORATOR AND REGISTRY COVERAGE
# ============================================================================


class TestFunctionBridgeCoverage:
    """Test fluent_function decorator and FunctionRegistry coverage."""

    def test_fluent_function_no_parentheses_usage(self) -> None:
        """Using @fluent_function without parentheses applies decorator directly."""

        @fluent_function
        def my_upper(value: str) -> FluentValue:
            return value.upper()

        result = my_upper("hello")
        assert result == "HELLO"

    def test_fluent_function_with_parentheses_usage(self) -> None:
        """Using @fluent_function() with parentheses works as factory."""

        @fluent_function()
        def my_lower(value: str) -> FluentValue:
            return value.lower()

        result = my_lower("HELLO")
        assert result == "hello"

    def test_fluent_function_with_locale_injection(self) -> None:
        """Using @fluent_function(inject_locale=True) sets locale attribute."""

        @fluent_function(inject_locale=True)
        def locale_aware(value: str, locale: str) -> FluentValue:
            return f"{value}@{locale}"

        assert hasattr(locale_aware, _FTL_REQUIRES_LOCALE_ATTR)
        assert getattr(locale_aware, _FTL_REQUIRES_LOCALE_ATTR) is True

    def test_fluent_function_wrapper_returns_value(self) -> None:
        """Wrapper function passes through the decorated function's return value."""

        @fluent_function
        def add_suffix(value: str, suffix: str = "!") -> FluentValue:
            return f"{value}{suffix}"

        result = add_suffix("Hello", suffix="?")
        assert result == "Hello?"

    def test_get_builtin_metadata_exists(self) -> None:
        """get_builtin_metadata returns metadata for known built-in function."""
        registry = FunctionRegistry()

        meta = registry.get_builtin_metadata("NUMBER")
        assert meta is not None
        assert meta.requires_locale is True

    def test_get_builtin_metadata_not_exists(self) -> None:
        """get_builtin_metadata returns None for unknown function name."""
        registry = FunctionRegistry()

        meta = registry.get_builtin_metadata("NONEXISTENT")
        assert meta is None


class TestFunctionBridgeLeadingUnderscore:
    """Test function parameter with leading underscore is preserved in mapping."""

    def test_parameter_with_leading_underscore(self) -> None:
        """Parameter with leading underscore is kept in param_mapping."""
        registry = FunctionRegistry()

        def test_func(_internal: str, public: str) -> str:  # noqa: PT019
            return f"{_internal}:{public}"

        registry.register(test_func, ftl_name="TEST")

        sig = registry._functions["TEST"]  # pylint: disable=protected-access
        param_values = [v for _, v in sig.param_mapping]
        assert "_internal" in param_values


class TestFunctionMetadataCallable:
    """Test should_inject_locale returns False for unknown function names."""

    def test_should_inject_locale_not_found(self) -> None:
        """should_inject_locale returns False for unregistered function name."""
        registry = FunctionRegistry()

        def custom(val: str) -> str:
            return val

        registry.register(custom, ftl_name="CUSTOM")
        assert registry.should_inject_locale("NOTFOUND") is False
