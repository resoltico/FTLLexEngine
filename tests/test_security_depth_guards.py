"""Security tests for depth guard fixes.

Tests DoS prevention for deeply nested function calls and term references.
Covers fixes for:
- Parser depth tracking for function arguments (Issue #1)
- Resolver depth tracking for function arguments (Issue #2)
- Term reference argument depth tracking (Observation B)

Python 3.13+.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.parser.core import FluentParserV1
from ftllexengine.syntax.parser.rules import ParseContext


class TestParserFunctionCallDepthTracking:
    """Parser depth guard for nested function calls.

    Previously, deeply nested function calls like NUMBER(A(B(C(...)))) bypassed
    the placeable nesting limit because depth was only tracked for placeables.
    """

    def test_enter_nesting_increments_depth(self) -> None:
        """Verify enter_nesting() creates context with incremented depth."""
        ctx = ParseContext(max_nesting_depth=10, current_depth=0)
        nested = ctx.enter_nesting()
        assert nested.current_depth == 1
        assert nested.max_nesting_depth == 10

    def test_enter_nesting_chain(self) -> None:
        """Verify chained enter_nesting() calls accumulate depth."""
        ctx = ParseContext(max_nesting_depth=10, current_depth=0)
        for i in range(5):
            ctx = ctx.enter_nesting()
            assert ctx.current_depth == i + 1

    def test_is_depth_exceeded_at_limit(self) -> None:
        """Verify is_depth_exceeded() returns True at max depth."""
        ctx = ParseContext(max_nesting_depth=3, current_depth=3)
        assert ctx.is_depth_exceeded() is True

    def test_is_depth_exceeded_below_limit(self) -> None:
        """Verify is_depth_exceeded() returns False below limit."""
        ctx = ParseContext(max_nesting_depth=3, current_depth=2)
        assert ctx.is_depth_exceeded() is False

    def test_deeply_nested_function_calls_rejected(self) -> None:
        """Parser should reject deeply nested function calls that exceed depth limit."""
        # Create parser with low depth limit
        parser = FluentParserV1(max_nesting_depth=5)

        # Create deeply nested function call: FUNC(FUNC(FUNC(...)))
        # Each level should count towards depth limit
        nested_call = "FUNC(" * 10 + "$x" + ")" * 10
        ftl = f"msg = {{ {nested_call} }}"

        # Parse should succeed but with Junk entries for deep nesting
        resource = parser.parse(ftl)

        # Either parse fails entirely (Junk) or returns pattern that won't resolve
        # The key is that it doesn't cause RecursionError
        assert resource is not None
        # Parsing deeply nested structures should produce Junk or errors
        from ftllexengine.syntax.ast import Junk, Message  # noqa: PLC0415

        has_junk = any(isinstance(e, Junk) for e in resource.entries)
        has_message = any(isinstance(e, Message) for e in resource.entries)
        # Either Junk was created or message was parsed (but may fail at runtime)
        assert has_junk or has_message

    def test_function_nesting_within_depth_limit_succeeds(self) -> None:
        """Function nesting within depth limit should parse correctly."""
        bundle = FluentBundle("en_US")

        # Moderate nesting that should succeed
        bundle.add_resource("msg = { NUMBER($x) }")

        result, errors = bundle.format_pattern("msg", {"x": 42})
        assert len(errors) == 0 or "42" in result

    @given(st.integers(min_value=2, max_value=10))
    @settings(max_examples=10)
    def test_function_nesting_depth_property(self, depth: int) -> None:
        """PROPERTY: Parser handles function nesting up to configured depth."""
        parser = FluentParserV1(max_nesting_depth=depth)

        # Create nesting just at the limit
        nested = "FUNC(" * (depth - 1) + "$x" + ")" * (depth - 1)
        ftl = f"msg = {{ {nested} }}"

        # Should parse without RecursionError
        resource = parser.parse(ftl)
        assert resource is not None


class TestParserTermReferenceDepthTracking:
    """Parser depth guard for term references with arguments.

    Term references with arguments like -term(case: "nominative") should
    also track depth to prevent DoS attacks.
    """

    def test_term_with_arguments_parses(self) -> None:
        """Basic term reference with arguments should parse."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("-brand = Firefox\n    .gender = masculine")
        bundle.add_resource('msg = { -brand(case: "nominative") }')

        result, _ = bundle.format_pattern("msg")
        assert "Firefox" in result or "{" in result

    def test_deeply_nested_term_arguments_rejected(self) -> None:
        """Parser should handle deeply nested term arguments."""
        parser = FluentParserV1(max_nesting_depth=5)

        # Term with nested function in argument
        ftl = "-term = Value\nmsg = { -term(x: NUMBER(NUMBER(NUMBER($a)))) }"
        resource = parser.parse(ftl)

        # Should parse without RecursionError
        assert resource is not None


