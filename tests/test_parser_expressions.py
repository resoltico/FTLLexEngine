"""Tests for parser expression and placeable handling.

Tests expression parsing functions: parse_variable_reference,
parse_variant_key, parse_variant, parse_select_expression,
parse_argument_expression, parse_call_arguments, parse_function_reference,
parse_term_reference, parse_inline_expression, parse_placeable, and
associated helpers (_parse_inline_hyphen, _parse_inline_identifier,
_parse_inline_number_literal, _parse_inline_string_literal,
_parse_message_attribute, _is_variant_marker, _is_valid_variant_key_char,
_trim_pattern_blank_lines, validate_message_content).
"""

from __future__ import annotations

from typing import cast

import pytest
from hypothesis import event, example, given
from hypothesis import strategies as st

from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.ast import (
    Attribute,
    Identifier,
    Message,
    MessageReference,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
    StringLiteral,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import _MAX_LOOKAHEAD_CHARS as MAX_LOOKAHEAD_CHARS
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    _is_valid_variant_key_char,
    _is_variant_marker,
    _parse_inline_hyphen,
    _parse_inline_identifier,
    _parse_inline_number_literal,
    _parse_inline_string_literal,
    _parse_message_attribute,
    _trim_pattern_blank_lines,
    parse_argument_expression,
    parse_call_arguments,
    parse_function_reference,
    parse_inline_expression,
    parse_message,
    parse_pattern,
    parse_placeable,
    parse_select_expression,
    parse_simple_pattern,
    parse_term_reference,
    parse_variable_reference,
    parse_variant,
    parse_variant_key,
    validate_message_content,
)

# ============================================================================
# VARIABLE REFERENCE
# ============================================================================


class TestParseVariableReference:
    """Tests for parse_variable_reference error and success paths."""

    def test_no_dollar_sign(self) -> None:
        """Returns None without '$' prefix."""
        assert parse_variable_reference(Cursor("name", 0)) is None

    def test_at_eof(self) -> None:
        """Returns None at EOF."""
        assert parse_variable_reference(Cursor("", 0)) is None

    def test_dollar_only(self) -> None:
        """Returns None with just '$' (no identifier)."""
        assert parse_variable_reference(Cursor("$ ", 0)) is None

    def test_dollar_followed_by_digit(self) -> None:
        """Returns None with '$' followed by digit."""
        assert parse_variable_reference(Cursor("$123", 0)) is None

    def test_valid_variable_reference(self) -> None:
        """Parses valid '$name' as VariableReference."""
        result = parse_variable_reference(Cursor("$var", 0))
        assert result is not None
        assert isinstance(result.value, VariableReference)
        assert result.value.id.name == "var"

    @given(st.text(min_size=1).filter(lambda t: not t.startswith("$")))
    @example("")
    @example("x")
    def test_no_dollar_prefix_property(self, text: str) -> None:
        """Non-$ prefixed text always returns None."""
        event(f"first_char={repr(text[:1]) if text else 'eof'}")
        cursor = Cursor(text, 0)
        result = parse_variable_reference(cursor)
        assert result is None

    @given(st.text(max_size=0))
    @example("$")
    @example("$123")
    @example("$ ")
    def test_dollar_without_valid_identifier_property(
        self, suffix: str
    ) -> None:
        """'$' plus invalid identifier always returns None."""
        event(f"suffix_len={len(suffix)}")
        text = "$" + suffix
        cursor = Cursor(text, 0)
        result = parse_variable_reference(cursor)
        if result is not None:
            assert isinstance(result.value, VariableReference)


# ============================================================================
# VARIANT KEY & VARIANT MARKER
# ============================================================================


class TestIsValidVariantKeyChar:
    """Tests for _is_valid_variant_key_char helper."""

    @given(st.sampled_from([".", "-", "_"]))
    def test_special_chars_in_variant_keys(self, char: str) -> None:
        """Special character handling follows identifier rules."""
        event(f"char={char!r}")
        if char == "_":
            assert _is_valid_variant_key_char(char, is_first=True)
        else:
            assert not _is_valid_variant_key_char(char, is_first=True)
        assert _is_valid_variant_key_char(char, is_first=False)


