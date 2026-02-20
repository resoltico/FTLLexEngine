"""Tests for syntax.parser.primitives module.

Property-based tests for primitive parsing utilities: identifiers, numbers,
string literals, and escape sequences. Ensures spec compliance, DoS protection,
error context propagation, and Unicode validation.

All ``@given`` tests emit ``event()`` calls for HypoFuzz guidance.
"""

from __future__ import annotations

from hypothesis import assume, event, example, given
from hypothesis import strategies as st

from ftllexengine.constants import MAX_IDENTIFIER_LENGTH as _MAX_IDENTIFIER_LENGTH
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.primitives import (
    _MAX_NUMBER_LENGTH,
    _MAX_STRING_LITERAL_LENGTH,
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

_IDENTIFIER_START_CHARS = st.sampled_from(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
)
_IDENTIFIER_CONT_CHARS = st.sampled_from(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
)


# ============================================================================
# TestIdentifierCharacterClassification
# ============================================================================


class TestIdentifierCharacterClassification:
    """Character classification for identifiers per Fluent spec."""

    @given(ch=st.characters(min_codepoint=97, max_codepoint=122))
    @example(ch="a")
    @example(ch="z")
    def test_lowercase_ascii_are_identifier_start(
        self, ch: str,
    ) -> None:
        """Lowercase ASCII letters a-z are valid identifier start."""
        event(f"char={ch}")
        assert is_identifier_start(ch)
        assert is_identifier_char(ch)

    @given(ch=st.characters(min_codepoint=65, max_codepoint=90))
    @example(ch="A")
    @example(ch="Z")
    def test_uppercase_ascii_are_identifier_start(
        self, ch: str,
    ) -> None:
        """Uppercase ASCII letters A-Z are valid identifier start."""
        event(f"char={ch}")
        assert is_identifier_start(ch)
        assert is_identifier_char(ch)

    @given(ch=st.characters(min_codepoint=48, max_codepoint=57))
    @example(ch="0")
    @example(ch="9")
    def test_digits_continue_but_not_start(self, ch: str) -> None:
        """ASCII digits 0-9 can continue identifiers but not start."""
        event(f"char={ch}")
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
            blacklist_characters=(
                "abcdefghijklmnopqrstuvwxyz"
                "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                "0123456789-_"
            )
        )
    )
    def test_non_identifier_chars_rejected(self, ch: str) -> None:
        """Non-identifier characters rejected by both validators."""
        assume(len(ch) == 1)
        event(f"outcome=rejected_ord_{ord(ch) % 256}")
        assert not is_identifier_start(ch)
        assert not is_identifier_char(ch)


# ============================================================================
# TestParseIdentifier
# ============================================================================


