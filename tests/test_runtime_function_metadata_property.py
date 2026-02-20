"""Property-based tests for function_metadata module.

Tests metadata system for built-in Fluent functions.
"""

import pytest
from hypothesis import event, given
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
        event(f"category={category.value}")
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
        event(f"category={category.value}")
        locale = "locale" if requires_locale else "no_locale"
        event(f"outcome={locale}")
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
        event(f"func_name={func_name}")
        assert requires_locale_injection(func_name) is True

    @given(st.text().filter(lambda x: x not in BUILTIN_FUNCTIONS))
    def test_unknown_functions_dont_require_locale(self, func_name: str) -> None:
        """Property: Unknown functions don't require locale injection."""
        event(f"name_len={len(func_name)}")
        assert requires_locale_injection(func_name) is False

    def test_empty_string_doesnt_require_locale(self) -> None:
        """Edge case: Empty string doesn't require locale."""
        assert requires_locale_injection("") is False

    @given(st.sampled_from(list(BUILTIN_FUNCTIONS.keys())))
    def test_requires_locale_idempotent(self, func_name: str) -> None:
        """Property: requires_locale_injection is idempotent."""
        event(f"func_name={func_name}")
        first = requires_locale_injection(func_name)
        second = requires_locale_injection(func_name)
        assert first == second


class TestIsBuiltinFunction:
    """Property-based tests for is_builtin_function function."""

    @given(st.sampled_from(["NUMBER", "DATETIME", "CURRENCY"]))
    def test_builtin_functions_recognized(self, func_name: str) -> None:
        """Property: All built-in function names are recognized."""
        event(f"func_name={func_name}")
        assert is_builtin_function(func_name) is True

    @given(st.text().filter(lambda x: x not in BUILTIN_FUNCTIONS))
    def test_non_builtin_functions_not_recognized(self, func_name: str) -> None:
        """Property: Non-built-in function names are not recognized."""
        event(f"name_len={len(func_name)}")
        assert is_builtin_function(func_name) is False

    def test_empty_string_not_builtin(self) -> None:
        """Edge case: Empty string is not a built-in function."""
        assert is_builtin_function("") is False

    @given(st.sampled_from(list(BUILTIN_FUNCTIONS.keys())))
    def test_is_builtin_idempotent(self, func_name: str) -> None:
        """Property: is_builtin_function is idempotent."""
        event(f"func_name={func_name}")
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
        event(f"name_len={len(func_name)}")
        assert get_python_name(func_name) is None

    def test_empty_string_returns_none(self) -> None:
        """Edge case: Empty string returns None."""
        assert get_python_name("") is None

    @given(st.sampled_from(list(BUILTIN_FUNCTIONS.keys())))
    def test_get_python_name_idempotent(self, func_name: str) -> None:
        """Property: get_python_name is idempotent."""
        event(f"func_name={func_name}")
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

        Implementation uses attribute-based detection.
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
        event(f"func_name={func_name}")
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
        builtin = "builtin" if is_builtin else "custom"
        event(f"outcome={builtin}")

        # If it's a built-in, must have Python name
        if is_builtin:
            assert python_name is not None
        # If it's not a built-in, Python name must be None
        else:
            assert python_name is None


class TestFunctionMetadataReturnTypes:
    """Property tests for return type invariants."""

    @given(func_name=st.text(min_size=1, max_size=50))
    def test_requires_locale_injection_is_boolean(
        self, func_name: str
    ) -> None:
        """requires_locale_injection always returns boolean."""
        result = requires_locale_injection(func_name)
        builtin = "builtin" if result else "custom"
        event(f"outcome={builtin}")
        assert isinstance(result, bool)

    @given(func_name=st.text(min_size=1, max_size=50))
    def test_is_builtin_function_is_boolean(
        self, func_name: str
    ) -> None:
        """is_builtin_function always returns boolean."""
        result = is_builtin_function(func_name)
        builtin = "builtin" if result else "custom"
        event(f"outcome={builtin}")
        assert isinstance(result, bool)

    @given(func_name=st.text(min_size=1, max_size=50))
    def test_get_python_name_returns_str_or_none(
        self, func_name: str
    ) -> None:
        """get_python_name returns str or None."""
        result = get_python_name(func_name)
        has_name = "found" if result else "none"
        event(f"outcome={has_name}")
        assert result is None or isinstance(result, str)

    @given(func_name=st.text(min_size=1, max_size=50))
    def test_builtin_implies_has_python_name(
        self, func_name: str
    ) -> None:
        """If function is built-in, it has a Python name."""
        builtin = "builtin" if is_builtin_function(func_name) else "custom"
        event(f"outcome={builtin}")
        if is_builtin_function(func_name):
            assert get_python_name(func_name) is not None

    @given(func_name=st.text(min_size=1, max_size=50))
    def test_requires_locale_implies_builtin(
        self, func_name: str
    ) -> None:
        """If function requires locale, it must be built-in."""
        needs = requires_locale_injection(func_name)
        event(f"outcome={'locale' if needs else 'no_locale'}")
        if needs:
            assert is_builtin_function(func_name)

    @given(func_name=st.text(min_size=1, max_size=50))
    def test_should_inject_locale_never_crashes(
        self, func_name: str
    ) -> None:
        """should_inject_locale never raises exception."""
        from ftllexengine.runtime.function_bridge import (  # noqa: PLC0415
            FunctionRegistry,
        )

        registry = FunctionRegistry()

        def test_func(value: str) -> str:
            return value

        registry.register(test_func, ftl_name=func_name)
        result = registry.should_inject_locale(func_name)
        event(f"outcome={'inject' if result else 'no_inject'}")
        assert isinstance(result, bool)


class TestShouldInjectLocaleEdgeCases:
    """Edge cases for FunctionRegistry.should_inject_locale."""

    def test_function_not_in_registry(self) -> None:
        """should_inject_locale returns False if not registered."""
        from ftllexengine.runtime.function_bridge import (  # noqa: PLC0415
            FunctionRegistry,
        )

        registry = FunctionRegistry()
        assert registry.should_inject_locale("NUMBER") is False

    def test_custom_function_same_name_as_builtin(self) -> None:
        """Custom function with built-in name does not inject."""
        from ftllexengine.runtime.function_bridge import (  # noqa: PLC0415
            FunctionRegistry,
        )

        registry = FunctionRegistry()

        def custom_number(value: float) -> str:
            return f"CUSTOM:{value}"

        registry.register(custom_number, ftl_name="NUMBER")
        assert registry.should_inject_locale("NUMBER") is False

    def test_explicitly_false_marker(self) -> None:
        """Explicit _ftl_requires_locale=False does not inject."""
        from ftllexengine.runtime.function_bridge import (  # noqa: PLC0415
            _FTL_REQUIRES_LOCALE_ATTR,
            FunctionRegistry,
        )

        registry = FunctionRegistry()

        def test_func(value: str) -> str:
            return value

        setattr(test_func, _FTL_REQUIRES_LOCALE_ATTR, False)
        registry.register(test_func, ftl_name="EXPLICIT_FALSE")
        assert registry.should_inject_locale("EXPLICIT_FALSE") is False

    def test_with_built_in_registry(self) -> None:
        """should_inject_locale with create_default_registry."""
        from ftllexengine.runtime.functions import (  # noqa: PLC0415
            create_default_registry,
        )

        registry = create_default_registry()
        assert registry.should_inject_locale("NUMBER") is True
        assert registry.should_inject_locale("DATETIME") is True
        assert registry.should_inject_locale("CURRENCY") is True
        assert registry.should_inject_locale("NONEXISTENT") is False
