"""Comprehensive property-based tests for syntax.parser.whitespace module.

Tests whitespace handling utilities for Fluent FTL parser.

"""

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.whitespace import (
    is_indented_continuation,
    skip_blank,
    skip_blank_inline,
    skip_multiline_pattern_start,
)


class TestSkipBlankInline:
    """Property-based tests for skip_blank_inline function."""

    def test_skip_blank_inline_no_spaces(self) -> None:
        """Verify skip_blank_inline returns same position when no spaces."""
        cursor = Cursor(source="hello", pos=0)
        new_cursor = skip_blank_inline(cursor)
        assert new_cursor.pos == 0

    def test_skip_blank_inline_leading_spaces(self) -> None:
        """Verify skip_blank_inline skips leading spaces."""
        cursor = Cursor(source="   hello", pos=0)
        new_cursor = skip_blank_inline(cursor)
        assert new_cursor.pos == 3
        assert new_cursor.current == "h"

    def test_skip_blank_inline_all_spaces(self) -> None:
        """Verify skip_blank_inline handles all-space string."""
        cursor = Cursor(source="     ", pos=0)
        new_cursor = skip_blank_inline(cursor)
        assert new_cursor.is_eof is True

    def test_skip_blank_inline_not_tab(self) -> None:
        """Verify skip_blank_inline does NOT skip tabs."""
        cursor = Cursor(source="  \thello", pos=0)
        new_cursor = skip_blank_inline(cursor)
        assert new_cursor.pos == 2
        assert new_cursor.current == "\t"

    def test_skip_blank_inline_not_newline(self) -> None:
        """Verify skip_blank_inline does NOT skip newlines."""
        cursor = Cursor(source="  \nhello", pos=0)
        new_cursor = skip_blank_inline(cursor)
        assert new_cursor.pos == 2
        assert new_cursor.current == "\n"

    @given(st.integers(min_value=0, max_value=100))
    def test_skip_blank_inline_various_space_counts(self, space_count: int) -> None:
        """Property: skip_blank_inline skips any number of spaces."""
        source = " " * space_count + "hello"
        cursor = Cursor(source=source, pos=0)
        new_cursor = skip_blank_inline(cursor)
        assert new_cursor.pos == space_count


class TestSkipBlank:
    """Property-based tests for skip_blank function."""

    def test_skip_blank_no_whitespace(self) -> None:
        """Verify skip_blank returns same position when no whitespace."""
        cursor = Cursor(source="hello", pos=0)
        new_cursor = skip_blank(cursor)
        assert new_cursor.pos == 0

    def test_skip_blank_spaces_only(self) -> None:
        """Verify skip_blank skips spaces."""
        cursor = Cursor(source="   hello", pos=0)
        new_cursor = skip_blank(cursor)
        assert new_cursor.pos == 3
        assert new_cursor.current == "h"

    def test_skip_blank_newlines_only(self) -> None:
        """Verify skip_blank skips newlines."""
        cursor = Cursor(source="\n\nhello", pos=0)
        new_cursor = skip_blank(cursor)
        assert new_cursor.pos == 2
        assert new_cursor.current == "h"

    def test_skip_blank_mixed_whitespace(self) -> None:
        """Verify skip_blank skips mixed spaces and newlines.

        Note: CR is normalized to LF at parser entry, so skip_blank
        only needs to handle space and LF.
        """
        cursor = Cursor(source="  \n   hello", pos=0)
        new_cursor = skip_blank(cursor)
        assert new_cursor.pos == 6
        assert new_cursor.current == "h"

    def test_skip_blank_all_whitespace(self) -> None:
        """Verify skip_blank handles all-whitespace string."""
        cursor = Cursor(source=" \n ", pos=0)
        new_cursor = skip_blank(cursor)
        assert new_cursor.is_eof is True

    def test_skip_blank_not_tab(self) -> None:
        """Verify skip_blank does NOT skip tabs."""
        cursor = Cursor(source=" \n\thello", pos=0)
        new_cursor = skip_blank(cursor)
        assert new_cursor.pos == 2
        assert new_cursor.current == "\t"

    def test_skip_blank_normalized_crlf(self) -> None:
        """Verify skip_blank handles CRLF that has been normalized to LF.

        Note: CRLF is normalized to LF at parser entry (FluentParserV1.parse()),
        so by the time skip_blank is called, '\r\n' has become '\n'.
        """
        # Simulate post-normalization: CRLF becomes LF
        cursor = Cursor(source="\nhello", pos=0)
        new_cursor = skip_blank(cursor)
        assert new_cursor.pos == 1
        assert new_cursor.current == "h"


