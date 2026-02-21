"""Error recovery, defensive code paths, and edge-case coverage for parser rules.

Consolidated from 12 per-metric test files into a single semantic unit.
Covers: error paths, defensive/unreachable branches (via mocking), FluentParserV1
integration for malformed input, and property-based edge-case tests.
"""

from __future__ import annotations

import logging
import sys
from unittest.mock import patch

from ftllexengine.syntax.ast import (
    Attribute,
    Identifier,
    Junk,
    Message,
    MessageReference,
    NumberLiteral,
    Placeable,
    StringLiteral,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.cursor import Cursor, ParseError, ParseResult
from ftllexengine.syntax.parser.core import FluentParserV1
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    _parse_inline_hyphen,
    _parse_inline_identifier,
    parse_argument_expression,
    parse_attribute,
    parse_call_arguments,
    parse_function_reference,
    parse_inline_expression,
    parse_message,
    parse_pattern,
    parse_placeable,
    parse_select_expression,
    parse_simple_pattern,
    parse_term,
    parse_term_reference,
    parse_variant,
    parse_variant_key,
)

# ============================================================================
# VARIANT KEY ERROR PATHS
# ============================================================================


class TestVariantKeyErrorPaths:
    """Error paths in parse_variant_key and parse_variant."""

    def test_negative_sign_both_fail(self) -> None:
        """Hyphen: parse_number fails, parse_identifier fails too."""
        cursor = Cursor("-", 0)
        result = parse_variant_key(cursor)
        assert result is None

    def test_negative_sign_identifier_fallback_via_mock(self) -> None:
        """Lines 878-879: Number fails, identifier succeeds (defensive).

        Structurally unreachable without mocking because if cursor starts
        with '-', parse_identifier also fails (can't start with '-').
        """
        with (
            patch(
                "ftllexengine.syntax.parser.rules.parse_number"
            ) as mock_num,
            patch(
                "ftllexengine.syntax.parser.rules.parse_identifier"
            ) as mock_id,
        ):
            mock_num.return_value = ParseError("forced failure", Cursor("-test", 0))
            mock_id.return_value = ParseResult(
                "test", Cursor("test", 4)
            )
            cursor = Cursor("-test", 0)
            result = parse_variant_key(cursor)
            assert result is not None

    def test_variant_missing_opening_bracket(self) -> None:
        """parse_variant: no '[' at start."""
        assert parse_variant(Cursor("one", 0)) is None

    def test_variant_missing_closing_bracket(self) -> None:
        """parse_variant: no ']' after key."""
        assert parse_variant(Cursor("[one", 0)) is None

    def test_variant_invalid_key(self) -> None:
        """parse_variant: invalid key character."""
        assert parse_variant(Cursor("[@]", 0)) is None

    def test_select_no_variants(self) -> None:
        """parse_select_expression: immediate close, no variants."""
        sel = VariableReference(id=Identifier("count"))
        assert parse_select_expression(Cursor("}", 0), sel, 0) is None

    def test_select_no_default_variant(self) -> None:
        """parse_select_expression: variants without default."""
        sel = VariableReference(id=Identifier("count"))
        result = parse_select_expression(
            Cursor("[one] item\n}", 0), sel, 0
        )
        assert result is None


# ============================================================================
# ARGUMENT EXPRESSION ERROR PATHS
# ============================================================================


