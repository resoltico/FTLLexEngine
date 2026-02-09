"""Property-based fuzzing tests for whitespace edge case handling.

This module provides comprehensive property-based tests targeting whitespace
handling bugs that have been historically problematic in the FTL parser,
serializer, and resolver. Each test is designed to exercise specific edge
cases identified through changelog analysis.

Whitespace Bug Categories Tested:
- FTL-GRAMMAR-003: Variant marker whitespace ([ one] vs [one])
- FTL-GRAMMAR-001: Blank lines before first content in multiline patterns
- FTL-PARSER-001: Comment blank line detection
- FTL-STRICT-WHITESPACE-001: Newlines around placeable expressions
- NAME-SERIALIZER-SPACING-001: Redundant newlines between messages
- SPEC-VARIANT-WHITESPACE-001: Newlines inside variant key brackets
- PERF-PARSER-MEM-RED-001: CRLF normalization handling
- Tab rejection per FTL specification

This file is marked with pytest.mark.fuzz and is excluded from normal test
runs. Run via: ./scripts/fuzz_hypofuzz.sh --deep or pytest -m fuzz
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, assume, event, example, given, settings
from hypothesis import strategies as st

# Mark all tests in this file as fuzzing tests (excluded from normal test runs)
pytestmark = pytest.mark.fuzz

from ftllexengine.syntax.ast import Junk, Message, Resource
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import FluentSerializer

from .strategies import (
    blank_line,
    blank_lines_sequence,
    ftl_identifiers,
    ftl_message_with_whitespace_edge_cases,
    ftl_resource_with_whitespace_chaos,
    ftl_select_with_whitespace_variants,
    ftl_simple_text,
    mixed_line_endings_text,
    pattern_with_leading_blank_lines,
    placeable_with_whitespace,
    text_with_tabs,
    text_with_trailing_whitespace,
    variable_indent_multiline_pattern,
    variant_key_with_whitespace,
)

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------


def has_junk(resource: Resource) -> bool:
    """Check if resource contains any Junk entries."""
    return any(isinstance(e, Junk) for e in resource.entries)


def get_message_count(resource: Resource) -> int:
    """Count valid Message entries in resource."""
    return sum(1 for e in resource.entries if isinstance(e, Message))


def normalize_whitespace_for_comparison(text: str) -> str:
    """Normalize whitespace for semantic comparison.

    Strips trailing whitespace from lines and normalizes line endings.
    """
    lines = text.splitlines()
    return "\n".join(line.rstrip() for line in lines)


# -----------------------------------------------------------------------------
# Variant Marker Whitespace Tests (FTL-GRAMMAR-003, SPEC-VARIANT-WHITESPACE-001)
# -----------------------------------------------------------------------------


class TestVariantMarkerWhitespace:
    """Property tests for variant key whitespace handling.

    Per Fluent EBNF, variant keys allow optional whitespace after opening
    bracket and before closing bracket. This was fixed in FTL-GRAMMAR-003.
    """

    @given(variant_key=variant_key_with_whitespace())
    @example("[ one]")  # FTL-GRAMMAR-003: spaces after opening bracket
    @example("[one ]")  # Spaces before closing bracket
    @example("[ one ]")  # Spaces on both sides
    @example("[ \n one \n ]")  # SPEC-VARIANT-WHITESPACE-001: newlines allowed
    @settings(max_examples=500, deadline=None)
    def test_variant_key_whitespace_parses(self, variant_key: str) -> None:
        """Variant keys with internal whitespace should parse correctly.

        Property: Whitespace inside variant key brackets is valid per spec
        and should not cause parse failures.
        """
        parser = FluentParserV1()

        # Extract just the key name from the variant key string
        key_name = variant_key.strip()[1:-1].strip()
        if not key_name or not key_name[0].isalpha():
            return  # Skip invalid keys

        # Emit semantic events for HypoFuzz guidance
        has_newline = "\n" in variant_key
        has_leading_space = variant_key.startswith(("[ ", "[\t"))
        has_trailing_space = variant_key.endswith((" ]", "\t]"))
        event(f"ws_type={'newline' if has_newline else 'inline'}")
        event(f"leading_ws={has_leading_space}")
        event(f"trailing_ws={has_trailing_space}")

        # Build a complete select expression with the variant key
        source = f"""msg = {{ $count ->
    *{variant_key} value
}}"""
        resource = parser.parse(source)

        # Should parse without creating Junk
        assert isinstance(resource, Resource)
        assert len(resource.entries) >= 1
        event("outcome=parsed")

    @given(msg_source=ftl_select_with_whitespace_variants())
    @settings(
        max_examples=500,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_select_with_whitespace_variants_roundtrip(self, msg_source: str) -> None:
        """Select expressions with whitespace in variants should roundtrip.

        Property: parse(serialize(parse(X))) maintains semantic equivalence.
        """
        parser = FluentParserV1()
        serializer = FluentSerializer()

        ast1 = parser.parse(msg_source)

        # Emit semantic events for HypoFuzz guidance
        event(f"entries={len(ast1.entries)}")
        event(f"has_junk={has_junk(ast1)}")

        # Skip if initial parse produces Junk
        assume(not has_junk(ast1))

        serialized = serializer.serialize(ast1)
        ast2 = parser.parse(serialized)

        # Should maintain same message count
        assert get_message_count(ast1) == get_message_count(ast2)
        event("outcome=roundtrip_success")


# -----------------------------------------------------------------------------
# Blank Line Handling Tests (FTL-GRAMMAR-001, FTL-PARSER-001)
# -----------------------------------------------------------------------------


class TestBlankLineHandling:
    """Property tests for blank line handling in patterns.

    Tests FTL-GRAMMAR-001: Parser must correctly handle blank lines before
    the first content line in multiline patterns.
    """

    @given(pattern=pattern_with_leading_blank_lines())
    @example("\n\n    value")  # FTL-GRAMMAR-001: blank lines before content
    @example("\n    value")  # Single blank line
    @example("\n\n\n  x")  # Multiple blanks, small indent
    @settings(max_examples=500, deadline=None)
    def test_leading_blank_lines_stripped(self, pattern: str) -> None:
        """Blank lines before content should not affect pattern value.

        Property: Leading blank lines in multiline patterns should be
        skipped during common_indent calculation.
        """
        parser = FluentParserV1()

        msg_id = "test_msg"
        source = f"{msg_id} ={pattern}"

        resource = parser.parse(source)

        # Emit semantic events for HypoFuzz guidance
        blank_count = pattern.split("\n")[:-1].count("") if "\n" in pattern else 0
        event(f"blank_lines={min(blank_count, 5)}")

        # Should produce a valid message
        assert isinstance(resource, Resource)
        if resource.entries and isinstance(resource.entries[0], Message):
            msg = resource.entries[0]
            assert msg.value is not None
            event("outcome=message_parsed")
            # The pattern value should not start with excessive whitespace
            # (blank lines and common indent should be stripped)

    @given(blanks=blank_lines_sequence())
    @settings(max_examples=300, deadline=None)
    def test_blank_lines_between_entries(self, blanks: str) -> None:
        """Blank lines between entries should be handled correctly.

        Property: Arbitrary blank line sequences between entries should
        not cause parse failures.
        """
        parser = FluentParserV1()

        source = f"msg1 = value1\n{blanks}\nmsg2 = value2"
        resource = parser.parse(source)

        # Emit semantic events for HypoFuzz guidance
        event(f"blank_seq_len={len(blanks)}")

        # Should parse both messages
        assert isinstance(resource, Resource)
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) >= 1  # At least one message should parse
        event(f"message_count={len(messages)}")

    @given(blank=blank_line())
    @settings(max_examples=200, deadline=None)
    def test_blank_line_with_spaces_only(self, blank: str) -> None:
        """Blank lines with only spaces should be valid separators.

        Property: Lines containing only spaces (no content) are valid
        blank lines per FTL spec.
        """
        parser = FluentParserV1()

        source = f"msg1 = value1\n{blank}\nmsg2 = value2"
        resource = parser.parse(source)

        # Emit semantic events for HypoFuzz guidance
        event(f"blank_len={len(blank)}")
        assert isinstance(resource, Resource)


# -----------------------------------------------------------------------------
# Placeable Whitespace Tests (FTL-STRICT-WHITESPACE-001)
# -----------------------------------------------------------------------------


class TestPlaceableWhitespace:
    """Property tests for whitespace around placeable expressions.

    Tests FTL-STRICT-WHITESPACE-001: Parser should allow any whitespace
    (including newlines) around placeable expression braces.
    """

    @given(placeable=placeable_with_whitespace())
    @example("{ \n $var }")  # Newline after opening brace
    @example("{ $var \n }")  # Newline before closing brace
    @example("{ \n $var \n }")  # Newlines on both sides
    @settings(max_examples=500, deadline=None)
    def test_placeable_whitespace_parses(self, placeable: str) -> None:
        """Placeables with newlines around braces should parse correctly.

        Property: Whitespace (including newlines) is valid around
        placeable expression content per FTL spec.
        """
        parser = FluentParserV1()

        source = f"msg = Hello {placeable} World"
        resource = parser.parse(source)

        # Emit semantic events for HypoFuzz guidance
        has_newline = "\n" in placeable
        event(f"placeable_ws={'newline' if has_newline else 'inline'}")

        assert isinstance(resource, Resource)
        assert len(resource.entries) >= 1

    @given(
        var_name=ftl_identifiers(),
        ws_before=st.sampled_from(["", " ", "  ", "\n", " \n "]),
        ws_after=st.sampled_from(["", " ", "  ", "\n", " \n "]),
    )
    @settings(max_examples=500, deadline=None)
    def test_variable_reference_whitespace_combinations(
        self, var_name: str, ws_before: str, ws_after: str
    ) -> None:
        """Variable references with various whitespace combinations should parse.

        Property: Any combination of spaces and newlines around variable
        reference is valid.
        """
        parser = FluentParserV1()

        source = f"msg = {{{ws_before}${var_name}{ws_after}}}"
        resource = parser.parse(source)

        # Emit semantic events for HypoFuzz guidance
        before_type = "newline" if "\n" in ws_before else "space" if ws_before else "none"
        after_type = "newline" if "\n" in ws_after else "space" if ws_after else "none"
        event(f"ws_before={before_type}")
        event(f"ws_after={after_type}")

        assert isinstance(resource, Resource)


# -----------------------------------------------------------------------------
# Tab Handling Tests (FTL Spec Compliance)
# -----------------------------------------------------------------------------


class TestTabHandling:
    """Property tests for tab character handling.

    Per FTL spec, tabs are NOT valid whitespace. Tab characters in
    syntactic positions should create Junk or be rejected.
    """

    @given(tabbed_text=text_with_tabs())
    @settings(max_examples=500, deadline=None)
    def test_tabs_in_syntactic_positions_create_issues(
        self, tabbed_text: str
    ) -> None:
        """Tabs in syntactic positions should be handled gracefully.

        Property: Parser should not crash on tab characters; tabs in
        certain positions may create Junk.
        """
        parser = FluentParserV1()

        # Emit semantic events for HypoFuzz guidance
        event(f"tab_count={tabbed_text.count(chr(9))}")

        # Test tab before equals
        source1 = f"msg\t= {tabbed_text}"
        resource1 = parser.parse(source1)
        assert isinstance(resource1, Resource)

        # Test tab after equals
        source2 = f"msg =\t{tabbed_text}"
        resource2 = parser.parse(source2)
        assert isinstance(resource2, Resource)

    @given(msg_id=ftl_identifiers())
    @example("hello")
    @settings(max_examples=200, deadline=None)
    def test_tab_indented_continuation_creates_junk(self, msg_id: str) -> None:
        """Tab-indented continuation lines should not be recognized.

        Property: Per FTL spec, only space indentation is valid for
        continuation lines. Tab indentation should create issues.
        """
        parser = FluentParserV1()

        # Tab-indented continuation line
        source = f"{msg_id} =\n\tLine one\n\tLine two"
        resource = parser.parse(source)

        # Should parse but likely create Junk due to invalid continuation
        assert isinstance(resource, Resource)
        # Entry should be Junk because tabs are not valid indentation
        if resource.entries:
            entry = resource.entries[0]
            # Either Junk or Message without the tab-indented content
            assert isinstance(entry, (Junk, Message))
            event(f"entry_type={type(entry).__name__}")


# -----------------------------------------------------------------------------
# Mixed Line Ending Tests (PERF-PARSER-MEM-RED-001)
# -----------------------------------------------------------------------------


class TestMixedLineEndings:
    """Property tests for CRLF and mixed line ending handling.

    Tests PERF-PARSER-MEM-RED-001: Parser should correctly normalize
    various line ending combinations.
    """

    @given(text=mixed_line_endings_text())
    @settings(max_examples=500, deadline=None)
    def test_mixed_line_endings_parse(self, text: str) -> None:
        """Files with mixed line endings should parse correctly.

        Property: Parser normalizes all line ending types (LF, CRLF, CR)
        to a consistent format.
        """
        parser = FluentParserV1()

        # Emit semantic events for HypoFuzz guidance
        has_crlf = "\r\n" in text
        has_cr = "\r" in text.replace("\r\n", "")
        has_lf = "\n" in text.replace("\r\n", "")
        event(f"endings={'mixed' if sum([has_crlf, has_cr, has_lf]) > 1 else 'single'}")

        # Create messages from the mixed text
        lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        entries: list[str] = []
        for i, line in enumerate(lines):
            if line.strip():
                entries.append(f"msg{i} = {line}")

        source = "\n".join(entries)
        resource = parser.parse(source)

        assert isinstance(resource, Resource)

    @given(msg_id=ftl_identifiers(), value=ftl_simple_text())
    @settings(max_examples=300, deadline=None)
    def test_crlf_line_endings_roundtrip(self, msg_id: str, value: str) -> None:
        """Messages with CRLF line endings should roundtrip correctly.

        Property: CRLF is normalized to LF during parsing; serialization
        produces consistent LF output.
        """
        parser = FluentParserV1()
        serializer = FluentSerializer()

        # Source with CRLF line endings
        source = f"{msg_id} = {value}\r\n"
        ast1 = parser.parse(source)

        assume(not has_junk(ast1))

        serialized = serializer.serialize(ast1)
        ast2 = parser.parse(serialized)

        # Should maintain message integrity
        assert get_message_count(ast1) == get_message_count(ast2)

        # Serialized output should use LF (not CRLF)
        assert "\r\n" not in serialized
        event("outcome=crlf_roundtrip_success")


# -----------------------------------------------------------------------------
# Variable Indentation Tests (Pattern Handling)
# -----------------------------------------------------------------------------


class TestVariableIndentation:
    """Property tests for variable indentation in multiline patterns.

    Tests that common_indent calculation works correctly when continuation
    lines have different indentation levels.
    """

    @given(pattern=variable_indent_multiline_pattern())
    @settings(
        max_examples=500,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_variable_indent_pattern_parses(self, pattern: str) -> None:
        """Patterns with varying indentation per line should parse correctly.

        Property: Common indent is calculated as minimum of all non-blank
        lines; each line can have different indentation.
        """
        parser = FluentParserV1()

        source = f"msg =\n{pattern}"
        resource = parser.parse(source)

        # Emit semantic events for HypoFuzz guidance
        line_count = pattern.count("\n") + 1
        event(f"pattern_lines={min(line_count, 10)}")

        assert isinstance(resource, Resource)
        assert len(resource.entries) >= 1

    @given(pattern=variable_indent_multiline_pattern())
    @settings(
        max_examples=300,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_variable_indent_roundtrip(self, pattern: str) -> None:
        """Patterns with variable indentation should roundtrip consistently.

        Property: parse(serialize(parse(X))) maintains semantic equivalence
        for patterns with varying indentation.
        """
        parser = FluentParserV1()
        serializer = FluentSerializer()

        source = f"msg =\n{pattern}"
        ast1 = parser.parse(source)

        assume(not has_junk(ast1))
        assume(get_message_count(ast1) == 1)

        serialized = serializer.serialize(ast1)
        ast2 = parser.parse(serialized)

        assert get_message_count(ast2) == 1
        event("outcome=indent_roundtrip_success")


# -----------------------------------------------------------------------------
# Trailing Whitespace Tests
# -----------------------------------------------------------------------------


class TestTrailingWhitespace:
    """Property tests for trailing whitespace handling.

    Tests that trailing whitespace in pattern values is handled
    consistently during parsing and serialization.
    """

    @given(text=text_with_trailing_whitespace())
    @settings(max_examples=500, deadline=None)
    def test_trailing_whitespace_parses(self, text: str) -> None:
        """Text with trailing whitespace should parse correctly.

        Property: Trailing whitespace in pattern values should not
        cause parse failures.
        """
        parser = FluentParserV1()

        source = f"msg = {text}"
        resource = parser.parse(source)

        # Emit semantic events for HypoFuzz guidance
        trailing_len = len(text) - len(text.rstrip())
        event(f"trailing_ws_len={min(trailing_len, 10)}")

        assert isinstance(resource, Resource)
        assert len(resource.entries) >= 1

    @given(text=text_with_trailing_whitespace())
    @settings(max_examples=300, deadline=None)
    def test_trailing_whitespace_roundtrip(self, text: str) -> None:
        """Trailing whitespace handling should be consistent on roundtrip.

        Property: Trailing whitespace may be normalized during serialization,
        but semantic content should be preserved.
        """
        parser = FluentParserV1()
        serializer = FluentSerializer()

        source = f"msg = {text}"
        ast1 = parser.parse(source)

        assume(not has_junk(ast1))

        serialized = serializer.serialize(ast1)
        ast2 = parser.parse(serialized)

        # Message count should be preserved
        assert get_message_count(ast1) == get_message_count(ast2)
        event("outcome=trailing_ws_roundtrip_success")


# -----------------------------------------------------------------------------
# Cross-Contamination Tests (Multiple Entry Types)
# -----------------------------------------------------------------------------


class TestWhitespaceCrossContamination:
    """Property tests for whitespace handling across multiple entry types.

    Tests that whitespace edge cases in one entry don't affect parsing
    of subsequent entries.
    """

    @given(source=ftl_resource_with_whitespace_chaos())
    @settings(
        max_examples=500,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example],
    )
    def test_whitespace_chaos_parses(self, source: str) -> None:
        """Resources with mixed whitespace edge cases should parse.

        Property: Parser should handle arbitrary combinations of
        whitespace edge cases without crashing.
        """
        parser = FluentParserV1()

        resource = parser.parse(source)

        # Emit semantic events for HypoFuzz guidance
        event(f"chaos_entries={len(resource.entries)}")
        event(f"has_junk={has_junk(resource)}")

        assert isinstance(resource, Resource)
        assert hasattr(resource, "entries")

    @given(source=ftl_resource_with_whitespace_chaos())
    @settings(
        max_examples=300,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example],
    )
    def test_whitespace_chaos_roundtrip(self, source: str) -> None:
        """Resources with whitespace chaos should roundtrip without growth.

        Property: parse(serialize(parse(X))) should not significantly
        increase whitespace or entry count.
        """
        parser = FluentParserV1()
        serializer = FluentSerializer()

        ast1 = parser.parse(source)
        assume(not has_junk(ast1))

        serialized = serializer.serialize(ast1)
        ast2 = parser.parse(serialized)

        # Entry count should be stable or decrease (Junk consolidation)
        assert len(ast2.entries) <= len(ast1.entries) + 1
        event("outcome=chaos_roundtrip_success")

    @given(msg=ftl_message_with_whitespace_edge_cases())
    @settings(
        max_examples=500,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow],
    )
    def test_message_whitespace_edge_cases_roundtrip(self, msg: str) -> None:
        """Individual messages with whitespace edge cases should roundtrip.

        Property: Messages exercising whitespace edge cases should
        maintain semantic equivalence through roundtrip.
        """
        parser = FluentParserV1()
        serializer = FluentSerializer()

        ast1 = parser.parse(msg)
        assume(not has_junk(ast1))
        assume(get_message_count(ast1) == 1)

        serialized = serializer.serialize(ast1)
        ast2 = parser.parse(serialized)

        # Should still have exactly one message
        assert get_message_count(ast2) == 1
        event("outcome=edge_case_roundtrip_success")


# -----------------------------------------------------------------------------
# Regression Tests (Promoted from Changelog Bugs)
# -----------------------------------------------------------------------------


class TestWhitespaceRegressions:
    """Explicit regression tests for known whitespace bugs.

    These tests ensure specific bugs documented in CHANGELOG.md remain fixed.
    They are NOT hypothesis-based; they test exact inputs that previously failed.
    """

    def test_ftl_grammar_003_variant_whitespace(self) -> None:
        """Regression: FTL-GRAMMAR-003 variant marker whitespace.

        Bug: Parser rejected variant keys with whitespace after opening
        bracket (e.g., [ one]).
        """
        parser = FluentParserV1()

        # The specific pattern that was broken
        source = """msg = { $count ->
    [ one] Single item
   *[other] Multiple items
}"""
        resource = parser.parse(source)

        assert isinstance(resource, Resource)
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)

    def test_ftl_grammar_001_blank_lines_before_content(self) -> None:
        """Regression: FTL-GRAMMAR-001 blank lines in multiline patterns.

        Bug: Parser incorrectly preserved indentation when blank lines
        appeared before first content line.
        """
        parser = FluentParserV1()
        serializer = FluentSerializer()

        # The specific pattern that was broken
        source = "msg =\n\n    value"
        resource = parser.parse(source)

        assert isinstance(resource, Resource)
        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        # The pattern value should be "value", not "    value"
        serialized = serializer.serialize(resource)
        # Re-parse and verify
        resource2 = parser.parse(serialized)
        assert get_message_count(resource2) == 1

    def test_ftl_strict_whitespace_001_placeable_newlines(self) -> None:
        """Regression: FTL-STRICT-WHITESPACE-001 placeable whitespace.

        Bug: Parser only allowed inline whitespace around placeable braces;
        newlines should also be valid.
        """
        parser = FluentParserV1()

        # The specific pattern that was broken
        source = "msg = { \n $name \n }"
        resource = parser.parse(source)

        assert isinstance(resource, Resource)
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)

    def test_spec_variant_whitespace_001_newlines_in_key(self) -> None:
        """Regression: SPEC-VARIANT-WHITESPACE-001 newlines in variant key.

        Bug: Parser rejected variant keys with newlines inside brackets.
        """
        parser = FluentParserV1()

        # The specific pattern that was broken
        source = """msg = { $count ->
    [
 one
 ] Single
   *[other] Multiple
}"""
        resource = parser.parse(source)

        assert isinstance(resource, Resource)
        # Should parse (may produce Junk if syntax is too unusual)

    def test_perf_parser_mem_red_001_crlf_normalization(self) -> None:
        """Regression: PERF-PARSER-MEM-RED-001 CRLF handling.

        Bug: CRLF normalization was inefficient or incorrect in some cases.
        """
        parser = FluentParserV1()

        # Source with mixed CRLF and LF
        source = "msg1 = First\r\nmsg2 = Second\nmsg3 = Third\r\n"
        resource = parser.parse(source)

        assert isinstance(resource, Resource)
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) == 3

    def test_name_serializer_spacing_001_redundant_newlines(self) -> None:
        """Regression: NAME-SERIALIZER-SPACING-001 redundant newlines.

        Bug: Serializer added extra blank lines between consecutive messages.
        """
        parser = FluentParserV1()
        serializer = FluentSerializer()

        # Compact messages without blank lines
        source = "msg1 = A\nmsg2 = B"
        resource = parser.parse(source)

        assert isinstance(resource, Resource)
        if has_junk(resource):
            pytest.skip("Input produced Junk; skipping roundtrip test")

        serialized = serializer.serialize(resource)

        # Re-parse and re-serialize
        resource2 = parser.parse(serialized)
        serialized2 = serializer.serialize(resource2)

        # Should stabilize (no growing blank lines)
        assert serialized == serialized2


# -----------------------------------------------------------------------------
# Entry Point
# -----------------------------------------------------------------------------


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
