"""Parser boundary condition tests for variants, patterns, identifiers, and whitespace.

Tests:
- Variant count boundaries: single variant, two variants, empty variant key rejection
- Pattern element boundaries: empty pattern, single element, whitespace-only
- String literal boundaries: empty, single character, unterminated
- Number literal boundaries: zero, negative, single digit, decimal
- Identifier boundaries: single character, hyphenated, invalid start character
- Term reference boundaries: single character name, reference inside pattern
- Attribute boundaries: single character name, zero and one attributes
- Whitespace continuation boundaries: minimum indent, no indent, single space
- Comment boundaries: empty comment, single character comment
- Cursor advancement boundaries: EOF, single newline, multiple newlines
- Character comparison boundaries: missing brackets, missing braces
"""


from ftllexengine.syntax.ast import Junk, Message, Pattern, Resource, SelectExpression, TextElement
from ftllexengine.syntax.parser import FluentParserV1


class TestVariantBoundaryConditions:
    """Variant count boundary conditions in select expression parsing."""

    def test_single_variant_select(self) -> None:
        """Select expression with exactly one (default) variant parses successfully."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $count ->
    *[other] Value
}
""")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert isinstance(messages[0].value, Pattern)

    def test_two_variants_select(self) -> None:
        """Select expression with two variants (one, other) parses successfully."""
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
        pattern = messages[0].value
        assert isinstance(pattern, Pattern)
        assert len(pattern.elements) == 1
        placeable = pattern.elements[0]
        assert isinstance(placeable, Placeable)
        select = placeable.expression
        assert isinstance(select, SelectExpression)
        assert len(select.variants) == 2

    def test_empty_variant_key_rejected(self) -> None:
        """Select expression with [] (empty variant key) produces a parse error."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $count ->
    [] Empty key
    *[other] Other
}
""")
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) >= 1

    def test_single_char_variant_key_allowed(self) -> None:
        """Single character variant keys [a] and [b] are valid."""
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
    """Pattern element boundary conditions in message parsing."""

    def test_empty_pattern_not_allowed_without_attributes(self) -> None:
        """Per FTL spec, message must have a Pattern or at least one Attribute."""
        parser = FluentParserV1()
        resource = parser.parse("msg = ")
        junks = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junks) == 1

    def test_single_element_pattern(self) -> None:
        """Pattern with a single TextElement is valid."""
        parser = FluentParserV1()
        resource = parser.parse("msg = Text")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert messages[0].value is not None
        assert len(messages[0].value.elements) == 1
        assert isinstance(messages[0].value.elements[0], TextElement)

    def test_pattern_with_only_whitespace(self) -> None:
        """Whitespace-only pattern with no attributes is invalid per FTL spec."""
        parser = FluentParserV1()
        resource = parser.parse("msg =    ")
        junks = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junks) == 1


class TestStringLiteralBoundaries:
    """String literal boundary conditions in expression parsing."""

    def test_empty_string_literal(self) -> None:
        """Empty string literal \"\" is a valid expression."""
        parser = FluentParserV1()
        resource = parser.parse('msg = { "" }')
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1

    def test_single_char_string_literal(self) -> None:
        """Single character string literal \"a\" is valid."""
        parser = FluentParserV1()
        resource = parser.parse('msg = { "a" }')
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1

    def test_unterminated_string_literal(self) -> None:
        """Unterminated string literal produces a parse error (Junk)."""
        parser = FluentParserV1()
        resource = parser.parse('msg = { "unterminated')
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) >= 1


class TestNumberLiteralBoundaries:
    """Number literal boundary conditions in expression parsing."""

    def test_zero_number(self) -> None:
        """Zero literal { 0 } is a valid number expression."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { 0 }")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1

    def test_negative_number(self) -> None:
        """Negative number literal { -42 } is valid."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { -42 }")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1

    def test_single_digit_number(self) -> None:
        """Single digit number literal { 7 } is valid."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { 7 }")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1

    def test_decimal_with_zero_fractional(self) -> None:
        """Decimal number { 5.0 } with zero fractional part is valid."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { 5.0 }")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1


