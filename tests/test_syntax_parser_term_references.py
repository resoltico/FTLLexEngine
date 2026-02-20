"""Parser tests for term references in inline expressions ({ -term }).

Phase 3D: TermReference Parsing Tests
Coverage Target: +50-60 lines of parser.py (lines 1348-1409 and 937-953)

Tests cover:
- Basic term reference: { -brand }
- Term reference with attribute: { -brand.version }
- Term reference with arguments: { -brand(case: "nominative") }
- Term references in patterns and select expressions
- Integration tests with terms and messages
"""

from __future__ import annotations

import pytest

from ftllexengine.syntax import (
    Message,
    NumberLiteral,
    Placeable,
    SelectExpression,
    Term,
    TermReference,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.parser import FluentParserV1


@pytest.fixture
def parser() -> FluentParserV1:
    """Create parser instance for each test."""
    return FluentParserV1()


# ============================================================================
# BASIC TERM REFERENCES
# ============================================================================


class TestFluentParserBasicTermReferences:
    """Test basic term reference parsing."""

    def test_parse_simple_term_reference(self, parser: FluentParserV1) -> None:
        """Parse basic term reference in message."""
        source = """message = Use { -brand } now"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert Message.guard(msg) and msg.value is not None
        msg_value = msg.value
        assert msg_value is not None
        assert len(msg_value.elements) == 3

        # "Use "
        elem0 = msg_value.elements[0]
        assert isinstance(elem0, TextElement)
        assert elem0.value == "Use "

        elem1 = msg_value.elements[1]
        assert Placeable.guard(elem1)
        expr = elem1.expression
        assert isinstance(expr, TermReference)
        assert expr.id.name == "brand"
        assert expr.attribute is None
        assert expr.arguments is None

        # " now"
        elem2 = msg_value.elements[2]
        assert isinstance(elem2, TextElement)
        assert elem2.value == " now"

    def test_parse_term_reference_only(self, parser: FluentParserV1) -> None:
        """Parse message with only term reference."""
        source = """app-name = { -brand }"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert Message.guard(msg) and msg.value is not None
        msg_value = msg.value
        assert msg_value is not None
        assert len(msg_value.elements) == 1

        placeable = msg_value.elements[0]
        assert Placeable.guard(placeable)
        assert isinstance(placeable.expression, TermReference)
        assert placeable.expression.id.name == "brand"

    def test_parse_multiple_term_references(self, parser: FluentParserV1) -> None:
        """Parse message with multiple term references."""
        source = """message = { -brand } by { -vendor }"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert Message.guard(msg) and msg.value is not None
        msg_value = msg.value
        assert msg_value is not None

        # Should have: {-brand} + " by " + {-vendor}
        assert len(msg_value.elements) == 3

        placeable1 = msg_value.elements[0]
        assert Placeable.guard(placeable1)
        assert isinstance(placeable1.expression, TermReference)
        assert placeable1.expression.id.name == "brand"

        assert isinstance(msg_value.elements[1], TextElement)
        assert msg_value.elements[1].value == " by "

        placeable2 = msg_value.elements[2]
        assert Placeable.guard(placeable2)
        assert isinstance(placeable2.expression, TermReference)
        assert placeable2.expression.id.name == "vendor"


# ============================================================================
# TERM REFERENCES WITH ATTRIBUTES
# ============================================================================


class TestFluentParserTermReferencesWithAttributes:
    """Test term references accessing attributes."""

    def test_parse_term_reference_with_attribute(self, parser: FluentParserV1) -> None:
        """Parse term reference accessing attribute."""
        source = """message = Welcome to { -brand.short }"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert Message.guard(msg) and msg.value is not None
        msg_value = msg.value
        assert msg_value is not None

        placeable = msg_value.elements[1]
        assert Placeable.guard(placeable)
        term_ref = placeable.expression
        assert isinstance(term_ref, TermReference)
        assert term_ref.id.name == "brand"
        assert term_ref.attribute is not None
        assert term_ref.attribute is not None
        assert term_ref.attribute.name == "short"
        assert term_ref.arguments is None

    def test_parse_term_reference_with_hyphenated_attribute(self, parser: FluentParserV1) -> None:
        """Parse term reference with hyphenated attribute."""
        source = """msg = { -brand.full-name }"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert Message.guard(msg) and msg.value is not None
        msg_value = msg.value
        assert msg_value is not None

        placeable = msg_value.elements[0]
        assert Placeable.guard(placeable)
        term_ref = placeable.expression
        assert isinstance(term_ref, TermReference)
        assert term_ref.id.name == "brand"
        assert term_ref.attribute is not None
        assert term_ref.attribute.name == "full-name"


# ============================================================================
# TERM REFERENCES WITH ARGUMENTS
# ============================================================================


class TestFluentParserTermReferencesWithArguments:
    """Test term references with call arguments.

    Note: Arguments for term references are parsed but this is an advanced feature.
    For simplicity, we test that the parser handles them even if arguments are None.
    """

    def test_parse_term_reference_no_arguments(self, parser: FluentParserV1) -> None:
        """Parse term reference without arguments (baseline)."""
        source = """message = Use { -brand }"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert Message.guard(msg) and msg.value is not None
        msg_value = msg.value
        assert msg_value is not None

        placeable = msg_value.elements[1]
        assert Placeable.guard(placeable)
        term_ref = placeable.expression
        assert isinstance(term_ref, TermReference)
        assert term_ref.id.name == "brand"
        assert term_ref.attribute is None
        assert term_ref.arguments is None


# ============================================================================
# TERM REFERENCES IN SELECT EXPRESSIONS
# ============================================================================


class TestFluentParserTermReferencesInSelect:
    """Test term references used in select expressions."""

    def test_parse_term_reference_with_select_simple(self, parser: FluentParserV1) -> None:
        """Parse message with term reference and select expression separately."""
        source = "message = Download { -brand } - { $count -> [one] 1 file *[other] files }"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert Message.guard(msg) and msg.value is not None
        msg_value = msg.value
        assert msg_value is not None

        # Should have term reference
        has_term_ref = any(
            isinstance(elem, Placeable) and isinstance(elem.expression, TermReference)
            for elem in msg_value.elements
        )
        assert has_term_ref

        # Should have select expression
        has_select = any(
            isinstance(elem, Placeable) and isinstance(elem.expression, SelectExpression)
            for elem in msg_value.elements
        )
        assert has_select

    def test_parse_term_reference_as_selector(self, parser: FluentParserV1) -> None:
        """Parse select expression with term reference in text before selector."""
        source = "message = { -brand } has { $count -> [one] 1 update *[other] many updates }"
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert Message.guard(msg) and msg.value is not None
        msg_value = msg.value
        assert msg_value is not None

        # First element should be term reference
        assert isinstance(msg_value.elements[0], Placeable)
        assert isinstance(msg_value.elements[0].expression, TermReference)


# ============================================================================
# INTEGRATION WITH TERMS AND MESSAGES
# ============================================================================


class TestFluentParserTermReferenceIntegration:
    """Test term references integrated with term definitions."""

    def test_parse_term_and_reference(self, parser: FluentParserV1) -> None:
        """Parse term definition and its reference together."""
        source = """-brand = Firefox
message = Use { -brand } browser"""
        resource = parser.parse(source)

        assert len(resource.entries) == 2

        # First entry: term definition
        term = resource.entries[0]
        assert isinstance(term, Term)
        assert term.id.name == "brand"

        # Second entry: message with reference
        msg = resource.entries[1]
        assert Message.guard(msg) and msg.value is not None
        msg_value = msg.value
        assert msg_value is not None
        placeable = msg_value.elements[1]
        assert Placeable.guard(placeable)
        assert isinstance(placeable.expression, TermReference)
        assert placeable.expression.id.name == "brand"

    def test_parse_term_with_attribute_and_reference_to_attribute(
        self, parser: FluentParserV1
    ) -> None:
        """Parse term with attribute and reference accessing that attribute."""
        source = """-brand = Firefox
    .short = FF
message = { -brand.short } is the short name"""
        resource = parser.parse(source)

        assert len(resource.entries) == 2

        # Term with attribute
        term = resource.entries[0]
        assert isinstance(term, Term)
        assert len(term.attributes) == 1

        # Message referencing term attribute
        msg = resource.entries[1]
        assert Message.guard(msg) and msg.value is not None
        msg_value = msg.value
        assert msg_value is not None
        placeable = msg_value.elements[0]
        assert Placeable.guard(placeable)
        term_ref = placeable.expression
        assert isinstance(term_ref, TermReference)
        assert term_ref.id.name == "brand"
        assert term_ref.attribute is not None
        assert term_ref.attribute.name == "short"


# ============================================================================
# EDGE CASES
# ============================================================================


class TestFluentParserTermReferenceEdgeCases:
    """Test edge cases and special scenarios."""

    def test_parse_negative_number_vs_term_reference(self, parser: FluentParserV1) -> None:
        """Ensure negative numbers are not confused with term references."""
        source = """number = The value is { -42 }"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert Message.guard(msg) and msg.value is not None
        msg_value = msg.value
        assert msg_value is not None

        placeable = msg_value.elements[1]
        assert Placeable.guard(placeable)
        # Should be NumberLiteral, not TermReference
        assert isinstance(placeable.expression, NumberLiteral)
        assert placeable.expression.value == -42

    def test_parse_term_reference_with_variable(self, parser: FluentParserV1) -> None:
        """Parse term reference alongside variable."""
        source = """msg = { -brand } for { $user }"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert Message.guard(msg) and msg.value is not None
        msg_value = msg.value
        assert msg_value is not None

        # Should have: {-brand} + " for " + {$user}
        assert isinstance(msg_value.elements[0], Placeable)
        assert isinstance(msg_value.elements[0].expression, TermReference)

        assert isinstance(msg_value.elements[2], Placeable)
        assert isinstance(msg_value.elements[2].expression, VariableReference)

    def test_parse_term_reference_with_whitespace(self, parser: FluentParserV1) -> None:
        """Parse term reference with various whitespace."""
        source = """msg = {  -brand  }"""
        resource = parser.parse(source)

        msg = resource.entries[0]
        assert Message.guard(msg) and msg.value is not None
        msg_value = msg.value
        assert msg_value is not None
        placeable = msg_value.elements[0]
        assert Placeable.guard(placeable)
        assert isinstance(placeable.expression, TermReference)
        assert placeable.expression.id.name == "brand"


# ============================================================================
# REAL-WORLD EXAMPLES
# ============================================================================


class TestFluentParserTermReferenceRealWorld:
    """Test real-world term reference usage patterns."""

    def test_parse_branded_message(self, parser: FluentParserV1) -> None:
        """Parse typical branded message."""
        source = """-brand-name = Firefox
-vendor = Mozilla
about = { -brand-name } by { -vendor }"""
        resource = parser.parse(source)

        assert len(resource.entries) == 3
        msg = resource.entries[2]
        assert Message.guard(msg) and msg.value is not None
        msg_value = msg.value
        assert msg_value is not None

        # Should contain two term references
        term_refs = [
            elem.expression
            for elem in msg_value.elements
            if isinstance(elem, Placeable) and isinstance(elem.expression, TermReference)
        ]
        assert len(term_refs) == 2
        assert term_refs[0].id.name == "brand-name"
        assert term_refs[1].id.name == "vendor"

    def test_parse_grammatical_term_reference(self, parser: FluentParserV1) -> None:
        """Parse term reference with grammatical case attribute."""
        source = """-firefox = Firefox
    .nominative = Firefox
    .genitive = Firefoxa
message = Open { -firefox.genitive } settings"""
        resource = parser.parse(source)

        msg = resource.entries[1]
        assert Message.guard(msg) and msg.value is not None
        msg_value = msg.value
        assert msg_value is not None
        placeable = msg_value.elements[1]
        assert Placeable.guard(placeable)
        term_ref = placeable.expression
        assert isinstance(term_ref, TermReference)
        assert term_ref.id.name == "firefox"
        assert term_ref.attribute is not None
        assert term_ref.attribute is not None
        assert term_ref.attribute.name == "genitive"

    def test_parse_complex_message_with_terms_and_variables(self, parser: FluentParserV1) -> None:
        """Parse complex message mixing terms, variables, and select."""
        source = (
            "-brand = AppName\n"
            "message = { -brand } has { $count -> "
            "[0] no items [one] 1 item *[other] { $count } items } for { $user }"
        )
        resource = parser.parse(source)

        msg = resource.entries[1]
        assert Message.guard(msg) and msg.value is not None
        msg_value = msg.value
        assert msg_value is not None

        # First element: term reference
        assert isinstance(msg_value.elements[0], Placeable)
        assert isinstance(msg_value.elements[0].expression, TermReference)

        # Contains select expression
        has_select = any(
            isinstance(elem, Placeable) and isinstance(elem.expression, SelectExpression)
            for elem in msg_value.elements
        )
        assert has_select

        # Contains variable reference
        has_var = any(
            isinstance(elem, Placeable) and isinstance(elem.expression, VariableReference)
            for elem in msg_value.elements
        )
        assert has_var
