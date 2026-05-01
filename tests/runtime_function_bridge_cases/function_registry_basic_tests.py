# mypy: ignore-errors
"""Split test cases from tests/test_runtime_function_bridge.py."""

from tests.runtime_function_bridge_cases import *  # noqa: F403 - shared split test support

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
        from ftllexengine.runtime.function_bridge import (
            fluent_function,
        )

        @fluent_function(inject_locale=True)
        def bad_func(value: int) -> str:
            """Only 1 positional param - incompatible with locale injection."""
            return str(value)

        registry = FunctionRegistry()

        with pytest.raises(TypeError, match="inject_locale=True requires at least 2 positional"):
            registry.register(bad_func, ftl_name="BAD")

    def test_register_inject_locale_function_with_compatible_signature(self) -> None:
        """Register function with inject_locale=True and correct signature succeeds."""
        from ftllexengine.runtime.function_bridge import (
            fluent_function,
        )

        @fluent_function(inject_locale=True)
        def good_func(value: int, locale_code: str) -> str:
            """2 positional params - compatible with locale injection."""
            return f"{value}@{locale_code}"

        registry = FunctionRegistry()
        registry.register(good_func, ftl_name="GOOD")

        assert registry.has_function("GOOD")
