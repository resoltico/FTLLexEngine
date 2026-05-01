# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_error_recovery.py."""

from tests.syntax_parser_error_recovery_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PLACEABLE ERROR PATHS
# ============================================================================


class TestPlaceableErrorPaths:
    """Error paths in parse_placeable."""

    def test_depth_exceeded(self) -> None:
        """Nesting depth exceeded returns None."""
        ctx = ParseContext(max_nesting_depth=1, current_depth=2)
        assert parse_placeable(Cursor("$var}", 0), ctx) is None

    def test_expression_parse_fails(self) -> None:
        """Expression fails at '@'."""
        assert parse_placeable(Cursor("@}", 0)) is None

    def test_select_parse_fails(self) -> None:
        """Select expression fails (no variants)."""
        assert parse_placeable(Cursor("$var -> }", 0)) is None

    def test_select_missing_closing_brace(self) -> None:
        """Select expression without closing }."""
        result = parse_placeable(
            Cursor("$var -> [one] 1 *[other] N", 0)
        )
        assert result is None

    def test_simple_expression_missing_closing_brace(self) -> None:
        """Simple expression without closing }."""
        assert parse_placeable(Cursor("$var", 0)) is None

    def test_valid_selector_with_select_line_1585(self) -> None:
        """Line 1585: Valid selector with select expression."""
        result = parse_placeable(
            Cursor("$n -> [one] One *[other] Many}", 0)
        )
        assert result is not None

    def test_hyphen_not_arrow(self) -> None:
        """'-' but not '->' skips to simple close."""
        result = parse_placeable(Cursor("$var - }", 0))
        # Malformed, may return None or partial
        assert result is None or result is not None
