# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_expressions.py."""

from tests.syntax_parser_expressions_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# INLINE EXPRESSION HELPERS
# ============================================================================


class TestInlineExpressionHelpers:
    """Tests for inline expression helper functions."""

    def test_inline_string_literal(self) -> None:
        """String literal inline expression."""
        result = _parse_inline_string_literal(Cursor('"text"', 0))
        assert result is not None
        assert isinstance(result.value, StringLiteral)

    def test_inline_string_literal_fails(self) -> None:
        """Unclosed string literal returns None."""
        assert _parse_inline_string_literal(Cursor('"', 0)) is None

    def test_inline_number_literal(self) -> None:
        """Number literal inline expression."""
        result = _parse_inline_number_literal(Cursor("42", 0))
        assert result is not None
        assert isinstance(result.value, NumberLiteral)

    def test_inline_number_single_digit(self) -> None:
        """Single digit number parses."""
        result = _parse_inline_number_literal(Cursor("1", 0))
        assert result is not None

    def test_inline_hyphen_term(self) -> None:
        """Hyphen-prefixed term reference."""
        result = _parse_inline_hyphen(Cursor("-brand", 0))
        assert result is not None
        assert isinstance(result.value, TermReference)

    def test_inline_hyphen_number(self) -> None:
        """Hyphen-prefixed negative number."""
        result = _parse_inline_hyphen(Cursor("-123", 0))
        assert result is not None
        assert isinstance(result.value, NumberLiteral)

    def test_inline_hyphen_fails(self) -> None:
        """Hyphen alone returns None."""
        assert _parse_inline_hyphen(Cursor("-", 0)) is None

    def test_message_attribute_with_dot(self) -> None:
        """Parse .attribute suffix."""
        attr, _ = _parse_message_attribute(Cursor(".attr", 0))
        assert attr is not None
        assert isinstance(attr, Identifier)

    def test_message_attribute_no_dot(self) -> None:
        """No dot returns None."""
        attr, _ = _parse_message_attribute(Cursor("x", 0))
        assert attr is None

    def test_message_attribute_identifier_fails(self) -> None:
        """Dot followed by non-identifier returns None."""
        attr, _ = _parse_message_attribute(Cursor(".123", 0))
        assert attr is None

    def test_inline_identifier_function_call(self) -> None:
        """Identifier followed by '(' is function call."""
        result = _parse_inline_identifier(Cursor("FUNC($x)", 0))
        assert result is not None

    def test_inline_identifier_message_ref(self) -> None:
        """Identifier as message reference."""
        result = _parse_inline_identifier(Cursor("msg", 0))
        assert result is not None
        assert isinstance(result.value, MessageReference)

    def test_inline_identifier_with_attribute(self) -> None:
        """Message reference with attribute."""
        result = _parse_inline_identifier(Cursor("msg.attr", 0))
        assert result is not None
        assert isinstance(result.value, MessageReference)
        assert result.value.attribute is not None

    def test_inline_identifier_non_ident_start(self) -> None:
        """Non-identifier start returns None."""
        assert _parse_inline_identifier(Cursor("123", 0)) is None

    def test_inline_identifier_function_fails(self) -> None:
        """Lowercase function with invalid args fails."""
        assert _parse_inline_identifier(
            Cursor("func(@)", 0)
        ) is None
