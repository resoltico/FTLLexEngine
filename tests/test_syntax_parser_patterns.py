"""Tests for parser pattern and whitespace handling.

Tests whitespace utilities (skip_blank_inline, skip_blank,
is_indented_continuation, skip_multiline_pattern_start) and pattern
parsing (parse_pattern, parse_simple_pattern) including multiline
continuation, blank line handling, text accumulation, variant delimiter
lookahead, and CRLF normalization.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from hypothesis import event, example, given
from hypothesis import strategies as st

from ftllexengine import parse_ftl
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.ast import (
    Message,
    Pattern,
    Placeable,
    SelectExpression,
    Term,
    TextElement,
)
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    parse_message,
    parse_pattern,
    parse_simple_pattern,
    parse_variant,
)
from ftllexengine.syntax.parser.whitespace import (
    is_indented_continuation,
    skip_blank,
    skip_blank_inline,
    skip_multiline_pattern_start,
)

# ============================================================================
# WHITESPACE UTILITIES
# ============================================================================


class TestSkipBlankInline:
    """Tests for skip_blank_inline (U+0020 only, per FTL spec)."""

    def test_no_spaces(self) -> None:
        """Returns same position when no spaces."""
        cursor = Cursor(source="hello", pos=0)
        assert skip_blank_inline(cursor).pos == 0

    def test_leading_spaces(self) -> None:
        """Skips leading spaces."""
        cursor = Cursor(source="   hello", pos=0)
        result = skip_blank_inline(cursor)
        assert result.pos == 3
        assert result.current == "h"

    def test_all_spaces(self) -> None:
        """Handles all-space string."""
        cursor = Cursor(source="     ", pos=0)
        assert skip_blank_inline(cursor).is_eof is True

    def test_stops_at_tab(self) -> None:
        """Does NOT skip tabs."""
        cursor = Cursor(source="  \thello", pos=0)
        result = skip_blank_inline(cursor)
        assert result.pos == 2
        assert result.current == "\t"

    def test_stops_at_newline(self) -> None:
        """Does NOT skip newlines."""
        cursor = Cursor(source="  \nhello", pos=0)
        result = skip_blank_inline(cursor)
        assert result.pos == 2
        assert result.current == "\n"

    def test_at_eof(self) -> None:
        """Handles EOF."""
        cursor = Cursor(source="", pos=0)
        assert skip_blank_inline(cursor).is_eof


class TestSkipBlank:
    """Tests for skip_blank (spaces and line endings)."""

    def test_no_whitespace(self) -> None:
        """Returns same position when no whitespace."""
        cursor = Cursor(source="hello", pos=0)
        assert skip_blank(cursor).pos == 0

    def test_spaces_only(self) -> None:
        """Skips spaces."""
        cursor = Cursor(source="   hello", pos=0)
        result = skip_blank(cursor)
        assert result.pos == 3
        assert result.current == "h"

    def test_newlines_only(self) -> None:
        """Skips newlines."""
        cursor = Cursor(source="\n\nhello", pos=0)
        result = skip_blank(cursor)
        assert result.pos == 2
        assert result.current == "h"

    def test_mixed_whitespace(self) -> None:
        """Skips mixed spaces and newlines."""
        cursor = Cursor(source="  \n   hello", pos=0)
        result = skip_blank(cursor)
        assert result.pos == 6
        assert result.current == "h"

    def test_all_whitespace(self) -> None:
        """Handles all-whitespace string."""
        cursor = Cursor(source=" \n ", pos=0)
        assert skip_blank(cursor).is_eof is True

    def test_stops_at_tab(self) -> None:
        """Does NOT skip tabs."""
        cursor = Cursor(source=" \n\thello", pos=0)
        result = skip_blank(cursor)
        assert result.pos == 2
        assert result.current == "\t"

    def test_normalized_crlf(self) -> None:
        """Handles CRLF normalized to LF."""
        cursor = Cursor(source="\nhello", pos=0)
        result = skip_blank(cursor)
        assert result.pos == 1
        assert result.current == "h"

    def test_at_eof(self) -> None:
        """Handles EOF."""
        cursor = Cursor(source="", pos=0)
        assert skip_blank(cursor).is_eof


class TestIsIndentedContinuation:
    """Tests for is_indented_continuation detection."""

    def test_true_for_indented_line(self) -> None:
        """Returns True for indented line after newline."""
        cursor = Cursor(source="\n  hello", pos=0)
        assert is_indented_continuation(cursor) is True

    def test_false_no_indentation(self) -> None:
        """Returns False without indentation."""
        cursor = Cursor(source="\nhello", pos=0)
        assert is_indented_continuation(cursor) is False

    def test_false_bracket(self) -> None:
        """Returns False for line starting with [ (variant)."""
        cursor = Cursor(source="\n  [variant]", pos=0)
        assert is_indented_continuation(cursor) is False

    def test_false_asterisk(self) -> None:
        """Returns False for line starting with * (default variant)."""
        cursor = Cursor(source="\n  *[default]", pos=0)
        assert is_indented_continuation(cursor) is False

    def test_false_dot(self) -> None:
        """Returns False for line starting with . (attribute)."""
        cursor = Cursor(source="\n  .attribute", pos=0)
        assert is_indented_continuation(cursor) is False

    def test_false_not_at_newline(self) -> None:
        """Returns False when not at newline."""
        cursor = Cursor(source="hello", pos=0)
        assert is_indented_continuation(cursor) is False

    def test_false_at_eof(self) -> None:
        """Returns False at EOF."""
        cursor = Cursor(source="", pos=0)
        assert is_indented_continuation(cursor) is False

    def test_normalized_line_ending(self) -> None:
        """Works with normalized LF line endings."""
        cursor = Cursor(source="\n  hello", pos=0)
        assert is_indented_continuation(cursor) is True

    def test_eof_after_newline(self) -> None:
        """Returns False for newline at EOF."""
        cursor = Cursor(source="\n", pos=0)
        assert is_indented_continuation(cursor) is False

    def test_only_spaces_after_newline(self) -> None:
        """Empty indented line is considered a valid continuation."""
        cursor = Cursor(source="\n   ", pos=0)
        assert is_indented_continuation(cursor) is True

    def test_tab_indentation_rejected(self) -> None:
        """Returns False for tab indentation."""
        cursor = Cursor(source="\n\thello", pos=0)
        assert is_indented_continuation(cursor) is False


class TestSkipMultilinePatternStart:
    """Tests for skip_multiline_pattern_start."""

    def test_inline_pattern(self) -> None:
        """Handles inline pattern (no newline)."""
        cursor = Cursor(source="  value", pos=0)
        new_cursor, indent = skip_multiline_pattern_start(cursor)
        assert new_cursor.pos == 2
        assert new_cursor.current == "v"
        assert indent == 0

    def test_multiline_pattern(self) -> None:
        """Handles multiline pattern (newline + indent)."""
        cursor = Cursor(source="\n  value", pos=0)
        new_cursor, indent = skip_multiline_pattern_start(cursor)
        assert new_cursor.pos == 3
        assert new_cursor.current == "v"
        assert indent == 2

    def test_no_continuation(self) -> None:
        """Stops at non-continuation newline."""
        cursor = Cursor(source="\nvalue", pos=0)
        new_cursor, indent = skip_multiline_pattern_start(cursor)
        assert new_cursor.pos == 0
        assert new_cursor.current == "\n"
        assert indent == 0

    def test_empty_input(self) -> None:
        """Handles empty input."""
        cursor = Cursor(source="", pos=0)
        new_cursor, indent = skip_multiline_pattern_start(cursor)
        assert new_cursor.is_eof
        assert indent == 0

    def test_no_leading_spaces(self) -> None:
        """Handles no leading spaces."""
        cursor = Cursor(source="value", pos=0)
        new_cursor, indent = skip_multiline_pattern_start(cursor)
        assert new_cursor.pos == 0
        assert new_cursor.current == "v"
        assert indent == 0

    def test_normalized_line_ending(self) -> None:
        """Handles normalized LF line endings."""
        cursor = Cursor(source="\n  value", pos=0)
        new_cursor, indent = skip_multiline_pattern_start(cursor)
        assert new_cursor.current == "v"
        assert indent == 2

    def test_stops_at_bracket(self) -> None:
        """Stops at bracket (variant marker)."""
        cursor = Cursor(source="\n  [variant]", pos=0)
        new_cursor, indent = skip_multiline_pattern_start(cursor)
        assert new_cursor.pos == 0
        assert new_cursor.current == "\n"
        assert indent == 0

    def test_inline_spaces_then_newline(self) -> None:
        """Handles inline spaces then newline."""
        cursor = Cursor(source="  \nvalue", pos=0)
        new_cursor, indent = skip_multiline_pattern_start(cursor)
        assert new_cursor.pos == 2
        assert new_cursor.current == "\n"
        assert indent == 0

    def test_only_newline(self) -> None:
        """Handles only newline."""
        cursor = Cursor(source="\n", pos=0)
        new_cursor, indent = skip_multiline_pattern_start(cursor)
        assert new_cursor.pos == 0
        assert indent == 0


class TestWhitespaceSpecCompliance:
    """Spec compliance, integration, and edge cases for whitespace."""

    def test_blank_inline_only_u0020(self) -> None:
        """blank_inline ONLY accepts U+0020 (space)."""
        assert skip_blank_inline(Cursor("   text", 0)).pos == 3
        assert skip_blank_inline(Cursor("\ttext", 0)).pos == 0

    def test_blank_accepts_lf(self) -> None:
        """blank accepts LF line endings."""
        assert skip_blank(Cursor("\ntext", 0)).current == "t"

    def test_blank_rejects_cr(self) -> None:
        """Standalone CR is NOT whitespace per Fluent spec."""
        assert skip_blank(Cursor("\rtext", 0)).current == "\r"

    def test_continuation_special_chars(self) -> None:
        """Special starting characters correctly identified."""
        assert is_indented_continuation(Cursor("\n [", 0)) is False
        assert is_indented_continuation(Cursor("\n *", 0)) is False
        assert is_indented_continuation(Cursor("\n .", 0)) is False
        assert is_indented_continuation(Cursor("\n a", 0)) is True

    def test_carriage_return_not_whitespace(self) -> None:
        """CR alone is not skipped by skip_blank."""
        cursor = Cursor(source="\rhello", pos=0)
        assert skip_blank(cursor).current == "\r"

    def test_inline_pattern_integration(self) -> None:
        """Simulate parsing message with inline pattern."""
        cursor = Cursor(source="hello = World", pos=5)
        cursor = skip_blank_inline(cursor)
        assert cursor.current == "="
        cursor = cursor.advance()
        cursor, indent = skip_multiline_pattern_start(cursor)
        assert cursor.current == "W"
        assert indent == 0

    def test_multiline_pattern_integration(self) -> None:
        """Simulate parsing message with multiline pattern."""
        cursor = Cursor(source="hello =\n  World", pos=5)
        cursor = skip_blank_inline(cursor)
        assert cursor.current == "="
        cursor = cursor.advance()
        cursor, indent = skip_multiline_pattern_start(cursor)
        assert cursor.current == "W"
        assert indent == 2

    def test_select_expression_with_blank(self) -> None:
        """Simulate parsing select expression with blank lines."""
        cursor = Cursor(source=" \n \n  [variant]", pos=0)
        cursor = skip_blank(cursor)
        assert cursor.current == "["

    def test_continuation_detection_in_pattern(self) -> None:
        """Detect continuation vs attribute."""
        c1 = Cursor(source="\n  continued text", pos=0)
        assert is_indented_continuation(c1) is True
        c2 = Cursor(source="\n  .attribute = value", pos=0)
        assert is_indented_continuation(c2) is False


# ============================================================================
# PARSE_SIMPLE_PATTERN
# ============================================================================


class TestParseSimplePattern:
    """Tests for parse_simple_pattern basic behavior."""

    def test_with_variable(self) -> None:
        """Parses pattern with variable reference."""
        cursor = Cursor("Hello {$name}", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert len(result.value.elements) == 2

    def test_stops_at_bracket(self) -> None:
        """Bracket lookahead: [key]rest is literal text."""
        cursor = Cursor("Value[key]rest", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.value.elements[0].value == "Value[key]rest"  # type: ignore[union-attr]
        assert result.cursor.is_eof

        # [key] followed by } IS a variant marker
        cursor = Cursor("Value [one]}", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.value.elements[0].value == "Value "  # type: ignore[union-attr]
        assert result.cursor.current == "["

    def test_stops_at_asterisk(self) -> None:
        """Asterisk lookahead: *[ is variant, * alone is literal."""
        cursor = Cursor("Text*[other]", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.cursor.current == "*"

        cursor = Cursor("Text*rest", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.value.elements[0].value == "Text*rest"  # type: ignore[union-attr]

    def test_stops_at_brace(self) -> None:
        """Stops at } (expression end)."""
        cursor = Cursor("Value}rest", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.cursor.current == "}"

    def test_placeable_parse_fails(self) -> None:
        """Returns None when placeable parsing fails."""
        cursor = Cursor("Text {invalid", 0)
        with patch(
            "ftllexengine.syntax.parser.rules.parse_placeable",
            return_value=None,
        ):
            result = parse_simple_pattern(cursor)
        assert result is None

    def test_variant_markers_lookahead(self) -> None:
        """Variant markers vs literal text disambiguation."""
        # *[other] IS a variant marker
        cursor = Cursor("*[other]", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert len(result.value.elements) == 0
        assert result.cursor.current == "*"

        # [INFO] followed by text is literal
        cursor = Cursor("[INFO] message", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.value.elements[0].value == "[INFO] message"  # type: ignore[union-attr]

    def test_malformed_placeable_returns_none(self) -> None:
        """Malformed placeable ({@) returns None."""
        cursor = Cursor("text{@", 0)
        result = parse_simple_pattern(cursor)
        assert result is None

    def test_in_select_expression(self) -> None:
        """parse_simple_pattern as used in select expression variants."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("""msg = {NUMBER(1) ->
    [one] One item
    *[other] Many items
}""")
        result, _ = bundle.format_pattern("msg")
        assert "item" in result


class TestSimplePatternTextAccDirect:
    """Tests for text_acc paths in parse_simple_pattern (Cursor-direct)."""

    def test_text_then_continuation_then_placeable(self) -> None:
        """Accumulated text merged with prior element before placeable."""
        result = parse_simple_pattern(Cursor("hello\n    {$x}", 0))
        assert result is not None
        assert len(result.value.elements) >= 2

    def test_continuation_then_placeable_no_prior(self) -> None:
        """Continuation before placeable with no prior elements."""
        result = parse_simple_pattern(Cursor("\n    {$x}", 0))
        assert result is not None

    def test_placeable_then_continuation_then_placeable(self) -> None:
        """Placeable, continuation, then another placeable."""
        result = parse_simple_pattern(Cursor("{$a}\n    {$b}", 0))
        assert result is not None

    def test_text_then_continuation_at_end(self) -> None:
        """Text followed by trailing continuation."""
        result = parse_simple_pattern(Cursor("hello\n    ", 0))
        assert result is not None

    def test_continuation_at_end_no_prior(self) -> None:
        """Trailing continuation with no prior elements."""
        result = parse_simple_pattern(Cursor("\n    ", 0))
        assert result is not None

    def test_placeable_then_continuation_at_end(self) -> None:
        """Placeable then trailing continuation."""
        result = parse_simple_pattern(Cursor("{$x}\n    ", 0))
        assert result is not None

    def test_complex_continuation_before_placeable(self) -> None:
        """Multiple continuations before placeable."""
        text = "start\n    line1\n    line2\n    {$x}"
        result = parse_simple_pattern(Cursor(text, 0))
        assert result is not None

    def test_multiple_placeables_with_continuations(self) -> None:
        """Multiple placeables separated by continuations."""
        result = parse_simple_pattern(Cursor("{$a}\n    {$b}\n    {$c}", 0))
        assert result is not None

    def test_blank_continuation_lines(self) -> None:
        """Blank lines between continuations."""
        result = parse_simple_pattern(Cursor("text\n\n    continued", 0))
        assert result is not None

    def test_continuation_before_placeable_with_text(self) -> None:
        """Leading spaces then text then placeable."""
        cursor = Cursor("    continuation{$var}", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert len(result.value.elements) >= 2

    def test_placeable_continuation_text_placeable(self) -> None:
        """Placeable, continuation with text, then another placeable."""
        cursor = Cursor("{$x}\n    text{$y}", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert len(result.value.elements) >= 3

    def test_continuation_before_text_no_prior(self) -> None:
        """Leading spaces then text, no prior elements."""
        cursor = Cursor("    line1\n    line2", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None

    def test_finalize_continuation_no_prior(self) -> None:
        """Finalize accumulated text when no prior elements."""
        cursor = Cursor("    just continuation", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert len(result.value.elements) >= 1

    def test_finalize_continuation_last_is_placeable(self) -> None:
        """Finalize accumulated text when last element is placeable."""
        cursor = Cursor("{$x}\n    continuation", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert len(result.value.elements) >= 2

    def test_direct_text_acc_finalization(self) -> None:
        """Extra spaces accumulated then stop character triggers finalization."""
        source = "a\n    b\n        }"
        result = parse_simple_pattern(Cursor(source, 0))
        assert result is not None
        assert len(result.value.elements) >= 1


class TestSimplePatternTextAccVariant:
    """Tests for text_acc in variant/message context (parse_ftl/parse_message)."""

    def test_extra_spaces_before_placeable(self) -> None:
        """Extra indentation before placeable in variant pattern."""
        ftl = """msg = { $n ->
    [one]
        first
            {$count}
    *[other] items
}"""
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

    def test_trailing_extra_spaces(self) -> None:
        """Trailing extra spaces at end of variant pattern."""
        ftl = """msg = { $n ->
    [one]
        item

    *[other] items
}"""
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

    def test_continuation_extra_spaces_then_placeable(self) -> None:
        """Extra spaces before placeable via parse_message."""
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

    def test_continuation_spaces_only_then_placeable(self) -> None:
        """Blank continuation creating extra_spaces, then text+placeable."""
        source = """msg = {$n ->
    [one] Start

            text {$x}
    *[other] End
}"""
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())
        assert result is not None
        assert isinstance(result.value, Message)

    def test_trailing_extra_spaces_via_message(self) -> None:
        """Variant ending with only accumulated extra spaces."""
        variant_one = (
            "[one] Text\n        MoreText\n                "
        )
        variant_other = "*[other] Items"
        source = (
            f"msg = {{$n ->\n    {variant_one}"
            f"\n    {variant_other}\n}}"
        )
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())
        assert result is not None
        assert isinstance(result.value, Message)
        assert result.value.value is not None

    def test_extra_spaces_at_close_brace(self) -> None:
        """Trailing extra spaces ending at close brace."""
        source = """msg = {$n ->
    *[other] Text

}"""
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())
        assert result is not None
        assert isinstance(result.value, Message)

    def test_complex_spacing_finalization(self) -> None:
        """Multiple continuations ending with accumulated spaces."""
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

    def test_variant_ending_with_continuation(self) -> None:
        """Variant ending with continuation extra spaces."""
        ftl = """msg = { $n ->
    [one] value
        text

    [two] other
    *[three] default
}"""
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

    def test_variant_extra_indent_then_next(self) -> None:
        """Variant with extra indent followed by next variant."""
        ftl = """msg = { $n ->
    [one]
        line1

    [two] line2
    *[other] other
}"""
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None


# ============================================================================
# PARSE_PATTERN
# ============================================================================


class TestParsePatternBasic:
    """Tests for parse_pattern basic behavior."""

    def test_no_text_before_newline(self) -> None:
        """Empty pattern at newline (cursor.pos == text_start)."""
        result = parse_pattern(Cursor("\n", 0))
        assert result is not None
        assert len(result.value.elements) == 0

    def test_placeable_then_newline(self) -> None:
        """Placeable immediately followed by newline."""
        result = parse_pattern(Cursor("{$var}\n", 0))
        assert result is not None
        assert len(result.value.elements) == 1

    def test_placeable_parse_fails(self) -> None:
        """Returns None when parse_placeable fails."""
        cursor = Cursor("Text {invalid", 0)
        with patch(
            "ftllexengine.syntax.parser.rules.parse_placeable",
            return_value=None,
        ):
            result = parse_pattern(cursor)
        assert result is None

    def test_stop_char_not_placeable(self) -> None:
        """Pattern with stop character that's not '{'."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Value\n")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert "Value" in result

    def test_empty_pattern_with_attribute(self) -> None:
        """Empty pattern followed by attribute."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg =\n    .attr = Attribute\n")
        result, errors = bundle.format_pattern("msg", attribute="attr")
        assert not errors
        assert "Attribute" in result

    def test_pattern_at_eof(self) -> None:
        """Pattern at EOF without trailing newline."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Value at EOF")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert "Value at EOF" in result


class TestParsePatternTopLevelDelimiters:
    """Tests for top-level pattern delimiter handling.

    In top-level patterns (not inside select expressions), characters
    like }, [, * are literal text, not structural delimiters.
    """

    def test_close_brace_is_text(self) -> None:
        """} is literal text in top-level patterns."""
        result = parse_pattern(Cursor("}text", 0))
        assert result is not None
        assert len(result.value.elements) == 1
        assert result.value.elements[0].value == "}text"  # type: ignore[union-attr]

    def test_bracket_is_text(self) -> None:
        """[ is literal text in top-level patterns."""
        result = parse_pattern(Cursor("[text", 0))
        assert result is not None
        assert len(result.value.elements) == 1
        assert result.value.elements[0].value == "[text"  # type: ignore[union-attr]

    def test_asterisk_is_text(self) -> None:
        """* is literal text in top-level patterns."""
        result = parse_pattern(Cursor("*text", 0))
        assert result is not None
        assert len(result.value.elements) == 1
        assert result.value.elements[0].value == "*text"  # type: ignore[union-attr]

    def test_special_char_sequences(self) -> None:
        """Multiple delimiters are all literal text."""
        result = parse_pattern(Cursor("}}]]", 0))
        assert result is not None
        assert len(result.value.elements) == 1
        assert result.value.elements[0].value == "}}]]"  # type: ignore[union-attr]

    def test_stop_char_advances_cursor(self) -> None:
        """] at position 0 advances cursor to prevent infinite loop."""
        result = parse_pattern(Cursor("]", 0))
        assert result is not None
        assert result.cursor.pos >= 1 or result.cursor.is_eof

    def test_includes_special_chars_combined(self) -> None:
        """All delimiter characters are literal in top-level patterns."""
        for delimiter in ["}", "[", "*"]:
            result = parse_pattern(Cursor(f"text{delimiter}more", 0))
            assert result is not None
            assert len(result.value.elements) == 1
            expected = f"text{delimiter}more"
            assert result.value.elements[0].value == expected  # type: ignore[union-attr]


class TestParsePatternContinuation:
    """Tests for continuation handling in parse_pattern."""

    def test_crlf_multiline(self) -> None:
        """CRLF in multiline continuation."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = First line\r\n    Second line")
        result, _ = bundle.format_pattern("msg")
        assert "First line" in result
        assert "Second line" in result

    def test_cr_only_continuation(self) -> None:
        """CR (old Mac style) at continuation."""
        cursor = Cursor("msg = First\r    Second", 6)
        result = parse_pattern(cursor)
        assert result is not None
        assert len(result.value.elements) > 0

    def test_continuation_after_placeable(self) -> None:
        """Multiline continuation after placeable adds space element."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = {NUMBER(5)}\n    continued text")
        result, _ = bundle.format_pattern("msg")
        assert "5" in result
        assert "continued text" in result

    def test_extra_spaces_before_placeable(self) -> None:
        """Extra indentation before placeable in top-level pattern."""
        ftl = "msg =\n    first\n        {$var}"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        has_placeable = any(
            isinstance(e, Placeable) for e in msg.value.elements
        )
        assert has_placeable

    def test_trailing_extra_spaces(self) -> None:
        """Trailing extra spaces at end of top-level pattern."""
        ftl = "msg =\n    first\n        "
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.value.elements) >= 1

    def test_extra_indent_preserved(self) -> None:
        """Extra indentation beyond common indent is preserved."""
        ftl = "msg =\n    first\n        second"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert "first" in text
        assert "second" in text

    def test_varying_extra_indent(self) -> None:
        """Multiple lines with varying extra indentation."""
        ftl = "msg =\n    base\n        extra4\n            extra8"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.value.elements) >= 1

    def test_accumulated_spaces_prepended(self) -> None:
        """Accumulated extra spaces prepended to following text."""
        ftl = "msg =\n    first\n        more text"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert "first" in text
        assert "more text" in text

    def test_multiple_continuations_varying_indent(self) -> None:
        """Multiple continuation lines with varying extra indentation."""
        ftl = "msg =\n    l1\n        l2\n            l3\n        l4"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        for line in ["l1", "l2", "l3", "l4"]:
            assert line in text

    def test_continuation_new_element_no_prior(self) -> None:
        """Accumulated continuation before text, no prior elements."""
        result = parse_pattern(Cursor("    continuation\n    more", 0))
        assert result is not None

    def test_continuation_new_element_last_placeable(self) -> None:
        """Accumulated continuation merged after placeable."""
        result = parse_pattern(Cursor("{$x}\n    text more", 0))
        assert result is not None

    def test_finalize_continuation_no_prior(self) -> None:
        """Finalize accumulated text when no prior elements."""
        result = parse_pattern(Cursor("    only continuation", 0))
        assert result is not None

    def test_finalize_continuation_last_placeable(self) -> None:
        """Finalize accumulated text when last is placeable."""
        result = parse_pattern(Cursor("{$x}\n    final", 0))
        assert result is not None

    def test_empty_pattern_continuation(self) -> None:
        """Continuation with empty elements list (newline at pos 0)."""
        result = parse_pattern(Cursor("\n    text", 0))
        assert result is not None

    def test_term_extra_indent_before_placeable(self) -> None:
        """Term with extra indentation before placeable."""
        ftl = "-term =\n    first\n        {$var}"
        resource = parse_ftl(ftl)
        term = resource.entries[0]
        assert isinstance(term, Term)
        assert term.value is not None
        has_placeable = any(
            isinstance(e, Placeable) for e in term.value.elements
        )
        assert has_placeable


