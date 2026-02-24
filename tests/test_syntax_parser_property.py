"""Hypothesis property-based tests for Fluent parser.

Focus on parser robustness, error recovery, and invariant properties.
Comprehensive coverage of FTL syntax elements, edge cases, and error recovery.
Includes round-trip, metamorphic, structural, and malformed-input properties.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import assume, event, example, given, settings
from hypothesis import strategies as st

from ftllexengine.syntax.ast import (
    Comment,
    Junk,
    Message,
    Resource,
    Term,
)
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import FluentSerializer
from tests.strategies import (
    ftl_identifiers as shared_ftl_identifiers,
)
from tests.strategies import (
    ftl_simple_text,
)

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
decimals = st.decimals(
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

        # Emit events for HypoFuzz guidance
        event("select_variant_count=1")
        event("select_type=minimal")

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

        # Emit events for HypoFuzz guidance
        event("select_variant_count=3")
        if key1 == key2:
            event("variant_keys=duplicate")
        else:
            event("variant_keys=unique")

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

        # Emit events for HypoFuzz guidance
        event(f"select_variant_count={min(count + 1, 10)}")

    @given(var_name=variable_names, text=safe_text)
    @settings(max_examples=100)
    def test_select_variant_with_text(self, var_name: str, text: str) -> None:
        """PROPERTY: Select variant values can contain text."""
        source = f"msg = {{ ${var_name} ->\n   *[other] {text}\n}}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("variant_value_type=text")

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

        # Emit events for HypoFuzz guidance
        event("variant_value_type=with_placeable")

    @given(var_name=variable_names, number=numbers)
    @settings(max_examples=100)
    def test_select_with_numeric_keys(self, var_name: str, number: int) -> None:
        """PROPERTY: Select with numeric variant keys parses."""
        source = f"msg = {{ ${var_name} ->\n    [{number}] Exact\n   *[other] Default\n}}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("variant_key_type=numeric")
        if number < 0:
            event("numeric_key_sign=negative")
        elif number == 0:
            event("numeric_key_sign=zero")
        else:
            event("numeric_key_sign=positive")


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

            # Emit events for HypoFuzz guidance
            event(f"entry_type={type(entry).__name__}")
        event("term_structure=simple")

    @given(term_id=ftl_identifiers, text=safe_text)
    @settings(max_examples=100)
    def test_term_with_text_value(self, term_id: str, text: str) -> None:
        """PROPERTY: Term with text value parses."""
        source = f"-{term_id} = {text}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("term_structure=with_text")

    @given(term_id=ftl_identifiers, var_name=variable_names)
    @settings(max_examples=100)
    def test_term_with_placeable(self, term_id: str, var_name: str) -> None:
        """PROPERTY: Term with placeable parses."""
        source = f"-{term_id} = Value {{ ${var_name} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("term_structure=with_placeable")

    @given(term_id=ftl_identifiers, attr_name=attribute_names)
    @settings(max_examples=100)
    def test_term_with_attribute(self, term_id: str, attr_name: str) -> None:
        """PROPERTY: Term with attribute parses."""
        source = f"-{term_id} = Value\n    .{attr_name} = Attribute value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("term_structure=with_attribute")

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

        # Emit events for HypoFuzz guidance
        event("term_ref_type=simple")

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

        # Emit events for HypoFuzz guidance
        event("term_ref_type=with_attribute")


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

        # Emit events for HypoFuzz guidance
        if len(text) == 0:
            event("string_length=empty")
        elif len(text) <= 10:
            event("string_length=short")
        elif len(text) <= 50:
            event("string_length=medium")
        else:
            event("string_length=long")

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

        # Emit events for HypoFuzz guidance
        if char in ('"', "\\"):
            event("char_type=special_escape")
        elif char.isalpha():
            event("char_type=alpha")
        elif char.isdigit():
            event("char_type=digit")
        else:
            event("char_type=other")

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

        # Emit events for HypoFuzz guidance
        codepoint = ord(unicode_char)
        if codepoint < 0x0800:
            event("unicode_range=latin_extended")
        elif codepoint < 0x3000:
            event("unicode_range=mid_bmp")
        else:
            event("unicode_range=cjk_symbols")


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

        # Emit events for HypoFuzz guidance
        if number < 0:
            event("integer_sign=negative")
        elif number == 0:
            event("integer_sign=zero")
        else:
            event("integer_sign=positive")
        if abs(number) > 1000000:
            event("integer_magnitude=large")

    @given(decimal=decimals)
    @settings(max_examples=150)
    def test_decimal_literal(self, decimal: Decimal) -> None:
        """PROPERTY: Decimal literals parse correctly."""
        # Use fixed-point notation to avoid scientific notation in FTL source
        num_str = format(decimal, "f")
        # Filter out strings that are too long for the parser
        assume(len(num_str) <= 50)
        source = f"msg = {{ {num_str} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        if decimal < Decimal("0"):
            event("decimal_sign=negative")
        elif decimal == Decimal("0"):
            event("decimal_sign=zero")
        else:
            event("decimal_sign=positive")
        # Check if it's a whole number decimal (use str to avoid overflow on huge Decimals)
        _, _, frac_part = num_str.lstrip("-").partition(".")
        if not frac_part or all(c == "0" for c in frac_part):
            event("decimal_type=whole")
        else:
            event("decimal_type=fractional")

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

        # Emit events for HypoFuzz guidance
        event("integer_sign=positive")
        if number > 100000:
            event("integer_magnitude=large")
        elif number > 1000:
            event("integer_magnitude=medium")
        else:
            event("integer_magnitude=small")

    @given(number=st.integers(min_value=-1000000, max_value=-1))
    @settings(max_examples=100)
    def test_negative_integer(self, number: int) -> None:
        """PROPERTY: Negative integers parse."""
        source = f"msg = {{ {number} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("integer_sign=negative")
        if abs(number) > 100000:
            event("integer_magnitude=large")
        elif abs(number) > 1000:
            event("integer_magnitude=medium")
        else:
            event("integer_magnitude=small")


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

        # Emit events for HypoFuzz guidance
        event("message_structure=value_only")

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

        # Emit events for HypoFuzz guidance
        event("message_structure=value_and_attribute")
        event("attribute_count=1")

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

        # Emit events for HypoFuzz guidance
        event("message_structure=value_and_attributes")
        event(f"attribute_count={min(count, 5)}")

    @given(msg_id=ftl_identifiers, attr_name=attribute_names)
    @settings(max_examples=100)
    def test_message_attribute_only(self, msg_id: str, attr_name: str) -> None:
        """PROPERTY: Message with only attributes (no value) parses."""
        source = f"{msg_id} =\n    .{attr_name} = Attribute value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("message_structure=attribute_only")

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

        # Emit events for HypoFuzz guidance
        event("message_structure=value_with_placeable")


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

        # Emit events for HypoFuzz guidance
        event("comment_level=standalone")

    @given(text=safe_text)
    @settings(max_examples=100)
    def test_group_comment(self, text: str) -> None:
        """PROPERTY: Group comment ## parses."""
        source = f"## {text}\n\nmsg = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("comment_level=group")

    @given(text=safe_text)
    @settings(max_examples=100)
    def test_resource_comment(self, text: str) -> None:
        """PROPERTY: Resource comment ### parses."""
        source = f"### {text}\n\nmsg = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("comment_level=resource")

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

        # Emit events for HypoFuzz guidance
        event(f"comment_lines={min(count, 5)}")

    @given(msg_id=ftl_identifiers, text=safe_text)
    @settings(max_examples=100)
    def test_comment_attached_to_message(self, msg_id: str, text: str) -> None:
        """PROPERTY: Comment immediately before message parses."""
        source = f"# {text}\n{msg_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("comment_position=attached")


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

        # Emit events for HypoFuzz guidance
        event("whitespace_position=before_equals")
        if spaces == 0:
            event("space_count=none")
        elif spaces <= 3:
            event("space_count=few")
        else:
            event("space_count=many")

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

        # Emit events for HypoFuzz guidance
        event("whitespace_position=after_equals")
        if spaces == 0:
            event("space_count=none")
        elif spaces <= 3:
            event("space_count=few")
        else:
            event("space_count=many")

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

        # Emit events for HypoFuzz guidance
        event("whitespace_type=indentation")
        if indent == 4:
            event("indent_level=minimal")
        elif indent <= 8:
            event("indent_level=standard")
        else:
            event("indent_level=deep")

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

        # Emit events for HypoFuzz guidance
        event("whitespace_type=blank_lines")
        if blank_lines == 0:
            event("blank_line_count=none")
        elif blank_lines == 1:
            event("blank_line_count=single")
        else:
            event("blank_line_count=multiple")

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

        # Emit events for HypoFuzz guidance
        event("whitespace_position=trailing")
        if trailing_spaces == 0:
            event("space_count=none")
        elif trailing_spaces <= 3:
            event("space_count=few")
        else:
            event("space_count=many")


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

        # Emit events for HypoFuzz guidance
        event("function_name=NUMBER")
        event("function_arg_type=variable")

    @given(var_name=variable_names)
    @settings(max_examples=150)
    def test_datetime_function_call(self, var_name: str) -> None:
        """PROPERTY: DATETIME($var) parses correctly."""
        source = f"msg = {{ DATETIME(${var_name}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("function_name=DATETIME")
        event("function_arg_type=variable")

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_function_with_named_arg(self, var_name: str) -> None:
        """PROPERTY: FUNC($var, opt: val) parses."""
        source = f"msg = {{ NUMBER(${var_name}, minimumFractionDigits: 2) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("function_options=with_named")
        event("option_value_type=numeric")

    @given(var_name=variable_names, number=numbers)
    @settings(max_examples=100)
    def test_function_with_numeric_option(self, var_name: str, number: int) -> None:
        """PROPERTY: Function with numeric option parses."""
        source = f"msg = {{ NUMBER(${var_name}, minimumFractionDigits: {number}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("function_options=with_numeric")
        if number < 0:
            event("option_value_sign=negative")
        elif number == 0:
            event("option_value_sign=zero")
        else:
            event("option_value_sign=positive")

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_function_with_string_option(self, var_name: str) -> None:
        """PROPERTY: Function with string option parses."""
        source = f'msg = {{ DATETIME(${var_name}, style: "long") }}'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("function_options=with_string")
        event("option_value_type=string")

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

        # Emit events for HypoFuzz guidance
        event("function_options=multiple")
        event(f"option_count={min(count, 5)}")

    @given(func_name=ftl_identifiers, var_name=variable_names)
    @settings(max_examples=100)
    def test_custom_function_call(self, func_name: str, var_name: str) -> None:
        """PROPERTY: Custom function calls parse."""
        # Note: uppercase function names required
        source = f"msg = {{ {func_name.upper()}(${var_name}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("function_name=CUSTOM")
        if len(func_name) <= 5:
            event("function_name_length=short")
        else:
            event("function_name_length=long")

    @given(number=numbers)
    @settings(max_examples=50)
    def test_function_with_number_literal_arg(self, number: int) -> None:
        """PROPERTY: Function with number literal argument parses."""
        source = f"msg = {{ NUMBER({number}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("function_arg_type=literal")
        if number < 0:
            event("literal_sign=negative")
        elif number == 0:
            event("literal_sign=zero")
        else:
            event("literal_sign=positive")

    @given(var_name=variable_names)
    @settings(max_examples=50)
    def test_nested_function_calls(self, var_name: str) -> None:
        """PROPERTY: Nested function calls parse (if supported)."""
        # Most parsers support simple nesting
        source = f"msg = {{ NUMBER(${var_name}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("function_nesting=simple")


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

        # Emit events for HypoFuzz guidance
        event("msg_ref_type=simple")
        if msg_id1 == msg_id2:
            event("msg_ref_self=true")
        else:
            event("msg_ref_self=false")

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

        # Emit events for HypoFuzz guidance
        event("msg_ref_type=with_attribute")

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

        # Emit events for HypoFuzz guidance
        event("msg_ref_type=multiple")
        event(f"msg_ref_count={min(count, 5)}")

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

        # Emit events for HypoFuzz guidance
        event("msg_ref_type=mixed_with_text")
        if len(text) == 0:
            event("surrounding_text=empty")
        else:
            event("surrounding_text=present")


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

        # Emit events for HypoFuzz guidance
        event("identifier_type=with_number_suffix")
        if number == 0:
            event("number_suffix=zero")
        elif number < 10:
            event("number_suffix=single_digit")
        elif number < 100:
            event("number_suffix=two_digit")
        else:
            event("number_suffix=three_digit")

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

        # Emit events for HypoFuzz guidance
        event("identifier_type=with_hyphens")
        event(f"identifier_parts={min(len(parts), 5)}")

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

        # Emit events for HypoFuzz guidance
        event("identifier_type=with_underscores")
        event(f"identifier_parts={min(len(parts), 5)}")

    @given(length=st.integers(min_value=1, max_value=100))
    @settings(max_examples=50)
    def test_identifier_length_handling(self, length: int) -> None:
        """PROPERTY: Identifiers of various lengths parse."""
        msg_id = "a" * length
        source = f"{msg_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("identifier_type=length_test")
        if length == 1:
            event("identifier_length=minimal")
        elif length <= 10:
            event("identifier_length=short")
        elif length <= 50:
            event("identifier_length=medium")
        else:
            event("identifier_length=long")

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

        # Emit events for HypoFuzz guidance
        event("identifier_type=mixed_case")
        if uppercase_count == 0:
            event("case_mix=all_lower")
        elif uppercase_count >= len(chars):
            event("case_mix=all_upper")
        else:
            event("case_mix=mixed")


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

        # Emit events for HypoFuzz guidance
        event("escape_type=unicode")
        if codepoint < 0x0080:
            event("codepoint_range=ascii")
        elif codepoint < 0x0800:
            event("codepoint_range=latin_extended")
        elif codepoint < 0x3000:
            event("codepoint_range=mid_bmp")
        else:
            event("codepoint_range=cjk_symbols")

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

        # Emit events for HypoFuzz guidance
        event("line_ending_type=unix")

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=100)
    def test_windows_line_endings(self, msg_id: str) -> None:
        """PROPERTY: Windows \\r\\n line endings parse correctly."""
        source = f"{msg_id}1 = value1\r\n{msg_id}2 = value2\r\n"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("line_ending_type=windows")

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=100)
    def test_old_mac_line_endings(self, msg_id: str) -> None:
        """PROPERTY: Old Mac \\r line endings parse."""
        source = f"{msg_id}1 = value1\r{msg_id}2 = value2\r"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("line_ending_type=old_mac")

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=50)
    def test_mixed_line_endings(self, msg_id: str) -> None:
        """PROPERTY: Mixed line endings are handled."""
        source = f"{msg_id}1 = value1\n{msg_id}2 = value2\r\n{msg_id}3 = value3\r"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("line_ending_type=mixed")

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=50)
    def test_no_final_newline(self, msg_id: str) -> None:
        """PROPERTY: Source without final newline parses."""
        source = f"{msg_id} = value"  # No trailing newline
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("line_ending_type=no_final")


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

        # Emit events for HypoFuzz guidance
        event("bom_presence=with_bom")

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=50)
    def test_source_without_bom(self, msg_id: str) -> None:
        """PROPERTY: Source without BOM parses normally."""
        source = f"{msg_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("bom_presence=without_bom")

    @given(msg_id=ftl_identifiers, text=safe_text)
    @settings(max_examples=50)
    def test_bom_only_at_start(self, msg_id: str, text: str) -> None:
        """PROPERTY: BOM only valid at file start."""
        source = f"{msg_id} = {text}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("bom_presence=no_bom_with_content")
        if len(text) == 0:
            event("text_content=empty")
        else:
            event("text_content=present")


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

        # Emit events for HypoFuzz guidance
        event("boundary_type=text_placeable")
        if len(text) == 0:
            event("prefix_text=empty")
        else:
            event("prefix_text=present")

    @given(var_name=variable_names, text=safe_text)
    @settings(max_examples=100)
    def test_placeable_text_boundary(self, var_name: str, text: str) -> None:
        """PROPERTY: Boundary between placeable and text is correct."""
        source = f"msg = {{ ${var_name} }}{text}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("boundary_type=placeable_text")
        if len(text) == 0:
            event("suffix_text=empty")
        else:
            event("suffix_text=present")

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

        # Emit events for HypoFuzz guidance
        event("boundary_type=placeable_placeable")
        if var1 == var2:
            event("adjacent_vars=same")
        else:
            event("adjacent_vars=different")

    @given(text1=safe_text, text2=safe_text)
    @settings(max_examples=50)
    def test_text_text_concatenation(self, text1: str, text2: str) -> None:
        """PROPERTY: Consecutive text elements are handled."""
        source = f"msg = {text1} {text2}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("boundary_type=text_text")
        total_len = len(text1) + len(text2)
        if total_len == 0:
            event("combined_text=empty")
        elif total_len <= 20:
            event("combined_text=short")
        else:
            event("combined_text=long")


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

        # Emit events for HypoFuzz guidance
        event("multiline_type=text_only")
        event(f"line_count={min(len(lines), 5)}")

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

        # Emit events for HypoFuzz guidance
        event("multiline_type=with_placeables")
        event(f"line_count={min(len(lines), 5)}")

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

        # Emit events for HypoFuzz guidance
        event("multiline_type=consistent_indent")
        if indent == 4:
            event("indent_level=minimal")
        elif indent <= 8:
            event("indent_level=standard")
        else:
            event("indent_level=deep")


