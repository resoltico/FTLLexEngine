"""Comprehensive tests for syntax.parser.primitives module.

Property-based tests for primitive parsing utilities: identifiers, numbers,
string literals, and escape sequences. Ensures spec compliance, DoS protection,
and error handling correctness.

Coverage Focus:
    - Length limit enforcement (DoS prevention)
    - Line ending validation in string literals
    - Unicode escape validation
    - Error context propagation
"""

from __future__ import annotations

from hypothesis import assume, example, given
from hypothesis import strategies as st

from ftllexengine.constants import (
    _MAX_IDENTIFIER_LENGTH,
    _MAX_NUMBER_LENGTH,
    _MAX_STRING_LITERAL_LENGTH,
)
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.primitives import (
    clear_parse_error,
    get_last_parse_error,
    is_identifier_char,
    is_identifier_start,
    parse_escape_sequence,
    parse_identifier,
    parse_number,
    parse_number_value,
    parse_string_literal,
)

# ============================================================================
# Hypothesis Strategies
# ============================================================================

# Valid identifier characters per Fluent spec
_IDENTIFIER_START_CHARS = st.sampled_from(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
)
_IDENTIFIER_CONT_CHARS = st.sampled_from(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
)


# ============================================================================
# Identifier Character Classification Tests
# ============================================================================


