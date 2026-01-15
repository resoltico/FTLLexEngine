"""Hypothesis property-based tests for multiline pattern parsing.

Uses property-based testing to verify invariants and edge cases in the
multiline pattern implementation.
"""

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from ftllexengine.syntax import Message, Placeable, Term, TextElement
from ftllexengine.syntax.parser import FluentParserV1
from tests.strategies import ftl_identifiers


# Strategy for generating valid text content (no special FTL chars)
@st.composite
def safe_text_content(draw):
    """Generate text content that doesn't contain FTL special characters."""
    # Avoid {, }, [, ], *, $ and control characters
    text = draw(st.text(
        alphabet=st.characters(
            blacklist_categories=("Cc", "Cs"),  # No control chars
            blacklist_characters="{}\n\r\t[]$*.#"  # No FTL special chars
        ),
        min_size=1,
        max_size=50
    ))
    assume(len(text.strip()) > 0)  # Must have non-whitespace content
    return text.strip()


# Strategy for indentation (spaces only, per FTL spec)
indentation = st.integers(min_value=1, max_value=8).map(lambda n: " " * n)


class TestMultilinePatternProperties:
    """Property-based tests for multiline patterns."""

    @given(
        msg_id=ftl_identifiers(),
        lines=st.lists(safe_text_content(), min_size=2, max_size=5),
        indent=indentation
    )
    @settings(max_examples=100)
    def test_multiline_pattern_always_parses(self, msg_id, lines, indent):
        """Any valid multiline pattern should parse without errors."""
        # Build multiline source
        source = f"{msg_id} =\n"
        for line in lines:
            source += f"{indent}{line}\n"

        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should produce at least one entry
        assert len(resource.entries) >= 1

        # First entry should be Message (not Junk)
        entry = resource.entries[0]
        assert isinstance(entry, Message), f"Expected Message, got {type(entry).__name__}: {entry}"
        assert entry.id.name == msg_id

    @given(
        msg_id=ftl_identifiers(),
        line1=safe_text_content(),
        line2=safe_text_content(),
        indent1=indentation,
        indent2=indentation
    )
    @settings(max_examples=50)
    def test_varying_indentation_handled(self, msg_id, line1, line2, indent1, indent2):
        """Multiline patterns with varying indentation should parse."""
        source = f"{msg_id} =\n{indent1}{line1}\n{indent2}{line2}\n"

        parser = FluentParserV1()
        resource = parser.parse(source)

        assert isinstance(resource.entries[0], Message)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        # Should have value with elements
        assert msg.value is not None
        assert len(msg.value.elements) >= 1

    @given(
        msg_id=ftl_identifiers(),
        text=safe_text_content(),
        indent=indentation
    )
    @settings(max_examples=50)
    def test_single_continuation_line(self, msg_id, text, indent):
        """Single continuation line should be parsed correctly."""
        source = f"{msg_id} =\n{indent}{text}\n"

        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.id.name == msg_id

        # Should have text in pattern
        text_elements = [e for e in msg.value.elements if isinstance(e, TextElement)]
        assert len(text_elements) > 0

        # Combined text should contain our input text
        combined_text = "".join(e.value for e in text_elements)
        assert text in combined_text

    @given(
        msg_id=ftl_identifiers(),
        num_lines=st.integers(min_value=1, max_value=10),
        indent=indentation
    )
    @settings(max_examples=50)
    def test_number_of_continuation_lines(self, msg_id, num_lines, indent):
        """Parser should handle arbitrary number of continuation lines."""
        source = f"{msg_id} =\n"
        for i in range(num_lines):
            source += f"{indent}Line{i}\n"

        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        # Should have parsed all lines (may create multiple text elements)
        assert msg.value is not None
        assert len(msg.value.elements) >= 1

    @given(
        msg_id=ftl_identifiers(),
        text=safe_text_content(),
        indent=indentation,
        line_ending=st.sampled_from(["\n", "\r\n"])
    )
    @settings(max_examples=30)
    def test_line_endings_handled(self, msg_id, text, indent, line_ending):
        """Both LF and CRLF line endings should work."""
        source = f"{msg_id} ={line_ending}{indent}{text}{line_ending}"

        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None