class TestIsIndentedContinuation:
    """Property-based tests for is_indented_continuation function."""

    def test_is_indented_continuation_true(self) -> None:
        """Verify is_indented_continuation returns True for indented line."""
        cursor = Cursor(source="\n  hello", pos=0)
        result = is_indented_continuation(cursor)
        assert result is True

    def test_is_indented_continuation_false_no_indentation(self) -> None:
        """Verify is_indented_continuation returns False without indentation."""
        cursor = Cursor(source="\nhello", pos=0)
        result = is_indented_continuation(cursor)
        assert result is False

    def test_is_indented_continuation_false_bracket(self) -> None:
        """Verify is_indented_continuation returns False for line starting with [."""
        cursor = Cursor(source="\n  [variant]", pos=0)
        result = is_indented_continuation(cursor)
        assert result is False

    def test_is_indented_continuation_false_asterisk(self) -> None:
        """Verify is_indented_continuation returns False for line starting with *."""
        cursor = Cursor(source="\n  *[default]", pos=0)
        result = is_indented_continuation(cursor)
        assert result is False

    def test_is_indented_continuation_false_dot(self) -> None:
        """Verify is_indented_continuation returns False for line starting with .."""
        cursor = Cursor(source="\n  .attribute", pos=0)
        result = is_indented_continuation(cursor)
        assert result is False

    def test_is_indented_continuation_not_at_newline(self) -> None:
        """Verify is_indented_continuation returns False when not at newline."""
        cursor = Cursor(source="hello", pos=0)
        result = is_indented_continuation(cursor)
        assert result is False

    def test_is_indented_continuation_at_eof(self) -> None:
        """Verify is_indented_continuation returns False at EOF."""
        cursor = Cursor(source="", pos=0)
        result = is_indented_continuation(cursor)
        assert result is False

    def test_is_indented_continuation_normalized_line_ending(self) -> None:
        """Verify is_indented_continuation works with normalized line endings.

        Note: Line endings (CRLF, CR) are normalized to LF at parser entry point,
        so this function only needs to handle LF. This test verifies correct
        behavior with normalized input.
        """
        # CRLF is normalized to LF at parser entry point before this function is called
        cursor = Cursor(source="\n  hello", pos=0)
        result = is_indented_continuation(cursor)
        assert result is True

    def test_is_indented_continuation_eof_after_newline(self) -> None:
        """Verify is_indented_continuation returns False for newline at EOF."""
        cursor = Cursor(source="\n", pos=0)
        result = is_indented_continuation(cursor)
        assert result is False

    @given(st.integers(min_value=1, max_value=20))
    def test_is_indented_continuation_various_indentations(
        self, indent_count: int
    ) -> None:
        """Property: is_indented_continuation returns True for any indentation level."""
        source = "\n" + " " * indent_count + "text"
        cursor = Cursor(source=source, pos=0)
        result = is_indented_continuation(cursor)
        assert result is True