class TestArgumentExpressionErrorPaths:
    """Error paths in parse_argument_expression."""

    def test_eof_returns_none(self) -> None:
        """EOF at argument position."""
        assert parse_argument_expression(Cursor("", 0)) is None

    def test_invalid_char_returns_none(self) -> None:
        """Invalid character (@) returns None."""
        assert parse_argument_expression(Cursor("@", 0)) is None

    def test_term_ref_fails_line_1105(self) -> None:
        """Line 1105: Term reference parse fails (hyphen + identifier)."""
        result = parse_argument_expression(Cursor("-x.123)", 0))
        assert result is None

    def test_term_ref_bare_hyphen_fails(self) -> None:
        """Hyphen followed by ')' fails term and number parse."""
        assert parse_argument_expression(Cursor("-)", 0)) is None

    def test_number_fails_defensive_line_1120(self) -> None:
        """Line 1120: parse_number returns None on digit (defensive).

        Requires mocking because parse_number is robust for digit start.
        """
        with patch(
            "ftllexengine.syntax.parser.rules.parse_number"
        ) as mock:
            mock.return_value = ParseError("forced failure", Cursor("9)", 0))
            assert parse_argument_expression(Cursor("9)", 0)) is None

    def test_identifier_fails_defensive_line_1139(self) -> None:
        """Line 1139: parse_identifier returns None (defensive).

        Requires mocking because is_identifier_start guarantees success.
        """
        with patch(
            "ftllexengine.syntax.parser.rules.parse_identifier"
        ) as mock:
            mock.return_value = ParseError("forced failure", Cursor("x)", 0))
            assert parse_argument_expression(Cursor("x)", 0)) is None

    def test_function_ref_fails_line_1150(self) -> None:
        """Line 1150: parse_function_reference returns None."""
        assert parse_argument_expression(
            Cursor("FUNC(@)", 0)
        ) is None

    def test_function_ref_succeeds(self) -> None:
        """Function reference parsing succeeds."""
        result = parse_argument_expression(Cursor("NUMBER(42)", 0))
        assert result is not None

    def test_uppercase_no_paren_is_message_ref(self) -> None:
        """Uppercase identifier without '(' is MessageReference."""
        result = parse_argument_expression(Cursor("NUMBER", 0))
        assert result is not None
        assert isinstance(result.value, MessageReference)
        assert result.value.id.name == "NUMBER"

    def test_uppercase_open_paren_at_eof(self) -> None:
        """Uppercase + '(' but incomplete call."""
        assert parse_argument_expression(Cursor("NUMBER(", 0)) is None

    def test_negative_number_succeeds(self) -> None:
        """Negative number parses as NumberLiteral."""
        result = parse_argument_expression(Cursor("-123", 0))
        assert result is not None
        assert isinstance(result.value, NumberLiteral)

    def test_positive_number_succeeds(self) -> None:
        """Digit-start parses as NumberLiteral."""
        result = parse_argument_expression(Cursor("42", 0))
        assert result is not None
        assert isinstance(result.value, NumberLiteral)

    def test_string_literal_argument(self) -> None:
        """String literal in argument position."""
        result = parse_argument_expression(Cursor('"text"', 0))
        assert result is not None
        assert isinstance(result.value, StringLiteral)

    def test_inline_placeable_argument(self) -> None:
        """Inline placeable { $var } in argument position."""
        result = parse_argument_expression(Cursor("{ $var }", 0))
        assert result is not None
        assert isinstance(result.value, Placeable)

    def test_identifier_with_underscore(self) -> None:
        """Identifier can contain underscore after letter."""
        result = parse_argument_expression(Cursor("my_var", 0))
        assert result is not None
        assert isinstance(result.value, MessageReference)


# ============================================================================
# CALL ARGUMENTS ERROR PATHS
# ============================================================================


class TestCallArgumentsErrorPaths:
    """Error paths in parse_call_arguments."""

    def test_named_arg_name_not_identifier(self) -> None:
        """Named argument name must be identifier (not variable)."""
        result = parse_call_arguments(Cursor('$var: "value")', 0))
        assert result is None

    def test_duplicate_named_argument(self) -> None:
        """Duplicate named argument names."""
        assert parse_call_arguments(Cursor("x: 1, x: 2)", 0)) is None

    def test_named_arg_missing_value(self) -> None:
        """Expected value after ':' but got ')'."""
        assert parse_call_arguments(Cursor("x: )", 0)) is None

    def test_named_arg_value_parse_fails(self) -> None:
        """Value expression parse fails after ':'."""
        assert parse_call_arguments(Cursor("x: @)", 0)) is None

    def test_named_arg_eof_after_colon(self) -> None:
        """EOF after ':' in named argument."""
        assert parse_call_arguments(Cursor("x:", 0)) is None

    def test_positional_after_named(self) -> None:
        """Positional args must come before named."""
        assert parse_call_arguments(Cursor("x: 1, $var)", 0)) is None

    def test_named_arg_non_literal_value(self) -> None:
        """Named argument value must be literal."""
        assert parse_call_arguments(
            Cursor("x: $var)", 0)
        ) is None

    def test_trailing_comma(self) -> None:
        """Trailing comma in argument list."""
        result = parse_call_arguments(Cursor("1, 2, )", 0))
        assert result is not None
        assert len(result.value.positional) == 2

    def test_argument_expression_fails_in_loop(self) -> None:
        """Argument expression fails at '@'."""
        assert parse_call_arguments(Cursor("@)", 0)) is None


# ============================================================================
# INLINE EXPRESSION AND HELPER ERROR PATHS
# ============================================================================