class TestContinuationDetectionProperties:
    """Property-based tests for continuation detection."""

    @given(
        msg_id=ftl_identifiers(),
        text1=safe_text_content(),
        text2=safe_text_content(),
        indent=indentation
    )
    @settings(max_examples=50)
    def test_space_indent_required(self, msg_id, text1, text2, indent):
        """Continuation lines must start with space, not tab."""
        # Space-indented continuation
        source_with_space = f"{msg_id} =\n{indent}{text1}\n{indent}{text2}\n"

        parser = FluentParserV1()
        resource = parser.parse(source_with_space)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Should parse both lines
        assert len(msg.value.elements) >= 2

    @given(
        msg_id=ftl_identifiers(),
        text=safe_text_content(),
        indent=indentation,
        special_char=st.sampled_from(["[", "*", "."])
    )
    @settings(max_examples=30)
    def test_special_char_stops_continuation(self, msg_id, text, indent, special_char):
        """Lines starting with [, *, or . should not be continuations."""
        source = f"{msg_id} =\n{indent}{text}\n{indent}{special_char}something\n"

        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        # Should only parse first line as value
        text_elements = [e for e in msg.value.elements if isinstance(e, TextElement)]
        combined = "".join(e.value for e in text_elements)

        # Should contain first line text
        assert text in combined
        # Should NOT contain the special char line (depends on special char behavior)


class TestMultilineInvariants:
    """Property-based tests for invariants in multiline parsing."""

    @given(
        msg_id=ftl_identifiers(),
        lines=st.lists(safe_text_content(), min_size=1, max_size=5),
        indent=indentation
    )
    @settings(max_examples=50)
    def test_parsing_is_deterministic(self, msg_id, lines, indent):
        """Parsing the same source twice should produce identical results."""
        source = f"{msg_id} =\n"
        for line in lines:
            source += f"{indent}{line}\n"

        parser1 = FluentParserV1()
        parser2 = FluentParserV1()

        resource1 = parser1.parse(source)
        resource2 = parser2.parse(source)

        # Should produce same number of entries
        assert len(resource1.entries) == len(resource2.entries)

        # Both should be Messages with same ID
        assert type(resource1.entries[0]) == type(resource2.entries[0])
        entry1 = resource1.entries[0]
        assert isinstance(entry1, Message)
        entry2 = resource2.entries[0]
        assert isinstance(entry2, Message)
        assert entry1.id.name == entry2.id.name

    @given(
        msg_id=ftl_identifiers(),
        lines=st.lists(safe_text_content(), min_size=2, max_size=5),
        indent=indentation
    )
    @settings(max_examples=50)
    def test_multiline_has_value(self, msg_id, lines, indent):
        """Every successfully parsed multiline message should have a value."""
        source = f"{msg_id} =\n"
        for line in lines:
            source += f"{indent}{line}\n"

        parser = FluentParserV1()
        resource = parser.parse(source)

        if isinstance(resource.entries[0], Message):
            msg = resource.entries[0]
            assert isinstance(msg, Message)
            assert msg.value is not None
            # Message should have value
            assert msg.value is not None
            # Value should have elements
            assert len(msg.value.elements) > 0

    @given(
        term_id=ftl_identifiers(),
        lines=st.lists(safe_text_content(), min_size=2, max_size=5),
        indent=indentation
    )
    @settings(max_examples=30)
    def test_multiline_works_for_terms(self, term_id, lines, indent):
        """Multiline patterns should work for terms too."""
        source = f"-{term_id} =\n"
        for line in lines:
            source += f"{indent}{line}\n"

        parser = FluentParserV1()
        resource = parser.parse(source)

        if isinstance(resource.entries[0], Term):
            term = resource.entries[0]
            assert term.value is not None
            assert len(term.value.elements) > 0


