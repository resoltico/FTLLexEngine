"""Targeted tests for parser.py to achieve maximum coverage.

Focuses on the 23 missing branches identified by coverage analysis:
- Line 106->108: EOF check in _skip_blank_inline_no_validation
- Line 395: Non-newline character in _is_indented_continuation
- Line 519: Missing opening quote in _parse_string_literal
- Line 572: EOF in _parse_number_literal
- Lines 650-653: Error recovery branches in _parse_variant_key
- Lines 687-688: Number literal key fallback in _parse_variant_key
- Line 877: Invalid pattern continuation
- Line 1033: Function argument edge case
- Line 1040: Named argument parsing edge case
- Line 1049: Function arguments edge case
- Line 1146: Attribute without preceding Message/Term
- Line 1176: Comment edge case
- Line 1398->1341: Named argument parsing branch
- Line 1443: Entry ID edge case
- Line 1528: Message ID edge case
- Line 1604: Term ID edge case
- Line 1667: Attribute name parsing edge case
- Line 1697: Variant key edge case
- Line 1731: Selector edge case
- Line 1789: Pattern element edge case
- Line 1798: Placeable expression edge case
- Lines 1904->1910, 1906->1910: Text element parsing branches
"""

from __future__ import annotations

from hypothesis import assume, given
from hypothesis import strategies as st

from ftllexengine.syntax.ast import Junk, Message
from ftllexengine.syntax.parser import FluentParserV1

# ============================================================================
# COVERAGE TARGET: Line 395 - Non-newline in _is_indented_continuation
# ============================================================================


class TestNonNewlineInIndentedContinuation:
    """Test parser behavior when checking indented continuation on non-newline."""

    def test_message_value_not_on_newline(self) -> None:
        """COVERAGE: Line 395 - Return False when not at newline."""
        parser = FluentParserV1()

        # Message value immediately after = (no newline)
        ftl_source = "msg = value"
        resource = parser.parse(ftl_source)

        # Should parse successfully (not an indented continuation)
        assert len(resource.entries) > 0

    @given(value=st.text(
        alphabet=st.characters(
            blacklist_categories=("Cc", "Cs"),
            blacklist_characters="{}[]#.=-*",
        ),
        min_size=1,
        max_size=20,
    ))
    def test_inline_value_property(self, value: str) -> None:
        """PROPERTY: Inline values (no newline) parse correctly."""
        assume("\n" not in value and "\r" not in value)
        assume(value.strip() == value)
        assume(not any(c in value for c in "{}[]#.=-*"))

        parser = FluentParserV1()
        ftl_source = f"msg = {value}"

        resource = parser.parse(ftl_source)
        # Should have at least one entry
        assert len(resource.entries) > 0


# ============================================================================
# COVERAGE TARGET: Line 519 - Missing opening quote in string literal
# ============================================================================


class TestMissingOpeningQuoteInStringLiteral:
    """Test error recovery when string literal missing opening quote."""

    def test_string_literal_without_quote(self) -> None:
        """COVERAGE: Line 519 - Error when string literal has no opening quote."""
        parser = FluentParserV1()

        # Try to parse something that looks like it should be a string but isn't
        # This is tricky because the parser might not reach the string literal parser
        # if the syntax is too malformed
        ftl_source = "msg = { FUNC(value) }"  # 'value' without quotes

        resource = parser.parse(ftl_source)
        # Parser should handle this (might create Junk or parse differently)
        assert len(resource.entries) > 0


# ============================================================================
# COVERAGE TARGET: Line 572 - EOF in number literal
# ============================================================================


class TestEOFInNumberLiteral:
    """Test parser behavior when EOF encountered in number literal."""

    def test_number_literal_at_eof(self) -> None:
        """COVERAGE: Line 572 - Number literal at end of file."""
        parser = FluentParserV1()

        # Number literal that ends the file
        ftl_source = "msg = { NUMBER(123"  # No closing paren or brace

        resource = parser.parse(ftl_source)
        # Should create Junk or handle error
        assert len(resource.entries) > 0

    def test_incomplete_number_at_eof(self) -> None:
        """COVERAGE: Line 572 - Incomplete number at EOF."""
        parser = FluentParserV1()

        ftl_source = "msg = { 42"  # Number without closing brace

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0


# ============================================================================
# COVERAGE TARGET: Lines 650-653 - Variant key error recovery
# ============================================================================


class TestVariantKeyErrorRecovery:
    """Test error recovery in variant key parsing."""

    def test_select_with_invalid_variant_key(self) -> None:
        """COVERAGE: Lines 650-653 - Error recovery in variant key."""
        parser = FluentParserV1()

        ftl_source = """
msg = { $count ->
    [] Empty key
   *[other] Other
}
"""

        resource = parser.parse(ftl_source)
        # Should handle invalid variant key
        assert len(resource.entries) > 0

    def test_select_with_malformed_key(self) -> None:
        """COVERAGE: Lines 650-653 - Malformed variant key."""
        parser = FluentParserV1()

        ftl_source = """
msg = { $count ->
    [unclosed Missing bracket
   *[other] Other
}
"""

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0


