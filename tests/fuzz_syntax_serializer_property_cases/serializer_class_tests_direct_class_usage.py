# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_syntax_serializer_property.py."""

from tests.fuzz_syntax_serializer_property_cases import *  # noqa: F403 - shared split test support

# =============================================================================
# Serializer Class Tests (Direct Class Usage)
# =============================================================================


class TestFluentSerializerClass:
    """Test FluentSerializer class directly (not just convenience function)."""

    @given(resource=ftl_resources())
    def test_serializer_instance_reusable(self, resource: Resource) -> None:
        """PROPERTY: FluentSerializer instances are reusable (thread-safe).

        Events emitted:
        - serializer=reused: Reuse tracking
        """
        event("serializer=reused")

        serializer = FluentSerializer()

        # Use same instance twice
        result1 = serializer.serialize(resource, validate=True)
        result2 = serializer.serialize(resource, validate=True)

        # Should produce identical results (no state mutation)
        assert result1 == result2

    @given(message=ftl_message_nodes())
    def test_serializer_matches_convenience_function(self, message: Message) -> None:
        """PROPERTY: FluentSerializer.serialize() == serialize().

        Events emitted:
        - serializer=class_vs_function: Comparison tracking
        """
        event("serializer=class_vs_function")

        resource = Resource(entries=(message,))

        serializer = FluentSerializer()
        class_result = serializer.serialize(resource, validate=True)
        func_result = serialize(resource, validate=True)

        assert class_result == func_result
