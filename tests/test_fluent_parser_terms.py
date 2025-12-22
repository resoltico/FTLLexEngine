"""Parser tests for term definitions (-term-id = pattern).

Phase 3C: Term Parsing Tests
Coverage Target: +60-70 lines of parser.py (lines 1237-1318 and 100-108)

Tests cover:
- Basic term parsing
- Terms with attributes
- Multiple terms in resource
- Terms with variables/select expressions
- Integration with messages
- Real-world term usage patterns
"""

from __future__ import annotations

import pytest

from ftllexengine.syntax import (
    Message,
    Placeable,
    SelectExpression,
    Term,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.parser import FluentParserV1


@pytest.fixture
def parser() -> FluentParserV1:
    """Create parser instance for each test."""
    return FluentParserV1()


# ============================================================================
# BASIC TERM PARSING
# ============================================================================


class TestFluentParserBasicTerms:
    """Test basic term parsing functionality."""

    def test_parse_simple_term(self, parser: FluentParserV1) -> None:
        """Parse basic term definition."""
        source = "-brand = Firefox"
        resource = parser.parse(source)

        assert len(resource.entries) == 1
        term = resource.entries[0]
        assert Term.guard(term) and term.value is not None
        term_value = term.value
        assert term_value is not None
        assert term.id.name == "brand"

        # Check value
        assert term_value is not None
        assert len(term_value.elements) == 1
        assert isinstance(term_value.elements[0], TextElement)
        elem0 = term_value.elements[0]
        assert TextElement.guard(elem0)
        assert elem0.value == "Firefox"

        # No attributes
        assert len(term.attributes) == 0

    def test_parse_term_with_hyphen_in_name(self, parser: FluentParserV1) -> None:
        """Parse term with hyphen in identifier."""
        source = "-brand-name = Mozilla Firefox"
        resource = parser.parse(source)

        term = resource.entries[0]
        assert Term.guard(term) and term.value is not None
        term_value = term.value
        assert term_value is not None
        assert term.id.name == "brand-name"
        elem0 = term_value.elements[0]
        assert TextElement.guard(elem0)
        assert elem0.value == "Mozilla Firefox"

    def test_parse_term_with_numbers(self, parser: FluentParserV1) -> None:
        """Parse term with numbers in identifier."""
        source = "-version2 = Build 115"
        resource = parser.parse(source)

        term = resource.entries[0]
        assert Term.guard(term) and term.value is not None
        term_value = term.value
        assert term_value is not None
        assert term.id.name == "version2"
        elem0 = term_value.elements[0]
        assert TextElement.guard(elem0)
        assert elem0.value == "Build 115"

    def test_parse_multiple_terms(self, parser: FluentParserV1) -> None:
        """Parse multiple term definitions."""
        source = """-brand = Firefox
-version = 115
-vendor = Mozilla"""
        resource = parser.parse(source)

        assert len(resource.entries) == 3
        assert all(isinstance(entry, Term) for entry in resource.entries)
        entry0 = resource.entries[0]
        assert Term.guard(entry0)
        assert entry0.id.name == "brand"
        entry1 = resource.entries[1]
        assert Term.guard(entry1)
        assert entry1.id.name == "version"
        entry2 = resource.entries[2]
        assert Term.guard(entry2)
        assert entry2.id.name == "vendor"


# ============================================================================
# TERMS WITH ATTRIBUTES
# ============================================================================


class TestFluentParserTermsWithAttributes:
    """Test terms with attributes."""

    def test_parse_term_with_single_attribute(self, parser: FluentParserV1) -> None:
        """Parse term with one attribute."""
        source = """-brand = Firefox
    .gender = masculine"""
        resource = parser.parse(source)

        assert len(resource.entries) == 1
        term = resource.entries[0]
        assert Term.guard(term)
        assert term.id.name == "brand"

        # Check attribute
        assert len(term.attributes) == 1
        attr = term.attributes[0]
        assert attr.id.name == "gender"
        attr_elem = attr.value.elements[0]
        assert TextElement.guard(attr_elem)
        assert attr_elem.value == "masculine"

    def test_parse_term_with_multiple_attributes(self, parser: FluentParserV1) -> None:
        """Parse term with multiple attributes."""
        source = """-brand = Firefox
    .nominative = Firefox
    .genitive = Firefoxa
    .dative = Firefoxam"""
        resource = parser.parse(source)

        term = resource.entries[0]
        assert isinstance(term, Term)
        assert len(term.attributes) == 3
        assert term.attributes[0].id.name == "nominative"
        assert term.attributes[1].id.name == "genitive"
        assert term.attributes[2].id.name == "dative"

    def test_parse_term_with_attribute_containing_variable(self, parser: FluentParserV1) -> None:
        """Parse term attribute with variable."""
        source = """-app = Application
    .version = Version { $versionNumber }"""
        resource = parser.parse(source)

        term = resource.entries[0]
        assert isinstance(term, Term)
        assert len(term.attributes) == 1

        attr = term.attributes[0]
        assert attr.id.name == "version"
        # Should contain text + variable
        assert len(attr.value.elements) == 2
        assert isinstance(attr.value.elements[1], Placeable)


# ============================================================================
# TERMS WITH PLACEABLES
# ============================================================================


class TestFluentParserTermsWithPlaceables:
    """Test terms containing variables and expressions."""

    def test_parse_term_with_variable(self, parser: FluentParserV1) -> None:
        """Parse term with variable reference."""
        source = "-welcome = Hello, { $name }!"
        resource = parser.parse(source)

        term = resource.entries[0]
        assert Term.guard(term) and term.value is not None
        term_value = term.value
        assert term_value is not None
        assert len(term_value.elements) == 3

        # Check pattern: "Hello, " + {$name} + "!"
        assert isinstance(term_value.elements[0], TextElement)
        elem0 = term_value.elements[0]
        assert TextElement.guard(elem0)
        assert elem0.value == "Hello, "

        assert isinstance(term_value.elements[1], Placeable)
        expr = term_value.elements[1].expression
        assert isinstance(expr, VariableReference)
        assert expr.id.name == "name"

        assert isinstance(term_value.elements[2], TextElement)
        elem2 = term_value.elements[2]
        assert TextElement.guard(elem2)
        assert elem2.value == "!"

    def test_parse_term_with_select_expression(self, parser: FluentParserV1) -> None:
        """Parse term with select expression."""
        source = """-items-count = { $count ->
    [one] 1 item
   *[other] { $count } items
}"""
        resource = parser.parse(source)

        term = resource.entries[0]
        assert Term.guard(term) and term.value is not None
        term_value = term.value
        assert term_value is not None
        assert len(term_value.elements) == 1

        placeable = term_value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, SelectExpression)

        select = placeable.expression
        assert isinstance(select.selector, VariableReference)
        assert select.selector.id.name == "count"
        assert len(select.variants) == 2