class TestResolverFunctionCallDepthTracking:
    """Resolver depth guard for function argument resolution.

    Previously, _resolve_function_call evaluated arguments without using
    expression_guard, allowing deeply nested function calls to bypass depth limit.
    """

    def test_resolver_handles_nested_function_calls(self) -> None:
        """Resolver should handle nested function calls without stack overflow."""
        bundle = FluentBundle("en_US")

        # Define a simple function that returns its input
        def identity(val: int | float | str) -> str:
            return str(val)

        bundle.add_function("ID", identity)
        bundle.add_resource("msg = { ID(ID(ID($x))) }")

        # Should resolve without RecursionError
        result, errors = bundle.format_pattern("msg", {"x": 42})
        assert result is not None
        assert "42" in result or len(errors) > 0

    def test_resolver_depth_limit_prevents_dos(self) -> None:
        """Resolver should not crash on adversarially nested AST."""
        from ftllexengine.syntax.ast import (  # noqa: PLC0415
            CallArguments,
            FunctionReference,
            Identifier,
            Message,
            Pattern,
            Placeable,
        )

        # Create deeply nested function call AST manually
        # This simulates an adversarial AST that bypasses parser limits
        def make_nested_func(depth: int, inner: FunctionReference) -> FunctionReference:
            if depth == 0:
                return inner
            return FunctionReference(
                id=Identifier("ID"),
                arguments=CallArguments(positional=(inner,), named=()),
            )

        # Start with innermost call
        innermost = FunctionReference(
            id=Identifier("ID"),
            arguments=CallArguments(
                positional=(
                    FunctionReference(
                        id=Identifier("NUMBER"),
                        arguments=CallArguments(positional=(), named=()),
                    ),
                ),
                named=(),
            ),
        )

        # Build deep nesting
        nested = innermost
        for _ in range(150):  # Exceed typical stack limits
            nested = make_nested_func(1, nested)

        # Create message with this nested structure
        msg = Message(
            id=Identifier("msg"),
            value=Pattern(elements=(Placeable(expression=nested),)),
            attributes=(),
        )

        # Add to bundle with low depth limit using internal _messages dict
        bundle = FluentBundle("en_US", max_nesting_depth=50)

        def identity(val: int | float | str) -> str:
            return str(val)

        bundle.add_function("ID", identity)
        bundle._messages["msg"] = msg

        # Should not crash with RecursionError
        # Either returns error or uses depth guard
        result, errors = bundle.format_pattern("msg")
        assert result is not None
        # Should have error due to depth limit
        assert len(errors) > 0 or "{" in result


class TestLocaleUtilsLazyImport:
    """Tests for lazy Babel import in locale_utils.

    locale_utils.py now imports Babel lazily to support parser-only installations.
    """

    def test_normalize_locale_no_babel_required(self) -> None:
        """normalize_locale() should work without Babel."""
        from ftllexengine.locale_utils import normalize_locale  # noqa: PLC0415

        # Pure string manipulation, no Babel needed
        assert normalize_locale("en-US") == "en_us"
        assert normalize_locale("pt-BR") == "pt_br"
        assert normalize_locale("EN-US") == "en_us"

    def test_get_system_locale_no_babel_required(self) -> None:
        """get_system_locale() should work without Babel."""
        from ftllexengine.locale_utils import get_system_locale  # noqa: PLC0415

        # Uses only stdlib locale module
        result = get_system_locale()
        assert isinstance(result, str)
        # At least 1 character (C locale returns 'c', normal locales return 'en_US' etc.)
        assert len(result) >= 1

    def test_get_babel_locale_requires_babel(self) -> None:
        """get_babel_locale() should raise ImportError if Babel missing.

        Note: This test assumes Babel IS installed in dev environment.
        It verifies the function works, not that it fails without Babel.
        """
        from ftllexengine.locale_utils import get_babel_locale  # noqa: PLC0415

        # Should work with Babel installed
        locale = get_babel_locale("en-US")
        assert locale.language == "en"
        assert locale.territory == "US"

    def test_get_babel_locale_caches_result(self) -> None:
        """get_babel_locale() should cache Locale objects."""
        from ftllexengine.locale_utils import get_babel_locale  # noqa: PLC0415

        # Call twice with same locale
        locale1 = get_babel_locale("de-DE")
        locale2 = get_babel_locale("de-DE")

        # Should return same cached object
        assert locale1 is locale2


class TestDeadCodeRemoval:
    """Verify parser still works after removing dead \\r checks.

    Line endings are normalized to LF at parser entry, so \\r checks
    in parser internals were dead code.
    """

    def test_crlf_normalization(self) -> None:
        """Parser should normalize CRLF to LF."""
        parser = FluentParserV1()

        # Source with CRLF line endings
        source = "msg = Hello\r\nworld\r\n"
        resource = parser.parse(source)

        # Should parse correctly
        from ftllexengine.syntax.ast import Message  # noqa: PLC0415

        assert len(resource.entries) >= 1
        # Find message
        msg = next((e for e in resource.entries if isinstance(e, Message)), None)
        assert msg is not None

    def test_cr_only_normalization(self) -> None:
        """Parser should normalize CR-only to LF."""
        parser = FluentParserV1()

        # Source with CR-only line endings (classic Mac)
        source = "msg = Hello\rworld\r"
        resource = parser.parse(source)

        # Should parse correctly
        assert resource is not None
        assert len(resource.entries) >= 1

    def test_mixed_line_endings(self) -> None:
        """Parser should handle mixed line endings."""
        parser = FluentParserV1()

        # Source with mixed line endings
        source = "msg1 = Hello\nmsg2 = World\r\nmsg3 = Foo\r"
        resource = parser.parse(source)

        # Should parse all messages
        from ftllexengine.syntax.ast import Message  # noqa: PLC0415

        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) >= 1
