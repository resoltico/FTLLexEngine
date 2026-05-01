# mypy: ignore-errors
"""Split test cases from tests/test_runtime_function_bridge.py."""

from tests.runtime_function_bridge_cases import *  # noqa: F403 - shared split test support

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
