# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_error_recovery.py."""

from tests.syntax_parser_error_recovery_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# TERM REFERENCE ERROR PATHS
# ============================================================================


class TestTermReferenceErrorPaths:
    """Error paths in parse_term_reference."""

    def test_missing_hyphen(self) -> None:
        """No '-' at start."""
        assert parse_term_reference(Cursor("brand", 0)) is None

    def test_identifier_fails_after_hyphen(self) -> None:
        """Identifier parse fails after '-'."""
        assert parse_term_reference(Cursor("-", 0)) is None

    def test_attribute_identifier_fails(self) -> None:
        """Attribute identifier parse fails after '.'."""
        assert parse_term_reference(Cursor("-brand.", 0)) is None

    def test_arguments_parse_fails(self) -> None:
        """Call arguments fail for term args."""
        assert parse_term_reference(
            Cursor("-brand(@)", 0)
        ) is None

    def test_arguments_missing_closing_paren_1449(self) -> None:
        """Lines 1449-1450: Expected ')' after term arguments."""
        result = parse_term_reference(
            Cursor("-brand(case: 'nom'", 0)
        )
        assert result is None

    def test_depth_exceeded_with_arguments(self) -> None:
        """Depth exceeded when parsing term arguments."""
        ctx = ParseContext(max_nesting_depth=2)
        nested = ctx.enter_nesting().enter_nesting()
        result = parse_term_reference(
            Cursor('-brand(case: "nom")', 0), nested
        )
        assert result is None

    def test_without_arguments_at_depth_limit(self) -> None:
        """Term ref without args succeeds at depth limit."""
        ctx = ParseContext(max_nesting_depth=2)
        nested = ctx.enter_nesting().enter_nesting()
        result = parse_term_reference(Cursor("-brand", 0), nested)
        assert result is not None
        assert result.value.id.name == "brand"

    def test_with_arguments_succeeds(self) -> None:
        """Term ref with arguments below depth limit."""
        result = parse_term_reference(
            Cursor('-term(case: "gen")', 0)
        )
        assert result is not None
        assert result.value.arguments is not None