class TestSkipMultilinePatternStart:
    """Property-based tests for skip_multiline_pattern_start function."""

    def test_skip_multiline_pattern_start_inline(self) -> None:
        """Verify skip_multiline_pattern_start handles inline pattern."""
        cursor = Cursor(source="  value", pos=0)
        new_cursor = skip_multiline_pattern_start(cursor)
        assert new_cursor.pos == 2
        assert new_cursor.current == "v"

    def test_skip_multiline_pattern_start_multiline(self) -> None:
        """Verify skip_multiline_pattern_start handles multiline pattern."""
        cursor = Cursor(source="\n  value", pos=0)
        new_cursor = skip_multiline_pattern_start(cursor)
        assert new_cursor.pos == 3
        assert new_cursor.current == "v"

    def test_skip_multiline_pattern_start_no_continuation(self) -> None:
        """Verify skip_multiline_pattern_start stops at non-continuation newline."""
        cursor = Cursor(source="\nvalue", pos=0)
        new_cursor = skip_multiline_pattern_start(cursor)
        assert new_cursor.pos == 0
        assert new_cursor.current == "\n"

    def test_skip_multiline_pattern_start_empty(self) -> None:
        """Verify skip_multiline_pattern_start handles empty input."""
        cursor = Cursor(source="", pos=0)
        new_cursor = skip_multiline_pattern_start(cursor)
        assert new_cursor.is_eof

    def test_skip_multiline_pattern_start_no_spaces(self) -> None:
        """Verify skip_multiline_pattern_start handles no leading spaces."""
        cursor = Cursor(source="value", pos=0)
        new_cursor = skip_multiline_pattern_start(cursor)
        assert new_cursor.pos == 0
        assert new_cursor.current == "v"

    def test_skip_multiline_pattern_start_normalized_line_ending(self) -> None:
        """Verify skip_multiline_pattern_start handles normalized line endings.

        Note: CRLF is normalized to LF at parser entry point before this
        function is called. This test verifies correct behavior with normalized input.
        """
        cursor = Cursor(source="\n  value", pos=0)
        new_cursor = skip_multiline_pattern_start(cursor)
        assert new_cursor.current == "v"

    def test_skip_multiline_pattern_start_stops_at_bracket(self) -> None:
        """Verify skip_multiline_pattern_start stops at bracket (variant)."""
        cursor = Cursor(source="\n  [variant]", pos=0)
        new_cursor = skip_multiline_pattern_start(cursor)
        assert new_cursor.pos == 0
        assert new_cursor.current == "\n"

    def test_skip_multiline_pattern_start_inline_then_newline(self) -> None:
        """Verify skip_multiline_pattern_start handles inline spaces then newline."""
        cursor = Cursor(source="  \nvalue", pos=0)
        new_cursor = skip_multiline_pattern_start(cursor)
        # Should skip inline spaces, but stop at newline without continuation
        assert new_cursor.pos == 2
        assert new_cursor.current == "\n"


class TestWhitespaceIntegration:
    """Integration tests for whitespace functions working together."""

    def test_parse_message_inline_pattern(self) -> None:
        """Integration: Simulate parsing message with inline pattern."""
        cursor = Cursor(source="hello = World", pos=5)  # After "hello"

        # Skip inline whitespace before =
        cursor = skip_blank_inline(cursor)
        assert cursor.current == "="

        # Skip =
        cursor = cursor.advance()

        # Skip whitespace before pattern
        cursor = skip_multiline_pattern_start(cursor)
        assert cursor.current == "W"

    def test_parse_message_multiline_pattern(self) -> None:
        """Integration: Simulate parsing message with multiline pattern."""
        cursor = Cursor(source="hello =\n  World", pos=5)  # After "hello"

        # Skip inline whitespace before =
        cursor = skip_blank_inline(cursor)
        assert cursor.current == "="

        # Skip =
        cursor = cursor.advance()

        # Skip whitespace before pattern (handles multiline)
        cursor = skip_multiline_pattern_start(cursor)
        assert cursor.current == "W"

    def test_parse_select_expression_with_blank(self) -> None:
        """Integration: Simulate parsing select expression with blank lines."""
        cursor = Cursor(source=" \n \n  [variant]", pos=0)

        # Skip blank (spaces and newlines)
        cursor = skip_blank(cursor)
        assert cursor.current == "["

    def test_continuation_detection_in_pattern(self) -> None:
        """Integration: Detect continuation vs attribute."""
        # Continuation line
        cursor1 = Cursor(source="\n  continued text", pos=0)
        assert is_indented_continuation(cursor1) is True

        # Attribute line (starts with .)
        cursor2 = Cursor(source="\n  .attribute = value", pos=0)
        assert is_indented_continuation(cursor2) is False


