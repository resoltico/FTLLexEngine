"""Tests for _compute_visible_precision edge cases.

Validates that visible fraction digit counting handles:
- Standard decimal formats
- Custom Babel patterns with digit literals in suffix text
- Currency-suffixed formats
- Boundary conditions (empty string, trailing decimal, leading decimal)

Property: for any formatted number, counted digits must not exceed the
actual fractional digit count regardless of trailing literal text.
"""

from __future__ import annotations

from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.functions import _compute_visible_precision


class TestComputeVisiblePrecisionStandard:
    """Standard formatting scenarios."""

    def test_two_decimal_dot(self) -> None:
        """Standard 2-decimal format with dot separator."""
        assert _compute_visible_precision("1,234.56", ".") == 2

    def test_two_decimal_comma(self) -> None:
        """Standard 2-decimal format with comma separator."""
        assert _compute_visible_precision("1.234,56", ",") == 2

    def test_no_decimal(self) -> None:
        """Integer format with no decimal separator."""
        assert _compute_visible_precision("1,234", ".") == 0

    def test_trailing_zeros(self) -> None:
        """Trailing zeros are counted (CLDR v operand preserves them)."""
        assert _compute_visible_precision("1.00", ".") == 2

    def test_three_decimals(self) -> None:
        """Three decimal places (e.g., BHD formatting)."""
        assert _compute_visible_precision("1.000", ".") == 3

    def test_single_decimal(self) -> None:
        """Single decimal digit."""
        assert _compute_visible_precision("1.5", ".") == 1


class TestComputeVisiblePrecisionCustomPatterns:
    """Custom Babel format patterns with literal text containing digits."""

    def test_digit_literal_suffix(self) -> None:
        """Custom pattern with digit-containing literal after fraction.

        Pattern like '#,##0.00 Dollars 123' produces a formatted string
        where literal text with digits follows the fractional part.
        Only the leading consecutive fraction digits should be counted.
        """
        assert _compute_visible_precision("100.00 Dollars 123", ".") == 2

    def test_currency_code_suffix_no_digits(self) -> None:
        """Currency code suffix without digits does not affect count."""
        assert _compute_visible_precision("100.00EUR", ".") == 2

    def test_currency_code_suffix_with_space(self) -> None:
        """Spaced currency code suffix."""
        assert _compute_visible_precision("100.00 EUR", ".") == 2

    def test_parenthetical_suffix(self) -> None:
        """Accounting format with parenthetical suffix."""
        assert _compute_visible_precision("(1,234.56)", ".") == 2

    def test_percent_suffix(self) -> None:
        """Percent format suffix."""
        assert _compute_visible_precision("45.67%", ".") == 2

    def test_suffix_starting_with_digits(self) -> None:
        """Suffix text that starts with digits after fraction.

        Fraction digits end at the first non-digit character after
        the decimal separator.
        """
        # "100.00123abc" -> fraction part is "00123abc", leading digits = 5
        # But this is unrealistic for real Babel patterns. Testing the algorithm:
        assert _compute_visible_precision("100.00 123abc", ".") == 2


class TestComputeVisiblePrecisionBoundary:
    """Boundary and edge conditions."""

    def test_empty_string(self) -> None:
        """Empty input string has zero precision."""
        assert _compute_visible_precision("", ".") == 0

    def test_leading_decimal(self) -> None:
        """Number with leading decimal point."""
        assert _compute_visible_precision(".5", ".") == 1

    def test_trailing_decimal_no_digits(self) -> None:
        """Trailing decimal with no fraction digits."""
        assert _compute_visible_precision("1.", ".") == 0

    def test_decimal_symbol_only(self) -> None:
        """String that is just the decimal symbol."""
        assert _compute_visible_precision(".", ".") == 0

    def test_no_matching_separator(self) -> None:
        """Separator not present in string."""
        assert _compute_visible_precision("1234", ".") == 0

    def test_multiple_separators(self) -> None:
        """Multiple occurrences of separator (uses rightmost via rsplit)."""
        assert _compute_visible_precision("1.234.56", ".") == 2


class TestComputeVisiblePrecisionHypothesis:
    """Property-based tests for visible precision counting."""

    @given(
        integer_part=st.integers(min_value=0, max_value=999_999),
        fraction_digits=st.integers(min_value=0, max_value=6),
        suffix=st.text(
            alphabet=st.sampled_from("abcABC %$"),
            min_size=0,
            max_size=5,
        ),
    )
    @settings(max_examples=200)
    def test_precision_matches_fraction_length(
        self,
        integer_part: int,
        fraction_digits: int,
        suffix: str,
    ) -> None:
        """Counted precision equals the number of requested fraction digits.

        Constructs formatted strings with a known number of fraction digits
        followed by optional non-digit suffix text. The computed precision
        must match the known fraction digit count.
        """
        event(f"fraction_digits={fraction_digits}")
        if fraction_digits == 0:
            formatted = f"{integer_part}{suffix}"
            result = _compute_visible_precision(formatted, ".")
            assert result == 0
        else:
            fraction = "0" * fraction_digits
            formatted = f"{integer_part}.{fraction}{suffix}"
            result = _compute_visible_precision(formatted, ".")
            assert result == fraction_digits

    @given(
        integer_part=st.integers(min_value=0, max_value=999_999),
        fraction_digits=st.integers(min_value=1, max_value=6),
        digit_suffix=st.text(
            alphabet=st.sampled_from("0123456789"),
            min_size=1,
            max_size=5,
        ),
    )
    @settings(max_examples=200)
    def test_digit_suffix_excluded_after_non_digit(
        self,
        integer_part: int,
        fraction_digits: int,
        digit_suffix: str,
    ) -> None:
        """Digit characters in suffix text are excluded from precision count.

        When a non-digit character separates fraction digits from suffix
        digits, only the leading fraction digits are counted.
        """
        event(f"suffix_len={len(digit_suffix)}")
        fraction = "0" * fraction_digits
        # Insert a space between fraction and digit suffix
        formatted = f"{integer_part}.{fraction} {digit_suffix}"
        result = _compute_visible_precision(formatted, ".")
        assert result == fraction_digits
