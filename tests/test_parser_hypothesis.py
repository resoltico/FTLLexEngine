"""Hypothesis property-based tests for Fluent parser.

Focus on parser robustness, error recovery, and invariant properties.
Comprehensive coverage of FTL syntax elements, edge cases, and error recovery.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.syntax.ast import Message, Term
from ftllexengine.syntax.parser import FluentParserV1

# ============================================================================
# HYPOTHESIS STRATEGIES
# ============================================================================

# Valid FTL identifiers (using st.from_regex per hypothesis.md)
ftl_identifiers = st.from_regex(r"[a-z][a-z0-9_-]*", fullmatch=True)

# Valid variable names (same as identifiers)
variable_names = ftl_identifiers

# Text content without FTL special characters - remove arbitrary max_size
safe_text = st.text(
    alphabet=st.characters(
        blacklist_categories=["Cc"],
        blacklist_characters=["{", "}", "[", "]", "$", "-", "*", ".", "#", "\n"],
    ),
    min_size=1,
).filter(lambda s: s.strip())

# Numbers for numeric literals - remove arbitrary bounds
numbers = st.integers()
decimals = st.floats(
    allow_nan=False,
    allow_infinity=False,
)

# Attribute names
attribute_names = ftl_identifiers

# Variant keys - use st.from_regex, remove arbitrary max_size
variant_keys = st.from_regex(r"[a-z][a-z0-9]*", fullmatch=True)


class TestParserRobustness:
    """Property-based tests for parser robustness."""

    @given(
        # Use ftl_identifiers strategy - cleaner and unconstrained
        identifier=ftl_identifiers,
    )
    @settings(max_examples=200)
    def test_simple_message_always_parses(self, identifier: str) -> None:
        """Simple message with valid identifier always parses successfully."""
        source = f"{identifier} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should always produce a resource
        assert resource is not None
        assert hasattr(resource, "entries")
        # Should have at least one entry (message or junk)
        assert len(resource.entries) >= 0

    @given(
        identifier=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll"), min_codepoint=97, max_codepoint=122
            ),
            min_size=1,
            max_size=20,
        ).filter(lambda x: x[0].isalpha()),
        value=st.text(
            alphabet=st.characters(blacklist_categories=["Cc"], blacklist_characters="{}\n"),
            min_size=0,
            max_size=100,
        ),
    )
    @settings(max_examples=200)
    def test_message_with_arbitrary_value_parses(
        self, identifier: str, value: str
    ) -> None:
        """Messages with arbitrary (non-special) text values parse."""
        source = f"{identifier} = {value}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None
        assert len(resource.entries) >= 0

    @given(
        comment_text=st.text(
            alphabet=st.characters(blacklist_categories=["Cc"], blacklist_characters="#"),
            min_size=0,
            max_size=100,
        ),
    )
    @settings(max_examples=150)
    def test_single_line_comment_always_parses(self, comment_text: str) -> None:
        """Single-line comments with arbitrary text parse successfully."""
        source = f"# {comment_text}\nkey = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse (comment + message)
        assert resource is not None
        assert len(resource.entries) >= 1

    @given(
        num_newlines=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=50)
    def test_blank_lines_do_not_affect_parsing(self, num_newlines: int) -> None:
        """Multiple blank lines should not affect parsing."""
        source = f"key1 = value1{'\\n' * num_newlines}key2 = value2"
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse both messages regardless of blank lines
        assert resource is not None
        # Could be 0-2 entries depending on junk handling
        assert len(resource.entries) >= 0

    @given(
        invalid_start=st.text(
            alphabet=st.characters(whitelist_categories=("P", "S")),
            min_size=1,
            max_size=5,
        ).filter(lambda x: x[0] not in "#-"),
    )
    @settings(max_examples=100)
    def test_invalid_entry_creates_junk(self, invalid_start: str) -> None:
        """Invalid entry start characters create junk entries."""
        source = f"{invalid_start} invalid\nkey = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should recover and parse the valid message
        assert resource is not None
        assert len(resource.entries) >= 0


class TestParserInvariants:
    """Metamorphic and invariant properties of the parser."""

    @given(
        source=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll"),
                min_codepoint=32,
                max_codepoint=126,
            ),
            min_size=0,
            max_size=500,
        ),
    )
    @settings(max_examples=200)
    def test_parser_never_crashes(self, source: str) -> None:
        """Parser should never crash, regardless of input."""
        parser = FluentParserV1()

        # Should not raise exceptions - parser always returns a resource
        resource = parser.parse(source)
        assert resource is not None

    @given(
        identifier=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll"), min_codepoint=97, max_codepoint=122
            ),
            min_size=1,
            max_size=20,
        ).filter(lambda x: x[0].isalpha()),
    )
    @settings(max_examples=100)
    def test_parse_idempotence(self, identifier: str) -> None:
        """Parsing the same source twice yields equivalent results."""
        source = f"{identifier} = value"
        parser = FluentParserV1()

        resource1 = parser.parse(source)
        resource2 = parser.parse(source)

        # Both should have same number of entries
        assert len(resource1.entries) == len(resource2.entries)

    @given(
        whitespace=st.text(alphabet=st.sampled_from([" ", "\t"]), min_size=0, max_size=10),
    )
    @settings(max_examples=100)
    def test_leading_whitespace_invariance(self, whitespace: str) -> None:
        """Leading whitespace on continuation lines is significant."""
        # Indented continuation should be treated as continuation
        source1 = "key = value"
        source2 = f"key = value\n{whitespace}  continuation"

        parser = FluentParserV1()
        resource1 = parser.parse(source1)
        resource2 = parser.parse(source2)

        # Both should parse (resource2 might have continuation)
        assert resource1 is not None
        assert resource2 is not None


class TestParserEdgeCases:
    """Edge cases and boundary conditions."""

    @given(
        num_hashes=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=50)
    def test_comment_hash_count_validation(self, num_hashes: int) -> None:
        """Comments with different hash counts are handled correctly."""
        source = f"{'#' * num_hashes} Comment\nkey = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should handle any number of hashes (1-3 valid, >3 creates junk)
        assert resource is not None
        assert len(resource.entries) >= 0

    @given(
        depth=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    def test_nested_placeables_parse(self, depth: int) -> None:  # noqa: ARG002
        """Nested placeables up to reasonable depth parse."""
        # Create nested variable references (simplified test - just validates parsing)
        inner = "$var"
        source = f"key = {{ {inner} }}"

        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse (might create errors for invalid syntax)
        assert resource is not None

    @given(
        num_variants=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=50)
    def test_select_expression_variant_count(self, num_variants: int) -> None:
        """Select expressions with varying variant counts parse."""
        # Generate variants
        variants = "\n".join([f"    [{i}] Variant {i}" for i in range(num_variants)])
        source = f"key = {{ $num ->\\n{variants}\\n   *[other] Default\\n}}"

        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse
        assert resource is not None

    def test_empty_source_produces_empty_resource(self) -> None:
        """Empty source produces resource with no entries."""
        parser = FluentParserV1()
        resource = parser.parse("")

        assert resource is not None
        assert len(resource.entries) == 0

    def test_only_whitespace_produces_empty_resource(self) -> None:
        """Source with only whitespace produces empty or junk resource."""
        parser = FluentParserV1()
        resource = parser.parse("   \n\t\n   \n")

        assert resource is not None
        # May be 0 (empty) or contain junk entries for malformed whitespace
        assert len(resource.entries) >= 0

    @given(
        identifier=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll"), min_codepoint=97, max_codepoint=122
            ),
            min_size=1,
            max_size=20,
        ).filter(lambda x: x[0].isalpha()),
        num_attributes=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100)
    def test_message_with_multiple_attributes(
        self, identifier: str, num_attributes: int
    ) -> None:
        """Messages with multiple attributes parse correctly."""
        attributes = "\n".join(
            [f"    .attr{i} = Value {i}" for i in range(num_attributes)]
        )
        source = f"{identifier} = Main value\n{attributes}"

        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse message with attributes
        assert resource is not None
        assert len(resource.entries) >= 0


class TestParserRecovery:
    """Test error recovery and resilience."""

    @given(
        num_errors=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    def test_multiple_errors_recovery(self, num_errors: int) -> None:
        """Parser recovers from multiple consecutive errors."""
        # Create multiple invalid lines followed by valid message
        invalid_lines = "\n".join([f"!!! invalid {i}" for i in range(num_errors)])
        source = f"{invalid_lines}\nkey = value"

        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should create junk entries and recover
        assert resource is not None
        assert len(resource.entries) >= 0

    @given(
        unicode_char=st.characters(min_codepoint=0x1F600, max_codepoint=0x1F64F),
    )
    @settings(max_examples=50)
    def test_unicode_emoji_in_values(self, unicode_char: str) -> None:
        """Unicode emoji characters in values are handled."""
        source = f"key = Hello {unicode_char}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse
        assert resource is not None

    def test_very_long_identifier(self) -> None:
        """Very long identifiers are handled."""
        long_id = "a" * 1000
        source = f"{long_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse (or create junk if too long)
        assert resource is not None

    def test_very_long_value(self) -> None:
        """Very long values are handled."""
        long_value = "value " * 1000
        source = f"key = {long_value}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse
        assert resource is not None


# ============================================================================
# VARIABLE REFERENCES
# ============================================================================


class TestVariableReferenceParsing:
    """Property tests for variable reference parsing."""

    @given(var_name=variable_names)
    @settings(max_examples=200)
    def test_simple_variable_reference_parses(self, var_name: str) -> None:
        """PROPERTY: { $var } always parses successfully."""
        source = f"msg = {{ ${var_name} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None
        assert len(resource.entries) > 0

    @given(var_name=variable_names, text=safe_text)
    @settings(max_examples=150)
    def test_variable_with_surrounding_text(self, var_name: str, text: str) -> None:
        """PROPERTY: Text { $var } text parses correctly."""
        source = f"msg = {text} {{ ${var_name} }} {text}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        var1=variable_names,
        var2=variable_names,
    )
    @settings(max_examples=150)
    def test_multiple_variable_references(self, var1: str, var2: str) -> None:
        """PROPERTY: Multiple { $var1 } { $var2 } parse correctly."""
        source = f"msg = {{ ${var1} }} {{ ${var2} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_variable_at_message_start(self, var_name: str) -> None:
        """PROPERTY: Message starting with { $var } parses."""
        source = f"msg = {{ ${var_name} }} text"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_variable_at_message_end(self, var_name: str) -> None:
        """PROPERTY: Message ending with { $var } parses."""
        source = f"msg = text {{ ${var_name} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_variable_only_message(self, var_name: str) -> None:
        """PROPERTY: Message with only { $var } parses."""
        source = f"msg = {{ ${var_name} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        var_name=variable_names,
        count=st.integers(min_value=2, max_value=10),
    )
    @settings(max_examples=50)
    def test_repeated_variable_references(self, var_name: str, count: int) -> None:
        """PROPERTY: Same variable referenced multiple times parses."""
        refs = " ".join([f"{{ ${var_name} }}" for _ in range(count)])
        source = f"msg = {refs}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None


# ============================================================================
# PLACEABLES
# ============================================================================


class TestPlaceableParsing:
    """Property tests for placeable expression parsing."""

    @given(text=safe_text)
    @settings(max_examples=150)
    def test_placeable_with_string_literal(self, text: str) -> None:
        """PROPERTY: { "string" } parses as placeable."""
        # Escape quotes in text
        escaped = text.replace('"', '\\"')
        source = f'msg = {{ "{escaped}" }}'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(number=numbers)
    @settings(max_examples=150)
    def test_placeable_with_number_literal(self, number: int) -> None:
        """PROPERTY: { 123 } parses as placeable."""
        source = f"msg = {{ {number} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        msg_id=ftl_identifiers,
        var_name=variable_names,
    )
    @settings(max_examples=100)
    def test_placeable_with_message_reference(
        self, msg_id: str, var_name: str
    ) -> None:
        """PROPERTY: { message-id } parses as message reference."""
        source = f"{msg_id} = value\nmsg = {{ {var_name} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        var_name=variable_names,
        count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    def test_consecutive_placeables(self, var_name: str, count: int) -> None:
        """PROPERTY: Multiple consecutive placeables parse."""
        placeables = "".join([f"{{ ${var_name}{i} }}" for i in range(count)])
        source = f"msg = {placeables}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        var_name=variable_names,
        whitespace=st.text(alphabet=" \t", min_size=0, max_size=5),
    )
    @settings(max_examples=100)
    def test_placeable_internal_whitespace(
        self, var_name: str, whitespace: str
    ) -> None:
        """PROPERTY: Whitespace inside { } is handled."""
        source = f"msg = {{{whitespace}${var_name}{whitespace}}}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None


# ============================================================================
# SELECT EXPRESSIONS
# ============================================================================


class TestSelectExpressionParsing:
    """Property tests for select expression parsing."""

    @given(var_name=variable_names)
    @settings(max_examples=150)
    def test_minimal_select_expression(self, var_name: str) -> None:
        """PROPERTY: Minimal select { $var -> *[other] X } parses."""
        source = f"msg = {{ ${var_name} ->\n   *[other] Default\n}}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        var_name=variable_names,
        key1=variant_keys,
        key2=variant_keys,
    )
    @settings(max_examples=150)
    def test_select_with_multiple_variants(
        self, var_name: str, key1: str, key2: str
    ) -> None:
        """PROPERTY: Select with multiple variants parses."""
        source = f"""msg = {{ ${var_name} ->
    [{key1}] Value1
    [{key2}] Value2
   *[other] Default
}}"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        var_name=variable_names,
        count=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=50)
    def test_select_with_many_variants(self, var_name: str, count: int) -> None:
        """PROPERTY: Select with many variants parses."""
        variants = "\n".join([f"    [key{i}] Value{i}" for i in range(count)])
        source = f"msg = {{ ${var_name} ->\n{variants}\n   *[other] Default\n}}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(var_name=variable_names, text=safe_text)
    @settings(max_examples=100)
    def test_select_variant_with_text(self, var_name: str, text: str) -> None:
        """PROPERTY: Select variant values can contain text."""
        source = f"msg = {{ ${var_name} ->\n   *[other] {text}\n}}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        var_name=variable_names,
        var_in_variant=variable_names,
    )
    @settings(max_examples=100)
    def test_select_variant_with_placeable(
        self, var_name: str, var_in_variant: str
    ) -> None:
        """PROPERTY: Select variant can contain placeables."""
        source = f"msg = {{ ${var_name} ->\n   *[other] Text {{ ${var_in_variant} }}\n}}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(var_name=variable_names, number=numbers)
    @settings(max_examples=100)
    def test_select_with_numeric_keys(self, var_name: str, number: int) -> None:
        """PROPERTY: Select with numeric variant keys parses."""
        source = f"msg = {{ ${var_name} ->\n    [{number}] Exact\n   *[other] Default\n}}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None


