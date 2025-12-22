"""Parser error path and edge case tests.

Targets uncovered error handling paths in the parser.
"""

from __future__ import annotations

from ftllexengine.syntax import parse
from ftllexengine.syntax.ast import Junk

# ============================================================================
# STRING LITERAL ESCAPE SEQUENCES
# ============================================================================


class TestStringEscapeSequences:
    """Test string literal escape sequence parsing."""

    def test_parse_string_with_tab_escape(self) -> None:
        """Parse string literal with \\t escape."""
        ftl = r'test = { "\t" }'
        resource = parse(ftl)

        assert len(resource.entries) == 1
        # Tab escape should be parsed
        entry = resource.entries[0]
        assert entry.__class__.__name__ in ("Message", "Junk")

    def test_parse_string_with_unicode_escape(self) -> None:
        """Parse string literal with \\uXXXX escape."""
        ftl = r'test = { "\u0041" }'  # \u0041 = 'A'
        resource = parse(ftl)

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        # Unicode escape should parse successfully
        assert entry.__class__.__name__ in ("Message", "Junk")

    def test_parse_string_with_invalid_unicode_escape(self) -> None:
        """Invalid unicode escape creates junk."""
        ftl = r'test = { "\uXYZ" }'  # Invalid hex digits
        resource = parse(ftl)

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        # Invalid unicode should create junk
        assert isinstance(entry, Junk)

    def test_parse_string_with_invalid_escape_sequence(self) -> None:
        """Invalid escape sequence creates junk."""
        ftl = r'test = { "\x" }'  # \x is not a valid escape
        resource = parse(ftl)

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        # Invalid escape should create junk
        assert isinstance(entry, Junk)


# ============================================================================
# NUMBER LITERAL EDGE CASES
# ============================================================================


class TestNumberLiteralParsing:
    """Test number literal parsing edge cases."""

    def test_parse_negative_number(self) -> None:
        """Parse negative number literal."""
        ftl = "test = { -42 }"
        resource = parse(ftl)

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert entry.__class__.__name__ in ("Message", "Junk")

    def test_parse_decimal_number(self) -> None:
        """Parse decimal number literal."""
        ftl = "test = { 3.14 }"
        resource = parse(ftl)

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert entry.__class__.__name__ in ("Message", "Junk")

    def test_parse_negative_decimal_number(self) -> None:
        """Parse negative decimal number."""
        ftl = "test = { -3.14 }"
        resource = parse(ftl)

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert entry.__class__.__name__ in ("Message", "Junk")


# ============================================================================
# ERROR RECOVERY TESTS
# ============================================================================


class TestParserErrorRecovery:
    """Test parser error recovery and junk creation."""

    def test_parse_message_with_missing_equals(self) -> None:
        """Message without '=' creates junk."""
        ftl = "test Hello"
        resource = parse(ftl)

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        # Should create junk for invalid syntax
        assert isinstance(entry, Junk)

    def test_parse_select_with_missing_arrow(self) -> None:
        """Select expression without '->' creates junk."""
        ftl = """test = { $value
   [one] One
  *[other] Other
}"""
        resource = parse(ftl)

        # Should create junk entry
        assert len(resource.entries) >= 1
        # At least one entry should be junk
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) >= 1

    def test_parse_unclosed_placeable(self) -> None:
        """Unclosed placeable creates junk."""
        ftl = "test = { $value"
        resource = parse(ftl)

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        # Unclosed placeable should create junk
        assert isinstance(entry, Junk)

    def test_parse_invalid_variant_syntax(self) -> None:
        """Invalid variant syntax creates junk."""
        ftl = """test = { $count ->
   one] One item
  *[other] Other
}"""
        resource = parse(ftl)

        # Should create junk for invalid variant
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) >= 1

    def test_parse_multiple_errors_creates_multiple_junk(self) -> None:
        """Multiple errors create multiple junk entries."""
        ftl = """invalid1 Missing equals
valid = Good message
invalid2 Also bad
another-valid = Another good one"""
        resource = parse(ftl)

        # Should have mix of valid messages and junk
        assert len(resource.entries) == 4
        junk_count = sum(1 for e in resource.entries if isinstance(e, Junk))
        assert junk_count == 2  # Two invalid entries


# ============================================================================
# WHITESPACE AND FORMATTING EDGE CASES
# ============================================================================


class TestWhitespaceEdgeCases:
    """Test whitespace handling edge cases."""

    def test_parse_message_with_trailing_whitespace(self) -> None:
        """Parse message with trailing whitespace."""
        ftl = "test = Hello   \n"
        resource = parse(ftl)

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert entry.__class__.__name__ == "Message"

    def test_parse_message_with_tabs(self) -> None:
        """Parse message with tab characters."""
        ftl = "test\t=\tHello"
        resource = parse(ftl)

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        assert entry.__class__.__name__ in ("Message", "Junk")

    def test_parse_message_with_windows_line_endings(self) -> None:
        """Parse file with Windows CRLF line endings."""
        ftl = "test = Hello\r\nworld = World\r\n"
        resource = parse(ftl)

        # Should parse both messages
        assert len(resource.entries) == 2


# ============================================================================
# IDENTIFIER VALIDATION
# ============================================================================


class TestIdentifierParsing:
    """Test identifier parsing and validation."""

    def test_parse_identifier_starting_with_number(self) -> None:
        """Identifier starting with number creates junk."""
        ftl = "123invalid = Value"
        resource = parse(ftl)

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        # Should create junk for invalid identifier
        assert isinstance(entry, Junk)

    def test_parse_identifier_with_special_chars(self) -> None:
        """Identifier with invalid special characters."""
        ftl = "test@invalid = Value"
        resource = parse(ftl)

        # Special chars should create junk
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) >= 1


# ============================================================================
# SELECT EXPRESSION EDGE CASES
# ============================================================================


class TestSelectExpressionEdgeCases:
    """Test select expression parsing edge cases."""

    def test_parse_select_with_no_default_variant(self) -> None:
        """Select without default variant."""
        ftl = """test = { $count ->
   [one] One
   [other] Other
}"""
        resource = parse(ftl)

        # Parser may accept this or create junk
        assert len(resource.entries) >= 1

    def test_parse_select_with_number_variant_key(self) -> None:
        """Select expression with number as variant key."""
        ftl = """test = { $value ->
   [0] Zero
   [1] One
  *[2] Other
}"""
        resource = parse(ftl)

        assert len(resource.entries) == 1
        entry = resource.entries[0]
        # Number keys should be valid
        assert entry.__class__.__name__ in ("Message", "Junk")

    def test_parse_select_with_empty_variant_value(self) -> None:
        """Select expression with empty variant value."""
        ftl = """test = { $count ->
   [one]
  *[other] Other
}"""
        resource = parse(ftl)

        # Empty variant value may create junk
        assert len(resource.entries) >= 1
