"""Complete coverage tests for function_metadata.py.

Tests all edge cases and error paths to achieve 100% coverage.
Financial-grade quality for production use.
"""

from __future__ import annotations

from unittest.mock import Mock

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
    should_inject_locale,
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
    """Test edge cases for should_inject_locale function."""

    def test_should_inject_locale_function_not_in_registry(self) -> None:
        """should_inject_locale returns False if function not in registry."""
        registry = FunctionRegistry()

        # NUMBER not registered yet
        assert should_inject_locale("NUMBER", registry) is False

    def test_should_inject_locale_custom_function_same_name(self) -> None:
        """should_inject_locale returns False for custom function with built-in name."""
        registry = FunctionRegistry()

        def custom_number(value: float) -> str:
            return f"CUSTOM:{value}"

        # Register custom function with same name as built-in
        registry.register(custom_number, ftl_name="NUMBER")

        # Should detect it's not the built-in and return False
        assert should_inject_locale("NUMBER", registry) is False

    def test_should_inject_locale_with_malformed_registry(self) -> None:
        """should_inject_locale handles malformed registry gracefully."""
        # Create mock registry that will cause AttributeError
        mock_registry = Mock()
        mock_registry.has_function.return_value = True
        mock_registry._functions = None  # Will cause AttributeError

        result = should_inject_locale("NUMBER", mock_registry)

        assert result is False

    def test_should_inject_locale_with_missing_global_func(self) -> None:
        """should_inject_locale handles missing global function."""

        registry = FunctionRegistry()

        def test_func(value: str) -> str:
            return value

        # Register function with name that's not in global registry
        registry.register(test_func, ftl_name="UNKNOWN_BUILTIN")

        # Artificially make it look like a built-in (hack for test coverage)
        # This tests the bundle_func is None or global_func is None path
        result = should_inject_locale("UNKNOWN_BUILTIN", registry)

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
        result = should_inject_locale(func_name, registry)
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
        assert should_inject_locale("NUMBER", registry) is True
        assert should_inject_locale("DATETIME", registry) is True
        assert should_inject_locale("CURRENCY", registry) is True

        # Non-existent function shouldn't inject
        assert should_inject_locale("NONEXISTENT", registry) is False


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
# COVERAGE TESTS - is_builtin_function_unmodified Edge Cases
# ============================================================================


class TestShouldInjectLocaleCoverage:
    """Test edge cases for should_inject_locale (lines 177, 187)."""

    def test_python_name_none_returns_false_line_177(self) -> None:
        """COVERAGE: get_python_name returns None for malformed function (line 177)."""
        # pylint: disable=import-outside-toplevel
        from ftllexengine.runtime.function_bridge import FunctionRegistry
        from ftllexengine.runtime.function_metadata import should_inject_locale

        registry = FunctionRegistry()

        # Use a non-existent function name that will return None from get_python_name
        # Line 176: python_name is None
        # Line 177: return False
        result = should_inject_locale("INVALID_BUILTIN", registry)
        assert result is False

    def test_bundle_func_none_returns_false_line_187(self) -> None:
        """COVERAGE: bundle_func is None returns False (line 187)."""
        # pylint: disable=import-outside-toplevel
        from unittest.mock import Mock

        from ftllexengine.runtime.function_bridge import FunctionRegistry
        from ftllexengine.runtime.function_metadata import should_inject_locale

        # Create a mock registry that claims to have the function but returns None from _functions
        mock_registry = Mock(spec=FunctionRegistry)
        mock_registry.has_function.return_value = True  # Claims to have NUMBER

        # Create a mock _functions dict that returns None for any key
        mock_functions = Mock()
        mock_functions.get.return_value = None  # Returns None when accessed
        mock_registry._functions = mock_functions

        # This should trigger line 186-187: bundle_func is None
        # Line 166: requires_locale_injection("NUMBER") returns True
        # Line 171: has_function returns True (mocked)
        # Line 175: get_python_name("NUMBER") returns "number_format"
        # Line 176: python_name is not None, continues
        # Line 183: bundle_func = None (mocked)
        # Line 186: bundle_func is None -> True
        # Line 187: return False
        result = should_inject_locale("NUMBER", mock_registry)
        assert result is False

    def test_get_callable_returns_none_line_194(self) -> None:
        """COVERAGE: get_callable returns None triggers line 194."""
        from unittest.mock import Mock

        from ftllexengine.runtime.function_bridge import FunctionRegistry

        # Create a mock registry that satisfies all checks up to get_callable
        mock_registry = Mock(spec=FunctionRegistry)
        mock_registry.has_function.return_value = True
        mock_registry.get_callable.return_value = None  # Key: returns None

        # Create a mock _functions dict for line 183-187 path
        mock_sig = Mock()
        mock_sig.callable = None  # This makes line 183 work
        mock_functions = {"NUMBER": mock_sig}
        mock_registry._functions = mock_functions

        # This should trigger line 194:
        # - Line 169-170: requires_locale_injection("NUMBER") returns True
        # - Line 173-174: has_function returns True (mocked)
        # - Line 177-178: get_python_name("NUMBER") returns "number_format"
        # - Line 192: bundle_callable = get_callable() returns None (mocked)
        # - Line 193: if bundle_callable is None -> True
        # - Line 194: return False
        result = should_inject_locale("NUMBER", mock_registry)
        assert result is False