# ============================================================================
# MULTILINE BLANK LINES
# ============================================================================


class TestMultilineBlankLines:
    """Tests for blank line handling in multiline patterns."""

    def test_single_blank_line_before_content(self) -> None:
        """Single blank line before content strips indentation."""
        ftl = "msg =\n\n    value"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.value.elements[0].value == "value"  # type: ignore[union-attr]

    def test_multiple_blank_lines_before_content(self) -> None:
        """Multiple blank lines before content strips indentation."""
        ftl = "msg =\n\n\n\n    value"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value.elements[0].value == "value"  # type: ignore[union-attr]

    def test_with_subsequent_lines(self) -> None:
        """Blank line before content with subsequent lines."""
        ftl = "msg =\n\n    first\n    second"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert text == "first\nsecond"

    def test_with_extra_indentation(self) -> None:
        """Blank line before content preserves extra indentation."""
        ftl = "msg =\n\n    first\n        second"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert text == "first\n    second"

    def test_bundle_format(self) -> None:
        """FluentBundle correctly formats with blank line before content."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg =\n\n    Hello World")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert result == "Hello World"

    def test_with_placeable(self) -> None:
        """Blank line before content with placeable."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg =\n\n    Hello { $name }")
        result, errors = bundle.format_pattern(
            "msg", {"name": "Alice"}
        )
        assert not errors
        assert "Hello" in result
        assert "Alice" in result

    def test_blank_line_at_end(self) -> None:
        """Blank line at end of pattern handled correctly."""
        ftl = "msg =\n    first\n\n    second"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert "first" in text
        assert "second" in text

    def test_mixed_blank_lines(self) -> None:
        """Blank lines at various positions."""
        ftl = "msg =\n\n    first\n\n    second\n\n    third"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert "first" in text
        assert "second" in text
        assert "third" in text

    def test_term_blank_line_before_content(self) -> None:
        """Term with blank line before content."""
        ftl = "-brand =\n\n    Firefox"
        resource = parse_ftl(ftl)
        term = resource.entries[0]
        assert isinstance(term, Term)
        text = "".join(
            e.value
            for e in term.value.elements
            if isinstance(e, TextElement)
        )
        assert text == "Firefox"

    def test_multiple_blank_lines_in_continuation(self) -> None:
        """Multiple consecutive blank lines within continuation."""
        ftl = "msg =\n    first\n\n\n    second"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert "first" in text
        assert "second" in text

    def test_term_blank_lines_in_continuation(self) -> None:
        """Term with blank lines in continuation."""
        ftl = "-term =\n\n\n    content"
        resource = parse_ftl(ftl)
        term = resource.entries[0]
        assert isinstance(term, Term)
        text = "".join(
            e.value
            for e in term.value.elements
            if isinstance(e, TextElement)
        )
        assert text == "content"

    def test_placeable_after_blanks_with_extra_indent(self) -> None:
        """Placeable after blank lines with extra indentation."""
        ftl = "msg =\n    text\n\n\n        {$var}"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        has_text = any(
            isinstance(e, TextElement) for e in msg.value.elements
        )
        has_placeable = any(
            isinstance(e, Placeable) for e in msg.value.elements
        )
        assert has_text
        assert has_placeable

    def test_only_extra_spaces_no_content(self) -> None:
        """Continuation with only extra spaces, no actual content."""
        ftl = "msg =\n    text\n\n    more"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert "text" in text
        assert "more" in text

    def test_complex_mixed_pattern(self) -> None:
        """Complex pattern mixing all edge cases."""
        ftl = "msg =\n\n\n    first\n\n        {$var}\n\n\n        last"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        has_text = any(
            isinstance(e, TextElement) for e in msg.value.elements
        )
        has_placeable = any(
            isinstance(e, Placeable) for e in msg.value.elements
        )
        assert has_text
        assert has_placeable

    def test_original_regression(self) -> None:
        """FTL-GRAMMAR-001: blank line sets common_indent to 0."""
        ftl = "msg =\n\n    value"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        element = msg.value.elements[0]  # type: ignore[union-attr]
        assert isinstance(element, TextElement)
        assert element.value == "value", (
            f"common_indent bug: expected 'value', got "
            f"'{element.value}'"
        )

    def test_regression_variant_simple_pattern(self) -> None:
        """Regression: parse_simple_pattern blank line indent."""
        ftl = """msg = { $n ->
    [one]

        item
    *[other] items
}"""
        bundle = FluentBundle("en_US")
        bundle.add_resource(ftl)
        result, errors = bundle.format_pattern("msg", {"n": 1})
        assert not errors
        assert "item" in result
        assert "        item" not in result

    @pytest.mark.parametrize(
        ("ftl", "expected"),
        [
            ("msg =\n\n    x", "x"),
            ("msg =\n\n\n    x", "x"),
            ("msg =\n\n\n\n\n    x", "x"),
            ("msg =\n\n        x", "x"),
            ("msg =\n\n            x", "x"),
        ],
    )
    def test_parametrized_blank_line_scenarios(
        self, ftl: str, expected: str
    ) -> None:
        """Various blank line scenarios all strip indentation."""
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert text == expected


