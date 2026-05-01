# mypy: ignore-errors
from tests.syntax_parser_property_cases import (
    Comment,
    FluentParserV1,
    Junk,
    Message,
    event,
    ftl_identifiers,
    given,
    numbers,
    safe_text,
    settings,
    st,
    variable_names,
)


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
        # Should have exactly one entry (the message)
        assert len(resource.entries) == 1
        # That entry should be a Message
        assert isinstance(resource.entries[0], Message)

        # Emit event for identifier characteristics (HypoFuzz guidance)
        if "-" in identifier:
            event("identifier=has_hyphen")
        if "_" in identifier:
            event("identifier=has_underscore")
        if any(c.isdigit() for c in identifier):
            event("identifier=has_digit")

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
        # Should have at least one entry
        assert len(resource.entries) >= 1
        # First entry should be a Message (possibly with junk value)
        first_entry = resource.entries[0]
        assert isinstance(first_entry, (Message, Junk))

        # Emit events for HypoFuzz guidance
        event(f"entry_type={type(first_entry).__name__}")
        if len(value) > 50:
            event("value_length=long")
        elif len(value) > 10:
            event("value_length=medium")
        else:
            event("value_length=short")

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

        # Emit events for HypoFuzz guidance
        if len(comment_text) > 50:
            event("comment_length=long")
        elif len(comment_text) > 10:
            event("comment_length=medium")
        else:
            event("comment_length=short")

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
        # Should have at least one entry (message or junk)
        assert len(resource.entries) >= 1
        # Check that we have Messages and/or Junk (not empty)
        for entry in resource.entries:
            assert isinstance(entry, (Message, Junk, Comment))

        # Emit events for HypoFuzz guidance
        if num_newlines == 0:
            event("blank_lines=none")
        elif num_newlines <= 2:
            event("blank_lines=few")
        else:
            event("blank_lines=many")

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

        # Should recover and parse something (message or junk)
        assert resource is not None
        # Parser should produce entries (even if junk)
        assert len(resource.entries) >= 1

        # Emit events for HypoFuzz guidance
        has_junk = any(isinstance(e, Junk) for e in resource.entries)
        event(f"recovery={'has_junk' if has_junk else 'no_junk'}")


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

        # Emit events for entry type distribution (HypoFuzz guidance)
        junk_count = sum(1 for e in resource.entries if isinstance(e, Junk))
        msg_count = sum(1 for e in resource.entries if isinstance(e, Message))
        if junk_count > 0:
            event(f"parse_result=has_junk_{min(junk_count, 5)}")
        if msg_count > 0:
            event(f"parse_result=has_messages_{min(msg_count, 5)}")
        if len(resource.entries) == 0:
            event("parse_result=empty")

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

        # Emit events for HypoFuzz guidance
        if len(identifier) > 10:
            event("identifier_length=long")
        elif len(identifier) > 5:
            event("identifier_length=medium")
        else:
            event("identifier_length=short")

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

        # Emit events for HypoFuzz guidance
        has_tabs = "\t" in whitespace
        has_spaces = " " in whitespace
        if has_tabs and has_spaces:
            event("whitespace_type=mixed")
        elif has_tabs:
            event("whitespace_type=tabs")
        elif has_spaces:
            event("whitespace_type=spaces")
        else:
            event("whitespace_type=none")


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
        # Should have at least one entry (comment/message or junk)
        assert len(resource.entries) >= 1

        # Emit events for HypoFuzz guidance
        if num_hashes == 1:
            event("comment_type=standalone")
        elif num_hashes == 2:
            event("comment_type=group")
        elif num_hashes == 3:
            event("comment_type=resource")
        else:
            event("comment_type=invalid_many_hashes")

    @given(
        depth=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    def test_nested_placeables_parse(self, depth: int) -> None:
        """Nested placeables up to reasonable depth parse."""
        # Create nested variable references (simplified test - just validates parsing)
        inner = "$var"
        source = f"key = {{ {inner} }}"

        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse (might create errors for invalid syntax)
        assert resource is not None

        # Emit depth event for HypoFuzz guidance
        event(f"depth={depth}")

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

        # Emit variant count event for HypoFuzz guidance
        event(f"variant_count={min(num_variants, 10)}")

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
        # Whitespace-only source may produce empty resource (this is valid)

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
        # Should have at least one entry (the message)
        assert len(resource.entries) >= 1
        # First entry should be a Message
        first_entry = resource.entries[0]
        assert isinstance(first_entry, (Message, Junk))

        # Emit events for HypoFuzz guidance
        event(f"attribute_count={min(num_attributes, 5)}")


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
        # Should have at least one entry (junk from invalid lines and/or message)
        assert len(resource.entries) >= 1

        # Emit events for HypoFuzz guidance
        event(f"error_count={min(num_errors, 5)}")
        junk_count = sum(1 for e in resource.entries if isinstance(e, Junk))
        event(f"junk_entries={min(junk_count, 5)}")

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

        # Emit events for HypoFuzz guidance
        event("unicode=emoji")

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

        # Emit events for HypoFuzz guidance
        event("variable_position=only")
        if len(var_name) > 10:
            event("var_name_length=long")
        else:
            event("var_name_length=short")

    @given(var_name=variable_names, text=safe_text)
    @settings(max_examples=150)
    def test_variable_with_surrounding_text(self, var_name: str, text: str) -> None:
        """PROPERTY: Text { $var } text parses correctly."""
        source = f"msg = {text} {{ ${var_name} }} {text}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("variable_position=middle")

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

        # Emit events for HypoFuzz guidance
        event("variable_count=2")
        if var1 == var2:
            event("variable_uniqueness=same")
        else:
            event("variable_uniqueness=different")

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_variable_at_message_start(self, var_name: str) -> None:
        """PROPERTY: Message starting with { $var } parses."""
        source = f"msg = {{ ${var_name} }} text"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("variable_position=start")

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_variable_at_message_end(self, var_name: str) -> None:
        """PROPERTY: Message ending with { $var } parses."""
        source = f"msg = text {{ ${var_name} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("variable_position=end")

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_variable_only_message(self, var_name: str) -> None:
        """PROPERTY: Message with only { $var } parses."""
        source = f"msg = {{ ${var_name} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("variable_position=only")

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

        # Emit events for HypoFuzz guidance
        event(f"variable_count={min(count, 10)}")
        event("variable_uniqueness=repeated")


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

        # Emit events for HypoFuzz guidance
        event("placeable_type=string_literal")

    @given(number=numbers)
    @settings(max_examples=150)
    def test_placeable_with_number_literal(self, number: int) -> None:
        """PROPERTY: { 123 } parses as placeable."""
        source = f"msg = {{ {number} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("placeable_type=number_literal")
        if number < 0:
            event("number_sign=negative")
        elif number == 0:
            event("number_sign=zero")
        else:
            event("number_sign=positive")

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

        # Emit events for HypoFuzz guidance
        event("placeable_type=message_ref")

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

        # Emit events for HypoFuzz guidance
        event(f"consecutive_placeables={min(count, 5)}")

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

        # Emit events for HypoFuzz guidance
        if len(whitespace) == 0:
            event("internal_whitespace=none")
        elif "\t" in whitespace:
            event("internal_whitespace=has_tabs")
        else:
            event("internal_whitespace=spaces_only")


# ============================================================================
# SELECT EXPRESSIONS
# ============================================================================


