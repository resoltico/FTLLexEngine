"""Complete coverage tests for resolver.py exception handling paths.

Tests for uncaught exceptions from custom functions to achieve 100% coverage.
Covers lines 913-928 (locale injection path) and 940-955 (non-locale path).

Property-based tests using Hypothesis for robust verification.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.diagnostics import ErrorCategory
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


class TestCustomFunctionExceptionWithLocaleInjection:
    """Test uncaught exceptions from custom functions requiring locale injection.

    Covers lines 913-928 in resolver.py: exception handling for functions that
    require locale injection but raise unexpected exceptions during execution.
    """

    def test_custom_function_runtime_error_with_locale_injection(self) -> None:
        """Custom function with locale injection raises RuntimeError."""

        def failing_function(value: str, locale: str) -> str:
            """Function that requires locale and raises RuntimeError."""
            msg = f"Intentional failure for {value} in {locale}"
            raise RuntimeError(msg)

        # Mark function as requiring locale injection
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

        # Should gracefully degrade with fallback
        assert "{!FAIL_WITH_LOCALE}" in result
        assert len(errors) == 1
        assert errors[0].category == ErrorCategory.RESOLUTION
        assert "Uncaught exception" in str(errors[0])
        assert "RuntimeError" in str(errors[0])

    def test_custom_function_key_error_with_locale_injection(self) -> None:
        """Custom function with locale injection raises KeyError."""

        def failing_function(_value: str, _locale: str) -> str:
            """Function that requires locale and raises KeyError."""
            data: dict[str, str] = {}
            return data["nonexistent_key"]  # Raises KeyError

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
            """Function that requires locale and performs division."""
            result = value / 0  # Intentional division by zero
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


class TestCustomFunctionExceptionWithoutLocaleInjection:
    """Test uncaught exceptions from custom functions without locale injection.

    Covers lines 940-955 in resolver.py: exception handling for functions that
    do NOT require locale injection but raise unexpected exceptions.
    """

    def test_custom_function_runtime_error_without_locale_injection(self) -> None:
        """Custom function without locale injection raises RuntimeError."""

        def failing_custom_func(value: str) -> str:
            """Custom function that raises RuntimeError."""
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
            """Custom function that raises IndexError."""
            empty_list: list[str] = []
            return empty_list[10]  # Raises IndexError

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
            """Custom function that raises AttributeError."""
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


class TestFunctionExceptionHypothesis:
    """Property-based tests for function exception handling."""

    @given(
        locale=st.sampled_from(["en", "de", "fr", "ja", "es", "ar"]),
        error_msg=st.text(min_size=1, max_size=100),
    )
    def test_locale_injection_exception_always_degrades_gracefully(
        self, locale: str, error_msg: str
    ) -> None:
        """Functions with locale injection always degrade gracefully on exceptions."""

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

        # Must never raise - always degrade gracefully
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
        """Functions without locale injection always degrade gracefully on exceptions."""

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

        # Must never raise - always degrade gracefully
        assert isinstance(result, str)
        assert len(errors) >= 1
        assert "{!CUSTOM}" in result
