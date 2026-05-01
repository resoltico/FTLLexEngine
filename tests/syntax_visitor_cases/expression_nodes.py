# mypy: ignore-errors
"""Split test cases from tests/test_syntax_visitor.py."""

from tests.syntax_visitor_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# EXPRESSION NODES
# ============================================================================


class TestVisitorLiterals:
    """Test visiting literal expression nodes."""

    def test_visit_string_literal(self) -> None:
        """Visit string literal."""
        visitor = CountingVisitor()
        literal = StringLiteral(value="test")

        visitor.visit(literal)

        assert visitor.counts["StringLiteral"] == 1

    def test_visit_number_literal(self) -> None:
        """Visit number literal."""
        visitor = CountingVisitor()
        literal = NumberLiteral(value=42, raw="42")

        visitor.visit(literal)

        assert visitor.counts["NumberLiteral"] == 1


class TestVisitorReferences:
    """Test visiting reference expression nodes."""

    def test_visit_variable_reference(self) -> None:
        """Visit variable reference."""
        visitor = CountingVisitor()
        ref = VariableReference(id=Identifier(name="count"))

        visitor.visit(ref)

        assert visitor.counts["VariableReference"] == 1
        assert visitor.counts["Identifier"] == 1

    def test_visit_message_reference_simple(self) -> None:
        """Visit message reference without attribute."""
        visitor = CountingVisitor()
        ref = MessageReference(id=Identifier(name="hello"), attribute=None)

        visitor.visit(ref)

        assert visitor.counts["MessageReference"] == 1
        assert visitor.counts["Identifier"] == 1

    def test_visit_message_reference_with_attribute(self) -> None:
        """Visit message reference with attribute."""
        visitor = CountingVisitor()
        ref = MessageReference(
            id=Identifier(name="button"), attribute=Identifier(name="tooltip")
        )

        visitor.visit(ref)

        assert visitor.counts["MessageReference"] == 1
        assert visitor.counts["Identifier"] == 2

    def test_visit_term_reference_simple(self) -> None:
        """Visit term reference without attribute or arguments."""
        visitor = CountingVisitor()
        ref = TermReference(id=Identifier(name="brand"), attribute=None, arguments=None)

        visitor.visit(ref)

        assert visitor.counts["TermReference"] == 1
        assert visitor.counts["Identifier"] == 1

    def test_visit_term_reference_with_attribute(self) -> None:
        """Visit term reference with attribute."""
        visitor = CountingVisitor()
        ref = TermReference(
            id=Identifier(name="brand"),
            attribute=Identifier(name="version"),
            arguments=None,
        )

        visitor.visit(ref)

        assert visitor.counts["TermReference"] == 1
        assert visitor.counts["Identifier"] == 2

    def test_visit_term_reference_with_arguments(self) -> None:
        """Visit term reference with arguments."""
        visitor = CountingVisitor()
        ref = TermReference(
            id=Identifier(name="brand"),
            attribute=None,
            arguments=CallArguments(positional=(), named=()),
        )

        visitor.visit(ref)

        assert visitor.counts["TermReference"] == 1
        assert visitor.counts["CallArguments"] == 1


class TestVisitorFunctionReference:
    """Test visiting FunctionReference nodes."""

    def test_visit_function_reference_no_args(self) -> None:
        """Visit function with no arguments."""
        visitor = CountingVisitor()
        func = FunctionReference(
            id=Identifier(name="NUMBER"), arguments=CallArguments(positional=(), named=())
        )

        visitor.visit(func)

        assert visitor.counts["FunctionReference"] == 1
        assert visitor.counts["Identifier"] == 1
        assert visitor.counts["CallArguments"] == 1

    def test_visit_function_reference_with_args(self) -> None:
        """Visit function with positional arguments."""
        visitor = CountingVisitor()
        func = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier(name="value")),), named=()
            ),
        )

        visitor.visit(func)

        assert visitor.counts["FunctionReference"] == 1
        assert visitor.counts["CallArguments"] == 1
        assert visitor.counts["VariableReference"] == 1


class TestVisitorSelectExpression:
    """Test visiting SelectExpression nodes."""

    def test_visit_select_expression(self) -> None:
        """Visit select expression with variants."""
        visitor = CountingVisitor()
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="count")),
            variants=(
                Variant(
                    key=Identifier(name="one"),
                    value=Pattern(elements=(TextElement(value="one item"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier(name="other"),
                    value=Pattern(elements=(TextElement(value="many items"),)),
                    default=True,
                ),
            ),
        )

        visitor.visit(select)

        assert visitor.counts["SelectExpression"] == 1
        assert visitor.counts["VariableReference"] == 1
        assert visitor.counts["Variant"] == 2
        assert visitor.counts["Pattern"] == 2


class TestVisitorVariant:
    """Test visiting Variant nodes."""

    def test_visit_variant_with_identifier_key(self) -> None:
        """Visit variant with identifier key."""
        visitor = CountingVisitor()
        variant = Variant(
            key=Identifier(name="one"),
            value=Pattern(elements=(TextElement(value="one"),)),
            default=False,
        )

        visitor.visit(variant)

        assert visitor.counts["Variant"] == 1
        assert visitor.counts["Identifier"] == 1
        assert visitor.counts["Pattern"] == 1

    def test_visit_variant_with_number_key(self) -> None:
        """Visit variant with number literal key."""
        visitor = CountingVisitor()
        variant = Variant(
            key=NumberLiteral(value=0, raw="0"),
            value=Pattern(elements=(TextElement(value="none"),)),
            default=False,
        )

        visitor.visit(variant)

        assert visitor.counts["Variant"] == 1
        assert visitor.counts["NumberLiteral"] == 1