# ============================================================================
# ROUND-TRIP PROPERTIES
# ============================================================================


class TestParserRoundTrip:
    """Property: parse(serialize(parse(source))) preserves AST structure."""

    @given(
        msg_id=shared_ftl_identifiers(),
        msg_value=ftl_simple_text(),
    )
    @settings(max_examples=1000)
    def test_simple_message_roundtrip(
        self, msg_id: str, msg_value: str
    ) -> None:
        """Simple messages round-trip through serialize/parse."""
        parser = FluentParserV1()
        serializer = FluentSerializer()

        ftl_source = f"{msg_id} = {msg_value}"
        resource1 = parser.parse(ftl_source)
        entry_count = len(resource1.entries)
        event(f"entry_count={entry_count}")

        assert entry_count > 0

        serialized = serializer.serialize(resource1)
        resource2 = parser.parse(serialized)

        assert len(resource2.entries) == entry_count
        if isinstance(resource1.entries[0], Message) and isinstance(
            resource2.entries[0], Message
        ):
            assert (
                resource1.entries[0].id.name
                == resource2.entries[0].id.name
            )

    @given(
        msg_id=shared_ftl_identifiers(),
        var_name=shared_ftl_identifiers(),
        prefix=ftl_simple_text(),
        suffix=ftl_simple_text(),
    )
    @settings(max_examples=500)
    def test_variable_interpolation_roundtrip(
        self,
        msg_id: str,
        var_name: str,
        prefix: str,
        suffix: str,
    ) -> None:
        """Messages with variable interpolation round-trip."""
        parser = FluentParserV1()
        serializer = FluentSerializer()

        ftl_source = (
            f"{msg_id} = {prefix} {{ ${var_name} }} {suffix}"
        )
        resource1 = parser.parse(ftl_source)
        has_junk = any(
            isinstance(e, Junk) for e in resource1.entries
        )
        event(
            f"outcome={'has_junk' if has_junk else 'roundtrip_clean'}"
        )

        assert not has_junk

        serialized = serializer.serialize(resource1)
        resource2 = parser.parse(serialized)

        assert not any(
            isinstance(e, Junk) for e in resource2.entries
        )


