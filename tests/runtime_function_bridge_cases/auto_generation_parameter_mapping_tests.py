# mypy: ignore-errors
"""Split test cases from tests/test_runtime_function_bridge.py."""

from tests.runtime_function_bridge_cases import *  # noqa: F403 - shared split test support

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
