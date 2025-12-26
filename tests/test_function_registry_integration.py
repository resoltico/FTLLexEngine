"""Integration tests for FunctionRegistry introspection with built-in functions.

Tests introspection API with real NUMBER, DATETIME, and CURRENCY functions.
Financial-grade quality for production use.
"""

from __future__ import annotations

import pytest

from ftllexengine import FluentBundle
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.functions import create_default_registry

# ============================================================================
# INTEGRATION TESTS - BUILT-IN FUNCTIONS
# ============================================================================


class TestBuiltInFunctionsIntrospection:
    """Test introspection of built-in NUMBER, DATETIME, CURRENCY functions."""

    @pytest.fixture
    def registry(self) -> FunctionRegistry:
        """Create a fresh registry with built-in functions."""
        return create_default_registry()

    def test_built_in_functions_are_registered(self, registry: FunctionRegistry) -> None:
        """Built-in functions are registered in default registry."""
        assert "NUMBER" in registry
        assert "DATETIME" in registry
        assert "CURRENCY" in registry

    def test_list_built_in_functions(self, registry: FunctionRegistry) -> None:
        """list_functions returns all built-in functions."""
        functions = registry.list_functions()

        assert "NUMBER" in functions
        assert "DATETIME" in functions
        assert "CURRENCY" in functions
        assert len(functions) >= 3

    def test_iterate_built_in_functions(self, registry: FunctionRegistry) -> None:
        """Can iterate over built-in functions."""
        collected = []
        for name in registry:
            collected.append(name)

        assert "NUMBER" in collected
        assert "DATETIME" in collected
        assert "CURRENCY" in collected

    def test_len_includes_built_in_functions(self, registry: FunctionRegistry) -> None:
        """len() includes all built-in functions."""
        count = len(registry)

        assert count >= 3

    def test_get_number_function_info(self, registry: FunctionRegistry) -> None:
        """get_function_info returns metadata for NUMBER function."""
        info = registry.get_function_info("NUMBER")

        assert info is not None
        assert info.ftl_name == "NUMBER"
        assert info.python_name == "number_format"
        assert callable(info.callable)
        # param_mapping is now immutable tuple[tuple[str, str], ...]
        assert isinstance(info.param_mapping, tuple)

        # Check parameter mappings (convert to dict for lookup)
        param_dict = dict(info.param_mapping)
        assert "minimumFractionDigits" in param_dict
        assert param_dict["minimumFractionDigits"] == "minimum_fraction_digits"
        assert "maximumFractionDigits" in param_dict
        assert param_dict["maximumFractionDigits"] == "maximum_fraction_digits"
        assert "useGrouping" in param_dict
        assert param_dict["useGrouping"] == "use_grouping"

    def test_get_datetime_function_info(self, registry: FunctionRegistry) -> None:
        """get_function_info returns metadata for DATETIME function."""
        info = registry.get_function_info("DATETIME")

        assert info is not None
        assert info.ftl_name == "DATETIME"
        assert info.python_name == "datetime_format"
        assert callable(info.callable)
        # param_mapping is now immutable tuple[tuple[str, str], ...]
        assert isinstance(info.param_mapping, tuple)

        # Check parameter mappings (convert to dict for lookup)
        param_dict = dict(info.param_mapping)
        assert "dateStyle" in param_dict
        assert param_dict["dateStyle"] == "date_style"
        assert "timeStyle" in param_dict
        assert param_dict["timeStyle"] == "time_style"

    def test_get_currency_function_info(self, registry: FunctionRegistry) -> None:
        """get_function_info returns metadata for CURRENCY function."""
        info = registry.get_function_info("CURRENCY")

        assert info is not None
        assert info.ftl_name == "CURRENCY"
        assert info.python_name == "currency_format"
        assert callable(info.callable)
        # param_mapping is now immutable tuple[tuple[str, str], ...]
        assert isinstance(info.param_mapping, tuple)

        # Check parameter mappings (convert to dict for lookup)
        param_dict = dict(info.param_mapping)
        assert "currency" in param_dict
        assert param_dict["currency"] == "currency"
        assert "currencyDisplay" in param_dict
        assert param_dict["currencyDisplay"] == "currency_display"


# ============================================================================
# INTEGRATION TESTS - BUNDLE FUNCTION REGISTRY
# ============================================================================


