"""Targeted tests for parse_simple_pattern text accumulator paths (lines 561-562, 605).

parse_simple_pattern is called from parse_variant for variant values in select expressions.
These tests exercise the specific text_acc finalization paths that were previously uncovered.
"""

from __future__ import annotations

from ftllexengine.syntax.ast import Message, Placeable, SelectExpression
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import ParseContext, parse_message


class TestParseSimplePatternTextAccumulatorLines561To562:
    """Cover lines 561-562: finalize text_acc before placeable in variant value."""

    def test_variant_with_continuation_extra_spaces_then_placeable(self) -> None:
        """Variant value: second continuation with extra spaces before placeable.

        This is the critical path for lines 561-562 in parse_simple_pattern:
        1. First continuation sets common indent (e.g., 4 spaces)
        2. Second continuation has MORE indent (e.g., 8 spaces) with placeable
        3. Extra spaces (8-4=4) get added to text_acc via line 553: text_acc.add(extra_spaces)
        4. Then immediately encounters placeable `{` on same continuation line
        5. Lines 561-562 finalize the accumulated extra spaces before the placeable

        FTL structure:
        msg = {$n ->
            [one] Line1
                Line2
                    {$var}
            *[other] Items
        }

        Parsing [one] variant value:
        - Initial: "Line1"
        - First continuation: "    Line2" (4 spaces) sets common_indent=4
        - Second continuation: "        {$var}" (8 spaces) creates extra_spaces="    " (4 spaces)
        - Extra spaces accumulated in text_acc
        - Then `{` is encountered, triggering lines 561-562 to finalize accumulated spaces
        """
        source = """msg = {$n ->
    [one] Line1
        Line2
            {$var}
    *[other] Items
}"""
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())

        assert result is not None
        message = result.value
        assert isinstance(message, Message)
        assert message.value is not None
        placeable = message.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, SelectExpression)
        # Variant [one] should have parsed with extra spaces preserved before placeable

    def test_variant_continuation_spaces_only_then_inline_placeable(self) -> None:
        """Variant with blank continuation creating extra_spaces, then text+placeable.

        Pattern that ensures text_acc has content when hitting placeable:
        1. First line of variant: "Start"
        2. Continuation with only spaces (creates common indent)
        3. Another continuation with extra spaces + text + placeable
        """
        source = """msg = {$n ->
    [one] Start

            text {$x}
    *[other] End
}"""
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())

        assert result is not None
        message = result.value
        assert isinstance(message, Message)


class TestParseSimplePatternTextAccumulatorLine605:
    """Cover line 605: finalize text_acc at end of parse_simple_pattern."""

    def test_variant_ending_with_only_accumulated_extra_spaces(self) -> None:
        """Variant value ends with continuation line that has ONLY extra spaces.

        This is the critical path for line 605 in parse_simple_pattern:
        1. First continuation sets common indent
        2. Second continuation has ONLY extra spaces (no text/placeable after)
        3. Extra spaces accumulated in text_acc
        4. Next line is NOT a continuation (next variant or close brace)
        5. Loop exits, line 605 finalizes remaining accumulated extra_spaces

        FTL structure:
        msg = {$n ->
            [one] Text
                MoreText

            *[other] Items
        }

        The [one] variant:
        - Initial: "Text"
        - First continuation: "    MoreText" (4 spaces) sets common_indent=4
        - Second continuation: "            " (12 spaces, ONLY spaces, no content)
          - Skip first 4 (common), extra_spaces="        " (8 spaces)
          - text_acc.add("        ")
          - After skipping all spaces, cursor at newline
          - Next line "*[other]" is NOT indented continuation
          - Loop breaks at line 555
        - Line 605 finalizes the accumulated 8 spaces
        """
        # CRITICAL: The line after "MoreText" must have ONLY spaces (more than common indent)
        # Followed by a line with LESS indent (so it's not a continuation)
        # Using explicit string construction to ensure exact spacing
        variant_one = "[one] Text\n        MoreText\n                "  # 16 spaces on last line
        variant_other = "*[other] Items"
        source = f"msg = {{$n ->\n    {variant_one}\n    {variant_other}\n}}"
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())

        assert result is not None
        message = result.value
        assert isinstance(message, Message)
        assert message.value is not None

    def test_variant_with_extra_spaces_ending_at_close_brace(self) -> None:
        """Variant value with trailing extra spaces ending at `}`.

        Variant is last in select expression, ends with accumulated spaces
        that need finalization when parse_simple_pattern hits `}`.
        """
        source = """msg = {$n ->
    *[other] Text

}"""
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())

        assert result is not None
        message = result.value
        assert isinstance(message, Message)

    def test_multiline_variant_complex_spacing_finalization(self) -> None:
        """Complex variant with multiple continuations ending with accumulated spaces.

        This creates a realistic scenario where:
        1. Multiple continuation lines establish common indent
        2. Final continuation has extra spaces but no content
        3. Extra spaces must be finalized at pattern end
        """
        source = """msg = {$count ->
    [one] Line one
        Line two
            Line three

    *[other] Other
}"""
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())

        assert result is not None
        message = result.value
        assert isinstance(message, Message)
        assert message.value is not None
        placeable = message.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, SelectExpression)
