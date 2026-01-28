"""Tests for resolver _call_function_safe error handling.

Validates that function call error handling is consistent between locale-injected
and non-locale call paths after DRY refactoring into _call_function_safe.

Property: FrozenFluentError propagates directly; all other exceptions are
caught, logged, and converted to fallback error strings.
"""

from __future__ import annotations

from ftllexengine.runtime.bundle import FluentBundle


class TestCallFunctionSafeLocaleInjected:
    """Error handling for locale-injected function calls."""

    def test_unknown_function_produces_fallback(self) -> None:
        """Calling an unregistered function produces fallback error string."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("msg = { NONEXISTENT($x) }")
        result, errors = bundle.format_pattern("msg", {"x": 42})
        assert "NONEXISTENT" in result
        assert len(errors) > 0

    def test_builtin_with_wrong_arity_produces_error(self) -> None:
        """Built-in function with wrong arity produces structured error."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("msg = { NUMBER() }")
        _result, errors = bundle.format_pattern("msg")
        assert len(errors) > 0


class TestCallFunctionSafeCustomFunction:
    """Error handling for custom (non-locale) function calls."""

    def test_custom_function_exception_caught(self) -> None:
        """Custom function raising exception produces fallback, not crash."""

        def bad_func(_value: object) -> str:
            msg = "intentional error"
            raise ValueError(msg)

        bundle = FluentBundle("en-US")
        bundle.add_function("BADFUNC", bad_func)
        bundle.add_resource("msg = { BADFUNC($x) }")
        _result, errors = bundle.format_pattern("msg", {"x": 42})
        # Should produce fallback, not crash
        assert len(errors) > 0

    def test_custom_function_success(self) -> None:
        """Custom function that succeeds returns its value."""

        def double_func(value: object) -> str:
            return str(int(value) * 2)  # type: ignore[call-overload]

        bundle = FluentBundle("en-US")
        bundle.add_function("DOUBLE", double_func)
        bundle.add_resource("msg = { DOUBLE($x) }")
        result, errors = bundle.format_pattern("msg", {"x": 5})
        assert "10" in result
        assert len(errors) == 0
