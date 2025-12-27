"""Complete coverage tests for function_metadata.py.

Tests all edge cases and error paths to achieve 100% coverage.
Financial-grade quality for production use.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.function_metadata import (
    BUILTIN_FUNCTIONS,
    FunctionCategory,
    FunctionMetadata,
    get_python_name,
    is_builtin_function,
    requires_locale_injection,
)

# ============================================================================
# UNIT TESTS - BASIC FUNCTIONALITY
# ============================================================================


class TestFunctionMetadataBasic:
    """Test basic function metadata operations."""

    def test_requires_locale_injection_for_number(self) -> None:
        """NUMBER requires locale injection."""
        assert requires_locale_injection("NUMBER") is True

    def test_requires_locale_injection_for_datetime(self) -> None:
        """DATETIME requires locale injection."""
        assert requires_locale_injection("DATETIME") is True

    def test_requires_locale_injection_for_currency(self) -> None:
        """CURRENCY requires locale injection."""
        assert requires_locale_injection("CURRENCY") is True

    def test_requires_locale_injection_for_custom(self) -> None:
        """Custom functions don't require locale injection."""
        assert requires_locale_injection("CUSTOM") is False

    def test_is_builtin_function_number(self) -> None:
        """NUMBER is a built-in function."""
        assert is_builtin_function("NUMBER") is True

    def test_is_builtin_function_custom(self) -> None:
        """CUSTOM is not a built-in function."""
        assert is_builtin_function("CUSTOM") is False

    def test_get_python_name_for_number(self) -> None:
        """Get Python name for NUMBER."""
        assert get_python_name("NUMBER") == "number_format"

    def test_get_python_name_for_datetime(self) -> None:
        """Get Python name for DATETIME."""
        assert get_python_name("DATETIME") == "datetime_format"

    def test_get_python_name_for_currency(self) -> None:
        """Get Python name for CURRENCY."""
        assert get_python_name("CURRENCY") == "currency_format"

    def test_get_python_name_for_custom(self) -> None:
        """Get Python name for custom function returns None."""
        assert get_python_name("CUSTOM") is None


# ============================================================================
# EDGE CASE TESTS - SHOULD_INJECT_LOCALE
# ============================================================================


class TestShouldInjectLocaleEdgeCases:
    """Test edge cases for FunctionRegistry.should_inject_locale method."""

    def test_should_inject_locale_function_not_in_registry(self) -> None:
        """should_inject_locale returns False if function not in registry."""
        registry = FunctionRegistry()

        # NUMBER not registered yet
        assert registry.should_inject_locale("NUMBER") is False

    def test_should_inject_locale_custom_function_same_name(self) -> None:
        """should_inject_locale returns False for custom function with built-in name."""
        registry = FunctionRegistry()

        def custom_number(value: float) -> str:
            return f"CUSTOM:{value}"

        # Register custom function with same name as built-in
        registry.register(custom_number, ftl_name="NUMBER")

        # Should detect it's not the built-in and return False
        assert registry.should_inject_locale("NUMBER") is False

    def test_should_inject_locale_with_marked_custom_function(self) -> None:
        """should_inject_locale returns True for custom function with locale marker."""
        from ftllexengine.runtime.function_bridge import fluent_function

        registry = FunctionRegistry()

        @fluent_function(inject_locale=True)
        def custom_locale(value: str, locale_code: str = "en") -> str:
            return f"{value}:{locale_code}"

        registry.register(custom_locale, ftl_name="CUSTOM_LOCALE")

        # Should return True because function is marked with _ftl_requires_locale
        assert registry.should_inject_locale("CUSTOM_LOCALE") is True

    def test_should_inject_locale_with_missing_function(self) -> None:
        """should_inject_locale handles missing function."""
        registry = FunctionRegistry()

        def test_func(value: str) -> str:
            return value

        # Register function with a name
        registry.register(test_func, ftl_name="CUSTOM")

        # Query for non-existent function
        result = registry.should_inject_locale("UNKNOWN")

        assert result is False


# ============================================================================
# HYPOTHESIS PROPERTY TESTS
# ============================================================================


