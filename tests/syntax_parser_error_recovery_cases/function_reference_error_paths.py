# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_error_recovery.py."""

from tests.syntax_parser_error_recovery_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# FUNCTION REFERENCE ERROR PATHS
# ============================================================================


class TestFunctionReferenceErrorPaths:
    """Error paths in parse_function_reference."""

    def test_identifier_parse_fails(self) -> None:
        """Non-identifier character at start."""
        assert parse_function_reference(Cursor("123", 0)) is None

    def test_missing_opening_paren(self) -> None:
        """Valid name but no '('."""
        assert parse_function_reference(Cursor("FUNC", 0)) is None

    def test_missing_closing_paren(self) -> None:
        """Arguments but no closing ')'."""
        assert parse_function_reference(Cursor("FUNC($x", 0)) is None

    def test_arguments_parse_fails(self) -> None:
        """Call arguments fail at '@'."""
        assert parse_function_reference(
            Cursor("FUNC(@)", 0)
        ) is None

    def test_depth_exceeded(self) -> None:
        """Nesting depth exceeded."""
        ctx = ParseContext(max_nesting_depth=1, current_depth=2)
        assert parse_function_reference(
            Cursor("FUNC($x)", 0), ctx
        ) is None
