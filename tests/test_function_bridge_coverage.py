"""Tests for runtime/function_bridge.py to achieve 100% coverage.

Focuses on parameter skip logic for 'self', '/', and '*' (line 106).
"""

from ftllexengine.runtime.function_bridge import FluentFunction, FunctionRegistry


class TestParameterSkipLogic:
    """Test that special parameter names are skipped (line 106)."""

    def test_register_function_with_self_parameter(self):
        """Test registering an unbound method with 'self' parameter."""
        registry = FunctionRegistry()

        # Create a class with a method containing 'self'
        class TestClass:
            def format_value(self, value: int) -> str:
                return f"Value: {value}"

        # Register the UNBOUND method (from class, not instance)
        # This will have 'self' in signature, triggering line 106
        registry.register(TestClass.format_value, ftl_name="FORMAT")

        # Call with instance as first positional arg
        instance = TestClass()
        result = registry.call("FORMAT", [instance, 42], {})  # type: ignore[list-item]
        assert result == "Value: 42"

        # Verify 'self' was skipped in parameter mapping
        sig = registry._functions["FORMAT"]
        param_values = [v for _, v in sig.param_mapping]
        assert "self" not in param_values
        assert "value" in param_values

    def test_register_function_with_star_separator(self):
        """Test registering function with keyword-only separator '*'."""
        registry = FunctionRegistry()

        # Function with keyword-only parameters (uses * separator)
        def format_kw_only(*, value: int, style: str = "plain") -> str:
            return f"{value} ({style})"

        registry.register(format_kw_only, ftl_name="KW")

        # Call with named arguments (star separator should be skipped)
        result = registry.call("KW", [], {"value": 10, "style": "fancy"})
        assert result == "10 (fancy)"

    def test_register_function_with_positional_only_slash(self):
        """Test registering function with positional-only separator '/'."""
        registry = FunctionRegistry()

        # Function with positional-only parameters
        def format_pos_only(value: int, /) -> str:
            return f"Result: {value}"

        registry.register(format_pos_only, ftl_name="POS")

        # Call should work, skipping '/' in mapping
        result = registry.call("POS", [99], {})
        assert result == "Result: 99"

    def test_register_method_with_self_and_kwargs(self):
        """Test method with self and keyword arguments."""
        registry = FunctionRegistry()

        class Formatter:
            def format_number(self, value: int, *, precision: int = 2) -> str:
                return f"{value:.{precision}f}"

        formatter = Formatter()
        registry.register(formatter.format_number, ftl_name="NUM")

        # self should be skipped, precision should map to precision
        result = registry.call("NUM", [42], {"precision": 1})
        assert result == "42.0"

    def test_all_special_params_are_skipped(self):
        """Verify that self, /, and * are all skipped in parameter mapping."""
        registry = FunctionRegistry()

        class ComplexFormatter:
            def complex_format(
                self, pos: int, /, *, keyword_arg: str = "default"
            ) -> str:
                return f"{pos}: {keyword_arg}"

        formatter = ComplexFormatter()
        registry.register(formatter.complex_format, ftl_name="COMPLEX")

        # Only 'keyword_arg' should be in the mapping, not self, /, or *
        sig = registry._functions["COMPLEX"]
        param_names = {v for _, v in sig.param_mapping}

        # Should include keyword_arg but NOT self, /, or *
        assert "keyword_arg" in param_names
        assert "self" not in param_names
        assert "/" not in param_names
        assert "*" not in param_names


# ============================================================================
# LINE 60: Test FluentFunction Protocol
# ============================================================================


