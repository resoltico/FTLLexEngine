# mypy: ignore-errors
"""Split test cases from tests/test_syntax_visitor.py."""

from tests.syntax_visitor_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# CALL ARGUMENTS
# ============================================================================


class TestVisitorCallArguments:
    """Test visiting CallArguments nodes."""

    def test_visit_call_arguments_empty(self) -> None:
        """Visit call arguments with no args."""
        visitor = CountingVisitor()
        args = CallArguments(positional=(), named=())

        visitor.visit(args)

        assert visitor.counts["CallArguments"] == 1

    def test_visit_call_arguments_positional(self) -> None:
        """Visit call arguments with positional args."""
        visitor = CountingVisitor()
        args = CallArguments(
            positional=(
                VariableReference(id=Identifier(name="x")),
                NumberLiteral(value=42, raw="42"),
            ),
            named=(),
        )

        visitor.visit(args)

        assert visitor.counts["CallArguments"] == 1
        assert visitor.counts["VariableReference"] == 1
        assert visitor.counts["NumberLiteral"] == 1

    def test_visit_call_arguments_named(self) -> None:
        """Visit call arguments with named args."""
        visitor = CountingVisitor()
        args = CallArguments(
            positional=(),
            named=(
                NamedArgument(
                    name=Identifier(name="param"),
                    value=StringLiteral(value="value"),
                ),
            ),
        )

        visitor.visit(args)

        assert visitor.counts["CallArguments"] == 1
        assert visitor.counts["NamedArgument"] == 1
        assert visitor.counts["StringLiteral"] == 1


class TestVisitorNamedArgument:
    """Test visiting NamedArgument nodes."""

    def test_visit_named_argument(self) -> None:
        """Visit named argument."""
        visitor = CountingVisitor()
        arg = NamedArgument(
            name=Identifier(name="minimumFractionDigits"), value=NumberLiteral(value=2, raw="2")
        )

        visitor.visit(arg)

        assert visitor.counts["NamedArgument"] == 1
        assert visitor.counts["Identifier"] == 1
        assert visitor.counts["NumberLiteral"] == 1


class TestVisitorIdentifier:
    """Test visiting Identifier nodes."""

    def test_visit_identifier(self) -> None:
        """Visit identifier."""
        visitor = CountingVisitor()
        ident = Identifier(name="test")

        visitor.visit(ident)

        assert visitor.counts["Identifier"] == 1
