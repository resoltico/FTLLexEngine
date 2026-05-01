# mypy: ignore-errors
"""Split test cases from tests/test_syntax_visitor_transformer.py."""

from tests.syntax_visitor_transformer_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# TESTS FOR _validate_scalar_result ERROR CASES
# ============================================================================


class TestValidateScalarResultErrors:
    """Test error cases in _validate_scalar_result (lines 318-331)."""

    def test_none_for_required_message_id_raises_typeerror(self) -> None:
        """Returning None for Message.id raises TypeError (lines 318-323)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="Hello"),)),
            attributes=(),
        )

        transformer = NoneReturningTransformer("Identifier")

        with pytest.raises(TypeError) as exc_info:
            transformer.visit(msg)

        assert "Cannot assign None to required scalar field 'Message.id'" in str(
            exc_info.value
        )
        assert "Required scalar fields must have a single ASTNode" in str(
            exc_info.value
        )

    def test_none_for_required_term_value_raises_typeerror(self) -> None:
        """Returning None for Term.value raises TypeError (lines 318-323)."""

        class NonePatternTransformer(ASTTransformer):
            def visit_Pattern(self, _node: Pattern) -> None:
                """Return None for Pattern (invalid for Term.value)."""
                return

        term = Term(
            id=Identifier(name="brand"),
            value=Pattern(elements=(TextElement(value="Firefox"),)),
            attributes=(),
        )

        transformer = NonePatternTransformer()

        with pytest.raises(TypeError) as exc_info:
            transformer.visit(term)

        assert "Cannot assign None to required scalar field 'Term.value'" in str(
            exc_info.value
        )

    def test_list_for_scalar_message_id_raises_typeerror(self) -> None:
        """Returning list for Message.id raises TypeError (lines 325-331)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="Hello"),)),
            attributes=(),
        )

        transformer = ListReturningTransformer("Identifier")

        with pytest.raises(TypeError) as exc_info:
            transformer.visit(msg)

        error_msg = str(exc_info.value)
        assert "Cannot assign list to scalar field 'Message.id'" in error_msg
        assert "Scalar fields require a single ASTNode" in error_msg
        assert "Got 2 nodes:" in error_msg
        assert "['Identifier', 'Identifier']" in error_msg

    def test_list_for_scalar_term_value_raises_typeerror(self) -> None:
        """Returning list for Term.value raises TypeError (lines 325-331)."""
        term = Term(
            id=Identifier(name="brand"),
            value=Pattern(elements=(TextElement(value="Firefox"),)),
            attributes=(),
        )

        transformer = ListReturningTransformer("Pattern")

        with pytest.raises(TypeError) as exc_info:
            transformer.visit(term)

        error_msg = str(exc_info.value)
        assert "Cannot assign list to scalar field 'Term.value'" in error_msg
        assert "Got 2 nodes:" in error_msg
        assert "['Pattern', 'Pattern']" in error_msg

    def test_list_for_scalar_placeable_expression_raises_typeerror(self) -> None:
        """Returning list for Placeable.expression raises TypeError (lines 325-331)."""

        class ListVariableRefTransformer(ASTTransformer):
            def visit_VariableReference(
                self, node: VariableReference
            ) -> list[VariableReference]:
                """Return list of VariableReferences."""
                return [node, VariableReference(id=Identifier(name="extra"))]

        placeable = Placeable(
            expression=VariableReference(id=Identifier(name="count"))
        )

        transformer = ListVariableRefTransformer()

        with pytest.raises(TypeError) as exc_info:
            transformer.visit(placeable)

        error_msg = str(exc_info.value)
        assert (
            "Cannot assign list to scalar field 'Placeable.expression'" in error_msg
        )
        assert "['VariableReference', 'VariableReference']" in error_msg
