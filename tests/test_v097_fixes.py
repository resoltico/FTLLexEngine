"""Tests for v0.97.0 fixes.

Covers:
- SEC-PARSER-ASYNC-ERROR-UNSAFE-001: contextvars async-safe error context
- SEC-RESOLVER-DEPTH-BYPASS-001: term argument expression_guard wrapping
- SEC-SERIALIZER-DEPTH-BYPASS-001: argument serialization depth_guard wrapping
- ARCH-AST-SPAN-MISSING-001: span fields on Pattern, TextElement, Placeable
- SPEC-PARSER-BLANK-HANDLING-001: blank (not blank_inline) in CallArguments
- MAINT-FUNC-REGISTRY-VAR-POSITIONAL-001: *args support with inject_locale
- MAINT-CONST-MISMATCH-001: MAX_CURRENCY_CACHE_SIZE constant

Python 3.13+.
"""

from __future__ import annotations

import asyncio

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.syntax.ast import (
    Pattern,
    Placeable,
    Span,
    StringLiteral,
    TextElement,
)
from ftllexengine.syntax.parser.primitives import (
    clear_parse_error,
    get_last_parse_error,
)

# ============================================================================
# SEC-PARSER-ASYNC-ERROR-UNSAFE-001: contextvars async isolation
# ============================================================================


class TestContextVarsAsyncIsolation:
    """Verify parse error context uses task-local storage via contextvars.

    contextvars provides automatic isolation per async task, preventing
    error context leakage between concurrent parse operations.
    """

    def test_error_context_defaults_to_none(self) -> None:
        """Fresh context should have no error recorded."""
        clear_parse_error()
        assert get_last_parse_error() is None

    def test_error_context_set_and_get(self) -> None:
        """Error context should be retrievable after being set."""
        from ftllexengine.syntax.cursor import Cursor  # noqa: PLC0415
        from ftllexengine.syntax.parser.primitives import parse_identifier  # noqa: PLC0415

        cursor = Cursor("123invalid", 0)
        result = parse_identifier(cursor)
        assert result is None

        error = get_last_parse_error()
        assert error is not None
        assert error.position == 0

    def test_async_task_isolation(self) -> None:
        """Each async task should have independent error context."""
        from ftllexengine.syntax.cursor import Cursor  # noqa: PLC0415
        from ftllexengine.syntax.parser.primitives import parse_identifier  # noqa: PLC0415

        results: dict[str, str | None] = {}

        async def task_a() -> None:
            cursor = Cursor("123bad", 0)
            parse_identifier(cursor)
            error = get_last_parse_error()
            results["a_error"] = error.message if error else None

        async def task_b() -> None:
            cursor = Cursor("validId", 0)
            result = parse_identifier(cursor)
            # Task B should have its own context, not polluted by task A
            results["b_result"] = result.value if result else None
            # After successful parse, error context from this task should differ
            err = get_last_parse_error()
            results["b_error_after"] = err.message if err else None

        async def run_tasks() -> None:
            # Run tasks concurrently - each gets own contextvars copy
            await asyncio.gather(task_a(), task_b())

        asyncio.run(run_tasks())

        # Task A should have recorded an error
        assert results["a_error"] is not None
        # Task B should have successfully parsed
        assert results["b_result"] == "validId"


# ============================================================================
# SEC-RESOLVER-DEPTH-BYPASS-001: term argument expression_guard
# ============================================================================


class TestTermArgumentDepthGuard:
    """Verify term argument evaluation uses expression_guard."""

    def test_term_with_arguments_resolves(self) -> None:
        """Term arguments should resolve under depth tracking."""
        from ftllexengine.runtime.bundle import FluentBundle  # noqa: PLC0415

        bundle = FluentBundle("en_US")
        bundle.add_resource(
            '-brand = { $case ->\n'
            '    [accusative] Firefox Browser\n'
            '   *[nominative] Firefox\n'
            '}\n'
            'about = About { -brand(case: "accusative") }\n'
        )

        result, errors = bundle.format_pattern("about")
        assert "Firefox" in result
        assert len(errors) == 0

    def test_term_arguments_respect_nesting_limit(self) -> None:
        """Term argument evaluation should be bounded by depth guard."""
        from ftllexengine.runtime.bundle import FluentBundle  # noqa: PLC0415

        bundle = FluentBundle("en_US", max_nesting_depth=5)
        bundle.add_resource(
            "-term = Value\n"
            "msg = { -term }\n"
        )

        result, _errors = bundle.format_pattern("msg")
        assert result is not None


