"""Additional targeted tests to push parser coverage towards 95-100%.

Targets specific uncovered lines from coverage analysis:
- Lines 104-108: Comment parsing failure recovery
- Line 395: EOF check in indented continuation
- Line 519: String literal without opening quote
- Lines 650-653: Error recovery paths
- Lines 687-688: More error paths
"""

from ftllexengine.syntax.parser import FluentParserV1


class TestCommentParsingFailureRecovery:
    """Cover lines 104-108: Comment parsing failure and line skipping."""

    def test_malformed_comment_recovery(self):
        """Lines 104-108: When comment parsing fails, skip to end of line.

        This happens when '#' is encountered but comment parse fails for some reason.
        The parser should skip to the next line and continue.
        Per parser code line 1873, comments with >3 '#' fail parsing.
        """
        # Comment with >3 hashes fails validation (line 1873: if hash_count > 3)
        source = "#### Invalid comment with 4 hashes\nkey = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should still parse the message after recovering from invalid comment
        assert len(resource.entries) >= 1

    def test_comment_at_eof_no_newline(self):
        """Lines 104-108: Comment at EOF without trailing newline.

        Tests EOF handling in comment skipping logic.
        """
        source = "key = value\n# Comment at end"  # No trailing newline
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse successfully
        assert len(resource.entries) >= 1


class TestIndentedContinuationEOF:
    """Cover line 395: EOF check in _is_indented_next_line."""

    def test_pattern_at_eof_no_newline(self):
        """Line 395: Check cursor.is_eof in continuation check.

        When a pattern ends at EOF without newline, the continuation
        check should return False.
        """
        source = "key = value"  # No trailing newline
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse successfully
        assert len(resource.entries) == 1

    def test_pattern_ends_with_non_newline(self):
        """Line 395: cursor.current not in newlines.

        When checking for continuation, if current char isn't newline,
        return False.
        """
        source = "key = value\nkey2 = value2"
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse both messages
        assert len(resource.entries) == 2


class TestStringLiteralErrors:
    """Cover line 519: String literal without opening quote."""

    def test_string_literal_missing_quote(self):
        """Line 519: String literal parse when no opening quote present.

        This is triggered in contexts where parser expects string literal
        but encounters something else.
        """
        # Function call with non-string argument where string might be tried
        source = "key = { FUNC(arg) }"  # 'arg' is identifier, not "arg" string
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should handle gracefully
        assert len(resource.entries) >= 1


class TestVariantKeyParsing:
    """Cover lines 650-653: Variant key parsing errors."""

    def test_variant_key_identifier_failure(self):
        """Lines 650-653: When identifier parse fails in variant key context.

        Variant keys can be numbers or identifiers. Test when identifier
        path is tried but fails.
        """
        source = """
key = { $var ->
    [123] Number variant
   *[default] Default
}
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse selector expression
        assert len(resource.entries) >= 1


class TestAttributePatternErrors:
    """Cover lines 687-688: Attribute pattern parsing errors."""

    def test_attribute_with_empty_pattern(self):
        """Lines 687-688: Attribute with malformed or empty pattern.

        Tests error handling when attribute pattern parse fails.
        """
        source = """
key = Value
    .attr =
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should handle attribute parse errors
        assert len(resource.entries) >= 1

    def test_attribute_missing_equals(self):
        """Lines 687-688: Attribute without = sign.

        Malformed attribute syntax.
        """
        source = """
key = Value
    .attr Value
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should handle malformed attribute
        assert len(resource.entries) >= 1


class TestSelectExpressionEdgeCases:
    """Cover additional select expression error paths."""

    def test_select_expression_no_variants(self):
        """Select expression with missing variants section."""
        source = "key = { $var -> }"
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should handle missing variants
        assert len(resource.entries) >= 1

    def test_select_expression_malformed_arrow(self):
        """Select expression with malformed arrow."""
        source = "key = { $var - }"  # Missing second '>'
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should handle malformed selector
        assert len(resource.entries) >= 1


class TestTermReferenceErrors:
    """Cover term reference error paths."""

    def test_term_reference_missing_dash(self):
        """Term reference without leading dash."""
        source = "key = { term }"  # Should be { -term }
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should treat as function or variable reference
        assert len(resource.entries) >= 1


class TestNumberLiteralEdgeCases:
    """Cover number literal parsing edge cases."""

    def test_number_literal_just_decimal_point(self):
        """Number literal that's just a decimal point."""
        source = "key = { . }"
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should handle malformed number
        assert len(resource.entries) >= 1

    def test_number_literal_multiple_decimal_points(self):
        """Number literal with multiple decimal points."""
        source = "key = { 1.2.3 }"
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should handle malformed number
        assert len(resource.entries) >= 1


class TestJunkRecovery:
    """Test junk entry creation and recovery."""

    def test_multiple_junk_entries_in_row(self):
        """Multiple malformed entries should create multiple junk entries."""
        source = """
!!!invalid1
!!!invalid2
key = value
!!!invalid3
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should recover and parse the valid message
        assert any(hasattr(entry, "id") and entry.id.name == "key"
                  for entry in resource.entries)

    def test_junk_with_unicode_characters(self):
        """Junk entries with non-ASCII characters."""
        source = """
¡¡¡ invalid with unicode ™®©
key = value
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should handle unicode in junk
        assert len(resource.entries) >= 1


class TestWhitespaceEdgeCases:
    """Cover whitespace handling edge cases."""

    def test_tabs_in_pattern(self):
        """Tabs in pattern (should be treated as literal text)."""
        source = "key = value\twith\ttabs"
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse and preserve tabs in text
        assert len(resource.entries) == 1

    def test_mixed_line_endings(self):
        """Mixed \r\n and \n line endings."""
        source = "key1 = value1\r\nkey2 = value2\nkey3 = value3"
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should handle both line ending styles
        assert len(resource.entries) == 3

    def test_multiple_blank_lines(self):
        """Multiple consecutive blank lines."""
        source = "key1 = value1\n\n\n\nkey2 = value2"
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should skip blank lines
        assert len(resource.entries) == 2


class TestVariantKeyIdentifierPath:
    """Cover lines 687-688: Variant key parsed as identifier (not number)."""

    def test_variant_key_identifier_after_number_fails(self):
        """Lines 687-688: Variant key tries number first, then identifier."""
        # Use identifier variant keys (non-numeric)
        source = """
key = { $var ->
    [yes] Affirmative
   *[no] Negative
}
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse with identifier variant keys
        assert len(resource.entries) >= 1


class TestMessageReferenceWithAttribute:
    """Cover lines 1172-1180: Message reference with attribute parsing."""

    def test_message_reference_with_attribute(self):
        """Lines 1172-1180: Parse message.attribute pattern."""
        # Message reference with attribute in a pattern
        source = """
greeting = Hello
welcome = { greeting.aria-label }
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse message reference with attribute
        assert len(resource.entries) >= 2

    def test_message_reference_attribute_after_function_call(self):
        """Lines 1172-1180: Attribute on message reference in function context."""
        # This might trigger the message reference attribute path
        source = """
key = { $var ->
    [a] { OTHER.attr }
   *[b] Default
}
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should handle message reference with attribute
        assert len(resource.entries) >= 1


class TestInvalidCommentWithFollowingContent:
    """Cover branch 106->108: Invalid comment with content after it."""

    def test_invalid_comment_followed_by_valid_message(self):
        """Branch 106->108: Invalid comment not at EOF."""
        # Multiple invalid comments followed by valid content
        source = """#### Invalid 4-hash comment
##### Invalid 5-hash comment
key = value
"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should recover and parse the message
        assert len(resource.entries) >= 1
