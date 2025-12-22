"""Comprehensive property-based tests for syntax.parser.primitives module.

Tests primitive parsing utilities for identifiers, numbers, and strings.

"""

from hypothesis import assume, given
from hypothesis import strategies as st

from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.primitives import (
    parse_escape_sequence,
    parse_identifier,
    parse_number,
    parse_number_value,
    parse_string_literal,
)


class TestParseIdentifier:
    """Property-based tests for parse_identifier function."""

    def test_parse_identifier_simple(self) -> None:
        """Verify parse_identifier parses simple identifier."""
        cursor = Cursor(source="hello", pos=0)
        result = parse_identifier(cursor)
        assert result is not None
        assert result.value == "hello"
        assert result.cursor.is_eof

    def test_parse_identifier_with_hyphens(self) -> None:
        """Verify parse_identifier parses identifier with hyphens."""
        cursor = Cursor(source="brand-name", pos=0)
        result = parse_identifier(cursor)
        assert result is not None
        assert result.value == "brand-name"

    def test_parse_identifier_with_underscores(self) -> None:
        """Verify parse_identifier parses identifier with underscores."""
        cursor = Cursor(source="file_name", pos=0)
        result = parse_identifier(cursor)
        assert result is not None
        assert result.value == "file_name"

    def test_parse_identifier_with_digits(self) -> None:
        """Verify parse_identifier parses identifier with digits."""
        cursor = Cursor(source="test123", pos=0)
        result = parse_identifier(cursor)
        assert result is not None
        assert result.value == "test123"

    def test_parse_identifier_single_letter(self) -> None:
        """Verify parse_identifier parses single letter identifier."""
        cursor = Cursor(source="x", pos=0)
        result = parse_identifier(cursor)
        assert result is not None
        assert result.value == "x"

    def test_parse_identifier_stops_at_space(self) -> None:
        """Verify parse_identifier stops at space."""
        cursor = Cursor(source="hello world", pos=0)
        result = parse_identifier(cursor)
        assert result is not None
        assert result.value == "hello"
        assert result.cursor.pos == 5

    def test_parse_identifier_starts_with_digit_fails(self) -> None:
        """Verify parse_identifier returns None when starting with digit."""
        cursor = Cursor(source="123test", pos=0)
        result = parse_identifier(cursor)
        assert result is None

    def test_parse_identifier_starts_with_hyphen_fails(self) -> None:
        """Verify parse_identifier returns None when starting with hyphen."""
        cursor = Cursor(source="-test", pos=0)
        result = parse_identifier(cursor)
        assert result is None

    def test_parse_identifier_at_eof_fails(self) -> None:
        """Verify parse_identifier returns None at EOF."""
        cursor = Cursor(source="", pos=0)
        result = parse_identifier(cursor)
        assert result is None

    @given(st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=1))
    def test_parse_identifier_alphabetic(self, identifier: str) -> None:
        """Property: parse_identifier succeeds for alphabetic strings."""
        cursor = Cursor(source=identifier, pos=0)
        result = parse_identifier(cursor)
        assert result is not None
        assert result.value == identifier


class TestParseNumberValue:
    """Property-based tests for parse_number_value function."""

    def test_parse_number_value_integer(self) -> None:
        """Verify parse_number_value returns int for integer string."""
        result = parse_number_value("42")
        assert result == 42
        assert isinstance(result, int)

    def test_parse_number_value_negative_integer(self) -> None:
        """Verify parse_number_value handles negative integers."""
        result = parse_number_value("-123")
        assert result == -123
        assert isinstance(result, int)

    def test_parse_number_value_float(self) -> None:
        """Verify parse_number_value returns float for decimal string."""
        result = parse_number_value("3.14")
        assert result == 3.14
        assert isinstance(result, float)

    def test_parse_number_value_negative_float(self) -> None:
        """Verify parse_number_value handles negative floats."""
        result = parse_number_value("-2.5")
        assert result == -2.5
        assert isinstance(result, float)

    def test_parse_number_value_zero(self) -> None:
        """Verify parse_number_value handles zero."""
        result = parse_number_value("0")
        assert result == 0
        assert isinstance(result, int)

    @given(st.integers())
    def test_parse_number_value_integers(self, value: int) -> None:
        """Property: parse_number_value correctly converts integer strings."""
        num_str = str(value)
        result = parse_number_value(num_str)
        assert result == value
        assert isinstance(result, int)

    @given(st.floats(allow_nan=False, allow_infinity=False))
    def test_parse_number_value_floats(self, value: float) -> None:
        """Property: parse_number_value correctly converts float strings."""
        num_str = str(value)
        assume("." in num_str)  # Ensure it's a float representation
        result = parse_number_value(num_str)
        assert isinstance(result, float)


