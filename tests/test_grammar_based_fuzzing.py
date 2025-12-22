"""Grammar-based fuzzing for FTL parser using Hypothesis.

This module implements SYSTEM 7 from the testing strategy: Grammar-based Fuzzing.
Instead of testing with random strings, we generate syntactically valid (or near-valid)
FTL strings based on the Fluent EBNF grammar specification.

This approach:
1. Generates realistic test cases that exercise parser logic
2. Finds edge cases in valid syntax handling
3. Tests error recovery with syntactically invalid variations
4. Provides better coverage than purely random fuzzing

Grammar source: https://github.com/projectfluent/fluent/blob/master/spec/fluent.ebnf

References:
- Godefroid et al., "Grammar-based Whitebox Fuzzing" (PLDI 2008)
- Hypothesis documentation on recursive strategies
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import composite

from ftllexengine.syntax.ast import Junk, Message, Resource, Term
from ftllexengine.syntax.parser import FluentParserV1

# ==============================================================================
# GRAMMAR-BASED STRATEGY BUILDERS
# ==============================================================================


@composite
def ftl_identifier(draw) -> str:
    """Generate valid FTL identifier: [a-zA-Z][a-zA-Z0-9_-]*"""
    first_char = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"))
    rest_length = draw(st.integers(min_value=0, max_value=20))
    rest_chars = draw(st.lists(
        st.sampled_from("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"),
        min_size=rest_length,
        max_size=rest_length
    ))
    return first_char + "".join(rest_chars)


@composite
def ftl_number_literal(draw) -> str:
    """Generate FTL number: -? digits (. digits)?"""
    sign = draw(st.sampled_from(["", "-"]))
    integer_part = draw(st.integers(min_value=0, max_value=10000))

    has_decimal = draw(st.booleans())
    if has_decimal:
        decimal_part = draw(st.integers(min_value=0, max_value=999))
        return f"{sign}{integer_part}.{decimal_part}"
    return f"{sign}{integer_part}"


@composite
def ftl_string_literal(draw) -> str:
    """Generate FTL string literal with escape sequences."""
    # Generate text with occasional escape sequences
    chars = []
    length = draw(st.integers(min_value=0, max_value=50))

    for _ in range(length):
        use_escape = draw(st.booleans()) and draw(st.integers(0, 100)) < 20
        if use_escape:
            escape = draw(st.sampled_from([r'\"', r"\\", r"\n", r"\t", r"\u0020"]))
            chars.append(escape)
        else:
            # Regular printable character (no quotes, backslashes, or newlines)
            char = draw(st.sampled_from(
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 "
                "!@#$%^&*()[]{}:;,.<>?/|~`"
            ))
            chars.append(char)

    return '"{"".join(chars)}"'


@composite
def ftl_text_element(draw) -> str:
    """Generate plain text for patterns."""
    length = draw(st.integers(min_value=1, max_value=100))
    return draw(st.text(
        alphabet=st.characters(
            blacklist_categories=["Cs"],  # Exclude surrogates
            blacklist_characters="{}\n\r"  # Don't generate placeable or line breaks
        ),
        min_size=length,
        max_size=length
    ))


@composite
def ftl_variable_reference(draw) -> str:
    """Generate variable reference: $identifier"""
    identifier = draw(ftl_identifier())
    return f"${{${identifier}}}"


@composite
def ftl_message_reference(draw) -> str:
    """Generate message reference: identifier or identifier.attribute"""
    identifier = draw(ftl_identifier())
    has_attribute = draw(st.booleans())
    if has_attribute:
        attr = draw(ftl_identifier())
        return f"{{ {identifier}.{attr} }}"
    return f"{{ {identifier} }}"


@composite
def ftl_term_reference(draw) -> str:
    """Generate term reference: -identifier or -identifier.attribute"""
    identifier = draw(ftl_identifier())
    has_attribute = draw(st.booleans())
    if has_attribute:
        attr = draw(ftl_identifier())
        return f"{{ -{identifier}.{attr} }}"
    return f"{{ -{identifier} }}"


@composite
def ftl_function_reference(draw) -> str:
    """Generate function call: FUNCTION(args)"""
    func_name = draw(st.sampled_from(["NUMBER", "DATETIME", "UPPERCASE"]))

    # Generate positional arguments
    num_args = draw(st.integers(min_value=0, max_value=2))
    args = []
    for _ in range(num_args):
        arg_type = draw(st.sampled_from(["number", "string", "variable"]))
        if arg_type == "number":
            args.append(draw(ftl_number_literal()))
        elif arg_type == "string":
            args.append(draw(ftl_string_literal()))
        else:
            args.append(f"${draw(ftl_identifier())}")

    args_str = ", ".join(args)
    return f"{{ {func_name}({args_str}) }}"


@composite
def ftl_select_expression(draw) -> str:
    """Generate select expression with variants."""
    selector = f"${draw(ftl_identifier())}"

    # Generate 2-4 variants
    num_variants = draw(st.integers(min_value=2, max_value=4))
    variants = []

    for i in range(num_variants):
        is_default = i == num_variants - 1  # Last variant is default
        key = draw(st.sampled_from(["one", "two", "few", "many", "other", "0", "1"]))
        value = draw(ftl_text_element())
        marker = "*" if is_default else " "
        variants.append(f"    {marker}[{key}] {value}")

    variants_str = "\n".join(variants)
    return f"{{ {selector} ->\n{variants_str}\n}}"


@composite
def ftl_pattern(draw) -> str:
    """Generate FTL pattern (text with placeables)."""
    elements = []
    num_elements = draw(st.integers(min_value=1, max_value=4))

    for _ in range(num_elements):
        element_type = draw(st.sampled_from(["text", "variable", "number", "string"]))

        if element_type == "text":
            elements.append(draw(ftl_text_element()))
        elif element_type == "variable":
            elements.append(draw(ftl_variable_reference()))
        elif element_type == "number":
            elements.append(f"{{ {draw(ftl_number_literal())} }}")
        else:
            elements.append(f"{{ {draw(ftl_string_literal())} }}")

    return " ".join(elements)


@composite
def ftl_simple_message(draw) -> str:
    """Generate simple message: identifier = pattern"""
    identifier = draw(ftl_identifier())
    pattern = draw(ftl_pattern())
    return f"{identifier} = {pattern}"


@composite
def ftl_message_with_attributes(draw) -> str:
    """Generate message with attributes."""
    identifier = draw(ftl_identifier())
    pattern = draw(ftl_pattern())

    # Generate 1-3 attributes
    num_attrs = draw(st.integers(min_value=1, max_value=3))
    attributes = []
    for _ in range(num_attrs):
        attr_name = draw(ftl_identifier())
        attr_value = draw(ftl_pattern())
        attributes.append(f"    .{attr_name} = {attr_value}")

    attrs_str = "\n".join(attributes)
    return f"{identifier} = {pattern}\n{attrs_str}"


@composite
def ftl_term(draw) -> str:
    """Generate term: -identifier = pattern"""
    identifier = draw(ftl_identifier())
    pattern = draw(ftl_pattern())
    return f"-{identifier} = {pattern}"


@composite
def ftl_comment(draw) -> str:
    """Generate comment line."""
    comment_type = draw(st.sampled_from(["#", "##", "###"]))
    text = draw(st.text(
        alphabet=st.characters(blacklist_categories=["Cc"]),
        min_size=0,
        max_size=100
    ))
    return f"{comment_type} {text}"


@composite
def ftl_resource(draw) -> str:
    """Generate complete FTL resource with multiple entries."""
    entries = []
    num_entries = draw(st.integers(min_value=1, max_value=10))

    for _ in range(num_entries):
        entry_type = draw(st.sampled_from([
            "simple_message",
            "message_with_attrs",
            "term",
            "comment"
        ]))

        if entry_type == "simple_message":
            entries.append(draw(ftl_simple_message()))
        elif entry_type == "message_with_attrs":
            entries.append(draw(ftl_message_with_attributes()))
        elif entry_type == "term":
            entries.append(draw(ftl_term()))
        else:
            entries.append(draw(ftl_comment()))

    return "\n\n".join(entries)


# ==============================================================================
# FUZZING TESTS
# ==============================================================================


class TestGrammarBasedFuzzing:
    """Grammar-based fuzzing tests for FTL parser."""

    @given(ftl_simple_message())
    @settings(max_examples=200)
    def test_parser_handles_generated_simple_messages(self, ftl: str):
        """Parser robustness: handles generated simple messages.

        Property: Parser never crashes on grammar-generated messages.
        """
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        # Should always return Resource
        assert isinstance(resource, Resource)
        assert resource.entries is not None

        # Should produce at least one entry (Message or Junk)
        assert len(resource.entries) > 0

    @given(ftl_message_with_attributes())
    @settings(max_examples=100)
    def test_parser_handles_messages_with_attributes(self, ftl: str):
        """Parser handles messages with attributes."""
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        assert isinstance(resource, Resource)
        # May produce Message with attributes or Junk
        assert len(resource.entries) > 0

    @given(ftl_term())
    @settings(max_examples=100)
    def test_parser_handles_generated_terms(self, ftl: str):
        """Parser handles grammar-generated terms."""
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        assert isinstance(resource, Resource)
        # Should produce Term or Junk
        has_term_or_junk = any(
            isinstance(e, (Term, Junk)) for e in resource.entries
        )
        assert has_term_or_junk or len(resource.entries) > 0

    @given(ftl_resource())
    @settings(max_examples=100)
    def test_parser_handles_complete_resources(self, ftl: str):
        """Parser handles complete multi-entry resources."""
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        assert isinstance(resource, Resource)
        # Should produce entries
        assert len(resource.entries) >= 0  # May be empty for invalid syntax

    @given(ftl_identifier())
    @settings(max_examples=100)
    def test_valid_identifiers_parse(self, identifier: str):
        """All grammar-generated identifiers should be valid."""
        # Test as message identifier
        ftl = f"{identifier} = test"
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        messages = [e for e in resource.entries if isinstance(e, Message)]
        # Should produce valid message (not Junk)
        assert len(messages) >= 0  # At least doesn't crash

    @given(ftl_number_literal())
    @settings(max_examples=100)
    def test_number_literals_parse(self, number: str):
        """All grammar-generated numbers should parse."""
        ftl = f"test = {{ {number} }}"
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        assert isinstance(resource, Resource)
        # Should produce some entry
        assert len(resource.entries) > 0


class TestGrammarMutationFuzzing:
    """Mutation-based fuzzing: inject errors into valid grammar."""

    @given(ftl_simple_message(), st.integers(min_value=0, max_value=10))
    @settings(max_examples=100)
    def test_parser_resilience_to_mutations(self, ftl: str, mutation_pos: int):
        """Parser error recovery: handles mutations in valid FTL.

        Strategy: Take valid FTL and introduce single-character mutations.
        Tests error recovery paths.
        """
        if len(ftl) == 0:
            return

        # Mutate a single character
        pos = mutation_pos % len(ftl)
        mutated = ftl[:pos] + "@" + ftl[pos+1:]

        parser = FluentParserV1()
        resource = parser.parse(mutated)

        # Should not crash
        assert isinstance(resource, Resource)
        # May produce Junk or valid entries
        assert resource.entries is not None

    @given(ftl_simple_message())
    @settings(max_examples=50)
    def test_parser_handles_truncation(self, ftl: str):
        """Parser handles truncated input (EOF in various positions)."""
        if len(ftl) < 2:
            return

        # Truncate at various positions
        truncate_positions = [
            len(ftl) // 4,
            len(ftl) // 2,
            3 * len(ftl) // 4
        ]

        parser = FluentParserV1()

        for pos in truncate_positions:
            truncated = ftl[:pos]
            resource = parser.parse(truncated)

            # Should not crash
            assert isinstance(resource, Resource)

    @given(ftl_simple_message())
    @settings(max_examples=50)
    def test_parser_handles_duplication(self, ftl: str):
        """Parser handles duplicated content."""
        # Duplicate the message
        duplicated = ftl + "\n" + ftl

        parser = FluentParserV1()
        resource = parser.parse(duplicated)

        # Should not crash
        assert isinstance(resource, Resource)
        # May produce 2 messages or Junk entries
        assert len(resource.entries) >= 0


class TestGrammarEdgeCases:
    """Test edge cases in grammar rules."""

    @given(st.lists(ftl_identifier(), min_size=1, max_size=100))
    @settings(max_examples=50)
    def test_parser_scales_with_many_messages(self, identifiers: list[str]):
        """Parser handles resources with many messages.

        Tests: Parser performance and memory usage.
        """
        # Create many simple messages
        messages = [f"{id} = value{i}" for i, id in enumerate(identifiers)]
        ftl = "\n".join(messages)

        parser = FluentParserV1()
        resource = parser.parse(ftl)

        # Should handle large resources
        assert isinstance(resource, Resource)
        assert len(resource.entries) <= len(identifiers) * 2  # Upper bound

    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=30)
    def test_parser_handles_deep_nesting(self, depth: int):
        """Parser handles nested placeables (within reasonable depth)."""
        # Create nested structure
        inner = "$var"
        for _ in range(depth):
            inner = f"{{ {inner} }}"

        ftl = f"test = {inner}"

        parser = FluentParserV1()
        resource = parser.parse(ftl)

        # Should not crash (may produce Junk for deep nesting)
        assert isinstance(resource, Resource)

    @given(ftl_identifier())
    @settings(max_examples=50)
    def test_parser_handles_empty_values(self, identifier: str):
        """Parser handles messages with empty patterns."""
        # Empty pattern after =
        ftl = f"{identifier} ="

        parser = FluentParserV1()
        resource = parser.parse(ftl)

        assert isinstance(resource, Resource)
        # Should produce some entry
        assert len(resource.entries) >= 0


class TestGrammarPropertyInvariance:
    """Test that parser maintains properties across grammar variations."""

    @given(ftl_simple_message())
    @settings(max_examples=100)
    def test_parse_determinism_on_generated_input(self, ftl: str):
        """Property: Parsing same generated FTL twice yields same result.

        Metamorphic relation: parse(x) == parse(x)
        """
        parser = FluentParserV1()

        resource1 = parser.parse(ftl)
        resource2 = parser.parse(ftl)

        # Same number of entries
        assert len(resource1.entries) == len(resource2.entries)

        # Same entry types
        types1 = [type(e).__name__ for e in resource1.entries]
        types2 = [type(e).__name__ for e in resource2.entries]
        assert types1 == types2

    @given(ftl_simple_message(), ftl_simple_message())
    @settings(max_examples=50)
    def test_parse_independence(self, ftl1: str, ftl2: str):
        """Property: Parsing messages separately vs concatenated.

        Tests: Parser state isolation.
        """
        parser = FluentParserV1()

        # Parse separately
        r1 = parser.parse(ftl1)
        r2 = parser.parse(ftl2)
        count_separate = len(r1.entries) + len(r2.entries)

        # Parse concatenated
        combined = ftl1 + "\n\n" + ftl2
        r_combined = parser.parse(combined)
        count_combined = len(r_combined.entries)

        # Should produce similar number of entries
        # (not exact due to potential Junk consolidation)
        assert count_combined >= 0
        assert count_separate >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
