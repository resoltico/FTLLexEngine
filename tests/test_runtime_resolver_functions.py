"""Function call safety and exception handling tests for FluentResolver.

Consolidates:
- test_resolver_function_call_safety.py: all
- test_resolver_function_exceptions.py: all
"""

from __future__ import annotations

from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.diagnostics import ErrorCategory
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.syntax.ast import (
    CallArguments,
    FunctionReference,
    Identifier,
    Message,
    Pattern,
    Placeable,
    StringLiteral,
    TextElement,
    VariableReference,
)

# ============================================================================
# FUNCTION CALL SAFETY (_call_function_safe)
# ============================================================================


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


# ============================================================================
# FUNCTION EXCEPTION HANDLING (locale injection path - lines 913-928)
# ============================================================================


class TestCustomFunctionExceptionWithLocaleInjection:
    """Test uncaught exceptions from custom functions requiring locale injection.

    Covers lines 913-928 in resolver.py: exception handling for functions that
    require locale injection but raise unexpected exceptions during execution.
    """

    def test_custom_function_runtime_error_with_locale_injection(self) -> None:
        """Custom function with locale injection raises RuntimeError."""

        def failing_function(value: str, locale: str) -> str:
            msg = f"Intentional failure for {value} in {locale}"
            raise RuntimeError(msg)

        failing_function._ftl_requires_locale = True  # type: ignore[attr-defined]

        registry = FunctionRegistry()
        registry.register(failing_function, ftl_name="FAIL_WITH_LOCALE")

        func_call = FunctionReference(
            id=Identifier("FAIL_WITH_LOCALE"),
            arguments=CallArguments(
                positional=(StringLiteral(value="test"),),
                named=(),
            ),
        )

        pattern = Pattern(
            elements=(
                TextElement(value="Before "),
                Placeable(expression=func_call),
                TextElement(value=" After"),
            )
        )
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {})
        assert "{!FAIL_WITH_LOCALE}" in result
        assert len(errors) == 1
        assert errors[0].category == ErrorCategory.RESOLUTION
        assert "Uncaught exception" in str(errors[0])
        assert "RuntimeError" in str(errors[0])

    def test_custom_function_key_error_with_locale_injection(self) -> None:
        """Custom function with locale injection raises KeyError."""

        def failing_function(_value: str, _locale: str) -> str:
            data: dict[str, str] = {}
            return data["nonexistent_key"]

        failing_function._ftl_requires_locale = True  # type: ignore[attr-defined]

        registry = FunctionRegistry()
        registry.register(failing_function, ftl_name="LOOKUP")

        func_call = FunctionReference(
            id=Identifier("LOOKUP"),
            arguments=CallArguments(
                positional=(StringLiteral(value="test"),),
                named=(),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=func_call),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en_US",
            messages={"msg": message},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {})
        assert "{!LOOKUP}" in result
        assert len(errors) == 1
        assert "KeyError" in str(errors[0])

    def test_custom_function_zero_division_with_locale_injection(self) -> None:
        """Custom function with locale injection raises ZeroDivisionError."""

        def dividing_function(value: int, _locale: str) -> str:
            result = value / 0
            return str(result)

        dividing_function._ftl_requires_locale = True  # type: ignore[attr-defined]

        registry = FunctionRegistry()
        registry.register(dividing_function, ftl_name="DIVIDE")

        func_call = FunctionReference(
            id=Identifier("DIVIDE"),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier("num")),),
                named=(),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=func_call),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="de_DE",
            messages={"msg": message},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"num": 10})
        assert "{!DIVIDE}" in result
        assert len(errors) == 1
        assert "ZeroDivisionError" in str(errors[0])


# ============================================================================
# FUNCTION EXCEPTION HANDLING (non-locale path - lines 940-955)
# ============================================================================


