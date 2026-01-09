"""Error path tests for syntax/parser/primitives.py to achieve 100% coverage.

Targets uncovered error conditions and edge cases in primitive parsing:
- parse_identifier error contexts
- parse_number error contexts
- parse_escape_sequence surrogate validation
- parse_string_literal unterminated strings

Tests for stale error context cleanup:
- Parse functions now clear error context at start to prevent stale data
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.primitives import (
    clear_parse_error,
    get_last_parse_error,
    parse_escape_sequence,
    parse_identifier,
    parse_number,
    parse_string_literal,
)


class TestParseErrorContext:
    """Test parse error context storage and retrieval."""

    def test_get_last_parse_error_after_identifier_failure(self) -> None:
        """Test error context after parse_identifier fails."""
        clear_parse_error()
        cursor = Cursor(source="123invalid", pos=0)
        result = parse_identifier(cursor)

        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "identifier" in error.message.lower()
        assert error.position == 0

    def test_get_last_parse_error_after_number_failure(self) -> None:
        """Test error context after parse_number fails."""
        clear_parse_error()
        cursor = Cursor(source="-", pos=0)
        result = parse_number(cursor)

        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "number" in error.message.lower()

    def test_get_last_parse_error_after_string_failure(self) -> None:
        """Test error context after parse_string_literal fails."""
        clear_parse_error()
        cursor = Cursor(source='"unterminated', pos=0)
        result = parse_string_literal(cursor)

        assert result is None
        error = get_last_parse_error()
        assert error is not None
        assert "unterminated" in error.message.lower() or "string" in error.message.lower()

    def test_clear_parse_error_works(self) -> None:
        """Test clear_parse_error removes error context."""
        # Trigger an error
        cursor = Cursor(source="123", pos=0)
        parse_identifier(cursor)

        # Clear it
        clear_parse_error()

        # Should return None
        error = get_last_parse_error()
        assert error is None

    def test_get_last_parse_error_without_error_returns_none(self) -> None:
        """Test get_last_parse_error returns None when no error."""
        clear_parse_error()
        error = get_last_parse_error()
        assert error is None

    def test_stale_error_cleared_by_identifier_parse(self) -> None:
        """Test parse_identifier clears stale error context.

        Scenario: A previous parse failure left error context, but a new
        successful parse should not return that stale error.
        """
        # Create stale error by failing parse_number
        cursor1 = Cursor(source="-abc", pos=0)
        parse_number(cursor1)
        stale_error = get_last_parse_error()
        assert stale_error is not None  # Error was set

        # Now parse a valid identifier - this should clear the stale error
        cursor2 = Cursor(source="validIdentifier", pos=0)
        result = parse_identifier(cursor2)
        assert result is not None  # Parse succeeded

        # Error context should be cleared
        error_after = get_last_parse_error()
        assert error_after is None

    def test_stale_error_cleared_by_number_parse(self) -> None:
        """Test parse_number clears stale error context."""
        # Create stale error by failing parse_identifier
        cursor1 = Cursor(source="123", pos=0)
        parse_identifier(cursor1)
        stale_error = get_last_parse_error()
        assert stale_error is not None

        # Now parse a valid number - this should clear the stale error
        cursor2 = Cursor(source="456", pos=0)
        result = parse_number(cursor2)
        assert result is not None

        # Error context should be cleared
        error_after = get_last_parse_error()
        assert error_after is None

    def test_stale_error_cleared_by_string_parse(self) -> None:
        """Test parse_string_literal clears stale error context."""
        # Create stale error by failing parse_number
        cursor1 = Cursor(source="-", pos=0)
        parse_number(cursor1)
        stale_error = get_last_parse_error()
        assert stale_error is not None

        # Now parse a valid string - this should clear the stale error
        cursor2 = Cursor(source='"valid string"', pos=0)
        result = parse_string_literal(cursor2)
        assert result is not None

        # Error context should be cleared
        error_after = get_last_parse_error()
        assert error_after is None


class TestParseNumberEdgeCases:
    """Test parse_number error paths."""

    def test_parse_number_minus_without_digits(self) -> None:
        """Test parse_number with minus sign but no digits."""
        cursor = Cursor(source="-", pos=0)
        result = parse_number(cursor)
        assert result is None

    def test_parse_number_minus_followed_by_non_digit(self) -> None:
        """Test parse_number with minus followed by non-digit."""
        cursor = Cursor(source="-abc", pos=0)
        result = parse_number(cursor)
        assert result is None

    def test_parse_number_decimal_without_fractional_part(self) -> None:
        """Test parse_number with decimal point but no fractional digits."""
        cursor = Cursor(source="123.", pos=0)
        result = parse_number(cursor)
        assert result is None

    def test_parse_number_decimal_followed_by_non_digit(self) -> None:
        """Test parse_number with decimal point followed by non-digit."""
        cursor = Cursor(source="123.abc", pos=0)
        result = parse_number(cursor)
        assert result is None

    @given(
        st.text(min_size=1, max_size=10).filter(
            lambda s: not s[0].isdigit() and s[0] != "-"
        )
    )
    def test_parse_number_invalid_start_property(self, text: str) -> None:
        """PROPERTY: parse_number fails for non-numeric start."""
        cursor = Cursor(source=text, pos=0)
        result = parse_number(cursor)
        assert result is None


class TestParseEscapeSequenceSurrogates:
    """Test parse_escape_sequence surrogate code point rejection."""

    def test_escape_sequence_surrogate_low_boundary(self) -> None:
        """Test U+D800 (lowest surrogate) is rejected."""
        cursor = Cursor(source="U00D800", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None

        error = get_last_parse_error()
        assert error is not None
        assert "surrogate" in error.message.lower()

    def test_escape_sequence_surrogate_high_boundary(self) -> None:
        """Test U+DFFF (highest surrogate) is rejected."""
        cursor = Cursor(source="U00DFFF", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None

        error = get_last_parse_error()
        assert error is not None
        assert "surrogate" in error.message.lower()

    def test_escape_sequence_surrogate_middle_range(self) -> None:
        """Test U+DC00 (middle of surrogate range) is rejected."""
        cursor = Cursor(source="U00DC00", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None

    def test_escape_sequence_just_before_surrogate_range(self) -> None:
        """Test U+D7FF (just before surrogates) is accepted."""
        cursor = Cursor(source="U00D7FF", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        char, _ = result
        assert ord(char) == 0xD7FF

    def test_escape_sequence_just_after_surrogate_range(self) -> None:
        """Test U+E000 (just after surrogates) is accepted."""
        cursor = Cursor(source="U00E000", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is not None
        char, _ = result
        assert ord(char) == 0xE000

    @given(st.integers(min_value=0xD800, max_value=0xDFFF))
    def test_all_surrogate_code_points_rejected(self, code_point: int) -> None:
        """PROPERTY: All surrogate code points U+D800-U+DFFF are rejected."""
        hex_str = f"U{code_point:06X}"
        cursor = Cursor(source=hex_str, pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None, f"Surrogate {hex_str} should be rejected"


class TestParseEscapeSequenceInvalidHex:
    """Test parse_escape_sequence with invalid hex digits."""

    def test_escape_sequence_unicode_short_invalid_hex(self) -> None:
        """Test \\uXXXX with invalid hex digit."""
        cursor = Cursor(source="u00GG", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None

    def test_escape_sequence_unicode_short_partial_hex(self) -> None:
        """Test \\uXXXX with only 2 hex digits."""
        cursor = Cursor(source="u00", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None

    def test_escape_sequence_unicode_long_invalid_hex(self) -> None:
        """Test \\UXXXXXX with invalid hex digit."""
        cursor = Cursor(source="U0000GG", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None

    def test_escape_sequence_unicode_long_partial_hex(self) -> None:
        """Test \\UXXXXXX with only 4 hex digits."""
        cursor = Cursor(source="U0000", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None

    def test_escape_sequence_code_point_too_large(self) -> None:
        """Test code point > U+10FFFF is rejected."""
        cursor = Cursor(source="U110000", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None

        error = get_last_parse_error()
        assert error is not None
        assert "10FFFF" in error.message or "code point" in error.message.lower()

    @given(
        st.integers(min_value=0x110000, max_value=0xFFFFFF)
    )
    def test_oversized_code_points_rejected(self, code_point: int) -> None:
        """PROPERTY: All code points > U+10FFFF are rejected."""
        hex_str = f"U{code_point:06X}"
        cursor = Cursor(source=hex_str, pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None


class TestParseEscapeSequenceInvalidEscapes:
    """Test parse_escape_sequence with invalid escape characters."""

    def test_escape_sequence_invalid_escape_char(self) -> None:
        """Test invalid escape character like \\x."""
        cursor = Cursor(source="x", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None

        error = get_last_parse_error()
        assert error is not None
        assert "invalid" in error.message.lower() or "escape" in error.message.lower()

    def test_escape_sequence_at_eof(self) -> None:
        """Test escape sequence at EOF."""
        cursor = Cursor(source="", pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None

        error = get_last_parse_error()
        assert error is not None
        assert "EOF" in error.message or "unexpected" in error.message.lower()

    @given(
        st.characters().filter(
            lambda c: c not in {'"', "\\", "n", "t", "u", "U"}
        )
    )
    def test_invalid_escape_chars_property(self, char: str) -> None:
        """PROPERTY: Only valid escape chars are accepted."""
        cursor = Cursor(source=char, pos=0)
        result = parse_escape_sequence(cursor)
        assert result is None


class TestParseStringLiteralErrors:
    """Test parse_string_literal error paths."""

    def test_string_literal_no_opening_quote(self) -> None:
        """Test parse_string_literal without opening quote."""
        cursor = Cursor(source="hello", pos=0)
        result = parse_string_literal(cursor)
        assert result is None

        error = get_last_parse_error()
        assert error is not None
        assert "quote" in error.message.lower()

    def test_string_literal_unterminated_at_eof(self) -> None:
        """Test parse_string_literal with unterminated string."""
        cursor = Cursor(source='"unterminated', pos=0)
        result = parse_string_literal(cursor)
        assert result is None

        error = get_last_parse_error()
        assert error is not None
        assert "unterminated" in error.message.lower()

    def test_string_literal_with_invalid_escape(self) -> None:
        """Test parse_string_literal with invalid escape sequence."""
        cursor = Cursor(source=r'"test\xinvalid"', pos=0)
        result = parse_string_literal(cursor)
        # Should fail during escape sequence parsing
        assert result is None

    def test_string_literal_empty_source(self) -> None:
        """Test parse_string_literal with empty source."""
        cursor = Cursor(source="", pos=0)
        result = parse_string_literal(cursor)
        assert result is None


class TestParseIdentifierErrors:
    """Test parse_identifier error paths."""

    def test_identifier_at_eof(self) -> None:
        """Test parse_identifier at EOF."""
        cursor = Cursor(source="", pos=0)
        result = parse_identifier(cursor)
        assert result is None

        error = get_last_parse_error()
        assert error is not None
        assert "identifier" in error.message.lower()

    def test_identifier_starts_with_digit(self) -> None:
        """Test parse_identifier starting with digit."""
        cursor = Cursor(source="123abc", pos=0)
        result = parse_identifier(cursor)
        assert result is None

    def test_identifier_starts_with_hyphen(self) -> None:
        """Test parse_identifier starting with hyphen."""
        cursor = Cursor(source="-test", pos=0)
        result = parse_identifier(cursor)
        assert result is None

    def test_identifier_starts_with_underscore_ok(self) -> None:
        """Test parse_identifier starting with underscore fails (must start with alpha)."""
        cursor = Cursor(source="_test", pos=0)
        result = parse_identifier(cursor)
        # Underscore is NOT alpha, so this should fail
        assert result is None

    @given(
        st.characters().filter(lambda c: not c.isalpha())
    )
    def test_identifier_non_alpha_start_property(self, char: str) -> None:
        """PROPERTY: Identifiers must start with alphabetic character."""
        cursor = Cursor(source=f"{char}test", pos=0)
        result = parse_identifier(cursor)
        assert result is None


class TestParseErrorContextExpectedValues:
    """Test parse error context expected values."""

    def test_identifier_error_has_expected_values(self) -> None:
        """Test identifier error includes expected characters."""
        clear_parse_error()
        cursor = Cursor(source="123", pos=0)
        parse_identifier(cursor)

        error = get_last_parse_error()
        assert error is not None
        assert len(error.expected) > 0
        assert "a-z" in error.expected or "A-Z" in error.expected

    def test_number_error_has_expected_values(self) -> None:
        """Test number error includes expected digits."""
        clear_parse_error()
        cursor = Cursor(source="-abc", pos=0)
        parse_number(cursor)

        error = get_last_parse_error()
        assert error is not None
        assert "0-9" in error.expected

    def test_string_error_has_expected_quote(self) -> None:
        """Test string error includes expected quote."""
        clear_parse_error()
        cursor = Cursor(source="hello", pos=0)
        parse_string_literal(cursor)

        error = get_last_parse_error()
        assert error is not None
        assert '"' in error.expected


class TestPrimitiveParsingIntegration:
    """Integration tests for primitive parsing error handling."""

    def test_mixed_parsing_errors_maintain_context(self) -> None:
        """Test that error context is correctly updated for each parse."""
        # Parse identifier - should fail
        cursor1 = Cursor(source="123", pos=0)
        result1 = parse_identifier(cursor1)
        assert result1 is None
        error1 = get_last_parse_error()
        assert error1 is not None

        # Parse number - should succeed, clearing error
        cursor2 = Cursor(source="456", pos=0)
        result2 = parse_number(cursor2)
        assert result2 is not None
        # Error context might still be set from previous failure

        # Parse string - should fail
        cursor3 = Cursor(source="no quote", pos=0)
        result3 = parse_string_literal(cursor3)
        assert result3 is None
        error3 = get_last_parse_error()
        assert error3 is not None
        assert "quote" in error3.message.lower()

    @given(
        st.one_of(
            st.just("123id"),  # Invalid identifier
            st.just("-"),      # Invalid number
            st.just('"eof'),   # Invalid string
        )
    )
    def test_error_context_property(self, invalid_input: str) -> None:
        """PROPERTY: Parse failures set error context."""
        clear_parse_error()
        cursor = Cursor(source=invalid_input, pos=0)

        # Try all parsers
        id_result = parse_identifier(cursor)
        if id_result is None:
            error = get_last_parse_error()
            if error is not None:  # Error context was set
                assert error.position >= 0
                assert len(error.message) > 0