class TestFunctionMetadataProperties:
    """Property-based tests for function metadata invariants."""

    @given(func_name=st.text(min_size=1, max_size=50))
    def test_requires_locale_injection_is_boolean(self, func_name: str) -> None:
        """requires_locale_injection always returns boolean."""
        result = requires_locale_injection(func_name)
        assert isinstance(result, bool)

    @given(func_name=st.text(min_size=1, max_size=50))
    def test_is_builtin_function_is_boolean(self, func_name: str) -> None:
        """is_builtin_function always returns boolean."""
        result = is_builtin_function(func_name)
        assert isinstance(result, bool)

    @given(func_name=st.text(min_size=1, max_size=50))
    def test_get_python_name_returns_str_or_none(self, func_name: str) -> None:
        """get_python_name returns str or None."""
        result = get_python_name(func_name)
        assert result is None or isinstance(result, str)

    @given(func_name=st.text(min_size=1, max_size=50))
    def test_builtin_implies_has_python_name(self, func_name: str) -> None:
        """If function is built-in, it has a Python name."""
        if is_builtin_function(func_name):
            assert get_python_name(func_name) is not None

    @given(func_name=st.text(min_size=1, max_size=50))
    def test_requires_locale_implies_builtin(self, func_name: str) -> None:
        """If function requires locale, it must be built-in."""
        if requires_locale_injection(func_name):
            assert is_builtin_function(func_name)

    @given(func_name=st.text(min_size=1, max_size=50))
    def test_should_inject_locale_never_crashes(self, func_name: str) -> None:
        """should_inject_locale never raises exception."""
        registry = FunctionRegistry()

        def test_func(value: str) -> str:
            return value

        registry.register(test_func, ftl_name=func_name)

        # Should never crash, always return boolean
        result = registry.should_inject_locale(func_name)
        assert isinstance(result, bool)


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestFunctionMetadataIntegration:
    """Integration tests with real function registry."""

    def test_all_builtin_functions_in_metadata(self) -> None:
        """All built-in functions have metadata."""
        expected_builtins = {"NUMBER", "DATETIME", "CURRENCY"}

        for func_name in expected_builtins:
            assert is_builtin_function(func_name)
            assert requires_locale_injection(func_name)
            assert get_python_name(func_name) is not None

    def test_builtin_functions_metadata_consistency(self) -> None:
        """Metadata is consistent across all functions."""
        for func_name, metadata in BUILTIN_FUNCTIONS.items():
            assert metadata.ftl_name == func_name
            assert metadata.python_name.endswith("_format")
            assert metadata.requires_locale is True
            assert metadata.category == FunctionCategory.FORMATTING

    def test_should_inject_locale_with_built_in_registry(self) -> None:
        """should_inject_locale works with built-in registry."""
        from ftllexengine.runtime.functions import create_default_registry

        registry = create_default_registry()

        # Built-in functions should inject locale
        assert registry.should_inject_locale("NUMBER") is True
        assert registry.should_inject_locale("DATETIME") is True
        assert registry.should_inject_locale("CURRENCY") is True

        # Non-existent function shouldn't inject
        assert registry.should_inject_locale("NONEXISTENT") is False


# ============================================================================
# METADATA STRUCTURE TESTS
# ============================================================================


class TestFunctionMetadataStructure:
    """Test FunctionMetadata dataclass structure."""

    def test_function_metadata_immutable(self) -> None:
        """FunctionMetadata is immutable."""
        metadata = FunctionMetadata(
            python_name="test_func",
            ftl_name="TEST",
            requires_locale=True,
            category=FunctionCategory.FORMATTING,
        )

        with pytest.raises(AttributeError):
            metadata.python_name = "new_name"  # type: ignore[misc]

    def test_function_metadata_default_category(self) -> None:
        """FunctionMetadata has default category."""
        metadata = FunctionMetadata(
            python_name="test_func",
            ftl_name="TEST",
            requires_locale=False,
        )

        assert metadata.category == FunctionCategory.FORMATTING

    def test_builtin_functions_dict_structure(self) -> None:
        """BUILTIN_FUNCTIONS dict has correct structure."""
        assert isinstance(BUILTIN_FUNCTIONS, dict)
        assert len(BUILTIN_FUNCTIONS) == 3

        for ftl_name, metadata in BUILTIN_FUNCTIONS.items():
            assert isinstance(ftl_name, str)
            assert isinstance(metadata, FunctionMetadata)
            assert ftl_name == metadata.ftl_name


# ============================================================================
# COVERAGE TESTS - FunctionRegistry.should_inject_locale Edge Cases
# ============================================================================


class TestShouldInjectLocaleCoverage:
    """Test edge cases for FunctionRegistry.should_inject_locale method."""

    def test_should_inject_locale_non_existent_function(self) -> None:
        """should_inject_locale returns False for non-existent function."""
        registry = FunctionRegistry()

        # Function not registered
        result = registry.should_inject_locale("INVALID_BUILTIN")
        assert result is False

    def test_should_inject_locale_unmarked_function(self) -> None:
        """should_inject_locale returns False for function without locale marker."""
        registry = FunctionRegistry()

        def simple_func(value: str) -> str:
            return value.upper()

        registry.register(simple_func, ftl_name="SIMPLE")

        # Function has no _ftl_requires_locale attribute
        result = registry.should_inject_locale("SIMPLE")
        assert result is False

    def test_should_inject_locale_explicitly_false(self) -> None:
        """should_inject_locale returns False when marker is explicitly False."""
        from ftllexengine.runtime.function_bridge import (
            _FTL_REQUIRES_LOCALE_ATTR,
        )

        registry = FunctionRegistry()

        def test_func(value: str) -> str:
            return value

        # Explicitly set marker to False
        setattr(test_func, _FTL_REQUIRES_LOCALE_ATTR, False)
        registry.register(test_func, ftl_name="EXPLICIT_FALSE")

        result = registry.should_inject_locale("EXPLICIT_FALSE")
        assert result is False