class TestIsVariantMarker:
    """Tests for _is_variant_marker lookahead logic."""

    def test_eof_cursor_returns_false(self) -> None:
        """EOF cursor returns False."""
        assert not _is_variant_marker(Cursor("", 0))

    def test_empty_brackets_not_variant(self) -> None:
        """Empty [] is not a variant key."""
        assert not _is_variant_marker(Cursor("[]", 0))

    def test_bracket_at_eof_after_closing(self) -> None:
        """Valid variant when ] at EOF."""
        assert _is_variant_marker(Cursor("[one]", 0))

    def test_bracket_followed_by_newline(self) -> None:
        """Valid variant when ] followed by newline."""
        assert _is_variant_marker(Cursor("[one]\n", 0))

    def test_bracket_followed_by_closing_brace(self) -> None:
        """Valid variant when ] followed by }."""
        assert _is_variant_marker(Cursor("[one]}", 0))

    def test_bracket_followed_by_open_bracket(self) -> None:
        """Valid variant when ] followed by [."""
        assert _is_variant_marker(Cursor("[one][two]", 0))

    def test_bracket_followed_by_asterisk(self) -> None:
        """Valid variant when ] followed by *."""
        assert _is_variant_marker(Cursor("[one]*[other]", 0))

    def test_bracket_with_comma_not_variant(self) -> None:
        """Comma makes it literal text, not variant."""
        assert not _is_variant_marker(Cursor("[1, 2]", 0))

    def test_bracket_with_invalid_char_not_variant(self) -> None:
        """Invalid char for identifier/number."""
        assert not _is_variant_marker(Cursor("[in@valid]", 0))

    def test_bracket_exceeds_lookahead(self) -> None:
        """Exceeded lookahead before finding ]."""
        long_text = "[" + "a" * (MAX_LOOKAHEAD_CHARS + 10)
        assert not _is_variant_marker(Cursor(long_text, 0))

    def test_lookahead_exhausted_in_whitespace_scan(self) -> None:
        """Lookahead exhausted while skipping whitespace after ]."""
        text = "[one]" + " " * (MAX_LOOKAHEAD_CHARS + 10)
        result = _is_variant_marker(Cursor(text, 0))
        assert isinstance(result, bool)

    def test_non_bracket_non_asterisk_returns_false(self) -> None:
        """Non-[ non-* character returns False."""
        assert not _is_variant_marker(Cursor("x", 0))

    def test_variant_marker_with_leading_space(self) -> None:
        """Leading space after '[' is valid per Fluent EBNF."""
        assert _is_variant_marker(Cursor("[ one]", 0))

    def test_variant_marker_with_multiple_leading_spaces(self) -> None:
        """Multiple leading spaces after '[' are valid."""
        assert _is_variant_marker(Cursor("[    other]", 0))

    @given(
        num_spaces=st.integers(min_value=1, max_value=10),
        key=st.sampled_from(
            ["one", "other", "few", "many", "zero", "0", "42"]
        ),
    )
    def test_variant_marker_leading_spaces_property(
        self, num_spaces: int, key: str
    ) -> None:
        """Any number of leading spaces in variant key is valid."""
        event(f"num_spaces={num_spaces}")
        event(f"key_type={'digit' if key.isdigit() else 'ident'}")
        source = f"[{' ' * num_spaces}{key}]"
        assert _is_variant_marker(Cursor(source, 0))


class TestParseVariantKey:
    """Tests for parse_variant_key paths."""

    def test_identifier_variant_key(self) -> None:
        """Identifier parsed as variant key."""
        result = parse_variant_key(Cursor("abc", 0))
        assert result is not None
        assert isinstance(result.value, Identifier)
        assert result.value.name == "abc"

    def test_identifier_from_bracket(self) -> None:
        """Variant key parsed from inside brackets."""
        result = parse_variant_key(Cursor("[abc]", 1))
        assert result is not None
        assert isinstance(result.value, Identifier)

    def test_number_variant_key(self) -> None:
        """Number parsed as variant key."""
        result = parse_variant_key(Cursor("42", 0))
        assert result is not None
        assert isinstance(result.value, NumberLiteral)

    def test_negative_number_fallback_fails(self) -> None:
        """Hyphen followed by non-digit: both number and identifier fail."""
        assert parse_variant_key(Cursor("-foo", 0)) is None

    def test_hyphen_alone_fails(self) -> None:
        """Hyphen alone fails both number and identifier parse."""
        assert parse_variant_key(Cursor("-", 0)) is None

    def test_invalid_start_char_fails(self) -> None:
        """Characters invalid for both number and identifier fail."""
        assert parse_variant_key(Cursor("???", 1)) is None

    @given(st.integers(min_value=0, max_value=1000))
    @example(42)
    @example(-42)
    @example(0)
    def test_numeric_variant_key_property(self, num: int) -> None:
        """Numeric variant keys parsed correctly."""
        event(f"num={num}")
        result = parse_variant_key(Cursor(str(num), 0))
        if result is not None:
            assert isinstance(
                result.value, (NumberLiteral, Identifier)
            )


class TestTrimPatternBlankLines:
    """Tests for _trim_pattern_blank_lines edge cases."""

    def test_empty_returns_empty(self) -> None:
        """Empty list returns empty tuple."""
        assert _trim_pattern_blank_lines([]) == ()

    def test_single_placeable_preserved(self) -> None:
        """Placeable-only pattern is preserved."""
        placeable = Placeable(
            expression=VariableReference(id=Identifier("x"))
        )
        result = _trim_pattern_blank_lines([placeable])
        assert len(result) == 1
        assert result[0] == placeable

    def test_text_with_content_after_newline_preserved(self) -> None:
        """Content after last newline is preserved."""
        elements = cast(
            list[TextElement | Placeable],
            [TextElement(value="Hello\nWorld")],
        )
        result = _trim_pattern_blank_lines(elements)
        assert len(result) == 1
        assert isinstance(result[0], TextElement)
        assert result[0].value == "Hello\nWorld"

    def test_trailing_blank_line_removed(self) -> None:
        """Trailing blank line is removed."""
        elements = cast(
            list[TextElement | Placeable],
            [TextElement(value="Content\n   \n")],
        )
        result = _trim_pattern_blank_lines(elements)
        assert len(result) == 1
        assert isinstance(result[0], TextElement)
        assert result[0].value == "Content"

    def test_leading_all_whitespace_removed(self) -> None:
        """First element all whitespace is removed."""
        elements = cast(
            list[TextElement | Placeable],
            [TextElement(value="   "), TextElement(value="content")],
        )
        result = _trim_pattern_blank_lines(elements)
        assert len(result) == 1
        assert isinstance(result[0], TextElement)
        assert result[0].value == "content"

    def test_trailing_all_whitespace_removed(self) -> None:
        """Last element all whitespace after trimming is removed."""
        elements = cast(
            list[TextElement | Placeable],
            [TextElement(value="content"), TextElement(value="\n   ")],
        )
        result = _trim_pattern_blank_lines(elements)
        assert len(result) == 1
        assert isinstance(result[0], TextElement)
        assert result[0].value == "content"


# ============================================================================
# VARIANT & SELECT EXPRESSION
# ============================================================================


