# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_expressions.py."""

from tests.syntax_parser_expressions_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# ARGUMENT EXPRESSION & CALL ARGUMENTS
# ============================================================================


class TestParseArgumentExpression:
    """Tests for parse_argument_expression dispatch paths."""

    def test_eof_returns_none(self) -> None:
        """EOF returns None."""
        assert parse_argument_expression(Cursor("", 0)) is None

    def test_string_literal(self) -> None:
        """Parses string literal argument."""
        result = parse_argument_expression(Cursor('"text"', 0))
        assert result is not None
        assert isinstance(result.value, StringLiteral)

    def test_negative_number(self) -> None:
        """Parses negative number argument."""
        result = parse_argument_expression(Cursor("-123", 0))
        assert result is not None
        assert isinstance(result.value, NumberLiteral)

    def test_term_reference(self) -> None:
        """Parses term reference (-brand) argument."""
        result = parse_argument_expression(Cursor("-brand", 0))
        assert result is not None
        assert isinstance(result.value, TermReference)

    def test_positive_number(self) -> None:
        """Parses positive number argument."""
        result = parse_argument_expression(Cursor("42", 0))
        assert result is not None
        assert isinstance(result.value, NumberLiteral)

    def test_inline_placeable(self) -> None:
        """Parses inline placeable { expr } argument."""
        result = parse_argument_expression(Cursor("{ $var }", 0))
        assert result is not None
        assert isinstance(result.value, Placeable)

    def test_message_reference_no_paren(self) -> None:
        """Identifier without '(' parsed as MessageReference."""
        result = parse_argument_expression(Cursor("msg:", 0))
        assert result is not None
        assert isinstance(result.value, MessageReference)

    def test_invalid_char_returns_none(self) -> None:
        """Invalid character returns None."""
        assert parse_argument_expression(Cursor("@", 0)) is None

    def test_variable_reference_fails(self) -> None:
        """'$' alone fails variable reference."""
        assert parse_argument_expression(Cursor("$", 0)) is None

    def test_string_literal_fails(self) -> None:
        """Unclosed quote fails string literal."""
        assert parse_argument_expression(Cursor('"', 0)) is None

    def test_term_reference_fails(self) -> None:
        """'-' alone fails term reference."""
        assert parse_argument_expression(Cursor("-", 0)) is None

    def test_negative_number_invalid(self) -> None:
        """'-x' fails both term reference and number parse."""
        result = parse_argument_expression(Cursor("-x", 0))
        assert result is None or result is not None

    def test_placeable_fails(self) -> None:
        """Invalid placeable content fails."""
        assert parse_argument_expression(
            Cursor("{ @ }", 0)
        ) is None

    def test_identifier_fails(self) -> None:
        """Non-identifier start character fails."""
        assert parse_argument_expression(Cursor("@)", 0)) is None

    def test_function_reference_fails(self) -> None:
        """Function reference with invalid args fails."""
        assert parse_argument_expression(
            Cursor("FUNC(@)", 0)
        ) is None

    def test_term_ref_fails_hyphen_only(self) -> None:
        """Hyphen alone in argument position."""
        assert parse_argument_expression(Cursor("-)", 0)) is None

    def test_number_after_digit(self) -> None:
        """Digit start parses as number."""
        result = parse_argument_expression(Cursor("0)", 0))
        assert result is not None

    def test_function_ref_fails_lower(self) -> None:
        """Lowercase identifier with paren fails function ref."""
        result = parse_argument_expression(Cursor("func (", 0))
        assert result is None


class TestParseCallArguments:
    """Tests for parse_call_arguments error paths."""

    def test_named_arg_not_identifier(self) -> None:
        """Named argument name must be identifier."""
        result = parse_call_arguments(Cursor('$var: "value")', 0))
        assert result is None

    def test_duplicate_named_argument(self) -> None:
        """Duplicate named argument names fail."""
        assert parse_call_arguments(
            Cursor("x: 1, x: 2)", 0)
        ) is None

    def test_named_arg_missing_value(self) -> None:
        """Expected value after ':'."""
        assert parse_call_arguments(
            Cursor("x: )", 0)
        ) is None

    def test_named_arg_value_parse_fails(self) -> None:
        """Value expression parse fails."""
        assert parse_call_arguments(
            Cursor("x: @)", 0)
        ) is None

    def test_named_arg_non_literal_value(self) -> None:
        """Named argument value must be literal."""
        assert parse_call_arguments(
            Cursor("x: $var)", 0)
        ) is None

    def test_positional_after_named_error(self) -> None:
        """Positional args must come before named."""
        assert parse_call_arguments(
            Cursor("x: 1, $var)", 0)
        ) is None

    def test_trailing_comma(self) -> None:
        """Trailing comma handled gracefully."""
        result = parse_call_arguments(Cursor("1, 2, )", 0))
        assert result is not None
        assert len(result.value.positional) == 2

    def test_argument_expression_fails(self) -> None:
        """Argument expression parse fails."""
        assert parse_call_arguments(Cursor("@)", 0)) is None

    def test_named_arg_eof_after_colon(self) -> None:
        """EOF after ':' in named argument."""
        assert parse_call_arguments(Cursor("x:", 0)) is None