# ============================================================================
# VARIANT DELIMITER LOOKAHEAD
# ============================================================================


class TestVariantDelimiterLookahead:
    """Tests for variant delimiter (* and [) in pattern text."""

    def test_asterisk_literal_in_variant(self) -> None:
        """'*' without '[' is treated as literal text."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
count = { $n ->
    [one] 1 * item
   *[other] { $n } * items
}
""")
        result, errors = bundle.format_pattern("count", {"n": 1})
        assert "1 * item" in result
        assert not errors

    def test_bracket_not_starting_variant(self) -> None:
        """'[' not followed by valid key is treated as literal."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
msg = { $type ->
    [info] [INFO] message
   *[other] [?] unknown
}
""")
        result, errors = bundle.format_pattern(
            "msg", {"type": "info"}
        )
        assert "[INFO] message" in result
        assert not errors

    def test_math_expression_in_variant(self) -> None:
        """Math-like expressions with * and [ in variant text."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
calc = { $op ->
    [mul] Result: 3 * 5 = 15
    [arr] Array: [1, 2, 3]
   *[other] Unknown operation
}
""")
        result, _ = bundle.format_pattern("calc", {"op": "mul"})
        assert "3 * 5 = 15" in result

        result, _ = bundle.format_pattern("calc", {"op": "arr"})
        assert "[1, 2, 3]" in result

    def test_asterisk_bracket_is_variant(self) -> None:
        """'*[' still correctly marks default variant."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
example = { $x ->
    [a] Value A
   *[b] Default B
}
""")
        result, errors = bundle.format_pattern(
            "example", {"x": "unknown"}
        )
        assert not errors
        assert "Default B" in result

    def test_numeric_variant_key(self) -> None:
        """[123] treated as variant key."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
indexed = { $i ->
    [0] Zero
    [1] One
   *[2] Default
}
""")
        result, errors = bundle.format_pattern("indexed", {"i": 0})
        assert not errors
        assert "Zero" in result

    def test_complex_asterisk_and_brackets(self) -> None:
        """Both * and [] as literals in variant text."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
complex = { $mode ->
    [matrix] See [matrix * vector] for details
    [calc] Compute a * b + c
   *[other] No special chars
}
""")
        result, _ = bundle.format_pattern(
            "complex", {"mode": "matrix"}
        )
        assert "[matrix * vector]" in result

    def test_variant_pattern_fails(self) -> None:
        """parse_variant returns None on malformed input."""
        cursor = Cursor("[one] {@", 0)
        assert parse_variant(cursor) is None