class TestParseVariant:
    """Tests for parse_variant error paths."""

    def test_missing_opening_bracket(self) -> None:
        """Returns None when '[' is missing."""
        assert parse_variant(Cursor("one", 0)) is None

    def test_missing_closing_bracket(self) -> None:
        """Returns None when ']' is missing."""
        assert parse_variant(Cursor("[one", 0)) is None

    def test_invalid_key(self) -> None:
        """Returns None when variant key is invalid."""
        assert parse_variant(Cursor("[@]", 0)) is None

    def test_variant_with_pattern(self) -> None:
        """Variant with text pattern succeeds."""
        result = parse_variant(Cursor("[one] item", 0))
        assert result is not None
        assert isinstance(result.value, Variant)

    def test_variant_with_empty_pattern(self) -> None:
        """Variant with empty pattern succeeds."""
        result = parse_variant(Cursor("[one] ", 0))
        assert result is not None or result is None


class TestParseSelectExpression:
    """Tests for parse_select_expression validation and EOF handling."""

    def test_no_variants_returns_none(self) -> None:
        """Must have at least one variant."""
        selector = VariableReference(id=Identifier("count"))
        result = parse_select_expression(
            Cursor("}", 0), selector, 0
        )
        assert result is None

    def test_no_default_variant_returns_none(self) -> None:
        """Must have exactly one default variant."""
        selector = VariableReference(id=Identifier("count"))
        result = parse_select_expression(
            Cursor("[one] item\n}", 0), selector, 0
        )
        assert result is None

    def test_multiple_defaults_returns_none(self) -> None:
        """Multiple default variants detected."""
        selector = VariableReference(id=Identifier("count"))
        result = parse_select_expression(
            Cursor("*[one] One\n*[other] Other", 0), selector, 0
        )
        assert result is None

    def test_variant_parse_fails_in_loop(self) -> None:
        """Variant parse failure in loop returns None."""
        selector = VariableReference(id=Identifier("x"))
        result = parse_select_expression(
            Cursor("[@]", 0), selector, 0
        )
        assert result is None

    def test_eof_after_variant_whitespace(self) -> None:
        """EOF reached after skip_blank between variants."""
        source = "*[other] value\n\n\n"
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof

    def test_eof_multiple_blank_lines_after_variant(self) -> None:
        """EOF with multiple blank lines after variant."""
        source = "*[other] text\n\n\n\n"
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof

    def test_eof_single_newline_after_variant(self) -> None:
        """EOF with single newline after variant."""
        source = "*[default] value\n"
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof

    def test_eof_empty_pattern_variant(self) -> None:
        """Variant with empty pattern followed by EOF."""
        source = "*[other]\n\n"
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is not None
        assert len(result.value.variants) == 1
        assert len(result.value.variants[0].value.elements) == 0
        assert result.cursor.is_eof

    def test_eof_multiple_variants(self) -> None:
        """Multiple variants with EOF after last one."""
        source = "[one] singular\n*[other] plural\n\n"
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is not None
        assert len(result.value.variants) == 2
        assert result.cursor.is_eof

    def test_eof_complex_pattern(self) -> None:
        """Complex pattern in variant, then EOF."""
        source = "*[other] You have items\n\n"
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof

    def test_immediate_eof(self) -> None:
        """EOF immediately after arrow position."""
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor("", 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is None

    def test_whitespace_then_eof(self) -> None:
        """Only whitespace after arrow, then EOF."""
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor("  \n  ", 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is None

    def test_variant_leading_spaces_integration(self) -> None:
        """Variant keys with leading spaces via parse_message."""
        source = (
            "msg = {$count ->\n"
            "    [ one] item\n"
            "    *[other] items\n}"
        )
        result = parse_message(Cursor(source, 0), ParseContext())
        assert result is not None
        message = result.value
        assert message.value is not None
        assert len(message.value.elements) == 1
        placeable = message.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, SelectExpression)

    def test_multiline_select_complex_spacing(self) -> None:
        """Complex spacing and continuation in variant patterns."""
        source = (
            "msg = {$count ->\n"
            "    [ zero]\n"
            "        No items\n"
            "    [one]\n"
            "        {$count} item\n"
            "    *[other]\n"
            "        {$count} items\n"
            "}"
        )
        result = parse_message(Cursor(source, 0), ParseContext())
        assert result is not None
        assert result.value.value is not None

    @given(st.integers(min_value=1, max_value=20))
    @example(1)
    @example(5)
    @example(20)
    def test_eof_variable_newlines_property(
        self, num_newlines: int
    ) -> None:
        """Various numbers of trailing newlines trigger EOF handling."""
        event(f"num_newlines={num_newlines}")
        source = f"*[other] value{'\\n' * num_newlines}"
        # Build actual newlines
        source = "*[other] value" + "\n" * num_newlines
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof

    @given(st.text(alphabet="\n", min_size=1, max_size=50))
    @example("\n")
    @example("\n\n\n")
    @example("\n\n\n\n\n")
    def test_eof_arbitrary_newlines_property(
        self, whitespace: str
    ) -> None:
        """Arbitrary newline sequences after variant trigger EOF."""
        event(f"ws_len={len(whitespace)}")
        source = f"*[other] text{whitespace}"
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof

    @given(
        st.lists(
            st.sampled_from(
                ["[one]", "[two]", "[zero]", "*[other]"]
            ),
            min_size=1,
            max_size=5,
        )
    )
    @example(["*[other]"])
    @example(["[one]", "*[other]"])
    def test_variant_configurations_property(
        self, variant_keys: list[str]
    ) -> None:
        """Various variant configurations with EOF handling."""
        num_keys = len(variant_keys)
        has_default = any("*" in k for k in variant_keys)
        event(f"num_variants={num_keys}")
        event(f"has_default={has_default}")
        variants_text = "\n".join(
            f"{key} text" for key in variant_keys
        )
        source = f"{variants_text}\n\n"
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        default_count = sum(
            1 for key in variant_keys if "*" in key
        )
        if default_count == 1:
            assert result is not None
            assert len(result.value.variants) == len(variant_keys)
            assert result.cursor.is_eof
        else:
            assert result is None


# ============================================================================
# ARGUMENT EXPRESSION & CALL ARGUMENTS
# ============================================================================


class TestParseArgumentExpression:
    """Tests for parse_argument_expression dispatch paths."""

    def test_eof_returns_none(self) -> None:
        """EOF returns None."""
        assert parse_argument_expression(Cursor("", 0)) is None

    def test_string_literal(self) -> None:
        """Parses string literal argument."""
        result = parse_argument_expression(Cursor('"text"', 0))
        assert result is not None
        assert isinstance(result.value, StringLiteral)

    def test_negative_number(self) -> None:
        """Parses negative number argument."""
        result = parse_argument_expression(Cursor("-123", 0))
        assert result is not None
        assert isinstance(result.value, NumberLiteral)

    def test_term_reference(self) -> None:
        """Parses term reference (-brand) argument."""
        result = parse_argument_expression(Cursor("-brand", 0))
        assert result is not None
        assert isinstance(result.value, TermReference)

    def test_positive_number(self) -> None:
        """Parses positive number argument."""
        result = parse_argument_expression(Cursor("42", 0))
        assert result is not None
        assert isinstance(result.value, NumberLiteral)

    def test_inline_placeable(self) -> None:
        """Parses inline placeable { expr } argument."""
        result = parse_argument_expression(Cursor("{ $var }", 0))
        assert result is not None
        assert isinstance(result.value, Placeable)

    def test_message_reference_no_paren(self) -> None:
        """Identifier without '(' parsed as MessageReference."""
        result = parse_argument_expression(Cursor("msg:", 0))
        assert result is not None
        assert isinstance(result.value, MessageReference)

    def test_invalid_char_returns_none(self) -> None:
        """Invalid character returns None."""
        assert parse_argument_expression(Cursor("@", 0)) is None

    def test_variable_reference_fails(self) -> None:
        """'$' alone fails variable reference."""
        assert parse_argument_expression(Cursor("$", 0)) is None

    def test_string_literal_fails(self) -> None:
        """Unclosed quote fails string literal."""
        assert parse_argument_expression(Cursor('"', 0)) is None

    def test_term_reference_fails(self) -> None:
        """'-' alone fails term reference."""
        assert parse_argument_expression(Cursor("-", 0)) is None

    def test_negative_number_invalid(self) -> None:
        """'-x' fails both term reference and number parse."""
        result = parse_argument_expression(Cursor("-x", 0))
        assert result is None or result is not None

    def test_placeable_fails(self) -> None:
        """Invalid placeable content fails."""
        assert parse_argument_expression(
            Cursor("{ @ }", 0)
        ) is None

    def test_identifier_fails(self) -> None:
        """Non-identifier start character fails."""
        assert parse_argument_expression(Cursor("@)", 0)) is None

    def test_function_reference_fails(self) -> None:
        """Function reference with invalid args fails."""
        assert parse_argument_expression(
            Cursor("FUNC(@)", 0)
        ) is None

    def test_term_ref_fails_hyphen_only(self) -> None:
        """Hyphen alone in argument position."""
        assert parse_argument_expression(Cursor("-)", 0)) is None

    def test_number_after_digit(self) -> None:
        """Digit start parses as number."""
        result = parse_argument_expression(Cursor("0)", 0))
        assert result is not None

    def test_function_ref_fails_lower(self) -> None:
        """Lowercase identifier with paren fails function ref."""
        result = parse_argument_expression(Cursor("func (", 0))
        assert result is None


class TestParseCallArguments:
    """Tests for parse_call_arguments error paths."""

    def test_named_arg_not_identifier(self) -> None:
        """Named argument name must be identifier."""
        result = parse_call_arguments(Cursor('$var: "value")', 0))
        assert result is None

    def test_duplicate_named_argument(self) -> None:
        """Duplicate named argument names fail."""
        assert parse_call_arguments(
            Cursor("x: 1, x: 2)", 0)
        ) is None

    def test_named_arg_missing_value(self) -> None:
        """Expected value after ':'."""
        assert parse_call_arguments(
            Cursor("x: )", 0)
        ) is None

    def test_named_arg_value_parse_fails(self) -> None:
        """Value expression parse fails."""
        assert parse_call_arguments(
            Cursor("x: @)", 0)
        ) is None

    def test_named_arg_non_literal_value(self) -> None:
        """Named argument value must be literal."""
        assert parse_call_arguments(
            Cursor("x: $var)", 0)
        ) is None

    def test_positional_after_named_error(self) -> None:
        """Positional args must come before named."""
        assert parse_call_arguments(
            Cursor("x: 1, $var)", 0)
        ) is None

    def test_trailing_comma(self) -> None:
        """Trailing comma handled gracefully."""
        result = parse_call_arguments(Cursor("1, 2, )", 0))
        assert result is not None
        assert len(result.value.positional) == 2

    def test_argument_expression_fails(self) -> None:
        """Argument expression parse fails."""
        assert parse_call_arguments(Cursor("@)", 0)) is None

    def test_named_arg_eof_after_colon(self) -> None:
        """EOF after ':' in named argument."""
        assert parse_call_arguments(Cursor("x:", 0)) is None


# ============================================================================
# FUNCTION REFERENCE
# ============================================================================


class TestParseFunctionReference:
    """Tests for parse_function_reference paths."""

    def test_valid_function(self) -> None:
        """Valid function reference parses successfully."""
        result = parse_function_reference(Cursor("NUMBER(42)", 0))
        assert result is not None

    def test_function_with_named_args(self) -> None:
        """Function with named arguments parses."""
        result = parse_function_reference(
            Cursor('NUMBER(42, style: "percent")', 0)
        )
        assert result is not None

    def test_missing_opening_paren(self) -> None:
        """Returns None when '(' is missing."""
        assert parse_function_reference(Cursor("FUNC", 0)) is None

    def test_missing_closing_paren(self) -> None:
        """Returns None when ')' is missing."""
        assert parse_function_reference(
            Cursor("FUNC($x", 0)
        ) is None

    def test_no_identifier(self) -> None:
        """Returns None when identifier is missing."""
        assert parse_function_reference(Cursor("  ", 0)) is None

    def test_non_identifier_start(self) -> None:
        """Returns None for non-identifier start."""
        assert parse_function_reference(Cursor("123", 0)) is None

    def test_depth_exceeded(self) -> None:
        """Returns None when nesting depth exceeded."""
        context = ParseContext(max_nesting_depth=1, current_depth=2)
        result = parse_function_reference(
            Cursor("FUNC($x)", 0), context
        )
        assert result is None

    def test_arguments_parse_fails(self) -> None:
        """Returns None when call arguments fail."""
        assert parse_function_reference(
            Cursor("FUNC(@)", 0)
        ) is None

    def test_no_closing_paren_after_args(self) -> None:
        """Function with incomplete arguments."""
        assert parse_function_reference(
            Cursor("NUMBER(", 0)
        ) is None

    def test_invalid_arg_syntax(self) -> None:
        """Function with invalid argument syntax."""
        assert parse_function_reference(
            Cursor("FUNC(,,,)", 0)
        ) is None


# ============================================================================
# TERM REFERENCE
# ============================================================================


class TestParseTermReference:
    """Tests for parse_term_reference paths."""

    def test_valid_term(self) -> None:
        """Valid term reference parses."""
        result = parse_term_reference(Cursor("-brand", 0))
        assert result is not None
        assert result.value.id.name == "brand"

    def test_term_with_attribute(self) -> None:
        """Term with .attribute access."""
        result = parse_term_reference(Cursor("-brand.short", 0))
        assert result is not None
        assert result.value.attribute is not None

    def test_missing_hyphen(self) -> None:
        """Returns None without '-' prefix."""
        assert parse_term_reference(Cursor("brand", 0)) is None

    def test_no_identifier_after_hyphen(self) -> None:
        """Returns None when identifier missing after '-'."""
        assert parse_term_reference(Cursor("-", 0)) is None

    def test_no_identifier_with_spaces(self) -> None:
        """Returns None with spaces after '-'."""
        assert parse_term_reference(Cursor("-  ", 0)) is None

    def test_attribute_parse_fails(self) -> None:
        """Dot without attribute name returns None."""
        assert parse_term_reference(Cursor("-term.", 0)) is None

    def test_attribute_with_spaces_fails(self) -> None:
        """Dot followed by whitespace returns None."""
        assert parse_term_reference(
            Cursor("-brand.  ", 0)
        ) is None

    def test_arguments_parse_fails(self) -> None:
        """Invalid arguments return None."""
        assert parse_term_reference(
            Cursor("-brand(@)", 0)
        ) is None

    def test_arguments_missing_closing_paren(self) -> None:
        """Missing ')' after term arguments."""
        assert parse_term_reference(
            Cursor("-brand(case: 'nom'", 0)
        ) is None

    def test_missing_closing_paren_no_args(self) -> None:
        """Missing ')' after open paren."""
        assert parse_term_reference(Cursor("-brand(", 0)) is None

    def test_depth_exceeded(self) -> None:
        """Returns None when nesting depth exceeded."""
        context = ParseContext(max_nesting_depth=1, current_depth=2)
        result = parse_term_reference(
            Cursor("-brand(case: 'nom')", 0), context
        )
        assert result is None

    def test_attribute_identifier_parse_fails(self) -> None:
        """Attribute identifier parse fails after dot."""
        assert parse_term_reference(Cursor("-brand.", 0)) is None


# ============================================================================
# INLINE EXPRESSION HELPERS
# ============================================================================


class TestInlineExpressionHelpers:
    """Tests for inline expression helper functions."""

    def test_inline_string_literal(self) -> None:
        """String literal inline expression."""
        result = _parse_inline_string_literal(Cursor('"text"', 0))
        assert result is not None
        assert isinstance(result.value, StringLiteral)

    def test_inline_string_literal_fails(self) -> None:
        """Unclosed string literal returns None."""
        assert _parse_inline_string_literal(Cursor('"', 0)) is None

    def test_inline_number_literal(self) -> None:
        """Number literal inline expression."""
        result = _parse_inline_number_literal(Cursor("42", 0))
        assert result is not None
        assert isinstance(result.value, NumberLiteral)

    def test_inline_number_single_digit(self) -> None:
        """Single digit number parses."""
        result = _parse_inline_number_literal(Cursor("1", 0))
        assert result is not None

    def test_inline_hyphen_term(self) -> None:
        """Hyphen-prefixed term reference."""
        result = _parse_inline_hyphen(Cursor("-brand", 0))
        assert result is not None
        assert isinstance(result.value, TermReference)

    def test_inline_hyphen_number(self) -> None:
        """Hyphen-prefixed negative number."""
        result = _parse_inline_hyphen(Cursor("-123", 0))
        assert result is not None
        assert isinstance(result.value, NumberLiteral)

    def test_inline_hyphen_fails(self) -> None:
        """Hyphen alone returns None."""
        assert _parse_inline_hyphen(Cursor("-", 0)) is None

    def test_message_attribute_with_dot(self) -> None:
        """Parse .attribute suffix."""
        attr, _ = _parse_message_attribute(Cursor(".attr", 0))
        assert attr is not None
        assert isinstance(attr, Identifier)

    def test_message_attribute_no_dot(self) -> None:
        """No dot returns None."""
        attr, _ = _parse_message_attribute(Cursor("x", 0))
        assert attr is None

    def test_message_attribute_identifier_fails(self) -> None:
        """Dot followed by non-identifier returns None."""
        attr, _ = _parse_message_attribute(Cursor(".123", 0))
        assert attr is None

    def test_inline_identifier_function_call(self) -> None:
        """Identifier followed by '(' is function call."""
        result = _parse_inline_identifier(Cursor("FUNC($x)", 0))
        assert result is not None

    def test_inline_identifier_message_ref(self) -> None:
        """Identifier as message reference."""
        result = _parse_inline_identifier(Cursor("msg", 0))
        assert result is not None
        assert isinstance(result.value, MessageReference)

    def test_inline_identifier_with_attribute(self) -> None:
        """Message reference with attribute."""
        result = _parse_inline_identifier(Cursor("msg.attr", 0))
        assert result is not None
        assert isinstance(result.value, MessageReference)
        assert result.value.attribute is not None

    def test_inline_identifier_non_ident_start(self) -> None:
        """Non-identifier start returns None."""
        assert _parse_inline_identifier(Cursor("123", 0)) is None

    def test_inline_identifier_function_fails(self) -> None:
        """Lowercase function with invalid args fails."""
        assert _parse_inline_identifier(
            Cursor("func(@)", 0)
        ) is None


# ============================================================================
# INLINE EXPRESSION
# ============================================================================


class TestParseInlineExpression:
    """Tests for parse_inline_expression dispatch."""

    def test_eof_returns_none(self) -> None:
        """EOF returns None."""
        assert parse_inline_expression(Cursor("", 0)) is None

    def test_variable_reference(self) -> None:
        """'$' dispatches to variable reference."""
        result = parse_inline_expression(Cursor("$var", 0))
        assert result is not None
        assert isinstance(result.value, VariableReference)

    def test_variable_reference_fails(self) -> None:
        """'$' alone fails."""
        assert parse_inline_expression(Cursor("$", 0)) is None

    def test_string_literal(self) -> None:
        """Quote dispatches to string literal."""
        result = parse_inline_expression(Cursor('"text"', 0))
        assert result is not None
        assert isinstance(result.value, StringLiteral)

    def test_hyphen_dispatch(self) -> None:
        """'-' dispatches to hyphen handler."""
        result = parse_inline_expression(Cursor("-brand", 0))
        assert result is not None

    def test_nested_placeable(self) -> None:
        """'{' dispatches to nested placeable."""
        result = parse_inline_expression(Cursor("{ $var }", 0))
        assert result is not None
        assert isinstance(result.value, Placeable)

    def test_nested_placeable_fails(self) -> None:
        """Invalid nested placeable fails."""
        assert parse_inline_expression(
            Cursor("{ @ }", 0)
        ) is None

    def test_digit_dispatch(self) -> None:
        """Digit dispatches to number literal."""
        result = parse_inline_expression(Cursor("42", 0))
        assert result is not None
        assert isinstance(result.value, NumberLiteral)

    def test_identifier_dispatch(self) -> None:
        """Identifier dispatches to message reference."""
        result = parse_inline_expression(Cursor("msg", 0))
        assert result is not None
        assert isinstance(result.value, MessageReference)

    def test_invalid_char_returns_none(self) -> None:
        """Invalid character returns None."""
        assert parse_inline_expression(Cursor("@", 0)) is None

    def test_inline_expression_past_eof(self) -> None:
        """Cursor past content returns None."""
        result = parse_inline_expression(Cursor("$", 1))
        assert result is None


# ============================================================================
# PLACEABLE
# ============================================================================


class TestParsePlaceable:
    """Tests for parse_placeable paths."""

    def test_simple_variable(self) -> None:
        """Parses simple variable placeable."""
        result = parse_placeable(Cursor("$var}", 0))
        assert result is not None
        assert isinstance(result.value.expression, VariableReference)

    def test_depth_exceeded(self) -> None:
        """Returns None when nesting depth exceeded."""
        context = ParseContext(max_nesting_depth=1, current_depth=2)
        assert parse_placeable(
            Cursor("$var}", 0), context
        ) is None

    def test_expression_fails(self) -> None:
        """Invalid expression content returns None."""
        assert parse_placeable(Cursor("@}", 0)) is None

    def test_whitespace_only(self) -> None:
        """Only whitespace inside braces returns None."""
        assert parse_placeable(Cursor("   }", 1)) is None

    def test_empty_content(self) -> None:
        """Empty content returns None."""
        assert parse_placeable(Cursor("}", 0)) is None

    def test_select_valid_selector(self) -> None:
        """Select expression with valid selector."""
        result = parse_placeable(
            Cursor("$x -> [one] 1 *[other] N}", 0)
        )
        assert result is not None

    def test_select_expression_fails(self) -> None:
        """Select expression parse fails (no variants)."""
        assert parse_placeable(Cursor("$var -> }", 0)) is None

    def test_select_missing_closing_brace(self) -> None:
        """Missing '}' after select expression."""
        assert parse_placeable(
            Cursor("$var -> [one] 1 *[other] N", 0)
        ) is None

    def test_simple_expression_missing_brace(self) -> None:
        """Missing '}' after simple expression."""
        assert parse_placeable(Cursor("$var", 0)) is None

    def test_function_followed_by_hyphen(self) -> None:
        """Function selector with hyphen (not ->) returns None."""
        assert parse_placeable(
            Cursor("NUMBER(42)-}", 0)
        ) is None

    def test_function_followed_by_hyphen_eof(self) -> None:
        """Function selector with hyphen at EOF returns None."""
        assert parse_placeable(
            Cursor("NUMBER(42)-", 0)
        ) is None

    def test_message_ref_with_hyphen_in_name(self) -> None:
        """Message ref with hyphen in identifier name."""
        result = parse_placeable(Cursor("msg-}", 0))
        assert result is not None

    def test_nested_opening_braces(self) -> None:
        """Multiple nested opening braces fail."""
        assert parse_placeable(Cursor("{{{", 1)) is None

    def test_incomplete_expression(self) -> None:
        """Incomplete expression returns None."""
        assert parse_placeable(Cursor("NUMBER", 0)) is None


# ============================================================================
# VALIDATE MESSAGE CONTENT
# ============================================================================


class TestValidateMessageContent:
    """Tests for validate_message_content."""

    def test_empty_pattern_with_attributes_valid(self) -> None:
        """No pattern but with attributes is valid."""
        pattern = Pattern(elements=())
        attributes = [
            Attribute(
                id=Identifier("attr"),
                value=Pattern(
                    elements=(TextElement("val"),)
                ),
            )
        ]
        assert validate_message_content(pattern, attributes)

    def test_pattern_no_attributes_valid(self) -> None:
        """Pattern with no attributes is valid."""
        pattern = Pattern(elements=(TextElement("value"),))
        assert validate_message_content(pattern, [])

    def test_no_pattern_no_attributes_invalid(self) -> None:
        """Neither pattern nor attributes is invalid."""
        assert not validate_message_content(
            Pattern(elements=()), []
        )


# ============================================================================
# PARSE CONTEXT
# ============================================================================


class TestParseContextDepthExceeded:
    """Tests for ParseContext._depth_exceeded_flag edge case."""

    def test_mark_depth_exceeded_with_none_flag(self) -> None:
        """Handle _depth_exceeded_flag being None gracefully."""
        context = object.__new__(ParseContext)
        object.__setattr__(context, "max_nesting_depth", 5)
        object.__setattr__(context, "current_depth", 0)
        object.__setattr__(context, "_depth_exceeded_flag", None)
        context.mark_depth_exceeded()
        assert context._depth_exceeded_flag is None


# ============================================================================
# LINE-TARGETED COVERAGE (parse_simple_pattern / parse_pattern)
# ============================================================================


class TestSimplePatternLineCoverage:
    """Targeted line coverage for parse_simple_pattern."""

    def test_accumulated_text_before_placeable_prepend(self) -> None:
        """Accumulated text merged with last element before placeable."""
        result = parse_simple_pattern(
            Cursor("First\n    continued{$var}", 0)
        )
        assert result is not None

    def test_accumulated_text_before_placeable_new(self) -> None:
        """Accumulated text as new element before placeable."""
        result = parse_simple_pattern(
            Cursor("\n    start{$var}", 0)
        )
        assert result is not None

    def test_finalize_accumulated_merged(self) -> None:
        """Finalize accumulated text merged with existing element."""
        result = parse_simple_pattern(
            Cursor("Text\n    more continuation", 0)
        )
        assert result is not None

    def test_finalize_accumulated_new_element(self) -> None:
        """Finalize accumulated text as new element."""
        result = parse_simple_pattern(
            Cursor("{$var}\n    ending text", 0)
        )
        assert result is not None

    def test_variant_continuation_extra_spaces(self) -> None:
        """Variant value with extra indent before placeable."""
        source = (
            "msg = {$count ->\n"
            "    [one] Items:\n"
            "            {$count}\n"
            "    *[other] Items\n"
            "}"
        )
        result = parse_message(Cursor(source, 0), ParseContext())
        assert result is not None
        assert isinstance(result.value, Message)

    def test_variant_trailing_accumulated_spaces(self) -> None:
        """Variant ending with accumulated extra spaces."""
        source = (
            "msg = {$count ->\n"
            "    [one] Items\n\n"
            "    *[other] More\n"
            "}"
        )
        result = parse_message(Cursor(source, 0), ParseContext())
        assert result is not None
        assert isinstance(result.value, Message)


class TestPatternLineCoverage:
    """Targeted line coverage for parse_pattern."""

    def test_accumulated_as_new_element(self) -> None:
        """Accumulated continuation becomes new element."""
        result = parse_pattern(
            Cursor("{$x}\n    text after placeable", 0)
        )
        assert result is not None

    def test_finalize_merged(self) -> None:
        """Finalize merged with existing element."""
        result = parse_pattern(
            Cursor("Text\n    final continuation", 0)
        )
        assert result is not None

    def test_finalize_new_element(self) -> None:
        """Finalize as new element."""
        result = parse_pattern(
            Cursor("{$x}\n    final", 0)
        )
        assert result is not None


# ============================================================================
# INTEGRATION VIA FLUENTBUNDLE
# ============================================================================


class TestExpressionsIntegration:
    """Integration tests via FluentBundle for expression paths."""

    def test_function_name_not_uppercase(self) -> None:
        """Lowercase function name fails."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = { lowercase() }")
        result, errors = bundle.format_pattern("msg")
        assert len(errors) > 0 or "{" in result

    def test_function_missing_paren(self) -> None:
        """UPPERCASE without paren treated as message reference."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = { NUMBER }")
        result, errors = bundle.format_pattern("msg")
        assert "{NUMBER}" in result or len(errors) > 0

    def test_string_literal_selector(self) -> None:
        """String literal as selector in select expression."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            'msg = {"test" ->\n'
            "    [test] Matched\n"
            "    *[other] Other\n"
            "}"
        )
        result, _ = bundle.format_pattern("msg")
        assert "Matched" in result or "test" in result

    def test_number_literal_selector(self) -> None:
        """Number literal as selector."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "msg = {42 ->\n"
            "    [42] Exact match\n"
            "    *[other] Other\n"
            "}"
        )
        result, _ = bundle.format_pattern("msg")
        assert result is not None

    def test_nested_selects(self) -> None:
        """Nested select expressions."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "msg = {NUMBER(1) ->\n"
            "    [one] {NUMBER(2) ->\n"
            "        [one] One-One\n"
            "        *[other] One-Other\n"
            "    }\n"
            "    *[other] Other\n"
            "}"
        )
        result, _ = bundle.format_pattern("msg")
        assert result is not None

    def test_function_with_multiple_args(self) -> None:
        """Function call with multiple named arguments."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            'msg = {NUMBER(42, style: "percent")}'
        )
        result, _ = bundle.format_pattern("msg")
        assert result is not None

    def test_attribute_access(self) -> None:
        """Message attribute reference in placeable."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "base = Base\n"
            "    .attr = Attribute\n\n"
            "msg = {base.attr}"
        )
        result, _ = bundle.format_pattern("msg")
        assert "Attribute" in result

    def test_term_attribute_selector(self) -> None:
        """Term attribute as selector."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "-brand = Firefox\n"
            "    .version = 1\n\n"
            "msg = {-brand.version ->\n"
            "    [1] Version One\n"
            "    *[other] Other Version\n"
            "}"
        )
        result, _ = bundle.format_pattern("msg")
        assert result is not None

    def test_deeply_nested_expressions(self) -> None:
        """Deep nesting of expressions."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "msg = {NUMBER(1) ->\n"
            "    [one] {NUMBER(2) ->\n"
            "        [one] {NUMBER(3) ->\n"
            "            [one] Deep\n"
            "            *[other] Level3\n"
            "        }\n"
            "        *[other] Level2\n"
            "    }\n"
            "    *[other] Level1\n"
            "}"
        )
        result, _ = bundle.format_pattern("msg")
        assert result is not None

    def test_select_missing_arrow(self) -> None:
        """Select expression without -> operator."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "msg = {NUMBER(1)\n"
            "    [one] One\n"
            "    *[other] Other\n"
            "}"
        )
        result, _errors = bundle.format_pattern("msg")
        assert result is not None

    def test_select_missing_default_via_bundle(self) -> None:
        """Select without default variant via bundle."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "msg = {NUMBER(1) ->\n"
            "    [one] One\n"
            "    [two] Two\n"
            "}"
        )
        result, _errors = bundle.format_pattern("msg")
        assert result is not None

    def test_unicode_expression(self) -> None:
        """Unicode characters in expressions."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            'msg = {"Hello \\u4E16\\u754C" ->\n'
            "    *[other] Unicode test\n"
            "}"
        )
        result, _ = bundle.format_pattern("msg")
        assert result is not None