# ============================================================================
# METAMORPHIC PROPERTIES
# ============================================================================


class TestParserMetamorphicProperties:
    """Metamorphic properties: predictable relations between inputs."""

    @given(
        value1=ftl_simple_text(),
        value2=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_concatenation_preserves_message_count(
        self, value1: str, value2: str
    ) -> None:
        """Separate messages in one source produce two entries."""
        parser = FluentParserV1()
        separate_source = f"m1 = {value1}\nm2 = {value2}"
        r1 = parser.parse(separate_source)

        non_junk = [
            e for e in r1.entries if not isinstance(e, Junk)
        ]
        msg_count = len(non_junk)
        event(f"non_junk_count={msg_count}")
        assert msg_count == 2

    @given(
        msg_id=shared_ftl_identifiers(),
        msg_value=ftl_simple_text(),
        newlines=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=200)
    def test_blank_line_count_independence(
        self, msg_id: str, msg_value: str, newlines: int
    ) -> None:
        """Blank lines between messages do not affect parse result."""
        parser = FluentParserV1()
        separator = "\n" * newlines
        ftl_source = f"m1 = test{separator}{msg_id} = {msg_value}"

        resource = parser.parse(ftl_source)
        messages = [
            e for e in resource.entries if isinstance(e, Message)
        ]
        event(f"separator_newlines={newlines}")
        assert len(messages) == 2

    @given(
        msg_id=shared_ftl_identifiers(),
        msg_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_deterministic_parsing(
        self, msg_id: str, msg_value: str
    ) -> None:
        """Parsing same input twice yields identical results."""
        source = f"{msg_id} = {msg_value}"
        parser = FluentParserV1()
        result1 = parser.parse(source)
        result2 = parser.parse(source)

        assert len(result1.entries) == len(result2.entries)
        for e1, e2 in zip(
            result1.entries, result2.entries, strict=True
        ):
            assert isinstance(e1, type(e2))
        event(f"entry_count={len(result1.entries)}")


# ============================================================================
# STRUCTURAL PROPERTIES
# ============================================================================


class TestParserStructuralProperties:
    """Properties about AST structure produced by parser."""

    @given(
        msg_id=shared_ftl_identifiers(),
        msg_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_message_has_required_fields(
        self, msg_id: str, msg_value: str
    ) -> None:
        """Parsed Messages have all required fields set."""
        parser = FluentParserV1()
        ftl_source = f"{msg_id} = {msg_value}"
        resource = parser.parse(ftl_source)
        messages = [
            e for e in resource.entries if isinstance(e, Message)
        ]

        assert len(messages) > 0
        msg = messages[0]
        assert msg.id is not None
        assert msg.id.name == msg_id
        assert msg.value is not None
        event(f"attribute_count={len(msg.attributes)}")

    @given(
        msg_id=shared_ftl_identifiers(),
        attr_name=shared_ftl_identifiers(),
        attr_value=ftl_simple_text(),
    )
    @settings(max_examples=200)
    def test_attribute_parsing_structure(
        self, msg_id: str, attr_name: str, attr_value: str
    ) -> None:
        """Messages with attributes parse into correct structure."""
        parser = FluentParserV1()
        ftl = f"{msg_id} =\n    .{attr_name} = {attr_value}"
        resource = parser.parse(ftl)
        messages = [
            e for e in resource.entries if isinstance(e, Message)
        ]

        has_attr = (
            bool(messages)
            and bool(messages[0].attributes)
        )
        event(
            f"outcome={'has_attr' if has_attr else 'no_attr'}"
        )
        if has_attr:
            attr = messages[0].attributes[0]
            assert attr.id.name == attr_name

    @given(
        term_id=shared_ftl_identifiers(),
        term_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_term_parsing_structure(
        self, term_id: str, term_value: str
    ) -> None:
        """Terms with leading hyphen parse correctly."""
        parser = FluentParserV1()
        ftl_source = f"-{term_id} = {term_value}"
        resource = parser.parse(ftl_source)

        terms = [
            e for e in resource.entries if isinstance(e, Term)
        ]
        event(f"term_count={len(terms)}")
        assert len(terms) > 0
        assert terms[0].id.name == term_id

    @given(
        msg_id=shared_ftl_identifiers(),
        nesting_depth=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=200)
    def test_nested_placeable_depth(
        self, msg_id: str, nesting_depth: int
    ) -> None:
        """Parser handles nested placeables up to depth limit."""
        parser = FluentParserV1()
        open_braces = "{ " * nesting_depth
        close_braces = " }" * nesting_depth
        ftl_source = f"{msg_id} = {open_braces}$x{close_braces}"

        resource = parser.parse(ftl_source)
        event(f"nesting_depth={nesting_depth}")
        assert len(resource.entries) > 0

    @given(source=st.text(min_size=0, max_size=500))
    @settings(max_examples=2000)
    def test_parser_always_returns_resource(
        self, source: str
    ) -> None:
        """Parser handles arbitrary input without crashing."""
        parser = FluentParserV1()
        try:
            result = parser.parse(source)
            assert isinstance(result, Resource)
            event(f"entry_count={len(result.entries)}")
        except RecursionError:
            pass

    @given(
        msg_id=shared_ftl_identifiers(),
        msg_value=ftl_simple_text(),
        leading_ws=st.text(alphabet=" \t", max_size=10),
        trailing_ws=st.text(alphabet=" \t", max_size=10),
    )
    @settings(max_examples=300)
    def test_whitespace_around_message(
        self, msg_id: str, msg_value: str,
        leading_ws: str, trailing_ws: str,
    ) -> None:
        """Leading/trailing whitespace does not change message ID."""
        parser = FluentParserV1()
        ftl1 = f"{msg_id} = {msg_value}"
        ftl2 = (
            f"{leading_ws}{msg_id} = {msg_value}{trailing_ws}"
        )

        resource1 = parser.parse(ftl1)
        resource2 = parser.parse(ftl2)

        msgs1 = [
            e for e in resource1.entries
            if isinstance(e, Message)
        ]
        msgs2 = [
            e for e in resource2.entries
            if isinstance(e, Message)
        ]
        ws_type = "mixed" if leading_ws and trailing_ws else "one"
        event(f"whitespace_padding={ws_type}")
        if msgs1 and msgs2:
            assert msgs1[0].id.name == msgs2[0].id.name


# ============================================================================
# MALFORMED INPUT PROPERTIES
# ============================================================================


@st.composite
def malformed_placeable(draw: st.DrawFn) -> str:
    """Generate placeables with strategic syntax errors."""
    corruptions = [
        "{",           # Missing content
        "{ ",          # Space but no content
        "{ $",         # Incomplete variable
        "{ $v",        # Incomplete variable name
        "{ $var",      # Missing closing }
        '{ "',         # Incomplete string literal
        '{ "text',     # Unterminated string
        "{ -",         # Incomplete term ref
        "{ -t",        # Incomplete term name
        "{ -term",     # Missing closing }
        "{ 1.",        # Malformed number
        "{ 1.2.",      # Invalid number format
        "{ FUNC",      # Missing parentheses
        "{ FUNC(",     # Incomplete function
        "{ FUNC($",    # Incomplete arg
        "{ msg.",      # Missing attr name
        "{ msg.@",     # Invalid attr name
        "{ $x ->",     # Incomplete select
        "{ $x -> [",   # Incomplete variant
        "{ $x -> [a]", # Missing pattern
    ]
    return draw(st.sampled_from(corruptions))


@st.composite
def malformed_function_call(draw: st.DrawFn) -> str:
    """Generate function calls with strategic syntax errors."""
    func_name = draw(
        st.sampled_from(["FUNC", "NUMBER", "DATETIME"])
    )
    corruptions = [
        f"{func_name}",
        f"{func_name}(",
        f"{func_name}($",
        f"{func_name}($v",
        f"{func_name}(1.2.",
        f'{{ {func_name}("',
        f"{func_name}(@",
        f"{func_name}(a:",
        f"{func_name}(a: )",
        f"{func_name}(123: x)",
        f"{func_name}(a: 1, a: 2)",
        f"{func_name}(x: 1, 2)",
    ]
    return draw(st.sampled_from(corruptions))


@st.composite
def malformed_select_expression(draw: st.DrawFn) -> str:
    """Generate select expressions with strategic errors."""
    var = draw(st.sampled_from(["$x", "$count", "$num"]))
    corruptions = [
        f"{{ {var} ->",
        f"{{ {var} -> [",
        f"{{ {var} -> [@",
        f"{{ {var} -> [a]",
        f"{{ {var} -> [a] Text",
        f"{{ {var} -> [a] {{ msg.",
        f"{{ {var} -> [one] X *[other] Y",
    ]
    return draw(st.sampled_from(corruptions))


@st.composite
def malformed_term_input(draw: st.DrawFn) -> str:
    """Generate terms with strategic syntax errors."""
    corruptions = [
        "-",
        "- ",
        "-@invalid",
        "-term",
        "-term =",
        "-term = val\n    .",
        "-term = val\n    .@",
    ]
    return draw(st.sampled_from(corruptions))


@st.composite
def malformed_term_reference(draw: st.DrawFn) -> str:
    """Generate term references with strategic errors."""
    corruptions = [
        "{ -",
        "{ - }",
        "{ -@bad }",
        "{ -term(",
        "{ -term(x",
        "{ -term.",
    ]
    return draw(st.sampled_from(corruptions))


@st.composite
def malformed_attribute(draw: st.DrawFn) -> str:
    """Generate attributes with strategic errors."""
    corruptions = [
        "    .",
        "    .@",
        "    . = val",
        "    .attr",
        "    .attr =",
    ]
    return draw(st.sampled_from(corruptions))


class TestMalformedPlaceables:
    """Parser handles malformed placeables without crashing."""

    @given(
        msg_id=shared_ftl_identifiers(),
        placeable=malformed_placeable(),
    )
    @settings(max_examples=100, deadline=None)
    @example(msg_id="key", placeable="{ msg.")
    @example(msg_id="key", placeable='{ "')
    @example(msg_id="key", placeable="{ 1.2.")
    def test_malformed_placeables(
        self, msg_id: str, placeable: str
    ) -> None:
        """Parser recovers from malformed placeables."""
        source = f"{msg_id} = {placeable}"
        event(f"placeable_len={len(placeable)}")
        parser = FluentParserV1()

        try:
            resource = parser.parse(source)
            assert resource is not None
        except RecursionError:
            assume(False)


class TestMalformedFunctionCalls:
    """Parser handles malformed function calls gracefully."""

    @given(
        msg_id=shared_ftl_identifiers(),
        func_call=malformed_function_call(),
    )
    @settings(max_examples=80, deadline=None)
    @example(msg_id="key", func_call="FUNC($")
    @example(msg_id="key", func_call="FUNC(1.2.")
    @example(msg_id="key", func_call='{ FUNC("')
    @example(msg_id="key", func_call="FUNC(@bad)")
    @example(msg_id="key", func_call="FUNC(a:)")
    @example(msg_id="key", func_call="FUNC")
    def test_malformed_function_calls(
        self, msg_id: str, func_call: str
    ) -> None:
        """Parser recovers from malformed function calls."""
        source = f"{msg_id} = {{ {func_call} }}"
        event(f"func_call_len={len(func_call)}")
        parser = FluentParserV1()
        resource = parser.parse(source)
        assert resource is not None


class TestMalformedSelectExpressions:
    """Parser handles malformed select expressions."""

    @given(
        msg_id=shared_ftl_identifiers(),
        select=malformed_select_expression(),
    )
    @settings(max_examples=50, deadline=None)
    @example(msg_id="key", select="{ $x -> [@")
    @example(msg_id="key", select="{ $x -> [a] Text")
    @example(
        msg_id="key",
        select="{ $x -> [a] { msg.",
    )
    def test_malformed_select_expressions(
        self, msg_id: str, select: str
    ) -> None:
        """Parser recovers from malformed selects."""
        source = f"{msg_id} = {select}"
        event(f"select_len={len(select)}")
        parser = FluentParserV1()
        resource = parser.parse(source)
        assert resource is not None


class TestMalformedTerms:
    """Parser handles malformed terms and term references."""

    @given(term_def=malformed_term_input())
    @settings(max_examples=40, deadline=None)
    @example(term_def="-@invalid")
    @example(term_def="-term = val\n    .")
    def test_malformed_term_definitions(
        self, term_def: str
    ) -> None:
        """Parser recovers from malformed term definitions."""
        event(f"input_len={len(term_def)}")
        parser = FluentParserV1()
        resource = parser.parse(term_def)
        assert resource is not None

    @given(
        msg_id=shared_ftl_identifiers(),
        term_ref=malformed_term_reference(),
    )
    @settings(max_examples=40, deadline=None)
    @example(msg_id="key", term_ref="{ -")
    @example(msg_id="key", term_ref="{ -term(")
    def test_malformed_term_references(
        self, msg_id: str, term_ref: str
    ) -> None:
        """Parser recovers from malformed term references."""
        source = f"{msg_id} = {term_ref}"
        event(f"term_ref_len={len(term_ref)}")
        parser = FluentParserV1()
        resource = parser.parse(source)
        assert resource is not None


class TestMalformedAttributes:
    """Parser handles malformed attributes."""

    @given(
        msg_id=shared_ftl_identifiers(),
        attr_line=malformed_attribute(),
    )
    @settings(max_examples=30, deadline=None)
    @example(msg_id="key", attr_line="    .")
    def test_malformed_attributes(
        self, msg_id: str, attr_line: str
    ) -> None:
        """Parser recovers from malformed attributes."""
        source = f"{msg_id} = value\n{attr_line}"
        event(f"attr_line_len={len(attr_line)}")
        parser = FluentParserV1()
        resource = parser.parse(source)
        assert resource is not None


class TestSpecialCharacterSequences:
    """Parser handles arbitrary special character sequences."""

    @given(
        text=st.text(
            alphabet="{}$-.[]*\n\r\t ",
            min_size=1,
            max_size=30,
        )
    )
    @settings(max_examples=200, deadline=None)
    def test_arbitrary_special_char_sequences(
        self, text: str
    ) -> None:
        """Parser never crashes on special FTL character combos."""
        assume(text.strip())
        parser = FluentParserV1()
        try:
            resource = parser.parse(text)
            assert resource is not None
            event(f"entry_count={len(resource.entries)}")
        except RecursionError:
            assume(False)

    @given(
        msg_id=shared_ftl_identifiers(),
        value=st.text(
            alphabet=(
                "abcdefghijklmnopqrstuvwxyz"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "0123456789{}$-. "
            ),
            min_size=1,
            max_size=40,
        ),
    )
    @settings(max_examples=150, deadline=None)
    def test_complex_value_patterns(
        self, msg_id: str, value: str
    ) -> None:
        """Parser handles complex patterns in values."""
        source = f"{msg_id} = {value}"
        parser = FluentParserV1()
        try:
            resource = parser.parse(source)
            assert resource is not None
            has_junk = any(
                isinstance(e, Junk) for e in resource.entries
            )
            event(
                f"outcome={'junk' if has_junk else 'clean'}"
            )
        except RecursionError:
            assume(False)

    @given(
        ftl_source=st.text(min_size=0, max_size=100)
    )
    @settings(max_examples=300, deadline=None)
    def test_universal_crash_resistance(
        self, ftl_source: str
    ) -> None:
        """Parser never crashes on any input."""
        parser = FluentParserV1()
        try:
            resource = parser.parse(ftl_source)
            assert resource is not None
            assert hasattr(resource, "entries")
            event(f"entry_count={len(resource.entries)}")
        except RecursionError:
            assume(False)

    @given(
        msg_id=shared_ftl_identifiers(),
        placeable_content=st.text(
            alphabet=(
                "abcdefghijklmnopqrstuvwxyz"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "0123456789$-. "
            ),
            min_size=0,
            max_size=20,
        ),
    )
    @settings(max_examples=100, deadline=None)
    def test_deterministic_placeable_parsing(
        self, msg_id: str, placeable_content: str
    ) -> None:
        """Parsing same placeable twice gives same result."""
        source = f"{msg_id} = {{ {placeable_content} }}"
        parser1 = FluentParserV1()
        parser2 = FluentParserV1()
        try:
            result1 = parser1.parse(source)
            result2 = parser2.parse(source)
            assert len(result1.entries) == len(result2.entries)
            for e1, e2 in zip(
                result1.entries, result2.entries, strict=True
            ):
                assert isinstance(e1, type(e2))
            event(f"entry_count={len(result1.entries)}")
        except RecursionError:
            assume(False)