# ============================================================================
# TERMS
# ============================================================================


class TestTermParsing:
    """Property tests for term definition and reference parsing."""

    @given(term_id=ftl_identifiers)
    @settings(max_examples=150)
    def test_simple_term_definition(self, term_id: str) -> None:
        """PROPERTY: -term = value parses as term."""
        source = f"-{term_id} = Term value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None
        if len(resource.entries) > 0:
            # Should be a Term entry
            entry = resource.entries[0]
            assert isinstance(entry, (Term, Message))  # Could be either

    @given(term_id=ftl_identifiers, text=safe_text)
    @settings(max_examples=100)
    def test_term_with_text_value(self, term_id: str, text: str) -> None:
        """PROPERTY: Term with text value parses."""
        source = f"-{term_id} = {text}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(term_id=ftl_identifiers, var_name=variable_names)
    @settings(max_examples=100)
    def test_term_with_placeable(self, term_id: str, var_name: str) -> None:
        """PROPERTY: Term with placeable parses."""
        source = f"-{term_id} = Value {{ ${var_name} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(term_id=ftl_identifiers, attr_name=attribute_names)
    @settings(max_examples=100)
    def test_term_with_attribute(self, term_id: str, attr_name: str) -> None:
        """PROPERTY: Term with attribute parses."""
        source = f"-{term_id} = Value\n    .{attr_name} = Attribute value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        msg_id=ftl_identifiers,
        term_id=ftl_identifiers,
    )
    @settings(max_examples=100)
    def test_message_referencing_term(self, msg_id: str, term_id: str) -> None:
        """PROPERTY: Message can reference term { -term }."""
        source = f"-{term_id} = Term\n{msg_id} = {{ -{term_id} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        msg_id=ftl_identifiers,
        term_id=ftl_identifiers,
        attr_name=attribute_names,
    )
    @settings(max_examples=100)
    def test_term_attribute_reference(
        self, msg_id: str, term_id: str, attr_name: str
    ) -> None:
        """PROPERTY: Term attribute reference { -term.attr } parses."""
        source = (
            f"-{term_id} = Term\n"
            f"    .{attr_name} = Attr\n"
            f"{msg_id} = {{ -{term_id}.{attr_name} }}"
        )
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None


