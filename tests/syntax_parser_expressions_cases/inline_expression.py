# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_expressions.py."""

from tests.syntax_parser_expressions_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# INLINE EXPRESSION
# ============================================================================


class TestParseInlineExpression:
    """Tests for parse_inline_expression dispatch."""

    def test_eof_returns_none(self) -> None:
        """EOF returns None."""
        assert parse_inline_expression(Cursor("", 0)) is None

    def test_variable_reference(self) -> None:
        """'$' dispatches to variable reference."""
        result = parse_inline_expression(Cursor("$var", 0))
        assert result is not None
        assert isinstance(result.value, VariableReference)

    def test_variable_reference_fails(self) -> None:
        """'$' alone fails."""
        assert parse_inline_expression(Cursor("$", 0)) is None

    def test_string_literal(self) -> None:
        """Quote dispatches to string literal."""
        result = parse_inline_expression(Cursor('"text"', 0))
        assert result is not None
        assert isinstance(result.value, StringLiteral)

    def test_hyphen_dispatch(self) -> None:
        """'-' dispatches to hyphen handler."""
        result = parse_inline_expression(Cursor("-brand", 0))
        assert result is not None

    def test_nested_placeable(self) -> None:
        """'{' dispatches to nested placeable."""
        result = parse_inline_expression(Cursor("{ $var }", 0))
        assert result is not None
        assert isinstance(result.value, Placeable)

    def test_nested_placeable_fails(self) -> None:
        """Invalid nested placeable fails."""
        assert parse_inline_expression(
            Cursor("{ @ }", 0)
        ) is None

    def test_digit_dispatch(self) -> None:
        """Digit dispatches to number literal."""
        result = parse_inline_expression(Cursor("42", 0))
        assert result is not None
        assert isinstance(result.value, NumberLiteral)

    def test_identifier_dispatch(self) -> None:
        """Identifier dispatches to message reference."""
        result = parse_inline_expression(Cursor("msg", 0))
        assert result is not None
        assert isinstance(result.value, MessageReference)

    def test_invalid_char_returns_none(self) -> None:
        """Invalid character returns None."""
        assert parse_inline_expression(Cursor("@", 0)) is None

    def test_inline_expression_past_eof(self) -> None:
        """Cursor past content returns None."""
        result = parse_inline_expression(Cursor("$", 1))
        assert result is None
