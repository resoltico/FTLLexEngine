# mypy: ignore-errors
"""Split test cases from tests/test_runtime_function_bridge.py."""

from tests.runtime_function_bridge_cases import *  # noqa: F403 - shared split test support

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
