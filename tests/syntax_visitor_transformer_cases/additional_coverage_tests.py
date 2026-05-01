# mypy: ignore-errors
"""Split test cases from tests/test_syntax_visitor_transformer.py."""

from tests.syntax_visitor_transformer_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# ADDITIONAL COVERAGE TESTS
# ============================================================================


class TestAdditionalCoverage:
    """Additional tests to ensure complete coverage."""

    def test_validate_scalar_result_all_field_types(self) -> None:
        """Test _validate_scalar_result for various required scalar fields."""

        class AlwaysNoneTransformer(ASTTransformer):
            def visit_Identifier(self, _node: Identifier) -> None:
                """Always return None."""
                return

        # Test various nodes with required scalar Identifier fields
        test_cases: list[tuple[str, VariableReference | Attribute]] = [
            (
                "VariableReference.id",
                VariableReference(id=Identifier(name="test")),
            ),
            (
                "Attribute.id",
                Attribute(
                    id=Identifier(name="test"),
                    value=Pattern(elements=(TextElement(value="val"),)),
                ),
            ),
        ]

        transformer = AlwaysNoneTransformer()

        for _field_name, node in test_cases:
            with pytest.raises(TypeError) as exc_info:
                transformer.visit(node)

            # Should raise error mentioning the field cannot be None
            assert "Cannot assign None to required scalar field" in str(exc_info.value)