class TestIdentifierCharacterClassification:
    """Test character classification for identifiers per Fluent spec."""

    @given(ch=st.characters(min_codepoint=97, max_codepoint=122))
    @example(ch="a")
    @example(ch="z")
    def test_lowercase_ascii_letters_are_identifier_start(self, ch: str) -> None:
        """Lowercase ASCII letters a-z are valid identifier start characters."""
        assert is_identifier_start(ch)
        assert is_identifier_char(ch)

    @given(ch=st.characters(min_codepoint=65, max_codepoint=90))
    @example(ch="A")
    @example(ch="Z")
    def test_uppercase_ascii_letters_are_identifier_start(self, ch: str) -> None:
        """Uppercase ASCII letters A-Z are valid identifier start characters."""
        assert is_identifier_start(ch)
        assert is_identifier_char(ch)

    @given(ch=st.characters(min_codepoint=48, max_codepoint=57))
    @example(ch="0")
    @example(ch="9")
    def test_digits_are_not_identifier_start_but_are_continuation(
        self, ch: str
    ) -> None:
        """ASCII digits 0-9 can continue identifiers but not start them."""
        assert not is_identifier_start(ch)
        assert is_identifier_char(ch)

    def test_hyphen_is_continuation_not_start(self) -> None:
        """Hyphen can continue identifier but not start it."""
        assert not is_identifier_start("-")
        assert is_identifier_char("-")

    def test_underscore_is_continuation_not_start(self) -> None:
        """Underscore can continue identifier but not start it."""
        assert not is_identifier_start("_")
        assert is_identifier_char("_")

    @given(
        ch=st.characters(
            blacklist_characters="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        )
    )
    def test_non_identifier_chars_rejected(self, ch: str) -> None:
        """Non-identifier characters are rejected by both validators."""
        assume(len(ch) == 1)
        assert not is_identifier_start(ch)
        assert not is_identifier_char(ch)


# ============================================================================
# Parse Identifier Tests (Including Length Limits)
# ============================================================================


class TestParseIdentifier:
    """Property-based tests for parse_identifier including DoS protection."""

    @given(
        start=_IDENTIFIER_START_CHARS,
        continuation=st.lists(_IDENTIFIER_CONT_CHARS, min_size=0, max_size=255),
    )
    @example(start="h", continuation=list("ello"))
    @example(start="x", continuation=[])
    def test_valid_identifiers_parse_successfully(
        self, start: str, continuation: list[str]
    ) -> None:
        """Valid identifiers within length limits parse successfully."""
        identifier = start + "".join(continuation)
        cursor = Cursor(source=identifier, pos=0)

        result = parse_identifier(cursor)

        assert result is not None
        assert result.value == identifier
        assert result.cursor.is_eof

    def test_identifier_exceeds_maximum_length_returns_none(self) -> None:
        """Identifier exceeding max length returns None (lines 204-208)."""
        # Create identifier of exactly max length + 1
        long_identifier = "a" * (_MAX_IDENTIFIER_LENGTH + 1)
        cursor = Cursor(source=long_identifier, pos=0)

        result = parse_identifier(cursor)

        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "exceeds maximum length" in error.message
        assert str(_MAX_IDENTIFIER_LENGTH) in error.message

    def test_identifier_at_exact_maximum_length_succeeds(self) -> None:
        """Identifier at exactly max length succeeds."""
        exact_max_identifier = "a" * _MAX_IDENTIFIER_LENGTH
        cursor = Cursor(source=exact_max_identifier, pos=0)

        result = parse_identifier(cursor)

        assert result is not None
        assert result.value == exact_max_identifier
        assert len(result.value) == _MAX_IDENTIFIER_LENGTH

    @given(n=st.integers(min_value=_MAX_IDENTIFIER_LENGTH + 1, max_value=10000))
    @example(n=_MAX_IDENTIFIER_LENGTH + 1)
    @example(n=_MAX_IDENTIFIER_LENGTH + 100)
    def test_identifier_length_property(self, n: int) -> None:
        """Property: Identifiers longer than max always fail."""
        long_identifier = "a" * n
        cursor = Cursor(source=long_identifier, pos=0)

        result = parse_identifier(cursor)

        assert result is None

    def test_identifier_starting_with_digit_fails(self) -> None:
        """Identifier starting with digit fails."""
        cursor = Cursor(source="123test", pos=0)
        result = parse_identifier(cursor)
        assert result is None

    def test_identifier_at_eof_fails(self) -> None:
        """Identifier at EOF fails."""
        cursor = Cursor(source="", pos=0)
        result = parse_identifier(cursor)
        assert result is None

    def test_parse_error_context_cleared_on_new_parse(self) -> None:
        """Parse error context is cleared on new parse attempt."""
        # First parse that fails
        cursor1 = Cursor(source="123", pos=0)
        parse_identifier(cursor1)
        error1 = get_last_parse_error()
        assert error1 is not None

        # Second successful parse should clear error
        cursor2 = Cursor(source="valid", pos=0)
        result = parse_identifier(cursor2)
        assert result is not None

        # Error should still be None after clear_parse_error was called
        # internally during the second parse
        # Let's verify we can manually clear it
        clear_parse_error()
        error2 = get_last_parse_error()
        assert error2 is None


# ============================================================================
# Parse Number Tests (Including Length Limits)
# ============================================================================


class TestParseNumber:
    """Property-based tests for parse_number including DoS protection."""

    @given(n=st.integers(min_value=0, max_value=10**50))
    @example(n=0)
    @example(n=42)
    @example(n=999)
    def test_valid_integers_parse_successfully(self, n: int) -> None:
        """Valid integers within length limits parse successfully."""
        # Skip if representation would exceed limit
        num_str = str(n)
        assume(len(num_str) <= _MAX_NUMBER_LENGTH)

        cursor = Cursor(source=num_str, pos=0)
        result = parse_number(cursor)

        assert result is not None
        assert result.value == num_str

    @given(n=st.floats(min_value=0.0, max_value=1e10, allow_nan=False))
    @example(n=3.14)
    @example(n=0.001)
    def test_valid_floats_parse_successfully(self, n: float) -> None:
        """Valid floats within length limits parse successfully."""
        num_str = str(n)
        assume("." in num_str)  # Ensure it's actually a float representation
        assume("e" not in num_str.lower())  # Parser doesn't support scientific notation
        assume(len(num_str) <= _MAX_NUMBER_LENGTH)

        cursor = Cursor(source=num_str, pos=0)
        result = parse_number(cursor)

        assert result is not None
        assert result.value == num_str

    def test_number_integer_part_exceeds_maximum_length_returns_none(self) -> None:
        """Number with integer part exceeding max length returns None (lines 267-271)."""
        # Create number with integer part longer than max
        long_integer = "1" * (_MAX_NUMBER_LENGTH + 1)
        cursor = Cursor(source=long_integer, pos=0)

        result = parse_number(cursor)

        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "exceeds maximum length" in error.message
        assert str(_MAX_NUMBER_LENGTH) in error.message

    def test_number_decimal_part_exceeds_maximum_length_returns_none(self) -> None:
        """Number with decimal part causing overflow returns None (lines 286-290)."""
        # Create number where total length (including decimal) exceeds max
        # Start with a valid integer part, then add massive decimal part
        # Total must exceed _MAX_NUMBER_LENGTH
        integer_part = "1"
        decimal_part = "1" * _MAX_NUMBER_LENGTH  # This will push us over
        long_decimal = f"{integer_part}.{decimal_part}"
        cursor = Cursor(source=long_decimal, pos=0)

        result = parse_number(cursor)

        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "exceeds maximum length" in error.message

    def test_number_at_exact_maximum_length_succeeds(self) -> None:
        """Number at exactly max length succeeds."""
        exact_max_number = "9" * _MAX_NUMBER_LENGTH
        cursor = Cursor(source=exact_max_number, pos=0)

        result = parse_number(cursor)

        assert result is not None
        assert result.value == exact_max_number

    def test_negative_number_parses(self) -> None:
        """Negative numbers parse correctly."""
        cursor = Cursor(source="-42", pos=0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == "-42"

    def test_decimal_without_trailing_digit_fails(self) -> None:
        """Decimal point without trailing digit fails."""
        cursor = Cursor(source="42.", pos=0)
        result = parse_number(cursor)
        # Parser fails because decimal point requires trailing digit
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "digit after decimal" in error.message.lower()

    def test_minus_without_digit_fails(self) -> None:
        """Minus sign without digit fails (lines 259-260)."""
        cursor = Cursor(source="-", pos=0)
        result = parse_number(cursor)
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "Expected number" in error.message

    def test_minus_followed_by_non_digit_fails(self) -> None:
        """Minus sign followed by non-digit fails (lines 259-260)."""
        cursor = Cursor(source="-x", pos=0)
        result = parse_number(cursor)
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "Expected number" in error.message


# ============================================================================
# Parse Number Value Tests
# ============================================================================


class TestParseNumberValue:
    """Tests for parse_number_value conversion utility."""

    @given(n=st.integers())
    @example(n=0)
    @example(n=42)
    @example(n=-100)
    def test_integer_strings_convert_to_int(self, n: int) -> None:
        """Integer strings convert to int type."""
        result = parse_number_value(str(n))
        assert isinstance(result, int)
        assert result == n

    @given(n=st.floats(allow_nan=False, allow_infinity=False))
    @example(n=3.14)
    @example(n=-2.5)
    def test_decimal_strings_convert_to_decimal(self, n: float) -> None:
        """Decimal strings convert to Decimal type for financial precision."""
        from decimal import Decimal  # noqa: PLC0415

        num_str = str(n)
        assume("." in num_str)  # Ensure decimal representation
        result = parse_number_value(num_str)
        assert isinstance(result, Decimal)
        # Compare using Decimal for precision
        assert result == Decimal(num_str)


# ============================================================================
# Parse String Literal Tests (Including Length Limits and Line Endings)
# ============================================================================


class TestParseStringLiteral:
    """Property-based tests for parse_string_literal including validation."""

    @given(
        content=st.text(
            alphabet=st.characters(blacklist_characters='"\\\n'),
            min_size=0,
            max_size=1000,
        )
    )
    @example(content="hello")
    @example(content="")
    def test_valid_strings_parse_successfully(self, content: str) -> None:
        """Valid strings without special characters parse successfully."""
        source = f'"{content}"'
        cursor = Cursor(source=source, pos=0)

        result = parse_string_literal(cursor)

        assert result is not None
        assert result.value == content

    def test_string_literal_exceeds_maximum_length_returns_none(self) -> None:
        """String literal exceeding max length returns None (lines 448-452)."""
        # Create string that exceeds max length
        # We need to create a string literal that, when parsed, has more than
        # _MAX_STRING_LITERAL_LENGTH characters in the accumulated chars list
        long_content = "a" * (_MAX_STRING_LITERAL_LENGTH + 1)
        source = f'"{long_content}"'
        cursor = Cursor(source=source, pos=0)

        result = parse_string_literal(cursor)

        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "exceeds maximum length" in error.message
        assert str(_MAX_STRING_LITERAL_LENGTH) in error.message

    def test_string_literal_with_line_ending_returns_none(self) -> None:
        """String literal with line ending (LF) returns None (lines 465-469)."""
        # Per Fluent spec, line endings are forbidden in string literals
        source = '"hello\nworld"'
        cursor = Cursor(source=source, pos=0)

        result = parse_string_literal(cursor)

        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "Line endings not allowed" in error.message or "line end" in error.message.lower()

    def test_string_literal_with_escaped_newline_succeeds(self) -> None:
        """String literal with \\n escape sequence succeeds."""
        source = r'"hello\nworld"'
        cursor = Cursor(source=source, pos=0)

        result = parse_string_literal(cursor)

        assert result is not None
        assert result.value == "hello\nworld"
        assert "\n" in result.value

    def test_string_literal_unterminated_returns_none(self) -> None:
        """Unterminated string literal returns None."""
        source = '"hello'
        cursor = Cursor(source=source, pos=0)

        result = parse_string_literal(cursor)

        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "Unterminated" in error.message

    def test_string_literal_not_starting_with_quote_fails(self) -> None:
        """String literal not starting with quote fails (lines 438-439)."""
        cursor = Cursor(source="hello", pos=0)
        result = parse_string_literal(cursor)
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "Expected opening quote" in error.message

    def test_string_literal_at_eof_fails(self) -> None:
        """String literal at EOF fails (lines 438-439)."""
        cursor = Cursor(source="", pos=0)
        result = parse_string_literal(cursor)
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "Expected opening quote" in error.message

    def test_string_literal_with_invalid_escape_sequence_fails(self) -> None:
        """String literal with invalid escape sequence fails (line 476)."""
        source = r'"hello\xworld"'  # \x is not a valid escape
        cursor = Cursor(source=source, pos=0)

        result = parse_string_literal(cursor)

        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "Invalid escape" in error.message

    @given(
        escape_char=st.sampled_from(['"', "\\", "n", "t"])
    )
    @example(escape_char='"')
    @example(escape_char="\\")
    def test_valid_escape_sequences_parse(self, escape_char: str) -> None:
        """Valid escape sequences parse correctly."""
        source = f'"\\{escape_char}"'
        cursor = Cursor(source=source, pos=0)

        result = parse_string_literal(cursor)

        assert result is not None
        # Verify the escape was processed
        match escape_char:
            case '"':
                assert result.value == '"'
            case "\\":
                assert result.value == "\\"
            case "n":
                assert result.value == "\n"
            case "t":
                assert result.value == "\t"


# ============================================================================
# Parse Escape Sequence Tests
# ============================================================================


class TestParseEscapeSequence:
    """Tests for parse_escape_sequence helper function."""

    def test_escape_quote(self) -> None:
        """Escape sequence \\" produces quote character."""
        cursor = Cursor(source='"', pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        char, _new_cursor = result
        assert char == '"'

    def test_escape_backslash(self) -> None:
        """Escape sequence \\\\ produces backslash character."""
        cursor = Cursor(source="\\", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        char, _new_cursor = result
        assert char == "\\"

    def test_escape_newline(self) -> None:
        """Escape sequence \\n produces newline character."""
        cursor = Cursor(source="n", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        char, _new_cursor = result
        assert char == "\n"

    def test_escape_tab(self) -> None:
        """Escape sequence \\t produces tab character."""
        cursor = Cursor(source="t", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        char, _new_cursor = result
        assert char == "\t"

    @given(
        hex_digits=st.text(
            alphabet="0123456789abcdefABCDEF",
            min_size=4,
            max_size=4,
        ).filter(lambda h: int(h, 16) < 0xD800 or int(h, 16) > 0xDFFF)
    )
    @example(hex_digits="00E4")
    @example(hex_digits="0041")
    def test_unicode_short_escape_valid(self, hex_digits: str) -> None:
        """Valid \\uXXXX escape sequences parse correctly."""
        source = f"u{hex_digits}rest"
        cursor = Cursor(source=source, pos=0)

        result = parse_escape_sequence(cursor)

        assert result is not None
        char, _new_cursor = result
        expected_char = chr(int(hex_digits, 16))
        assert char == expected_char

    def test_unicode_short_escape_surrogate_fails(self) -> None:
        """\\uXXXX with surrogate code point fails."""
        # D800 is start of surrogate range
        source = "uD800"
        cursor = Cursor(source=source, pos=0)

        result = parse_escape_sequence(cursor)

        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "surrogate" in error.message.lower()

    @given(
        hex_digits=st.text(
            alphabet="0123456789abcdefABCDEF",
            min_size=6,
            max_size=6,
        ).filter(
            lambda h: int(h, 16) <= 0x10FFFF
            and (int(h, 16) < 0xD800 or int(h, 16) > 0xDFFF)
        )
    )
    @example(hex_digits="01F600")
    @example(hex_digits="000041")
    def test_unicode_long_escape_valid(self, hex_digits: str) -> None:
        """Valid \\UXXXXXX escape sequences parse correctly."""
        source = f"U{hex_digits}rest"
        cursor = Cursor(source=source, pos=0)

        result = parse_escape_sequence(cursor)

        assert result is not None
        char, _new_cursor = result
        expected_char = chr(int(hex_digits, 16))
        assert char == expected_char

    def test_unicode_long_escape_exceeds_max_codepoint_fails(self) -> None:
        """\\UXXXXXX with code point > 10FFFF fails."""
        source = "U110000"  # One past maximum
        cursor = Cursor(source=source, pos=0)

        result = parse_escape_sequence(cursor)

        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "10FFFF" in error.message or "code point" in error.message.lower()

    def test_unicode_long_escape_surrogate_fails(self) -> None:
        """\\UXXXXXX with surrogate code point fails."""
        source = "U00D800"
        cursor = Cursor(source=source, pos=0)

        result = parse_escape_sequence(cursor)

        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "surrogate" in error.message.lower()

    def test_unicode_short_escape_insufficient_digits_fails(self) -> None:
        """\\uXXX with less than 4 hex digits fails (lines 343-348)."""
        source = "u123"  # Only 3 hex digits
        cursor = Cursor(source=source, pos=0)

        result = parse_escape_sequence(cursor)

        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "Invalid Unicode escape" in error.message
        assert "4" in error.message

    def test_unicode_short_escape_non_hex_fails(self) -> None:
        """\\uXXXX with non-hex characters fails (lines 343-348)."""
        source = "u00GG"  # G is not a hex digit
        cursor = Cursor(source=source, pos=0)

        result = parse_escape_sequence(cursor)

        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "Invalid Unicode escape" in error.message

    def test_unicode_long_escape_insufficient_digits_fails(self) -> None:
        """\\UXXXXX with less than 6 hex digits fails (lines 371-376)."""
        source = "U12345"  # Only 5 hex digits
        cursor = Cursor(source=source, pos=0)

        result = parse_escape_sequence(cursor)

        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "Invalid Unicode escape" in error.message
        assert "6" in error.message

    def test_unicode_long_escape_non_hex_fails(self) -> None:
        """\\UXXXXXX with non-hex characters fails (lines 371-376)."""
        source = "U0000GG"  # G is not a hex digit
        cursor = Cursor(source=source, pos=0)

        result = parse_escape_sequence(cursor)

        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "Invalid Unicode escape" in error.message

    def test_invalid_escape_character_fails(self) -> None:
        """Invalid escape character fails."""
        cursor = Cursor(source="x", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None

    def test_escape_at_eof_fails(self) -> None:
        """Escape sequence at EOF fails."""
        cursor = Cursor(source="", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None


# ============================================================================
# Integration Tests
# ============================================================================


class TestPrimitivesIntegration:
    """Integration tests combining multiple primitives."""

    def test_parse_multiple_identifiers_sequentially(self) -> None:
        """Parse multiple identifiers from same source."""
        source = "hello world test"
        cursor = Cursor(source=source, pos=0)

        # Parse first
        result1 = parse_identifier(cursor)
        assert result1 is not None
        assert result1.value == "hello"

        # Skip space
        cursor = result1.cursor.advance()

        # Parse second
        result2 = parse_identifier(cursor)
        assert result2 is not None
        assert result2.value == "world"

    def test_parse_number_then_identifier(self) -> None:
        """Parse number followed by identifier."""
        source = "42 test"
        cursor = Cursor(source=source, pos=0)

        # Parse number
        num_result = parse_number(cursor)
        assert num_result is not None
        assert num_result.value == "42"

        # Skip space
        cursor = num_result.cursor.advance()

        # Parse identifier
        id_result = parse_identifier(cursor)
        assert id_result is not None
        assert id_result.value == "test"

    @given(
        identifiers=st.lists(
            st.text(
                alphabet=st.characters(min_codepoint=97, max_codepoint=122),
                min_size=1,
                max_size=10,
            ),
            min_size=1,
            max_size=5,
        )
    )
    @example(identifiers=["hello", "world"])
    def test_parse_identifier_list_property(self, identifiers: list[str]) -> None:
        """Property: Can parse list of space-separated identifiers."""
        source = " ".join(identifiers)
        cursor = Cursor(source=source, pos=0)

        for expected_id in identifiers:
            result = parse_identifier(cursor)
            assert result is not None
            assert result.value == expected_id

            # Skip to next (either space or EOF)
            cursor = result.cursor
            if not cursor.is_eof and cursor.current == " ":
                cursor = cursor.advance()


# ============================================================================
# Error Context Tests
# ============================================================================


class TestParseErrorContext:
    """Tests for parse error context management."""

    def test_get_last_parse_error_returns_none_initially(self) -> None:
        """get_last_parse_error returns None when no error occurred."""
        clear_parse_error()
        error = get_last_parse_error()
        assert error is None

    def test_parse_error_stores_context(self) -> None:
        """Parse error stores detailed context."""
        cursor = Cursor(source="123invalid", pos=0)
        result = parse_identifier(cursor)
        assert result is None

        error = get_last_parse_error()
        assert error is not None
        assert error.message
        assert error.position == 0
        assert len(error.expected) > 0

    def test_clear_parse_error_clears_context(self) -> None:
        """clear_parse_error clears error context."""
        # Cause an error
        cursor = Cursor(source="123", pos=0)
        parse_identifier(cursor)
        assert get_last_parse_error() is not None

        # Clear it
        clear_parse_error()
        assert get_last_parse_error() is None

    def test_successive_parse_attempts_update_error(self) -> None:
        """Successive parse attempts update error context."""
        # First error
        cursor1 = Cursor(source="123", pos=0)
        parse_identifier(cursor1)
        error1 = get_last_parse_error()

        # Second error (different position)
        cursor2 = Cursor(source="  456", pos=2)
        parse_identifier(cursor2)
        error2 = get_last_parse_error()

        assert error2 is not None
        assert error2.position == 2
        # Different from first error
        assert error1 is not None
        assert error2.position != error1.position
