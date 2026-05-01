# mypy: ignore-errors
"""Split test cases from tests/test_runtime_function_bridge.py."""

from tests.runtime_function_bridge_cases import *  # noqa: F403 - shared split test support

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

        def test_func(_internal: str, public: str) -> str:  # noqa: PT019 - intentional
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
