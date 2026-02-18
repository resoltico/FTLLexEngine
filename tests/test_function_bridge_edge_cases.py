"""Tests for FunctionRegistry frozen state, parameter collision, and freeze/frozen.

Covers TypeError on registration of frozen registry, ValueError on parameter
name collision, freeze() mutation, and frozen property getter.
"""

from __future__ import annotations

import pytest

from ftllexengine.runtime.function_bridge import FunctionRegistry


class TestFrozenRegistryLines160To164:
    """Test lines 160-164: TypeError when registering on frozen registry."""

    def test_register_on_frozen_registry_raises_type_error(self) -> None:
        """Test register() raises TypeError on frozen registry (lines 160-164)."""
        registry = FunctionRegistry()

        # Freeze the registry
        registry.freeze()

        # Try to register a function on frozen registry
        def my_func(value: str, locale_code: str, /) -> str:  # noqa: ARG001
            return value

        # Should raise TypeError with specific message
        with pytest.raises(
            TypeError,
            match=r"Cannot modify frozen registry.*create_default_registry",
        ):
            registry.register(my_func, ftl_name="MYFUNC")


class TestParameterCollisionLines188To193:
    """Test lines 188-193: ValueError on parameter name collision."""

    def test_register_with_parameter_collision_raises_value_error(self) -> None:
        """Test register() raises ValueError on parameter collision (lines 188-193)."""
        registry = FunctionRegistry()

        # Create a function with parameters that will collide after stripping underscores
        # Both `_value` and `value` would map to camelCase `value`
        def colliding_func(
            val: str,
            locale_code: str,  # noqa: ARG001
            /,
            _test_param: int = 0,  # Will strip to `test_param` -> `testParam`
            test_param: int = 0,  # Also maps to `testParam`  # noqa: ARG001
        ) -> str:
            return val

        # Should raise ValueError about parameter collision
        with pytest.raises(ValueError, match=r"Parameter name collision.*testParam"):
            registry.register(colliding_func, ftl_name="COLLIDE")


class TestFreezeMethodLine285:
    """Test line 285: freeze() method."""

    def test_freeze_sets_frozen_flag(self) -> None:
        """Test freeze() sets _frozen = True (line 285)."""
        registry = FunctionRegistry()

        # Initially not frozen
        assert not registry.frozen

        # Freeze it
        registry.freeze()

        # Should now be frozen
        assert registry.frozen

    def test_freeze_prevents_registration(self) -> None:
        """Test freeze() actually prevents further registration."""
        registry = FunctionRegistry()

        # Register a function before freezing
        def func1(value: str, locale_code: str, /) -> str:  # noqa: ARG001
            return value

        registry.register(func1, ftl_name="FUNC1")
        assert "FUNC1" in registry

        # Freeze the registry
        registry.freeze()

        # Try to register another function
        def func2(value: str, locale_code: str, /) -> str:  # noqa: ARG001
            return value

        # Should fail
        with pytest.raises(TypeError):
            registry.register(func2, ftl_name="FUNC2")

        # Original function still there
        assert "FUNC1" in registry
        # New function not added
        assert "FUNC2" not in registry


class TestFrozenPropertyLine294:
    """Test line 294: frozen property getter."""

    def test_frozen_property_returns_false_initially(self) -> None:
        """Test frozen property returns False for new registry (line 294)."""
        registry = FunctionRegistry()

        # Should not be frozen initially
        result = registry.frozen

        assert result is False

    def test_frozen_property_returns_true_after_freeze(self) -> None:
        """Test frozen property returns True after freeze() (line 294)."""
        registry = FunctionRegistry()

        # Freeze it
        registry.freeze()

        # Property should return True
        result = registry.frozen

        assert result is True

    def test_frozen_property_is_readonly(self) -> None:
        """Test frozen property cannot be set directly."""
        registry = FunctionRegistry()

        # Should not be able to set frozen property
        with pytest.raises(AttributeError):
            registry.frozen = True  # type: ignore[misc]


class TestFrozenRegistryCopyIntegration:
    """Integration tests for frozen registry and copy()."""

    def test_copy_of_frozen_registry_is_mutable(self) -> None:
        """Test copy() of frozen registry creates mutable copy."""
        registry = FunctionRegistry()

        # Register and freeze
        def func1(value: str, locale_code: str, /) -> str:  # noqa: ARG001
            return value

        registry.register(func1, ftl_name="FUNC1")
        registry.freeze()

        # Create copy
        copy = registry.copy()

        # Copy should not be frozen
        assert not copy.frozen

        # Should be able to register on copy
        def func2(value: str, locale_code: str, /) -> str:  # noqa: ARG001
            return value

        copy.register(func2, ftl_name="FUNC2")

        # Copy has both functions
        assert "FUNC1" in copy
        assert "FUNC2" in copy

        # Original only has first function
        assert "FUNC1" in registry
        assert "FUNC2" not in registry


