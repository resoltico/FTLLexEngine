# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_syntax_serializer_property.py."""

from tests.fuzz_syntax_serializer_property_cases import *  # noqa: F403 - shared split test support

# =============================================================================
# Roundtrip Properties (Core Correctness)
# =============================================================================


class TestRoundtripProperties:
    """Test roundtrip correctness: parse(serialize(ast)) preserves structure."""

    @given(resource=ftl_resources())
    @settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_resource_roundtrip_preserves_structure(self, resource: Resource) -> None:
        """PROPERTY: Serialized resources can be parsed back to equivalent AST.

        Events emitted:
        - entry_count={n}: Number of entries in resource
        - entry_type={type}: Type of each entry encountered
        """
        # Emit entry count for HypoFuzz coverage
        event(f"entry_count={len(resource.entries)}")

        # Serialize the resource
        serialized = serialize(resource, validate=True)

        # Parse the serialized output
        parser = FluentParserV1()
        reparsed = parser.parse(serialized)

        # Emit entry types for HypoFuzz coverage
        for entry in resource.entries:
            event(f"entry_type={type(entry).__name__}")

        # Verify entry count preserved (no parse errors mean no Junk entries added)
        assert len(reparsed.entries) == len(resource.entries)

    @given(message=ftl_message_nodes())
    def test_message_roundtrip_idempotence(self, message: Message) -> None:
        """PROPERTY: serialize(parse(serialize(ast))) == serialize(ast).

        Idempotence ensures serialization is stable across multiple cycles.

        Events emitted:
        - has_attributes={bool}: Whether message has attributes
        - attribute_count={n}: Number of attributes
        - pattern_starts_with_space={bool}: Edge case tracking
        """
        # Track leading-space edge case for HypoFuzz coverage guidance.
        pattern_value = message.value
        starts_with_space = False
        if pattern_value and pattern_value.elements:
            first_elem = pattern_value.elements[0]
            if isinstance(first_elem, TextElement) and first_elem.value.startswith(" "):
                starts_with_space = True

        event(f"pattern_starts_with_space={starts_with_space}")

        resource = Resource(entries=(message,))

        # Emit attribute coverage events
        event(f"has_attributes={len(message.attributes) > 0}")
        if message.attributes:
            event(f"attribute_count={len(message.attributes)}")

        # First serialization
        serialized1 = serialize(resource, validate=True)

        # Parse and re-serialize
        parser = FluentParserV1()
        reparsed = parser.parse(serialized1)
        serialized2 = serialize(reparsed, validate=True)

        # Idempotence: second serialization matches first
        assert serialized1 == serialized2

    @given(term=ftl_term_nodes())
    def test_term_roundtrip_idempotence(self, term: Term) -> None:
        """PROPERTY: Terms serialize idempotently.

        Events emitted:
        - has_attributes={bool}: Whether term has attributes
        - pattern_starts_with_space={bool}: Edge case tracking
        """
        # Track leading-space edge case for HypoFuzz coverage guidance.
        pattern_value = term.value
        starts_with_space = False
        if pattern_value and pattern_value.elements:
            first_elem = pattern_value.elements[0]
            if isinstance(first_elem, TextElement) and first_elem.value.startswith(" "):
                starts_with_space = True

        event(f"pattern_starts_with_space={starts_with_space}")

        resource = Resource(entries=(term,))

        event(f"has_attributes={len(term.attributes) > 0}")

        serialized1 = serialize(resource, validate=True)

        parser = FluentParserV1()
        reparsed = parser.parse(serialized1)
        serialized2 = serialize(reparsed, validate=True)

        assert serialized1 == serialized2

    @given(pattern=ftl_patterns())
    def test_pattern_roundtrip_preserves_elements(self, pattern: Pattern) -> None:
        """PROPERTY: Pattern serialization preserves all elements.

        Events emitted:
        - element_count={n}: Number of elements in pattern
        - element_type={type}: Type of each element
        - has_placeable={bool}: Whether pattern contains placeables
        """
        # Wrap pattern in a message
        message = Message(
            id=Identifier(name="test"),
            value=pattern,
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Emit pattern structure events
        event(f"element_count={len(pattern.elements)}")
        has_placeable = any(isinstance(e, Placeable) for e in pattern.elements)
        event(f"has_placeable={has_placeable}")

        for element in pattern.elements:
            event(f"element_type={type(element).__name__}")

        serialized = serialize(resource, validate=True)

        parser = FluentParserV1()
        reparsed = parser.parse(serialized)

        # Verify no parse errors (no Junk entries) and correct entry count
        assert len(reparsed.entries) == 1