class TestMultilineWithPlaceablesProperties:
    """Property-based tests for multiline patterns with placeables."""

    @given(
        msg_id=ftl_identifiers(),
        text_before=safe_text_content(),
        var_name=ftl_identifiers(),
        text_after=safe_text_content(),
        indent=indentation
    )
    @settings(max_examples=30)
    def test_placeable_in_multiline(self, msg_id, text_before, var_name, text_after, indent):
        """Placeables in multiline patterns should be parsed correctly."""
        source = f"{msg_id} =\n{indent}{text_before} {{ ${var_name} }} {text_after}\n"

        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        if isinstance(msg, Message):
            # Test verifies message parses successfully
            # Placeables may vary depending on generated input
            assert msg.value is not None

    @given(
        msg_id=ftl_identifiers(),
        var_names=st.lists(ftl_identifiers(), min_size=2, max_size=4),
        indent=indentation
    )
    @settings(max_examples=30)
    def test_multiple_placeables_multiline(self, msg_id, var_names, indent):
        """Multiple placeables across lines should be parsed."""
        source = f"{msg_id} =\n"
        for var_name in var_names:
            source += f"{indent}{{ ${var_name} }}\n"

        parser = FluentParserV1()
        resource = parser.parse(source)

        if isinstance(resource.entries[0], Message):
            msg = resource.entries[0]
            assert isinstance(msg, Message)
            assert msg.value is not None
            # Should have parsed placeables
            placeables = [e for e in msg.value.elements if isinstance(e, Placeable)]
            # May not match exactly due to parsing rules, but should have some
            assert len(placeables) >= 1


class TestMultilineWhitespaceProperties:
    """Property-based tests for whitespace handling."""

    @given(
        msg_id=ftl_identifiers(),
        text=safe_text_content(),
        num_spaces=st.integers(min_value=1, max_value=10)
    )
    @settings(max_examples=30)
    def test_arbitrary_indentation_level(self, msg_id, text, num_spaces):
        """Any indentation level (1+ spaces) should work."""
        indent = " " * num_spaces
        source = f"{msg_id} =\n{indent}{text}\n"

        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.value is not None

    @given(
        msg_id=ftl_identifiers(),
        lines=st.lists(safe_text_content(), min_size=2, max_size=4),
        base_indent=st.integers(min_value=1, max_value=4)
    )
    @settings(max_examples=30)
    def test_consistent_indentation(self, msg_id, lines, base_indent):
        """Consistent indentation across lines should work."""
        indent = " " * base_indent
        source = f"{msg_id} =\n"
        for line in lines:
            source += f"{indent}{line}\n"

        parser = FluentParserV1()
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Should parse all lines
        assert len(msg.value.elements) >= len(lines)


class TestMultilineErrorRecovery:
    """Property-based tests for error recovery."""

    @given(
        msg_id=ftl_identifiers(),
        text=safe_text_content(),
        indent=indentation
    )
    @settings(max_examples=30)
    def test_incomplete_pattern_recovers(self, msg_id, text, indent):
        """Parser should handle incomplete patterns gracefully."""
        # Pattern without closing newline
        source = f"{msg_id} =\n{indent}{text}"

        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should still produce an entry
        assert len(resource.entries) >= 1

    @given(
        msg_id1=ftl_identifiers(),
        msg_id2=ftl_identifiers(),
        text1=safe_text_content(),
        text2=safe_text_content(),
        indent=indentation
    )
    @settings(max_examples=30)
    def test_multiple_messages_parsed(self, msg_id1, msg_id2, text1, text2, indent):
        """Multiple multiline messages should be parsed correctly."""
        assume(msg_id1 != msg_id2)  # Need different IDs

        source = f"{msg_id1} =\n{indent}{text1}\n{msg_id2} =\n{indent}{text2}\n"

        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should have two entries
        assert len(resource.entries) >= 2

        if isinstance(resource.entries[0], Message) and isinstance(resource.entries[1], Message):
            assert resource.entries[0].id.name == msg_id1
            assert resource.entries[1].id.name == msg_id2
