# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_error_recovery.py."""

from tests.syntax_parser_error_recovery_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# ARGUMENT EXPRESSION ERROR PATHS
# ============================================================================


class TestArgumentExpressionErrorPaths:
    """Error paths in parse_argument_expression."""

    def test_eof_returns_none(self) -> None:
        """EOF at argument position."""
        assert parse_argument_expression(Cursor("", 0)) is None

    def test_invalid_char_returns_none(self) -> None:
        """Invalid character (@) returns None."""
        assert parse_argument_expression(Cursor("@", 0)) is None

    def test_term_ref_fails_line_1105(self) -> None:
        """Line 1105: Term reference parse fails (hyphen + identifier)."""
        result = parse_argument_expression(Cursor("-x.123)", 0))
        assert result is None

    def test_term_ref_bare_hyphen_fails(self) -> None:
        """Hyphen followed by ')' fails term and number parse."""
        assert parse_argument_expression(Cursor("-)", 0)) is None

    def test_number_fails_defensive_line_1120(self) -> None:
        """Line 1120: parse_number returns None on digit (defensive).

        Requires mocking because parse_number is robust for digit start.
        """
        with patch(
            "ftllexengine.syntax.parser.expressions.parse_number"
        ) as mock:
            mock.return_value = ParseError("forced failure", Cursor("9)", 0))
            assert parse_argument_expression(Cursor("9)", 0)) is None

    def test_identifier_fails_defensive_line_1139(self) -> None:
        """Line 1139: parse_identifier returns None (defensive).

        Requires mocking because is_identifier_start guarantees success.
        """
        with patch(
            "ftllexengine.syntax.parser.expressions.parse_identifier"
        ) as mock:
            mock.return_value = ParseError("forced failure", Cursor("x)", 0))
            assert parse_argument_expression(Cursor("x)", 0)) is None

    def test_function_ref_fails_line_1150(self) -> None:
        """Line 1150: parse_function_reference returns None."""
        assert parse_argument_expression(
            Cursor("FUNC(@)", 0)
        ) is None

    def test_function_ref_succeeds(self) -> None:
        """Function reference parsing succeeds."""
        result = parse_argument_expression(Cursor("NUMBER(42)", 0))
        assert result is not None

    def test_uppercase_no_paren_is_message_ref(self) -> None:
        """Uppercase identifier without '(' is MessageReference."""
        result = parse_argument_expression(Cursor("NUMBER", 0))
        assert result is not None
        assert isinstance(result.value, MessageReference)
        assert result.value.id.name == "NUMBER"

    def test_uppercase_open_paren_at_eof(self) -> None:
        """Uppercase + '(' but incomplete call."""
        assert parse_argument_expression(Cursor("NUMBER(", 0)) is None

    def test_negative_number_succeeds(self) -> None:
        """Negative number parses as NumberLiteral."""
        result = parse_argument_expression(Cursor("-123", 0))
        assert result is not None
        assert isinstance(result.value, NumberLiteral)

    def test_positive_number_succeeds(self) -> None:
        """Digit-start parses as NumberLiteral."""
        result = parse_argument_expression(Cursor("42", 0))
        assert result is not None
        assert isinstance(result.value, NumberLiteral)

    def test_string_literal_argument(self) -> None:
        """String literal in argument position."""
        result = parse_argument_expression(Cursor('"text"', 0))
        assert result is not None
        assert isinstance(result.value, StringLiteral)

    def test_inline_placeable_argument(self) -> None:
        """Inline placeable { $var } in argument position."""
        result = parse_argument_expression(Cursor("{ $var }", 0))
        assert result is not None
        assert isinstance(result.value, Placeable)

    def test_identifier_with_underscore(self) -> None:
        """Identifier can contain underscore after letter."""
        result = parse_argument_expression(Cursor("my_var", 0))
        assert result is not None
        assert isinstance(result.value, MessageReference)