class TestFluentFunctionDecoratorWithParentheses:
    """Test lines 134-148: fluent_function decorator WITH parentheses."""

    def test_fluent_function_decorator_with_inject_locale_true(self) -> None:
        """Test @fluent_function(inject_locale=True) decorator path (lines 134-148)."""
        from ftllexengine.runtime.function_bridge import fluent_function  # noqa: PLC0415

        # Use decorator WITH parentheses
        @fluent_function(inject_locale=True)
        def my_format(value: str, locale_code: str, /) -> str:
            return f"{value}_{locale_code}"

        # Verify the function works
        result = my_format("test", "en_US")
        assert result == "test_en_US"

        # Verify the locale injection marker was set
        assert hasattr(my_format, "_ftl_requires_locale")
        assert my_format._ftl_requires_locale is True

    def test_fluent_function_decorator_with_inject_locale_false(self) -> None:
        """Test @fluent_function(inject_locale=False) decorator path."""
        from ftllexengine.runtime.function_bridge import fluent_function  # noqa: PLC0415

        # Use decorator WITH parentheses but inject_locale=False
        @fluent_function(inject_locale=False)
        def my_upper(value: str) -> str:
            return value.upper()

        # Verify the function works
        result = my_upper("test")
        assert result == "TEST"

        # Verify the locale injection marker was NOT set
        assert not getattr(my_upper, "_ftl_requires_locale", False)

    def test_fluent_function_decorator_without_parentheses(self) -> None:
        """Test @fluent_function decorator WITHOUT parentheses (line 147)."""
        from ftllexengine.runtime.function_bridge import fluent_function  # noqa: PLC0415

        # Use decorator WITHOUT parentheses
        @fluent_function
        def my_simple(value: str) -> str:
            return value.lower()

        # Verify the function works
        result = my_simple("TEST")
        assert result == "test"

        # When used without parentheses and without inject_locale, should not set marker
        assert not getattr(my_simple, "_ftl_requires_locale", False)


class TestRegisterWithUninspectableCallable:
    """Test lines 258-264: ValueError when callable has no inspectable signature."""

    def test_register_uninspectable_callable_raises_type_error(self) -> None:
        """Test register() raises TypeError for callables without signatures (lines 258-264)."""
        registry = FunctionRegistry()

        # Create a mock callable that signature() cannot inspect
        class UninspectableCallable:
            def __call__(self, *args: object, **kwargs: object) -> str:  # noqa: ARG002
                return "test"

        # Manually break signature inspection by making it raise ValueError
        from unittest.mock import patch  # noqa: PLC0415

        uninspectable = UninspectableCallable()

        with (
            patch(
                "ftllexengine.runtime.function_bridge.signature",
                side_effect=ValueError("No signature"),
            ),
            pytest.raises(
                TypeError,
                match=r"Cannot register.*no inspectable signature.*param_mapping",
            ),
        ):
            registry.register(uninspectable, ftl_name="UNINSPECTABLE")


class TestShouldInjectLocaleWithMissingFunction:
    """Test lines 575-579: should_inject_locale when function not in registry."""

    def test_should_inject_locale_returns_false_for_missing_function(self) -> None:
        """Test should_inject_locale returns False for non-existent function (lines 575-576)."""
        registry = FunctionRegistry()

        # Function doesn't exist in registry
        result = registry.should_inject_locale("NONEXISTENT")

        # Should return False (not raise)
        assert result is False

    def test_should_inject_locale_returns_false_for_function_without_marker(self) -> None:
        """Test should_inject_locale when function has no marker.

        Returns False when function exists but has no marker (lines 578-579).
        """
        registry = FunctionRegistry()

        # Register a function without locale injection marker
        def my_func(value: str, locale_code: str, /) -> str:  # noqa: ARG001
            return value

        registry.register(my_func, ftl_name="CUSTOM")

        # Function exists, but doesn't have _ftl_requires_locale marker
        result = registry.should_inject_locale("CUSTOM")

        # Should return False (lines 578-579: getattr returns False)
        assert result is False

    def test_should_inject_locale_returns_true_for_function_with_marker(self) -> None:
        """Test should_inject_locale returns True when function has marker set."""
        from ftllexengine.runtime.function_bridge import fluent_function  # noqa: PLC0415

        registry = FunctionRegistry()

        # Register a function with locale injection marker
        @fluent_function(inject_locale=True)
        def my_format(value: str, locale_code: str, /) -> str:
            return f"{value}_{locale_code}"

        registry.register(my_format, ftl_name="MYFORMAT")

        # Function has marker, should return True
        result = registry.should_inject_locale("MYFORMAT")

        assert result is True


class TestGetExpectedPositionalArgs:
    """Test lines 605-608: get_expected_positional_args method."""

    def test_get_expected_positional_args_for_builtin_function(self) -> None:
        """Test get_expected_positional_args returns count for built-in (lines 605-608)."""
        from ftllexengine.runtime.functions import create_default_registry  # noqa: PLC0415

        registry = create_default_registry()

        # NUMBER is a built-in function with 1 positional arg
        result = registry.get_expected_positional_args("NUMBER")

        assert result == 1

    def test_get_expected_positional_args_for_custom_function(self) -> None:
        """Test get_expected_positional_args returns None for custom function."""
        registry = FunctionRegistry()

        # Register a custom function
        def my_func(value: str, locale_code: str, /) -> str:  # noqa: ARG001
            return value

        registry.register(my_func, ftl_name="CUSTOM")

        # Custom function should return None (not in BUILTIN_FUNCTIONS)
        result = registry.get_expected_positional_args("CUSTOM")

        assert result is None


class TestGetBuiltinMetadata:
    """Test lines 626-628: get_builtin_metadata method."""

    def test_get_builtin_metadata_for_builtin_function(self) -> None:
        """Test get_builtin_metadata returns metadata for built-in (lines 626-628)."""
        from ftllexengine.runtime.functions import create_default_registry  # noqa: PLC0415

        registry = create_default_registry()

        # NUMBER is a built-in function
        metadata = registry.get_builtin_metadata("NUMBER")

        # Should return metadata object
        assert metadata is not None
        assert metadata.requires_locale is True

    def test_get_builtin_metadata_for_custom_function(self) -> None:
        """Test get_builtin_metadata returns None for custom function."""
        registry = FunctionRegistry()

        # Register a custom function
        def my_func(value: str, locale_code: str, /) -> str:  # noqa: ARG001
            return value

        registry.register(my_func, ftl_name="CUSTOM")

        # Custom function should return None
        metadata = registry.get_builtin_metadata("CUSTOM")

        assert metadata is None
