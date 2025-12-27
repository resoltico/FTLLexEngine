"""Final coverage tests for runtime/function_bridge.py.

Targets specific uncovered lines to achieve 100% coverage:
- Lines 160-164: TypeError when registering on frozen registry
- Lines 188-193: ValueError on parameter name collision
- Line 285: freeze() method setting _frozen = True
- Line 294: frozen property getter

Python 3.13+.
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
