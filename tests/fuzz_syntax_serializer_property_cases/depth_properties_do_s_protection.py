# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_syntax_serializer_property.py."""

from tests.fuzz_syntax_serializer_property_cases import *  # noqa: F403 - shared split test support

# =============================================================================
# Depth Properties (DoS Protection)
# =============================================================================


class TestDepthProperties:
    """Test max_depth protection against stack overflow."""

    @given(deep_placeable=ftl_deep_placeables(depth=5))
    def test_moderate_depth_succeeds(self, deep_placeable: Placeable) -> None:
        """PROPERTY: Moderately nested ASTs serialize successfully.

        Events emitted:
        - depth=moderate: Depth category
        """
        event("depth=moderate")

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(deep_placeable,)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Should succeed with default max_depth
        serialized = serialize(resource, validate=True, max_depth=MAX_DEPTH)
        assert isinstance(serialized, str)

    def test_extreme_depth_raises_depth_error(self) -> None:
        """COVERAGE: SerializationDepthError on overflow."""

        # Build deeply nested structure exceeding limit
        # Start with innermost expression
        inner_expr = VariableReference(id=Identifier(name="x"))

        # Wrap in 150 nested placeables (exceeds default MAX_DEPTH=100)
        current: Placeable | VariableReference = inner_expr
        for _ in range(150):
            current = Placeable(expression=current)

        # After loop, current is guaranteed to be Placeable
        outermost_placeable = typing.cast("Placeable", current)

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(outermost_placeable,)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        with pytest.raises(SerializationDepthError, match="depth limit exceeded"):
            serialize(resource, validate=True, max_depth=MAX_DEPTH)

    def test_custom_max_depth_respected(self) -> None:
        """COVERAGE: Custom max_depth parameter."""

        # Build structure with 10 nested placeables
        inner_expr = VariableReference(id=Identifier(name="x"))
        current: Placeable | VariableReference = inner_expr
        for _ in range(10):
            current = Placeable(expression=current)

        # After loop, current is guaranteed to be Placeable
        outermost_placeable = typing.cast("Placeable", current)

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(outermost_placeable,)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Should fail with max_depth=5
        with pytest.raises(SerializationDepthError):
            serialize(resource, validate=True, max_depth=5)

        # Should succeed with max_depth=15
        serialized = serialize(resource, validate=True, max_depth=15)
        assert isinstance(serialized, str)