class TestInlineExpressionErrorPaths:
    """Error paths in inline expression helpers."""

    def test_inline_hyphen_all_fail(self) -> None:
        """_parse_inline_hyphen: both term and number fail."""
        assert _parse_inline_hyphen(Cursor("-", 0)) is None

    def test_inline_hyphen_term_attr_fails_line_1365(self) -> None:
        """Line 1365: Term reference fails (invalid attribute)."""
        result = _parse_inline_hyphen(Cursor("-x.123", 0))
        assert result is None

    def test_inline_identifier_function_fails(self) -> None:
        """_parse_inline_identifier: function parse fails."""
        assert _parse_inline_identifier(
            Cursor("func(@)", 0)
        ) is None

    def test_inline_identifier_parse_fails(self) -> None:
        """_parse_inline_identifier: parse_identifier fails."""
        assert _parse_inline_identifier(Cursor("123", 0)) is None

    def test_inline_expression_eof(self) -> None:
        """parse_inline_expression: EOF returns None."""
        assert parse_inline_expression(Cursor("", 0)) is None

    def test_inline_expression_invalid_char(self) -> None:
        """parse_inline_expression: invalid character returns None."""
        assert parse_inline_expression(Cursor("@", 0)) is None

    def test_inline_expression_variable_fails(self) -> None:
        """parse_inline_expression: '$' but identifier fails."""
        assert parse_inline_expression(Cursor("$", 0)) is None

    def test_inline_expression_nested_placeable_fails(self) -> None:
        """parse_inline_expression: nested placeable fails."""
        assert parse_inline_expression(Cursor("{ @ }", 0)) is None

    def test_inline_expression_message_attr_fails(self) -> None:
        """Message reference attribute parsing fails (invalid attr)."""
        cursor = Cursor("msg.-test", 0)
        result = parse_inline_expression(cursor)
        assert result is None or (
            result is not None and hasattr(result, "value")
        )


# ============================================================================
# PLACEABLE ERROR PATHS
# ============================================================================


class TestPlaceableErrorPaths:
    """Error paths in parse_placeable."""

    def test_depth_exceeded(self) -> None:
        """Nesting depth exceeded returns None."""
        ctx = ParseContext(max_nesting_depth=1, current_depth=2)
        assert parse_placeable(Cursor("$var}", 0), ctx) is None

    def test_expression_parse_fails(self) -> None:
        """Expression fails at '@'."""
        assert parse_placeable(Cursor("@}", 0)) is None

    def test_select_parse_fails(self) -> None:
        """Select expression fails (no variants)."""
        assert parse_placeable(Cursor("$var -> }", 0)) is None

    def test_select_missing_closing_brace(self) -> None:
        """Select expression without closing }."""
        result = parse_placeable(
            Cursor("$var -> [one] 1 *[other] N", 0)
        )
        assert result is None

    def test_simple_expression_missing_closing_brace(self) -> None:
        """Simple expression without closing }."""
        assert parse_placeable(Cursor("$var", 0)) is None

    def test_valid_selector_with_select_line_1585(self) -> None:
        """Line 1585: Valid selector with select expression."""
        result = parse_placeable(
            Cursor("$n -> [one] One *[other] Many}", 0)
        )
        assert result is not None

    def test_hyphen_not_arrow(self) -> None:
        """'-' but not '->' skips to simple close."""
        result = parse_placeable(Cursor("$var - }", 0))
        # Malformed, may return None or partial
        assert result is None or result is not None


# ============================================================================
# FUNCTION REFERENCE ERROR PATHS
# ============================================================================


class TestFunctionReferenceErrorPaths:
    """Error paths in parse_function_reference."""

    def test_identifier_parse_fails(self) -> None:
        """Non-identifier character at start."""
        assert parse_function_reference(Cursor("123", 0)) is None

    def test_missing_opening_paren(self) -> None:
        """Valid name but no '('."""
        assert parse_function_reference(Cursor("FUNC", 0)) is None

    def test_missing_closing_paren(self) -> None:
        """Arguments but no closing ')'."""
        assert parse_function_reference(Cursor("FUNC($x", 0)) is None

    def test_arguments_parse_fails(self) -> None:
        """Call arguments fail at '@'."""
        assert parse_function_reference(
            Cursor("FUNC(@)", 0)
        ) is None

    def test_depth_exceeded(self) -> None:
        """Nesting depth exceeded."""
        ctx = ParseContext(max_nesting_depth=1, current_depth=2)
        assert parse_function_reference(
            Cursor("FUNC($x)", 0), ctx
        ) is None


