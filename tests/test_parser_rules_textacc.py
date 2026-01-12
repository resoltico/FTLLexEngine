"""Targeted tests for text_acc accumulation paths in parse_simple_pattern and parse_pattern.

These tests specifically target lines 505-510 and 559-563 in parse_simple_pattern,
and lines 691 and 746 in parse_pattern.
"""

from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import parse_pattern, parse_simple_pattern


class TestParseSimplePatternTextAccLinesFiveZeroFiveToFiveZeroSeven:
    """Target lines 505-507: Merge accumulated text with last non-placeable element."""

    def test_text_then_continuation_then_placeable(self) -> None:
        """Lines 505-507: text, newline + spaces, then immediately placeable."""
        # Flow: Parse "hello" -> TextElement, hit '\n' (indented continuation), accumulate
        # "\n" to text_acc, skip spaces, hit '{'. text_acc has content, elements exist,
        # last is not Placeable, should hit lines 505-507.
        text = "hello\n    {$x}"
        cursor = Cursor(text, 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        # The "\n" should be merged with "hello"
        assert len(result.value.elements) >= 2


class TestParseSimplePatternTextAccLinesFiveZeroEightToFiveOneZero:
    """Target lines 508-510: Append accumulated text as new element."""

    def test_continuation_then_placeable_no_prior_elements(self) -> None:
        """Lines 508-510: Pattern starts with continuation then placeable."""
        # Flow: Start with newline and indentation, is_indented_continuation accumulates
        # newline to text_acc, skip spaces, hit opening brace. text_acc has content,
        # elements is empty, should hit lines 508-510.
        text = "\n    {$x}"
        cursor = Cursor(text, 0)
        result = parse_simple_pattern(cursor)
        assert result is not None

    def test_placeable_then_continuation_then_placeable(self) -> None:
        """Lines 508-510: placeable, continuation, then placeable."""
        # Flow: Parse first placeable (last element is Placeable), hit newline with
        # indentation (accumulate to text_acc), skip spaces, hit opening brace.
        # text_acc has content, last element is Placeable, should hit lines 508-510.
        text = "{$a}\n    {$b}"
        cursor = Cursor(text, 0)
        result = parse_simple_pattern(cursor)
        assert result is not None


class TestParseSimplePatternTextAccLinesFiveFiveNineToFiveSixOne:
    """Target lines 559-561: Finalize accumulated text merged with last element."""

    def test_text_then_continuation_at_end(self) -> None:
        """Lines 559-561: Pattern ends with text, continuation."""
        # Flow: Parse "hello" as TextElement, hit newline with indentation (accumulate
        # to text_acc), skip spaces, reach EOF. For 559-561, text_acc must have
        # content at pattern end (continuation but no text after it).
        text = "hello\n    "
        cursor = Cursor(text, 0)
        result = parse_simple_pattern(cursor)
        assert result is not None


class TestParseSimplePatternTextAccLinesFiveSixTwoToFiveSixThree:
    """Target lines 562-563: Finalize accumulated text as new element."""

    def test_continuation_at_end_no_prior_elements(self) -> None:
        """Lines 562-563: Pattern ends with just continuation."""
        # Flow: Hit newline (is_indented_continuation accumulates newline to text_acc),
        # skip spaces, reach EOF. Exit loop, text_acc has content, elements is empty,
        # should hit lines 562-563.
        text = "\n    "
        cursor = Cursor(text, 0)
        result = parse_simple_pattern(cursor)
        assert result is not None

    def test_placeable_then_continuation_at_end(self) -> None:
        """Lines 562-563: placeable then continuation at EOF."""
        # Flow: Parse placeable (last is Placeable), hit newline with indentation
        # (accumulate to text_acc), skip spaces, reach EOF. Exit loop, text_acc has
        # content, last is Placeable, should hit lines 562-563.
        text = "{$x}\n    "
        cursor = Cursor(text, 0)
        result = parse_simple_pattern(cursor)
        assert result is not None


class TestParsePatternLine691:
    """Target line 691: Accumulated text as new element in parse_pattern."""

    def test_pattern_continuation_as_new_element(self) -> None:
        """Line 691: parse_pattern accumulated text as new element."""
        # Similar logic to parse_simple_pattern
        # Need continuation followed by new text, with no prior elements or last is Placeable
        text = "{$x}\n    text"
        cursor = Cursor(text, 0)
        result = parse_pattern(cursor)
        assert result is not None


class TestParsePatternLine746:
    """Target line 746: Finalize accumulated text as new element in parse_pattern."""

    def test_pattern_finalize_as_new_element(self) -> None:
        """Line 746: parse_pattern finalize accumulated as new element."""
        # Pattern ending with continuation after placeable
        text = "{$x}\n    "
        cursor = Cursor(text, 0)
        result = parse_pattern(cursor)
        assert result is not None


class TestMultilineContinuationPatterns:
    """Additional multi-line continuation patterns for comprehensive coverage."""

    def test_complex_continuation_before_placeable(self) -> None:
        """Complex pattern with multiple continuations."""
        text = "start\n    line1\n    line2\n    {$x}"
        cursor = Cursor(text, 0)
        result = parse_simple_pattern(cursor)
        assert result is not None

    def test_multiple_placeables_with_continuations(self) -> None:
        """Multiple placeables separated by continuations."""
        text = "{$a}\n    {$b}\n    {$c}"
        cursor = Cursor(text, 0)
        result = parse_simple_pattern(cursor)
        assert result is not None

    def test_pattern_with_blank_continuation_lines(self) -> None:
        """Pattern with blank lines between continuations."""
        text = "text\n\n    continued"
        cursor = Cursor(text, 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
