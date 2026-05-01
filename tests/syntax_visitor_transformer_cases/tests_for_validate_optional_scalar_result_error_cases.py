# mypy: ignore-errors
"""Split test cases from tests/test_syntax_visitor_transformer.py."""

from tests.syntax_visitor_transformer_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# TESTS FOR _validate_optional_scalar_result ERROR CASES
# ============================================================================


class TestValidateOptionalScalarResultErrors:
    """Test error cases in _validate_optional_scalar_result (lines 360-366)."""

    def test_list_for_optional_message_value_raises_typeerror(self) -> None:
        """Returning list for Message.value (optional) raises TypeError (lines 360-366)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="Hello"),)),
            attributes=(),
        )

        transformer = ListReturningTransformer("Pattern")

        with pytest.raises(TypeError) as exc_info:
            transformer.visit(msg)

        error_msg = str(exc_info.value)
        assert (
            "Cannot assign list to optional scalar field 'Message.value'" in error_msg
        )
        assert "Scalar fields require a single ASTNode or None" in error_msg
        assert "Got 2 nodes:" in error_msg

    def test_list_for_optional_message_reference_attribute_raises_typeerror(
        self,
    ) -> None:
        """Returning list for MessageReference.attribute raises TypeError (lines 360-366)."""
        msg_ref = MessageReference(
            id=Identifier(name="button"), attribute=Identifier(name="tooltip")
        )

        transformer = ListReturningTransformer("Identifier")

        # The error will occur when visiting the attribute field
        with pytest.raises(TypeError) as exc_info:
            transformer.visit(msg_ref)

        error_msg = str(exc_info.value)
        # Could be Message.id or MessageReference.attribute depending on traversal order
        assert "Cannot assign list to" in error_msg
        assert "scalar field" in error_msg