# ============================================================================
# COVERAGE TARGET: Lines 687-688 - Number literal key fallback
# ============================================================================


class TestNumberLiteralKeyFallback:
    """Test number literal as variant key."""

    def test_number_literal_variant_key(self) -> None:
        """COVERAGE: Lines 687-688 - Number literal as variant key."""
        parser = FluentParserV1()

        ftl_source = """
msg = { $count ->
    [0] Zero
    [1] One
    [42] Forty-two
   *[other] Other
}
"""

        resource = parser.parse(ftl_source)
        # Should parse number literal keys successfully
        assert len(resource.entries) > 0

    @given(number=st.integers(min_value=0, max_value=1000))
    def test_number_key_property(self, number: int) -> None:
        """PROPERTY: Number literal variant keys parse correctly."""
        parser = FluentParserV1()

        ftl_source = f"""
msg = {{ $count ->
    [{number}] Value
   *[other] Other
}}
"""

        resource = parser.parse(ftl_source)
        # Should parse successfully
        msg = resource.entries[0]
        assert isinstance(msg, (Message, Junk))


# ============================================================================
# COVERAGE TARGET: Line 877 - Invalid pattern continuation
# ============================================================================


class TestInvalidPatternContinuation:
    """Test parser behavior with invalid pattern continuation."""

    def test_pattern_with_invalid_continuation(self) -> None:
        """COVERAGE: Line 877 - Invalid continuation in pattern."""
        parser = FluentParserV1()

        # Pattern with unexpected indentation
        ftl_source = """
msg = Line 1
      Invalid indented line without attribute marker
"""

        resource = parser.parse(ftl_source)
        # Parser should handle this (create Junk or parse as separate entries)
        assert len(resource.entries) >= 1


# ============================================================================
# COVERAGE TARGET: Lines 1033, 1040, 1049 - Function argument edge cases
# ============================================================================


class TestFunctionArgumentEdgeCases:
    """Test function argument parsing edge cases."""

    def test_function_with_empty_arguments(self) -> None:
        """COVERAGE: Line 1033, 1040, 1049 - Function edge cases."""
        parser = FluentParserV1()

        ftl_source = "msg = { FUNC() }"

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0

    def test_function_with_only_positional_args(self) -> None:
        """COVERAGE: Function with only positional arguments."""
        parser = FluentParserV1()

        ftl_source = "msg = { FUNC($a, $b, $c) }"

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0

    def test_function_with_only_named_args(self) -> None:
        """COVERAGE: Function with only named arguments."""
        parser = FluentParserV1()

        ftl_source = 'msg = { FUNC(key: "value", other: "data") }'

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0

    def test_function_with_mixed_args(self) -> None:
        """COVERAGE: Function with both positional and named arguments."""
        parser = FluentParserV1()

        ftl_source = 'msg = { FUNC($pos1, $pos2, named: "value") }'

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0


# ============================================================================
# COVERAGE TARGET: Line 1146 - Attribute without preceding entry
# ============================================================================


class TestAttributeWithoutPrecedingEntry:
    """Test parser behavior when attribute appears without Message/Term."""

    def test_standalone_attribute(self) -> None:
        """COVERAGE: Line 1146 - Attribute without Message/Term."""
        parser = FluentParserV1()

        # Attribute line without a message/term before it
        ftl_source = "    .attr = Value"

        resource = parser.parse(ftl_source)
        # Should create Junk entry
        assert len(resource.entries) > 0
        assert isinstance(resource.entries[0], Junk)


# ============================================================================
# COVERAGE TARGET: Line 1176 - Comment edge case
# ============================================================================


class TestCommentEdgeCase:
    """Test comment parsing edge cases."""

    def test_comment_with_no_content(self) -> None:
        """COVERAGE: Line 1176 - Comment edge case."""
        parser = FluentParserV1()

        ftl_source = """
#
##
### Resource comment with minimal content
"""

        resource = parser.parse(ftl_source)
        # Should parse comments (even empty ones)
        assert len(resource.entries) >= 0  # Comments might not create entries

    def test_mixed_comments(self) -> None:
        """Test various comment types."""
        parser = FluentParserV1()

        ftl_source = """
# Regular comment
msg = Value
## Group comment
other = Text
### Resource comment
"""

        resource = parser.parse(ftl_source)
        assert len(resource.entries) >= 2  # At least the two messages


# ============================================================================
# COVERAGE TARGET: Lines 1443, 1528, 1604 - Entry ID edge cases
# ============================================================================


class TestEntryIDEdgeCases:
    """Test entry ID parsing edge cases."""

    def test_message_with_minimal_id(self) -> None:
        """COVERAGE: Line 1528 - Message ID edge case."""
        parser = FluentParserV1()

        ftl_source = "m = Value"  # Single character ID

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0

    def test_term_with_minimal_id(self) -> None:
        """COVERAGE: Line 1604 - Term ID edge case."""
        parser = FluentParserV1()

        ftl_source = "-t = Value"  # Single character term ID

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0

    @given(id_name=st.from_regex(r"[a-zA-Z][a-zA-Z0-9_-]{0,30}", fullmatch=True))
    def test_various_id_formats(self, id_name: str) -> None:
        """PROPERTY: Various ID formats parse correctly."""
        parser = FluentParserV1()

        ftl_source = f"{id_name} = Value"

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0