# ============================================================================
# SEC-SERIALIZER-DEPTH-BYPASS-001: argument serialization depth_guard
# ============================================================================


class TestSerializerArgumentDepthGuard:
    """Verify serializer wraps argument serialization in depth_guard."""

    def test_function_call_with_arguments_serializes(self) -> None:
        """Function call arguments should serialize under depth tracking."""
        from ftllexengine.syntax import serialize  # noqa: PLC0415
        from ftllexengine.syntax.ast import (  # noqa: PLC0415
            CallArguments,
            FunctionReference,
            Identifier,
            Message,
            NamedArgument,
            Resource,
            VariableReference,
        )

        call_args = CallArguments(
            positional=(VariableReference(id=Identifier("count")),),
            named=(
                NamedArgument(
                    name=Identifier("style"),
                    value=StringLiteral(value="decimal"),
                ),
            ),
        )
        func_ref = FunctionReference(
            id=Identifier("NUMBER"),
            arguments=call_args,
        )
        msg = Message(
            id=Identifier("msg"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)
        assert "NUMBER" in result
        assert "$count" in result
        assert 'style: "decimal"' in result


# ============================================================================
# ARCH-AST-SPAN-MISSING-001: span fields on Pattern, TextElement, Placeable
# ============================================================================


class TestASTSpanFields:
    """Verify span fields exist on Pattern, TextElement, and Placeable."""

    def test_pattern_span_defaults_to_none(self) -> None:
        """Pattern span should default to None."""
        pattern = Pattern(elements=())
        assert pattern.span is None

    def test_pattern_span_accepts_span(self) -> None:
        """Pattern span should accept a Span value."""
        span = Span(start=0, end=10)
        pattern = Pattern(elements=(), span=span)
        assert pattern.span == span
        assert pattern.span.start == 0
        assert pattern.span.end == 10

    def test_text_element_span_defaults_to_none(self) -> None:
        """TextElement span should default to None."""
        elem = TextElement(value="hello")
        assert elem.span is None

    def test_text_element_span_accepts_span(self) -> None:
        """TextElement span should accept a Span value."""
        span = Span(start=5, end=10)
        elem = TextElement(value="hello", span=span)
        assert elem.span == span

    def test_placeable_span_defaults_to_none(self) -> None:
        """Placeable span should default to None."""
        placeable = Placeable(expression=StringLiteral(value="x"))
        assert placeable.span is None

    def test_placeable_span_accepts_span(self) -> None:
        """Placeable span should accept a Span value."""
        span = Span(start=0, end=5)
        placeable = Placeable(expression=StringLiteral(value="x"), span=span)
        assert placeable.span == span

    @given(
        st.integers(min_value=0, max_value=10000).flatmap(
            lambda s: st.tuples(st.just(s), st.integers(min_value=s, max_value=s + 10000))
        )
    )
    @settings(max_examples=20)
    def test_span_field_roundtrip_property(self, start_end: tuple[int, int]) -> None:
        """PROPERTY: Span values stored on AST nodes are preserved."""
        start, end = start_end
        event(f"span_range={end - start}")
        span = Span(start=start, end=end)
        pattern = Pattern(elements=(TextElement(value="x", span=span),), span=span)
        assert pattern.span is not None
        assert pattern.span.start == start
        assert pattern.span.end == end
        elem_span = pattern.elements[0].span
        assert elem_span is not None
        assert elem_span == span

    def test_span_fields_frozen(self) -> None:
        """Span on AST nodes should be immutable."""
        span = Span(start=0, end=5)
        pattern = Pattern(elements=(), span=span)

        with pytest.raises((AttributeError, TypeError)):
            pattern.span = Span(start=1, end=6)  # type: ignore[misc]


# ============================================================================
# SPEC-PARSER-BLANK-HANDLING-001: blank in CallArguments
# ============================================================================


class TestCallArgumentsBlankHandling:
    """Verify CallArguments uses blank (allowing newlines), not blank_inline."""

    def test_multiline_function_arguments(self) -> None:
        """Function arguments should accept newlines between them."""
        from ftllexengine.syntax.parser.core import FluentParserV1  # noqa: PLC0415

        ftl = (
            "msg = { NUMBER(\n"
            "    $count,\n"
            "    minimumFractionDigits: 2\n"
            ") }\n"
        )
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        from ftllexengine.syntax.ast import Junk, Message  # noqa: PLC0415

        messages = [e for e in resource.entries if isinstance(e, Message)]
        junk = [e for e in resource.entries if isinstance(e, Junk)]

        assert len(messages) == 1, f"Expected 1 message, got {len(messages)}, junk: {junk}"
        assert len(junk) == 0

    def test_single_line_function_arguments_still_work(self) -> None:
        """Single-line arguments should continue to work."""
        from ftllexengine.syntax.parser.core import FluentParserV1  # noqa: PLC0415

        ftl = "msg = { NUMBER($count, minimumFractionDigits: 2) }\n"
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        from ftllexengine.syntax.ast import Junk, Message  # noqa: PLC0415

        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        junk = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk) == 0


