"""Tests for parser inline expression rules at edge inputs.

Tests:
- parse_variant_key behavior with non-key characters
- parse_call_arguments with truncated or invalid input sequences
- parse_inline_expression with uppercase message references including attributes
- parse_placeable handling when '-' after expression is not '->'
"""

from __future__ import annotations

from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.ast import MessageReference
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import (
    parse_call_arguments,
    parse_inline_expression,
    parse_placeable,
    parse_variant_key,
)


class TestVariantKeyNonKeyCharacter:
    """parse_variant_key returns None for characters that are neither numeric nor alphabetic."""

    def test_at_symbol_returns_none(self) -> None:
        """@ is neither a digit (numeric) nor ASCII letter (identifier) - parse fails."""
        cursor = Cursor("@invalid", 0)
        result = parse_variant_key(cursor)
        assert result is None

    def test_exclamation_returns_none(self) -> None:
        """! is neither a digit nor ASCII letter - parse fails."""
        cursor = Cursor("!", 0)
        result = parse_variant_key(cursor)
        assert result is None

    def test_open_brace_returns_none(self) -> None:
        """{ is neither a digit nor ASCII letter - parse fails."""
        cursor = Cursor("{key}", 0)
        result = parse_variant_key(cursor)
        assert result is None

    def test_asterisk_returns_none(self) -> None:
        """* is neither a digit nor ASCII letter - parse fails."""
        cursor = Cursor("*other", 0)
        result = parse_variant_key(cursor)
        assert result is None


class TestCallArgumentsEOFAfterColon:
    """parse_call_arguments returns None when input ends immediately after the colon."""

    def test_eof_after_colon(self) -> None:
        """Input truncated at colon produces None (no value token follows)."""
        cursor = Cursor("style:", 0)
        result = parse_call_arguments(cursor)
        assert result is None


class TestCallArgumentsInvalidValue:
    """parse_call_arguments returns None when the argument value is unparseable."""

    def test_closing_paren_as_value_returns_none(self) -> None:
        """')' cannot start an argument expression - parse fails immediately."""
        cursor = Cursor("style: )", 0)
        result = parse_call_arguments(cursor)
        assert result is None

    def test_at_symbol_as_value_returns_none(self) -> None:
        """'@' cannot start an argument expression - parse fails immediately."""
        cursor = Cursor("key: @invalid", 0)
        result = parse_call_arguments(cursor)
        assert result is None


class TestUppercaseMessageReferenceWithAttribute:
    """parse_inline_expression handles uppercase message references with attributes."""

    def test_uppercase_message_with_attribute_direct_parse(self) -> None:
        """MSG.attr parses as MessageReference with id='MSG' and attribute='attr'."""
        cursor = Cursor("MSG.attr", 0)
        result = parse_inline_expression(cursor)

        assert result is not None
        assert isinstance(result.value, MessageReference)
        assert result.value.id.name == "MSG"
        assert result.value.attribute is not None
        assert result.value.attribute.name == "attr"

    def test_uppercase_message_attribute_resolves_via_bundle(self) -> None:
        """Uppercase message reference with attribute resolves to the attribute value."""
        bundle = FluentBundle("en_US")
        ftl = """MSG = Value
    .attr = Attribute value

msg = {MSG.attr}
"""
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")
        assert "Attribute value" in result


class TestPlaceableNotSelectExpression:
    """parse_placeable handles '-' after expression that is not '->' correctly."""

    def test_minus_not_arrow_after_variable(self) -> None:
        """Variable followed by '-x' (not '->') inside a placeable is not a select.

        parse_placeable receives source after the '{' has been consumed.
        It parses $var, skips whitespace, encounters '-' then 'x' (not '>').
        This is not a select expression, and the remaining '-x}' cannot close
        the placeable, so None is returned.
        """
        cursor = Cursor("$var -x}", 0)
        result = parse_placeable(cursor)
        assert result is None

    def test_negative_number_not_select_via_bundle(self) -> None:
        """Negative number literal inside a placeable is parsed as a number, not a select."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = {-5}")
        result, _ = bundle.format_pattern("msg")
        assert "-5" in result