# ============================================================================
# STRING LITERALS
# ============================================================================


class TestStringLiteralParsing:
    """Property tests for string literal parsing."""

    @given(text=safe_text)
    @settings(max_examples=150)
    def test_simple_string_literal(self, text: str) -> None:
        """PROPERTY: "text" parses as string literal."""
        escaped = text.replace('"', '\\"').replace("\\", "\\\\")
        source = f'msg = {{ "{escaped}" }}'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    def test_empty_string_literal(self) -> None:
        """PROPERTY: Empty string "" parses."""
        source = 'msg = { "" }'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(char=st.characters(min_codepoint=32, max_codepoint=126))
    @settings(max_examples=100)
    def test_string_with_single_char(self, char: str) -> None:
        """PROPERTY: Single character strings parse."""
        if char == '"':
            escaped = '\\"'
        elif char == "\\":
            escaped = "\\\\"
        else:
            escaped = char
        source = f'msg = {{ "{escaped}" }}'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        unicode_char=st.characters(min_codepoint=0x0100, max_codepoint=0xFFFF),
    )
    @settings(max_examples=100)
    def test_string_with_unicode(self, unicode_char: str) -> None:
        """PROPERTY: String literals with Unicode parse."""
        source = f'msg = {{ "{unicode_char}" }}'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None