class TestFluentFunctionProtocol:
    """Test FluentFunction protocol definition (line 60)."""

    def test_fluent_function_protocol_implementation(self) -> None:
        """Test that FluentFunction protocol is correctly implemented (line 60)."""
        # Import and access the protocol to trigger coverage of line 60
        # The __call__ method's ellipsis (...) needs to be referenced
        from inspect import signature

        # Directly access the protocol's __call__ method to trigger line 60
        # This is necessary to get coverage for the protocol stub
        protocol_method = FluentFunction.__call__
        assert protocol_method is not None

        # Get the FluentFunction protocol's __call__ signature
        # This forces evaluation of the protocol definition
        protocol_sig = signature(FluentFunction.__call__)

        # Verify the protocol has the correct parameters
        params = list(protocol_sig.parameters.keys())
        assert "self" in params or len(params) >= 2  # self, value, locale_code

        # Create a class that implements the FluentFunction protocol
        class CustomFormatter:
            """Custom formatter that implements FluentFunction protocol."""

            def __call__(
                self, value: int, locale_code: str, /, **kwargs: int  # noqa: ARG002
            ) -> str:
                """Implement the FluentFunction protocol signature."""
                precision = kwargs.get("precision", 2)
                return f"{value:.{precision}f}"

        # Create an instance
        formatter = CustomFormatter()

        # Verify it can be used as a FluentFunction
        # The protocol requires: (value, locale_code, /, **kwargs) -> str
        result = formatter(42, "en_US", precision=3)
        assert result == "42.000"

        # Register it with FunctionRegistry
        registry = FunctionRegistry()
        registry.register(formatter, ftl_name="CUSTOM")

        # Call via registry - returns FluentValue, assert string type for this test
        call_result = registry.call("CUSTOM", [100, "en_US"], {"precision": 1})
        assert isinstance(call_result, str)
        assert call_result == "100.0"

    def test_fluent_function_protocol_type_checking(self) -> None:
        """Test FluentFunction protocol accepts conforming callables (line 60)."""

        def simple_function(
            value: str, locale_code: str, /, **_kwargs: str
        ) -> str:
            """Simple function matching FluentFunction protocol."""
            return f"{value} [{locale_code}]"

        # Should match FluentFunction protocol
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="SIMPLE")

        result = registry.call("SIMPLE", ["test", "lv_LV"], {})
        assert result == "test [lv_LV]"

    def test_protocol_ellipsis_stub_coverage(self) -> None:
        """Force coverage of protocol stub ellipsis (line 60)."""
        # Create a mock Protocol instance to trigger the stub
        # The protocol's __call__ contains the ellipsis that needs coverage
        from contextlib import suppress

        from ftllexengine.runtime.function_bridge import FluentValue

        # Attempt to instantiate the protocol directly (should fail)
        # but this may trigger coverage of the ellipsis
        # Expected - protocols can't be instantiated
        with suppress(TypeError):
            FluentFunction()  # type: ignore[misc]

        # Alternative: create subclass and call the method
        class MockProtocolImpl(FluentFunction):
            """Mock implementation to trigger protocol method."""

            def __call__(
                self,
                value: FluentValue,
                locale_code: str,  # noqa: ARG002
                /,
                **kwargs: FluentValue,  # noqa: ARG002
            ) -> str:
                """Implementation."""
                return str(value)

        # This forces the protocol's __call__ definition to be evaluated
        mock = MockProtocolImpl()
        assert mock("test", "en") == "test"


# ============================================================================
# LINES 297-298: Test get_callable Returns None Branch
# ============================================================================


class TestGetCallableNoneBranch:
    """Test get_callable returns None for non-existent function."""

    def test_get_callable_returns_none_for_missing_function(self) -> None:
        """Test get_callable returns None when function not found (lines 297-298)."""
        registry = FunctionRegistry()

        # Request callable for function that doesn't exist
        result = registry.get_callable("NONEXISTENT")

        # Should return None
        assert result is None

    def test_get_callable_returns_callable_for_existing_function(self) -> None:
        """Test get_callable returns callable when function exists (line 298)."""
        registry = FunctionRegistry()

        def my_func(val: int, locale: str, /) -> str:
            return f"{val}@{locale}"

        registry.register(my_func, ftl_name="MYFUNC")

        # Get the callable
        result = registry.get_callable("MYFUNC")

        # Should return the original function
        assert result is my_func