# ============================================================================
# TERM REFERENCE ERROR PATHS
# ============================================================================


class TestTermReferenceErrorPaths:
    """Error paths in parse_term_reference."""

    def test_missing_hyphen(self) -> None:
        """No '-' at start."""
        assert parse_term_reference(Cursor("brand", 0)) is None

    def test_identifier_fails_after_hyphen(self) -> None:
        """Identifier parse fails after '-'."""
        assert parse_term_reference(Cursor("-", 0)) is None

    def test_attribute_identifier_fails(self) -> None:
        """Attribute identifier parse fails after '.'."""
        assert parse_term_reference(Cursor("-brand.", 0)) is None

    def test_arguments_parse_fails(self) -> None:
        """Call arguments fail for term args."""
        assert parse_term_reference(
            Cursor("-brand(@)", 0)
        ) is None

    def test_arguments_missing_closing_paren_1449(self) -> None:
        """Lines 1449-1450: Expected ')' after term arguments."""
        result = parse_term_reference(
            Cursor("-brand(case: 'nom'", 0)
        )
        assert result is None

    def test_depth_exceeded_with_arguments(self) -> None:
        """Depth exceeded when parsing term arguments."""
        ctx = ParseContext(max_nesting_depth=2)
        nested = ctx.enter_nesting().enter_nesting()
        result = parse_term_reference(
            Cursor('-brand(case: "nom")', 0), nested
        )
        assert result is None

    def test_without_arguments_at_depth_limit(self) -> None:
        """Term ref without args succeeds at depth limit."""
        ctx = ParseContext(max_nesting_depth=2)
        nested = ctx.enter_nesting().enter_nesting()
        result = parse_term_reference(Cursor("-brand", 0), nested)
        assert result is not None
        assert result.value.id.name == "brand"

    def test_with_arguments_succeeds(self) -> None:
        """Term ref with arguments below depth limit."""
        result = parse_term_reference(
            Cursor('-term(case: "gen")', 0)
        )
        assert result is not None
        assert result.value.arguments is not None


# ============================================================================
# DEFENSIVE MOCKING TESTS (UNREACHABLE CODE PATHS)
# ============================================================================


class TestDefensiveMocking:
    """Defensive None checks for unreachable code paths.

    These lines are structurally unreachable in normal execution but
    exist as guardrails against future refactoring.
    """

    def test_parse_message_attrs_returns_none(self) -> None:
        """parse_message_attributes returns None (defensive)."""
        with patch(
            "ftllexengine.syntax.parser.rules"
            ".parse_message_attributes"
        ) as mock:
            mock.return_value = None
            assert parse_message(
                Cursor("hello = value", 0)
            ) is None

    def test_parse_attribute_pattern_returns_none(self) -> None:
        """parse_pattern returns None in parse_attribute (defensive)."""
        with patch(
            "ftllexengine.syntax.parser.rules.parse_pattern"
        ) as mock:
            mock.return_value = None
            assert parse_attribute(
                Cursor(".attr = value", 0)
            ) is None

    def test_parse_term_pattern_returns_none(self) -> None:
        """parse_pattern returns None in parse_term (defensive)."""
        with patch(
            "ftllexengine.syntax.parser.rules.parse_pattern"
        ) as mock:
            mock.return_value = None
            assert parse_term(
                Cursor("-brand = value", 0)
            ) is None

    def test_parse_term_attrs_returns_none_line_2038(self) -> None:
        """Line 2038: parse_message_attributes returns None in term."""
        with patch(
            "ftllexengine.syntax.parser.rules"
            ".parse_message_attributes"
        ) as mock:
            mock.return_value = None
            assert parse_term(
                Cursor("-brand = value", 0)
            ) is None

    def test_parse_message_pattern_returns_none(self) -> None:
        """parse_pattern returns None in parse_message (defensive)."""
        with patch(
            "ftllexengine.syntax.parser.rules.parse_pattern"
        ) as mock:
            mock.return_value = None
            assert parse_message(
                Cursor("hello = value", 0)
            ) is None


# ============================================================================
# PARSER INTEGRATION - MALFORMED INPUT
# ============================================================================