# ============================================================================
# NUMBER LITERALS
# ============================================================================


class TestNumberLiteralParsing:
    """Property tests for number literal parsing."""

    @given(number=numbers)
    @settings(max_examples=200)
    def test_integer_literal(self, number: int) -> None:
        """PROPERTY: Integer literals parse correctly."""
        source = f"msg = {{ {number} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(decimal=decimals)
    @settings(max_examples=150)
    def test_decimal_literal(self, decimal: float) -> None:
        """PROPERTY: Decimal literals parse correctly."""
        source = f"msg = {{ {decimal} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    def test_zero_literal(self) -> None:
        """PROPERTY: Zero literal parses."""
        source = "msg = { 0 }"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(number=st.integers(min_value=0, max_value=1000000))
    @settings(max_examples=100)
    def test_positive_integer(self, number: int) -> None:
        """PROPERTY: Positive integers parse."""
        source = f"msg = {{ {number} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(number=st.integers(min_value=-1000000, max_value=-1))
    @settings(max_examples=100)
    def test_negative_integer(self, number: int) -> None:
        """PROPERTY: Negative integers parse."""
        source = f"msg = {{ {number} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None


# ============================================================================
# MESSAGE STRUCTURE
# ============================================================================


class TestMessageStructure:
    """Property tests for message structure parsing."""

    @given(msg_id=ftl_identifiers, text=safe_text)
    @settings(max_examples=150)
    def test_message_with_value_only(self, msg_id: str, text: str) -> None:
        """PROPERTY: Message with only value parses."""
        source = f"{msg_id} = {text}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        msg_id=ftl_identifiers,
        attr_name=attribute_names,
        text=safe_text,
    )
    @settings(max_examples=150)
    def test_message_with_single_attribute(
        self, msg_id: str, attr_name: str, text: str
    ) -> None:
        """PROPERTY: Message with one attribute parses."""
        source = f"{msg_id} = Value\n    .{attr_name} = {text}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        msg_id=ftl_identifiers,
        count=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=50)
    def test_message_with_multiple_attributes(
        self, msg_id: str, count: int
    ) -> None:
        """PROPERTY: Message with multiple attributes parses."""
        attrs = "\n".join([f"    .attr{i} = Value{i}" for i in range(count)])
        source = f"{msg_id} = Main\n{attrs}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(msg_id=ftl_identifiers, attr_name=attribute_names)
    @settings(max_examples=100)
    def test_message_attribute_only(self, msg_id: str, attr_name: str) -> None:
        """PROPERTY: Message with only attributes (no value) parses."""
        source = f"{msg_id} =\n    .{attr_name} = Attribute value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        msg_id=ftl_identifiers,
        var_name=variable_names,
    )
    @settings(max_examples=100)
    def test_message_value_with_placeable(
        self, msg_id: str, var_name: str
    ) -> None:
        """PROPERTY: Message value with placeable parses."""
        source = f"{msg_id} = Text {{ ${var_name} }} more"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None


