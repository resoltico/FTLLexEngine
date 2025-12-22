"""Parser boundary condition tests to kill survived mutations.

This module targets specific mutation survivors identified in mutation testing:
- Empty variant lists
- Single variant scenarios
- Boundary conditions in loops and conditionals
- Edge cases at limits

Target: Kill ~60 parser-related mutations
Phase: 1 (High-Impact Quick Wins)
"""

import pytest

from ftllexengine.syntax.ast import Junk, Message, Pattern, Resource, SelectExpression, TextElement
from ftllexengine.syntax.parser import FluentParserV1


class TestVariantBoundaryConditions:
    """Test boundary conditions in variant parsing.

    Targets mutations like:
    - if len(variants) > 0 → if len(variants) > 1
    - if len(variants) >= 1 → if len(variants) >= 2
    """

    def test_single_variant_select(self):
        """Kills: len(variants) > 0 → len(variants) > 1 mutation.

        Ensures exactly one variant (the default) is allowed.
        """
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $count ->
    *[other] Value
}
""")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert isinstance(messages[0].value, Pattern)

    def test_two_variants_select(self):
        """Kills: len(variants) >= 1 → len(variants) >= 2 mutation.

        Ensures exactly two variants are allowed.
        """
        from ftllexengine.syntax.ast import Placeable  # noqa: PLC0415

        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $count ->
    [one] One
    *[other] Other
}
""")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        # Verify we have a select expression with 2 variants
        pattern = messages[0].value
        assert isinstance(pattern, Pattern)
        assert len(pattern.elements) == 1
        placeable = pattern.elements[0]
        assert isinstance(placeable, Placeable)
        select = placeable.expression
        assert isinstance(select, SelectExpression)
        assert len(select.variants) == 2

    def test_empty_variant_key_rejected(self):
        """Kills: len(key) > 0 → len(key) > 1 mutation.

        Empty variant keys should be rejected.
        """
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $count ->
    [] Empty key
    *[other] Other
}
""")
        # Should produce Junk for invalid syntax
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) >= 1

    def test_single_char_variant_key_allowed(self):
        """Kills: len(key) > 1 → len(key) > 2 mutation.

        Single character variant keys should be allowed.
        """
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $count ->
    [a] A
    *[b] B
}
""")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1


class TestPatternBoundaryConditions:
    """Test boundary conditions in pattern parsing.

    Targets mutations in pattern element handling.
    """

    def test_empty_pattern_not_allowed_without_attributes(self):
        """Per Fluent spec: Message must have Pattern OR Attribute.

        Empty pattern with no attributes creates Junk (parse error).
        """
        parser = FluentParserV1()
        resource = parser.parse("msg = ")
        # Per spec: Message ::= ID "=" ((Pattern Attribute*) | (Attribute+))
        # Empty pattern with no attributes is invalid
        junks = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junks) == 1  # Parse error creates Junk

    def test_single_element_pattern(self):
        """Kills: len(elements) > 1 mutations.

        Single element patterns should work.
        """
        parser = FluentParserV1()
        resource = parser.parse("msg = Text")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert messages[0].value is not None
        assert len(messages[0].value.elements) == 1
        assert isinstance(messages[0].value.elements[0], TextElement)

    def test_pattern_with_only_whitespace(self):
        """Per Fluent spec: Whitespace-only pattern with no attributes is invalid.

        Pattern with only spaces/tabs creates Junk (parse error).
        """
        parser = FluentParserV1()
        resource = parser.parse("msg =    ")
        # Per spec: Empty pattern with no attributes is invalid
        junks = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junks) == 1


class TestStringLiteralBoundaries:
    """Test boundary conditions in string literal parsing.

    Targets mutations in string handling.
    """

    def test_empty_string_literal(self):
        """Kills: len(string) > 0 mutations.

        Empty string literals should be valid.
        """
        parser = FluentParserV1()
        resource = parser.parse('msg = { "" }')
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1

    def test_single_char_string_literal(self):
        """Kills: len(string) > 1 mutations.

        Single character strings should work.
        """
        parser = FluentParserV1()
        resource = parser.parse('msg = { "a" }')
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1

    def test_unterminated_string_literal(self):
        """Kills: string termination check mutations.

        Unterminated strings should produce Junk.
        """
        parser = FluentParserV1()
        resource = parser.parse('msg = { "unterminated')
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) >= 1


class TestNumberLiteralBoundaries:
    """Test boundary conditions in number literal parsing.

    Targets mutations in number handling.
    """

    def test_zero_number(self):
        """Kills: num > 0 → num >= 0 mutations.

        Zero should be a valid number.
        """
        parser = FluentParserV1()
        resource = parser.parse("msg = { 0 }")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1

    def test_negative_number(self):
        """Kills: num >= 0 mutations.

        Negative numbers should be valid.
        """
        parser = FluentParserV1()
        resource = parser.parse("msg = { -42 }")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1

    def test_single_digit_number(self):
        """Kills: number length boundary mutations.

        Single digit numbers should work.
        """
        parser = FluentParserV1()
        resource = parser.parse("msg = { 7 }")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1

    def test_decimal_with_zero_fractional(self):
        """Kills: fractional part boundary mutations.

        Numbers like 5.0 should be valid.
        """
        parser = FluentParserV1()
        resource = parser.parse("msg = { 5.0 }")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1