class TestBundleFunctionRegistryIntrospection:
    """Test introspection of FluentBundle function registry."""

    def test_bundle_has_built_in_functions(self) -> None:
        """FluentBundle includes built-in functions."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # Access bundle's function registry (internal API for testing)
        assert "NUMBER" in bundle._function_registry  # pylint: disable=protected-access
        assert "DATETIME" in bundle._function_registry  # pylint: disable=protected-access
        assert "CURRENCY" in bundle._function_registry  # pylint: disable=protected-access

    def test_bundle_can_list_functions(self) -> None:
        """Can list functions from bundle's registry."""
        bundle = FluentBundle("en_US", use_isolating=False)

        functions = bundle._function_registry.list_functions()  # pylint: disable=protected-access

        assert "NUMBER" in functions
        assert "DATETIME" in functions
        assert "CURRENCY" in functions

    def test_bundle_can_add_custom_function_and_introspect(self) -> None:
        """Can add custom function to bundle and introspect it."""
        bundle = FluentBundle("en_US", use_isolating=False)

        def CUSTOM(value: str) -> str:  # pylint: disable=invalid-name
            return value.upper()

        bundle.add_function("CUSTOM", CUSTOM)

        # Introspect
        assert "CUSTOM" in bundle._function_registry  # pylint: disable=protected-access
        functions = bundle._function_registry.list_functions()  # pylint: disable=protected-access
        assert "CUSTOM" in functions

        info = bundle._function_registry.get_function_info("CUSTOM")  # pylint: disable=protected-access
        assert info is not None
        assert info.ftl_name == "CUSTOM"


# ============================================================================
# INTEGRATION TESTS - FUNCTION DISCOVERY WORKFLOW
# ============================================================================


class TestFunctionDiscoveryWorkflow:
    """Test real-world function discovery workflows."""

    def test_discover_all_available_functions(self) -> None:
        """Discover all available functions in bundle."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # List all available functions
        available = bundle._function_registry.list_functions()  # pylint: disable=protected-access

        # Should have at least the 3 built-in functions
        assert len(available) >= 3
        assert all(isinstance(name, str) for name in available)

    def test_inspect_function_parameters(self) -> None:
        """Inspect function parameters for documentation."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # Get NUMBER function info
        info = bundle._function_registry.get_function_info("NUMBER")  # pylint: disable=protected-access

        assert info is not None

        # Inspect parameter mappings (convert tuple to dict)
        param_dict = dict(info.param_mapping)

        # Should have all NUMBER parameters
        expected_params = {
            "minimumFractionDigits",
            "maximumFractionDigits",
            "useGrouping",
            "value",
            "localeCode",
        }
        assert expected_params.issubset(set(param_dict.keys()))

    def test_verify_function_exists_before_use(self) -> None:
        """Verify built-in NUMBER function exists and is usable."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # NUMBER is a built-in function - must exist
        assert "NUMBER" in bundle._function_registry  # pylint: disable=protected-access

        # Use it in FTL
        bundle.add_resource("price = { NUMBER($amount, minimumFractionDigits: 2) }")
        result, errors = bundle.format_pattern("price", {"amount": 123.456})
        assert errors == ()
        assert "123" in result

    def test_list_functions_for_auto_documentation(self) -> None:
        """Generate function list for auto-documentation."""
        bundle = FluentBundle("en_US", use_isolating=False)

        functions = {}
        for name in bundle._function_registry:  # pylint: disable=protected-access
            info = bundle._function_registry.get_function_info(name)  # pylint: disable=protected-access
            # All registered functions must have metadata for documentation
            assert info is not None, f"Function {name} has no metadata"
            # Convert immutable tuple to list of keys for documentation
            param_keys = [k for k, _ in info.param_mapping]
            functions[name] = {
                "python_name": info.python_name,
                "parameters": param_keys,
            }

        # Should have documentation for all built-in functions
        assert "NUMBER" in functions
        assert "DATETIME" in functions
        assert "CURRENCY" in functions

        # NUMBER should have expected parameters
        assert "minimumFractionDigits" in functions["NUMBER"]["parameters"]
        assert "maximumFractionDigits" in functions["NUMBER"]["parameters"]


# ============================================================================
# INTEGRATION TESTS - FINANCIAL USE CASES
# ============================================================================


class TestFinancialUseCases:
    """Financial-grade integration tests for function introspection."""

    def test_verify_currency_function_before_formatting(self) -> None:
        """Verify CURRENCY function exists before using in financial app."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # Critical check before processing financial data
        assert "CURRENCY" in bundle._function_registry  # pylint: disable=protected-access

        # Get function info to verify it's the right function
        info = bundle._function_registry.get_function_info("CURRENCY")  # pylint: disable=protected-access
        assert info is not None
        assert info.python_name == "currency_format"

        # Safe to use
        bundle.add_resource('price = { CURRENCY($amount, currency: "EUR") }')
        result, errors = bundle.format_pattern("price", {"amount": 1234.56})
        assert errors == ()
        assert "1" in result
        assert "234" in result

    def test_verify_number_function_for_vat_calculations(self) -> None:
        """Verify NUMBER function for VAT calculations."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # Critical for VAT display
        assert "NUMBER" in bundle._function_registry  # pylint: disable=protected-access

        # Get function info
        info = bundle._function_registry.get_function_info("NUMBER")  # pylint: disable=protected-access
        assert info is not None

        # Verify has minimum_fraction_digits for financial precision (convert tuple to dict)
        param_dict = dict(info.param_mapping)
        assert "minimumFractionDigits" in param_dict

        # Use in VAT calculation
        bundle.add_resource("vat = VAT: { NUMBER($amount, minimumFractionDigits: 2) }")
        result, errors = bundle.format_pattern("vat", {"amount": 23.45})
        assert errors == ()
        assert "23.45" in result

    def test_custom_financial_function_registration(self) -> None:
        """Register and verify custom financial function."""
        bundle = FluentBundle("lv_LV", use_isolating=False)

        def LATVIAN_VAT(amount: float, rate: float = 0.21) -> str:  # pylint: disable=invalid-name
            """Calculate Latvian VAT (21%)."""
            vat = amount * rate
            return f"{vat:.2f}"

        # Register custom function
        bundle.add_function("LATVIAN_VAT", LATVIAN_VAT)

        # Verify registration
        assert "LATVIAN_VAT" in bundle._function_registry  # pylint: disable=protected-access

        # Get function info
        info = bundle._function_registry.get_function_info("LATVIAN_VAT")  # pylint: disable=protected-access
        assert info is not None
        assert info.python_name == "LATVIAN_VAT"

        # Use in FTL
        bundle.add_resource("vat = VAT: €{ LATVIAN_VAT($amount) }")
        result, errors = bundle.format_pattern("vat", {"amount": 100.0})
        assert errors == ()
        assert "21.00" in result

    def test_iterate_all_functions_for_validation(self) -> None:
        """Iterate all functions for validation in financial app."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # Validation: ensure all expected functions are present
        required_functions = {"NUMBER", "CURRENCY", "DATETIME"}

        available_functions = set(bundle._function_registry.list_functions())  # pylint: disable=protected-access

        # All required functions must be present
        assert required_functions.issubset(available_functions)

        # Verify each required function has valid metadata
        for func_name in required_functions:
            info = bundle._function_registry.get_function_info(func_name)  # pylint: disable=protected-access
            assert info is not None
            assert info.ftl_name == func_name
            assert callable(info.callable)
            # param_mapping is now immutable tuple[tuple[str, str], ...]
            assert isinstance(info.param_mapping, tuple)


