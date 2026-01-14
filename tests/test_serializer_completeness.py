"""Systematic serializer completeness testing.

This module provides comprehensive coverage of all AST node types and their
combinations through the serializer. It ensures that every AST node type,
with all possible attribute combinations, can be serialized correctly.

Testing Strategy:
    - Matrix-based testing: All node types × all attribute combinations
    - Focus on uncovered lines in serializer.py
    - Verify serialization doesn't crash and produces valid output
    - Where possible, verify parse → serialize → parse roundtrip

Target Coverage (serializer.py):
    - Lines 76-77: Message with comment
    - Lines 97-112: Term serialization (entire method)
    - Lines 89-90: Message with attributes
    - Lines 116-117: Attribute serialization
    - Lines 145-146: StringLiteral expression
    - Lines 149: NumberLiteral expression
    - Lines 155-157: MessageReference
    - Lines 160-164: TermReference with attribute/arguments
    - Lines 167-168: FunctionReference
    - Lines 175-190: CallArguments (positional and named)

See SYSTEM 5 in the testing strategy document.
"""

import pytest

from ftllexengine.enums import CommentType
from ftllexengine.syntax.ast import (
    Attribute,
    CallArguments,
    Comment,
    FunctionReference,
    Identifier,
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
from ftllexengine.syntax.serializer import serialize


class TestMessageSerialization:
    """Test all Message node variations.

    Matrix dimensions:
        - value: present / None
        - attributes: 0 / 1 / many
        - comment: present / None
    """

    def test_message_simple_value_only(self):
        """Message with value, no attributes, no comment.

        Baseline case - most common message type.
        """
        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="Hello"),)),
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "test = Hello\n" in ftl
        assert ftl.strip() == "test = Hello"

    def test_message_with_comment(self):
        """Lines 76-77: Message with comment.

        Target: Uncovered comment serialization in Message
        """
        message = Message(
            id=Identifier(name="greeting"),
            value=Pattern(elements=(TextElement(value="Hello World"),)),
            attributes=(),
            comment=Comment(content="A friendly greeting", type=CommentType.COMMENT),
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "# A friendly greeting\n" in ftl
        assert "greeting = Hello World\n" in ftl

    def test_message_with_single_attribute(self):
        """Lines 89-90: Message with one attribute."""
        attribute = Attribute(
            id=Identifier(name="tooltip"),
            value=Pattern(elements=(TextElement(value="Hover text"),)),
        )
        message = Message(
            id=Identifier(name="button"),
            value=Pattern(elements=(TextElement(value="Click me"),)),
            attributes=(attribute,),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "button = Click me\n" in ftl
        assert "    .tooltip = Hover text\n" in ftl

    def test_message_with_multiple_attributes(self):
        """Lines 89-90: Message with multiple attributes."""
        attr1 = Attribute(
            id=Identifier(name="title"),
            value=Pattern(elements=(TextElement(value="Button Title"),)),
        )
        attr2 = Attribute(
            id=Identifier(name="aria-label"),
            value=Pattern(elements=(TextElement(value="Accessible Label"),)),
        )
        attr3 = Attribute(
            id=Identifier(name="placeholder"),
            value=Pattern(elements=(TextElement(value="Enter text"),)),
        )
        message = Message(
            id=Identifier(name="input-field"),
            value=Pattern(elements=(TextElement(value="Default value"),)),
            attributes=(attr1, attr2, attr3),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "input-field = Default value\n" in ftl
        assert "    .title = Button Title\n" in ftl
        assert "    .aria-label = Accessible Label\n" in ftl
        assert "    .placeholder = Enter text\n" in ftl

    def test_message_attributes_only_no_value(self):
        """Message with attributes but no value.

        This is a valid Fluent construct - message can have just attributes.
        """
        attribute = Attribute(
            id=Identifier(name="tooltip"),
            value=Pattern(elements=(TextElement(value="Hover text"),)),
        )
        message = Message(
            id=Identifier(name="button"),
            value=None,  # No value!
            attributes=(attribute,),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        # Should serialize just the identifier and attributes
        assert "button" in ftl
        assert ".tooltip = Hover text" in ftl
        # Should NOT have " = " for the message itself
        lines = ftl.strip().split("\n")
        assert lines[0] == "button"

    def test_message_with_comment_and_attributes(self):
        """Lines 76-77, 89-90: Message with both comment and attributes."""
        attribute = Attribute(
            id=Identifier(name="accesskey"),
            value=Pattern(elements=(TextElement(value="S"),)),
        )
        message = Message(
            id=Identifier(name="save-button"),
            value=Pattern(elements=(TextElement(value="Save"),)),
            attributes=(attribute,),
            comment=Comment(content="Save button text", type=CommentType.COMMENT),
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "# Save button text\n" in ftl
        assert "save-button = Save\n" in ftl
        assert "    .accesskey = S\n" in ftl


class TestTermSerialization:
    """Test all Term node variations.

    Lines 97-112: Entire visit_Term method uncovered!
    This is the most critical gap in serializer coverage.

    Matrix dimensions:
        - attributes: 0 / 1 / many
        - comment: present / None
    """

    def test_term_simple_no_attributes(self):
        """Lines 97-112: Basic term serialization.

        Example: -brand = Firefox
        """
        term = Term(
            id=Identifier(name="brand"),
            value=Pattern(elements=(TextElement(value="Firefox"),)),
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(term,))

        ftl = serialize(resource)

        assert "-brand = Firefox\n" in ftl
        assert ftl.strip() == "-brand = Firefox"

    def test_term_with_comment(self):
        """Lines 97-99: Term with comment."""
        term = Term(
            id=Identifier(name="brand-name"),
            value=Pattern(elements=(TextElement(value="Firefox Browser"),)),
            attributes=(),
            comment=Comment(content="Official brand name", type=CommentType.COMMENT),
        )
        resource = Resource(entries=(term,))

        ftl = serialize(resource)

        assert "# Official brand name\n" in ftl
        assert "-brand-name = Firefox Browser\n" in ftl

    def test_term_with_single_attribute(self):
        """Lines 108-110: Term with one attribute."""
        attribute = Attribute(
            id=Identifier(name="short"),
            value=Pattern(elements=(TextElement(value="FX"),)),
        )
        term = Term(
            id=Identifier(name="product"),
            value=Pattern(elements=(TextElement(value="Firefox"),)),
            attributes=(attribute,),
            comment=None,
        )
        resource = Resource(entries=(term,))

        ftl = serialize(resource)

        assert "-product = Firefox\n" in ftl
        assert "    .short = FX\n" in ftl

    def test_term_with_multiple_attributes(self):
        """Lines 108-110: Term with multiple attributes."""
        attr1 = Attribute(
            id=Identifier(name="nominative"),
            value=Pattern(elements=(TextElement(value="Firefox"),)),
        )
        attr2 = Attribute(
            id=Identifier(name="genitive"),
            value=Pattern(elements=(TextElement(value="Firefox's"),)),
        )
        attr3 = Attribute(
            id=Identifier(name="accusative"),
            value=Pattern(elements=(TextElement(value="Firefox"),)),
        )
        term = Term(
            id=Identifier(name="app-name"),
            value=Pattern(elements=(TextElement(value="Firefox"),)),
            attributes=(attr1, attr2, attr3),
            comment=None,
        )
        resource = Resource(entries=(term,))

        ftl = serialize(resource)

        assert "-app-name = Firefox\n" in ftl
        assert "    .nominative = Firefox\n" in ftl
        assert "    .genitive = Firefox's\n" in ftl
        assert "    .accusative = Firefox\n" in ftl

    def test_term_with_comment_and_attributes(self):
        """Lines 97-112: Term with both comment and attributes."""
        attribute = Attribute(
            id=Identifier(name="short"),
            value=Pattern(elements=(TextElement(value="FX"),)),
        )
        term = Term(
            id=Identifier(name="brand"),
            value=Pattern(elements=(TextElement(value="Firefox"),)),
            attributes=(attribute,),
            comment=Comment(content="Brand with variations", type=CommentType.COMMENT),
        )
        resource = Resource(entries=(term,))

        ftl = serialize(resource)

        assert "# Brand with variations\n" in ftl
        assert "-brand = Firefox\n" in ftl
        assert "    .short = FX\n" in ftl

    def test_term_with_select_expression(self):
        """Lines 97-112: Term with complex pattern (select expression)."""
        variant1 = Variant(
            key=Identifier(name="nominative"),  # VariantKey is Identifier | NumberLiteral
            value=Pattern(elements=(TextElement(value="Firefox"),)),
            default=False,
        )
        variant2 = Variant(
            key=Identifier(name="accusative"),
            value=Pattern(elements=(TextElement(value="Firefoxa"),)),
            default=True,
        )
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier(name="case")),
            variants=(variant1, variant2),
        )
        pattern = Pattern(elements=(Placeable(expression=select_expr),))

        term = Term(
            id=Identifier(name="brand-name"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(term,))

        ftl = serialize(resource)

        assert "-brand-name = " in ftl
        assert "$case ->" in ftl
        assert "[nominative] Firefox" in ftl
        assert "*[accusative] Firefoxa" in ftl


class TestExpressionSerialization:
    """Test all Expression node types.

    Target uncovered expression types:
        - Lines 145-146: StringLiteral
        - Lines 149: NumberLiteral
        - Lines 155-157: MessageReference
        - Lines 160-164: TermReference with attribute/arguments
        - Lines 167-168: FunctionReference
    """

    def test_string_literal(self):
        """Lines 145-146: StringLiteral in expression."""
        expr = StringLiteral(value="Hello World")
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="test"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert 'test = { "Hello World" }' in ftl

    def test_string_literal_with_escapes(self):
        """Lines 145-146: StringLiteral with special characters requiring escapes."""
        # Test backslash escape
        expr = StringLiteral(value="C:\\Users\\test")
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="path"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        # Should escape backslashes
        assert '{ "C:\\\\Users\\\\test" }' in ftl

    def test_string_literal_with_quotes(self):
        """Lines 145-146: StringLiteral with embedded quotes."""
        expr = StringLiteral(value='Say "Hello"')
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="greeting"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        # Should escape quotes
        assert '{ "Say \\"Hello\\"" }' in ftl

    def test_number_literal(self):
        """Line 149: NumberLiteral in expression."""
        expr = NumberLiteral(value=42, raw="42")
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="answer"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "answer = { 42 }" in ftl

    def test_number_literal_decimal(self):
        """Line 149: NumberLiteral with decimal."""
        from decimal import Decimal  # noqa: PLC0415
        expr = NumberLiteral(value=Decimal("3.14159"), raw="3.14159")
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="pi"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "pi = { 3.14159 }" in ftl

    def test_message_reference_no_attribute(self):
        """Lines 155-157: MessageReference without attribute."""
        expr = MessageReference(id=Identifier(name="other-message"), attribute=None)
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="test"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "test = { other-message }" in ftl

    def test_message_reference_with_attribute(self):
        """Lines 155-157: MessageReference with attribute."""
        expr = MessageReference(
            id=Identifier(name="button"), attribute=Identifier(name="tooltip")
        )
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="help"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "help = { button.tooltip }" in ftl

    def test_term_reference_basic(self):
        """Lines 160-164: TermReference without attribute or arguments."""
        expr = TermReference(
            id=Identifier(name="brand"), attribute=None, arguments=None
        )
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="welcome"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "welcome = { -brand }" in ftl

    def test_term_reference_with_attribute(self):
        """Lines 161-162: TermReference with attribute."""
        expr = TermReference(
            id=Identifier(name="brand"),
            attribute=Identifier(name="short"),
            arguments=None,
        )
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="title"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "title = { -brand.short }" in ftl

    def test_term_reference_with_arguments(self):
        """Lines 163-164: TermReference with arguments."""
        named_arg = NamedArgument(
            name=Identifier(name="case"),
            value=StringLiteral(value="nominative"),
        )
        call_args = CallArguments(positional=(), named=(named_arg,))
        expr = TermReference(
            id=Identifier(name="brand"), attribute=None, arguments=call_args
        )
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="sentence"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "sentence = { -brand(case: " in ftl
        assert "nominative" in ftl

    def test_term_reference_with_attribute_and_arguments(self):
        """Lines 161-164: TermReference with both attribute and arguments."""
        named_arg = NamedArgument(
            name=Identifier(name="gender"), value=StringLiteral(value="masculine")
        )
        call_args = CallArguments(positional=(), named=(named_arg,))
        expr = TermReference(
            id=Identifier(name="brand"),
            attribute=Identifier(name="long"),
            arguments=call_args,
        )
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="description"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "description = { -brand.long(" in ftl
        assert "gender:" in ftl

    def test_function_reference(self):
        """Lines 167-168: FunctionReference with arguments."""
        named_arg = NamedArgument(
            name=Identifier(name="minimumFractionDigits"),
            value=NumberLiteral(value=2, raw="2"),
        )
        call_args = CallArguments(positional=(), named=(named_arg,))
        expr = FunctionReference(id=Identifier(name="NUMBER"), arguments=call_args)
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="price"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "price = { NUMBER(" in ftl
        assert "minimumFractionDigits:" in ftl


class TestCallArgumentsSerialization:
    """Test CallArguments in various combinations.

    Lines 175-190: Call arguments (positional and named)
    """

    def test_call_arguments_positional_only(self):
        """Lines 178-181: CallArguments with only positional arguments."""
        arg1 = NumberLiteral(value=42, raw="42")
        arg2 = StringLiteral(value="test")
        call_args = CallArguments(positional=(arg1, arg2), named=())
        expr = FunctionReference(id=Identifier(name="FUNC"), arguments=call_args)
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="test"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert 'FUNC(42, "test")' in ftl

    def test_call_arguments_named_only(self):
        """Lines 184-188: CallArguments with only named arguments."""
        arg1 = NamedArgument(name=Identifier(name="key1"), value=NumberLiteral(value=1, raw="1"))
        arg2 = NamedArgument(
            name=Identifier(name="key2"), value=StringLiteral(value="value")
        )
        call_args = CallArguments(positional=(), named=(arg1, arg2))
        expr = FunctionReference(id=Identifier(name="FUNC"), arguments=call_args)
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="test"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "FUNC(key1: 1, key2:" in ftl

    def test_call_arguments_mixed(self):
        """Lines 178-188: CallArguments with both positional and named."""
        pos_arg = NumberLiteral(value=100, raw="100")
        named_arg = NamedArgument(
            name=Identifier(name="unit"), value=StringLiteral(value="USD")
        )
        call_args = CallArguments(positional=(pos_arg,), named=(named_arg,))
        expr = FunctionReference(id=Identifier(name="NUMBER"), arguments=call_args)
        placeable = Placeable(expression=expr)
        pattern = Pattern(elements=(placeable,))
        message = Message(
            id=Identifier(name="price"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "NUMBER(100, unit:" in ftl


class TestComplexPatterns:
    """Test complex patterns with multiple elements."""

    def test_pattern_mixed_text_and_placeables(self):
        """Pattern with alternating text and placeable elements."""
        text1 = TextElement(value="Hello ")
        var_ref = VariableReference(id=Identifier(name="userName"))
        placeable1 = Placeable(expression=var_ref)
        text2 = TextElement(value=", welcome to ")
        term_ref = TermReference(
            id=Identifier(name="appName"), attribute=None, arguments=None
        )
        placeable2 = Placeable(expression=term_ref)
        text3 = TextElement(value="!")

        pattern = Pattern(
            elements=(text1, placeable1, text2, placeable2, text3)
        )
        message = Message(
            id=Identifier(name="greeting"),
            value=pattern,
            attributes=(),
            comment=None,
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        assert "greeting = Hello { $userName }, welcome to { -appName }!" in ftl


class TestSerializerRoundtrip:
    """Test that serialization produces parseable FTL.

    These tests verify serialize → parse → serialize idempotence.
    """

    def test_roundtrip_message_with_all_features(self):
        """Complex message roundtrips correctly.

        Note: Comments are not currently preserved through parse/serialize cycle.
        This is a known limitation - comments are parsed but not attached to messages.
        """
        attribute = Attribute(
            id=Identifier(name="tooltip"),
            value=Pattern(elements=(TextElement(value="Help text"),)),
        )
        message = Message(
            id=Identifier(name="button"),
            value=Pattern(elements=(TextElement(value="Click here"),)),
            attributes=(attribute,),
            comment=None,  # Comments not preserved through parsing
        )
        resource = Resource(entries=(message,))

        # Serialize
        ftl1 = serialize(resource)

        # Parse
        parser = FluentParserV1()
        resource = parser.parse(ftl1)

        # Serialize again
        ftl2 = serialize(resource)

        # Should be identical (without comments)
        assert ftl1 == ftl2

    def test_roundtrip_term_with_attributes(self):
        """Term with attributes roundtrips correctly."""
        attr1 = Attribute(
            id=Identifier(name="short"),
            value=Pattern(elements=(TextElement(value="FX"),)),
        )
        term = Term(
            id=Identifier(name="brand"),
            value=Pattern(elements=(TextElement(value="Firefox"),)),
            attributes=(attr1,),
            comment=None,
        )
        resource = Resource(entries=(term,))

        ftl1 = serialize(resource)
        parser = FluentParserV1()
        resource_parsed = parser.parse(ftl1)
        ftl2 = serialize(resource_parsed)

        assert ftl1 == ftl2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