class TestCustomFunctionExceptionWithoutLocaleInjection:
    """Test uncaught exceptions from custom functions without locale injection.

    Covers lines 940-955 in resolver.py: exception handling for functions that
    do NOT require locale injection but raise unexpected exceptions.
    """

    def test_custom_function_runtime_error_without_locale_injection(self) -> None:
        """Custom function without locale injection raises RuntimeError."""

        def failing_custom_func(value: str) -> str:
            msg = f"Custom error for {value}"
            raise RuntimeError(msg)

        registry = FunctionRegistry()
        registry.register(failing_custom_func, ftl_name="CUSTOM_FAIL")

        func_call = FunctionReference(
            id=Identifier("CUSTOM_FAIL"),
            arguments=CallArguments(
                positional=(StringLiteral(value="data"),),
                named=(),
            ),
        )

        pattern = Pattern(
            elements=(
                TextElement(value="Start "),
                Placeable(expression=func_call),
                TextElement(value=" End"),
            )
        )
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="fr",
            messages={"msg": message},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {})
        assert "{!CUSTOM_FAIL}" in result
        assert len(errors) == 1
        assert errors[0].category == ErrorCategory.RESOLUTION
        assert "Uncaught exception" in str(errors[0])
        assert "RuntimeError" in str(errors[0])

    def test_custom_function_index_error_without_locale_injection(self) -> None:
        """Custom function without locale injection raises IndexError."""

        def index_error_func(_value: str) -> str:
            empty_list: list[str] = []
            return empty_list[10]

        registry = FunctionRegistry()
        registry.register(index_error_func, ftl_name="GETINDEX")

        func_call = FunctionReference(
            id=Identifier("GETINDEX"),
            arguments=CallArguments(
                positional=(StringLiteral(value="text"),),
                named=(),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=func_call),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="ja",
            messages={"msg": message},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {})
        assert "{!GETINDEX}" in result
        assert len(errors) == 1
        assert "IndexError" in str(errors[0])

    def test_custom_function_attribute_error_without_locale_injection(self) -> None:
        """Custom function without locale injection raises AttributeError."""

        def attr_error_func(value: str) -> str:
            return value.nonexistent_method()  # type: ignore[attr-defined]

        registry = FunctionRegistry()
        registry.register(attr_error_func, ftl_name="GETATTR")

        func_call = FunctionReference(
            id=Identifier("GETATTR"),
            arguments=CallArguments(
                positional=(StringLiteral(value="test"),),
                named=(),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=func_call),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="es",
            messages={"msg": message},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {})
        assert "{!GETATTR}" in result
        assert len(errors) == 1
        assert "AttributeError" in str(errors[0])


# ============================================================================
# PROPERTY-BASED FUNCTION EXCEPTION TESTS
# ============================================================================


class TestFunctionExceptionHypothesis:
    """Property-based tests for function exception handling."""

    @given(
        locale=st.sampled_from(["en", "de", "fr", "ja", "es", "ar"]),
        error_msg=st.text(min_size=1, max_size=100),
    )
    def test_locale_injection_exception_always_degrades_gracefully(
        self, locale: str, error_msg: str
    ) -> None:
        """Property: Functions with locale injection always degrade gracefully."""
        event(f"locale={locale}")

        def failing_func(_value: str, _locale: str) -> str:
            raise RuntimeError(error_msg)

        failing_func._ftl_requires_locale = True  # type: ignore[attr-defined]

        registry = FunctionRegistry()
        registry.register(failing_func, ftl_name="FAIL")

        func_call = FunctionReference(
            id=Identifier("FAIL"),
            arguments=CallArguments(
                positional=(StringLiteral(value="x"),),
                named=(),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=func_call),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale=locale,
            messages={"msg": message},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {})
        assert isinstance(result, str)
        assert len(errors) >= 1
        assert "{!FAIL}" in result

    @given(
        locale=st.sampled_from(["en", "de", "fr", "ja", "es"]),
        error_msg=st.text(min_size=1, max_size=100),
    )
    def test_non_locale_injection_exception_always_degrades_gracefully(
        self, locale: str, error_msg: str
    ) -> None:
        """Property: Functions without locale injection always degrade gracefully."""
        event(f"locale={locale}")

        def failing_custom(_value: str) -> str:
            raise KeyError(error_msg)

        registry = FunctionRegistry()
        registry.register(failing_custom, ftl_name="CUSTOM")

        func_call = FunctionReference(
            id=Identifier("CUSTOM"),
            arguments=CallArguments(
                positional=(StringLiteral(value="x"),),
                named=(),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=func_call),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale=locale,
            messages={"msg": message},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {})
        assert isinstance(result, str)
        assert len(errors) >= 1
        assert "{!CUSTOM}" in result