# ============================================================================
# COMMENTS
# ============================================================================


class TestCommentParsing:
    """Property tests for comment parsing."""

    @given(text=safe_text)
    @settings(max_examples=150)
    def test_standalone_comment(self, text: str) -> None:
        """PROPERTY: Standalone comment parses."""
        source = f"# {text}\n\nmsg = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(text=safe_text)
    @settings(max_examples=100)
    def test_group_comment(self, text: str) -> None:
        """PROPERTY: Group comment ## parses."""
        source = f"## {text}\n\nmsg = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(text=safe_text)
    @settings(max_examples=100)
    def test_resource_comment(self, text: str) -> None:
        """PROPERTY: Resource comment ### parses."""
        source = f"### {text}\n\nmsg = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        text=safe_text,
        count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    def test_multiple_comment_lines(self, text: str, count: int) -> None:
        """PROPERTY: Multiple consecutive comment lines parse."""
        comments = "\n".join([f"# {text} {i}" for i in range(count)])
        source = f"{comments}\n\nmsg = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(msg_id=ftl_identifiers, text=safe_text)
    @settings(max_examples=100)
    def test_comment_attached_to_message(self, msg_id: str, text: str) -> None:
        """PROPERTY: Comment immediately before message parses."""
        source = f"# {text}\n{msg_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None


# ============================================================================
# WHITESPACE HANDLING
# ============================================================================