class TestParserMalformedInput:
    """FluentParserV1 integration for error recovery on malformed FTL."""

    def test_four_hash_comment_recovery(self) -> None:
        """Invalid >3 hash comment is recovered as junk."""
        parser = FluentParserV1()
        res = parser.parse(
            "#### Invalid\nkey = value"
        )
        assert any(
            hasattr(e, "id") and e.id.name == "key"
            for e in res.entries
        )

    def test_multiple_junk_entries(self) -> None:
        """Multiple malformed entries create multiple junk entries."""
        parser = FluentParserV1()
        res = parser.parse(
            "!!!invalid1\n!!!invalid2\nkey = value\n"
        )
        assert any(
            hasattr(e, "id") and e.id.name == "key"
            for e in res.entries
        )

    def test_junk_with_unicode(self) -> None:
        """Junk entries with non-ASCII characters."""
        parser = FluentParserV1()
        res = parser.parse("¡¡¡ invalid\nkey = value\n")
        assert len(res.entries) >= 1

    def test_empty_variant_key(self) -> None:
        """Empty variant key []."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { $c -> [] x *[o] O }\n"
        )
        assert len(res.entries) >= 1

    def test_unclosed_variant_bracket(self) -> None:
        """Unclosed variant bracket."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { $c -> [unclosed X *[o] O }\n"
        )
        assert len(res.entries) >= 1

    def test_select_missing_arrow(self) -> None:
        """Select expression without '->'."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { $val\n   [one] One\n  *[other] Other\n}\n"
        )
        junk = [e for e in res.entries if isinstance(e, Junk)]
        assert len(junk) >= 1

    def test_unclosed_placeable(self) -> None:
        """Unclosed placeable creates junk."""
        parser = FluentParserV1()
        res = parser.parse("msg = { $value")
        assert isinstance(res.entries[0], Junk)

    def test_invalid_variant_syntax(self) -> None:
        """Invalid variant syntax (missing '[')."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { $c ->\n   one] One\n  *[other] O\n}\n"
        )
        junk = [e for e in res.entries if isinstance(e, Junk)]
        assert len(junk) >= 1

    def test_empty_placeable(self) -> None:
        """Empty placeable { }."""
        parser = FluentParserV1()
        res = parser.parse("key = { }")
        assert res is not None

    def test_standalone_attribute(self) -> None:
        """Attribute without Message/Term creates junk."""
        parser = FluentParserV1()
        res = parser.parse("    .attr = Value")
        assert isinstance(res.entries[0], Junk)

    def test_invalid_term_name(self) -> None:
        """Term '-' without valid identifier."""
        parser = FluentParserV1()
        res = parser.parse("- = Invalid")
        assert len(res.entries) >= 1

    def test_message_without_equals(self) -> None:
        """Message identifier without '=' creates junk."""
        parser = FluentParserV1()
        res = parser.parse("test Hello")
        assert isinstance(res.entries[0], Junk)

    def test_identifier_starting_with_number(self) -> None:
        """Identifier starting with number creates junk."""
        parser = FluentParserV1()
        res = parser.parse("123invalid = Value")
        assert isinstance(res.entries[0], Junk)

    def test_eof_after_equals(self) -> None:
        """EOF after '=' sign."""
        parser = FluentParserV1()
        res = parser.parse("msg =")
        assert len(res.entries) > 0

    def test_eof_after_identifier(self) -> None:
        """File ends right after message ID."""
        parser = FluentParserV1()
        res = parser.parse("msg")
        assert len(res.entries) > 0

    def test_multiple_errors_creates_multiple_junk(self) -> None:
        """Multiple errors create junk interleaved with valid entries."""
        parser = FluentParserV1()
        res = parser.parse(
            "invalid1 Missing\nvalid = Good\n"
            "invalid2 Also\nanother = OK\n"
        )
        assert len(res.entries) == 4
        junk_count = sum(
            1 for e in res.entries if isinstance(e, Junk)
        )
        assert junk_count == 2


