"""Hypothesis-based property tests for currency parsing.

Functions return tuple[value, errors]:
- parse_currency() returns tuple[tuple[Decimal, str] | None, tuple[FluentParseError, ...]]
- Functions never raise exceptions; errors returned in tuple

Focus on financial precision and edge cases.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.parsing import parse_currency
from ftllexengine.parsing.currency import _get_currency_maps


class TestParseCurrencyHypothesis:
    """Property-based tests for parse_currency()."""

    @given(
        amount=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("999999.99"),
            places=2,
        ),
        currency_symbol=st.sampled_from(["€", "$", "£", "¥", "₹", "₽", "₪", "₫", "₱"]),
    )
    @settings(max_examples=200, deadline=None)  # deadline=None for CLDR cache warmup
    def test_parse_currency_roundtrip_financial_precision(
        self, amount: Decimal, currency_symbol: str
    ) -> None:
        """Roundtrip parsing preserves financial precision (critical for accounting)."""
        # Format: symbol + amount (no locale formatting for simplicity)
        currency_str = f"{currency_symbol}{amount}"

        # Yen sign ambiguous (JPY vs CNY based on locale)
        # Pound sign ambiguous (GBP, EGP, etc. based on locale)
        ambiguous_symbols = {
            "$": "USD", "¢": "USD", "₨": "INR", "₱": "PHP", "¥": "JPY", "£": "GBP"
        }
        default_currency = ambiguous_symbols.get(currency_symbol)

        result, errors = parse_currency(
            currency_str, "en_US", default_currency=default_currency
        )
        assert not errors
        assert result is not None

        parsed_amount, currency_code = result

        # Must preserve exact decimal value (no float rounding)
        assert parsed_amount == amount, f"Expected {amount}, got {parsed_amount}"
        assert isinstance(parsed_amount, Decimal), "Must return Decimal for precision"

        # Currency code must be valid
        assert len(currency_code) == 3
        assert currency_code.isupper()

    @given(
        # Use actual ISO 4217 codes from CLDR (validated against CLDR)
        currency_code=st.sampled_from([
            "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "CNY", "INR",
            "BRL", "MXN", "KRW", "RUB", "ZAR", "SGD", "HKD", "NOK", "SEK", "DKK",
            "PLN", "TRY", "THB", "MYR", "IDR", "PHP", "VND", "CZK", "HUF", "ILS",
        ]),
    )
    @settings(max_examples=50)
    def test_parse_currency_iso_code_format(self, currency_code: str) -> None:
        """Valid ISO 4217 currency codes should be recognized."""
        amount_str = f"{currency_code} 123.45"

        result, errors = parse_currency(amount_str, "en_US")
        assert not errors, f"Failed for {currency_code}: {errors}"
        assert result is not None

        parsed_amount, parsed_code = result

        # Should preserve ISO code exactly
        assert parsed_code == currency_code
        assert parsed_amount == Decimal("123.45")

    @given(
        unknown_symbol=st.text(
            alphabet=st.characters(
                whitelist_categories=["So"],  # Other symbols
                blacklist_characters="€$£¥₹₽¢₡₦₧₨₩₪₫₱₴₵₸₺₼₾",
            ),
            min_size=1,
            max_size=1,
        ).filter(lambda x: x not in "€$£¥₹₽¢₡₦₧₨₩₪₫₱₴₵₸₺₼₾"),
    )
    @settings(max_examples=50)
    def test_parse_currency_unknown_symbol_returns_error(
        self, unknown_symbol: str
    ) -> None:
        """Unknown currency symbols should return error in tuple; function never raises."""
        currency_str = f"{unknown_symbol}100.50"

        result, errors = parse_currency(
            currency_str, "en_US", default_currency="USD"
        )
        assert len(errors) > 0
        assert result is None

    def test_parse_currency_symbol_in_regex_but_not_in_map(self) -> None:
        """Test defensive code: symbol in regex but not in mapping."""
        from unittest.mock import patch

        from ftllexengine.parsing.currency import _get_currency_pattern_full

        # Get original maps and create modified version missing € symbol
        original_symbol_map, original_ambiguous, original_locale_map, original_valid_codes = (
            _get_currency_maps()
        )
        modified_map = original_symbol_map.copy()
        del modified_map["€"]

        # Clear pattern cache before test
        _get_currency_pattern_full.cache_clear()

        # Mock _get_currency_maps to return modified maps
        mock_return = (
            modified_map, original_ambiguous, original_locale_map, original_valid_codes
        )
        with patch(
            "ftllexengine.parsing.currency._get_currency_maps",
            return_value=mock_return,
        ):
            # Clear cache again after patching to force regeneration
            _get_currency_pattern_full.cache_clear()

            # Now € is in the regex but not in the map - should return error
            result, errors = parse_currency("€100.50", "en_US")
            assert len(errors) > 0
            assert result is None

        # Clean up - restore cache
        _get_currency_pattern_full.cache_clear()

    @given(
        invalid_number=st.one_of(
            st.text(
                alphabet=st.characters(whitelist_categories=["L"]),  # Letters only
                min_size=1,
                max_size=10,
            ).filter(lambda x: x.upper() not in ("NAN", "INFINITY", "INF")),
            st.just("abc"),
            st.just("xyz123"),
            st.just("!@#"),
            st.just(""),
        ),
    )
    @settings(max_examples=50)
    def test_parse_currency_invalid_number_returns_error(
        self, invalid_number: str
    ) -> None:
        """Invalid numbers should return error in tuple; function never raises."""
        # Note: Babel accepts NaN/Infinity/Inf (any case) as valid Decimal values
        # Use $ with default_currency
        currency_str = f"${invalid_number}"

        result, errors = parse_currency(
            currency_str, "en_US", default_currency="USD"
        )
        assert len(errors) > 0
        assert result is None

    @given(
        value=st.one_of(
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.lists(st.integers()),
            st.dictionaries(st.text(), st.integers()),
        ),
    )
    @settings(max_examples=50)
    def test_parse_currency_type_error_returns_error(self, value: object) -> None:
        """Non-string types should return error in tuple; function never raises."""
        result, errors = parse_currency(value, "en_US")
        assert len(errors) > 0
        assert result is None

    @given(
        amount=st.decimals(
            min_value=Decimal("-999999.99"),
            max_value=Decimal("-0.01"),
            places=2,
        ),
    )
    @settings(max_examples=100)
    def test_parse_currency_negative_amounts(self, amount: Decimal) -> None:
        """Negative amounts should parse correctly (debt, refunds)."""
        currency_str = f"${amount}"

        result, errors = parse_currency(currency_str, "en_US", default_currency="USD")
        assert not errors
        assert result is not None

        parsed_amount, _ = result

        # Negative amounts are valid for accounting
        assert parsed_amount == amount
        assert parsed_amount < 0

    @given(
        amount=st.decimals(
            min_value=Decimal("0.001"),
            max_value=Decimal("0.999"),
            places=3,
        ),
    )
    @settings(max_examples=100)
    def test_parse_currency_fractional_amounts(self, amount: Decimal) -> None:
        """Sub-dollar amounts should preserve precision (critical for financial)."""
        currency_str = f"${amount}"

        result, errors = parse_currency(currency_str, "en_US", default_currency="USD")
        assert not errors
        assert result is not None

        parsed_amount, _ = result

        # Must preserve fractional precision
        assert parsed_amount == amount
        assert parsed_amount < Decimal("1.00")

    @given(
        locale=st.sampled_from(["en_US", "de_DE", "fr_FR", "ja_JP", "lv_LV", "pl_PL"]),
    )
    @settings(max_examples=50)
    def test_parse_currency_locale_independence(self, locale: str) -> None:
        """Currency parsing should work across locales."""
        # Use ISO code (universal)
        currency_str = "EUR 1234.56"

        result, errors = parse_currency(currency_str, locale)
        assert not errors
        assert result is not None

        parsed_amount, currency_code = result

        assert currency_code == "EUR"
        # Note: Babel parsing may interpret differently based on locale
        # Main check: doesn't crash and returns valid Decimal
        assert isinstance(parsed_amount, Decimal)

    @given(
        value=st.text(
            alphabet=st.characters(min_codepoint=32, max_codepoint=126),  # ASCII printable
            min_size=1,
        ).filter(
            lambda x: (
                # Exclude common currency symbols
                not any(
                    symbol in x for symbol in "€$£¥₹₽¢₡₦₧₨₩₪₫₱₴₵₸₺₼₾"
                )
                # Exclude 3-letter ISO currency codes
                and not any(
                    x[i : i + 3].isupper() and x[i : i + 3].isalpha()
                    for i in range(len(x) - 2)
                )
                # Exclude CLDR-derived currency symbols (many single-letter symbols exist)
                # e.g., 'F' -> FRF, 'R' -> ZAR, 'K' -> various currencies
                and not any(
                    symbol in x for symbol in _get_currency_maps()[0]
                )
            )
        ),
    )
    @settings(max_examples=100)
    def test_parse_currency_no_symbol_returns_error(self, value: str) -> None:
        """Strings without currency symbols/codes should return error in tuple."""
        result, errors = parse_currency(value, "en_US")
        assert len(errors) > 0
        assert result is None


class TestCurrencyMetamorphicProperties:
    """Metamorphic properties for currency parsing."""

    @given(
        amount1=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("999.99"), places=2),
        amount2=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("999.99"), places=2),
        currency=st.sampled_from(["EUR", "USD", "GBP"]),  # Exclude JPY (zero-decimal)
    )
    @settings(max_examples=100)
    def test_parse_currency_comparison_property(
        self, amount1: Decimal, amount2: Decimal, currency: str
    ) -> None:
        """parse(format(a)) < parse(format(b)) iff a < b (ordering preserved)."""
        from ftllexengine.runtime.functions import currency_format

        formatted1 = currency_format(float(amount1), "en_US", currency=currency)
        formatted2 = currency_format(float(amount2), "en_US", currency=currency)

        # $ and £ are ambiguous - specify default_currency
        result1, errors1 = parse_currency(formatted1, "en_US", default_currency=currency)
        result2, errors2 = parse_currency(formatted2, "en_US", default_currency=currency)

        assert not errors1
        assert not errors2
        assert result1 is not None
        assert result2 is not None

        parsed1, _ = result1
        parsed2, _ = result2

        # Ordering must be preserved (with small tolerance for float precision)
        if amount1 < amount2 - Decimal("0.01"):
            assert parsed1 < parsed2
        elif amount1 > amount2 + Decimal("0.01"):
            assert parsed1 > parsed2
        # Skip equality check for very close values due to float precision

    @given(
        amount=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("999999.99"), places=2),
        locale1=st.sampled_from(["en_US", "de_DE", "lv_LV"]),
        locale2=st.sampled_from(["en_US", "de_DE", "lv_LV"]),
    )
    @settings(max_examples=100)
    def test_parse_currency_locale_format_independence(
        self, amount: Decimal, locale1: str, locale2: str
    ) -> None:
        """parse(format(x, L1), L1) == parse(format(x, L2), L2) for all locales."""
        from ftllexengine.runtime.functions import currency_format

        # Format in different locales
        formatted1 = currency_format(float(amount), locale1, currency="EUR")
        formatted2 = currency_format(float(amount), locale2, currency="EUR")

        # Parse with respective locales
        result1, errors1 = parse_currency(formatted1, locale1)
        result2, errors2 = parse_currency(formatted2, locale2)

        assert not errors1
        assert not errors2
        assert result1 is not None
        assert result2 is not None

        parsed1, code1 = result1
        parsed2, code2 = result2

        # Numeric value and currency code should be identical
        assert parsed1 == parsed2 == amount
        assert code1 == code2 == "EUR"

    @given(
        amount=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("999.99"), places=2),
    )
    @settings(max_examples=100)
    def test_parse_currency_addition_homomorphism(self, amount: Decimal) -> None:
        """parse(format(a)) + parse(format(a)) == parse(format(2*a)) (within precision)."""
        from ftllexengine.runtime.functions import currency_format

        formatted1 = currency_format(float(amount), "en_US", currency="USD")
        formatted2 = currency_format(float(amount * 2), "en_US", currency="USD")

        # $ is ambiguous - specify default_currency
        result1, errors1 = parse_currency(formatted1, "en_US", default_currency="USD")
        result2, errors2 = parse_currency(formatted2, "en_US", default_currency="USD")

        assert not errors1
        assert not errors2
        assert result1 is not None
        assert result2 is not None

        parsed1, _ = result1
        parsed2, _ = result2

        # Addition property (within Decimal precision)
        assert parsed1 + parsed1 == parsed2

    @given(
        amount=st.decimals(
            min_value=Decimal("1.00"),
            max_value=Decimal("9999999999.99"),
            places=2,
        ),
        currency=st.sampled_from(["EUR", "USD", "GBP", "INR"]),  # Exclude JPY (zero-decimal)
    )
    @settings(max_examples=100)
    def test_parse_currency_very_large_amounts(
        self, amount: Decimal, currency: str
    ) -> None:
        """Very large amounts should parse correctly (stress test)."""
        from ftllexengine.runtime.functions import currency_format

        formatted = currency_format(float(amount), "en_US", currency=currency)
        # $ and £ are ambiguous - specify default_currency
        result, errors = parse_currency(formatted, "en_US", default_currency=currency)

        assert not errors
        assert result is not None
        parsed_amount, parsed_currency = result

        # Large amounts must preserve precision (within 2 decimal places)
        assert abs(parsed_amount - amount) < Decimal("0.01")
        assert parsed_currency == currency

    @given(
        symbol=st.sampled_from(["€", "$", "£", "¥", "₹", "₽", "₪", "₫", "₱"]),
    )
    @settings(max_examples=50)
    def test_parse_currency_symbol_position_invariance(self, symbol: str) -> None:
        """Currency symbol position shouldn't affect parsing result."""
        # Test both prefix and suffix positions
        amount = Decimal("123.45")

        # Ambiguous symbols require default_currency
        ambiguous_symbols = {"$": "USD", "¢": "USD", "₨": "INR", "₱": "PHP"}
        default_currency = ambiguous_symbols.get(symbol)

        # Symbol before amount
        result1, _errors1 = parse_currency(
            f"{symbol}{amount}", "en_US", default_currency=default_currency
        )

        # Symbol after amount (common in some locales)
        result2, _errors2 = parse_currency(
            f"{amount} {symbol}", "en_US", default_currency=default_currency
        )

        # Both should parse to same amount (if they parse at all)
        if result1 is not None and result2 is not None:
            assert result1[0] == result2[0] == amount
            assert result1[1] == result2[1]  # Same currency code

    @given(
        amount=st.decimals(
            min_value=Decimal("0.00"),
            max_value=Decimal("0.00"),
        ),
    )
    @settings(max_examples=10)
    def test_parse_currency_zero_amount(self, amount: Decimal) -> None:  # noqa: ARG002
        """Zero amounts should parse correctly."""
        currency_str = "$0.00"

        result, errors = parse_currency(currency_str, "en_US", default_currency="USD")
        assert not errors
        assert result is not None

        parsed_amount, currency_code = result

        assert parsed_amount == Decimal("0.00")
        assert currency_code == "USD"

    @given(
        whitespace=st.text(
            alphabet=st.sampled_from([" ", "\t"]),
            min_size=0,
            max_size=3,
        ),
    )
    @settings(max_examples=50)
    def test_parse_currency_whitespace_tolerance(self, whitespace: str) -> None:
        """Currency parsing should tolerate whitespace."""
        # Add whitespace around currency and amount
        currency_str = f"{whitespace}€{whitespace}100.50{whitespace}"

        result, errors = parse_currency(currency_str, "en_US", default_currency="USD")

        assert not errors
        if result is not None:
            parsed_amount, currency_code = result
            assert parsed_amount == Decimal("100.50")
            assert currency_code == "EUR"


