"""Tests for ASTTransformer runtime type validation.

Validates that ASTTransformer._transform_list rejects transformed nodes
that do not match the expected field type, preventing silent AST corruption
from buggy transformers.

Property: transformers that return wrong-typed nodes raise TypeError with
a message identifying the field and the unexpected type.
"""

from __future__ import annotations

import pytest

from ftllexengine.syntax.ast import (
    CallArguments,
    FunctionReference,
    Identifier,
    Message,
    NamedArgument,
    Pattern,
    Placeable,
    Resource,
    StringLiteral,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.visitor import ASTTransformer


def _make_resource(*messages: Message) -> Resource:
    """Create a Resource with the given messages."""
    return Resource(entries=messages)


def _make_simple_message(name: str, text: str) -> Message:
    """Create a simple message with a text pattern."""
    return Message(
        id=Identifier(name=name, span=None),
        value=Pattern(elements=(TextElement(value=text),)),
        attributes=(),
        comment=None,
        span=None,
    )


class TestTransformListTypeValidation:
    """_transform_list rejects wrong-typed nodes."""

    def test_message_in_pattern_elements_rejected(self) -> None:
        """Message node in Pattern.elements raises TypeError.

        Pattern.elements expects TextElement | Placeable. Producing a Message
        violates the field type constraint.
        """

        class BadTransformer(ASTTransformer):
            def visit_TextElement(self, node: TextElement) -> Message:  # noqa: N802, ARG002
                return _make_simple_message("wrong", "bad")

        resource = _make_resource(_make_simple_message("msg", "hello"))
        transformer = BadTransformer()

        with pytest.raises(TypeError, match=r"Pattern\.elements.*TextElement \| Placeable"):
            transformer.transform(resource)

    def test_text_element_in_resource_entries_rejected(self) -> None:
        """TextElement in Resource.entries raises TypeError.

        Resource.entries expects Message | Term | Comment | Junk.
        """

        class BadTransformer(ASTTransformer):
            def visit_Message(self, node: Message) -> TextElement:  # noqa: N802, ARG002
                return TextElement(value="not a message")

        resource = _make_resource(_make_simple_message("msg", "hello"))
        transformer = BadTransformer()

        with pytest.raises(TypeError, match=r"Resource\.entries.*Message \| Term"):
            transformer.transform(resource)

    def test_message_in_call_arguments_named_rejected(self) -> None:
        """Message in CallArguments.named raises TypeError.

        CallArguments.named expects NamedArgument only.
        """

        class BadTransformer(ASTTransformer):
            def visit_NamedArgument(self, node: NamedArgument) -> Message:  # noqa: N802, ARG002
                return _make_simple_message("wrong", "bad")

        func_ref = FunctionReference(
            id=Identifier(name="NUMBER", span=None),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier(name="x", span=None), span=None),),
                named=(
                    NamedArgument(
                        name=Identifier(name="style", span=None),
                        value=StringLiteral(value="decimal", span=None),
                        span=None,
                    ),
                ),
            ),
            span=None,
        )
        msg = Message(
            id=Identifier(name="msg", span=None),
            value=Pattern(
                elements=(Placeable(expression=func_ref),),
            ),
            attributes=(),
            comment=None,
            span=None,
        )
        resource = _make_resource(msg)
        transformer = BadTransformer()

        with pytest.raises(TypeError, match=r"CallArguments\.named.*NamedArgument"):
            transformer.transform(resource)


class TestTransformListTypeValidationExpand:
    """_transform_list validates types in expanded lists."""

    def test_expanded_list_with_wrong_type_rejected(self) -> None:
        """List expansion with wrong type raises TypeError.

        When visit_* returns a list, each element must match expected types.
        """

        class ExpandBadTransformer(ASTTransformer):
            def visit_TextElement(  # noqa: N802
                self, node: TextElement  # noqa: ARG002
            ) -> list[Message]:
                return [_make_simple_message("wrong", "bad")]

        resource = _make_resource(_make_simple_message("msg", "hello"))
        transformer = ExpandBadTransformer()

        with pytest.raises(TypeError, match=r"Pattern\.elements"):
            transformer.transform(resource)


class TestTransformListTypeValidationValid:
    """Valid transformations pass type validation."""

    def test_identity_transform_succeeds(self) -> None:
        """Identity transformer (no changes) passes validation."""
        resource = _make_resource(
            _make_simple_message("msg1", "hello"),
            _make_simple_message("msg2", "world"),
        )
        transformer = ASTTransformer()
        result = transformer.transform(resource)
        assert isinstance(result, Resource)

    def test_correct_type_replacement_succeeds(self) -> None:
        """Replacing TextElement with another TextElement passes validation."""

        class UpperTransformer(ASTTransformer):
            def visit_TextElement(self, node: TextElement) -> TextElement:  # noqa: N802
                return TextElement(value=node.value.upper())

        resource = _make_resource(_make_simple_message("msg", "hello"))
        transformer = UpperTransformer()
        result = transformer.transform(resource)
        assert isinstance(result, Resource)
        elements = result.entries[0].value.elements  # type: ignore[union-attr]
        assert elements[0].value == "HELLO"  # type: ignore[union-attr]

    def test_none_removal_succeeds(self) -> None:
        """Removing elements via None passes validation (no type check needed)."""

        class RemoveTransformer(ASTTransformer):
            def visit_Message(self, node: Message) -> None:  # noqa: N802, ARG002
                return None

        resource = _make_resource(
            _make_simple_message("msg1", "hello"),
            _make_simple_message("msg2", "world"),
        )
        transformer = RemoveTransformer()
        result = transformer.transform(resource)
        assert isinstance(result, Resource)
        assert len(result.entries) == 0

    def test_correct_expansion_succeeds(self) -> None:
        """Expanding one Message into two Messages passes validation."""

        class DuplicateTransformer(ASTTransformer):
            def visit_Message(self, node: Message) -> list[Message]:  # noqa: N802
                copy = Message(
                    id=Identifier(name=node.id.name + "_copy", span=None),
                    value=node.value,
                    attributes=(),
                    comment=None,
                    span=None,
                )
                return [node, copy]

        resource = _make_resource(_make_simple_message("msg", "hello"))
        transformer = DuplicateTransformer()
        result = transformer.transform(resource)
        assert isinstance(result, Resource)
        assert len(result.entries) == 2
        entry0 = result.entries[0]
        entry1 = result.entries[1]
        assert isinstance(entry0, Message)
        assert isinstance(entry1, Message)
        assert entry0.id.name == "msg"
        assert entry1.id.name == "msg_copy"