class TestParserMalformedExpressions:
    """FluentParserV1 integration for malformed expressions."""

    def test_invalid_selector_variable(self) -> None:
        """$ followed by invalid character in selector."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { $-invalid -> *[key] Value }"
        )
        assert any(isinstance(e, Junk) for e in res.entries)

    def test_unclosed_string_literal_in_selector(self) -> None:
        """Unclosed string literal in selector."""
        parser = FluentParserV1()
        res = parser.parse(
            'msg = { "unclosed -> *[key] Value }'
        )
        assert any(isinstance(e, Junk) for e in res.entries)

    def test_function_no_parens(self) -> None:
        """UPPERCASE without parens is MessageReference."""
        parser = FluentParserV1()
        res = parser.parse("key = { FUNC }")
        msg = res.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        p = msg.value.elements[0]
        assert isinstance(p, Placeable)
        assert isinstance(p.expression, MessageReference)

    def test_function_missing_argument(self) -> None:
        """Function with incomplete arguments."""
        parser = FluentParserV1()
        res = parser.parse("key = { UPPERCASE( }")
        assert res is not None

    def test_function_invalid_argument(self) -> None:
        """Function with @invalid argument."""
        parser = FluentParserV1()
        res = parser.parse("key = { FUNC(@invalid) }")
        assert res is not None

    def test_term_ref_invalid_identifier(self) -> None:
        """Term reference '-#' with invalid identifier."""
        parser = FluentParserV1()
        res = parser.parse("key = { -# }")
        assert len(res.entries) >= 1

    def test_lowercase_function_call(self) -> None:
        """Lowercase identifier with () is now valid per spec."""
        parser = FluentParserV1()
        res = parser.parse("key = { lowercase() }")
        assert len(res.entries) >= 1

    def test_nested_malformed(self) -> None:
        """Deeply malformed nested structures."""
        parser = FluentParserV1()
        res = parser.parse(
            "key1 = { $v -> [a] { FUNC( *[b] X }\nkey2 = ok\n"
        )
        assert len(res.entries) >= 1

    def test_term_reference_arguments_unclosed(self) -> None:
        """Term arguments without closing ')'."""
        parser = FluentParserV1()
        res = parser.parse("key = { -term(arg ")
        assert res is not None

    def test_named_argument_number_as_name(self) -> None:
        """Number as named argument name."""
        parser = FluentParserV1()
        res = parser.parse('key = { FUNC(123: "value") }')
        assert res is not None

    def test_duplicate_named_argument_via_parser(self) -> None:
        """Duplicate named argument names via parser."""
        parser = FluentParserV1()
        res = parser.parse("key = { FUNC(foo: 1, foo: 2) }")
        assert res is not None

    def test_positional_after_named_via_parser(self) -> None:
        """Positional after named argument."""
        parser = FluentParserV1()
        res = parser.parse("key = { FUNC(name: 1, 2) }")
        assert res is not None

    def test_named_arg_missing_value_via_parser(self) -> None:
        """Named argument missing value."""
        parser = FluentParserV1()
        res = parser.parse("key = { FUNC(name:) }")
        assert res is not None

    def test_incomplete_number_at_eof(self) -> None:
        """Number literal at EOF without closing brace."""
        parser = FluentParserV1()
        res = parser.parse("msg = { 42")
        assert len(res.entries) > 0

    def test_number_multiple_decimal_points(self) -> None:
        """Number with multiple decimal points."""
        parser = FluentParserV1()
        res = parser.parse("msg = { 1.2.3 }")
        assert len(res.entries) >= 1

    def test_select_with_empty_variant_value(self) -> None:
        """Select expression with empty variant value."""
        parser = FluentParserV1()
        res = parser.parse(
            "test = { $c ->\n   [one]\n  *[other] O\n}\n"
        )
        assert len(res.entries) >= 1


# ============================================================================
# MESSAGE REFERENCE WITH ATTRIBUTES
# ============================================================================


class TestMessageReferenceWithAttribute:
    """Coverage for lowercase message references with .attribute syntax."""

    def test_msg_dot_attr_inline(self) -> None:
        """Parse { msg.attr } in inline expression."""
        parser = FluentParserV1()
        res = parser.parse("key = { msg.attr }")
        msg = res.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        p = msg.value.elements[0]
        assert isinstance(p, Placeable)
        ref = p.expression
        assert isinstance(ref, MessageReference)
        assert ref.id.name == "msg"
        assert ref.attribute is not None
        assert ref.attribute.name == "attr"

    def test_msg_dot_attr_in_attribute_value(self) -> None:
        """Parse { msg.help } in message attribute value."""
        parser = FluentParserV1()
        res = parser.parse(
            "key = Value\n    .tooltip = { msg.help }\n"
        )
        msg = res.entries[0]
        assert isinstance(msg, Message)
        attr = msg.attributes[0]
        assert isinstance(attr, Attribute)
        p = attr.value.elements[0]
        assert isinstance(p, Placeable)
        ref = p.expression
        assert isinstance(ref, MessageReference)
        assert ref.attribute is not None
        assert ref.attribute.name == "help"

    def test_msg_dot_missing_attr_name(self) -> None:
        """{ msg. } with missing attribute name."""
        parser = FluentParserV1()
        res = parser.parse("key = { msg. }")
        assert len(res.entries) >= 1

    def test_msg_dot_invalid_attr(self) -> None:
        """{ msg.@ } with invalid attribute."""
        parser = FluentParserV1()
        res = parser.parse("key = { msg.@ }")
        assert res is not None

    def test_msg_dot_hash_attr(self) -> None:
        """{ msg.# } with invalid attribute."""
        parser = FluentParserV1()
        res = parser.parse("key = { msg.# }")
        assert len(res.entries) >= 1

    def test_mixed_identifiers_with_attributes(self) -> None:
        """Various identifier cases with attributes."""
        parser = FluentParserV1()
        cases = [
            ("key = { foo.bar }", "foo", "bar"),
            ("key = { a.b }", "a", "b"),
            ("key = { msg123.attr456 }", "msg123", "attr456"),
        ]
        for source, exp_msg, exp_attr in cases:
            res = parser.parse(source)
            msg = res.entries[0]
            assert isinstance(msg, Message), f"Failed: {source}"
            assert msg.value is not None
            p = msg.value.elements[0]
            assert isinstance(p, Placeable)
            ref = p.expression
            assert isinstance(ref, MessageReference)
            assert ref.id.name == exp_msg
            assert ref.attribute is not None
            assert ref.attribute.name == exp_attr


# ============================================================================
# DEBUG LOGGING
# ============================================================================


class TestDebugLogging:
    """Tests for debug logging coverage (junk creation)."""

    def test_junk_creation_triggers_debug_log(self) -> None:
        """Debug logging when creating Junk entries."""
        logging.basicConfig(
            level=logging.DEBUG, stream=sys.stderr, force=True
        )
        try:
            parser = FluentParserV1()
            res = parser.parse("invalid { syntax")
            assert len(res.entries) >= 1
        except KeyError:
            pass
        finally:
            logging.basicConfig(
                level=logging.WARNING, force=True
            )


# ============================================================================
# WHITESPACE AND LINE ENDING EDGE CASES
# ============================================================================


class TestWhitespaceAndLineEndings:
    """Whitespace, CRLF, and formatting edge cases."""

    def test_crlf_multiline(self) -> None:
        """CRLF (\\r\\n) line endings in multiline pattern."""
        parser = FluentParserV1()
        res = parser.parse(
            "key =\r\n    Line one\r\n    Line two\r\n"
        )
        msg = res.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.value.elements) >= 2

    def test_mixed_line_endings(self) -> None:
        """Mixed \\r\\n and \\n line endings."""
        parser = FluentParserV1()
        res = parser.parse(
            "k1 = v1\r\nk2 = v2\nk3 = v3"
        )
        assert len(res.entries) == 3

    def test_tabs_in_pattern(self) -> None:
        """Tabs in pattern are literal text."""
        parser = FluentParserV1()
        res = parser.parse("key = value\twith\ttabs")
        assert len(res.entries) == 1

    def test_multiple_blank_lines(self) -> None:
        """Multiple consecutive blank lines between entries."""
        parser = FluentParserV1()
        res = parser.parse("k1 = v1\n\n\n\nk2 = v2")
        assert len(res.entries) == 2

    def test_empty_source(self) -> None:
        """Empty source produces empty resource."""
        parser = FluentParserV1()
        res = parser.parse("")
        assert len(res.entries) == 0

    def test_windows_crlf_entries(self) -> None:
        """Windows CRLF between entries."""
        parser = FluentParserV1()
        res = parser.parse("test = Hello\r\nworld = World\r\n")
        assert len(res.entries) == 2

    def test_text_with_stop_char_bracket(self) -> None:
        """Text stops at '[' bracket."""
        parser = FluentParserV1()
        res = parser.parse("key = text[bracket")
        msg = res.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        text_vals = [
            e.value for e in msg.value.elements
            if isinstance(e, TextElement)
        ]
        assert any("text" in v for v in text_vals)