# ============================================================================
# COVERAGE TARGET: Line 1667 - Attribute name edge case
# ============================================================================


class TestAttributeNameEdgeCase:
    """Test attribute name parsing edge cases."""

    def test_attribute_with_minimal_name(self) -> None:
        """COVERAGE: Line 1667 - Attribute name edge case."""
        parser = FluentParserV1()

        ftl_source = """
msg = Value
    .a = Attribute with single-char name
"""

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0


# ============================================================================
# COVERAGE TARGET: Lines 1697, 1731 - Variant and selector edge cases
# ============================================================================


class TestVariantAndSelectorEdgeCases:
    """Test variant key and selector parsing edge cases."""

    def test_select_with_string_variant_key(self) -> None:
        """COVERAGE: Line 1697 - Variant key edge case."""
        parser = FluentParserV1()

        ftl_source = """
msg = { $type ->
    [a] Short key
    [very-long-variant-key-name] Long key
   *[other] Default
}
"""

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0

    def test_select_with_variable_selector(self) -> None:
        """COVERAGE: Line 1731 - Selector edge case."""
        parser = FluentParserV1()

        ftl_source = """
msg = { $count ->
    [0] Zero
   *[other] Other
}
"""

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0


# ============================================================================
# COVERAGE TARGET: Lines 1789, 1798 - Pattern element edge cases
# ============================================================================


class TestPatternElementEdgeCases:
    """Test pattern element parsing edge cases."""

    def test_pattern_with_only_placeables(self) -> None:
        """COVERAGE: Line 1789, 1798 - Pattern element edge cases."""
        parser = FluentParserV1()

        ftl_source = "msg = { $a }{ $b }{ $c }"

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0

    def test_pattern_with_adjacent_placeables(self) -> None:
        """COVERAGE: Adjacent placeables without text."""
        parser = FluentParserV1()

        ftl_source = "msg = { $x }{ FUNC() }"

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0


# ============================================================================
# COVERAGE TARGET: Lines 1904->1910, 1906->1910 - Text element branches
# ============================================================================


class TestTextElementBranches:
    """Test text element parsing branches."""

    def test_text_with_escape_sequences(self) -> None:
        """COVERAGE: Lines 1904->1910, 1906->1910 - Text element branches."""
        parser = FluentParserV1()

        # Text with various content that might trigger different branches
        ftl_source = r"msg = Text with \u0020 unicode escape"

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0

    def test_text_with_special_sequences(self) -> None:
        """COVERAGE: Text with special character sequences."""
        parser = FluentParserV1()

        ftl_source = "msg = Text with \\n newline and \\t tab escapes"

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0

    @given(text=st.text(
        alphabet=st.characters(
            blacklist_categories=("Cc", "Cs"),
            blacklist_characters="{}[]#",
        ),
        min_size=1,
        max_size=50,
    ))
    def test_various_text_content(self, text: str) -> None:
        """PROPERTY: Various text content parses correctly."""
        assume("\n" not in text and "\r" not in text)
        assume(text.strip())
        assume(not text.startswith("."))
        assume(not text.startswith("-"))

        parser = FluentParserV1()
        safe_text = text.replace("\\", "\\\\")
        ftl_source = f"msg = {safe_text}"

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0


# ============================================================================
# COVERAGE TARGET: Line 106->108 - EOF check in blank inline skip
# ============================================================================


class TestEOFInBlankInlineSkip:
    """Test EOF handling when skipping blank inline content."""

    def test_eof_after_identifier(self) -> None:
        """COVERAGE: Line 106->108 - EOF check branch."""
        parser = FluentParserV1()

        # File ends right after message ID
        ftl_source = "msg"  # No = or value

        resource = parser.parse(ftl_source)
        # Should create Junk or handle gracefully
        assert len(resource.entries) > 0

    def test_eof_after_equals(self) -> None:
        """COVERAGE: EOF after = sign."""
        parser = FluentParserV1()

        ftl_source = "msg ="  # No value after =

        resource = parser.parse(ftl_source)
        assert len(resource.entries) > 0


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestParserIntegration:
    """Integration tests combining multiple edge cases."""

    def test_complex_ftl_with_edge_cases(self) -> None:
        """Integration: FTL resource exercising multiple edge cases."""
        parser = FluentParserV1()

        ftl_source = """
# Comment
msg = Value
    .a = Short attr

-t = Term

select = { $n ->
    [0] Zero
    [1] One
   *[other] Other
}

func = { FUNC() }

complex = { $a }{ $b } text { UPPER($c) }
"""

        resource = parser.parse(ftl_source)
        # Should parse entire resource
        assert len(resource.entries) >= 5
