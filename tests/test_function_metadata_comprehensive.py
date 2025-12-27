"""Comprehensive property-based tests for function_metadata module.

Tests metadata system for built-in Fluent functions.

"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ftllexengine import FluentBundle
from ftllexengine.runtime.function_metadata import (
    BUILTIN_FUNCTIONS,
    FunctionCategory,
    FunctionMetadata,
    get_python_name,
    is_builtin_function,
    requires_locale_injection,
)


class TestFunctionCategoryEnum:
    """Property-based tests for FunctionCategory enum."""

    def test_all_members_have_string_values(self) -> None:
        """Property: All FunctionCategory members have non-empty string values."""
        for member in FunctionCategory:
            assert isinstance(member.value, str)
            assert len(member.value) > 0

    def test_str_returns_value(self) -> None:
        """Property: __str__ returns the enum value for all members."""
        for member in FunctionCategory:
            assert str(member) == member.value

    def test_function_category_members_exist(self) -> None:
        """Verify all expected FunctionCategory members exist."""
        assert FunctionCategory.FORMATTING.value == "formatting"
        assert FunctionCategory.TEXT.value == "text"
        assert FunctionCategory.CUSTOM.value == "custom"

    @given(st.sampled_from(FunctionCategory))
    def test_function_category_str_idempotent(self, category: FunctionCategory) -> None:
        """Property: str(category) is idempotent."""
        first = str(category)
        second = str(category)
        assert first == second


class TestFunctionMetadataDataclass:
    """Property-based tests for FunctionMetadata dataclass."""

    def test_function_metadata_frozen(self) -> None:
        """Property: FunctionMetadata instances are immutable (frozen)."""
        metadata = FunctionMetadata(
            python_name="test_func",
            ftl_name="TEST",
            requires_locale=True,
            category=FunctionCategory.CUSTOM,
        )

        with pytest.raises((AttributeError, TypeError)):
            metadata.python_name = "changed"  # type: ignore[misc]

    @given(
        st.text(min_size=1),
        st.text(min_size=1),
        st.booleans(),
        st.sampled_from(FunctionCategory),
    )
    def test_function_metadata_construction(
        self,
        python_name: str,
        ftl_name: str,
        requires_locale: bool,
        category: FunctionCategory,
    ) -> None:
        """Property: FunctionMetadata can be constructed with any valid inputs."""
        metadata = FunctionMetadata(
            python_name=python_name,
            ftl_name=ftl_name,
            requires_locale=requires_locale,
            category=category,
        )

        assert metadata.python_name == python_name
        assert metadata.ftl_name == ftl_name
        assert metadata.requires_locale == requires_locale
        assert metadata.category == category

    def test_function_metadata_default_category(self) -> None:
        """Property: FunctionMetadata has default category FORMATTING."""
        metadata = FunctionMetadata(
            python_name="test",
            ftl_name="TEST",
            requires_locale=True,
        )
        assert metadata.category == FunctionCategory.FORMATTING


class TestBuiltinFunctionsRegistry:
    """Tests for BUILTIN_FUNCTIONS registry."""

    def test_builtin_functions_contains_number(self) -> None:
        """Verify NUMBER function is in built-in registry."""
        assert "NUMBER" in BUILTIN_FUNCTIONS
        assert BUILTIN_FUNCTIONS["NUMBER"].python_name == "number_format"
        assert BUILTIN_FUNCTIONS["NUMBER"].requires_locale is True

    def test_builtin_functions_contains_datetime(self) -> None:
        """Verify DATETIME function is in built-in registry."""
        assert "DATETIME" in BUILTIN_FUNCTIONS
        assert BUILTIN_FUNCTIONS["DATETIME"].python_name == "datetime_format"
        assert BUILTIN_FUNCTIONS["DATETIME"].requires_locale is True

    def test_builtin_functions_contains_currency(self) -> None:
        """Verify CURRENCY function is in built-in registry."""
        assert "CURRENCY" in BUILTIN_FUNCTIONS
        assert BUILTIN_FUNCTIONS["CURRENCY"].python_name == "currency_format"
        assert BUILTIN_FUNCTIONS["CURRENCY"].requires_locale is True

    def test_builtin_functions_count(self) -> None:
        """Property: BUILTIN_FUNCTIONS has exactly 3 entries."""
        assert len(BUILTIN_FUNCTIONS) == 3

    def test_all_builtins_require_locale(self) -> None:
        """Property: All current built-in functions require locale injection."""
        for metadata in BUILTIN_FUNCTIONS.values():
            assert metadata.requires_locale is True

    def test_all_builtins_are_formatting_category(self) -> None:
        """Property: All current built-in functions are in FORMATTING category."""
        for metadata in BUILTIN_FUNCTIONS.values():
            assert metadata.category == FunctionCategory.FORMATTING


class TestRequiresLocaleInjection:
    """Property-based tests for requires_locale_injection function."""

    @given(st.sampled_from(["NUMBER", "DATETIME", "CURRENCY"]))
    def test_builtin_functions_require_locale(self, func_name: str) -> None:
        """Property: All built-in functions require locale injection."""
        assert requires_locale_injection(func_name) is True

    @given(st.text().filter(lambda x: x not in BUILTIN_FUNCTIONS))
    def test_unknown_functions_dont_require_locale(self, func_name: str) -> None:
        """Property: Unknown functions don't require locale injection."""
        assert requires_locale_injection(func_name) is False

    def test_empty_string_doesnt_require_locale(self) -> None:
        """Edge case: Empty string doesn't require locale."""
        assert requires_locale_injection("") is False

    @given(st.sampled_from(list(BUILTIN_FUNCTIONS.keys())))
    def test_requires_locale_idempotent(self, func_name: str) -> None:
        """Property: requires_locale_injection is idempotent."""
        first = requires_locale_injection(func_name)
        second = requires_locale_injection(func_name)
        assert first == second


