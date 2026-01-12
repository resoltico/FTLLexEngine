"""Precision tests for the final 5 uncovered lines.

These tests use specific patterns designed to hit exact code paths.
"""

from unittest.mock import patch

from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import (
    _parse_inline_hyphen,
    parse_argument_expression,
    parse_pattern,
    parse_placeable,
)


class TestLine691:
    """Precision test for line 691 in parse_pattern."""

    def test_line_691_placeable_continuation_placeable(self) -> None:
        """Line 691: {placeable}\\n SPACES{placeable}."""
        # Flow: Parse{$a}, hit \\n, is_indented_continuation=True,
        # accumulate "\\n" to text_acc, skip spaces, now at '{',
        # text_acc.has_content()=True, last element is Placeable,
        # should execute line 691
        text = "{$a}\n    {$b}"
        cursor = Cursor(text, 0)
        result = parse_pattern(cursor)
        assert result is not None

    def test_line_691_start_continuation_placeable(self) -> None:
        """Line 691: \\n SPACES{placeable} at start."""
        # Flow: Hit \\n at start, is_indented_continuation=True,
        # accumulate "\\n" to text_acc, skip spaces, now at '{',
        # text_acc.has_content()=True, elements is empty,
        # should execute line 691
        text = "\n    {$x}"
        cursor = Cursor(text, 0)
        result = parse_pattern(cursor)
        assert result is not None


class TestLine990:
    """Precision test for line 990."""

    def test_line_990_term_ref_fails(self) -> None:
        """Line 990: Hyphen + identifier_start but term parsing fails."""
        # "-x.123" - 'x' is identifier_start, so we call parse_term_reference
        # Inside parse_term_reference, '.' triggers attribute parsing
        # But '123' is not valid identifier start, parse_identifier fails
        # parse_term_reference returns None at line 1289
        # Back to parse_argument_expression line 990, return None
        cursor = Cursor("-x.123)", 0)
        result = parse_argument_expression(cursor)
        assert result is None


class TestLine1024:
    """Precision test for line 1024 (defensive/unreachable)."""

    def test_line_1024_defensive_code(self) -> None:
        """Line 1024: Defensive code - parse_identifier fails after is_identifier_start passes."""
        # This line is likely unreachable in normal execution
        # If is_identifier_start returns True, parse_identifier should always succeed
        # This is defensive code for unexpected edge cases

        # Try to trigger with mocking
        with patch("ftllexengine.syntax.parser.rules.parse_identifier") as mock_id:
            mock_id.return_value = None  # Force failure
            cursor = Cursor("x)", 0)
            result = parse_argument_expression(cursor)
            # Should hit line 1024
            assert result is None


class TestLine1035:
    """Precision test for line 1035."""

    def test_line_1035_function_succeeds(self) -> None:
        """Line 1035: Function reference parsing SUCCEEDS."""
        # Line 1035 is the success path when parse_function_reference returns non-None
        cursor = Cursor("NUMBER(42)", 0)
        result = parse_argument_expression(cursor)
        assert result is not None

    def test_line_1034_function_fails(self) -> None:
        """Line 1034: Function reference parsing fails."""
        cursor = Cursor("FUNC(@)", 0)
        result = parse_argument_expression(cursor)
        assert result is None


class TestLine1365:
    """Precision test for line 1365."""

    def test_line_1365_term_ref_fails_in_inline(self) -> None:
        """Line 1365: Hyphen + identifier_start but term reference fails."""
        # Same scenario as line 990: term reference with invalid attribute
        cursor = Cursor("-x.123", 0)
        result = _parse_inline_hyphen(cursor)
        assert result is None


class TestLine1585:
    """Precision test for line 1585 branch."""

    def test_line_1585_valid_selector_with_select(self) -> None:
        """Line 1585->1608: Valid selector with select expression."""
        cursor = Cursor("$n -> [one] One *[other] Many}", 0)
        result = parse_placeable(cursor)
        assert result is not None


class TestAllFiveLines:
    """Comprehensive test exercising all 5 remaining lines."""

    def test_all_remaining_lines(self) -> None:
        """Test all 5 remaining uncovered lines."""
        # Line 691
        r1 = parse_pattern(Cursor("{$x}\n    {$y}", 0))
        assert r1 is not None

        # Line 990
        r2 = parse_argument_expression(Cursor("-x.123)", 0))
        assert r2 is None

        # Line 1024 (defensive/unreachable) - tested with mocking separately

        # Line 1035 - function reference success
        r3 = parse_argument_expression(Cursor("NUMBER(42)", 0))
        assert r3 is not None

        # Line 1365
        r5 = _parse_inline_hyphen(Cursor("-x.123", 0))
        assert r5 is None

        # Line 1585
        r6 = parse_placeable(Cursor("$v -> [a] A *[b] B}", 0))
        assert r6 is not None
