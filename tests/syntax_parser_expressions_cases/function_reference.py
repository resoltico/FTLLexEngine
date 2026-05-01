# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_expressions.py."""

from tests.syntax_parser_expressions_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# FUNCTION REFERENCE
# ============================================================================


class TestParseFunctionReference:
    """Tests for parse_function_reference paths."""

    def test_valid_function(self) -> None:
        """Valid function reference parses successfully."""
        result = parse_function_reference(Cursor("NUMBER(42)", 0))
        assert result is not None

    def test_function_with_named_args(self) -> None:
        """Function with named arguments parses."""
        result = parse_function_reference(
            Cursor('NUMBER(42, style: "percent")', 0)
        )
        assert result is not None

    def test_missing_opening_paren(self) -> None:
        """Returns None when '(' is missing."""
        assert parse_function_reference(Cursor("FUNC", 0)) is None

    def test_missing_closing_paren(self) -> None:
        """Returns None when ')' is missing."""
        assert parse_function_reference(
            Cursor("FUNC($x", 0)
        ) is None

    def test_no_identifier(self) -> None:
        """Returns None when identifier is missing."""
        assert parse_function_reference(Cursor("  ", 0)) is None

    def test_non_identifier_start(self) -> None:
        """Returns None for non-identifier start."""
        assert parse_function_reference(Cursor("123", 0)) is None

    def test_depth_exceeded(self) -> None:
        """Returns None when nesting depth exceeded."""
        context = ParseContext(max_nesting_depth=1, current_depth=2)
        result = parse_function_reference(
            Cursor("FUNC($x)", 0), context
        )
        assert result is None

    def test_arguments_parse_fails(self) -> None:
        """Returns None when call arguments fail."""
        assert parse_function_reference(
            Cursor("FUNC(@)", 0)
        ) is None

    def test_no_closing_paren_after_args(self) -> None:
        """Function with incomplete arguments."""
        assert parse_function_reference(
            Cursor("NUMBER(", 0)
        ) is None

    def test_invalid_arg_syntax(self) -> None:
        """Function with invalid argument syntax."""
        assert parse_function_reference(
            Cursor("FUNC(,,,)", 0)
        ) is None
