"""Tests for syntax.serializer: FluentSerializer, serialize(), edge cases, internal helpers.

Validates serialization of AST nodes back to FTL syntax, including control character
escaping, depth limits, junk entries, multiline patterns, and classify/escape internals.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, event, example, given
from hypothesis import strategies as st

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.enums import CommentType
from ftllexengine.syntax import serialize
from ftllexengine.syntax.ast import (
    Annotation,
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
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import (
    FluentSerializer,
    SerializationDepthError,
    SerializationValidationError,
    _classify_line,
    _escape_text,
    _LineKind,  # Private import for internal unit tests
    _validate_resource,
)

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
# TEXT ELEMENT BRACE SERIALIZATION TESTS
# ============================================================================


class TestTextElementBraceSerialization:
    """Test that literal braces in TextElements are serialized per Fluent Spec 1.0.

    Per Fluent Spec: Backslash has no escaping power in TextElements.
    Literal braces MUST be expressed as StringLiterals within Placeables:
    - { must be serialized as {"{"} (Placeable containing StringLiteral)
    - } must be serialized as {"}"} (Placeable containing StringLiteral)

    This produces valid FTL that compliant parsers accept.
    """

    def test_open_brace_becomes_string_literal_placeable(self) -> None:
        """Open brace { in text becomes {"{"} per Fluent spec."""
        msg = Message(
            id=Identifier(name="brace"),
            value=Pattern(elements=(TextElement(value="Use {variable} syntax"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # Braces become StringLiteral Placeables: { "{" }variable{ "}" }
        assert 'brace = Use { "{" }variable{ "}" } syntax\n' in result

    def test_close_brace_becomes_string_literal_placeable(self) -> None:
        """Close brace } in text becomes {"}"} per Fluent spec."""
        msg = Message(
            id=Identifier(name="json"),
            value=Pattern(elements=(TextElement(value='{"key": "value"}'),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # Both { and } become StringLiteral Placeables
        assert '{ "{" }' in result
        assert '{ "}" }' in result
        # Full pattern: { "{" }"key": "value"{ "}" }
        assert 'json = { "{" }"key": "value"{ "}" }\n' in result

    def test_backslash_not_escaped_in_text_elements(self) -> None:
        """Backslash has no special meaning in TextElements per Fluent spec.

        Per spec: backslash only has escaping power in StringLiterals,
        not in TextElements. A backslash in text is preserved as-is.
        """
        msg = Message(
            id=Identifier(name="path"),
            value=Pattern(elements=(TextElement(value="C:\\Users\\file.txt"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # Backslash preserved as-is (no escaping in TextElements)
        assert "path = C:\\Users\\file.txt\n" in result

    def test_backslash_before_brace_preserved(self) -> None:
        """Backslash before brace: backslash preserved, brace becomes placeable."""
        msg = Message(
            id=Identifier(name="escaped"),
            value=Pattern(elements=(TextElement(value="Literal \\{ brace"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # Backslash preserved, brace becomes StringLiteral Placeable
        assert 'escaped = Literal \\{ "{" } brace\n' in result

    def test_preserve_text_without_braces(self) -> None:
        """Text without braces should not be modified."""
        msg = Message(
            id=Identifier(name="plain"),
            value=Pattern(elements=(TextElement(value="Hello, World!"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "plain = Hello, World!\n" in result

    def test_mixed_text_and_placeables(self) -> None:
        """Text with literal braces alongside real placeables."""
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

        # Literal braces become StringLiteral Placeables, real placeable unchanged
        assert 'mixed = JSON: { "{" }key{ "}" } = { $value }\n' in result

    def test_multiple_consecutive_braces(self) -> None:
        """Multiple consecutive braces each become separate placeables."""
        msg = Message(
            id=Identifier(name="multi"),
            value=Pattern(elements=(TextElement(value="{{nested}}"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # Each brace becomes its own placeable
        assert 'multi = { "{" }{ "{" }'  in result
        assert '{ "}" }{ "}" }' in result

    def test_brace_at_start_of_text(self) -> None:
        """Brace at start of text element."""
        msg = Message(
            id=Identifier(name="start"),
            value=Pattern(elements=(TextElement(value="{start"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert 'start = { "{" }start\n' in result

    def test_brace_at_end_of_text(self) -> None:
        """Brace at end of text element."""
        msg = Message(
            id=Identifier(name="end"),
            value=Pattern(elements=(TextElement(value="end}"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert 'end = end{ "}" }\n' in result

    def test_only_braces(self) -> None:
        """Text containing only braces."""
        msg = Message(
            id=Identifier(name="braces"),
            value=Pattern(elements=(TextElement(value="{}"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert 'braces = { "{" }{ "}" }\n' in result


# ============================================================================
# IDENTIFIER VALIDATION TESTS
# ============================================================================


class TestIdentifierValidation:
    """Test identifier validation during serialization."""

    def test_invalid_message_id_rejected(self) -> None:
        """Invalid message identifier rejected when validate=True.

        Regression test for SER-INVALID-OUTPUT-001.
        Parser-produced ASTs have valid identifiers, but programmatically
        constructed ASTs can contain arbitrary strings. Serializer should
        validate identifiers when validate=True.
        """
        msg = Message(
            id=Identifier(name="invalid message with spaces"),
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        with pytest.raises(SerializationValidationError, match="Invalid identifier"):
            serialize(resource, validate=True)

    def test_invalid_variable_reference_rejected(self) -> None:
        """Invalid variable identifier rejected when validate=True."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=VariableReference(
                            id=Identifier(name="my var")  # Space invalid
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        with pytest.raises(SerializationValidationError, match="Invalid identifier"):
            serialize(resource, validate=True)

    def test_invalid_identifier_allowed_when_validation_disabled(self) -> None:
        """Invalid identifier allowed when validate=False."""
        msg = Message(
            id=Identifier(name="invalid id"),
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        # Should not raise exception
        result = serialize(resource, validate=False)
        assert "invalid id" in result

    def test_valid_identifier_with_hyphens_and_underscores(self) -> None:
        """Valid identifiers with hyphens and underscores pass validation."""
        msg = Message(
            id=Identifier(name="valid-id_123"),
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)
        assert "valid-id_123" in result


# ============================================================================
# EDGE CASES AND INTERNAL HELPERS (from test_serializer_edge_cases.py)
# ============================================================================


class TestControlCharacterEscaping:
    """Test StringLiteral escaping of all control characters."""

    def test_del_character_escaped_as_unicode(self) -> None:
        """DEL character (0x7F) serialized as \\u007F escape sequence."""
        # DEL is a control character that needs Unicode escaping
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(expression=StringLiteral(value="before\x7Fafter")),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        # DEL must be escaped as \u007F
        assert r"\u007F" in result
        assert "before" in result
        assert "after" in result

    def test_nul_character_escaped(self) -> None:
        """NUL character (0x00) serialized as \\u0000 escape sequence."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(expression=StringLiteral(value="a\x00b")),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        assert r"\u0000" in result

    def test_bel_character_escaped(self) -> None:
        """BEL character (0x07) serialized as \\u0007 escape sequence."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(expression=StringLiteral(value="ring\x07bell")),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        assert r"\u0007" in result

    def test_vertical_tab_escaped(self) -> None:
        """Vertical tab (0x0B) serialized as \\u000B escape sequence."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(expression=StringLiteral(value="a\x0Bb")),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        assert r"\u000B" in result

    def test_form_feed_escaped(self) -> None:
        """Form feed (0x0C) serialized as \\u000C escape sequence."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(expression=StringLiteral(value="page\x0Cbreak")),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        assert r"\u000C" in result

    def test_escape_character_escaped(self) -> None:
        """ESC character (0x1B) serialized as \\u001B escape sequence."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(expression=StringLiteral(value="before\x1Bafter")),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        assert r"\u001B" in result

    @given(
        control_char=st.one_of(
            st.integers(min_value=0x00, max_value=0x1F),  # C0 control characters
            st.just(0x7F),  # DEL
        )
    )
    @example(control_char=0x7F)  # Ensure DEL is explicitly tested
    @example(control_char=0x00)  # NUL
    @example(control_char=0x01)  # SOH
    @example(control_char=0x1F)  # Unit separator
    def test_all_control_characters_escaped_property(self, control_char: int) -> None:
        """All control characters (0x00-0x1F, 0x7F) escaped as Unicode."""
        is_del = control_char == 0x7F
        event(f"control_char=0x{control_char:02X}")
        event(f"is_del={is_del}")
        char = chr(control_char)
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(expression=StringLiteral(value=f"a{char}b")),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        # Verify Unicode escape present
        expected_escape = f"\\u{control_char:04X}"
        assert expected_escape in result

        # Verify the raw control character is NOT in the output
        # (it should be escaped)
        # Exception: newline/tab which might be normalized by string handling
        if char not in "\n\t":
            assert char not in result


class TestSerializationDepthLimitWithoutValidation:
    """Test depth limit enforcement during serialization when validation is disabled.

    Per serializer.py lines 297-299, the serialize method has a try/except
    that catches DepthLimitExceededError during the _serialize_resource call.
    This is distinct from the validation phase depth check.

    To trigger this:
    1. Disable validation (validate=False)
    2. Create AST with nesting that exceeds max_depth
    3. Depth guard triggers during serialization, not validation
    """

    def test_depth_exceeded_during_serialization_not_validation(self) -> None:
        """Depth limit enforced during serialization even when validation disabled."""
        # Create deeply nested Placeables beyond the limit
        # Start with innermost expression
        max_depth = 5
        inner_expr: StringLiteral | Placeable = StringLiteral(value="deep")

        # Build nested Placeables: each Placeable adds one depth level
        for _ in range(max_depth + 1):  # Exceed limit by 1
            inner_expr = Placeable(expression=inner_expr)

        # Type narrowing: at this point inner_expr is definitely a Placeable
        inner_placeable: Placeable = inner_expr  # type: ignore[assignment]

        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(inner_placeable,)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        # Validation is disabled - should still catch depth during serialization
        with pytest.raises(SerializationDepthError, match="nesting exceeds maximum depth"):
            serialize(resource, validate=False, max_depth=max_depth)

    def test_depth_exactly_at_limit_succeeds_without_validation(self) -> None:
        """AST exactly at depth limit serializes successfully without validation."""
        max_depth = 5
        inner_expr: StringLiteral | Placeable = StringLiteral(value="ok")

        # Build nested Placeables exactly at limit
        for _ in range(max_depth):
            inner_expr = Placeable(expression=inner_expr)

        # Type narrowing: at this point inner_expr is definitely a Placeable
        inner_placeable: Placeable = inner_expr  # type: ignore[assignment]

        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(inner_placeable,)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        # Should succeed - exactly at limit
        result = serialize(resource, validate=False, max_depth=max_depth)
        assert "ok" in result

    @given(
        depth_over_limit=st.integers(min_value=1, max_value=10),
        max_depth=st.integers(min_value=3, max_value=20),
    )
    @example(depth_over_limit=1, max_depth=5)
    @example(depth_over_limit=5, max_depth=10)
    def test_serialization_depth_property(
        self, depth_over_limit: int, max_depth: int
    ) -> None:
        """Serialization depth limit enforced regardless of validation setting."""
        total = max_depth + depth_over_limit
        event(f"max_depth={max_depth}")
        event(f"depth_over_limit={depth_over_limit}")
        event(f"total_nesting={total}")
        # Build AST exceeding depth limit
        inner_expr: StringLiteral | Placeable = StringLiteral(value="x")
        for _ in range(max_depth + depth_over_limit):
            inner_expr = Placeable(expression=inner_expr)

        # Type narrowing: at this point inner_expr is definitely a Placeable
        inner_placeable: Placeable = inner_expr  # type: ignore[assignment]

        msg = Message(
            id=Identifier(name="m"),
            value=Pattern(elements=(inner_placeable,)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        # Should raise SerializationDepthError
        with pytest.raises(SerializationDepthError):
            serialize(resource, validate=False, max_depth=max_depth)


class TestJunkWithLeadingWhitespace:
    """Test Junk entry serialization with leading whitespace.

    Per serializer.py line 321, when a Junk entry follows another entry
    and the Junk content starts with whitespace, the separator logic takes
    a different path (pass statement, no additional separator added).

    This tests the specific branch: isinstance(entry, Junk) and entry.content[0] in "\\n "
    """

    def test_junk_with_leading_newline_after_message(self) -> None:
        """Junk with leading newline after message skips adding separator."""
        msg = Message(
            id=Identifier(name="hello"),
            value=Pattern(elements=(TextElement(value="World"),)),
            attributes=(),
        )
        # Junk with leading newline - parser includes preceding whitespace
        junk = Junk(content="\ninvalid junk content")
        resource = Resource(entries=(msg, junk))

        result = serialize(resource)

        # Should not have double newline - Junk content already starts with \n
        # Result should be: "hello = World\n\ninvalid junk content\n"
        # But since Junk already has \n, we don't add another separator
        assert "hello = World\n" in result
        assert "\ninvalid junk content" in result
        # Should NOT have triple newline
        assert "\n\n\n" not in result

    def test_junk_with_leading_space_after_message(self) -> None:
        """Junk with leading space after message skips adding separator."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="value"),)),
            attributes=(),
        )
        # Junk with leading space
        junk = Junk(content=" some junk")
        resource = Resource(entries=(msg, junk))

        result = serialize(resource)

        # Junk already has leading space, so separator is skipped
        assert "test = value\n some junk" in result

    def test_junk_without_leading_whitespace_gets_separator(self) -> None:
        """Junk without leading whitespace gets normal separator."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="value"),)),
            attributes=(),
        )
        # Junk WITHOUT leading whitespace
        junk = Junk(content="junk content")
        resource = Resource(entries=(msg, junk))

        result = serialize(resource)

        # Normal separator added
        assert "test = value\n" in result
        assert "\njunk content" in result

    def test_empty_junk_content_gets_separator(self) -> None:
        """Empty Junk content gets normal separator (no [0] index access)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="value"),)),
            attributes=(),
        )
        # Empty junk - entry.content[0] won't be accessed due to short-circuit
        junk = Junk(content="")
        resource = Resource(entries=(msg, junk))

        result = serialize(resource)

        # Empty junk still gets separator
        assert "test = value\n" in result

    @given(
        leading_char=st.sampled_from(["\n", " ", "\t", "j"]),
        has_content=st.booleans(),
    )
    @example(leading_char="\n", has_content=True)
    @example(leading_char=" ", has_content=True)
    @example(leading_char="j", has_content=True)
    def test_junk_separator_logic_property(
        self, leading_char: str, has_content: bool
    ) -> None:
        """Junk separator logic handles various leading characters correctly."""
        is_ws = leading_char in ("\n", " ", "\t")
        event(f"leading_char_is_whitespace={is_ws}")
        event(f"has_content={has_content}")
        msg = Message(
            id=Identifier(name="m"),
            value=Pattern(elements=(TextElement(value="v"),)),
            attributes=(),
        )

        junk = (
            Junk(content=f"{leading_char}content")
            if has_content
            else Junk(content="")
        )

        resource = Resource(entries=(msg, junk))

        # Should not raise - serialization should handle all cases
        result = serialize(resource)
        assert isinstance(result, str)
        assert "m = v" in result


