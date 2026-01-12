"""Test for branch coverage at line 1585 in parse_placeable.

The branch 1585->1608 represents the case where:
- We have a valid selector expression
- Followed by '-' but NOT '->'
- This is treated as end of expression, not select expression
"""

from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import parse_placeable


class TestBranch1585:
    """Test the uncovered branch at line 1585."""

    def test_function_followed_by_hyphen(self) -> None:
        """Valid function selector, hyphen, then closing brace."""
        # After parsing "NUMBER(42)", cursor at hyphen
        # Function is valid selector, but hyphen not followed by greater-than
        # Line 1585 False branch, fall through to line 1608
        # Expected closing brace but found hyphen, return None
        text = "NUMBER(42)-}"
        cursor = Cursor(text, 0)
        result = parse_placeable(cursor)
        assert result is None

    def test_function_followed_by_hyphen_eof(self) -> None:
        """Valid function selector, hyphen, then EOF."""
        # Line 1585: next_cursor.is_eof = True, False branch
        text = "NUMBER(42)-"
        cursor = Cursor(text, 0)
        result = parse_placeable(cursor)
        assert result is None

    def test_message_ref_followed_by_hyphen(self) -> None:
        """Valid message reference selector, hyphen, then closing brace."""
        # Message references can be selectors too
        # Note: Identifiers can contain hyphens, so "msg-" is valid identifier name
        text = "msg-}"
        cursor = Cursor(text, 0)
        result = parse_placeable(cursor)
        # Result depends on identifier parsing rules
        assert result is not None