# ============================================================================
# INTEGRATION TESTS - EDGE CASES
# ============================================================================


class TestIntrospectionEdgeCases:
    """Edge cases for introspection in real-world scenarios."""

    def test_empty_custom_registry_introspection(self) -> None:
        """Introspect bundle with only built-in functions."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # Should have exactly the built-in functions
        functions = bundle._function_registry.list_functions()  # pylint: disable=protected-access
        assert len(functions) == 3
        assert set(functions) == {"NUMBER", "DATETIME", "CURRENCY"}

    def test_multiple_custom_functions_introspection(self) -> None:
        """Introspect bundle with multiple custom functions."""
        bundle = FluentBundle("en_US", use_isolating=False)

        def FUNC1(x: str) -> str:  # pylint: disable=invalid-name
            return x.upper()

        def FUNC2(x: str) -> str:  # pylint: disable=invalid-name
            return x.lower()

        def FUNC3(x: str) -> str:  # pylint: disable=invalid-name
            return x.title()

        bundle.add_function("FUNC1", FUNC1)
        bundle.add_function("FUNC2", FUNC2)
        bundle.add_function("FUNC3", FUNC3)

        # Should have built-in + custom functions
        functions = bundle._function_registry.list_functions()  # pylint: disable=protected-access
        assert len(functions) == 6
        assert set(functions) == {"NUMBER", "DATETIME", "CURRENCY", "FUNC1", "FUNC2", "FUNC3"}

        # Can introspect all
        for func_name in functions:
            info = bundle._function_registry.get_function_info(func_name)  # pylint: disable=protected-access
            assert info is not None

    def test_overwrite_built_in_function_introspection(self) -> None:
        """Overwriting built-in function updates introspection."""
        bundle = FluentBundle("en_US", use_isolating=False)

        def CUSTOM_NUMBER(value: int) -> str:  # pylint: disable=invalid-name
            """Custom number formatter."""
            return f"CUSTOM:{value}"

        # Overwrite NUMBER
        bundle.add_function("NUMBER", CUSTOM_NUMBER)

        # Introspection shows custom version
        info = bundle._function_registry.get_function_info("NUMBER")  # pylint: disable=protected-access
        assert info is not None
        assert info.python_name == "CUSTOM_NUMBER"

        # Still only 3 functions (no duplication)
        functions = bundle._function_registry.list_functions()  # pylint: disable=protected-access
        assert len(functions) == 3
