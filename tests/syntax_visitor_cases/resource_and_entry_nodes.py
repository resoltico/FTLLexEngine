# mypy: ignore-errors
"""Split test cases from tests/test_syntax_visitor.py."""

from tests.syntax_visitor_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# RESOURCE AND ENTRY NODES
# ============================================================================


class TestVisitorResource:
    """Test visiting Resource nodes."""

    def test_visit_empty_resource(self) -> None:
        """Visit empty resource."""
        visitor = CountingVisitor()
        resource = Resource(entries=())

        visitor.visit(resource)

        assert visitor.counts["Resource"] == 1

    def test_visit_resource_with_messages(self) -> None:
        """Visit resource with multiple messages."""
        visitor = CountingVisitor()
        resource = Resource(
            entries=(
                Message(
                    id=Identifier(name="hello"),
                    value=Pattern(elements=(TextElement(value="Hello"),)),
                    attributes=(),
                ),
                Message(
                    id=Identifier(name="goodbye"),
                    value=Pattern(elements=(TextElement(value="Goodbye"),)),
                    attributes=(),
                ),
            )
        )

        visitor.visit(resource)

        assert visitor.counts["Resource"] == 1
        assert visitor.counts["Message"] == 2
        assert visitor.counts["Identifier"] == 2
        assert visitor.counts["Pattern"] == 2
        assert visitor.counts["TextElement"] == 2


class TestVisitorMessage:
    """Test visiting Message nodes."""

    def test_visit_simple_message(self) -> None:
        """Visit message with text only."""
        visitor = CountingVisitor()
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
        )

        visitor.visit(msg)

        assert visitor.counts["Message"] == 1
        assert visitor.counts["Identifier"] == 1
        assert visitor.counts["Pattern"] == 1
        assert visitor.counts["TextElement"] == 1

    def test_visit_message_with_attributes(self) -> None:
        """Visit message with attributes."""
        visitor = CountingVisitor()
        msg = Message(
            id=Identifier(name="button"),
            value=Pattern(elements=(TextElement(value="Save"),)),
            attributes=(
                Attribute(
                    id=Identifier(name="tooltip"),
                    value=Pattern(elements=(TextElement(value="Click to save"),)),
                ),
            ),
        )

        visitor.visit(msg)

        assert visitor.counts["Message"] == 1
        assert visitor.counts["Attribute"] == 1
        assert visitor.counts["Identifier"] == 2  # message + attribute

    def test_visit_message_with_comment(self) -> None:
        """Visit message with comment."""
        visitor = CountingVisitor()
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
            comment=Comment(content="This is a comment", type=CommentType.COMMENT),
        )

        visitor.visit(msg)

        assert visitor.counts["Message"] == 1
        assert visitor.counts["Comment"] == 1

    def test_visit_message_without_value(self) -> None:
        """Visit message without value (only attributes)."""
        visitor = CountingVisitor()
        msg = Message(
            id=Identifier(name="test"),
            value=None,
            attributes=(
                Attribute(
                    id=Identifier(name="attr"),
                    value=Pattern(elements=(TextElement(value="Value"),)),
                ),
            ),
        )

        visitor.visit(msg)

        assert visitor.counts["Message"] == 1
        assert visitor.counts["Attribute"] == 1
        # No Pattern count for message value (it's None)
        assert visitor.counts["Pattern"] == 1  # From attribute


class TestVisitorTerm:
    """Test visiting Term nodes."""

    def test_visit_simple_term(self) -> None:
        """Visit term with text only."""
        visitor = CountingVisitor()
        term = Term(
            id=Identifier(name="brand"),
            value=Pattern(elements=(TextElement(value="Firefox"),)),
            attributes=(),
        )

        visitor.visit(term)

        assert visitor.counts["Term"] == 1
        assert visitor.counts["Identifier"] == 1
        assert visitor.counts["Pattern"] == 1

    def test_visit_term_with_attributes(self) -> None:
        """Visit term with attributes."""
        visitor = CountingVisitor()
        term = Term(
            id=Identifier(name="brand"),
            value=Pattern(elements=(TextElement(value="Firefox"),)),
            attributes=(
                Attribute(
                    id=Identifier(name="version"),
                    value=Pattern(elements=(TextElement(value="120"),)),
                ),
            ),
        )

        visitor.visit(term)

        assert visitor.counts["Term"] == 1
        assert visitor.counts["Attribute"] == 1

    def test_visit_term_with_comment(self) -> None:
        """Visit term with comment."""
        visitor = CountingVisitor()
        term = Term(
            id=Identifier(name="brand"),
            value=Pattern(elements=(TextElement(value="Firefox"),)),
            attributes=(),
            comment=Comment(content="Brand name", type=CommentType.COMMENT),
        )

        visitor.visit(term)

        assert visitor.counts["Term"] == 1
        assert visitor.counts["Comment"] == 1


class TestVisitorAttribute:
    """Test visiting Attribute nodes."""

    def test_visit_attribute(self) -> None:
        """Visit attribute node."""
        visitor = CountingVisitor()
        attr = Attribute(
            id=Identifier(name="tooltip"),
            value=Pattern(elements=(TextElement(value="Help text"),)),
        )

        visitor.visit(attr)

        assert visitor.counts["Attribute"] == 1
        assert visitor.counts["Identifier"] == 1
        assert visitor.counts["Pattern"] == 1


class TestVisitorCommentJunk:
    """Test visiting Comment and Junk nodes."""

    def test_visit_comment(self) -> None:
        """Visit comment node."""
        visitor = CountingVisitor()
        comment = Comment(content="This is a comment", type=CommentType.COMMENT)

        visitor.visit(comment)

        assert visitor.counts["Comment"] == 1

    def test_visit_junk(self) -> None:
        """Visit junk node."""
        visitor = CountingVisitor()
        junk = Junk(content="invalid { syntax")

        visitor.visit(junk)

        assert visitor.counts["Junk"] == 1
