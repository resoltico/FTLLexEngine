"""Parser tests for message attributes (.attribute = pattern).

Phase 3B: Attribute Parsing Tests
Coverage Target: +60-80 lines of parser.py (lines 1148-1199 and 1145-1182)

Tests cover:
- Basic attribute parsing
- Multiple attributes per message
- Attributes with variables
- Attributes with select expressions
- Edge cases (empty patterns, special characters)
- Real-world examples from production FTL files
"""

from __future__ import annotations

import pytest

from ftllexengine.syntax import (
    Attribute,
    Message,
    Placeable,
    SelectExpression,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.parser import FluentParserV1


@pytest.fixture
def parser() -> FluentParserV1:
    """Create parser instance for each test."""
    return FluentParserV1()


# ============================================================================
# BASIC ATTRIBUTE PARSING
# ============================================================================


class TestFluentParserBasicAttributes:
    """Test basic attribute parsing functionality."""

    def test_parse_message_with_single_attribute(self, parser: FluentParserV1) -> None:
        """Parse message with one attribute."""
        source = """button = Save
    .tooltip = Click to save changes"""
        resource = parser.parse(source)

        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.id.name == "button"

        # Check main value
        assert msg.value is not None
        assert len(msg.value.elements) == 1
        assert isinstance(msg.value.elements[0], TextElement)
        assert msg.value.elements[0].value == "Save"

        # Check attribute
        assert len(msg.attributes) == 1
        attr = msg.attributes[0]
        assert isinstance(attr, Attribute)
        assert attr.id.name == "tooltip"
        assert len(attr.value.elements) == 1
        assert isinstance(attr.value.elements[0], TextElement)
        assert attr.value.elements[0].value == "Click to save changes"

    def test_parse_message_with_multiple_attributes(self, parser: FluentParserV1) -> None:
        """Parse message with multiple attributes."""
        source = """login-button = Sign In
    .tooltip = Click here to sign in
    .aria-label = Sign in button
    .accesskey = L"""
        resource = parser.parse(source)

        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.id.name == "login-button"

        # Check attributes
        assert len(msg.attributes) == 3
        assert msg.attributes[0].id.name == "tooltip"
        assert msg.attributes[1].id.name == "aria-label"
        assert msg.attributes[2].id.name == "accesskey"

        # Check attribute values
        attr0_elem = msg.attributes[0].value.elements[0]
        assert TextElement.guard(attr0_elem)
        assert attr0_elem.value == "Click here to sign in"
        attr1_elem = msg.attributes[1].value.elements[0]
        assert TextElement.guard(attr1_elem)
        assert attr1_elem.value == "Sign in button"
        attr2_elem = msg.attributes[2].value.elements[0]
        assert TextElement.guard(attr2_elem)
        assert attr2_elem.value == "L"

    def test_parse_attribute_with_hyphen_in_name(self, parser: FluentParserV1) -> None:
        """Parse attribute with hyphen in identifier."""
        source = """element = Value
    .aria-label = Accessible label"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert len(msg.attributes) == 1
        assert msg.attributes[0].id.name == "aria-label"

    def test_parse_attribute_with_underscore_in_name(self, parser: FluentParserV1) -> None:
        """Parse attribute with underscore in identifier."""
        source = """data = Content
    .custom_attribute = Custom value"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert len(msg.attributes) == 1
        assert msg.attributes[0].id.name == "custom_attribute"


# ============================================================================
# ATTRIBUTES WITH PLACEABLES
# ============================================================================


class TestFluentParserAttributesWithPlaceables:
    """Test attributes containing variables and expressions."""

    def test_parse_attribute_with_variable(self, parser: FluentParserV1) -> None:
        """Parse attribute with variable reference."""
        source = """greeting = Hello
    .message = Welcome, { $name }!"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert len(msg.attributes) == 1

        attr = msg.attributes[0]
        assert attr.id.name == "message"
        assert len(attr.value.elements) == 3

        # Check pattern: "Welcome, " + {$name} + "!"
        assert isinstance(attr.value.elements[0], TextElement)
        assert attr.value.elements[0].value == "Welcome, "

        assert isinstance(attr.value.elements[1], Placeable)
        expr = attr.value.elements[1].expression
        assert isinstance(expr, VariableReference)
        assert expr.id.name == "name"

        assert isinstance(attr.value.elements[2], TextElement)
        assert attr.value.elements[2].value == "!"

    def test_parse_attribute_with_select_expression(self, parser: FluentParserV1) -> None:
        """Parse attribute with select expression."""
        source = """items = Items
    .count = { $num ->
        [one] 1 item
       *[other] { $num } items
    }"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert len(msg.attributes) == 1

        attr = msg.attributes[0]
        assert attr.id.name == "count"
        assert len(attr.value.elements) == 1

        # Check select expression
        placeable = attr.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, SelectExpression)

        select = placeable.expression
        assert isinstance(select.selector, VariableReference)
        assert select.selector.id.name == "num"
        assert len(select.variants) == 2

    def test_parse_attribute_with_multiple_variables(self, parser: FluentParserV1) -> None:
        """Parse attribute with multiple variables."""
        source = """profile = Profile
    .description = User { $firstName } { $lastName } from { $city }"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        attr = msg.attributes[0]

        # Should have: "User " + {$firstName} + " " + {$lastName} + " from " + {$city}
        assert len(attr.value.elements) == 6

        # Verify variables
        assert isinstance(attr.value.elements[1], Placeable)
        var1 = attr.value.elements[1].expression
        assert isinstance(var1, VariableReference)
        assert var1.id.name == "firstName"

        assert isinstance(attr.value.elements[3], Placeable)
        var2 = attr.value.elements[3].expression
        assert isinstance(var2, VariableReference)
        assert var2.id.name == "lastName"

        assert isinstance(attr.value.elements[5], Placeable)
        var3 = attr.value.elements[5].expression
        assert isinstance(var3, VariableReference)
        assert var3.id.name == "city"


# ============================================================================
# EDGE CASES AND ERROR HANDLING
# ============================================================================


class TestFluentParserAttributeEdgeCases:
    """Test edge cases and error conditions."""

    def test_parse_message_without_attributes(self, parser: FluentParserV1) -> None:
        """Parse message with no attributes."""
        source = "simple = Just a simple message"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert len(msg.attributes) == 0

    def test_parse_attribute_with_indentation_variations(self, parser: FluentParserV1) -> None:
        """Parse attributes with different indentation levels."""
        source = """button = Save
    .attr1 = Value 1
        .attr2 = Value 2
            .attr3 = Value 3"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        # All should be parsed as attributes
        assert len(msg.attributes) == 3
        assert msg.attributes[0].id.name == "attr1"
        assert msg.attributes[1].id.name == "attr2"
        assert msg.attributes[2].id.name == "attr3"

    def test_parse_attribute_with_unicode_content(self, parser: FluentParserV1) -> None:
        """Parse attribute with Unicode characters."""
        source = """message = Message
    .emoji = Click 👍 to like
    .chinese = 你好世界"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert len(msg.attributes) == 2
        emoji_elem = msg.attributes[0].value.elements[0]
        assert TextElement.guard(emoji_elem)
        assert emoji_elem.value == "Click 👍 to like"
        chinese_elem = msg.attributes[1].value.elements[0]
        assert TextElement.guard(chinese_elem)
        assert chinese_elem.value == "你好世界"

    def test_parse_multiple_messages_with_attributes(self, parser: FluentParserV1) -> None:
        """Parse multiple messages, each with attributes."""
        source = """button1 = Save
    .tooltip = Save changes

