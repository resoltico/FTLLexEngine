# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_patterns.py."""

from tests.syntax_parser_patterns_cases import *  # noqa: F403 - shared split test support

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