# ============================================================================
# TERMS WITH MESSAGES
# ============================================================================


class TestFluentParserTermsWithMessages:
    """Test integration of terms with messages."""

    def test_parse_terms_and_messages_mixed(self, parser: FluentParserV1) -> None:
        """Parse file with both terms and messages."""
        source = """-brand = Firefox
message1 = Hello
-version = 115
message2 = World"""
        resource = parser.parse(source)

        assert len(resource.entries) == 4
        assert isinstance(resource.entries[0], Term)
        assert isinstance(resource.entries[1], Message)
        assert isinstance(resource.entries[2], Term)
        assert isinstance(resource.entries[3], Message)

        entry0 = resource.entries[0]
        assert Term.guard(entry0)
        assert entry0.id.name == "brand"
        entry1 = resource.entries[1]
        assert Message.guard(entry1)
        assert entry1.id.name == "message1"
        entry2 = resource.entries[2]
        assert Term.guard(entry2)
        assert entry2.id.name == "version"
        entry3 = resource.entries[3]
        assert Message.guard(entry3)
        assert entry3.id.name == "message2"

    def test_parse_term_followed_by_message_with_attributes(self, parser: FluentParserV1) -> None:
        """Parse term followed by message, both with attributes."""
        source = """-brand = Firefox
    .short = FF

button = Click
    .tooltip = Click here"""
        resource = parser.parse(source)

        assert len(resource.entries) == 2

        term = resource.entries[0]
        assert Term.guard(term)
        assert term.id.name == "brand"
        assert len(term.attributes) == 1

        msg = resource.entries[1]
        assert isinstance(msg, Message)
        assert msg.id.name == "button"
        assert len(msg.attributes) == 1


# ============================================================================
# EDGE CASES
# ============================================================================