class TestIsBuiltinFunction:
    """Property-based tests for is_builtin_function function."""

    @given(st.sampled_from(["NUMBER", "DATETIME", "CURRENCY"]))
    def test_builtin_functions_recognized(self, func_name: str) -> None:
        """Property: All built-in function names are recognized."""
        assert is_builtin_function(func_name) is True

    @given(st.text().filter(lambda x: x not in BUILTIN_FUNCTIONS))
    def test_non_builtin_functions_not_recognized(self, func_name: str) -> None:
        """Property: Non-built-in function names are not recognized."""
        assert is_builtin_function(func_name) is False

    def test_empty_string_not_builtin(self) -> None:
        """Edge case: Empty string is not a built-in function."""
        assert is_builtin_function("") is False

    @given(st.sampled_from(list(BUILTIN_FUNCTIONS.keys())))
    def test_is_builtin_idempotent(self, func_name: str) -> None:
        """Property: is_builtin_function is idempotent."""
        first = is_builtin_function(func_name)
        second = is_builtin_function(func_name)
        assert first == second


class TestGetPythonName:
    """Property-based tests for get_python_name function."""

    def test_number_python_name(self) -> None:
        """Verify NUMBER maps to correct Python name."""
        assert get_python_name("NUMBER") == "number_format"

    def test_datetime_python_name(self) -> None:
        """Verify DATETIME maps to correct Python name."""
        assert get_python_name("DATETIME") == "datetime_format"

    def test_currency_python_name(self) -> None:
        """Verify CURRENCY maps to correct Python name."""
        assert get_python_name("CURRENCY") == "currency_format"

    @given(st.text().filter(lambda x: x not in BUILTIN_FUNCTIONS))
    def test_unknown_function_returns_none(self, func_name: str) -> None:
        """Property: Unknown functions return None."""
        assert get_python_name(func_name) is None

    def test_empty_string_returns_none(self) -> None:
        """Edge case: Empty string returns None."""
        assert get_python_name("") is None

    @given(st.sampled_from(list(BUILTIN_FUNCTIONS.keys())))
    def test_get_python_name_idempotent(self, func_name: str) -> None:
        """Property: get_python_name is idempotent."""
        first = get_python_name(func_name)
        second = get_python_name(func_name)
        assert first == second