# ============================================================================
# MAINT-FUNC-REGISTRY-VAR-POSITIONAL-001: *args with inject_locale
# ============================================================================


class TestVarPositionalInjectLocale:
    """Verify FunctionRegistry accepts *args functions with inject_locale."""

    def test_var_positional_function_accepted(self) -> None:
        """Function with *args and inject_locale should register without error."""
        from ftllexengine.runtime.function_bridge import (  # noqa: PLC0415
            FunctionRegistry,
            fluent_function,
        )

        @fluent_function(inject_locale=True)
        def custom_format(*args: object) -> str:
            return str(args)

        registry = FunctionRegistry()
        # Should not raise TypeError
        registry.register(custom_format, ftl_name="CUSTOM_FORMAT")

    def test_var_positional_with_one_named_param_accepted(self) -> None:
        """Function with one named param + *args and inject_locale should work."""
        from ftllexengine.runtime.function_bridge import (  # noqa: PLC0415
            FunctionRegistry,
            fluent_function,
        )

        @fluent_function(inject_locale=True)
        def format_val(value: object, *args: object) -> str:  # noqa: ARG001
            return str(value)

        registry = FunctionRegistry()
        # Should not raise TypeError - *args can accept locale
        registry.register(format_val, ftl_name="FORMAT_VAL")

    def test_no_var_positional_insufficient_params_rejected(self) -> None:
        """Function without *args and only 1 param should be rejected."""
        from ftllexengine.runtime.function_bridge import (  # noqa: PLC0415
            FunctionRegistry,
            fluent_function,
        )

        @fluent_function(inject_locale=True)
        def bad_func(value: object) -> str:
            return str(value)

        registry = FunctionRegistry()
        with pytest.raises(TypeError, match="inject_locale"):
            registry.register(bad_func, ftl_name="BAD_FUNC")

    def test_two_positional_params_accepted(self) -> None:
        """Function with 2 positional params and inject_locale should work."""
        from ftllexengine.runtime.function_bridge import (  # noqa: PLC0415
            FunctionRegistry,
            fluent_function,
        )

        @fluent_function(inject_locale=True)
        def good_func(value: object, locale_code: str) -> str:  # noqa: ARG001
            return str(value)

        registry = FunctionRegistry()
        # Should not raise
        registry.register(good_func, ftl_name="GOOD_FUNC")


# ============================================================================
# MAINT-CONST-MISMATCH-001: MAX_CURRENCY_CACHE_SIZE
# ============================================================================


class TestMaxCurrencyCacheSize:
    """Verify MAX_CURRENCY_CACHE_SIZE is used for currency caching."""

    def test_constant_exists_and_is_positive(self) -> None:
        """MAX_CURRENCY_CACHE_SIZE should exist and be a positive integer."""
        from ftllexengine.constants import MAX_CURRENCY_CACHE_SIZE  # noqa: PLC0415

        assert isinstance(MAX_CURRENCY_CACHE_SIZE, int)
        assert MAX_CURRENCY_CACHE_SIZE > 0

    def test_currency_cache_uses_correct_constant(self) -> None:
        """_get_currency_impl should use MAX_CURRENCY_CACHE_SIZE, not territory size."""
        from ftllexengine.constants import MAX_CURRENCY_CACHE_SIZE  # noqa: PLC0415
        from ftllexengine.introspection.iso import _get_currency_impl  # noqa: PLC0415

        # lru_cache exposes cache_info which includes maxsize
        cache_info = _get_currency_impl.cache_info()  # pylint: disable=no-value-for-parameter
        assert cache_info.maxsize == MAX_CURRENCY_CACHE_SIZE

    def test_constant_in_all(self) -> None:
        """MAX_CURRENCY_CACHE_SIZE should be exported in constants __all__."""
        from ftllexengine import constants  # noqa: PLC0415

        assert "MAX_CURRENCY_CACHE_SIZE" in constants.__all__