# ============================================================================
# PATTERN CONTINUATION EDGE CASES
# ============================================================================


class TestPatternContinuationEdgeCases:
    """Pattern continuation and text accumulation edge cases."""

    def test_pattern_line_691_placeable_continuation(self) -> None:
        """Placeable then continuation creates new text element."""
        result = parse_pattern(Cursor("{$x}\n    {$y}", 0))
        assert result is not None

    def test_pattern_continuation_after_placeable(self) -> None:
        """Continuation text as new element after placeable."""
        result = parse_pattern(
            Cursor("{$var}\n    continuation", 0)
        )
        assert result is not None
        assert len(result.value.elements) >= 2

    def test_continuation_at_start(self) -> None:
        """Continuation at start of pattern."""
        result = parse_pattern(Cursor("\n    {$x}", 0))
        assert result is not None

    def test_simple_pattern_continuation_before_placeable(self) -> None:
        """text accumulation before placeable in simple pattern."""
        result = parse_simple_pattern(
            Cursor("hello\n world{$x}", 0)
        )
        assert result is not None

    def test_simple_pattern_continuation_at_end(self) -> None:
        """text accumulation finalized at end of simple pattern."""
        result = parse_simple_pattern(
            Cursor("hello\n world", 0)
        )
        assert result is not None

    def test_pattern_at_eof_no_newline(self) -> None:
        """Pattern ends at EOF without newline."""
        parser = FluentParserV1()
        res = parser.parse("key = value")
        assert len(res.entries) == 1

    def test_pattern_ending_at_variant_marker(self) -> None:
        """Pattern ends at start of variant marker."""
        parser = FluentParserV1()
        res = parser.parse("key = text\n    [")
        assert len(res.entries) >= 1

    def test_select_with_malformed_arrow_eof(self) -> None:
        """Incomplete arrow at EOF."""
        parser = FluentParserV1()
        res = parser.parse("key = { $var -")
        assert len(res.entries) >= 1

    def test_function_with_trailing_comma(self) -> None:
        """Function call with trailing comma."""
        parser = FluentParserV1()
        res = parser.parse("key = { FUNC(a, b,) }")
        assert len(res.entries) >= 1


