"""Tests for FTL serializer.

Validates serialization of AST nodes back to FTL syntax.
"""

from __future__ import annotations

from ftllexengine.enums import CommentType
from ftllexengine.syntax import serialize
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
from ftllexengine.syntax.serializer import FluentSerializer

# ============================================================================
# BASIC SERIALIZATION TESTS
# ============================================================================


class TestSerializerBasic:
    """Test basic serializer functionality."""

    def test_serialize_empty_resource(self) -> None:
        """Serialize empty resource."""
        resource = Resource(entries=())

        result = serialize(resource)

        assert result == ""

    def test_serializer_class_directly(self) -> None:
        """Use FluentSerializer class directly."""
        serializer = FluentSerializer()
        resource = Resource(entries=())

        result = serializer.serialize(resource)

        assert result == ""


# ============================================================================
# MESSAGE SERIALIZATION
# ============================================================================


class TestSerializerMessage:
    """Test message serialization."""

    def test_serialize_simple_message(self) -> None:
        """Serialize message with text only."""
        msg = Message(
            id=Identifier(name="hello"),
            value=Pattern(elements=(TextElement(value="Hello, World!"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert result == "hello = Hello, World!\n"

    def test_serialize_message_with_variable(self) -> None:
        """Serialize message with variable interpolation."""
        msg = Message(
            id=Identifier(name="greeting"),
            value=Pattern(
                elements=(
                    TextElement(value="Hello, "),
                    Placeable(expression=VariableReference(id=Identifier(name="name"))),
                    TextElement(value="!"),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert result == "greeting = Hello, { $name }!\n"

    def test_serialize_message_without_value(self) -> None:
        """Serialize message without value (only attributes)."""
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
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "test" in result
        assert ".attr = Value" in result

    def test_serialize_message_with_comment(self) -> None:
        """Serialize message with associated comment."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
            comment=Comment(content="This is a comment", type=CommentType.COMMENT),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "# This is a comment\n" in result
        assert "test = Test\n" in result

    def test_serialize_message_with_attributes(self) -> None:
        """Serialize message with attributes."""
        msg = Message(
            id=Identifier(name="button"),
            value=Pattern(elements=(TextElement(value="Save"),)),
            attributes=(
                Attribute(
                    id=Identifier(name="tooltip"),
                    value=Pattern(elements=(TextElement(value="Click to save"),)),
                ),
                Attribute(
                    id=Identifier(name="aria-label"),
                    value=Pattern(elements=(TextElement(value="Save button"),)),
                ),
            ),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "button = Save\n" in result
        assert "    .tooltip = Click to save\n" in result
        assert "    .aria-label = Save button\n" in result

    def test_serialize_multiple_messages(self) -> None:
        """Serialize multiple messages with blank line separation."""
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

        result = serialize(resource)

        assert "hello = Hello\n" in result
        assert "goodbye = Goodbye\n" in result


# ============================================================================
# TERM SERIALIZATION
# ============================================================================


class TestSerializerTerm:
    """Test term serialization."""

    def test_serialize_simple_term(self) -> None:
        """Serialize simple term."""
        term = Term(
            id=Identifier(name="brand"),
            value=Pattern(elements=(TextElement(value="Firefox"),)),
            attributes=(),
        )
        resource = Resource(entries=(term,))

        result = serialize(resource)

        assert result == "-brand = Firefox\n"

    def test_serialize_term_with_attributes(self) -> None:
        """Serialize term with attributes."""
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
        resource = Resource(entries=(term,))

        result = serialize(resource)

        assert "-brand = Firefox\n" in result
        assert "    .version = 120\n" in result

    def test_serialize_term_with_comment(self) -> None:
        """Serialize term with comment."""
        term = Term(
            id=Identifier(name="brand"),
            value=Pattern(elements=(TextElement(value="Firefox"),)),
            attributes=(),
            comment=Comment(content="Brand name", type=CommentType.COMMENT),
        )
        resource = Resource(entries=(term,))

        result = serialize(resource)

        assert "# Brand name\n" in result
        assert "-brand = Firefox\n" in result


# ============================================================================
# COMMENT AND JUNK SERIALIZATION
# ============================================================================


class TestSerializerCommentJunk:
    """Test comment and junk serialization."""

    def test_serialize_standalone_comment(self) -> None:
        """Serialize standalone comment."""
        comment = Comment(content="This is a comment", type=CommentType.COMMENT)
        resource = Resource(entries=(comment,))

        result = serialize(resource)

        assert result == "# This is a comment\n"

    def test_serialize_group_comment(self) -> None:
        """Serialize group comment (##)."""
        comment = Comment(content="Group comment", type=CommentType.GROUP)
        resource = Resource(entries=(comment,))

        result = serialize(resource)

        assert result == "## Group comment\n"

    def test_serialize_resource_comment(self) -> None:
        """Serialize resource comment (###)."""
        comment = Comment(content="Resource comment", type=CommentType.RESOURCE)
        resource = Resource(entries=(comment,))

        result = serialize(resource)

        assert result == "### Resource comment\n"

    def test_serialize_multiline_comment(self) -> None:
        """Serialize multi-line comment."""
        comment = Comment(content="Line 1\nLine 2\nLine 3", type=CommentType.COMMENT)
        resource = Resource(entries=(comment,))

        result = serialize(resource)

        assert "# Line 1\n# Line 2\n# Line 3\n" in result

    def test_serialize_multiline_comment_with_empty_lines(self) -> None:
        """Serialize comment with empty lines (no trailing space on empty lines)."""
        comment = Comment(content="Line 1\n\nLine 3", type=CommentType.COMMENT)
        resource = Resource(entries=(comment,))

        result = serialize(resource)

        # Empty line should not have trailing space - "# \n" is wrong, "#\n" is correct
        assert "# Line 1\n#\n# Line 3\n" in result
        assert "# \n" not in result  # No trailing space on empty comment lines

    def test_serialize_comment_only_empty_lines(self) -> None:
        """Serialize comment that is only empty lines."""
        comment = Comment(content="\n\n", type=CommentType.COMMENT)
        resource = Resource(entries=(comment,))

        result = serialize(resource)

        # All lines should be just "#\n" without trailing space
        assert result == "#\n#\n#\n"
        assert "# \n" not in result

    def test_serialize_junk(self) -> None:
        """Serialize junk entry."""
        junk = Junk(content="invalid { syntax")
        resource = Resource(entries=(junk,))

        result = serialize(resource)

        assert result == "invalid { syntax\n"


# ============================================================================
# EXPRESSION SERIALIZATION
# ============================================================================


class TestSerializerExpressions:
    """Test expression serialization."""

    def test_serialize_string_literal(self) -> None:
        """Serialize string literal in placeable."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(Placeable(expression=StringLiteral(value="test value")),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert '{ "test value" }' in result

    def test_serialize_string_literal_with_escapes(self) -> None:
        """Serialize string literal with escape characters."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(expression=StringLiteral(value='quote: " backslash: \\')),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert r'{ "quote: \" backslash: \\" }' in result

    def test_serialize_number_literal(self) -> None:
        """Serialize number literal."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=NumberLiteral(value=42, raw="42")),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "{ 42 }" in result

    def test_serialize_variable_reference(self) -> None:
        """Serialize variable reference."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(expression=VariableReference(id=Identifier(name="count"))),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "{ $count }" in result


# ============================================================================
# REFERENCE SERIALIZATION
# ============================================================================


class TestSerializerReferences:
    """Test reference serialization."""

    def test_serialize_message_reference_simple(self) -> None:
        """Serialize message reference without attribute."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=MessageReference(
                            id=Identifier(name="other"), attribute=None
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "{ other }" in result

    def test_serialize_message_reference_with_attribute(self) -> None:
        """Serialize message reference with attribute."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=MessageReference(
                            id=Identifier(name="button"),
                            attribute=Identifier(name="tooltip"),
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "{ button.tooltip }" in result

    def test_serialize_term_reference_simple(self) -> None:
        """Serialize term reference without attribute."""
        msg = Message(
            id=Identifier(name="welcome"),
            value=Pattern(
                elements=(
                    TextElement(value="Welcome to "),
                    Placeable(
                        expression=TermReference(
                            id=Identifier(name="brand"), attribute=None, arguments=None
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "{ -brand }" in result

    def test_serialize_term_reference_with_attribute(self) -> None:
        """Serialize term reference with attribute."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(
                            id=Identifier(name="brand"),
                            attribute=Identifier(name="version"),
                            arguments=None,
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "{ -brand.version }" in result

    def test_serialize_term_reference_with_arguments(self) -> None:
        """Serialize term reference with call arguments."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(
                            id=Identifier(name="brand"),
                            attribute=None,
                            arguments=CallArguments(
                                positional=(NumberLiteral(value=1, raw="1"),), named=()
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "{ -brand(1) }" in result


# ============================================================================
# FUNCTION REFERENCE SERIALIZATION
# ============================================================================


class TestSerializerFunctionReference:
    """Test function reference serialization."""

    def test_serialize_function_no_args(self) -> None:
        """Serialize function call with no arguments."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier(name="NOW"),
                            arguments=CallArguments(positional=(), named=()),
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "{ NOW() }" in result

    def test_serialize_function_with_positional_args(self) -> None:
        """Serialize function with positional arguments."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier(name="NUMBER"),
                            arguments=CallArguments(
                                positional=(
                                    VariableReference(id=Identifier(name="value")),
                                ),
                                named=(),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "{ NUMBER($value) }" in result

    def test_serialize_function_with_multiple_positional_args(self) -> None:
        """Serialize function with multiple positional arguments."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier(name="TEST"),
                            arguments=CallArguments(
                                positional=(
                                    NumberLiteral(value=1, raw="1"),
                                    NumberLiteral(value=2, raw="2"),
                                    StringLiteral(value="three"),
                                ),
                                named=(),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert '{ TEST(1, 2, "three") }' in result

    def test_serialize_function_with_named_args(self) -> None:
        """Serialize function with named arguments."""
        msg = Message(
            id=Identifier(name="price"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier(name="NUMBER"),
                            arguments=CallArguments(
                                positional=(),
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
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "{ NUMBER(minimumFractionDigits: 2) }" in result

    def test_serialize_function_with_mixed_args(self) -> None:
        """Serialize function with both positional and named arguments."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier(name="DATETIME"),
                            arguments=CallArguments(
                                positional=(
                                    VariableReference(id=Identifier(name="date")),
                                ),
                                named=(
                                    NamedArgument(
                                        name=Identifier(name="dateStyle"),
                                        value=StringLiteral(value="long"),
                                    ),
                                    NamedArgument(
                                        name=Identifier(name="timeStyle"),
                                        value=StringLiteral(value="short"),
                                    ),
                                ),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "{ DATETIME($date, dateStyle: " in result
        assert 'timeStyle: "short") }' in result


# ============================================================================
# SELECT EXPRESSION SERIALIZATION
# ============================================================================


class TestSerializerSelectExpression:
    """Test select expression serialization."""

    def test_serialize_simple_select(self) -> None:
        """Serialize select expression with variants."""
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
                                        elements=(TextElement(value="many emails"),)
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
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "{ $count ->" in result
        assert "[one] one email" in result
        assert "*[other] many emails" in result

    def test_serialize_select_with_number_keys(self) -> None:
        """Serialize select expression with numeric variant keys."""
        msg = Message(
            id=Identifier(name="items"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=SelectExpression(
                            selector=VariableReference(id=Identifier(name="count")),
                            variants=(
                                Variant(
                                    key=NumberLiteral(value=0, raw="0"),
                                    value=Pattern(
                                        elements=(TextElement(value="no items"),)
                                    ),
                                    default=False,
                                ),
                                Variant(
                                    key=NumberLiteral(value=1, raw="1"),
                                    value=Pattern(
                                        elements=(TextElement(value="one item"),)
                                    ),
                                    default=False,
                                ),
                                Variant(
                                    key=Identifier(name="other"),
                                    value=Pattern(
                                        elements=(TextElement(value="many items"),)
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
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "[0] no items" in result
        assert "[1] one item" in result
        assert "*[other] many items" in result


# ============================================================================
# COMPLEX INTEGRATION TESTS
# ============================================================================


class TestSerializerIntegration:
    """Test serializer with complex AST structures."""

    def test_serialize_mixed_resource(self) -> None:
        """Serialize resource with comments, messages, and terms."""
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
            )
        )

        result = serialize(resource)

        assert "# Header comment\n" in result
        assert "hello = Hello\n" in result
        assert "-brand = Firefox\n" in result

    def test_serialize_complex_message_with_select(self) -> None:
        """Serialize message with select expression and variables."""
        msg = Message(
            id=Identifier(name="user-files"),
            value=Pattern(
                elements=(
                    TextElement(value="User "),
                    Placeable(expression=VariableReference(id=Identifier(name="name"))),
                    TextElement(value=" has "),
                    Placeable(
                        expression=SelectExpression(
                            selector=VariableReference(id=Identifier(name="count")),
                            variants=(
                                Variant(
                                    key=Identifier(name="one"),
                                    value=Pattern(
                                        elements=(TextElement(value="one file"),)
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
                                            TextElement(value=" files"),
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
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "User { $name } has { $count ->" in result
        assert "[one] one file" in result
        assert "*[other] { $count } files" in result

    def test_serialize_message_with_all_features(self) -> None:
        """Serialize message using all features."""
        msg = Message(
            id=Identifier(name="complex"),
            value=Pattern(
                elements=(
                    TextElement(value="Price: "),
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier(name="NUMBER"),
                            arguments=CallArguments(
                                positional=(
                                    VariableReference(id=Identifier(name="price")),
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
            attributes=(
                Attribute(
                    id=Identifier(name="tooltip"),
                    value=Pattern(elements=(TextElement(value="Product price"),)),
                ),
            ),
            comment=Comment(content="Displays formatted price", type=CommentType.COMMENT),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "# Displays formatted price\n" in result
        assert "complex = Price: { NUMBER($price, minimumFractionDigits: 2) }\n" in result
        assert "    .tooltip = Product price\n" in result


# ============================================================================
# TEXT ELEMENT ESCAPING TESTS
# ============================================================================


class TestTextElementEscaping:
    """Test that special characters in TextElements are properly escaped.

    Regression tests for LOGIC-SER-011: TextElements containing { } must be
    escaped per FTL spec to avoid placeable interpretation.
    """

    def test_escape_open_brace_in_text(self) -> None:
        """Open brace { in text must be escaped as \\{."""
        msg = Message(
            id=Identifier(name="brace"),
            value=Pattern(elements=(TextElement(value="Use {variable} syntax"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "brace = Use \\{variable\\} syntax\n" in result

    def test_escape_close_brace_in_text(self) -> None:
        """Close brace } in text must be escaped as \\}."""
        msg = Message(
            id=Identifier(name="json"),
            value=Pattern(elements=(TextElement(value='{"key": "value"}'),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # Both { and } should be escaped
        assert "json = \\{" in result
        assert "\\}" in result

    def test_escape_backslash_before_brace(self) -> None:
        """Backslash must be escaped first to prevent double-escaping.

        Without proper order: text with \\{ would become \\\\{ then \\\\\\{
        With proper order: \\ becomes \\\\ first, then { becomes \\{
        """
        msg = Message(
            id=Identifier(name="escaped"),
            value=Pattern(elements=(TextElement(value="Literal \\{ brace"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # Backslash should be escaped, then brace should be escaped
        assert "escaped = Literal \\\\\\{ brace\n" in result

    def test_preserve_text_without_special_chars(self) -> None:
        """Text without special characters should not be modified."""
        msg = Message(
            id=Identifier(name="plain"),
            value=Pattern(elements=(TextElement(value="Hello, World!"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "plain = Hello, World!\n" in result

    def test_mixed_text_and_placeables(self) -> None:
        """Text with braces alongside real placeables."""
        msg = Message(
            id=Identifier(name="mixed"),
            value=Pattern(
                elements=(
                    TextElement(value="JSON: {key} = "),
                    Placeable(expression=VariableReference(id=Identifier(name="value"))),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # The literal {key} should be escaped, but the placeable should not
        assert "mixed = JSON: \\{key\\} = { $value }\n" in result