class TestParseIdentifier:
    """Property-based tests for parse_identifier including DoS limits."""

    @given(
        start=_IDENTIFIER_START_CHARS,
        cont=st.lists(
            _IDENTIFIER_CONT_CHARS, min_size=0, max_size=255,
        ),
    )
    @example(start="h", cont=list("ello"))
    @example(start="x", cont=[])
    def test_valid_identifiers_parse(
        self, start: str, cont: list[str],
    ) -> None:
        """Valid identifiers within length limits parse successfully."""
        identifier = start + "".join(cont)
        event(f"boundary=id_len_{min(len(identifier), 20)}")
        cursor = Cursor(source=identifier, pos=0)
        result = parse_identifier(cursor)
        assert result is not None
        assert result.value == identifier
        assert result.cursor.is_eof

    def test_with_hyphens(self) -> None:
        """Identifier with hyphens parses."""
        cursor = Cursor(source="brand-name", pos=0)
        result = parse_identifier(cursor)
        assert result is not None
        assert result.value == "brand-name"

    def test_with_underscores(self) -> None:
        """Identifier with underscores parses."""
        cursor = Cursor(source="file_name", pos=0)
        result = parse_identifier(cursor)
        assert result is not None
        assert result.value == "file_name"

    def test_with_digits(self) -> None:
        """Identifier with digits parses."""
        cursor = Cursor(source="test123", pos=0)
        result = parse_identifier(cursor)
        assert result is not None
        assert result.value == "test123"

    def test_single_letter(self) -> None:
        """Single letter identifier parses."""
        cursor = Cursor(source="x", pos=0)
        result = parse_identifier(cursor)
        assert result is not None
        assert result.value == "x"

    def test_stops_at_space(self) -> None:
        """Identifier stops at space character."""
        cursor = Cursor(source="hello world", pos=0)
        result = parse_identifier(cursor)
        assert result is not None
        assert result.value == "hello"
        assert result.cursor.pos == 5

    def test_exceeds_max_length_returns_none(self) -> None:
        """Identifier exceeding max length returns None."""
        long_id = "a" * (_MAX_IDENTIFIER_LENGTH + 1)
        cursor = Cursor(source=long_id, pos=0)
        result = parse_identifier(cursor)
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "exceeds maximum length" in error.message

    def test_at_exact_max_length_succeeds(self) -> None:
        """Identifier at exactly max length succeeds."""
        exact = "a" * _MAX_IDENTIFIER_LENGTH
        cursor = Cursor(source=exact, pos=0)
        result = parse_identifier(cursor)
        assert result is not None
        assert len(result.value) == _MAX_IDENTIFIER_LENGTH

    @given(
        n=st.integers(
            min_value=_MAX_IDENTIFIER_LENGTH + 1,
            max_value=10000,
        )
    )
    @example(n=_MAX_IDENTIFIER_LENGTH + 1)
    def test_over_max_length_always_fails(self, n: int) -> None:
        """Identifiers longer than max always fail."""
        event(f"boundary=over_max_{min(n - _MAX_IDENTIFIER_LENGTH, 50)}")
        cursor = Cursor(source="a" * n, pos=0)
        assert parse_identifier(cursor) is None

    def test_starting_with_digit_fails(self) -> None:
        """Identifier starting with digit fails."""
        cursor = Cursor(source="123test", pos=0)
        assert parse_identifier(cursor) is None

    def test_starting_with_hyphen_fails(self) -> None:
        """Identifier starting with hyphen fails."""
        cursor = Cursor(source="-test", pos=0)
        assert parse_identifier(cursor) is None

    def test_starting_with_underscore_fails(self) -> None:
        """Identifier starting with underscore fails (alpha required)."""
        cursor = Cursor(source="_test", pos=0)
        assert parse_identifier(cursor) is None

    def test_at_eof_fails(self) -> None:
        """Identifier at EOF fails."""
        cursor = Cursor(source="", pos=0)
        assert parse_identifier(cursor) is None

    @given(
        st.characters().filter(lambda c: not c.isalpha())
    )
    def test_non_alpha_start_always_fails(self, char: str) -> None:
        """Identifiers must start with alphabetic character."""
        event(f"outcome=rejected_start_ord_{ord(char) % 256}")
        cursor = Cursor(source=f"{char}test", pos=0)
        assert parse_identifier(cursor) is None


# ============================================================================
# TestParseNumber
# ============================================================================