class TestIdentifierBoundaries:
    """Identifier boundary conditions in message and term parsing."""

    def test_single_char_identifier(self) -> None:
        """Single character message identifier is valid."""
        parser = FluentParserV1()
        resource = parser.parse("a = Value")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert messages[0].id.name == "a"

    def test_identifier_with_single_hyphen(self) -> None:
        """Hyphenated identifier a-b is valid."""
        parser = FluentParserV1()
        resource = parser.parse("a-b = Value")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert messages[0].id.name == "a-b"

    def test_identifier_starting_with_digit_rejected(self) -> None:
        """Identifier starting with a digit is rejected (Junk)."""
        parser = FluentParserV1()
        resource = parser.parse("1abc = Value")
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) >= 1


class TestTermReferenceBoundaries:
    """Term reference boundary conditions in term and message parsing."""

    def test_single_char_term_name(self) -> None:
        """Single character term name -t is valid."""
        parser = FluentParserV1()
        resource = parser.parse("-t = Term")
        assert isinstance(resource, Resource)
        assert len(resource.entries) >= 1

    def test_term_reference_in_pattern(self) -> None:
        """Term reference { -brand } inside a message pattern parses correctly."""
        parser = FluentParserV1()
        resource = parser.parse("""
-brand = Firefox
msg = { -brand }
""")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1


class TestAttributeBoundaries:
    """Attribute boundary conditions in message parsing."""

    def test_single_char_attribute_name(self) -> None:
        """Single character attribute name .a is valid."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = Value
    .a = Attr
""")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert len(messages[0].attributes) == 1

    def test_message_with_zero_attributes(self) -> None:
        """Message without attributes is valid."""
        parser = FluentParserV1()
        resource = parser.parse("msg = Value")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert len(messages[0].attributes) == 0

    def test_message_with_one_attribute(self) -> None:
        """Message with exactly one attribute is valid."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = Value
    .attr = Attr
""")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert len(messages[0].attributes) == 1


class TestWhitespaceBoundaries:
    """Whitespace and indentation boundary conditions in continuation line parsing."""

    def test_minimum_indent_for_continuation(self) -> None:
        """Four-space indented continuation line is parsed correctly."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg =
    Line
""")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1

    def test_no_indent_breaks_continuation(self) -> None:
        """Unindented line after message breaks the continuation (treated as new entry)."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg =
Line
""")
        assert len(resource.entries) >= 1

    def test_single_space_indent(self) -> None:
        """Single space indented continuation line is valid."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg =
 Continued
""")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1


class TestCommentBoundaries:
    """Comment boundary conditions in FTL comment parsing."""

    def test_empty_comment(self) -> None:
        """Hash-only line (# with no content) is a valid empty comment."""
        parser = FluentParserV1()
        resource = parser.parse("#\nmsg = Value")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1

    def test_single_char_comment(self) -> None:
        """Comment with a single character content is valid."""
        parser = FluentParserV1()
        resource = parser.parse("# x\nmsg = Value")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1


class TestCursorAdvancementBoundaries:
    """Cursor advancement boundary conditions at EOF and with empty input."""

    def test_parse_at_eof(self) -> None:
        """Parsing a message at exactly EOF produces a valid message entry."""
        parser = FluentParserV1()
        resource = parser.parse("msg = Value")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1

    def test_parse_single_newline(self) -> None:
        """Single newline produces an empty resource with no entries."""
        parser = FluentParserV1()
        resource = parser.parse("\n")
        assert isinstance(resource, Resource)
        assert len(resource.entries) == 0

    def test_parse_multiple_consecutive_newlines(self) -> None:
        """Multiple consecutive newlines produce an empty resource."""
        parser = FluentParserV1()
        resource = parser.parse("\n\n\n")
        assert isinstance(resource, Resource)
        assert len(resource.entries) == 0


class TestCharacterComparisonBoundaries:
    """Character comparison boundary conditions for bracket and brace matching."""

    def test_variant_missing_opening_bracket(self) -> None:
        """Missing [ before variant key produces a parse error."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $x ->
    one] Value
    *[other] Other
}
""")
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) >= 1

    def test_variant_missing_closing_bracket(self) -> None:
        """Missing ] after variant key produces a parse error."""
        parser = FluentParserV1()
        resource = parser.parse("""
msg = { $x ->
    [one Value
    *[other] Other
}
""")
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) >= 1

    def test_placeable_missing_opening_brace(self) -> None:
        """$var } without { is treated as literal text, not a variable reference."""
        parser = FluentParserV1()
        resource = parser.parse("msg = $var }")
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert isinstance(messages[0].value, Pattern)

    def test_placeable_missing_closing_brace(self) -> None:
        """{ $var without } produces a parse error."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { $var")
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) >= 1