# ============================================================================
# COVERAGE TESTS - infer_from_locale PARAMETER
# ============================================================================


class TestCurrencyInferFromLocale:
    """Test infer_from_locale parameter for ambiguous symbols."""

    @given(
        amount=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("999999.99"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    @settings(max_examples=100)
    def test_infer_from_locale_with_us_dollar(self, amount: Decimal) -> None:
        """COVERAGE: infer_from_locale=True infers USD from en_US."""
        currency_str = f"${amount}"

        result, errors = parse_currency(currency_str, "en_US", infer_from_locale=True)
        assert not errors
        assert result is not None

        parsed_amount, currency_code = result
        assert currency_code == "USD"
        assert parsed_amount == amount

    @given(
        amount=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("999999.99"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    @settings(max_examples=100)
    def test_infer_from_locale_with_canadian_dollar(self, amount: Decimal) -> None:
        """COVERAGE: infer_from_locale=True infers CAD from en_CA."""
        currency_str = f"${amount}"

        result, errors = parse_currency(currency_str, "en_CA", infer_from_locale=True)
        assert not errors
        assert result is not None

        _parsed_amount, currency_code = result
        assert currency_code == "CAD"

    def test_infer_from_locale_uses_default_for_ambiguous(self) -> None:
        """COVERAGE: infer_from_locale with ambiguous symbol uses default.

        Ambiguous symbols now have defaults in _AMBIGUOUS_SYMBOL_DEFAULTS.
        When locale doesn't have a specific mapping, the default is used.
        """
        currency_str = "$100.00"

        # Use a locale without territory (just language code) - won't be in mapping
        # Now falls back to _AMBIGUOUS_SYMBOL_DEFAULTS["$"] = "USD"
        result, errors = parse_currency(
            currency_str, "en", infer_from_locale=True
        )
        assert len(errors) == 0
        assert result is not None
        assert result[1] == "USD"  # Falls back to default

    def test_ambiguous_symbol_no_default_returns_error(self) -> None:
        """COVERAGE: Ambiguous symbol without default returns error."""
        currency_str = "$100.00"

        # No default_currency, no infer_from_locale - should return error
        result, errors = parse_currency(currency_str, "en_US")
        assert len(errors) > 0
        assert result is None
