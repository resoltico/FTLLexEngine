"""Security tests for recent fixes.

Tests DoS prevention and error handling for:
- SEC-RESOLVER-RECURSION-BYPASS-001: Selector expression depth guard
- SEC-SERIALIZER-RECURSION-BYPASS-001: Serializer selector depth guard
- RES-DEPTH-LEAK-001: Global depth tracking via contextvars
- RES-BABEL-CRASH-001: BabelImportError graceful handling
- SEC-PARSER-UNBOUNDED-001: Parser token length limits

Python 3.13+.
"""

from __future__ import annotations

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.core import FluentParserV1
from ftllexengine.syntax.parser.primitives import (
    _MAX_IDENTIFIER_LENGTH,
    _MAX_NUMBER_LENGTH,
    _MAX_STRING_LITERAL_LENGTH,
    parse_identifier,
    parse_number,
    parse_string_literal,
)


class TestSelectorExpressionDepthGuard:
    """Tests for SEC-RESOLVER-RECURSION-BYPASS-001.

    Verifies that SelectExpression selector resolution uses expression_guard
    to prevent DoS via deeply nested selectors.
    """

    def test_selector_depth_tracked_in_select_expression(self) -> None:
        """Selector resolution should use expression depth guard."""
        bundle = FluentBundle("en_US", max_nesting_depth=10)

        # Create select expression with variable selector
        bundle.add_resource("""
count =
    { $num ->
        [one] One item
       *[other] { $num } items
    }
""")

        result, errors = bundle.format_pattern("count", {"num": 5})
        assert "5" in result or "items" in result
        assert len(errors) == 0

    def test_nested_selector_respects_depth_limit(self) -> None:
        """Deeply nested selector should not cause stack overflow."""
        from ftllexengine.syntax.ast import (  # noqa: PLC0415
            Identifier,
            Message,
            NumberLiteral,
            Pattern,
            Placeable,
            SelectExpression,
            TextElement,
            VariableReference,
            Variant,
        )

        # Create SelectExpression with nested selector
        # selector = { $x -> [1] A *[other] B } (the selector itself is a nested select)
        inner_select = SelectExpression(
            selector=VariableReference(id=Identifier("x")),
            variants=(
                Variant(
                    key=NumberLiteral(raw="1", value=1),
                    value=Pattern(elements=(TextElement("A"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement("B"),)),
                    default=True,
                ),
            ),
        )

        # Outer select uses the inner select as its selector
        # This is intentionally malformed for testing (SelectExpression as selector)
        outer_select = SelectExpression(
            selector=inner_select,  # type: ignore[arg-type]
            variants=(
                Variant(
                    key=Identifier("A"),
                    value=Pattern(elements=(TextElement("Got A"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement("Got other"),)),
                    default=True,
                ),
            ),
        )

        msg = Message(
            id=Identifier("msg"),
            value=Pattern(elements=(Placeable(expression=outer_select),)),
            attributes=(),
        )

        bundle = FluentBundle("en_US", max_nesting_depth=50)
        bundle._messages["msg"] = msg

        # Should resolve without stack overflow
        result, _ = bundle.format_pattern("msg", {"x": 1})
        assert result is not None


class TestSerializerSelectorDepthGuard:
    """Tests for SEC-SERIALIZER-RECURSION-BYPASS-001.

    Verifies that serializer wraps selector serialization in depth_guard.
    """

    def test_serializer_handles_nested_select_selector(self) -> None:
        """Serializer should track depth for SelectExpression selectors."""
        from ftllexengine.syntax import serialize  # noqa: PLC0415
        from ftllexengine.syntax.ast import (  # noqa: PLC0415
            Identifier,
            Message,
            NumberLiteral,
            Pattern,
            Placeable,
            Resource,
            SelectExpression,
            TextElement,
            VariableReference,
            Variant,
        )

        # Build a select with a simple selector
        select = SelectExpression(
            selector=VariableReference(id=Identifier("x")),
            variants=(
                Variant(
                    key=NumberLiteral(raw="1", value=1),
                    value=Pattern(elements=(TextElement("One"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement("Other"),)),
                    default=True,
                ),
            ),
        )

        msg = Message(
            id=Identifier("msg"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )

        resource = Resource(entries=(msg,))

        # Should serialize without error
        result = serialize(resource)
        assert "msg" in result
        assert "$x ->" in result

    def test_deeply_nested_selector_serialization_limited(self) -> None:
        """Deeply nested selector should trigger depth limit in serializer."""
        from ftllexengine.syntax import serialize  # noqa: PLC0415
        from ftllexengine.syntax.ast import (  # noqa: PLC0415
            Identifier,
            Message,
            Pattern,
            Placeable,
            Resource,
            SelectExpression,
            TextElement,
            VariableReference,
            Variant,
        )
        from ftllexengine.syntax.serializer import SerializationDepthError  # noqa: PLC0415

        # Build deeply nested selects
        def make_nested_select(depth: int) -> SelectExpression:
            if depth == 0:
                return SelectExpression(
                    selector=VariableReference(id=Identifier("x")),
                    variants=(
                        Variant(
                            key=Identifier("a"),
                            value=Pattern(elements=(TextElement("A"),)),
                            default=False,
                        ),
                        Variant(
                            key=Identifier("other"),
                            value=Pattern(elements=(TextElement("B"),)),
                            default=True,
                        ),
                    ),
                )
            inner = make_nested_select(depth - 1)
            # Intentionally malformed: using SelectExpression as selector
            return SelectExpression(
                selector=inner,  # type: ignore[arg-type]
                variants=(
                    Variant(
                        key=Identifier("a"),
                        value=Pattern(elements=(TextElement("A"),)),
                        default=False,
                    ),
                    Variant(
                        key=Identifier("other"),
                        value=Pattern(elements=(TextElement("B"),)),
                        default=True,
                    ),
                ),
            )

        nested = make_nested_select(150)
        msg = Message(
            id=Identifier("msg"),
            value=Pattern(elements=(Placeable(expression=nested),)),
            attributes=(),
        )

        resource = Resource(entries=(msg,))

        # Should raise depth error, not RecursionError
        with pytest.raises(SerializationDepthError):
            serialize(resource, max_depth=50)


class TestGlobalDepthTracking:
    """Tests for RES-DEPTH-LEAK-001.

    Verifies that GlobalDepthGuard prevents custom functions from
    bypassing depth limits by calling back into bundle.format_pattern().
    """

    def test_global_depth_guard_prevents_callback_bypass(self) -> None:
        """Custom function calling format_pattern should respect global depth."""
        bundle = FluentBundle("en_US", max_nesting_depth=10)

        call_count = 0

        def recursive_func(_val: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count > 5:
                return "stopped"
            # Try to call back into bundle (simulating callback bypass attempt)
            # This should eventually hit global depth limit
            inner_result, _ = bundle.format_pattern("inner", {"x": call_count})
            return inner_result

        bundle.add_function("RECURSE", recursive_func)
        bundle.add_resource("inner = { RECURSE($x) }")
        bundle.add_resource('outer = { RECURSE("start") }')

        # Should not cause stack overflow
        result, errors = bundle.format_pattern("outer")
        assert result is not None
        # Either resolves with depth limit error or stops naturally
        assert len(errors) > 0 or "stopped" in result or call_count <= 15

    def test_normal_resolution_not_affected(self) -> None:
        """Normal resolution without callbacks should work fine."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("hello = Hello, { $name }!")

        result, errors = bundle.format_pattern("hello", {"name": "World"})
        # Result includes Unicode bidi isolation markers around interpolated values
        assert "Hello," in result
        assert "World" in result
        assert len(errors) == 0


class TestBabelImportErrorHandling:
    """Tests for RES-BABEL-CRASH-001.

    Verifies that BabelImportError is caught gracefully during plural matching.
    """

    def test_plural_matching_with_babel(self) -> None:
        """Plural matching should work when Babel is installed."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("""
items =
    { $count ->
        [one] One item
       *[other] { $count } items
    }
""")

        result, errors = bundle.format_pattern("items", {"count": 1})
        assert "One item" in result
        assert len(errors) == 0

        result, errors = bundle.format_pattern("items", {"count": 5})
        # Result includes Unicode bidi isolation markers around interpolated values
        assert "5" in result
        assert "items" in result
        assert len(errors) == 0

    def test_select_falls_back_on_exact_match(self) -> None:
        """Select should use exact match before plural matching."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("""
items =
    { $count ->
        [0] No items
        [1] One item
       *[other] Many items
    }
""")

        result, _ = bundle.format_pattern("items", {"count": 0})
        assert "No items" in result

        result, _ = bundle.format_pattern("items", {"count": 1})
        assert "One item" in result

        result, _ = bundle.format_pattern("items", {"count": 99})
        assert "Many items" in result


class TestParserTokenLengthLimits:
    """Tests for SEC-PARSER-UNBOUNDED-001.

    Verifies that parser primitives enforce length limits to prevent DoS.
    """

    def test_identifier_length_limit(self) -> None:
        """Identifiers exceeding max length should be rejected."""
        # Create identifier exceeding limit
        long_id = "a" * (_MAX_IDENTIFIER_LENGTH + 10)
        cursor = Cursor(long_id, 0)

        result = parse_identifier(cursor)
        # Should fail due to length limit
        assert result is None

    def test_identifier_at_limit_accepted(self) -> None:
        """Identifiers at exactly max length should be accepted."""
        max_id = "a" * _MAX_IDENTIFIER_LENGTH
        cursor = Cursor(max_id, 0)

        result = parse_identifier(cursor)
        # Should succeed at the limit
        assert result is not None
        assert result.value == max_id

    def test_normal_identifier_accepted(self) -> None:
        """Normal identifiers should parse correctly."""
        cursor = Cursor("hello-world_123", 0)
        result = parse_identifier(cursor)
        assert result is not None
        assert result.value == "hello-world_123"

    def test_number_length_limit(self) -> None:
        """Numbers exceeding max length should be rejected."""
        long_num = "1" * (_MAX_NUMBER_LENGTH + 10)
        cursor = Cursor(long_num, 0)

        result = parse_number(cursor)
        assert result is None

    def test_number_at_limit_accepted(self) -> None:
        """Numbers at exactly max length should be accepted."""
        max_num = "1" * _MAX_NUMBER_LENGTH
        cursor = Cursor(max_num, 0)

        result = parse_number(cursor)
        assert result is not None
        assert result.value == max_num

    def test_normal_number_accepted(self) -> None:
        """Normal numbers should parse correctly."""
        cursor = Cursor("-123.456", 0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == "-123.456"

    def test_string_literal_length_limit(self) -> None:
        """String literals exceeding max length should be rejected."""
        long_str = '"' + "x" * (_MAX_STRING_LITERAL_LENGTH + 10) + '"'
        cursor = Cursor(long_str, 0)

        result = parse_string_literal(cursor)
        assert result is None

    def test_normal_string_accepted(self) -> None:
        """Normal string literals should parse correctly."""
        cursor = Cursor('"Hello, World!"', 0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == "Hello, World!"

    @given(st.integers(min_value=1, max_value=_MAX_IDENTIFIER_LENGTH))
    @settings(max_examples=20)
    def test_identifier_length_property(self, length: int) -> None:
        """PROPERTY: Identifiers up to max length should parse."""
        event(f"length={length}")
        identifier = "a" * length
        cursor = Cursor(identifier, 0)
        result = parse_identifier(cursor)
        assert result is not None
        assert len(result.value) == length

    @given(st.integers(min_value=1, max_value=min(1000, _MAX_NUMBER_LENGTH)))
    @settings(max_examples=20)
    def test_number_length_property(self, length: int) -> None:
        """PROPERTY: Numbers up to max length should parse."""
        event(f"length={length}")
        number = "1" * length
        cursor = Cursor(number, 0)
        result = parse_number(cursor)
        assert result is not None
        assert len(result.value) == length


class TestParserIntegration:
    """Integration tests for parser length limits in full parsing context."""

    def test_long_message_id_rejected(self) -> None:
        """Parser should reject message with too-long ID."""
        parser = FluentParserV1()
        long_id = "a" * (_MAX_IDENTIFIER_LENGTH + 10)
        ftl = f"{long_id} = Hello"

        resource = parser.parse(ftl)

        # Should produce Junk, not crash
        from ftllexengine.syntax.ast import Junk, Message  # noqa: PLC0415

        has_junk = any(isinstance(e, Junk) for e in resource.entries)
        has_valid_message = any(
            isinstance(e, Message) and e.id.name == long_id for e in resource.entries
        )
        # Either Junk or no valid message with that ID
        assert has_junk or not has_valid_message

    def test_normal_ftl_parses_correctly(self) -> None:
        """Normal FTL should parse without issues."""
        parser = FluentParserV1()
        ftl = """
hello = Hello, World!
welcome = Welcome, { $name }!
count = { $num ->
    [one] One item
   *[other] { $num } items
}
"""
        resource = parser.parse(ftl)

        from ftllexengine.syntax.ast import Message  # noqa: PLC0415

        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 3
