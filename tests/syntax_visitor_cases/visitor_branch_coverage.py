# mypy: ignore-errors
"""Split test cases from tests/test_syntax_visitor.py."""

from tests.syntax_visitor_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# VISITOR BRANCH COVERAGE
# ============================================================================


class TestVisitorBranchCoverage:
    """Test visitor branch coverage for tuple fields and primitive fields."""

    def test_visit_node_with_empty_tuple_field(self) -> None:
        """Visitor handles message with empty attributes tuple."""
        message = Message(
            id=Identifier("empty"),
            value=Pattern(elements=(TextElement("Value"),)),
            attributes=(),
        )

        class CountingVisitorLocal(ASTVisitor):
            """Visitor that counts all nodes visited."""

            def __init__(self) -> None:
                """Initialize counter."""
                super().__init__()
                self.visit_count = 0

            def visit(self, node: Any) -> Any:
                """Count each visit."""
                self.visit_count += 1
                return super().visit(node)

        visitor = CountingVisitorLocal()
        visitor.visit(message)

        assert visitor.visit_count > 0

    def test_visit_node_with_primitive_fields(self) -> None:
        """Visitor dispatches to visit_Identifier for Identifier nodes."""
        ident = Identifier("test")

        class FieldInspector(ASTVisitor):
            """Visitor that tracks Identifier visits."""

            def __init__(self) -> None:
                """Initialize tracker."""
                super().__init__()
                self.visited_identifier = False

            def visit_Identifier(self, node: Identifier) -> Any:
                """Record that Identifier was visited."""
                self.visited_identifier = True
                return self.generic_visit(node)

        visitor = FieldInspector()
        visitor.visit(ident)

        assert visitor.visited_identifier

    def test_visit_node_with_none_field(self) -> None:
        """Visitor handles message with comment=None field gracefully."""
        message = Message(
            id=Identifier("noComment"),
            value=Pattern(elements=(TextElement("Val"),)),
            attributes=(),
            comment=None,
        )

        visitor = ASTVisitor()
        result = visitor.visit(message)

        assert result is not None


class TestVisitorBranchCoverageExtended:
    """Extended visitor branch coverage tests."""

    def test_visit_resource_with_mixed_entries(self) -> None:
        """Visitor traverses Resource with mix of messages, terms, comments, and junk."""
        resource = Resource(
            entries=(
                Comment(content="File comment", type=CommentType.RESOURCE),
                Message(
                    id=Identifier("msg"),
                    value=Pattern(elements=(TextElement("Value"),)),
                    attributes=(),
                ),
                Term(
                    id=Identifier("term"),
                    value=Pattern(elements=(TextElement("Term"),)),
                    attributes=(),
                ),
                Junk(content="invalid"),
            )
        )

        visitor = ASTVisitor()
        result = visitor.visit(resource)

        assert result is not None

    def test_visit_with_dataclass_fields(self) -> None:
        """Visitor traverses nodes with int and bool dataclass fields."""
        num_lit = NumberLiteral(value=42, raw="42")

        variant = Variant(
            key=num_lit,
            value=Pattern(elements=(TextElement("Forty-two"),)),
            default=True,
        )

        select = SelectExpression(
            selector=VariableReference(id=Identifier("num")),
            variants=(variant,),
        )

        message = Message(
            id=Identifier("select"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )

        visitor = ASTVisitor()
        result = visitor.visit(message)

        assert result is not None


class TestTransformerListExpansion:
    """ASTTransformer that returns a list from a visit method expands elements."""

    def test_transform_list_with_multiple_results(self) -> None:
        """Transformer returning a list from visit_TextElement expands pattern elements."""

        class ListExpandingTransformer(ASTTransformer):
            """Transformer that returns a list instead of a single node."""

            def visit_TextElement(self, node: TextElement) -> Any:
                """Return two nodes in place of one."""
                return [
                    TextElement(value=node.value.upper()),
                    TextElement(value=" "),
                ]

        pattern = Pattern(elements=(
            TextElement(value="hello"),
            TextElement(value="world"),
        ))

        transformer = ListExpandingTransformer()
        result = transformer.visit(pattern)

        assert isinstance(result, Pattern)
        assert len(result.elements) > 2
