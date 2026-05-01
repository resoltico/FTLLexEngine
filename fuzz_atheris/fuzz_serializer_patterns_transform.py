from __future__ import annotations

from dataclasses import replace as dc_replace
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    import atheris
from fuzz_serializer_support import (
    SerializerFuzzError,
    _build_visitor_resource,
    _domain,
    _verify_serializer_roundtrip,
)

from ftllexengine.syntax.ast import (
    Identifier,
    Message,
    Resource,
    SelectExpression,
    Term,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.visitor import ASTTransformer, ASTVisitor


def _pattern_visitor_dispatch(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """ASTVisitor dispatch reaches custom handlers and generic traversal."""
    del pattern  # pattern name unused beyond dispatch routing
    _domain.visitor_runs += 1
    resource = _build_visitor_resource(fdp)

    class CountingVisitor(ASTVisitor):
        """Count dispatch hits across a deliberately mixed AST."""

        def __init__(self) -> None:
            """Initialize node visit counters."""
            super().__init__()
            self.messages = 0
            self.terms = 0
            self.text_elements = 0
            self.variables = 0
            self.select_expressions = 0

        def visit_Message(self, node: Message) -> Message:  # noqa: N802 - NodeName
            """Count message visits and continue traversal."""
            self.messages += 1
            return cast("Message", self.generic_visit(node))

        def visit_Term(self, node: Term) -> Term:  # noqa: N802 - NodeName
            """Count term visits and continue traversal."""
            self.terms += 1
            return cast("Term", self.generic_visit(node))

        def visit_TextElement(self, node: TextElement) -> TextElement:  # noqa: N802 - NodeName
            """Count text-element visits and continue traversal."""
            self.text_elements += 1
            return cast("TextElement", self.generic_visit(node))

        def visit_VariableReference(  # noqa: N802 - NodeName
            self, node: VariableReference
        ) -> VariableReference:
            """Count variable-reference visits and continue traversal."""
            self.variables += 1
            return cast("VariableReference", self.generic_visit(node))

        def visit_SelectExpression(  # noqa: N802 - NodeName
            self, node: SelectExpression
        ) -> SelectExpression:
            """Count select-expression visits and continue traversal."""
            self.select_expressions += 1
            return cast("SelectExpression", self.generic_visit(node))

    visitor = CountingVisitor()
    result = visitor.visit(resource)

    if result is not resource:
        msg = "ASTVisitor.visit(Resource) did not return the visited node"
        raise SerializerFuzzError(msg)
    if visitor.messages < 1 or visitor.terms < 1:
        msg = "ASTVisitor failed to dispatch to Message/Term handlers"
        raise SerializerFuzzError(msg)
    if visitor.text_elements < 4:
        msg = f"Expected multiple TextElement visits, got {visitor.text_elements}"
        raise SerializerFuzzError(
            msg,
        )
    if visitor.variables < 1 or visitor.select_expressions < 1:
        msg = (
            "ASTVisitor failed to traverse nested "
            "VariableReference/SelectExpression nodes"
        )
        raise SerializerFuzzError(
            msg,
        )

def _pattern_transformer_roundtrip(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """ASTTransformer list expansion preserves serializer roundtrip invariants."""
    _domain.transformer_runs += 1
    resource = _build_visitor_resource(fdp)
    duplicate_suffix = f"-copy-{fdp.ConsumeIntInRange(0, 99)}"

    class ExpandingTransformer(ASTTransformer):
        """Expand a single message into two messages via list return."""

        def __init__(self, suffix: str) -> None:
            """Store suffix used for the duplicated message ID."""
            super().__init__()
            self._suffix = suffix
            self.expansions = 0

        def visit_Message(self, node: Message) -> list[Message]:  # noqa: N802 - NodeName
            """Duplicate visited messages after transforming their children."""
            transformed = self.generic_visit(node)
            if not isinstance(transformed, Message):
                msg = (
                    "ASTTransformer.generic_visit(Message) returned "
                    f"{type(transformed).__name__}"
                )
                raise SerializerFuzzError(msg)

            self.expansions += 1
            duplicate = dc_replace(
                transformed,
                id=Identifier(name=f"{transformed.id.name}{self._suffix}"),
            )
            return [transformed, duplicate]

    transformer = ExpandingTransformer(duplicate_suffix)
    transformed = transformer.transform(resource)

    if not isinstance(transformed, Resource):
        msg = f"transform(Resource) returned {type(transformed).__name__}"
        raise SerializerFuzzError(msg)

    message_count = sum(
        1 for entry in transformed.entries if isinstance(entry, Message)
    )
    if transformer.expansions < 1 or message_count < 2:
        msg = "ASTTransformer list expansion did not duplicate message entries"
        raise SerializerFuzzError(
            msg,
        )

    _verify_serializer_roundtrip(transformed, pattern)

def _pattern_transformer_validation(
    fdp: atheris.FuzzedDataProvider,
    pattern: str,
) -> None:
    """ASTTransformer rejects invalid scalar replacements for required fields."""
    del pattern  # validation path does not serialize on success
    resource = _build_visitor_resource(fdp)
    invalid_mode = fdp.ConsumeIntInRange(0, 1)

    class InvalidScalarTransformer(ASTTransformer):
        """Return invalid scalar replacements to verify runtime validation."""

        def __init__(self, mode: int) -> None:
            """Select whether to return None or a list for Identifier fields."""
            super().__init__()
            self._mode = mode

        def visit_Identifier(  # noqa: N802 - NodeName
            self, node: Identifier
        ) -> None | list[Identifier]:
            """Break required scalar field contracts for Identifier nodes."""
            if self._mode == 0:
                return None
            return [node, dc_replace(node, name=f"{node.name}-dup")]

    transformer = InvalidScalarTransformer(invalid_mode)

    try:
        transformer.transform(resource)
    except TypeError as exc:
        if "Message.id" not in str(exc):
            msg = (
                "ASTTransformer raised unexpected TypeError during scalar "
                f"validation: {exc}"
            )
            raise SerializerFuzzError(msg) from exc
        _domain.validation_errors += 1
        return

    msg = "ASTTransformer accepted invalid scalar replacement for Message.id"
    raise SerializerFuzzError(msg)