class TestWhitespaceEdgeCases:
    """Edge case tests for whitespace handling."""

    def test_skip_blank_inline_at_eof(self) -> None:
        """Verify skip_blank_inline handles EOF."""
        cursor = Cursor(source="", pos=0)
        new_cursor = skip_blank_inline(cursor)
        assert new_cursor.is_eof

    def test_skip_blank_at_eof(self) -> None:
        """Verify skip_blank handles EOF."""
        cursor = Cursor(source="", pos=0)
        new_cursor = skip_blank(cursor)
        assert new_cursor.is_eof

    def test_is_indented_continuation_only_spaces_after_newline(self) -> None:
        """Verify is_indented_continuation handles newline followed by only spaces."""
        cursor = Cursor(source="\n   ", pos=0)
        result = is_indented_continuation(cursor)
        # Empty indented line is considered a valid continuation
        assert result is True

    def test_skip_multiline_pattern_start_only_newline(self) -> None:
        """Verify skip_multiline_pattern_start handles only newline."""
        cursor = Cursor(source="\n", pos=0)
        new_cursor = skip_multiline_pattern_start(cursor)
        assert new_cursor.pos == 0

    def test_whitespace_with_carriage_return_only(self) -> None:
        """Verify carriage return alone is not skipped as whitespace.

        Note: Standalone CR is NOT considered whitespace by skip_blank.
        CR is normalized to LF at parser entry (FluentParserV1.parse()),
        but if a cursor is created directly with CR, it won't be skipped.
        This matches the Fluent spec which defines whitespace as U+0020
        and line endings as LF/CRLF (not standalone CR).
        """
        cursor = Cursor(source="\rhello", pos=0)
        new_cursor = skip_blank(cursor)
        # CR alone is not skipped since it's not valid whitespace
        assert new_cursor.pos == 0
        assert new_cursor.current == "\r"

    def test_is_indented_continuation_with_tab_indentation(self) -> None:
        """Verify is_indented_continuation returns False for tab indentation."""
        cursor = Cursor(source="\n\thello", pos=0)
        result = is_indented_continuation(cursor)
        assert result is False  # Tabs are not valid indentation


class TestWhitespaceSpecCompliance:
    """Tests for FTL specification compliance."""

    def test_blank_inline_only_u0020(self) -> None:
        """Verify blank_inline ONLY accepts U+0020 (space)."""
        # Should skip U+0020
        cursor1 = Cursor(source="   text", pos=0)
        new_cursor1 = skip_blank_inline(cursor1)
        assert new_cursor1.pos == 3

        # Should NOT skip U+0009 (tab)
        cursor2 = Cursor(source="\ttext", pos=0)
        new_cursor2 = skip_blank_inline(cursor2)
        assert new_cursor2.pos == 0

    def test_blank_accepts_line_endings(self) -> None:
        """Verify blank accepts LF line endings.

        Note: CR and CRLF are normalized to LF at parser entry
        (FluentParserV1.parse()), so skip_blank only needs to handle LF.
        Standalone CR is NOT whitespace per Fluent spec.
        """
        # LF (U+000A) - accepted
        cursor1 = Cursor(source="\ntext", pos=0)
        new_cursor1 = skip_blank(cursor1)
        assert new_cursor1.current == "t"

        # After normalization, CRLF becomes LF - which is accepted
        # Simulating post-normalization
        cursor2 = Cursor(source="\ntext", pos=0)
        new_cursor2 = skip_blank(cursor2)
        assert new_cursor2.current == "t"

        # CR alone is NOT whitespace (not skipped)
        cursor3 = Cursor(source="\rtext", pos=0)
        new_cursor3 = skip_blank(cursor3)
        assert new_cursor3.current == "\r"  # CR is not skipped

    def test_continuation_special_chars(self) -> None:
        """Verify continuation correctly identifies special starting characters."""
        # [ indicates variant
        assert is_indented_continuation(Cursor("\n [", 0)) is False

        # * indicates default variant
        assert is_indented_continuation(Cursor("\n *", 0)) is False

        # . indicates attribute
        assert is_indented_continuation(Cursor("\n .", 0)) is False

        # Regular character is continuation
        assert is_indented_continuation(Cursor("\n a", 0)) is True