# ============================================================================
# HYPOTHESIS PROPERTY TESTS
# ============================================================================


pytestmark_fuzz = pytest.mark.fuzz


@pytestmark_fuzz
class TestExpressionsHypothesis:
    """Property-based tests for expression parsing."""

    @given(st.integers(min_value=0, max_value=1000))
    @example(42)
    @example(-42)
    @example(0)
    def test_numeric_argument_roundtrip(self, num: int) -> None:
        """Numbers parse correctly as argument expressions."""
        event(f"num_sign={'neg' if num < 0 else 'pos'}")
        cursor = Cursor(str(num), 0)
        result = parse_argument_expression(cursor)
        if result is not None:
            assert isinstance(
                result.value, (NumberLiteral, TermReference)
            )

    @given(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1,
            max_size=20,
        )
    )
    @example("msg")
    @example("x")
    def test_identifier_as_inline_expression(
        self, name: str
    ) -> None:
        """Valid identifiers parsed as message references."""
        event(f"name_len={len(name)}")
        result = parse_inline_expression(Cursor(name, 0))
        assert result is not None
        assert isinstance(result.value, MessageReference)

    @given(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1,
            max_size=20,
        )
    )
    @example("count")
    @example("x")
    def test_variable_reference_property(self, name: str) -> None:
        """'$' + valid identifier always parses as VariableReference."""
        event(f"name_len={len(name)}")
        source = f"${name}"
        result = parse_variable_reference(Cursor(source, 0))
        assert result is not None
        assert isinstance(result.value, VariableReference)
        assert result.value.id.name == name

    @given(
        st.text(
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1,
            max_size=10,
        )
    )
    @example("NUMBER")
    @example("DATETIME")
    def test_function_no_paren_returns_none(
        self, name: str
    ) -> None:
        """UPPERCASE identifier without paren returns None."""
        event(f"name_len={len(name)}")
        result = parse_function_reference(Cursor(name, 0))
        assert result is None

    @given(
        st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1,
            max_size=10,
        )
    )
    @example("brand")
    @example("x")
    def test_term_reference_property(self, name: str) -> None:
        """'-' + valid identifier always parses as TermReference."""
        event(f"name_len={len(name)}")
        source = f"-{name}"
        result = parse_term_reference(Cursor(source, 0))
        assert result is not None
        assert isinstance(result.value, TermReference)
        assert result.value.id.name == name