button2 = Cancel
    .tooltip = Cancel operation
    .accesskey = C

button3 = Delete
    .tooltip = Delete item"""
        resource = parser.parse(source)

        assert len(resource.entries) == 3

        msg1 = resource.entries[0]
        assert isinstance(msg1, Message)
        assert msg1.id.name == "button1"
        assert len(msg1.attributes) == 1

        msg2 = resource.entries[1]
        assert isinstance(msg2, Message)
        assert msg2.id.name == "button2"
        assert len(msg2.attributes) == 2

        msg3 = resource.entries[2]
        assert isinstance(msg3, Message)
        assert msg3.id.name == "button3"
        assert len(msg3.attributes) == 1

    def test_parse_attribute_stops_at_non_indented_line(self, parser: FluentParserV1) -> None:
        """Attribute parsing stops when encountering non-indented line."""
        source = """message1 = First
    .attr = Attribute
message2 = Second"""
        resource = parser.parse(source)

        assert len(resource.entries) == 2

        msg1 = resource.entries[0]
        assert isinstance(msg1, Message)
        assert msg1.id.name == "message1"
        assert len(msg1.attributes) == 1

        msg2 = resource.entries[1]
        assert isinstance(msg2, Message)
        assert msg2.id.name == "message2"
        assert len(msg2.attributes) == 0


# ============================================================================
# REAL-WORLD EXAMPLES
# ============================================================================


class TestFluentParserAttributesRealWorld:
    """Test real-world attribute usage patterns."""

    def test_parse_firefox_style_message(self, parser: FluentParserV1) -> None:
        """Parse Firefox-style message with multiple attributes."""
        source = """tab-close-button = Close
    .tooltiptext = Close tab
    .aria-label = Close tab button
    .accesskey = C"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.id.name == "tab-close-button"
        assert len(msg.attributes) == 3
        assert msg.attributes[0].id.name == "tooltiptext"
        assert msg.attributes[1].id.name == "aria-label"
        assert msg.attributes[2].id.name == "accesskey"

    def test_parse_form_field_with_attributes(self, parser: FluentParserV1) -> None:
        """Parse form field message with placeholder and error."""
        source = """email-field = Email
    .placeholder = Enter your email address
    .error = Please enter a valid email
    .help-text = We'll never share your email"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert len(msg.attributes) == 3

    def test_parse_dialog_with_dynamic_attributes(self, parser: FluentParserV1) -> None:
        """Parse dialog message with variables in attributes."""
        source = """delete-confirmation = Delete Item
    .message = Are you sure you want to delete { $itemName }?
    .confirm-label = Delete
    .cancel-label = Cancel"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert len(msg.attributes) == 3

        # Check variable in first attribute
        message_attr = msg.attributes[0]
        assert message_attr.id.name == "message"
        # Should contain variable
        has_variable = any(
            isinstance(elem, Placeable) and isinstance(elem.expression, VariableReference)
            for elem in message_attr.value.elements
        )
        assert has_variable

    def test_parse_pluralized_attribute(self, parser: FluentParserV1) -> None:
        """Parse attribute with plural select expression."""
        source = """file-download = Download
    .status = { $count ->
        [0] No files
        [one] 1 file
       *[other] { $count } files
    } downloaded"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert len(msg.attributes) == 1

        status_attr = msg.attributes[0]
        assert status_attr.id.name == "status"
        # Should contain select expression
        assert len(status_attr.value.elements) == 2
        assert isinstance(status_attr.value.elements[0], Placeable)
        assert isinstance(status_attr.value.elements[0].expression, SelectExpression)