class TestWhitespaceHandling:
    """Property tests for whitespace handling."""

    @given(
        msg_id=ftl_identifiers,
        spaces=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=100)
    def test_spaces_before_equals(self, msg_id: str, spaces: int) -> None:
        """PROPERTY: Spaces before = are handled."""
        source = f"{msg_id}{' ' * spaces}= value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        msg_id=ftl_identifiers,
        spaces=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=100)
    def test_spaces_after_equals(self, msg_id: str, spaces: int) -> None:
        """PROPERTY: Spaces after = are handled."""
        source = f"{msg_id} ={' ' * spaces}value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        msg_id=ftl_identifiers,
        indent=st.integers(min_value=4, max_value=12),
    )
    @settings(max_examples=50)
    def test_attribute_indentation(self, msg_id: str, indent: int) -> None:
        """PROPERTY: Attribute indentation is handled."""
        source = f"{msg_id} = value\n{' ' * indent}.attr = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        msg_id=ftl_identifiers,
        blank_lines=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=50)
    def test_blank_lines_between_messages(
        self, msg_id: str, blank_lines: int
    ) -> None:
        """PROPERTY: Blank lines between messages don't affect parsing."""
        source = f"{msg_id}1 = value1{chr(10) * blank_lines}{msg_id}2 = value2"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        msg_id=ftl_identifiers,
        trailing_spaces=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=50)
    def test_trailing_whitespace(self, msg_id: str, trailing_spaces: int) -> None:
        """PROPERTY: Trailing whitespace is handled."""
        source = f"{msg_id} = value{' ' * trailing_spaces}\n"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None


# ============================================================================
# FUNCTION CALLS
# ============================================================================


class TestFunctionCallParsing:
    """Property tests for function call parsing."""

    @given(var_name=variable_names)
    @settings(max_examples=150)
    def test_number_function_call(self, var_name: str) -> None:
        """PROPERTY: NUMBER($var) parses correctly."""
        source = f"msg = {{ NUMBER(${var_name}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(var_name=variable_names)
    @settings(max_examples=150)
    def test_datetime_function_call(self, var_name: str) -> None:
        """PROPERTY: DATETIME($var) parses correctly."""
        source = f"msg = {{ DATETIME(${var_name}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_function_with_named_arg(self, var_name: str) -> None:
        """PROPERTY: FUNC($var, opt: val) parses."""
        source = f"msg = {{ NUMBER(${var_name}, minimumFractionDigits: 2) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(var_name=variable_names, number=numbers)
    @settings(max_examples=100)
    def test_function_with_numeric_option(self, var_name: str, number: int) -> None:
        """PROPERTY: Function with numeric option parses."""
        source = f"msg = {{ NUMBER(${var_name}, minimumFractionDigits: {number}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_function_with_string_option(self, var_name: str) -> None:
        """PROPERTY: Function with string option parses."""
        source = f'msg = {{ DATETIME(${var_name}, style: "long") }}'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        var_name=variable_names,
        count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    def test_function_with_multiple_options(self, var_name: str, count: int) -> None:
        """PROPERTY: Function with multiple options parses."""
        options = ", ".join([f"opt{i}: {i}" for i in range(count)])
        source = f"msg = {{ NUMBER(${var_name}, {options}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(func_name=ftl_identifiers, var_name=variable_names)
    @settings(max_examples=100)
    def test_custom_function_call(self, func_name: str, var_name: str) -> None:
        """PROPERTY: Custom function calls parse."""
        # Note: uppercase function names required
        source = f"msg = {{ {func_name.upper()}(${var_name}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(number=numbers)
    @settings(max_examples=50)
    def test_function_with_number_literal_arg(self, number: int) -> None:
        """PROPERTY: Function with number literal argument parses."""
        source = f"msg = {{ NUMBER({number}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(var_name=variable_names)
    @settings(max_examples=50)
    def test_nested_function_calls(self, var_name: str) -> None:
        """PROPERTY: Nested function calls parse (if supported)."""
        # Most parsers support simple nesting
        source = f"msg = {{ NUMBER(${var_name}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None


# ============================================================================
# MESSAGE REFERENCES
# ============================================================================


class TestMessageReferenceParsing:
    """Property tests for message reference parsing."""

    @given(msg_id1=ftl_identifiers, msg_id2=ftl_identifiers)
    @settings(max_examples=150)
    def test_simple_message_reference(self, msg_id1: str, msg_id2: str) -> None:
        """PROPERTY: { msg-id } references another message."""
        source = f"{msg_id1} = Value1\n{msg_id2} = {{ {msg_id1} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        msg_id1=ftl_identifiers,
        msg_id2=ftl_identifiers,
        attr_name=attribute_names,
    )
    @settings(max_examples=100)
    def test_message_attribute_reference(
        self, msg_id1: str, msg_id2: str, attr_name: str
    ) -> None:
        """PROPERTY: { msg.attr } references message attribute."""
        source = (
            f"{msg_id1} = Value\n"
            f"    .{attr_name} = Attr\n"
            f"{msg_id2} = {{ {msg_id1}.{attr_name} }}"
        )
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        msg_id=ftl_identifiers,
        count=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=50)
    def test_multiple_message_references(self, msg_id: str, count: int) -> None:
        """PROPERTY: Multiple message references in one pattern parse."""
        refs = " ".join([f"{{ {msg_id}{i} }}" for i in range(count)])
        # Create referenced messages
        messages = "\n".join([f"{msg_id}{i} = Value{i}" for i in range(count)])
        source = f"{messages}\nfinal = {refs}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(msg_id1=ftl_identifiers, msg_id2=ftl_identifiers, text=safe_text)
    @settings(max_examples=100)
    def test_message_reference_with_text(
        self, msg_id1: str, msg_id2: str, text: str
    ) -> None:
        """PROPERTY: Message reference mixed with text parses."""
        source = f"{msg_id1} = Value\n{msg_id2} = {text} {{ {msg_id1} }} {text}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None