class TestFluentParserTermEdgeCases:
    """Test edge cases and error conditions."""

    def test_parse_term_with_unicode(self, parser: FluentParserV1) -> None:
        """Parse term with Unicode content."""
        source = "-greeting = 你好 👋"
        resource = parser.parse(source)

        term = resource.entries[0]
        assert Term.guard(term) and term.value is not None
        term_value = term.value
        assert term_value is not None
        elem0 = term_value.elements[0]
        assert TextElement.guard(elem0)
        assert elem0.value == "你好 👋"

    def test_parse_term_with_whitespace_variations(self, parser: FluentParserV1) -> None:
        """Parse term with various whitespace."""
        source = "-brand   =   Firefox   "
        resource = parser.parse(source)

        term = resource.entries[0]
        assert Term.guard(term) and term.value is not None
        term_value = term.value
        assert term_value is not None
        assert term.id.name == "brand"
        elem0 = term_value.elements[0]
        assert TextElement.guard(elem0)
        assert elem0.value == "Firefox   "

    def test_parse_multiple_terms_with_blank_lines(self, parser: FluentParserV1) -> None:
        """Parse terms separated by blank lines."""
        source = """-brand = Firefox

-version = 115

-vendor = Mozilla"""
        resource = parser.parse(source)

        assert len(resource.entries) == 3
        assert all(isinstance(entry, Term) for entry in resource.entries)

    def test_parse_term_stops_at_next_term(self, parser: FluentParserV1) -> None:
        """Term attribute parsing stops at next term."""
        source = """-term1 = Value 1
    .attr = Attribute
-term2 = Value 2"""
        resource = parser.parse(source)

        assert len(resource.entries) == 2

        term1 = resource.entries[0]
        assert isinstance(term1, Term)
        assert term1.id.name == "term1"
        assert len(term1.attributes) == 1

        term2 = resource.entries[1]
        assert isinstance(term2, Term)
        assert term2.id.name == "term2"
        assert len(term2.attributes) == 0


# ============================================================================
# REAL-WORLD EXAMPLES
# ============================================================================


class TestFluentParserTermsRealWorld:
    """Test real-world term usage patterns."""

    def test_parse_brand_terms(self, parser: FluentParserV1) -> None:
        """Parse typical branding terms."""
        source = """-brand-short-name = Firefox
-brand-full-name = Mozilla Firefox
-vendor-short-name = Mozilla"""
        resource = parser.parse(source)

        assert len(resource.entries) == 3
        assert all(isinstance(entry, Term) for entry in resource.entries)

    def test_parse_grammatical_term(self, parser: FluentParserV1) -> None:
        """Parse term with grammatical case attributes."""
        source = """-firefox = Firefox
    .gender = masculine
    .nominative = Firefox
    .genitive = Firefoxa
    .dative = Firefoxam
    .accusative = Firefox
    .locative = Firefoxā
    .vocative = Firefox"""
        resource = parser.parse(source)

        term = resource.entries[0]
        assert Term.guard(term)
        assert term.id.name == "firefox"
        assert len(term.attributes) == 7

    def test_parse_versioned_term(self, parser: FluentParserV1) -> None:
        """Parse term with version information."""
        source = """-app-name = MyApp
    .version = { $version }
    .build = { $buildNumber }"""
        resource = parser.parse(source)

        term = resource.entries[0]
        assert isinstance(term, Term)
        assert len(term.attributes) == 2

        # Both attributes should contain variables
        for attr in term.attributes:
            has_variable = any(
                isinstance(elem, Placeable) and isinstance(elem.expression, VariableReference)
                for elem in attr.value.elements
            )
            assert has_variable

    def test_parse_parameterized_term(self, parser: FluentParserV1) -> None:
        """Parse term that will be referenced with parameters."""
        source = """-file-menu = File
-edit-menu = Edit
-view-menu = View"""
        resource = parser.parse(source)

        assert len(resource.entries) == 3
        entry0 = resource.entries[0]
        assert Term.guard(entry0)
        assert entry0.id.name == "file-menu"
        entry1 = resource.entries[1]
        assert Term.guard(entry1)
        assert entry1.id.name == "edit-menu"
        entry2 = resource.entries[2]
        assert Term.guard(entry2)
        assert entry2.id.name == "view-menu"

    def test_parse_term_with_complex_select(self, parser: FluentParserV1) -> None:
        """Parse term with complex plural select."""
        source = """-photos = { $count ->
    [0] no photos
    [one] one photo
   *[other] { $count } photos
}"""
        resource = parser.parse(source)

        term = resource.entries[0]
        assert Term.guard(term) and term.value is not None
        term_value = term.value
        assert term_value is not None
        assert term.id.name == "photos"

        # Should contain select expression
        placeable = term_value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, SelectExpression)
        assert len(placeable.expression.variants) == 3
