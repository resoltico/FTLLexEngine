"""Tests for ASTTransformer scalar field validation (B-ARCH-TYPE-001).

Verifies that ASTTransformer validates scalar field assignments, preventing
invalid AST construction from incorrect visit() return values.

Python 3.13+. Uses pytest.
"""

from __future__ import annotations

import pytest

from ftllexengine.syntax.ast import (
    Identifier,
    Message,
    Pattern,
    Placeable,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.visitor import ASTTransformer


class TestASTTransformerValidation:
    """Tests for ASTTransformer scalar field validation."""

    def test_scalar_field_accepts_single_node(self) -> None:
        """Scalar field accepts single ASTNode return value."""
        class RenameIdentifierTransformer(ASTTransformer):
            def visit_Identifier(self, node: Identifier) -> Identifier:
                return Identifier(name="renamed")

        message = Message(
            id=Identifier(name="hello"),
            value=Pattern(elements=(TextElement(value="World"),)),
            attributes=(),
        )

        transformer = RenameIdentifierTransformer()
        transformed = transformer.transform(message)

        # Transformation should succeed
        assert isinstance(transformed, Message)
        assert transformed.id.name == "renamed"

    def test_scalar_field_rejects_none(self) -> None:
        """Scalar field assignment rejects None return value."""
        class RemoveIdentifierTransformer(ASTTransformer):
            def visit_Identifier(self, node: Identifier) -> None:
                return None  # Invalid: scalar field requires node

        message = Message(
            id=Identifier(name="hello"),
            value=Pattern(elements=(TextElement(value="World"),)),
            attributes=(),
        )

        transformer = RemoveIdentifierTransformer()

        with pytest.raises(TypeError) as exc_info:
            transformer.transform(message)

        error_msg = str(exc_info.value)
        assert "Cannot assign None to required scalar field" in error_msg
        assert "Message.id" in error_msg
        assert "Required scalar fields must have a single ASTNode" in error_msg

    def test_scalar_field_rejects_list(self) -> None:
        """Scalar field assignment rejects list[ASTNode] return value."""
        class ExpandIdentifierTransformer(ASTTransformer):
            def visit_Identifier(self, node: Identifier) -> list[Identifier]:
                return [  # Invalid: scalar field requires single node
                    Identifier(name="id1"),
                    Identifier(name="id2"),
                ]

        message = Message(
            id=Identifier(name="hello"),
            value=Pattern(elements=(TextElement(value="World"),)),
            attributes=(),
        )

        transformer = ExpandIdentifierTransformer()

        with pytest.raises(TypeError) as exc_info:
            transformer.transform(message)

        error_msg = str(exc_info.value)
        assert "Cannot assign list to scalar field" in error_msg
        assert "Message.id" in error_msg
        assert "Got 2 nodes" in error_msg

    def test_collection_field_accepts_list(self) -> None:
        """Collection field accepts list[ASTNode] return value via _transform_list."""
        class ExpandTextElementTransformer(ASTTransformer):
            def visit_TextElement(self, node: TextElement) -> list[TextElement]:
                # Valid: Pattern.elements is a collection field
                return [
                    TextElement(value="Hello"),
                    TextElement(value=" "),
                    TextElement(value="World"),
                ]

        pattern = Pattern(elements=(TextElement(value="HelloWorld"),))

        transformer = ExpandTextElementTransformer()
        transformed = transformer.transform(pattern)

        # Transformation should succeed
        assert isinstance(transformed, Pattern)
        assert len(transformed.elements) == 3
        first_element = transformed.elements[0]
        assert isinstance(first_element, TextElement)
        assert first_element.value == "Hello"

    def test_optional_scalar_field_accepts_none_when_original_is_none(self) -> None:
        """Optional scalar fields (e.g., Message.value) accept None when original has attributes."""
        from ftllexengine.syntax.ast import Attribute  # noqa: PLC0415

        # Message without value but with attribute (valid per spec)
        message = Message(
            id=Identifier(name="empty"),
            value=None,  # Optional field
            attributes=(
                Attribute(
                    id=Identifier(name="attr"),
                    value=Pattern(elements=(TextElement(value="val"),)),
                ),
            ),
        )

        class NoOpTransformer(ASTTransformer):
            pass

        transformer = NoOpTransformer()
        transformed = transformer.transform(message)

        # Transformation should succeed
        assert isinstance(transformed, Message)
        assert transformed.value is None

    def test_optional_scalar_field_accepts_none_when_transformer_removes(self) -> None:
        """Optional scalar fields accept None return value to remove existing value."""
        from ftllexengine.enums import CommentType  # noqa: PLC0415
        from ftllexengine.syntax.ast import Comment  # noqa: PLC0415

        # Message with comment (optional field)
        message = Message(
            id=Identifier(name="hello"),
            value=Pattern(elements=(TextElement(value="World"),)),
            attributes=(),
            comment=Comment(content="A comment", type=CommentType.COMMENT),
        )

        class RemoveCommentTransformer(ASTTransformer):
            def visit_Comment(self, node: Comment) -> None:
                return None  # Valid: removes optional comment field

        transformer = RemoveCommentTransformer()
        transformed = transformer.transform(message)

        # Transformation should succeed with comment removed
        assert isinstance(transformed, Message)
        assert transformed.comment is None
        assert transformed.id.name == "hello"

    def test_placeable_expression_validation(self) -> None:
        """Placeable.expression validates scalar field assignment."""
        class RemoveExpressionTransformer(ASTTransformer):
            def visit_VariableReference(self, node: VariableReference) -> None:
                return None  # Invalid: Placeable.expression requires node

        placeable = Placeable(expression=VariableReference(id=Identifier(name="var")))

        transformer = RemoveExpressionTransformer()

        with pytest.raises(TypeError) as exc_info:
            transformer.transform(placeable)

        error_msg = str(exc_info.value)
        assert "Cannot assign None to required scalar field" in error_msg
        assert "Placeable.expression" in error_msg

    def test_error_message_shows_node_types_for_list(self) -> None:
        """Error message for list assignment shows node types."""
        class MultipleIdentifiersTransformer(ASTTransformer):
            def visit_Identifier(self, node: Identifier) -> list[Identifier]:
                return [
                    Identifier(name="a"),
                    Identifier(name="b"),
                    Identifier(name="c"),
                ]

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
        )

        transformer = MultipleIdentifiersTransformer()

        with pytest.raises(TypeError) as exc_info:
            transformer.transform(message)

        error_msg = str(exc_info.value)
        assert "Got 3 nodes" in error_msg
        assert "['Identifier', 'Identifier', 'Identifier']" in error_msg

    def test_nested_transformation_validates_all_levels(self) -> None:
        """Validation applies recursively at all nesting levels."""
        class RemoveNestedIdentifierTransformer(ASTTransformer):
            def visit_Identifier(self, node: Identifier) -> Identifier | None:
                if node.name == "var":
                    return None  # Invalid for scalar field
                return node

        # Nested structure: Message -> Pattern -> Placeable -> VariableReference -> Identifier
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(
                elements=(
                    Placeable(expression=VariableReference(id=Identifier(name="var"))),
                )
            ),
            attributes=(),
        )

        transformer = RemoveNestedIdentifierTransformer()

        with pytest.raises(TypeError) as exc_info:
            transformer.transform(message)

        # Error should be raised when trying to assign None to VariableReference.id
        error_msg = str(exc_info.value)
        assert "Cannot assign None to required scalar field" in error_msg
        assert "VariableReference.id" in error_msg

    def test_validation_with_generic_visit(self) -> None:
        """Validation works with default generic_visit (no custom visit methods)."""
        class BreakScalarFieldTransformer(ASTTransformer):
            def visit_Identifier(self, node: Identifier) -> None:
                return None

        # Use a complex node to test generic_visit path
        from ftllexengine.syntax.ast import (  # noqa: PLC0415
            NumberLiteral,
            SelectExpression,
            Variant,
        )

        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier(name="count")),
            variants=(
                Variant(
                    key=NumberLiteral(value=1, raw="1"),
                    value=Pattern(elements=(TextElement(value="one"),)),
                    default=True,
                ),
            ),
        )

        transformer = BreakScalarFieldTransformer()

        with pytest.raises(TypeError) as exc_info:
            transformer.transform(select_expr)

        # Should fail on SelectExpression.selector -> VariableReference.id
        error_msg = str(exc_info.value)
        assert "Cannot assign None to required scalar field" in error_msg