class TestParseNumber:
    """Property-based tests for parse_number including DoS limits."""

    @given(n=st.integers(min_value=0, max_value=10**50))
    @example(n=0)
    @example(n=42)
    def test_valid_integers_parse(self, n: int) -> None:
        """Valid integers within length limits parse successfully."""
        num_str = str(n)
        assume(len(num_str) <= _MAX_NUMBER_LENGTH)
        event(f"boundary=int_len_{min(len(num_str), 20)}")
        cursor = Cursor(source=num_str, pos=0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == num_str

    @given(
        n=st.floats(
            min_value=0.0, max_value=1e10, allow_nan=False,
        )
    )
    @example(n=3.14)
    @example(n=0.001)
    def test_valid_floats_parse(self, n: float) -> None:
        """Valid floats within length limits parse successfully."""
        num_str = str(n)
        assume("." in num_str)
        assume("e" not in num_str.lower())
        assume(len(num_str) <= _MAX_NUMBER_LENGTH)
        event(f"boundary=float_len_{min(len(num_str), 20)}")
        cursor = Cursor(source=num_str, pos=0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == num_str

    def test_negative_number(self) -> None:
        """Negative numbers parse correctly."""
        cursor = Cursor(source="-42", pos=0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == "-42"

    def test_negative_float(self) -> None:
        """Negative floats parse correctly."""
        cursor = Cursor(source="-2.5", pos=0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == "-2.5"

    def test_zero(self) -> None:
        """Zero parses correctly."""
        cursor = Cursor(source="0", pos=0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == "0"

    def test_float_with_leading_zero(self) -> None:
        """Float with leading zero parses correctly."""
        cursor = Cursor(source="0.001", pos=0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == "0.001"

    def test_stops_at_non_digit(self) -> None:
        """Number parsing stops at non-digit character."""
        cursor = Cursor(source="123abc", pos=0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == "123"
        assert result.cursor.pos == 3

    def test_integer_exceeds_max_length(self) -> None:
        """Number with integer part exceeding max length fails."""
        long_int = "1" * (_MAX_NUMBER_LENGTH + 1)
        cursor = Cursor(source=long_int, pos=0)
        result = parse_number(cursor)
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "exceeds maximum length" in error.message

    def test_decimal_exceeds_max_length(self) -> None:
        """Number with decimal part causing overflow fails."""
        decimal_part = "1" * _MAX_NUMBER_LENGTH
        long_decimal = f"1.{decimal_part}"
        cursor = Cursor(source=long_decimal, pos=0)
        result = parse_number(cursor)
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "exceeds maximum length" in error.message

    def test_at_exact_max_length_succeeds(self) -> None:
        """Number at exactly max length succeeds."""
        exact = "9" * _MAX_NUMBER_LENGTH
        cursor = Cursor(source=exact, pos=0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == exact

    def test_decimal_without_trailing_digit_fails(self) -> None:
        """Decimal point without trailing digit fails."""
        cursor = Cursor(source="42.", pos=0)
        assert parse_number(cursor) is None
        error = get_last_parse_error()
        assert error is not None
        assert "digit after decimal" in error.message.lower()

    def test_decimal_followed_by_non_digit_fails(self) -> None:
        """Decimal point followed by non-digit fails."""
        cursor = Cursor(source="123.abc", pos=0)
        assert parse_number(cursor) is None

    def test_minus_without_digit_fails(self) -> None:
        """Minus sign without digit fails."""
        cursor = Cursor(source="-", pos=0)
        assert parse_number(cursor) is None
        error = get_last_parse_error()
        assert error is not None
        assert "Expected number" in error.message

    def test_minus_followed_by_non_digit_fails(self) -> None:
        """Minus sign followed by non-digit fails."""
        cursor = Cursor(source="-x", pos=0)
        assert parse_number(cursor) is None

    def test_at_eof_fails(self) -> None:
        """Number at EOF fails."""
        cursor = Cursor(source="", pos=0)
        assert parse_number(cursor) is None

    def test_rejects_unicode_superscript_digits(self) -> None:
        """Unicode superscript digits rejected (FTL requires ASCII 0-9).

        str.isdigit() returns True for Unicode digits like U+00B2,
        but FTL spec only allows ASCII digits 0-9.
        """
        for char in ("\u00b2", "\u00b3", "\u0660"):
            cursor = Cursor(source=char, pos=0)
            result = parse_number(cursor)
            assert result is None, (
                f"Unicode digit U+{ord(char):04X} should be rejected"
            )

    @given(
        st.text(min_size=1, max_size=10).filter(
            lambda s: not s[0].isdigit() and s[0] != "-"
        )
    )
    def test_non_numeric_start_always_fails(
        self, text: str,
    ) -> None:
        """Non-numeric start always fails."""
        event(f"outcome=rejected_start_ord_{ord(text[0]) % 256}")
        cursor = Cursor(source=text, pos=0)
        assert parse_number(cursor) is None


# ============================================================================
# TestParseNumberValue
# ============================================================================


class TestParseNumberValue:
    """Tests for parse_number_value conversion utility."""

    @given(n=st.integers())
    @example(n=0)
    @example(n=42)
    @example(n=-100)
    def test_integer_strings_convert_to_int(self, n: int) -> None:
        """Integer strings convert to int type."""
        event(f"boundary=int_abs_{min(abs(n), 1000)}")
        result = parse_number_value(str(n))
        assert isinstance(result, int)
        assert result == n

    @given(n=st.floats(allow_nan=False, allow_infinity=False))
    @example(n=3.14)
    @example(n=-2.5)
    def test_decimal_strings_convert_to_decimal(
        self, n: float,
    ) -> None:
        """Decimal strings convert to Decimal for financial precision."""
        from decimal import Decimal  # noqa: PLC0415

        num_str = str(n)
        assume("." in num_str)
        event(f"boundary=decimal_len_{min(len(num_str), 20)}")
        result = parse_number_value(num_str)
        assert isinstance(result, Decimal)
        assert result == Decimal(num_str)


# ============================================================================
# TestParseStringLiteral
# ============================================================================


class TestParseStringLiteral:
    """Property-based tests for parse_string_literal."""

    @given(
        content=st.text(
            alphabet=st.characters(blacklist_characters='"\\\n'),
            min_size=0,
            max_size=1000,
        )
    )
    @example(content="hello")
    @example(content="")
    def test_valid_strings_parse(self, content: str) -> None:
        """Valid strings without special characters parse."""
        event(f"boundary=str_len_{min(len(content), 50)}")
        source = f'"{content}"'
        cursor = Cursor(source=source, pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == content

    def test_empty_string(self) -> None:
        """Empty string literal parses."""
        cursor = Cursor(source='""', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == ""

    def test_with_escaped_quote(self) -> None:
        """String with escaped quotes parses."""
        cursor = Cursor(source=r'"with \"quotes\""', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == 'with "quotes"'

    def test_with_escaped_backslash(self) -> None:
        """String with escaped backslash parses."""
        cursor = Cursor(source=r'"path\\to\\file"', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == "path\\to\\file"

    def test_with_newline_escape(self) -> None:
        """String with \\n escape parses."""
        cursor = Cursor(source=r'"line1\nline2"', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == "line1\nline2"

    def test_with_tab_escape(self) -> None:
        """String with \\t escape parses."""
        cursor = Cursor(source=r'"col1\tcol2"', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == "col1\tcol2"

    def test_with_unicode_escape(self) -> None:
        """String with \\uXXXX escape parses."""
        cursor = Cursor(source=r'"unicode: \u00E4"', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == "unicode: \u00e4"

    def test_multiple_escapes(self) -> None:
        """String with multiple escape sequences parses."""
        cursor = Cursor(source=r'"a\"b\\c\nd"', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == 'a"b\\c\nd'

    def test_stops_at_closing_quote(self) -> None:
        """String stops at closing quote."""
        cursor = Cursor(source='"hello" world', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == "hello"
        assert result.cursor.pos == 7

    def test_exceeds_max_length(self) -> None:
        """String exceeding max length returns None."""
        long_content = "a" * (_MAX_STRING_LITERAL_LENGTH + 1)
        source = f'"{long_content}"'
        cursor = Cursor(source=source, pos=0)
        result = parse_string_literal(cursor)
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "exceeds maximum length" in error.message

    def test_line_ending_forbidden(self) -> None:
        """String with line ending (LF) returns None per spec."""
        source = '"hello\nworld"'
        cursor = Cursor(source=source, pos=0)
        result = parse_string_literal(cursor)
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "Line endings not allowed" in error.message

    def test_unterminated_returns_none(self) -> None:
        """Unterminated string literal returns None."""
        cursor = Cursor(source='"hello', pos=0)
        result = parse_string_literal(cursor)
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "Unterminated" in error.message

    def test_no_opening_quote_fails(self) -> None:
        """String not starting with quote fails."""
        cursor = Cursor(source="hello", pos=0)
        assert parse_string_literal(cursor) is None
        error = get_last_parse_error()
        assert error is not None
        assert "Expected opening quote" in error.message

    def test_at_eof_fails(self) -> None:
        """String at EOF fails."""
        cursor = Cursor(source="", pos=0)
        assert parse_string_literal(cursor) is None

    def test_invalid_escape_fails(self) -> None:
        """String with invalid escape sequence fails."""
        source = r'"hello\xworld"'
        cursor = Cursor(source=source, pos=0)
        assert parse_string_literal(cursor) is None

    @given(escape_char=st.sampled_from(['"', "\\", "n", "t"]))
    @example(escape_char='"')
    @example(escape_char="\\")
    def test_valid_escape_sequences(
        self, escape_char: str,
    ) -> None:
        """Valid escape sequences parse correctly."""
        event(f"strategy=escape_{escape_char}")
        source = f'"\\{escape_char}"'
        cursor = Cursor(source=source, pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        expected = {'"': '"', "\\": "\\", "n": "\n", "t": "\t"}
        assert result.value == expected[escape_char]


# ============================================================================
# TestParseEscapeSequenceBasic
# ============================================================================


class TestParseEscapeSequenceBasic:
    """Basic escape sequence tests: simple escapes and invalid cases."""

    def test_escape_quote(self) -> None:
        """Escape \\\" produces quote character."""
        cursor = Cursor(source='"', pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        assert result[0] == '"'

    def test_escape_backslash(self) -> None:
        """Escape \\\\ produces backslash character."""
        cursor = Cursor(source="\\", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        assert result[0] == "\\"

    def test_escape_newline(self) -> None:
        """Escape \\n produces newline character."""
        cursor = Cursor(source="n", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        assert result[0] == "\n"

    def test_escape_tab(self) -> None:
        """Escape \\t produces tab character."""
        cursor = Cursor(source="t", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        assert result[0] == "\t"

    def test_invalid_escape_char_fails(self) -> None:
        """Invalid escape character like \\x fails."""
        cursor = Cursor(source="x", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "Invalid escape" in error.message

    def test_at_eof_fails(self) -> None:
        """Escape at EOF fails."""
        cursor = Cursor(source="", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "EOF" in error.message

    @given(
        st.characters().filter(
            lambda c: c not in {'"', "\\", "n", "t", "u", "U"}
        )
    )
    def test_only_valid_escapes_accepted(self, char: str) -> None:
        """Only valid escape characters are accepted."""
        event(f"outcome=rejected_escape_ord_{ord(char) % 256}")
        cursor = Cursor(source=char, pos=0)
        assert parse_escape_sequence(cursor) is None


# ============================================================================
# TestParseEscapeSequenceUnicode
# ============================================================================


class TestParseEscapeSequenceUnicode:
    """Unicode escape sequence tests: \\uXXXX and \\UXXXXXX."""

    # -- \\uXXXX (4-digit BMP) -------------------------------------------

    @given(
        hex_digits=st.text(
            alphabet="0123456789abcdefABCDEF",
            min_size=4,
            max_size=4,
        ).filter(
            lambda h: int(h, 16) < 0xD800 or int(h, 16) > 0xDFFF
        )
    )
    @example(hex_digits="00E4")
    @example(hex_digits="0041")
    def test_4digit_valid(self, hex_digits: str) -> None:
        """Valid \\uXXXX escape sequences parse correctly."""
        code_point = int(hex_digits, 16)
        event(f"boundary=bmp_codepoint_{min(code_point, 0xFFFF)}")
        source = f"u{hex_digits}rest"
        cursor = Cursor(source=source, pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        assert result[0] == chr(code_point)

    def test_4digit_surrogate_d800_fails(self) -> None:
        """\\uD800 (low surrogate boundary) rejected."""
        cursor = Cursor(source="uD800", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "surrogate" in error.message.lower()

    def test_4digit_surrogate_dfff_fails(self) -> None:
        """\\uDFFF (high surrogate boundary) rejected."""
        cursor = Cursor(source="uDFFF", pos=0)
        assert parse_escape_sequence(cursor) is None

    def test_4digit_surrogate_dc00_fails(self) -> None:
        """\\uDC00 (mid surrogate range) rejected."""
        cursor = Cursor(source="uDC00", pos=0)
        assert parse_escape_sequence(cursor) is None

    def test_4digit_insufficient_digits_fails(self) -> None:
        """\\uXXX with fewer than 4 hex digits fails."""
        cursor = Cursor(source="u123", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "4" in error.message

    def test_4digit_non_hex_fails(self) -> None:
        """\\uXXXX with non-hex characters fails."""
        cursor = Cursor(source="u00GG", pos=0)
        assert parse_escape_sequence(cursor) is None

    # -- \\UXXXXXX (6-digit full range) -----------------------------------

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
    def test_6digit_valid(self, hex_digits: str) -> None:
        """Valid \\UXXXXXX escape sequences parse correctly."""
        code_point = int(hex_digits, 16)
        event(f"boundary=full_codepoint_{min(code_point, 0x10FFFF)}")
        source = f"U{hex_digits}rest"
        cursor = Cursor(source=source, pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        assert result[0] == chr(code_point)

    def test_6digit_exceeds_max_codepoint_fails(self) -> None:
        """\\UXXXXXX with code point > 10FFFF fails."""
        cursor = Cursor(source="U110000", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "10FFFF" in error.message

    def test_6digit_surrogate_d800_fails(self) -> None:
        """\\U00D800 (low surrogate) rejected."""
        cursor = Cursor(source="U00D800", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "surrogate" in error.message.lower()

    def test_6digit_surrogate_dfff_fails(self) -> None:
        """\\U00DFFF (high surrogate) rejected."""
        cursor = Cursor(source="U00DFFF", pos=0)
        assert parse_escape_sequence(cursor) is None

    def test_6digit_surrogate_dc00_fails(self) -> None:
        """\\U00DC00 (mid surrogate range) rejected."""
        cursor = Cursor(source="U00DC00", pos=0)
        assert parse_escape_sequence(cursor) is None

    def test_6digit_insufficient_digits_fails(self) -> None:
        """\\UXXXXX with fewer than 6 hex digits fails."""
        cursor = Cursor(source="U12345", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "6" in error.message

    def test_6digit_partial_2_digits_fails(self) -> None:
        """\\UXX with only 2 hex digits fails."""
        cursor = Cursor(source="U00", pos=0)
        assert parse_escape_sequence(cursor) is None

    def test_6digit_non_hex_fails(self) -> None:
        """\\UXXXXXX with non-hex characters fails."""
        cursor = Cursor(source="U0000GG", pos=0)
        assert parse_escape_sequence(cursor) is None

    # -- Surrogate boundary tests -----------------------------------------

    def test_just_below_surrogate_range(self) -> None:
        """U+D7FF (just before surrogates) accepted."""
        cursor = Cursor(source="U00D7FF", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        assert ord(result[0]) == 0xD7FF

    def test_just_above_surrogate_range(self) -> None:
        """U+E000 (just after surrogates) accepted."""
        cursor = Cursor(source="U00E000", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        assert ord(result[0]) == 0xE000

    # -- Property tests ---------------------------------------------------

    @given(
        surrogate=st.integers(
            min_value=0xD800, max_value=0xDFFF,
        )
    )
    def test_all_surrogates_rejected(
        self, surrogate: int,
    ) -> None:
        """All surrogate code points U+D800-U+DFFF rejected."""
        event(f"boundary=surrogate_{surrogate - 0xD800}")
        hex_value = f"U{surrogate:06X}"
        cursor = Cursor(source=hex_value, pos=0)
        assert parse_escape_sequence(cursor) is None

    @given(
        st.integers(min_value=0x110000, max_value=0xFFFFFF)
    )
    def test_oversized_code_points_rejected(
        self, code_point: int,
    ) -> None:
        """All code points > U+10FFFF rejected."""
        event(f"boundary=oversized_{min(code_point - 0x110000, 100)}")
        hex_str = f"U{code_point:06X}"
        cursor = Cursor(source=hex_str, pos=0)
        assert parse_escape_sequence(cursor) is None


# ============================================================================
# TestParseErrorContext
# ============================================================================


class TestParseErrorContext:
    """Parse error context management and stale error clearing."""

    def test_returns_none_initially(self) -> None:
        """get_last_parse_error returns None when no error."""
        clear_parse_error()
        assert get_last_parse_error() is None

    def test_stores_context_on_failure(self) -> None:
        """Parse error stores detailed context."""
        cursor = Cursor(source="123invalid", pos=0)
        assert parse_identifier(cursor) is None
        error = get_last_parse_error()
        assert error is not None
        assert error.message
        assert error.position == 0
        assert len(error.expected) > 0

    def test_clear_removes_context(self) -> None:
        """clear_parse_error clears error context."""
        cursor = Cursor(source="123", pos=0)
        parse_identifier(cursor)
        assert get_last_parse_error() is not None
        clear_parse_error()
        assert get_last_parse_error() is None

    def test_successive_attempts_update_error(self) -> None:
        """Successive parse failures update error context."""
        cursor1 = Cursor(source="123", pos=0)
        parse_identifier(cursor1)
        error1 = get_last_parse_error()

        cursor2 = Cursor(source="  456", pos=2)
        parse_identifier(cursor2)
        error2 = get_last_parse_error()

        assert error1 is not None
        assert error2 is not None
        assert error2.position == 2
        assert error2.position != error1.position

    def test_stale_error_cleared_by_identifier(self) -> None:
        """Successful parse_identifier clears stale error."""
        cursor1 = Cursor(source="-abc", pos=0)
        parse_number(cursor1)
        assert get_last_parse_error() is not None

        cursor2 = Cursor(source="validId", pos=0)
        result = parse_identifier(cursor2)
        assert result is not None
        assert get_last_parse_error() is None

    def test_stale_error_cleared_by_number(self) -> None:
        """Successful parse_number clears stale error."""
        cursor1 = Cursor(source="123", pos=0)
        parse_identifier(cursor1)
        assert get_last_parse_error() is not None

        cursor2 = Cursor(source="456", pos=0)
        result = parse_number(cursor2)
        assert result is not None
        assert get_last_parse_error() is None

    def test_stale_error_cleared_by_string(self) -> None:
        """Successful parse_string_literal clears stale error."""
        cursor1 = Cursor(source="-", pos=0)
        parse_number(cursor1)
        assert get_last_parse_error() is not None

        cursor2 = Cursor(source='"valid"', pos=0)
        result = parse_string_literal(cursor2)
        assert result is not None
        assert get_last_parse_error() is None

    def test_identifier_error_expected_values(self) -> None:
        """Identifier error includes expected character ranges."""
        clear_parse_error()
        cursor = Cursor(source="123", pos=0)
        parse_identifier(cursor)
        error = get_last_parse_error()
        assert error is not None
        assert "a-z" in error.expected or "A-Z" in error.expected

    def test_number_error_expected_values(self) -> None:
        """Number error includes expected digit range."""
        clear_parse_error()
        cursor = Cursor(source="-abc", pos=0)
        parse_number(cursor)
        error = get_last_parse_error()
        assert error is not None
        assert "0-9" in error.expected

    def test_string_error_expected_quote(self) -> None:
        """String error includes expected quote."""
        clear_parse_error()
        cursor = Cursor(source="hello", pos=0)
        parse_string_literal(cursor)
        error = get_last_parse_error()
        assert error is not None
        assert '"' in error.expected


# ============================================================================
# TestPrimitivesIntegration
# ============================================================================


class TestPrimitivesIntegration:
    """Integration tests combining multiple primitives."""

    def test_sequential_identifiers(self) -> None:
        """Parse multiple identifiers from same source."""
        source = "hello world"
        cursor = Cursor(source=source, pos=0)
        result1 = parse_identifier(cursor)
        assert result1 is not None
        assert result1.value == "hello"

        cursor = result1.cursor.advance()
        result2 = parse_identifier(cursor)
        assert result2 is not None
        assert result2.value == "world"

    def test_number_then_identifier(self) -> None:
        """Parse number followed by identifier."""
        cursor = Cursor(source="42 test", pos=0)
        num = parse_number(cursor)
        assert num is not None
        assert num.value == "42"
        cursor = num.cursor.advance()
        ident = parse_identifier(cursor)
        assert ident is not None
        assert ident.value == "test"

    def test_mixed_escape_types(self) -> None:
        """Parse string with mixed escape types."""
        cursor = Cursor(source=r'"\u00E4\n\t\"\\"', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == '\u00e4\n\t"\\'

    def test_identifier_and_string_sequence(self) -> None:
        """Parse identifier followed by string."""
        cursor = Cursor(source='greeting = "Hello"', pos=0)
        ident = parse_identifier(cursor)
        assert ident is not None
        assert ident.value == "greeting"
        str_cursor = Cursor(
            source='greeting = "Hello"', pos=11,
        )
        string = parse_string_literal(str_cursor)
        assert string is not None
        assert string.value == "Hello"

    @given(
        identifiers=st.lists(
            st.text(
                alphabet=st.characters(
                    min_codepoint=97, max_codepoint=122,
                ),
                min_size=1,
                max_size=10,
            ),
            min_size=1,
            max_size=5,
        )
    )
    @example(identifiers=["hello", "world"])
    def test_identifier_list_property(
        self, identifiers: list[str],
    ) -> None:
        """Space-separated identifiers parse sequentially."""
        event(f"boundary=id_count_{len(identifiers)}")
        source = " ".join(identifiers)
        cursor = Cursor(source=source, pos=0)

        for expected_id in identifiers:
            result = parse_identifier(cursor)
            assert result is not None
            assert result.value == expected_id
            cursor = result.cursor
            if not cursor.is_eof and cursor.current == " ":
                cursor = cursor.advance()

    def test_mixed_parse_errors_maintain_context(self) -> None:
        """Error context correctly updated across parse types."""
        cursor1 = Cursor(source="123", pos=0)
        assert parse_identifier(cursor1) is None

        cursor2 = Cursor(source="456", pos=0)
        assert parse_number(cursor2) is not None

        cursor3 = Cursor(source="no quote", pos=0)
        assert parse_string_literal(cursor3) is None
        error = get_last_parse_error()
        assert error is not None
        assert "quote" in error.message.lower()