class TestPatternWithoutBraces:
    """Test Pattern serialization path when text has no braces.

    Per serializer.py line 483->467, there's an else branch when text
    contains neither { nor } characters. This tests the optimization path
    that emits text directly without brace handling.
    """

    def test_text_without_braces_direct_output(self) -> None:
        """Text without braces takes direct output path."""
        msg = Message(
            id=Identifier(name="plain"),
            value=Pattern(
                elements=(
                    TextElement(value="No braces here, just plain text!"),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        # Should contain the text as-is (no brace escaping needed)
        assert "No braces here, just plain text!" in result
        # Should NOT have any brace-related escaping
        assert '{ "{" }' not in result
        assert '{ "}" }' not in result

    def test_text_with_only_safe_punctuation(self) -> None:
        """Text with punctuation but no braces serializes directly."""
        msg = Message(
            id=Identifier(name="punct"),
            value=Pattern(
                elements=(
                    TextElement(value="Hello, world! How are you?"),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        assert "Hello, world! How are you?" in result
        # No brace escaping
        assert '{ "{" }' not in result

    def test_text_with_numbers_and_symbols(self) -> None:
        """Text with numbers and safe symbols serializes directly."""
        msg = Message(
            id=Identifier(name="data"),
            value=Pattern(
                elements=(
                    TextElement(value="Price: $42.00 (20% off)"),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        assert "Price: $42.00 (20% off)" in result

    @given(
        text=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd", "Zs"),
                whitelist_characters="!@#$%^&*()_+-=[]|;:'\",.<>?/~`",
            ),
            min_size=1,
            max_size=100,
        ).filter(lambda t: "{" not in t and "}" not in t)
    )
    @example(text="Simple text without any braces")
    @example(text="Numbers 123 and symbols !@#")
    def test_brace_free_text_property(self, text: str) -> None:
        """Text without braces always serializes without brace escaping."""
        event(f"input_len={len(text)}")
        assume(text.strip())  # Non-empty after stripping
        # Leading whitespace gets wrapped in a StringLiteral placeable for
        # roundtrip correctness (see _serialize_pattern); not this test's concern.
        assume(not text[0].isspace())

        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value=text),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # Should contain the original text
        assert text in result
        # Should NOT have brace escaping since input has no braces
        assert '{ "{" }' not in result or "{" in text  # Only if original had them
        assert '{ "}" }' not in result or "}" in text


class TestMultilinePatternIndentation:
    """Test multi-line pattern indentation handling.

    Per serializer.py lines 474-475, newlines in TextElements are replaced
    with newline + 4-space indentation for FTL continuation lines.
    """

    def test_multiline_text_indented(self) -> None:
        """Newlines in TextElement followed by 4-space indentation."""
        msg = Message(
            id=Identifier(name="multi"),
            value=Pattern(
                elements=(
                    TextElement(value="Line 1\nLine 2\nLine 3"),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        # Each newline should be followed by 4 spaces (continuation indent)
        assert "Line 1\n    Line 2\n    Line 3" in result

    def test_multiline_with_braces_indented_and_escaped(self) -> None:
        """Multiline text with braces: both indentation and brace escaping."""
        msg = Message(
            id=Identifier(name="complex"),
            value=Pattern(
                elements=(
                    TextElement(value="First {line}\nSecond }line"),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        # Should have indentation AND brace escaping
        assert "First" in result
        assert "Second" in result
        assert '{ "{" }' in result  # { escaped
        assert '{ "}" }' in result  # } escaped
        # Newline creates indentation
        assert "\n    " in result

    @given(
        lines=st.lists(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd", "Zs"),
                    min_codepoint=0x20,  # Printable ASCII and above
                ),
                min_size=1,
                max_size=50,
            ).filter(lambda t: "{" not in t and "}" not in t),
            min_size=2,
            max_size=5,
        )
    )
    @example(lines=["First line", "Second line", "Third line"])
    def test_multiline_indentation_property(self, lines: list[str]) -> None:
        """Multiline patterns always indent continuation lines with 4 spaces."""
        event(f"line_count={len(lines)}")
        assume(all(line.strip() for line in lines))  # Non-empty lines
        # Leading whitespace on the first line gets wrapped in a StringLiteral
        # placeable for roundtrip correctness; not this test's concern.
        assume(not lines[0][0].isspace())

        text = "\n".join(lines)
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value=text),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # After first line, each line should be indented with 4 spaces
        for i, line in enumerate(lines):
            if i == 0:
                # First line not indented
                assert lines[0] in result
            else:
                # Subsequent lines indented
                assert f"\n    {line}" in result or line in result


class TestMixedPatternElements:
    """Test Pattern serialization with mixed TextElement and Placeable elements.

    This ensures the elif branch at line 483 is properly covered when
    iterating through pattern elements that alternate between types.
    """

    def test_mixed_text_and_placeable_elements(self) -> None:
        """Pattern with alternating TextElement and Placeable elements."""
        msg = Message(
            id=Identifier(name="mixed"),
            value=Pattern(
                elements=(
                    TextElement(value="Start "),
                    Placeable(expression=VariableReference(id=Identifier(name="var1"))),
                    TextElement(value=" middle "),
                    Placeable(expression=VariableReference(id=Identifier(name="var2"))),
                    TextElement(value=" end"),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        assert "Start { $var1 } middle { $var2 } end" in result

    def test_multiple_consecutive_placeables(self) -> None:
        """Pattern with consecutive Placeable elements (no text between)."""
        msg = Message(
            id=Identifier(name="consecutive"),
            value=Pattern(
                elements=(
                    Placeable(expression=VariableReference(id=Identifier(name="a"))),
                    Placeable(expression=VariableReference(id=Identifier(name="b"))),
                    Placeable(expression=VariableReference(id=Identifier(name="c"))),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        assert "{ $a }{ $b }{ $c }" in result

    def test_text_then_multiple_placeables(self) -> None:
        """Pattern starting with text followed by multiple placeables."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    TextElement(value="Prefix: "),
                    Placeable(expression=StringLiteral(value="one")),
                    Placeable(expression=StringLiteral(value="two")),
                    Placeable(expression=StringLiteral(value="three")),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        assert 'Prefix: { "one" }{ "two" }{ "three" }' in result

    @given(
        num_text=st.integers(min_value=1, max_value=5),
        num_placeable=st.integers(min_value=1, max_value=5),
    )
    @example(num_text=3, num_placeable=2)
    @example(num_text=1, num_placeable=4)
    def test_mixed_pattern_property(self, num_text: int, num_placeable: int) -> None:
        """Patterns with varying numbers of text and placeable elements serialize correctly."""
        event(f"num_text={num_text}")
        event(f"num_placeable={num_placeable}")
        elements: list[TextElement | Placeable] = []

        # Alternate between text and placeable
        for i in range(max(num_text, num_placeable)):
            if i < num_text:
                elements.append(TextElement(value=f"text{i} "))
            if i < num_placeable:
                elements.append(
                    Placeable(
                        expression=VariableReference(id=Identifier(name=f"v{i}"))
                    )
                )

        msg = Message(
            id=Identifier(name="m"),
            value=Pattern(elements=tuple(elements)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)
        assert "m = " in result


class TestSelectExpressionVariantKeys:
    """Test SelectExpression with both Identifier and NumberLiteral variant keys.

    Ensures match statement at line 619-623 covers both cases completely,
    including exit paths (622->625).
    """

    def test_select_with_identifier_keys_only(self) -> None:
        """SelectExpression with all Identifier variant keys."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=SelectExpression(
                            selector=VariableReference(id=Identifier(name="count")),
                            variants=(
                                Variant(
                                    key=Identifier(name="one"),
                                    value=Pattern(
                                        elements=(TextElement(value="One item"),)
                                    ),
                                    default=False,
                                ),
                                Variant(
                                    key=Identifier(name="other"),
                                    value=Pattern(
                                        elements=(TextElement(value="Many items"),)
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

        assert "[one]" in result
        assert "*[other]" in result
        assert "One item" in result
        assert "Many items" in result

    def test_select_with_number_keys_only(self) -> None:
        """SelectExpression with all NumberLiteral variant keys."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=SelectExpression(
                            selector=VariableReference(id=Identifier(name="count")),
                            variants=(
                                Variant(
                                    key=NumberLiteral(value=1, raw="1"),
                                    value=Pattern(
                                        elements=(TextElement(value="Exactly one"),)
                                    ),
                                    default=False,
                                ),
                                Variant(
                                    key=NumberLiteral(value=0, raw="0"),
                                    value=Pattern(
                                        elements=(TextElement(value="Zero"),)
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

        assert "[1]" in result
        assert "*[0]" in result
        assert "Exactly one" in result
        assert "Zero" in result

    def test_select_with_mixed_identifier_and_number_keys(self) -> None:
        """SelectExpression with both Identifier and NumberLiteral keys."""
        msg = Message(
            id=Identifier(name="mixed"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=SelectExpression(
                            selector=VariableReference(id=Identifier(name="val")),
                            variants=(
                                Variant(
                                    key=NumberLiteral(value=0, raw="0"),
                                    value=Pattern(
                                        elements=(TextElement(value="Zero"),)
                                    ),
                                    default=False,
                                ),
                                Variant(
                                    key=NumberLiteral(value=1, raw="1"),
                                    value=Pattern(
                                        elements=(TextElement(value="One"),)
                                    ),
                                    default=False,
                                ),
                                Variant(
                                    key=Identifier(name="other"),
                                    value=Pattern(
                                        elements=(TextElement(value="Other"),)
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

        # Both NumberLiteral and Identifier cases exercised
        assert "[0]" in result
        assert "[1]" in result
        assert "*[other]" in result


class TestFunctionReferenceValidation:
    """Test FunctionReference validation path coverage.

    Ensures the FunctionReference case at line 183-193 in _validate_expression
    is fully covered, including exit paths (185->exit).
    """

    def test_function_reference_with_positional_args_validated(self) -> None:
        """FunctionReference with positional arguments passes validation."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier(name="NUMBER"),
                            arguments=CallArguments(
                                positional=(
                                    VariableReference(id=Identifier(name="count")),
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

        # Should validate successfully
        result = serialize(resource, validate=True)
        assert "NUMBER($count)" in result

    def test_function_reference_with_named_args_validated(self) -> None:
        """FunctionReference with named arguments passes validation."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier(name="DATETIME"),
                            arguments=CallArguments(
                                positional=(),
                                named=(
                                    NamedArgument(
                                        name=Identifier(name="month"),
                                        value=StringLiteral(value="long"),
                                    ),
                                    NamedArgument(
                                        name=Identifier(name="day"),
                                        value=StringLiteral(value="numeric"),
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

        # Should validate successfully
        result = serialize(resource, validate=True)
        assert "DATETIME" in result
        assert 'month: "long"' in result
        assert 'day: "numeric"' in result

    def test_function_reference_with_mixed_args_validated(self) -> None:
        """FunctionReference with both positional and named args validated."""
        msg = Message(
            id=Identifier(name="formatted"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier(name="NUMBER"),
                            arguments=CallArguments(
                                positional=(
                                    VariableReference(id=Identifier(name="amount")),
                                ),
                                named=(
                                    NamedArgument(
                                        name=Identifier(name="style"),
                                        value=StringLiteral(value="currency"),
                                    ),
                                    NamedArgument(
                                        name=Identifier(name="currency"),
                                        value=StringLiteral(value="USD"),
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

        result = serialize(resource, validate=True)
        assert "NUMBER($amount" in result
        assert 'style: "currency"' in result
        assert 'currency: "USD"' in result


# =============================================================================
# _classify_line unit tests (covers lines 358, 361)
# =============================================================================


class TestClassifyLine:
    """Direct unit tests for _classify_line continuation line classifier."""

    def test_empty_line(self) -> None:
        """Empty string classified as EMPTY."""
        kind, ws_len = _classify_line("")
        assert kind is _LineKind.EMPTY
        assert ws_len == 0

    def test_whitespace_only_single_space(self) -> None:
        """Single space classified as WHITESPACE_ONLY."""
        kind, ws_len = _classify_line(" ")
        assert kind is _LineKind.WHITESPACE_ONLY
        assert ws_len == 0

    def test_whitespace_only_multiple_spaces(self) -> None:
        """Multiple spaces classified as WHITESPACE_ONLY."""
        kind, ws_len = _classify_line("     ")
        assert kind is _LineKind.WHITESPACE_ONLY
        assert ws_len == 0

    def test_syntax_leading_dot_no_whitespace(self) -> None:
        """Dot at position 0 classified as SYNTAX_LEADING with ws_len=0."""
        kind, ws_len = _classify_line(".")
        assert kind is _LineKind.SYNTAX_LEADING
        assert ws_len == 0

    def test_syntax_leading_dot_with_whitespace(self) -> None:
        """Dot preceded by spaces classified as SYNTAX_LEADING."""
        kind, ws_len = _classify_line("   .attr")
        assert kind is _LineKind.SYNTAX_LEADING
        assert ws_len == 3

    def test_syntax_leading_asterisk(self) -> None:
        """Asterisk preceded by spaces classified as SYNTAX_LEADING."""
        kind, ws_len = _classify_line("   *")
        assert kind is _LineKind.SYNTAX_LEADING
        assert ws_len == 3

    def test_syntax_leading_bracket(self) -> None:
        """Open bracket preceded by spaces classified as SYNTAX_LEADING."""
        kind, ws_len = _classify_line("  [key]")
        assert kind is _LineKind.SYNTAX_LEADING
        assert ws_len == 2

    def test_normal_text(self) -> None:
        """Regular text classified as NORMAL."""
        kind, ws_len = _classify_line("hello")
        assert kind is _LineKind.NORMAL
        assert ws_len == 0

    def test_normal_text_with_leading_whitespace(self) -> None:
        """Text with leading whitespace but non-syntax first char is NORMAL."""
        kind, ws_len = _classify_line("   hello")
        assert kind is _LineKind.NORMAL
        assert ws_len == 0

    def test_dot_after_text_is_normal(self) -> None:
        """Dot NOT as first non-ws character is NORMAL."""
        kind, ws_len = _classify_line("x.y")
        assert kind is _LineKind.NORMAL
        assert ws_len == 0


# =============================================================================
# _escape_text unit tests (covers brace escaping paths)
# =============================================================================


class TestEscapeText:
    """Direct unit tests for _escape_text brace escaping."""

    def test_no_braces(self) -> None:
        """Text without braces passes through unchanged."""
        output: list[str] = []
        _escape_text("hello world", output)
        assert "".join(output) == "hello world"

    def test_open_brace(self) -> None:
        """Open brace escaped as StringLiteral placeable."""
        output: list[str] = []
        _escape_text("before{after", output)
        assert "".join(output) == 'before{ "{" }after'

    def test_close_brace(self) -> None:
        """Close brace escaped as StringLiteral placeable."""
        output: list[str] = []
        _escape_text("x}y", output)
        assert "".join(output) == 'x{ "}" }y'

    def test_both_braces(self) -> None:
        """Both brace types escaped."""
        output: list[str] = []
        _escape_text("{}", output)
        assert "".join(output) == '{ "{" }{ "}" }'

    def test_empty_text(self) -> None:
        """Empty text produces no output."""
        output: list[str] = []
        _escape_text("", output)
        assert output == []

    def test_only_open_brace(self) -> None:
        """Single open brace."""
        output: list[str] = []
        _escape_text("{", output)
        assert "".join(output) == '{ "{" }'

    def test_braces_in_middle_of_text(self) -> None:
        """Braces surrounded by text."""
        output: list[str] = []
        _escape_text("a{b}c", output)
        assert "".join(output) == 'a{ "{" }b{ "}" }c'

    def test_consecutive_braces(self) -> None:
        """Multiple consecutive braces."""
        output: list[str] = []
        _escape_text("{{", output)
        assert "".join(output) == '{ "{" }{ "{" }'


# =============================================================================
# _emit_classified_line integration tests (covers lines 742-751)
# =============================================================================


class TestEmitClassifiedLineCoverage:
    """Roundtrip tests that exercise _emit_classified_line branches."""

    _parser = FluentParserV1()

    def _roundtrip_check(self, result: str) -> None:
        """Verify parse-serialize roundtrip produces no Junk and is idempotent."""
        reparsed = self._parser.parse(result)
        assert not any(isinstance(e, Junk) for e in reparsed.entries)
        s2 = serialize(reparsed)
        assert result == s2

    def test_whitespace_only_continuation_line(self) -> None:
        """Multiline text with whitespace-only continuation (lines 742-744)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(TextElement(value="line1\n   \nline3"),)
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert '{ "   " }' in result
        self._roundtrip_check(result)

    def test_syntax_leading_dot(self) -> None:
        """Continuation line with dot as first non-ws char (lines 746-751)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(TextElement(value="line1\n.attr"),)
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert '{ "." }' in result
        self._roundtrip_check(result)

    def test_syntax_leading_with_ws_prefix(self) -> None:
        """Syntax char preceded by whitespace (ws_len > 0 branch).

        Content spaces before the syntax char are wrapped in a StringLiteral
        placeable so the parser cannot absorb them as structural indent.
        """
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(TextElement(value="line1\n   .something"),)
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert '{ "   " }' in result  # Content spaces wrapped
        assert '{ "." }' in result    # Syntax char wrapped
        self._roundtrip_check(result)

    def test_syntax_leading_with_remaining_text(self) -> None:
        """Syntax char followed by additional text (remaining branch)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(TextElement(value="line1\n*default value"),)
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert '{ "*" }' in result
        assert "default value" in result
        self._roundtrip_check(result)

    def test_syntax_leading_bracket_with_content(self) -> None:
        """Bracket syntax char with trailing content."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(TextElement(value="line1\n[not a variant"),)
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert '{ "[" }' in result
        self._roundtrip_check(result)

    def test_syntax_leading_ws_prefix_roundtrip_promoted(self) -> None:
        """Content spaces before syntax char survive parse-serialize roundtrip.

        Promoted from Atheris fuzzer finding (finding_0001): convergence failure
        S(AST) != S(P(S(AST))) when continuation line had content whitespace
        before a wrapped syntax character. The parser absorbed content spaces
        as structural indent during common-indent stripping.
        """
        msg = Message(
            id=Identifier(name="fuec"),
            value=Pattern(
                elements=(
                    TextElement(value="    dS7aQ\n      .h?Q"),
                )
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        # Leading 4 spaces wrapped at pattern level
        assert '{ "    " }' in result
        # Content spaces before syntax char wrapped at line level
        assert '{ "      " }' in result
        assert '{ "." }' in result
        self._roundtrip_check(result)

    def test_syntax_char_only_no_remaining(self) -> None:
        """Continuation line is just a syntax char, no remaining text (750->exit)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(TextElement(value="line1\n."),)
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert '{ "." }' in result
        reparsed = self._parser.parse(result)
        assert not any(isinstance(e, Junk) for e in reparsed.entries)


# =============================================================================
# Pattern edge cases (covers lines 643->645, 699-700, 723->690, 871->874)
# =============================================================================


class TestPatternEmissionEdgeCases:
    """Tests for pattern serialization edge cases."""

    _parser = FluentParserV1()

    def test_first_text_element_all_spaces(self) -> None:
        """First TextElement is all spaces: leading_ws consumed entirely (lines 699-700)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    TextElement(value="   "),
                    Placeable(
                        expression=VariableReference(id=Identifier(name="x"))
                    ),
                )
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert '{ "   " }' in result
        assert "$x" in result

    def test_placeable_not_last_element(self) -> None:
        """Placeable followed by TextElement (loop continuation 723->690)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=VariableReference(
                            id=Identifier(name="name")
                        )
                    ),
                    TextElement(value=" said hello"),
                )
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert "$name" in result
        assert "said hello" in result

    def test_intra_element_separate_line_trigger(self) -> None:
        """Single TextElement with embedded newline + NORMAL leading ws (643->645)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    TextElement(
                        value="line1\n  normal with leading whitespace"
                    ),
                )
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        # Separate-line mode activated: pattern starts on new line
        assert result.startswith("test = \n    ")
        # Roundtrip
        reparsed = self._parser.parse(result)
        assert not any(isinstance(e, Junk) for e in reparsed.entries)

    def _roundtrip_convergence(self, source: str) -> None:
        """Verify S(P(x)) == S(P(S(P(x)))) for an FTL source string."""
        parsed = self._parser.parse(source)
        s1 = serialize(parsed)
        reparsed = self._parser.parse(s1)
        s2 = serialize(reparsed)
        assert s1 == s2, f"Convergence failure:\nS1: {s1!r}\nS2: {s2!r}"

    def test_cross_element_ws_only_no_separate_line_promoted(self) -> None:
        """WHITESPACE_ONLY cross-element does not trigger separate-line mode.

        Promoted from Atheris roundtrip fuzzer finding: convergence failure
        S(P(x)) != S(P(S(P(x)))) when a whitespace-only TextElement followed
        a newline-ending TextElement. The cross-element check triggered
        separate-line mode; the serializer wrapped the spaces in a Placeable;
        on re-parse the Placeable was opaque to the cross-element check,
        so separate-line mode did not trigger, producing different output.
        """
        self._roundtrip_convergence("aaaaa =\n    h\n           \n")

    def test_cross_element_ws_only_direct_ast(self) -> None:
        """Cross-element WHITESPACE_ONLY: inline mode, content wrapped."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    TextElement(value="h\n"),
                    TextElement(value="       "),
                )
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        # Should NOT use separate-line mode (WHITESPACE_ONLY handled by wrapping)
        assert result.startswith("test = h")
        assert '{ "       " }' in result
        reparsed = self._parser.parse(result)
        assert not any(isinstance(e, Junk) for e in reparsed.entries)
        s2 = serialize(reparsed)
        assert result == s2

    def test_cross_element_syntax_leading_no_separate_line(self) -> None:
        """Cross-element SYNTAX_LEADING: inline mode, content wrapped."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    TextElement(value="h\n"),
                    TextElement(value="   .dotcontent"),
                )
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        # Should NOT use separate-line mode (SYNTAX_LEADING handled by wrapping)
        assert result.startswith("test = h")
        assert '{ "   " }' in result
        assert '{ "." }' in result
        reparsed = self._parser.parse(result)
        assert not any(isinstance(e, Junk) for e in reparsed.entries)
        s2 = serialize(reparsed)
        assert result == s2

    def test_cross_element_normal_still_triggers_separate_line(self) -> None:
        """Cross-element NORMAL: separate-line mode correctly activates."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    TextElement(value="h\n"),
                    TextElement(value="  normal text"),
                )
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        # NORMAL with leading whitespace needs separate-line mode
        assert result.startswith("test = \n    ")
        reparsed = self._parser.parse(result)
        assert not any(isinstance(e, Junk) for e in reparsed.entries)

    def test_number_literal_variant_key(self) -> None:
        """SelectExpression with NumberLiteral variant key (line 871->874)."""
        sel = SelectExpression(
            selector=VariableReference(id=Identifier(name="count")),
            variants=(
                Variant(
                    key=NumberLiteral(value=1, raw="1"),
                    value=Pattern(
                        elements=(TextElement(value="one item"),)
                    ),
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
        msg = Message(
            id=Identifier(name="items"),
            value=Pattern(
                elements=(Placeable(expression=sel),)
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert "[1]" in result
        assert "[other]" in result


# =============================================================================
# Defensive re-raise tests (covers lines 286, 449)
# =============================================================================


class TestDefensiveReRaises:
    """Test defensive re-raise paths for non-RESOLUTION FrozenFluentError."""

    def test_validate_resource_non_resolution_error_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-RESOLUTION FrozenFluentError re-raised from validation (line 286)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="hello"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        def fake_validate_pattern(
            _pattern: Pattern,
            _context: str,
            _depth_guard: object,
        ) -> None:
            raise FrozenFluentError(
                message="Test non-resolution error",
                category=ErrorCategory.PARSE,
            )

        monkeypatch.setattr(
            "ftllexengine.syntax.serializer._validate_pattern",
            fake_validate_pattern,
        )

        with pytest.raises(FrozenFluentError, match="non-resolution"):
            _validate_resource(resource)

    def test_serialize_non_resolution_error_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Non-RESOLUTION FrozenFluentError re-raised from serialization (line 449)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="hello"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        def fake_serialize_resource(
            _self: object,
            _node: Resource,
            _output: list[str],
            _depth_guard: object,
        ) -> None:
            raise FrozenFluentError(
                message="Test serialize non-resolution",
                category=ErrorCategory.PARSE,
            )

        monkeypatch.setattr(
            "ftllexengine.syntax.serializer.FluentSerializer._serialize_resource",
            fake_serialize_resource,
        )

        with pytest.raises(FrozenFluentError, match="serialize non-resolution"):
            serialize(resource, validate=False)


class TestSerializerSelectorDepthGuard:
    """Serializer wraps SelectExpression selector in depth guard.

    A well-formed SelectExpression with a variable selector serializes normally.
    A malformed AST where SelectExpression is nested as its own selector (impossible
    in parsed FTL, but constructible via the API) must raise SerializationDepthError
    before triggering a RecursionError.
    """

    def test_valid_select_expression_serializes(self) -> None:
        """SelectExpression with variable selector serializes to valid FTL."""
        from ftllexengine.syntax import serialize  # noqa: PLC0415

        select = SelectExpression(
            selector=VariableReference(id=Identifier("x")),
            variants=(
                Variant(
                    key=NumberLiteral(raw="1", value=1),
                    value=Pattern(elements=(TextElement("One"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement("Other"),)),
                    default=True,
                ),
            ),
        )
        msg = Message(
            id=Identifier("msg"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        assert "msg" in result
        assert "$x ->" in result

    def test_deeply_nested_selector_raises_depth_error(self) -> None:
        """Malformed deeply-nested SelectExpression selector raises SerializationDepthError."""
        from ftllexengine.syntax import serialize  # noqa: PLC0415

        def make_nested_select(depth: int) -> SelectExpression:
            if depth == 0:
                return SelectExpression(
                    selector=VariableReference(id=Identifier("x")),
                    variants=(
                        Variant(
                            key=Identifier("a"),
                            value=Pattern(elements=(TextElement("A"),)),
                            default=False,
                        ),
                        Variant(
                            key=Identifier("other"),
                            value=Pattern(elements=(TextElement("B"),)),
                            default=True,
                        ),
                    ),
                )
            inner = make_nested_select(depth - 1)
            # Intentionally malformed: SelectExpression as its own selector
            return SelectExpression(
                selector=inner,  # type: ignore[arg-type]
                variants=(
                    Variant(
                        key=Identifier("a"),
                        value=Pattern(elements=(TextElement("A"),)),
                        default=False,
                    ),
                    Variant(
                        key=Identifier("other"),
                        value=Pattern(elements=(TextElement("B"),)),
                        default=True,
                    ),
                ),
            )

        nested = make_nested_select(150)
        msg = Message(
            id=Identifier("msg"),
            value=Pattern(elements=(Placeable(expression=nested),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        with pytest.raises(SerializationDepthError):
            serialize(resource, max_depth=50)


# ============================================================================
# SERIALIZER BRANCH COVERAGE
# ============================================================================


class TestSerializerBranchCoverage:
    """Test serializer branch coverage."""

    def test_serialize_junk_entry(self) -> None:
        """Junk entry without annotations is serialized as its raw content."""
        junk = Junk(content="invalid content here")
        resource = Resource(entries=(junk,))

        result = serialize(resource)

        assert "invalid content here" in result

    def test_serialize_text_without_braces(self) -> None:
        """Message with plain text content serializes correctly."""
        message = Message(
            id=Identifier("simple"),
            value=Pattern(elements=(TextElement("Plain text without braces"),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "simple = Plain text without braces" in result

    def test_serialize_text_with_braces(self) -> None:
        """Text with literal braces serializes via StringLiteral placeables."""
        message = Message(
            id=Identifier("braced"),
            value=Pattern(
                elements=(
                    TextElement("a"),
                    Placeable(expression=StringLiteral(value="{")),
                    TextElement("b"),
                    Placeable(expression=StringLiteral(value="}")),
                    TextElement("c"),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "braced" in result

    def test_serialize_select_expression(self) -> None:
        """SelectExpression with default variant serializes with *[other]."""
        select = SelectExpression(
            selector=VariableReference(id=Identifier("count")),
            variants=(
                Variant(
                    key=Identifier("one"),
                    value=Pattern(elements=(TextElement("One item"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement("Many items"),)),
                    default=True,
                ),
            ),
        )

        message = Message(
            id=Identifier("plural"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "plural" in result
        assert "*[other]" in result

    def test_serialize_number_literal_variant_key(self) -> None:
        """Variant with NumberLiteral key serializes as [1]."""
        select = SelectExpression(
            selector=VariableReference(id=Identifier("num")),
            variants=(
                Variant(
                    key=NumberLiteral(value=1, raw="1"),
                    value=Pattern(elements=(TextElement("One"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement("Other"),)),
                    default=True,
                ),
            ),
        )

        message = Message(
            id=Identifier("numkey"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "[1]" in result
        assert "*[other]" in result

    def test_serialize_nested_placeable(self) -> None:
        """Nested Placeable (Placeable inside Placeable) serializes with double braces."""
        inner = Placeable(expression=VariableReference(id=Identifier("inner")))
        outer = Placeable(expression=inner)

        message = Message(
            id=Identifier("nested"),
            value=Pattern(elements=(outer,)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "{ { $inner } }" in result


class TestSerializerBranchCoverageExtended:
    """Extended serializer branch coverage tests."""

    def test_serialize_message_with_comment(self) -> None:
        """Message with attached comment serializes comment on separate line."""
        comment = Comment(content="Message comment", type=CommentType.COMMENT)
        message = Message(
            id=Identifier("commented"),
            value=Pattern(elements=(TextElement("Value"),)),
            attributes=(),
            comment=comment,
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "# Message comment" in result
        assert "commented = Value" in result

    def test_serialize_term_with_attributes(self) -> None:
        """Term with attributes serializes term and all attributes."""
        term = Term(
            id=Identifier("brand"),
            value=Pattern(elements=(TextElement("Firefox"),)),
            attributes=(
                Attribute(
                    id=Identifier("gender"),
                    value=Pattern(elements=(TextElement("masculine"),)),
                ),
            ),
        )
        resource = Resource(entries=(term,))

        result = serialize(resource)

        assert "-brand = Firefox" in result
        assert ".gender = masculine" in result

    def test_serialize_function_with_named_args(self) -> None:
        """Function call with named arguments serializes with correct syntax."""
        func_ref = FunctionReference(
            id=Identifier("NUMBER"),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier("count")),),
                named=(
                    NamedArgument(
                        name=Identifier("style"),
                        value=StringLiteral(value="percent"),
                    ),
                ),
            ),
        )

        message = Message(
            id=Identifier("percent"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "NUMBER" in result
        assert "style" in result


class TestSerializerJunkCoverage:
    """Junk entry with annotations serializes raw content."""

    def test_serialize_junk_entry_with_annotations(self) -> None:
        """Junk entry with annotations is serialized as its raw content."""
        junk = Junk(
            content="this is not valid FTL",
            annotations=(
                Annotation(code="E0003", message="Expected token: ="),
            ),
        )
        resource = Resource(entries=(junk,))

        ftl = serialize(resource)

        assert "this is not valid FTL" in ftl


class TestSerializerPlaceableCoverage:
    """Placeable serialization branch coverage."""

    def test_serialize_placeable_in_pattern(self) -> None:
        """Placeable in pattern serializes with correct brace syntax."""
        placeable = Placeable(expression=VariableReference(id=Identifier(name="name")))
        pattern = Pattern(elements=(TextElement(value="Hello "), placeable))
        message = Message(
            id=Identifier(name="greeting"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "{ $name }" in ftl


class TestSerializerNumberLiteralVariantKeyCoverage:
    """NumberLiteral variant key serialization."""

    def test_serialize_select_with_number_literal_key(self) -> None:
        """Variant with NumberLiteral keys serializes as [1], [2], *[other]."""
        variant1 = Variant(
            key=NumberLiteral(value=1, raw="1"),
            value=Pattern(elements=(TextElement(value="one item"),)),
            default=False,
        )
        variant2 = Variant(
            key=NumberLiteral(value=2, raw="2"),
            value=Pattern(elements=(TextElement(value="two items"),)),
            default=False,
        )
        variant_other = Variant(
            key=Identifier(name="other"),
            value=Pattern(elements=(TextElement(value="many items"),)),
            default=True,
        )
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier(name="count")),
            variants=(variant1, variant2, variant_other),
        )
        placeable = Placeable(expression=select_expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="items"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "[1]" in ftl
        assert "[2]" in ftl
        assert "*[other]" in ftl


class TestSerializerStringLiteralEscapesCoverage:
    """Control character escaping in StringLiteral values."""

    def test_serialize_string_literal_with_tab(self) -> None:
        """Tab character in StringLiteral is escaped as \\u0009."""
        expr = StringLiteral(value="Hello\tWorld")
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="tabbed"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "\\u0009" in ftl

    def test_serialize_string_literal_with_newline(self) -> None:
        """Newline character in StringLiteral is escaped as \\u000A."""
        expr = StringLiteral(value="Line1\nLine2")
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="multiline"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "\\u000A" in ftl

    def test_serialize_string_literal_with_carriage_return(self) -> None:
        """Carriage return in StringLiteral is escaped as \\u000D."""
        expr = StringLiteral(value="Line1\rLine2")
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="crlf"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "\\u000D" in ftl


class TestSerializerBranchExhaustive:
    """Exhaustive branch coverage for serializer dispatch."""

    def test_serialize_empty_pattern(self) -> None:
        """Pattern with no elements serializes as empty value line."""
        pattern = Pattern(elements=())
        message = Message(
            id=Identifier(name="empty"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)
        assert "empty = \n" in ftl

    def test_serialize_text_only_pattern(self) -> None:
        """Pattern with multiple TextElements concatenates them."""
        pattern = Pattern(
            elements=(
                TextElement(value="Hello "),
                TextElement(value="World"),
                TextElement(value="!"),
            )
        )
        message = Message(
            id=Identifier(name="greeting"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)
        assert "greeting = Hello World!\n" in ftl

    def test_serialize_multiple_junk_entries(self) -> None:
        """Multiple Junk entries all serialize as their raw content."""
        junk1 = Junk(content="bad syntax 1")
        junk2 = Junk(content="bad syntax 2")
        resource = Resource(entries=(junk1, junk2))

        ftl = serialize(resource)
        assert "bad syntax 1" in ftl
        assert "bad syntax 2" in ftl

    def test_serialize_select_number_only_variants(self) -> None:
        """Select with only NumberLiteral keys serializes correctly."""
        variants = (
            Variant(
                key=NumberLiteral(value=0, raw="0"),
                value=Pattern(elements=(TextElement(value="zero"),)),
                default=False,
            ),
            Variant(
                key=NumberLiteral(value=1, raw="1"),
                value=Pattern(elements=(TextElement(value="one"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier(name="n")),
            variants=variants,
        )
        placeable = Placeable(expression=select_expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="count"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)
        assert "[0] zero" in ftl
        assert "*[1] one" in ftl


class TestSerializerVariantCountProperty:
    """Property-based test for serializer with varying variant counts."""

    @given(
        st.integers(min_value=1, max_value=10),
    )
    def test_serializer_handles_multiple_variants(self, variant_count: int) -> None:
        """Serializer handles select expressions with varying variant counts."""
        event(f"variant_count={variant_count}")
        variants = [
            Variant(
                key=Identifier(f"key{i}"),
                value=Pattern(elements=(TextElement(f"Value {i}"),)),
                default=(i == variant_count - 1),
            )
            for i in range(variant_count)
        ]

        select = SelectExpression(
            selector=VariableReference(id=Identifier("sel")),
            variants=tuple(variants),
        )

        message = Message(
            id=Identifier("multi"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        for i in range(variant_count):
            assert f"key{i}" in result
