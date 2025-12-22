"""Complete coverage tests for syntax/parser/patterns.py.

Tests all uncovered lines and branches to achieve 100% coverage.

Missing coverage:
- Line 53: Variable reference without '$'
- Line 60: Variable reference with '$' but invalid identifier
- Lines 95-141: parse_simple_pattern function
- Line 180: CRLF handling in multiline continuation
- Line 190: Adding space when last element is Placeable
- Line 207: Placeable parsing failure
- Branch 227->171: False branch of cursor.pos > text_start
"""

from __future__ import annotations

from unittest.mock import patch

from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import (
    parse_pattern,
    parse_simple_pattern,
    parse_variable_reference,
)

# ============================================================================
# LINE 53: Variable Reference Without '$'
# ============================================================================


class TestLine53VariableReferenceWithoutDollar:
    """Test line 53: parse_variable_reference when '$' is missing."""

    def test_variable_reference_no_dollar_sign(self) -> None:
        """Test parse_variable_reference returns None without '$' (line 53)."""
        source = "name"  # No $ prefix
        cursor = Cursor(source, 0)

        result = parse_variable_reference(cursor)

        # Should return None
        assert result is None

    def test_variable_reference_at_eof(self) -> None:
        """Test parse_variable_reference at EOF (line 53)."""
        source = ""  # EOF
        cursor = Cursor(source, 0)

        result = parse_variable_reference(cursor)

        # Should return None at EOF
        assert result is None


# ============================================================================
# LINE 60: Variable Reference With '$' But Invalid Identifier
# ============================================================================


class TestLine60VariableReferenceInvalidIdentifier:
    """Test line 60: parse_variable_reference with invalid identifier."""

    def test_variable_reference_dollar_only(self) -> None:
        """Test parse_variable_reference with just '$' (line 60)."""
        source = "$ "  # $ followed by space (no identifier)
        cursor = Cursor(source, 0)

        result = parse_variable_reference(cursor)

        # Should return None because identifier parsing fails
        assert result is None

    def test_variable_reference_dollar_followed_by_number(self) -> None:
        """Test parse_variable_reference with '$' followed by number."""
        source = "$123"  # Identifier can't start with number
        cursor = Cursor(source, 0)

        result = parse_variable_reference(cursor)

        # Should return None
        assert result is None


# ============================================================================
# LINES 95-141: parse_simple_pattern Function
# ============================================================================


