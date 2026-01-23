"""Tests for extract_references function in introspection module.

Tests reference extraction for message and term dependency analysis.
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.introspection import extract_references
from ftllexengine.introspection.message import ReferenceExtractor
from ftllexengine.syntax.ast import Message, Term
from ftllexengine.syntax.parser import FluentParserV1

# ============================================================================
# UNIT TESTS - EXTRACT REFERENCES
# ============================================================================


class TestExtractReferencesBasic:
    """Basic unit tests for extract_references function."""

    def test_message_with_no_references(self) -> None:
        """Message without references returns empty sets."""
        parser = FluentParserV1()
        resource = parser.parse("greeting = Hello, World!")
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        msg_refs, term_refs = extract_references(msg)
        assert msg_refs == frozenset()
        assert term_refs == frozenset()

    def test_message_with_message_reference(self) -> None:
        """Message with { other } extracts message reference."""
        parser = FluentParserV1()
        resource = parser.parse("greeting = { hello }")
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        msg_refs, term_refs = extract_references(msg)
        assert msg_refs == frozenset({"hello"})
        assert term_refs == frozenset()

    def test_message_with_term_reference(self) -> None:
        """Message with { -brand } extracts term reference."""
        parser = FluentParserV1()
        resource = parser.parse("greeting = Welcome to { -brand }!")
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        msg_refs, term_refs = extract_references(msg)
        assert msg_refs == frozenset()
        assert term_refs == frozenset({"brand"})

    def test_message_with_mixed_references(self) -> None:
        """Message with both message and term references extracts both."""
        parser = FluentParserV1()
        resource = parser.parse("greeting = { hello } from { -brand }")
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        msg_refs, term_refs = extract_references(msg)
        assert msg_refs == frozenset({"hello"})
        assert term_refs == frozenset({"brand"})

    def test_message_with_multiple_message_references(self) -> None:
        """Message with multiple message references extracts all."""
        parser = FluentParserV1()
        resource = parser.parse("combo = { hello } and { goodbye }")
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        msg_refs, term_refs = extract_references(msg)
        assert msg_refs == frozenset({"hello", "goodbye"})
        assert term_refs == frozenset()

    def test_message_with_duplicate_references(self) -> None:
        """Duplicate references are deduplicated."""
        parser = FluentParserV1()
        resource = parser.parse("repeat = { hello } and { hello } again")
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        msg_refs, _ = extract_references(msg)
        assert msg_refs == frozenset({"hello"})

    def test_message_with_attribute_references(self) -> None:
        """References in attributes are extracted."""
        parser = FluentParserV1()
        ftl = """
greeting = Hi
    .tooltip = See { other }
"""
        resource = parser.parse(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        msg_refs, _ = extract_references(msg)
        assert msg_refs == frozenset({"other"})

    def test_term_with_term_reference(self) -> None:
        """Term with { -other } extracts term reference."""
        parser = FluentParserV1()
        resource = parser.parse("-brand = { -company } Product")
        term = resource.entries[0]
        assert isinstance(term, Term)

        msg_refs, term_refs = extract_references(term)
        assert msg_refs == frozenset()
        assert term_refs == frozenset({"company"})

    def test_references_in_select_expression(self) -> None:
        """References inside select expression variants are extracted."""
        parser = FluentParserV1()
        ftl = """
count = { $num ->
    [one] { singular }
   *[other] { plural }
}
"""
        resource = parser.parse(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        msg_refs, _ = extract_references(msg)
        assert msg_refs == frozenset({"singular", "plural"})


# ============================================================================
# UNIT TESTS - REFERENCE EXTRACTOR CLASS
# ============================================================================


class TestReferenceExtractorClass:
    """Tests for ReferenceExtractor visitor class."""

    def test_extractor_initial_state(self) -> None:
        """Extractor starts with empty sets."""
        extractor = ReferenceExtractor()
        assert extractor.message_refs == set()
        assert extractor.term_refs == set()

    def test_extractor_collects_message_refs(self) -> None:
        """Extractor collects message references via visit."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { other } { another }")
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        extractor = ReferenceExtractor()
        extractor.visit(msg.value)

        assert "other" in extractor.message_refs
        assert "another" in extractor.message_refs

    def test_extractor_collects_term_refs(self) -> None:
        """Extractor collects term references via visit."""
        parser = FluentParserV1()
        resource = parser.parse("msg = { -brand } { -app }")
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

        extractor = ReferenceExtractor()
        extractor.visit(msg.value)

        assert "brand" in extractor.term_refs
        assert "app" in extractor.term_refs


# ============================================================================
# PROPERTY TESTS - EXTRACT REFERENCES
# ============================================================================


# Strategy for valid identifiers
identifiers = st.from_regex(r"[a-z][a-z0-9]*", fullmatch=True)


class TestExtractReferencesProperties:
    """Property-based tests for extract_references."""

    @given(msg_id=identifiers)
    @settings(max_examples=100)
    def test_plain_message_no_references(self, msg_id: str) -> None:
        """PROPERTY: Plain text message has no references."""
        parser = FluentParserV1()
        resource = parser.parse(f"{msg_id} = Hello World")
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        msg_refs, term_refs = extract_references(msg)
        assert msg_refs == frozenset()
        assert term_refs == frozenset()

    @given(
        msg_id=identifiers,
        ref_id=identifiers,
    )
    @settings(max_examples=100)
    def test_message_ref_is_extracted(self, msg_id: str, ref_id: str) -> None:
        """PROPERTY: { ref_id } reference is extracted."""
        parser = FluentParserV1()
        resource = parser.parse(f"{msg_id} = {{ {ref_id} }}")
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        msg_refs, _ = extract_references(msg)
        assert ref_id in msg_refs

    @given(
        msg_id=identifiers,
        term_id=identifiers,
    )
    @settings(max_examples=100)
    def test_term_ref_is_extracted(self, msg_id: str, term_id: str) -> None:
        """PROPERTY: { -term_id } reference is extracted."""
        parser = FluentParserV1()
        resource = parser.parse(f"{msg_id} = {{ -{term_id} }}")
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        _, term_refs = extract_references(msg)
        assert term_id in term_refs
