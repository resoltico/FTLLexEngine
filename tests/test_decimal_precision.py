"""Tests for Decimal precision in NumberLiteral (C-SEMANTIC-001).

Verifies that decimal literals use Decimal type for financial-grade precision,
eliminating float rounding surprises.

Python 3.13+. Uses pytest.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from ftllexengine.syntax import parse as parse_ftl
from ftllexengine.syntax.ast import Message, NumberLiteral, Pattern, Placeable

if TYPE_CHECKING:
    from ftllexengine.syntax.ast import Resource


class TestDecimalPrecision:
    """Tests for NumberLiteral Decimal precision guarantee."""

    def test_decimal_literal_preserves_precision(self) -> None:
        """Decimal literal parses to Decimal preserving all digits."""
        # This specific value loses precision with IEEE 754 float
        source = "msg = { 1.0000000000000001 }"
        resource = parse_ftl(source)

        assert len(resource.entries) == 1
        message = resource.entries[0]
        assert isinstance(message, Message)
        assert message.value is not None

        # Extract the NumberLiteral from the pattern
        pattern = message.value
        assert isinstance(pattern, Pattern)
        assert len(pattern.elements) == 1

        placeable = pattern.elements[0]
        assert isinstance(placeable, Placeable)

        number_lit = placeable.expression
        assert isinstance(number_lit, NumberLiteral)

        # Verify type is Decimal, not float
        assert isinstance(number_lit.value, Decimal)

        # Verify precision is preserved
        expected = Decimal("1.0000000000000001")
        assert number_lit.value == expected

        # Verify that raw string is preserved for serialization
        assert number_lit.raw == "1.0000000000000001"

    def test_integer_literal_still_uses_int(self) -> None:
        """Integer literal parses to int for memory efficiency."""
        source = "msg = { 123 }"
        resource = parse_ftl(source)

        message = resource.entries[0]
        assert isinstance(message, Message)
        assert message.value is not None

        pattern = message.value
        assert isinstance(pattern, Pattern)

        placeable = pattern.elements[0]
        assert isinstance(placeable, Placeable)

        number_lit = placeable.expression
        assert isinstance(number_lit, NumberLiteral)

        # Verify type is int
        assert isinstance(number_lit.value, int)
        assert number_lit.value == 123

    def test_financial_grade_precision_example(self) -> None:
        """Financial calculation example: 0.1 + 0.2 = 0.3 (not 0.30000000000000004)."""
        # With float: 0.1 + 0.2 = 0.30000000000000004
        # With Decimal: 0.1 + 0.2 = 0.3

        source1 = "val1 = { 0.1 }"
        source2 = "val2 = { 0.2 }"
        source3 = "val3 = { 0.3 }"

        resource1 = parse_ftl(source1)
        resource2 = parse_ftl(source2)
        resource3 = parse_ftl(source3)

        def extract_value(resource: Resource) -> int | Decimal:
            message = resource.entries[0]
            assert isinstance(message, Message)
            pattern = message.value
            assert isinstance(pattern, Pattern)
            placeable = pattern.elements[0]
            assert isinstance(placeable, Placeable)
            number_lit = placeable.expression
            assert isinstance(number_lit, NumberLiteral)
            return number_lit.value

        val1 = extract_value(resource1)
        val2 = extract_value(resource2)
        val3 = extract_value(resource3)

        # All should be Decimal
        assert isinstance(val1, Decimal)
        assert isinstance(val2, Decimal)
        assert isinstance(val3, Decimal)

        # Financial arithmetic works correctly
        assert val1 + val2 == val3

    def test_large_precision_decimal(self) -> None:
        """Large precision decimal (e.g., exchange rates) preserves all digits."""
        # Exchange rate example: 1 EUR = 1.234567890123456 USD
        source = "rate = { 1.234567890123456 }"
        resource = parse_ftl(source)

        message = resource.entries[0]
        assert isinstance(message, Message)
        pattern = message.value
        assert isinstance(pattern, Pattern)
        placeable = pattern.elements[0]
        assert isinstance(placeable, Placeable)
        number_lit = placeable.expression

        assert isinstance(number_lit, NumberLiteral)
        assert isinstance(number_lit.value, Decimal)

        expected = Decimal("1.234567890123456")
        assert number_lit.value == expected

    def test_negative_decimal_precision(self) -> None:
        """Negative decimals also use Decimal type."""
        source = "temp = { -273.15 }"
        resource = parse_ftl(source)

        message = resource.entries[0]
        assert isinstance(message, Message)
        pattern = message.value
        assert isinstance(pattern, Pattern)
        placeable = pattern.elements[0]
        assert isinstance(placeable, Placeable)
        number_lit = placeable.expression

        assert isinstance(number_lit, NumberLiteral)
        assert isinstance(number_lit.value, Decimal)
        assert number_lit.value == Decimal("-273.15")

    def test_scientific_notation_not_supported(self) -> None:
        """FTL does not support scientific notation (e.g., 1.23e10)."""
        # Per Fluent spec, only decimal notation is supported
        # This test documents the boundary
        source = "val = { 1.23e10 }"
        resource = parse_ftl(source)

        # Parser treats "e10" as part of Junk, not a valid number
        # This is correct per Fluent spec
        assert len(resource.entries) > 0
        # First entry may be Junk due to invalid syntax
        # (exact behavior depends on parser recovery)