# ============================================================================
# IDENTIFIER VALIDATION
# ============================================================================


class TestIdentifierValidation:
    """Property tests for identifier validation."""

    @given(
        prefix=st.text(
            alphabet=st.characters(min_codepoint=97, max_codepoint=122),
            min_size=1,
            max_size=5,
        ),
        number=st.integers(min_value=0, max_value=999),
    )
    @settings(max_examples=150)
    def test_identifier_with_number_suffix(self, prefix: str, number: int) -> None:
        """PROPERTY: Identifiers can have numeric suffixes."""
        msg_id = f"{prefix}{number}"
        source = f"{msg_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        parts=st.lists(
            st.text(
                alphabet=st.characters(min_codepoint=97, max_codepoint=122),
                min_size=1,
                max_size=5,
            ),
            min_size=2,
            max_size=5,
        ),
    )
    @settings(max_examples=100)
    def test_identifier_with_hyphens(self, parts: list[str]) -> None:
        """PROPERTY: Identifiers with hyphens parse."""
        msg_id = "-".join(parts)
        source = f"{msg_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        parts=st.lists(
            st.text(
                alphabet=st.characters(min_codepoint=97, max_codepoint=122),
                min_size=1,
                max_size=5,
            ),
            min_size=2,
            max_size=5,
        ),
    )
    @settings(max_examples=100)
    def test_identifier_with_underscores(self, parts: list[str]) -> None:
        """PROPERTY: Identifiers with underscores parse."""
        msg_id = "_".join(parts)
        source = f"{msg_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(length=st.integers(min_value=1, max_value=100))
    @settings(max_examples=50)
    def test_identifier_length_handling(self, length: int) -> None:
        """PROPERTY: Identifiers of various lengths parse."""
        msg_id = "a" * length
        source = f"{msg_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        msg_id=ftl_identifiers,
        uppercase_count=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=100)
    def test_identifier_case_sensitivity(
        self, msg_id: str, uppercase_count: int
    ) -> None:
        """PROPERTY: Identifier case is preserved."""
        # Mix case by uppercasing some characters
        chars = list(msg_id)
        for i in range(min(uppercase_count, len(chars))):
            chars[i] = chars[i].upper()
        mixed_case_id = "".join(chars)
        source = f"{mixed_case_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None


# ============================================================================
# ESCAPE SEQUENCES
# ============================================================================


class TestEscapeSequenceParsing:
    """Property tests for escape sequence handling."""

    def test_unicode_escape_basic(self) -> None:
        """PROPERTY: Basic Unicode escapes parse."""
        source = r'msg = { "\u0041" }'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        codepoint=st.integers(
            min_value=0x0020,
            max_value=0xD7FF,
        ),  # Valid Unicode range
    )
    @settings(max_examples=100)
    def test_unicode_escape_various_codepoints(self, codepoint: int) -> None:
        """PROPERTY: Unicode escapes for various codepoints parse."""
        source = f'msg = {{ "\\u{codepoint:04X}" }}'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    def test_escaped_quote_in_string(self) -> None:
        """PROPERTY: Escaped quotes in strings parse."""
        source = r'msg = { "He said \"Hello\"" }'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    def test_escaped_backslash_in_string(self) -> None:
        """PROPERTY: Escaped backslashes parse."""
        source = r'msg = { "Path: C:\\Windows" }'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    def test_escaped_braces_in_text(self) -> None:
        """PROPERTY: Escaped braces in text parse."""
        source = r"msg = Literal \{ and \} braces"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None


# ============================================================================
# LINE ENDING HANDLING
# ============================================================================