# ============================================================================
# HYPOTHESIS PROPERTY TESTS
# ============================================================================


class TestPatternsHypothesis:
    """Property-based tests for pattern and whitespace handling."""

    @given(st.integers(min_value=0, max_value=100))
    def test_skip_blank_inline_various_counts(
        self, space_count: int
    ) -> None:
        """Any number of spaces skipped by skip_blank_inline."""
        event(f"space_count={space_count}")
        source = " " * space_count + "hello"
        cursor = Cursor(source=source, pos=0)
        assert skip_blank_inline(cursor).pos == space_count

    @given(st.integers(min_value=1, max_value=20))
    def test_is_indented_continuation_various(
        self, indent_count: int
    ) -> None:
        """Any indentation level detected as continuation."""
        event(f"indent_count={indent_count}")
        source = "\n" + " " * indent_count + "text"
        cursor = Cursor(source=source, pos=0)
        assert is_indented_continuation(cursor) is True

    @given(
        extra_indent=st.integers(min_value=1, max_value=12),
        base_indent=st.integers(min_value=4, max_value=8),
    )
    def test_extra_spaces_before_placeable(
        self, extra_indent: int, base_indent: int
    ) -> None:
        """Extra indentation before placeable is preserved."""
        boundary = "deep" if extra_indent > 8 else "shallow"
        event(f"boundary={boundary}")
        event(f"base_indent={base_indent}")
        base = " " * base_indent
        extra = " " * (base_indent + extra_indent)
        ftl = f"msg =\n{base}text\n{extra}{{$var}}"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        elements = msg.value.elements
        assert len(elements) >= 2
        assert isinstance(elements[-1], Placeable)

    @given(trailing_spaces=st.integers(min_value=1, max_value=20))
    def test_trailing_spaces_handled(
        self, trailing_spaces: int
    ) -> None:
        """Patterns with trailing spaces parse successfully."""
        event(f"trailing_spaces={trailing_spaces}")
        spaces = " " * trailing_spaces
        ftl = f"msg =\n    text\n{spaces}"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

    @given(
        base_indent=st.integers(min_value=4, max_value=8),
        extra_indent=st.integers(min_value=1, max_value=8),
    )
    def test_extra_indent_handling(
        self, base_indent: int, extra_indent: int
    ) -> None:
        """Extra indentation correctly accumulated."""
        event(f"extra_indent={extra_indent}")
        event(f"base_indent={base_indent}")
        base = " " * base_indent
        extra = " " * (base_indent + extra_indent)
        ftl = f"msg =\n{base}first\n{extra}second"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert "first" in text
        assert "second" in text

    @given(
        num_lines=st.integers(min_value=2, max_value=5),
        indent_base=st.integers(min_value=4, max_value=8),
    )
    def test_multiline_extra_indent_accumulation(
        self, num_lines: int, indent_base: int
    ) -> None:
        """Multiple lines with extra indent accumulate correctly."""
        event(f"num_lines={num_lines}")
        event(f"indent_base={indent_base}")
        lines_ftl = [f"line{i}" for i in range(num_lines)]
        base = " " * indent_base
        ftl_lines = ["msg ="]
        ftl_lines.append(f"{base}{lines_ftl[0]}")
        for i in range(1, num_lines):
            extra = " " * (i % 3)
            ftl_lines.append(f"{base}{extra}{lines_ftl[i]}")
        ftl = "\n".join(ftl_lines)
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        for line_text in lines_ftl:
            assert line_text in text

    @given(
        extra_indent=st.integers(min_value=1, max_value=8),
        base_indent=st.integers(min_value=4, max_value=8),
    )
    def test_term_extra_indent(
        self, extra_indent: int, base_indent: int
    ) -> None:
        """Terms handle extra indentation like messages."""
        event(f"extra_indent={extra_indent}")
        event(f"base_indent={base_indent}")
        base = " " * base_indent
        extra = " " * (base_indent + extra_indent)
        ftl = f"-term =\n{base}first\n{extra}second"
        resource = parse_ftl(ftl)
        term = resource.entries[0]
        assert isinstance(term, Term)
        text = "".join(
            e.value
            for e in term.value.elements
            if isinstance(e, TextElement)
        )
        assert "first" in text
        assert "second" in text

    @given(
        num_blank_lines=st.integers(min_value=1, max_value=10),
        indent_size=st.integers(min_value=1, max_value=8),
    )
    def test_blank_lines_and_indentation(
        self, num_blank_lines: int, indent_size: int
    ) -> None:
        """Any blank lines before content strip indent."""
        event(f"num_blank_lines={num_blank_lines}")
        event(f"indent_size={indent_size}")
        blank_lines = "\n" * num_blank_lines
        indent = " " * indent_size
        ftl = f"msg ={blank_lines}{indent}content"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.value.elements[0].value == "content"  # type: ignore[union-attr]

    @given(
        content=st.text(
            min_size=1,
            max_size=50,
            alphabet="abcdefghijklmnopqrstuvwxyz",
        )
    )
    def test_content_preserved_after_blank_lines(
        self, content: str
    ) -> None:
        """Content after blank lines is preserved exactly."""
        event(f"content_length={len(content)}")
        ftl = f"msg =\n\n    {content}"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert text == content

    @example("Hello")
    @example("Line1\nLine2")
    @given(st.text(min_size=1, max_size=50))
    def test_parse_simple_pattern_property(
        self, text: str
    ) -> None:
        """parse_simple_pattern handles arbitrary text."""
        if not text or text[0] in ("}", "[", "*"):
            return
        has_newline = "\n" in text
        event(f"has_newline={has_newline}")
        cursor = Cursor(text, 0)
        result = parse_simple_pattern(cursor)
        outcome = "parsed" if result else "none"
        event(f"outcome={outcome}")
        assert result is None or isinstance(result.value, Pattern)

    @example("value")
    @example("{$x}")
    @given(st.text(min_size=1, max_size=50))
    def test_parse_pattern_property(self, text: str) -> None:
        """parse_pattern handles arbitrary text."""
        has_placeable = "{" in text
        event(f"has_placeable={has_placeable}")
        cursor = Cursor(text, 0)
        result = parse_pattern(cursor)
        outcome = "parsed" if result else "none"
        event(f"outcome={outcome}")
        assert result is None or isinstance(result.value, Pattern)
