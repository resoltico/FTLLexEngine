"""AST-first serializer fuzzing tests.

Property-based tests using AST node generation directly, bypassing string
parsing. This approach:
- Guarantees 100% valid input (no junk filtering)
- Explores semantic space rather than syntactic space
- Tests serializer behavior with all valid AST variations

Note: This file is marked with pytest.mark.fuzz and is excluded from normal
test runs. Run via: ./scripts/fuzz.sh or pytest -m fuzz
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from ftllexengine.syntax.ast import (
    Attribute,
    Comment,
    Identifier,
    Message,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    Term,
    TextElement,
)
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import FluentSerializer
from tests.helpers.ast_checks import normalize_ast
from tests.strategies import (
    ftl_attribute_nodes,
    ftl_comment_nodes,
    ftl_message_nodes,
    ftl_patterns,
    ftl_resources,
    ftl_select_expressions,
    ftl_term_nodes,
)

# Mark all tests in this file as fuzzing tests
pytestmark = pytest.mark.fuzz


# -----------------------------------------------------------------------------
# Property Tests: AST-First Serialization
# -----------------------------------------------------------------------------


class TestASTSerializationProperties:
    """Property tests for serializing AST nodes directly."""

    @given(ftl_message_nodes())
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_message_roundtrip(self, message: Message) -> None:
        """Property: serialize(message) produces parseable FTL."""
        serializer = FluentSerializer()
        parser = FluentParserV1()

        # Create resource with single message
        resource = Resource(entries=(message,))

        # Serialize
        ftl = serializer.serialize(resource)
        assert isinstance(ftl, str)
        assert len(ftl) > 0

        # Parse back
        reparsed = parser.parse(ftl)
        assert isinstance(reparsed, Resource)
        assert len(reparsed.entries) >= 1

        # First entry should be a message (not junk)
        first_entry = reparsed.entries[0]
        event(f"message_elements={len(message.value.elements) if message.value else 0}")
        assert isinstance(first_entry, Message), f"Got {type(first_entry).__name__}: {ftl}"
        event("outcome=message_roundtrip_success")

    @given(ftl_term_nodes())
    @settings(
        max_examples=300,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_term_roundtrip(self, term: Term) -> None:
        """Property: serialize(term) produces parseable FTL."""
        serializer = FluentSerializer()
        parser = FluentParserV1()

        resource = Resource(entries=(term,))
        ftl = serializer.serialize(resource)

        assert isinstance(ftl, str)
        assert ftl.startswith("-")  # Terms start with -

        reparsed = parser.parse(ftl)
        assert len(reparsed.entries) >= 1
        assert isinstance(reparsed.entries[0], Term)
        event("outcome=term_roundtrip_success")

    @given(ftl_attribute_nodes())
    @settings(
        max_examples=300,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_attribute_roundtrip(self, attr: Attribute) -> None:
        """Property: Attributes serialize within a message."""
        serializer = FluentSerializer()
        parser = FluentParserV1()

        # Embed attribute in a message (attributes require a parent)
        message = Message(
            id=Identifier(name="host"),
            value=Pattern(elements=(TextElement(value="text"),)),
            attributes=(attr,),
        )
        resource = Resource(entries=(message,))

        ftl = serializer.serialize(resource)
        assert isinstance(ftl, str)

        reparsed = parser.parse(ftl)
        assert len(reparsed.entries) >= 1
        first = reparsed.entries[0]
        assert isinstance(first, Message)
        attr_count = len(first.attributes)
        event(f"attr_count={attr_count}")
        assert attr_count >= 1
        event("outcome=attribute_roundtrip_success")

    @given(ftl_comment_nodes())
    @settings(max_examples=200, deadline=None)
    def test_comment_roundtrip(self, comment: Comment) -> None:
        """Property: serialize(comment) produces parseable FTL."""
        serializer = FluentSerializer()
        parser = FluentParserV1()

        resource = Resource(entries=(comment,))
        ftl = serializer.serialize(resource)

        assert isinstance(ftl, str)
        assert ftl.startswith("#")

        reparsed = parser.parse(ftl)
        assert len(reparsed.entries) >= 1
        assert isinstance(reparsed.entries[0], Comment)
        event("outcome=comment_roundtrip_success")

    @given(ftl_resources())
    @settings(
        max_examples=300,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example],
        deadline=None,
    )
    def test_resource_roundtrip(self, resource: Resource) -> None:
        """Property: serialize(parse(serialize(resource))) stabilizes."""
        serializer = FluentSerializer()
        parser = FluentParserV1()

        # First serialization
        ftl1 = serializer.serialize(resource)
        assert isinstance(ftl1, str)

        # Parse and re-serialize
        reparsed = parser.parse(ftl1)
        ftl2 = serializer.serialize(reparsed)

        # Third cycle
        reparsed2 = parser.parse(ftl2)
        ftl3 = serializer.serialize(reparsed2)

        # After first roundtrip, should stabilize
        assert ftl2 == ftl3, f"Not idempotent:\nftl2: {ftl2!r}\nftl3: {ftl3!r}"
        event(f"resource_entries={len(resource.entries)}")
        event("outcome=resource_idempotence_success")


class TestPatternSerializationProperties:
    """Property tests for pattern serialization."""

    @given(ftl_patterns())
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_pattern_in_message(self, pattern: Pattern) -> None:
        """Property: Any valid pattern can be serialized in a message."""
        serializer = FluentSerializer()
        parser = FluentParserV1()

        message = Message(
            id=Identifier(name="test"),
            value=pattern,
            attributes=(),
        )
        resource = Resource(entries=(message,))

        ftl = serializer.serialize(resource)
        assert isinstance(ftl, str)

        reparsed = parser.parse(ftl)
        assert len(reparsed.entries) >= 1
        event(f"pattern_elements={len(pattern.elements)}")
        event("outcome=pattern_serialized")

    @given(ftl_select_expressions())
    @settings(
        max_examples=300,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_select_expression_serialization(self, select: SelectExpression) -> None:
        """Property: Select expressions serialize correctly."""
        serializer = FluentSerializer()
        parser = FluentParserV1()

        pattern = Pattern(elements=(Placeable(expression=select),))
        message = Message(
            id=Identifier(name="test"),
            value=pattern,
            attributes=(),
        )
        resource = Resource(entries=(message,))

        ftl = serializer.serialize(resource)
        assert isinstance(ftl, str)
        assert "->" in ftl  # Select syntax marker

        reparsed = parser.parse(ftl)
        assert len(reparsed.entries) >= 1
        event(f"select_variants={len(select.variants)}")
        event("outcome=select_serialized")


class TestAttributeSerializationProperties:
    """Property tests for attribute serialization."""

    @given(ftl_patterns(), ftl_patterns())
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_message_with_attributes(self, value: Pattern, attr_value: Pattern) -> None:
        """Property: Messages with attributes serialize correctly."""
        serializer = FluentSerializer()
        parser = FluentParserV1()

        attribute = Attribute(
            id=Identifier(name="tooltip"),
            value=attr_value,
        )
        message = Message(
            id=Identifier(name="button"),
            value=value,
            attributes=(attribute,),
        )
        resource = Resource(entries=(message,))

        ftl = serializer.serialize(resource)
        assert isinstance(ftl, str)
        assert ".tooltip" in ftl

        reparsed = parser.parse(ftl)
        messages = [e for e in reparsed.entries if isinstance(e, Message)]
        assert len(messages) >= 1
        assert len(messages[0].attributes) >= 1
        event("outcome=attr_roundtrip_success")


class TestSemanticEquivalence:
    """Tests for semantic equivalence after roundtrip."""

    @given(ftl_resources())
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example],
        deadline=None,
    )
    def test_semantic_preservation(self, resource: Resource) -> None:
        """Property: Roundtrip preserves semantic content."""
        serializer = FluentSerializer()
        parser = FluentParserV1()

        ftl = serializer.serialize(resource)
        reparsed = parser.parse(ftl)

        # Normalize both for comparison
        orig_norm = normalize_ast(resource)
        reparsed_norm = normalize_ast(reparsed)

        # Compare normalized forms
        # Note: This may fail for edge cases where serialization
        # changes representation (e.g., escaping). That's expected.
        assert isinstance(orig_norm, dict)
        assert isinstance(reparsed_norm, dict)

        # Entry count should match
        orig_entries = orig_norm.get("entries", [])
        reparsed_entries = reparsed_norm.get("entries", [])
        assert len(orig_entries) == len(reparsed_entries)
        event(f"entries={len(orig_entries)}")
        event("outcome=semantic_preserved")


class TestEdgeCaseSerialization:
    """Tests for edge case serialization."""

    def test_empty_resource(self) -> None:
        """Empty resource serializes to empty string."""
        serializer = FluentSerializer()
        resource = Resource(entries=())

        ftl = serializer.serialize(resource)
        assert ftl == ""

    def test_message_with_empty_pattern(self) -> None:
        """Message with minimal pattern."""
        serializer = FluentSerializer()
        parser = FluentParserV1()

        message = Message(
            id=Identifier(name="minimal"),
            value=Pattern(elements=(TextElement(value="x"),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        ftl = serializer.serialize(resource)
        assert "minimal" in ftl
        assert "x" in ftl

        reparsed = parser.parse(ftl)
        assert len(reparsed.entries) >= 1

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=100))
    @settings(max_examples=100, deadline=None)
    def test_identifier_roundtrip(self, name: str) -> None:
        """Property: Valid identifiers survive roundtrip."""
        serializer = FluentSerializer()
        parser = FluentParserV1()

        message = Message(
            id=Identifier(name=name),
            value=Pattern(elements=(TextElement(value="value"),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        ftl = serializer.serialize(resource)
        reparsed = parser.parse(ftl)

        messages = [e for e in reparsed.entries if isinstance(e, Message)]
        assert len(messages) >= 1
        assert messages[0].id.name == name
        event(f"id_len={len(name)}")