class TestShouldInjectLocale:
    """Property-based tests for FunctionRegistry.should_inject_locale method."""

    def test_builtin_number_should_inject(self) -> None:
        """Verify built-in NUMBER function should get locale injection."""
        bundle = FluentBundle("en", use_isolating=False)
        assert bundle._function_registry.should_inject_locale("NUMBER") is True

    def test_builtin_datetime_should_inject(self) -> None:
        """Verify built-in DATETIME function should get locale injection."""
        bundle = FluentBundle("en", use_isolating=False)
        assert bundle._function_registry.should_inject_locale("DATETIME") is True

    def test_builtin_currency_should_inject(self) -> None:
        """Verify built-in CURRENCY function should get locale injection."""
        bundle = FluentBundle("en", use_isolating=False)
        assert bundle._function_registry.should_inject_locale("CURRENCY") is True

    def test_custom_function_no_inject(self) -> None:
        """Verify custom function doesn't get locale injection."""
        bundle = FluentBundle("en", use_isolating=False)

        def custom_upper(text: str) -> str:
            return text.upper()

        bundle.add_function("UPPER", custom_upper)
        assert bundle._function_registry.should_inject_locale("UPPER") is False

    def test_replaced_builtin_no_inject(self) -> None:
        """Verify replaced built-in function doesn't get locale injection."""
        bundle = FluentBundle("en", use_isolating=False)

        def custom_number(value: float | int) -> str:
            return f"CUSTOM:{value}"

        # Replace built-in NUMBER with custom implementation
        bundle.add_function("NUMBER", custom_number)

        # Should NOT inject locale because it's not the original built-in
        assert bundle._function_registry.should_inject_locale("NUMBER") is False

    def test_nonexistent_function_no_inject(self) -> None:
        """Verify non-existent function doesn't get locale injection."""
        bundle = FluentBundle("en", use_isolating=False)
        assert bundle._function_registry.should_inject_locale("NONEXISTENT") is False

    def test_is_builtin_function_custom_function(self) -> None:
        """Verify is_builtin_function returns False for custom function."""
        # Custom function name not in BUILTIN_FUNCTIONS
        assert is_builtin_function("CUSTOM") is False

    def test_custom_function_with_locale_marker(self) -> None:
        """Test custom function marked with _ftl_requires_locale attribute.

        v0.36.0 changed implementation to use attribute-based detection.
        Functions marked with _ftl_requires_locale = True get locale injection.
        """
        from ftllexengine.runtime.function_bridge import fluent_function  # noqa: PLC0415

        bundle = FluentBundle("en", use_isolating=False)

        @fluent_function(inject_locale=True)
        def custom_locale_func(value: str, locale_code: str = "en") -> str:
            return f"{value}:{locale_code}"

        bundle.add_function("CUSTOM_LOCALE", custom_locale_func)

        # Should inject locale because it has the marker attribute
        assert bundle._function_registry.should_inject_locale("CUSTOM_LOCALE") is True

    @given(st.sampled_from(["NUMBER", "DATETIME", "CURRENCY"]))
    def test_should_inject_idempotent(self, func_name: str) -> None:
        """Property: should_inject_locale is idempotent for built-ins."""
        bundle = FluentBundle("en", use_isolating=False)
        first = bundle._function_registry.should_inject_locale(func_name)
        second = bundle._function_registry.should_inject_locale(func_name)
        assert first == second

    def test_empty_string_no_inject(self) -> None:
        """Edge case: Empty string doesn't get locale injection."""
        bundle = FluentBundle("en", use_isolating=False)
        assert bundle._function_registry.should_inject_locale("") is False


class TestFunctionMetadataInvariants:
    """Test mathematical properties and invariants."""

    def test_requires_locale_implies_is_builtin(self) -> None:
        """Property: If requires_locale_injection is True, then is_builtin_function is True."""
        for func_name in ["NUMBER", "DATETIME", "CURRENCY"]:
            if requires_locale_injection(func_name):
                assert is_builtin_function(func_name)

    def test_is_builtin_has_python_name(self) -> None:
        """Property: If is_builtin_function is True, then get_python_name returns non-None."""
        for func_name in BUILTIN_FUNCTIONS:
            if is_builtin_function(func_name):
                assert get_python_name(func_name) is not None

    def test_python_name_not_none_implies_is_builtin(self) -> None:
        """Property: If get_python_name returns non-None, then is_builtin_function is True."""
        for func_name in ["NUMBER", "DATETIME", "CURRENCY"]:
            if get_python_name(func_name) is not None:
                assert is_builtin_function(func_name)

    @given(st.text())
    def test_metamorphic_is_builtin_get_python_name(self, func_name: str) -> None:
        """Metamorphic: is_builtin and get_python_name consistency."""
        is_builtin = is_builtin_function(func_name)
        python_name = get_python_name(func_name)

        # If it's a built-in, must have Python name
        if is_builtin:
            assert python_name is not None
        # If it's not a built-in, Python name must be None
        else:
            assert python_name is None
