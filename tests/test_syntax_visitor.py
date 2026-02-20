"""Tests for syntax.visitor: ASTVisitor traversal, dispatch, and defensive branches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ftllexengine.enums import CommentType
from ftllexengine.syntax.ast import (
    Attribute,
    CallArguments,
    Comment,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    MessageReference,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.visitor import ASTVisitor

# ============================================================================
# HELPER VISITORS
# ============================================================================


class CountingVisitor(ASTVisitor):
    """Counts visits to each node type."""

    def __init__(self) -> None:
        """Initialize counters."""
        super().__init__()
        self.counts: dict[str, int] = {}

    def visit(self, node: Any) -> Any:
        """Track each visit."""
        node_type = type(node).__name__
        self.counts[node_type] = self.counts.get(node_type, 0) + 1
        return super().visit(node)


class CollectingVisitor(ASTVisitor):
    """Collects all identifiers visited."""

    def __init__(self) -> None:
        """Initialize collection."""
        super().__init__()
        self.identifiers: list[str] = []

    def visit_Identifier(self, node: Identifier) -> Any:
        """Collect identifier names."""
        self.identifiers.append(node.name)
        return self.generic_visit(node)


class TransformingVisitor(ASTVisitor):
    """Transforms text to uppercase."""

    def visit_TextElement(self, node: TextElement) -> TextElement:
        """Transform text to uppercase."""
        return TextElement(value=node.value.upper())


# ============================================================================
# BASIC VISITOR TESTS
# ============================================================================


class TestASTVisitorBasic:
    """Test basic visitor functionality."""

    def test_visit_dispatches_to_specific_method(self) -> None:
        """Visitor dispatches to visit_NodeType method."""
        visitor = CountingVisitor()
        node = Identifier(name="test")

        visitor.visit(node)

        assert visitor.counts["Identifier"] == 1

    def test_generic_visit_returns_node(self) -> None:
        """Generic visit returns node unchanged."""
        visitor = ASTVisitor()
        node = Identifier(name="test")

        result = visitor.generic_visit(node)

        assert result is node


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


# ============================================================================
# PATTERN AND ELEMENT NODES
# ============================================================================


class TestVisitorPattern:
    """Test visiting Pattern nodes."""

    def test_visit_pattern_with_text(self) -> None:
        """Visit pattern with text elements."""
        visitor = CountingVisitor()
        pattern = Pattern(elements=(TextElement(value="Hello"),))

        visitor.visit(pattern)

        assert visitor.counts["Pattern"] == 1
        assert visitor.counts["TextElement"] == 1

    def test_visit_pattern_with_mixed_elements(self) -> None:
        """Visit pattern with text and placeables."""
        visitor = CountingVisitor()
        pattern = Pattern(
            elements=(
                TextElement(value="Hello, "),
                Placeable(expression=VariableReference(id=Identifier(name="name"))),
                TextElement(value="!"),
            )
        )

        visitor.visit(pattern)

        assert visitor.counts["Pattern"] == 1
        assert visitor.counts["TextElement"] == 2
        assert visitor.counts["Placeable"] == 1
        assert visitor.counts["VariableReference"] == 1


class TestVisitorTextElement:
    """Test visiting TextElement nodes."""

    def test_visit_text_element(self) -> None:
        """Visit text element."""
        visitor = CountingVisitor()
        text = TextElement(value="Hello, World!")

        visitor.visit(text)

        assert visitor.counts["TextElement"] == 1


class TestVisitorPlaceable:
    """Test visiting Placeable nodes."""

    def test_visit_placeable_with_variable(self) -> None:
        """Visit placeable containing variable."""
        visitor = CountingVisitor()
        placeable = Placeable(expression=VariableReference(id=Identifier(name="var")))

        visitor.visit(placeable)

        assert visitor.counts["Placeable"] == 1
        assert visitor.counts["VariableReference"] == 1
        assert visitor.counts["Identifier"] == 1


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


# ============================================================================
# VISITOR CUSTOMIZATION
# ============================================================================


class TestVisitorCustomization:
    """Test custom visitor implementations."""

    def test_collecting_visitor(self) -> None:
        """Custom visitor can collect specific data."""
        visitor = CollectingVisitor()
        resource = Resource(
            entries=(
                Message(
                    id=Identifier(name="hello"),
                    value=Pattern(
                        elements=(
                            TextElement(value="Hello, "),
                            Placeable(
                                expression=VariableReference(id=Identifier(name="name"))
                            ),
                        )
                    ),
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

        assert "hello" in visitor.identifiers
        assert "goodbye" in visitor.identifiers
        assert "name" in visitor.identifiers

    def test_transforming_visitor(self) -> None:
        """Custom visitor can transform nodes."""
        visitor = TransformingVisitor()
        text = TextElement(value="hello")

        result = visitor.visit(text)

        assert isinstance(result, TextElement)
        assert result.value == "HELLO"


# ============================================================================
# COMPLEX INTEGRATION TESTS
# ============================================================================


class TestVisitorIntegration:
    """Test visitor with complex AST structures."""

    def test_visit_complex_message_with_select(self) -> None:
        """Visit message with select expression and multiple variants."""
        visitor = CountingVisitor()
        msg = Message(
            id=Identifier(name="emails"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=SelectExpression(
                            selector=VariableReference(id=Identifier(name="count")),
                            variants=(
                                Variant(
                                    key=Identifier(name="one"),
                                    value=Pattern(
                                        elements=(TextElement(value="one email"),)
                                    ),
                                    default=False,
                                ),
                                Variant(
                                    key=Identifier(name="other"),
                                    value=Pattern(
                                        elements=(
                                            Placeable(
                                                expression=VariableReference(
                                                    id=Identifier(name="count")
                                                )
                                            ),
                                            TextElement(value=" emails"),
                                        )
                                    ),
                                    default=True,
                                ),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )

        visitor.visit(msg)

        assert visitor.counts["Message"] == 1
        assert visitor.counts["SelectExpression"] == 1
        assert visitor.counts["Variant"] == 2
        assert visitor.counts["VariableReference"] == 2  # selector + in variant

    def test_visit_message_with_function_call(self) -> None:
        """Visit message with function call."""
        visitor = CountingVisitor()
        msg = Message(
            id=Identifier(name="price"),
            value=Pattern(
                elements=(
                    TextElement(value="Price: "),
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier(name="NUMBER"),
                            arguments=CallArguments(
                                positional=(
                                    VariableReference(id=Identifier(name="value")),
                                ),
                                named=(
                                    NamedArgument(
                                        name=Identifier(name="minimumFractionDigits"),
                                        value=NumberLiteral(value=2, raw="2"),
                                    ),
                                ),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )

        visitor.visit(msg)

        assert visitor.counts["Message"] == 1
        assert visitor.counts["FunctionReference"] == 1
        assert visitor.counts["CallArguments"] == 1
        assert visitor.counts["NamedArgument"] == 1

    def test_visit_resource_with_mixed_entries(self) -> None:
        """Visit resource with messages, terms, comments, and junk."""
        visitor = CountingVisitor()
        resource = Resource(
            entries=(
                Comment(content="Header comment", type=CommentType.COMMENT),
                Message(
                    id=Identifier(name="hello"),
                    value=Pattern(elements=(TextElement(value="Hello"),)),
                    attributes=(),
                ),
                Term(
                    id=Identifier(name="brand"),
                    value=Pattern(elements=(TextElement(value="Firefox"),)),
                    attributes=(),
                ),
                Junk(content="invalid syntax"),
            )
        )

        visitor.visit(resource)

        assert visitor.counts["Resource"] == 1
        assert visitor.counts["Comment"] == 1
        assert visitor.counts["Message"] == 1
        assert visitor.counts["Term"] == 1
        assert visitor.counts["Junk"] == 1


# ============================================================================
# DEFENSIVE BRANCHES (from test_visitor_branch_coverage.py)
# ============================================================================


@dataclass(frozen=True)
class MockFieldContainer:
    """Mock container without __dataclass_fields__ for testing defensive branches."""

    value: str


class PlainObject:
    """Plain object without dataclass fields for testing defensive branches."""

    def __init__(self, data: str) -> None:
        """Initialize with data."""
        self.data = data


class TestGenericVisitDefensiveBranches:
    """Test defensive branches in generic_visit for non-ASTNode values."""

    def test_generic_visit_tuple_with_non_dataclass_items(self) -> None:
        """Test line 214->212: tuple containing items without __dataclass_fields__.

        This tests the defensive branch where a tuple field contains items that
        are not ASTNodes (don't have __dataclass_fields__).
        """

        class CountingVisitor(ASTVisitor):
            """Visitor that counts visits."""

            def __init__(self) -> None:
                """Initialize visitor."""
                super().__init__()
                self.visit_count = 0

            def visit(self, node):
                """Count each visit."""
                self.visit_count += 1
                return super().visit(node)

        # Create a message with normal structure
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
        )

        # Monkey-patch the elements tuple to include a non-ASTNode item
        # This is testing a defensive code path that shouldn't happen in normal usage
        # but guards against malformed AST structures
        modified_elements = (
            TextElement(value="First"),
            MockFieldContainer(value="not_an_astnode"),  # No __dataclass_fields__
            TextElement(value="Last"),
        )

        # Use object.__setattr__ to bypass frozen dataclass protection
        object.__setattr__(msg.value, "elements", modified_elements)

        visitor = CountingVisitor()
        visitor.generic_visit(msg)

        # The visitor should visit the Message, Pattern, Identifier, and the two TextElements
        # but NOT the MockFieldContainer (it lacks __dataclass_fields__)
        # Visit count: Message (1) + Identifier (1) + Pattern (1) + 2 TextElements (2) = 5
        assert visitor.visit_count == 5

    def test_generic_visit_tuple_with_mixed_items(self) -> None:
        """Test tuple containing mix of ASTNodes and non-ASTNodes.

        This comprehensively tests the line 214 branch logic where we check
        each tuple item for __dataclass_fields__.
        """

        class VisitOrderTracker(ASTVisitor):
            """Track order of visits."""

            def __init__(self) -> None:
                """Initialize tracker."""
                super().__init__()
                self.visit_order: list[str] = []

            def visit(self, node):
                """Record visit order."""
                node_name = type(node).__name__
                if node_name == "TextElement":
                    text_value = getattr(node, "value", "")
                    self.visit_order.append(f"TextElement:{text_value}")
                else:
                    self.visit_order.append(node_name)
                return super().visit(node)

        # Create pattern with mixed elements
        pattern = Pattern(
            elements=(
                TextElement(value="A"),
                TextElement(value="B"),
            )
        )

        # Inject non-ASTNode items into the tuple
        mixed_elements = (
            TextElement(value="A"),
            "string_value",  # Not an ASTNode, will be skipped
            TextElement(value="B"),
            123,  # int, will be skipped by primitive check
        )

        object.__setattr__(pattern, "elements", mixed_elements)

        visitor = VisitOrderTracker()
        visitor.generic_visit(pattern)

        # Should visit TextElement:A and TextElement:B, skipping string and int
        assert "TextElement:A" in visitor.visit_order
        assert "TextElement:B" in visitor.visit_order
        # String and int should not appear
        assert "str" not in visitor.visit_order
        assert "int" not in visitor.visit_order

    def test_generic_visit_non_tuple_non_dataclass_field(self) -> None:
        """Test line 217->203: single field that is an object without __dataclass_fields__.

        This tests the defensive else branch where a field value is:
        - Not None
        - Not a primitive (str, int, float, bool)
        - Not a tuple
        - Not an ASTNode (no __dataclass_fields__)
        """
        # Create a message
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
        )

        # Replace the 'comment' field (normally None or Comment ASTNode) with a
        # plain object that doesn't have __dataclass_fields__
        plain_obj = PlainObject(data="test")
        object.__setattr__(msg, "comment", plain_obj)

        class VisitorTracker(ASTVisitor):
            """Track what gets visited."""

            def __init__(self) -> None:
                """Initialize tracker."""
                super().__init__()
                self.visited_types: set[str] = set()

            def visit(self, node):
                """Track visits."""
                self.visited_types.add(type(node).__name__)
                return super().visit(node)

        visitor = VisitorTracker()
        visitor.generic_visit(msg)

        # Should have visited Message's children (Identifier, Pattern, TextElement)
        # but NOT the PlainObject (it doesn't have __dataclass_fields__)
        assert "Identifier" in visitor.visited_types
        assert "Pattern" in visitor.visited_types
        assert "TextElement" in visitor.visited_types
        assert "PlainObject" not in visitor.visited_types