class TestParseNumber:
    """Property-based tests for parse_number function."""

    def test_parse_number_simple_integer(self) -> None:
        """Verify parse_number parses simple integer."""
        cursor = Cursor(source="42", pos=0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == "42"
        assert result.cursor.is_eof

    def test_parse_number_negative_integer(self) -> None:
        """Verify parse_number parses negative integer."""
        cursor = Cursor(source="-123", pos=0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == "-123"

    def test_parse_number_float(self) -> None:
        """Verify parse_number parses float."""
        cursor = Cursor(source="3.14", pos=0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == "3.14"

    def test_parse_number_negative_float(self) -> None:
        """Verify parse_number parses negative float."""
        cursor = Cursor(source="-2.5", pos=0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == "-2.5"

    def test_parse_number_zero(self) -> None:
        """Verify parse_number parses zero."""
        cursor = Cursor(source="0", pos=0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == "0"

    def test_parse_number_float_with_leading_zero(self) -> None:
        """Verify parse_number parses float with leading zero."""
        cursor = Cursor(source="0.001", pos=0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == "0.001"

    def test_parse_number_stops_at_non_digit(self) -> None:
        """Verify parse_number stops at non-digit character."""
        cursor = Cursor(source="123abc", pos=0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == "123"
        assert result.cursor.pos == 3

    def test_parse_number_no_digits_after_minus_fails(self) -> None:
        """Verify parse_number returns None for minus without digits."""
        cursor = Cursor(source="-abc", pos=0)
        result = parse_number(cursor)
        assert result is None

    def test_parse_number_decimal_without_trailing_digits_fails(self) -> None:
        """Verify parse_number returns None for decimal without trailing digits."""
        cursor = Cursor(source="123.", pos=0)
        result = parse_number(cursor)
        assert result is None

    def test_parse_number_at_eof_fails(self) -> None:
        """Verify parse_number returns None at EOF."""
        cursor = Cursor(source="", pos=0)
        result = parse_number(cursor)
        assert result is None

    @given(st.integers(min_value=0, max_value=1000000))
    def test_parse_number_positive_integers(self, value: int) -> None:
        """Property: parse_number correctly parses positive integer strings."""
        num_str = str(value)
        cursor = Cursor(source=num_str, pos=0)
        result = parse_number(cursor)
        assert result is not None
        assert result.value == num_str

    def test_parse_number_rejects_unicode_superscript_digits(self) -> None:
        """Regression test: Unicode superscript digits must not be parsed as numbers.

        FTL spec only allows ASCII digits 0-9 in number literals.
        str.isdigit() returns True for Unicode digits like ² (U+00B2),
        but int() cannot parse them, causing ValueError.
        """
        # Superscript 2 (U+00B2) - isdigit() returns True but not ASCII
        cursor = Cursor(source="²", pos=0)
        result = parse_number(cursor)
        assert result is None, "Unicode superscript digits should not parse as numbers"

        # Superscript 3 (U+00B3)
        cursor = Cursor(source="³", pos=0)
        result = parse_number(cursor)
        assert result is None

        # Arabic-Indic digit (U+0660)
        cursor = Cursor(source="\u0660", pos=0)
        result = parse_number(cursor)
        assert result is None

    def test_parse_number_unicode_digit_in_placeable_context(self) -> None:
        """Regression test: FTL source with Unicode digits should not crash.

        Input like '{²' was causing ValueError in parse_number_value() because
        the parser incorrectly identified ² as a number due to isdigit().
        """
        # This tests the primitives layer - the full integration test is in
        # test_localization_hypothesis.py::test_format_value_never_crashes
        cursor = Cursor(source="²abc", pos=0)
        result = parse_number(cursor)
        assert result is None, "Should reject Unicode digit ² at start"


class TestParseEscapeSequence:
    """Property-based tests for parse_escape_sequence function."""

    def test_parse_escape_sequence_quote(self) -> None:
        """Verify parse_escape_sequence handles escaped quote."""
        cursor = Cursor(source='"hello', pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        escaped_char, new_cursor = result
        assert escaped_char == '"'
        assert new_cursor.pos == 1

    def test_parse_escape_sequence_backslash(self) -> None:
        """Verify parse_escape_sequence handles escaped backslash."""
        cursor = Cursor(source="\\hello", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        escaped_char, new_cursor = result
        assert escaped_char == "\\"
        assert new_cursor.pos == 1

    def test_parse_escape_sequence_newline(self) -> None:
        """Verify parse_escape_sequence handles \\n."""
        cursor = Cursor(source="nhello", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        escaped_char, new_cursor = result
        assert escaped_char == "\n"
        assert new_cursor.pos == 1

    def test_parse_escape_sequence_tab(self) -> None:
        """Verify parse_escape_sequence handles \\t."""
        cursor = Cursor(source="thello", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        escaped_char, new_cursor = result
        assert escaped_char == "\t"
        assert new_cursor.pos == 1

    def test_parse_escape_sequence_unicode_4digit(self) -> None:
        """Verify parse_escape_sequence handles \\uXXXX."""
        cursor = Cursor(source="u00E4", pos=0)  # ä
        result = parse_escape_sequence(cursor)
        assert result is not None
        escaped_char, new_cursor = result
        assert escaped_char == "ä"
        assert new_cursor.pos == 5

    def test_parse_escape_sequence_unicode_6digit(self) -> None:
        """Verify parse_escape_sequence handles \\UXXXXXX."""
        cursor = Cursor(source="U01F600", pos=0)  # Emoji
        result = parse_escape_sequence(cursor)
        assert result is not None
        escaped_char, new_cursor = result
        assert len(escaped_char) == 1  # Single character
        assert new_cursor.pos == 7

    def test_parse_escape_sequence_invalid_escape_fails(self) -> None:
        """Verify parse_escape_sequence returns None for invalid escape."""
        cursor = Cursor(source="xhello", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None

    def test_parse_escape_sequence_at_eof_fails(self) -> None:
        """Verify parse_escape_sequence returns None at EOF."""
        cursor = Cursor(source="", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None

    def test_parse_escape_sequence_unicode_invalid_hex_fails(self) -> None:
        """Verify parse_escape_sequence returns None for invalid Unicode hex."""
        cursor = Cursor(source="u00GG", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None

    def test_parse_escape_sequence_unicode_too_large_fails(self) -> None:
        """Verify parse_escape_sequence returns None for code point > U+10FFFF."""
        cursor = Cursor(source="U110000", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None

    def test_parse_escape_sequence_surrogate_low_fails(self) -> None:
        """Verify parse_escape_sequence rejects low surrogate U+D800."""
        cursor = Cursor(source="U00D800", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None

    def test_parse_escape_sequence_surrogate_high_fails(self) -> None:
        """Verify parse_escape_sequence rejects high surrogate U+DFFF."""
        cursor = Cursor(source="U00DFFF", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None

    def test_parse_escape_sequence_surrogate_middle_fails(self) -> None:
        """Verify parse_escape_sequence rejects surrogate in middle of range."""
        cursor = Cursor(source="U00DC00", pos=0)  # Middle of surrogate range
        result = parse_escape_sequence(cursor)
        assert result is None

    @given(
        surrogate=st.integers(min_value=0xD800, max_value=0xDFFF),
    )
    def test_parse_escape_sequence_all_surrogates_rejected(self, surrogate: int) -> None:
        """Property: All surrogate code points (U+D800-U+DFFF) are rejected."""
        hex_value = f"U{surrogate:06X}"
        cursor = Cursor(source=hex_value, pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None, f"Surrogate {hex_value} should be rejected"

    def test_parse_escape_sequence_just_below_surrogate_range_works(self) -> None:
        """Verify code point just below surrogate range (U+D7FF) works."""
        cursor = Cursor(source="U00D7FF", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        escaped_char, _ = result
        assert ord(escaped_char) == 0xD7FF

    def test_parse_escape_sequence_just_above_surrogate_range_works(self) -> None:
        """Verify code point just above surrogate range (U+E000) works."""
        cursor = Cursor(source="U00E000", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        escaped_char, _ = result
        assert ord(escaped_char) == 0xE000


class TestParseStringLiteral:
    """Property-based tests for parse_string_literal function."""

    def test_parse_string_literal_simple(self) -> None:
        """Verify parse_string_literal parses simple string."""
        cursor = Cursor(source='"hello"', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == "hello"
        assert result.cursor.is_eof

    def test_parse_string_literal_empty(self) -> None:
        """Verify parse_string_literal parses empty string."""
        cursor = Cursor(source='""', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == ""
        assert result.cursor.is_eof

    def test_parse_string_literal_with_escaped_quote(self) -> None:
        """Verify parse_string_literal handles escaped quotes."""
        cursor = Cursor(source=r'"with \"quotes\""', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == 'with "quotes"'

    def test_parse_string_literal_with_escaped_backslash(self) -> None:
        """Verify parse_string_literal handles escaped backslash."""
        cursor = Cursor(source=r'"path\\to\\file"', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == "path\\to\\file"

    def test_parse_string_literal_with_newline_escape(self) -> None:
        """Verify parse_string_literal handles \\n escape."""
        cursor = Cursor(source=r'"line1\nline2"', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == "line1\nline2"

    def test_parse_string_literal_with_tab_escape(self) -> None:
        """Verify parse_string_literal handles \\t escape."""
        cursor = Cursor(source=r'"col1\tcol2"', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == "col1\tcol2"

    def test_parse_string_literal_with_unicode_escape(self) -> None:
        """Verify parse_string_literal handles \\uXXXX escape."""
        cursor = Cursor(source=r'"unicode: \u00E4"', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == "unicode: ä"

    def test_parse_string_literal_unterminated_fails(self) -> None:
        """Verify parse_string_literal returns None for unterminated string."""
        cursor = Cursor(source='"hello', pos=0)
        result = parse_string_literal(cursor)
        assert result is None

    def test_parse_string_literal_no_opening_quote_fails(self) -> None:
        """Verify parse_string_literal returns None without opening quote."""
        cursor = Cursor(source="hello", pos=0)
        result = parse_string_literal(cursor)
        assert result is None

    def test_parse_string_literal_at_eof_fails(self) -> None:
        """Verify parse_string_literal returns None at EOF."""
        cursor = Cursor(source="", pos=0)
        result = parse_string_literal(cursor)
        assert result is None

    @given(st.text(alphabet=st.characters(blacklist_characters='"\\\n\r\t')))
    def test_parse_string_literal_various_content(self, content: str) -> None:
        """Property: parse_string_literal correctly parses quoted strings."""
        source = f'"{content}"'
        cursor = Cursor(source=source, pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == content

    def test_parse_string_literal_multiple_escapes(self) -> None:
        """Verify parse_string_literal handles multiple escape sequences."""
        cursor = Cursor(source=r'"a\"b\\c\nd"', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == 'a"b\\c\nd'

    def test_parse_string_literal_stops_at_closing_quote(self) -> None:
        """Verify parse_string_literal stops at closing quote."""
        cursor = Cursor(source='"hello" world', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == "hello"
        assert result.cursor.pos == 7


class TestParserIntegration:
    """Integration tests for parser primitives working together."""

    def test_parse_identifier_then_number(self) -> None:
        """Integration: Parse identifier followed by number."""
        cursor = Cursor(source="name123", pos=0)

        # Parse identifier first
        id_result = parse_identifier(cursor)
        assert id_result is not None
        assert id_result.value == "name123"  # Identifier includes digits

    def test_parse_number_in_context(self) -> None:
        """Integration: Parse number within larger text."""
        cursor = Cursor(source="count = 42", pos=8)  # Position at "42"

        result = parse_number(cursor)
        assert result is not None
        assert result.value == "42"

    def test_parse_string_with_unicode_and_escapes(self) -> None:
        """Integration: Parse string with mixed escape types."""
        cursor = Cursor(source=r'"\u00E4\n\t\"\\"', pos=0)
        result = parse_string_literal(cursor)
        assert result is not None
        assert result.value == 'ä\n\t"\\'

    def test_parse_identifier_and_string_in_sequence(self) -> None:
        """Integration: Parse identifier followed by string."""
        cursor = Cursor(source='greeting = "Hello"', pos=0)

        # Parse identifier
        id_result = parse_identifier(cursor)
        assert id_result is not None
        assert id_result.value == "greeting"

        # Skip to string (manually for this test)
        str_cursor = Cursor(source='greeting = "Hello"', pos=11)
        str_result = parse_string_literal(str_cursor)
        assert str_result is not None
        assert str_result.value == "Hello"
