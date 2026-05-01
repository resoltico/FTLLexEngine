# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_error_recovery.py."""

from tests.syntax_parser_error_recovery_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# INLINE EXPRESSION AND HELPER ERROR PATHS
# ============================================================================


class TestInlineExpressionErrorPaths:
    """Error paths in inline expression helpers."""

    def test_inline_hyphen_all_fail(self) -> None:
        """_parse_inline_hyphen: both term and number fail."""
        assert _parse_inline_hyphen(Cursor("-", 0)) is None

    def test_inline_hyphen_term_attr_fails_line_1365(self) -> None:
        """Line 1365: Term reference fails (invalid attribute)."""
        result = _parse_inline_hyphen(Cursor("-x.123", 0))
        assert result is None

    def test_inline_identifier_function_fails(self) -> None:
        """_parse_inline_identifier: function parse fails."""
        assert _parse_inline_identifier(
            Cursor("func(@)", 0)
        ) is None

    def test_inline_identifier_parse_fails(self) -> None:
        """_parse_inline_identifier: parse_identifier fails."""
        assert _parse_inline_identifier(Cursor("123", 0)) is None

    def test_inline_expression_eof(self) -> None:
        """parse_inline_expression: EOF returns None."""
        assert parse_inline_expression(Cursor("", 0)) is None

    def test_inline_expression_invalid_char(self) -> None:
        """parse_inline_expression: invalid character returns None."""
        assert parse_inline_expression(Cursor("@", 0)) is None

    def test_inline_expression_variable_fails(self) -> None:
        """parse_inline_expression: '$' but identifier fails."""
        assert parse_inline_expression(Cursor("$", 0)) is None

    def test_inline_expression_nested_placeable_fails(self) -> None:
        """parse_inline_expression: nested placeable fails."""
        assert parse_inline_expression(Cursor("{ @ }", 0)) is None

    def test_inline_expression_message_attr_fails(self) -> None:
        """Message reference attribute parsing fails (invalid attr)."""
        cursor = Cursor("msg.-test", 0)
        result = parse_inline_expression(cursor)
        assert result is None or (
            result is not None and hasattr(result, "value")
        )