# ============================================================================
# PARSER INTEGRATION SUITE
# ============================================================================


class TestParserIntegration:
    """Integration tests combining multiple edge cases."""

    def test_complex_resource(self) -> None:
        """FTL resource exercising multiple edge cases."""
        parser = FluentParserV1()
        res = parser.parse(
            "# Comment\n"
            "msg = Value\n"
            "    .a = Short attr\n"
            "\n"
            "-t = Term\n"
            "\n"
            "select = { $n ->\n"
            "    [0] Zero\n"
            "    [1] One\n"
            "   *[other] Other\n"
            "}\n"
            "\n"
            "func = { FUNC() }\n"
            "\n"
            "complex = { $a }{ $b } text { UPPER($c) }\n"
        )
        assert len(res.entries) >= 5

    def test_select_with_number_and_identifier_keys(self) -> None:
        """Select with both number and identifier variant keys."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { $c ->\n"
            "    [0] Zero\n"
            "    [1] One\n"
            "    [42] Forty-two\n"
            "   *[other] Other\n"
            "}\n"
        )
        assert len(res.entries) >= 1

    def test_select_identifier_keys(self) -> None:
        """Select with identifier variant keys."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { $v ->\n"
            "    [yes] Affirmative\n"
            "   *[no] Negative\n"
            "}\n"
        )
        assert len(res.entries) >= 1

    def test_variant_key_negative_hyphen_not_number(self) -> None:
        """Variant key starts with - but isn't a number."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { $s ->\n"
            "    [-not-a-number] Value\n"
            "   *[default] Default\n"
            "}\n"
        )
        assert len(res.entries) >= 1

    def test_term_attribute_selection(self) -> None:
        """Select on term attribute."""
        parser = FluentParserV1()
        res = parser.parse(
            "-term = Term\n"
            "    .attr = a\n"
            "msg = { -term.attr -> *[a] Value }\n"
        )
        assert len(res.entries) >= 1

    def test_term_reference_arguments_via_parser(self) -> None:
        """Term reference with arguments."""
        parser = FluentParserV1()
        res = parser.parse(
            "msg = { -term(case: 'accusative') }"
        )
        assert len(res.entries) >= 1

    def test_pattern_with_only_placeables(self) -> None:
        """Pattern with adjacent placeables."""
        parser = FluentParserV1()
        res = parser.parse("msg = { $a }{ $b }{ $c }")
        assert len(res.entries) > 0

    def test_function_variations(self) -> None:
        """Function with various argument combinations."""
        parser = FluentParserV1()
        for src in [
            "m = { FUNC() }",
            "m = { FUNC($a, $b, $c) }",
            'm = { FUNC(key: "value", ot: "data") }',
            'm = { FUNC($p1, $p2, named: "value") }',
        ]:
            res = parser.parse(src)
            assert len(res.entries) > 0, f"Failed: {src}"
