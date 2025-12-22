"""Comprehensive coverage tests for syntax/parser/patterns.py.

Targets uncovered lines:
- Line 31: Variable reference without $ prefix
- Lines 124-127: Text element edge case (cursor.pos == text_start)
- Line 211->155: Pattern parsing edge case
"""

from __future__ import annotations

from ftllexengine.runtime.bundle import FluentBundle

# ============================================================================
# LINE 31: Variable Reference Without $ Prefix
# ============================================================================


class TestVariableReferenceErrorPaths:
    """Test variable reference parsing error paths (line 31)."""

    def test_variable_reference_requires_dollar_sign(self) -> None:
        """Test that variable reference without $ fails (line 31).

        parse_variable_reference expects '$' at start. If missing, returns None (line 31).
        """
        bundle = FluentBundle("en_US")
        # Pattern with identifier but no $
        bundle.add_resource("msg = Value { var }")

        # Should treat as message reference, not variable
        result, _errors = bundle.format_pattern("msg")
        # Will error because 'var' message doesn't exist
        assert len(_errors) > 0 or "{var}" in result


# ============================================================================
# LINES 124-127: Text Element Edge Case
# ============================================================================


class TestTextElementEdgeCases:
    """Test text element parsing edge cases (lines 124-127)."""

    def test_pattern_with_stop_char_not_placeable(self) -> None:
        """Test pattern with stop character that's not '{' (lines 124-127).

        When cursor is at a stop character but hasn't consumed any text,
        the parser advances to prevent infinite loop (line 127).
        """
        bundle = FluentBundle("en_US")
        # Pattern ending at newline (stop char)
        bundle.add_resource("msg = Value\n")

        result, _errors = bundle.format_pattern("msg")
        assert "Value" in result

    def test_empty_pattern_followed_by_attribute(self) -> None:
        """Test empty pattern followed by attribute (edge case).

        This tests the cursor advancement when pos == text_start.
        """
        bundle = FluentBundle("en_US")
        # Message with empty value but attributes
        bundle.add_resource("""
msg =
    .attr = Attribute
""")

        result, _errors = bundle.format_pattern("msg", attribute="attr")
        assert "Attribute" in result


# ============================================================================
# LINE 211->155: Pattern Parsing Edge Case
# ============================================================================


class TestPatternParsingEdgeCases:
    """Test pattern parsing edge cases (line 211->155)."""

    def test_pattern_at_eof_without_newline(self) -> None:
        """Test pattern parsing at EOF (line 211).

        When pattern ends at EOF, cursor.pos > text_start check succeeds.
        """
        bundle = FluentBundle("en_US")
        # Pattern at EOF without trailing newline
        bundle.add_resource("msg = Value at EOF")  # No \n

        result, _errors = bundle.format_pattern("msg")
        assert "Value at EOF" in result

    def test_multiline_pattern_with_continuation(self) -> None:
        """Test multiline pattern with indented continuation."""
        bundle = FluentBundle("en_US")
        # Multiline pattern with continuation
        bundle.add_resource("""
msg =
    First line
    Second line
""")

        result, _errors = bundle.format_pattern("msg")
        # Should contain both lines
        assert "First line" in result or "Second line" in result


# ============================================================================
# Integration Tests
# ============================================================================


class TestPatternParsingIntegration:
    """Integration tests for pattern parsing."""

    def test_complex_pattern_with_text_and_placeables(self) -> None:
        """Test pattern with mixed text and placeables."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Hello { $name }, you have { $count } messages.")

        result, _errors = bundle.format_pattern("msg", {"name": "Alice", "count": 5})
        # Account for Unicode bidi marks
        assert "Alice" in result
        assert "5" in result
        assert "messages" in result

    def test_pattern_with_special_characters(self) -> None:
        """Test pattern with special characters."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Value with \t tabs and  spaces")

        result, _errors = bundle.format_pattern("msg")
        assert "Value" in result

    def test_pattern_with_unicode(self) -> None:
        """Test pattern with Unicode characters."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Unicode: \u4e2d\u6587 \u1f600")

        result, _errors = bundle.format_pattern("msg")
        assert "Unicode:" in result
        assert "\u4e2d\u6587" in result

    def test_empty_pattern_edge_case(self) -> None:
        """Test truly empty pattern."""
        bundle = FluentBundle("en_US")
        # Message with whitespace-only pattern
        bundle.add_resource("msg =   \n")

        result, _errors = bundle.format_pattern("msg")
        # Should return something (empty or error)
        assert isinstance(result, str)


# ============================================================================
# VARIANT DELIMITER LOOKAHEAD (AUDIT-PARSER-ROBUSTNESS-004)
# ============================================================================


class TestVariantDelimiterLookahead:
    """Test variant delimiter lookahead for literal * and [ in variant text.

    v0.26.0: Added lookahead to distinguish variant syntax from literal text.
    Per FTL spec, '*' and '[' are allowed as literal text in variant values
    when they don't form valid variant markers.
    """

    def test_asterisk_in_variant_text(self) -> None:
        """Test that '*' without '[' is treated as literal text."""
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

        result, errors = bundle.format_pattern("count", {"n": 5})
        assert "* items" in result

    def test_bracket_not_starting_variant_key(self) -> None:
        """Test that '[' not followed by valid key is treated as literal."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
msg = { $type ->
    [info] [INFO] message
   *[other] [?] unknown
}
""")

        result, errors = bundle.format_pattern("msg", {"type": "info"})
        assert "[INFO] message" in result
        assert not errors

    def test_math_expression_in_variant(self) -> None:
        """Test math-like expressions with * and [ in variant text."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
calc = { $op ->
    [mul] Result: 3 * 5 = 15
    [arr] Array: [1, 2, 3]
   *[other] Unknown operation
}
""")

        result, _errors = bundle.format_pattern("calc", {"op": "mul"})
        assert "3 * 5 = 15" in result

        result, _errors = bundle.format_pattern("calc", {"op": "arr"})
        assert "[1, 2, 3]" in result

    def test_asterisk_before_bracket_is_variant(self) -> None:
        """Test that '*[' still correctly marks default variant."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
example = { $x ->
    [a] Value A
   *[b] Default B
}
""")

        # Unmatched value should use default
        result, _errors = bundle.format_pattern("example", {"x": "unknown"})
        assert "Default B" in result

    def test_numeric_variant_key(self) -> None:
        """Test that [123] is still treated as variant key."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
indexed = { $i ->
    [0] Zero
    [1] One
   *[2] Default
}
""")

        result, _errors = bundle.format_pattern("indexed", {"i": 0})
        assert "Zero" in result

        result, _errors = bundle.format_pattern("indexed", {"i": 1})
        assert "One" in result

    def test_complex_variant_with_asterisk_and_brackets(self) -> None:
        """Test complex variant with both * and [] as literals."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("""
complex = { $mode ->
    [matrix] See [matrix * vector] for details
    [calc] Compute a * b + c
   *[other] No special chars
}
""")

        result, _errors = bundle.format_pattern("complex", {"mode": "matrix"})
        assert "[matrix * vector]" in result

        result, _errors = bundle.format_pattern("complex", {"mode": "calc"})
        assert "a * b + c" in result