class TestParseSimplePattern:
    """Test parse_simple_pattern function (lines 95-141)."""

    def test_simple_pattern_with_variable(self) -> None:
        """Test parse_simple_pattern with variable reference."""
        # Simple pattern used in select expression variants
        source = "Hello {$name}"
        cursor = Cursor(source, 0)

        result = parse_simple_pattern(cursor)

        # Should parse successfully
        assert result is not None
        pattern = result.value
        assert len(pattern.elements) == 2  # Text + Placeable

    def test_simple_pattern_stops_at_bracket(self) -> None:
        """Test parse_simple_pattern lookahead for '[' variant key detection.

        v0.26.0: '[' is a variant marker only if:
        - Content is valid identifier/number
        - Followed by newline/}/[/* (not regular text)
        """
        # [key]rest - [key] followed by text is literal
        source = "Value[key]rest"
        cursor = Cursor(source, 0)

        result = parse_simple_pattern(cursor)

        # Should parse entire string as literal text
        assert result is not None
        assert result.value.elements[0].value == "Value[key]rest"  # type: ignore[union-attr]
        assert result.cursor.is_eof

        # Incomplete bracket is literal text
        source = "Value[rest"
        cursor = Cursor(source, 0)

        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.value.elements[0].value == "Value[rest"  # type: ignore[union-attr]

        # [key] followed by } IS a variant marker
        source = "Value [one]}"
        cursor = Cursor(source, 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.value.elements[0].value == "Value "  # type: ignore[union-attr]
        assert result.cursor.current == "["

    def test_simple_pattern_stops_at_asterisk(self) -> None:
        """Test parse_simple_pattern lookahead for '*' variant marker detection.

        v0.26.0: '*' is a variant marker only if followed by '['.
        """
        # *[ pattern IS a variant marker - stops at *
        source = "Text*[other]"
        cursor = Cursor(source, 0)

        result = parse_simple_pattern(cursor)

        # Should parse "Text" and stop at *
        assert result is not None
        assert result.cursor.current == "*"

        # * alone (not followed by [) is literal text
        source = "Text*rest"
        cursor = Cursor(source, 0)

        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.value.elements[0].value == "Text*rest"  # type: ignore[union-attr]
        assert result.cursor.is_eof

    def test_simple_pattern_stops_at_brace(self) -> None:
        """Test parse_simple_pattern stops at '}' (expression end)."""
        source = "Value}rest"  # Stops at }
        cursor = Cursor(source, 0)

        result = parse_simple_pattern(cursor)

        # Should parse "Value" and stop at }
        assert result is not None
        assert result.cursor.current == "}"

    def test_simple_pattern_placeable_parse_fails(self) -> None:
        """Test parse_simple_pattern returns None when placeable parsing fails."""
        source = "Text {invalid"
        cursor = Cursor(source, 0)

        # Mock parse_placeable from rules module
        with patch(
            "ftllexengine.syntax.parser.rules.parse_placeable",
            return_value=None,
        ):
            result = parse_simple_pattern(cursor)

        # Should return None when placeable parsing fails
        assert result is None

    def test_simple_pattern_variant_markers_lookahead(self) -> None:
        """Test parse_simple_pattern lookahead for variant markers.

        v0.26.0: Lookahead distinguishes variant syntax from literal text.
        - '*[' IS a variant marker (stops parsing)
        - '[key] text' is literal (text follows)
        - '*' alone is literal
        """
        # *[other] IS a variant marker - should stop immediately
        source = "*[other]"
        cursor = Cursor(source, 0)

        result = parse_simple_pattern(cursor)

        # Should stop at * (variant marker)
        assert result is not None
        assert len(result.value.elements) == 0  # Empty before marker
        assert result.cursor.current == "*"

        # [key] followed by text is literal
        source = "[INFO] message"
        cursor = Cursor(source, 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.value.elements[0].value == "[INFO] message"  # type: ignore[union-attr]

        # * alone (not *[) is literal
        source = "* hello"
        cursor = Cursor(source, 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.value.elements[0].value == "* hello"  # type: ignore[union-attr]


# ============================================================================
# LINE 180: CRLF Handling in Multiline Continuation
# ============================================================================


class TestLine180CRLFMultilineContinuation:
    """Test line 180: CRLF handling in indented continuation."""

    def test_pattern_multiline_continuation_crlf(self) -> None:
        """Test parse_pattern with CRLF in multiline continuation (line 180)."""
        # Pattern with CRLF and indented continuation
        bundle = FluentBundle("en_US")
        ftl = "msg = First line\r\n    Second line"
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")

        # Should handle CRLF correctly
        assert "First line" in result
        assert "Second line" in result

    def test_pattern_multiline_cr_only_at_continuation(self) -> None:
        """Test parse_pattern with just CR (old Mac style) at continuation."""
        source = "msg = First\r    Second"
        cursor = Cursor(source, 6)  # Start after "msg = "

        result = parse_pattern(cursor)

        # Should handle CR correctly
        assert result is not None
        # Pattern should contain text from both lines
        assert len(result.value.elements) > 0


# ============================================================================
# LINE 190: Adding Space When Last Element is Placeable
# ============================================================================


class TestLine190SpaceAfterPlaceable:
    """Test line 190: adding space element when last element is Placeable."""

    def test_pattern_multiline_continuation_after_placeable(self) -> None:
        """Test parse_pattern adds space when last element is Placeable (line 190).

        When a multiline continuation occurs and the last element is a Placeable
        (not text), a new TextElement with space is added (line 190).
        """
        bundle = FluentBundle("en_US")
        # Pattern with placeable followed by multiline continuation
        ftl = """msg = {NUMBER(5)}
    continued text"""
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")

        # Should have space between placeable and continued text
        assert "5" in result
        assert "continued text" in result


# ============================================================================
# LINE 207: Placeable Parsing Failure in parse_pattern
# ============================================================================


class TestLine207PlaceableParsingFailure:
    """Test line 207: parse_pattern returns None when placeable parsing fails."""

    def test_pattern_placeable_parse_fails(self) -> None:
        """Test parse_pattern returns None when parse_placeable fails (line 207)."""
        source = "Text {invalid"
        cursor = Cursor(source, 0)

        # Mock parse_placeable from rules module
        with patch(
            "ftllexengine.syntax.parser.rules.parse_placeable",
            return_value=None,
        ):
            result = parse_pattern(cursor)

        # Should return None when placeable parsing fails
        assert result is None


# ============================================================================
# BRANCH 227->171: False Branch of cursor.pos > text_start
# ============================================================================


class TestBranch227Line171NoTextCollected:
    """Test branch 227->171: False branch when cursor.pos == text_start."""

    def test_pattern_no_text_before_newline(self) -> None:
        """Test parse_pattern when cursor at newline with no text collected.

        When cursor is positioned at a newline and no text was collected
        (cursor.pos == text_start), the if at line 227 is False, and we
        skip adding a text element.
        """
        # Pattern that immediately ends with newline (no text to collect)
        source = "\n"
        cursor = Cursor(source, 0)

        result = parse_pattern(cursor)

        # Should parse successfully with empty pattern
        assert result is not None
        # Pattern should be empty or only contain placeholders
        assert len(result.value.elements) == 0

    def test_pattern_starts_with_placeable_then_newline(self) -> None:
        """Test parse_pattern with placeable immediately followed by newline.

        {$var}\n - after parsing placeable, cursor is at \n with text_start == cursor.pos
        """
        source = "{$var}\n"
        cursor = Cursor(source, 0)

        result = parse_pattern(cursor)

        # Should parse successfully
        assert result is not None
        # Should have only the placeable, no text element
        assert len(result.value.elements) == 1


# ============================================================================
# Integration Tests
# ============================================================================


class TestPatternsIntegration:
    """Integration tests for pattern parsing."""

    def test_complex_pattern_with_all_features(self) -> None:
        """Test complex pattern with multiline, CRLF, and placeables."""
        bundle = FluentBundle("en_US")
        ftl = """msg = Start {NUMBER(1)} middle\r
    continued {NUMBER(2)}
    final"""
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")

        # Should handle all features
        assert "Start" in result
        assert "1" in result
        assert "middle" in result
        assert "continued" in result
        assert "2" in result
        assert "final" in result

    def test_simple_pattern_in_select_expression(self) -> None:
        """Test parse_simple_pattern as used in select expressions."""
        bundle = FluentBundle("en_US")
        # Select expression uses parse_simple_pattern for variant patterns
        ftl = """msg = {NUMBER(1) ->
    [one] One item
    *[other] Many items
}"""
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")

        # Variant patterns should be parsed correctly
        # NUMBER(1) should match 'other' category
        assert "item" in result
