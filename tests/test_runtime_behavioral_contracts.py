"""Tests for runtime behavioral contracts covering async safety, depth guards, and AST fields.

Tests:
- Parse errors returned as typed ParseError values (no side-channel state)
- Term argument evaluation respects nesting depth guards
- Serializer wraps argument serialization in depth guard
- AST span fields exist on Pattern, TextElement, and Placeable
- Function call arguments accept newlines between arguments
- FunctionRegistry accepts *args functions when inject_locale=True
- MAX_CURRENCY_CACHE_SIZE constant is used for currency caching
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
from ftllexengine.syntax.cursor import ParseError


class TestTypedErrorReturn:
    """Parse errors returned as typed ParseError values.

    Primitives return ParseResult[T] | ParseError directly.
    No shared state — each call is independent.
    """

    def test_failure_returns_parse_error(self) -> None:
        """Failed parse returns ParseError, not None."""
        from ftllexengine.syntax.cursor import Cursor  # noqa: PLC0415
        from ftllexengine.syntax.parser.primitives import parse_identifier  # noqa: PLC0415

        cursor = Cursor("123invalid", 0)
        result = parse_identifier(cursor)
        assert isinstance(result, ParseError)
        assert result.cursor.pos == 0

    def test_success_is_not_parse_error(self) -> None:
        """Successful parse does not return ParseError."""
        from ftllexengine.syntax.cursor import Cursor  # noqa: PLC0415
        from ftllexengine.syntax.parser.primitives import parse_identifier  # noqa: PLC0415

        cursor = Cursor("validId", 0)
        result = parse_identifier(cursor)
        assert not isinstance(result, ParseError)
        assert result.value == "validId"

    def test_async_calls_are_independent(self) -> None:
        """Concurrent async parse calls return independent values."""
        from ftllexengine.syntax.cursor import Cursor  # noqa: PLC0415
        from ftllexengine.syntax.parser.primitives import parse_identifier  # noqa: PLC0415

        results: dict[str, object] = {}

        async def task_a() -> None:
            cursor = Cursor("123bad", 0)
            results["a"] = parse_identifier(cursor)

        async def task_b() -> None:
            cursor = Cursor("validId", 0)
            results["b"] = parse_identifier(cursor)

        async def run_tasks() -> None:
            await asyncio.gather(task_a(), task_b())

        asyncio.run(run_tasks())

        assert isinstance(results["a"], ParseError)
        assert not isinstance(results["b"], ParseError)


class TestTermArgumentDepthGuard:
    """Term argument evaluation uses the expression depth guard."""

    def test_term_with_arguments_resolves(self) -> None:
        """Term arguments are resolved under depth tracking."""
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
        """Term argument evaluation is bounded by the nesting depth limit."""
        from ftllexengine.runtime.bundle import FluentBundle  # noqa: PLC0415

        bundle = FluentBundle("en_US", max_nesting_depth=5)
        bundle.add_resource(
            "-term = Value\n"
            "msg = { -term }\n"
        )

        result, _errors = bundle.format_pattern("msg")
        assert result is not None


class TestSerializerArgumentDepthGuard:
    """Serializer wraps argument serialization in a depth guard."""

    def test_function_call_with_arguments_serializes(self) -> None:
        """Function call arguments serialize correctly under depth tracking."""
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


class TestASTSpanFields:
    """Pattern, TextElement, and Placeable AST nodes have optional span fields."""

    def test_pattern_span_defaults_to_none(self) -> None:
        """Pattern span defaults to None when not provided."""
        pattern = Pattern(elements=())
        assert pattern.span is None

    def test_pattern_span_accepts_span(self) -> None:
        """Pattern span accepts and preserves a Span value."""
        span = Span(start=0, end=10)
        pattern = Pattern(elements=(), span=span)
        assert pattern.span == span
        assert pattern.span.start == 0
        assert pattern.span.end == 10

    def test_text_element_span_defaults_to_none(self) -> None:
        """TextElement span defaults to None when not provided."""
        elem = TextElement(value="hello")
        assert elem.span is None

    def test_text_element_span_accepts_span(self) -> None:
        """TextElement span accepts and preserves a Span value."""
        span = Span(start=5, end=10)
        elem = TextElement(value="hello", span=span)
        assert elem.span == span

    def test_placeable_span_defaults_to_none(self) -> None:
        """Placeable span defaults to None when not provided."""
        placeable = Placeable(expression=StringLiteral(value="x"))
        assert placeable.span is None

    def test_placeable_span_accepts_span(self) -> None:
        """Placeable span accepts and preserves a Span value."""
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
        """PROPERTY: Span values stored on AST nodes are preserved exactly."""
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
        """Span fields on AST nodes are immutable (frozen dataclass)."""
        span = Span(start=0, end=5)
        pattern = Pattern(elements=(), span=span)

        with pytest.raises((AttributeError, TypeError)):
            pattern.span = Span(start=1, end=6)  # type: ignore[misc]


class TestCallArgumentsBlankHandling:
    """Function call arguments accept blank lines (newlines) between arguments."""

    def test_multiline_function_arguments(self) -> None:
        """Function arguments on separate lines parse as a single valid call."""
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
        """Single-line arguments continue to work as expected."""
        from ftllexengine.syntax.parser.core import FluentParserV1  # noqa: PLC0415

        ftl = "msg = { NUMBER($count, minimumFractionDigits: 2) }\n"
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        from ftllexengine.syntax.ast import Junk, Message  # noqa: PLC0415

        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        junk = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk) == 0


class TestVarPositionalInjectLocale:
    """FunctionRegistry accepts *args functions when inject_locale=True."""

    def test_var_positional_function_accepted(self) -> None:
        """Function with *args and inject_locale=True registers without error."""
        from ftllexengine.runtime.function_bridge import (  # noqa: PLC0415
            FunctionRegistry,
            fluent_function,
        )

        @fluent_function(inject_locale=True)
        def custom_format(*args: object) -> str:
            return str(args)

        registry = FunctionRegistry()
        registry.register(custom_format, ftl_name="CUSTOM_FORMAT")

    def test_var_positional_with_one_named_param_accepted(self) -> None:
        """Function with one named param plus *args and inject_locale=True is accepted."""
        from ftllexengine.runtime.function_bridge import (  # noqa: PLC0415
            FunctionRegistry,
            fluent_function,
        )

        @fluent_function(inject_locale=True)
        def format_val(value: object, *args: object) -> str:  # noqa: ARG001
            return str(value)

        registry = FunctionRegistry()
        registry.register(format_val, ftl_name="FORMAT_VAL")

    def test_no_var_positional_insufficient_params_rejected(self) -> None:
        """Function without *args and only 1 positional param is rejected with inject_locale."""
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
        """Function with 2 positional params and inject_locale=True is accepted."""
        from ftllexengine.runtime.function_bridge import (  # noqa: PLC0415
            FunctionRegistry,
            fluent_function,
        )

        @fluent_function(inject_locale=True)
        def good_func(value: object, locale_code: str) -> str:  # noqa: ARG001
            return str(value)

        registry = FunctionRegistry()
        registry.register(good_func, ftl_name="GOOD_FUNC")


class TestMaxCurrencyCacheSize:
    """MAX_CURRENCY_CACHE_SIZE constant controls the currency implementation cache."""

    def test_constant_exists_and_is_positive(self) -> None:
        """MAX_CURRENCY_CACHE_SIZE is a positive integer."""
        from ftllexengine.constants import MAX_CURRENCY_CACHE_SIZE  # noqa: PLC0415

        assert isinstance(MAX_CURRENCY_CACHE_SIZE, int)
        assert MAX_CURRENCY_CACHE_SIZE > 0

    def test_currency_cache_uses_correct_constant(self) -> None:
        """_get_currency_impl lru_cache maxsize matches MAX_CURRENCY_CACHE_SIZE."""
        from ftllexengine.constants import MAX_CURRENCY_CACHE_SIZE  # noqa: PLC0415
        from ftllexengine.introspection.iso import _get_currency_impl  # noqa: PLC0415

        cache_info = _get_currency_impl.cache_info()  # pylint: disable=no-value-for-parameter
        assert cache_info.maxsize == MAX_CURRENCY_CACHE_SIZE

    def test_constant_in_all(self) -> None:
        """MAX_CURRENCY_CACHE_SIZE is exported in constants.__all__."""
        from ftllexengine import constants  # noqa: PLC0415

        assert "MAX_CURRENCY_CACHE_SIZE" in constants.__all__
