# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_error_recovery.py."""

from tests.syntax_parser_error_recovery_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# DEFENSIVE MOCKING TESTS (UNREACHABLE CODE PATHS)
# ============================================================================


class TestDefensiveMocking:
    """Defensive None checks for unreachable code paths.

    These lines are structurally unreachable in normal execution but
    exist as guardrails against future refactoring.
    """

    def test_parse_message_attrs_returns_none(self) -> None:
        """parse_message_attributes returns None (defensive)."""
        with patch(
            "ftllexengine.syntax.parser.entries"
            ".parse_message_attributes"
        ) as mock:
            mock.return_value = None
            assert parse_message(
                Cursor("hello = value", 0)
            ) is None

    def test_parse_attribute_pattern_returns_none(self) -> None:
        """parse_pattern returns None in parse_attribute (defensive)."""
        with patch(
            "ftllexengine.syntax.parser.entries.parse_pattern"
        ) as mock:
            mock.return_value = None
            assert parse_attribute(
                Cursor(".attr = value", 0)
            ) is None

    def test_parse_term_pattern_returns_none(self) -> None:
        """parse_pattern returns None in parse_term (defensive)."""
        with patch(
            "ftllexengine.syntax.parser.entries.parse_pattern"
        ) as mock:
            mock.return_value = None
            assert parse_term(
                Cursor("-brand = value", 0)
            ) is None

    def test_parse_term_attrs_returns_none_line_2038(self) -> None:
        """Line 2038: parse_message_attributes returns None in term."""
        with patch(
            "ftllexengine.syntax.parser.entries"
            ".parse_message_attributes"
        ) as mock:
            mock.return_value = None
            assert parse_term(
                Cursor("-brand = value", 0)
            ) is None

    def test_parse_message_pattern_returns_none(self) -> None:
        """parse_pattern returns None in parse_message (defensive)."""
        with patch(
            "ftllexengine.syntax.parser.entries.parse_pattern"
        ) as mock:
            mock.return_value = None
            assert parse_message(
                Cursor("hello = value", 0)
            ) is None
