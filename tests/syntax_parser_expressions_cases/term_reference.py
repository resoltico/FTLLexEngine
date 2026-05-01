# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_expressions.py."""

from tests.syntax_parser_expressions_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# TERM REFERENCE
# ============================================================================


class TestParseTermReference:
    """Tests for parse_term_reference paths."""

    def test_valid_term(self) -> None:
        """Valid term reference parses."""
        result = parse_term_reference(Cursor("-brand", 0))
        assert result is not None
        assert result.value.id.name == "brand"

    def test_term_with_attribute(self) -> None:
        """Term with .attribute access."""
        result = parse_term_reference(Cursor("-brand.short", 0))
        assert result is not None
        assert result.value.attribute is not None

    def test_missing_hyphen(self) -> None:
        """Returns None without '-' prefix."""
        assert parse_term_reference(Cursor("brand", 0)) is None

    def test_no_identifier_after_hyphen(self) -> None:
        """Returns None when identifier missing after '-'."""
        assert parse_term_reference(Cursor("-", 0)) is None

    def test_no_identifier_with_spaces(self) -> None:
        """Returns None with spaces after '-'."""
        assert parse_term_reference(Cursor("-  ", 0)) is None

    def test_attribute_parse_fails(self) -> None:
        """Dot without attribute name returns None."""
        assert parse_term_reference(Cursor("-term.", 0)) is None

    def test_attribute_with_spaces_fails(self) -> None:
        """Dot followed by whitespace returns None."""
        assert parse_term_reference(
            Cursor("-brand.  ", 0)
        ) is None

    def test_arguments_parse_fails(self) -> None:
        """Invalid arguments return None."""
        assert parse_term_reference(
            Cursor("-brand(@)", 0)
        ) is None

    def test_arguments_missing_closing_paren(self) -> None:
        """Missing ')' after term arguments."""
        assert parse_term_reference(
            Cursor("-brand(case: 'nom'", 0)
        ) is None

    def test_missing_closing_paren_no_args(self) -> None:
        """Missing ')' after open paren."""
        assert parse_term_reference(Cursor("-brand(", 0)) is None

    def test_depth_exceeded(self) -> None:
        """Returns None when nesting depth exceeded."""
        context = ParseContext(max_nesting_depth=1, current_depth=2)
        result = parse_term_reference(
            Cursor("-brand(case: 'nom')", 0), context
        )
        assert result is None

    def test_attribute_identifier_parse_fails(self) -> None:
        """Attribute identifier parse fails after dot."""
        assert parse_term_reference(Cursor("-brand.", 0)) is None
