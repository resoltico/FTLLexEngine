# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_expressions.py."""

from tests.syntax_parser_expressions_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PLACEABLE
# ============================================================================


class TestParsePlaceable:
    """Tests for parse_placeable paths."""

    def test_simple_variable(self) -> None:
        """Parses simple variable placeable."""
        result = parse_placeable(Cursor("$var}", 0))
        assert result is not None
        assert isinstance(result.value.expression, VariableReference)

    def test_depth_exceeded(self) -> None:
        """Returns None when nesting depth exceeded."""
        context = ParseContext(max_nesting_depth=1, current_depth=2)
        assert parse_placeable(
            Cursor("$var}", 0), context
        ) is None

    def test_expression_fails(self) -> None:
        """Invalid expression content returns None."""
        assert parse_placeable(Cursor("@}", 0)) is None

    def test_whitespace_only(self) -> None:
        """Only whitespace inside braces returns None."""
        assert parse_placeable(Cursor("   }", 1)) is None

    def test_empty_content(self) -> None:
        """Empty content returns None."""
        assert parse_placeable(Cursor("}", 0)) is None

    def test_select_valid_selector(self) -> None:
        """Select expression with valid selector."""
        result = parse_placeable(
            Cursor("$x -> [one] 1 *[other] N}", 0)
        )
        assert result is not None

    def test_select_expression_fails(self) -> None:
        """Select expression parse fails (no variants)."""
        assert parse_placeable(Cursor("$var -> }", 0)) is None

    def test_select_missing_closing_brace(self) -> None:
        """Missing '}' after select expression."""
        assert parse_placeable(
            Cursor("$var -> [one] 1 *[other] N", 0)
        ) is None

    def test_simple_expression_missing_brace(self) -> None:
        """Missing '}' after simple expression."""
        assert parse_placeable(Cursor("$var", 0)) is None

    def test_function_followed_by_hyphen(self) -> None:
        """Function selector with hyphen (not ->) returns None."""
        assert parse_placeable(
            Cursor("NUMBER(42)-}", 0)
        ) is None

    def test_function_followed_by_hyphen_eof(self) -> None:
        """Function selector with hyphen at EOF returns None."""
        assert parse_placeable(
            Cursor("NUMBER(42)-", 0)
        ) is None

    def test_message_ref_with_hyphen_in_name(self) -> None:
        """Message ref with hyphen in identifier name."""
        result = parse_placeable(Cursor("msg-}", 0))
        assert result is not None

    def test_nested_opening_braces(self) -> None:
        """Multiple nested opening braces fail."""
        assert parse_placeable(Cursor("{{{", 1)) is None

    def test_incomplete_expression(self) -> None:
        """Incomplete expression returns None."""
        assert parse_placeable(Cursor("NUMBER", 0)) is None