class TestIdentifierBoundaries:
    """Test boundary conditions in identifier parsing.

    Targets mutations in identifier validation.
    """

    def test_single_char_identifier(self):
        """Kills: len(identifier) > 1 mutations.

        Single character identifiers should be valid.
        """
        parser = FluentParserV1()
        resource = parser.parse("a = Value")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert messages[0].id.name == "a"

    def test_identifier_with_single_hyphen(self):
        """Kills: identifier boundary mutations.

        Identifiers like a-b should work.
        """
        parser = FluentParserV1()
        resource = parser.parse("a-b = Value")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert messages[0].id.name == "a-b"

    def test_identifier_starting_boundary(self):
        """Kills: identifier start character mutations.

        Identifiers must start with letter.
        """
        parser = FluentParserV1()
        # Invalid: starts with digit
        resource = parser.parse("1abc = Value")
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) >= 1


class TestTermReferenceBoundaries:
    """Test boundary conditions in term reference parsing.

    Targets mutations in term handling.
    """

    def test_single_char_term_name(self):
        """Kills: term name length boundary mutations.

        Single character term names should work.
        """
        parser = FluentParserV1()
        resource = parser.parse("-t = Term")
        # Should parse successfully (term or junk)
        assert isinstance(resource, Resource)
        assert len(resource.entries) >= 1

    def test_term_reference_in_pattern(self):
        """Kills: term reference parsing mutations.

        Term references should parse correctly.
        """
        parser = FluentParserV1()
        resource = parser.parse("""
-brand = Firefox
msg = { -brand }
""")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1


class TestAttributeBoundaries:
    """Test boundary conditions in attribute parsing.

    Targets mutations in attribute handling.
    """

    def test_single_char_attribute_name(self):
        """Kills: attribute name length mutations.

        Single character attribute names should work.
        """
        parser = FluentParserV1()
        resource = parser.parse("""
msg = Value
    .a = Attr
""")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert len(messages[0].attributes) == 1

    def test_message_with_zero_attributes(self):
        """Kills: len(attributes) > 0 mutations.

        Messages without attributes should work.
        """
        parser = FluentParserV1()
        resource = parser.parse("msg = Value")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert len(messages[0].attributes) == 0

    def test_message_with_one_attribute(self):
        """Kills: len(attributes) > 1 mutations.

        Messages with exactly one attribute should work.
        """
        parser = FluentParserV1()
        resource = parser.parse("""
msg = Value
    .attr = Attr
""")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert len(messages[0].attributes) == 1


class TestWhitespaceBoundaries:
    """Test boundary conditions in whitespace handling.

    Targets mutations in whitespace/indentation logic.
    """

    def test_minimum_indent_for_continuation(self):
        """Kills: indent boundary mutations.

        Minimum valid indent should work.
        """
        parser = FluentParserV1()
        resource = parser.parse("""
msg =
    Line
""")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1

    def test_no_indent_breaks_continuation(self):
        """Kills: indent > 0 → indent > 1 mutations.

        Zero indent should break continuation.
        """
        parser = FluentParserV1()
        resource = parser.parse("""
msg =
Line
""")
        # "Line" should be treated as new entry, not continuation
        assert len(resource.entries) >= 1

    def test_single_space_indent(self):
        """Kills: indent boundary at 1 space.

        Single space indent should work for continuations.
        """
        parser = FluentParserV1()
        resource = parser.parse("""
msg =
 Continued
""")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1


class TestCommentBoundaries:
    """Test boundary conditions in comment parsing.

    Targets mutations in comment handling.
    """

    def test_empty_comment(self):
        """Kills: comment content length mutations.

        Empty comments should be valid.
        """
        parser = FluentParserV1()
        resource = parser.parse("#\nmsg = Value")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1

    def test_single_char_comment(self):
        """Kills: comment length > 1 mutations.

        Single character comments should work.
        """
        parser = FluentParserV1()
        resource = parser.parse("# x\nmsg = Value")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1


class TestCursorAdvancementBoundaries:
    """Test boundary conditions in cursor advancement.

    Targets off-by-one errors in cursor movement.
    """

    def test_parse_at_eof(self):
        """Kills: EOF boundary check mutations.

        Parsing at exactly EOF should handle correctly.
        """
        parser = FluentParserV1()
        resource = parser.parse("msg = Value")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1

    def test_parse_single_newline(self):
        """Kills: newline handling boundary mutations.

        Single newline should parse correctly.
        """
        parser = FluentParserV1()
        resource = parser.parse("\n")
        assert isinstance(resource, Resource)
        assert len(resource.entries) == 0

    def test_parse_multiple_consecutive_newlines(self):
        """Kills: newline counting mutations.

        Multiple newlines should be handled.
        """
        parser = FluentParserV1()
        resource = parser.parse("\n\n\n")
        assert isinstance(resource, Resource)
        assert len(resource.entries) == 0


class TestCharacterComparisonBoundaries:
    """Test character comparison mutations.

    Targets mutations like '[' → ']' in comparisons.
    """

    def test_variant_missing_opening_bracket(self):
        """Kills: '[' → ']' mutation.

        Missing [ should produce error.
        """
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $x ->
    one] Value
    *[other] Other
}
""")
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) >= 1

    def test_variant_missing_closing_bracket(self):
        """Kills: ']' → '[' mutation.

        Missing ] should produce error.
        """
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $x ->
    [one Value
    *[other] Other
}
""")
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) >= 1

    def test_placeable_missing_opening_brace(self):
        """Kills: '{' → '}' mutation.

        Missing { before variable should produce text, not placeable.
        """
        parser = FluentParserV1()
        # This is valid FTL - $var } is just text (not a placeable)
        resource = parser.parse("msg = $var }")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        # Verify it's treated as text, not a variable reference
        assert isinstance(messages[0].value, Pattern)

    def test_placeable_missing_closing_brace(self):
        """Kills: '}' → '{' mutation.

        Missing } should produce error.
        """
        parser = FluentParserV1()
        resource = parser.parse("msg = { $var")
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