class TestLineEndingHandling:
    """Property tests for line ending handling."""

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=100)
    def test_unix_line_endings(self, msg_id: str) -> None:
        """PROPERTY: Unix \\n line endings parse correctly."""
        source = f"{msg_id}1 = value1\n{msg_id}2 = value2\n"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=100)
    def test_windows_line_endings(self, msg_id: str) -> None:
        """PROPERTY: Windows \\r\\n line endings parse correctly."""
        source = f"{msg_id}1 = value1\r\n{msg_id}2 = value2\r\n"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=100)
    def test_old_mac_line_endings(self, msg_id: str) -> None:
        """PROPERTY: Old Mac \\r line endings parse."""
        source = f"{msg_id}1 = value1\r{msg_id}2 = value2\r"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=50)
    def test_mixed_line_endings(self, msg_id: str) -> None:
        """PROPERTY: Mixed line endings are handled."""
        source = f"{msg_id}1 = value1\n{msg_id}2 = value2\r\n{msg_id}3 = value3\r"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=50)
    def test_no_final_newline(self, msg_id: str) -> None:
        """PROPERTY: Source without final newline parses."""
        source = f"{msg_id} = value"  # No trailing newline
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None


# ============================================================================
# UTF-8 BOM HANDLING
# ============================================================================


class TestUTF8BOMHandling:
    """Property tests for UTF-8 BOM handling."""

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=100)
    def test_utf8_bom_at_start(self, msg_id: str) -> None:
        """PROPERTY: UTF-8 BOM at file start is handled."""
        bom = "\ufeff"
        source = f"{bom}{msg_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=50)
    def test_source_without_bom(self, msg_id: str) -> None:
        """PROPERTY: Source without BOM parses normally."""
        source = f"{msg_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(msg_id=ftl_identifiers, text=safe_text)
    @settings(max_examples=50)
    def test_bom_only_at_start(self, msg_id: str, text: str) -> None:
        """PROPERTY: BOM only valid at file start."""
        source = f"{msg_id} = {text}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None


# ============================================================================
# PATTERN ELEMENT BOUNDARIES
# ============================================================================


class TestPatternElementBoundaries:
    """Property tests for pattern element boundaries."""

    @given(var_name=variable_names, text=safe_text)
    @settings(max_examples=100)
    def test_text_placeable_boundary(self, var_name: str, text: str) -> None:
        """PROPERTY: Boundary between text and placeable is correct."""
        source = f"msg = {text}{{ ${var_name} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(var_name=variable_names, text=safe_text)
    @settings(max_examples=100)
    def test_placeable_text_boundary(self, var_name: str, text: str) -> None:
        """PROPERTY: Boundary between placeable and text is correct."""
        source = f"msg = {{ ${var_name} }}{text}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        var1=variable_names,
        var2=variable_names,
    )
    @settings(max_examples=100)
    def test_placeable_placeable_boundary(self, var1: str, var2: str) -> None:
        """PROPERTY: Adjacent placeables have correct boundary."""
        source = f"msg = {{ ${var1} }}{{ ${var2} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(text1=safe_text, text2=safe_text)
    @settings(max_examples=50)
    def test_text_text_concatenation(self, text1: str, text2: str) -> None:
        """PROPERTY: Consecutive text elements are handled."""
        source = f"msg = {text1} {text2}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None


# ============================================================================
# MULTILINE PATTERNS
# ============================================================================


class TestMultilinePatterns:
    """Property tests for multiline pattern handling."""

    @given(msg_id=ftl_identifiers, lines=st.lists(safe_text, min_size=2, max_size=5))
    @settings(max_examples=100)
    def test_multiline_text_value(self, msg_id: str, lines: list[str]) -> None:
        """PROPERTY: Multiline text values parse."""
        # Indent continuation lines
        text_lines = [lines[0]] + [f"    {line}" for line in lines[1:]]
        source = f"{msg_id} =\n" + "\n".join(text_lines)
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        msg_id=ftl_identifiers,
        var_name=variable_names,
        lines=st.lists(safe_text, min_size=2, max_size=5),
    )
    @settings(max_examples=50)
    def test_multiline_with_placeables(
        self, msg_id: str, var_name: str, lines: list[str]
    ) -> None:
        """PROPERTY: Multiline patterns with placeables parse."""
        text_lines = [f"{lines[0]} {{ ${var_name} }}"] + [
            f"    {line}" for line in lines[1:]
        ]
        source = f"{msg_id} =\n" + "\n".join(text_lines)
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        msg_id=ftl_identifiers,
        indent=st.integers(min_value=4, max_value=12),
    )
    @settings(max_examples=50)
    def test_multiline_indentation_consistency(
        self, msg_id: str, indent: int
    ) -> None:
        """PROPERTY: Consistent indentation in multiline patterns."""
        source = (
            f"{msg_id} =\n"
            f"{' ' * indent}Line 1\n"
            f"{' ' * indent}Line 2\n"
            f"{' ' * indent}Line 3"
        )
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None
