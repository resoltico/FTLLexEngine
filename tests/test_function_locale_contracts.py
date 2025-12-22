"""Contract tests: FluentBundle output must match direct function output.

These tests ensure that functions called through FluentBundle produce
identical results to direct function calls with the same locale.

This catches bugs like resolver.py locale injection failures.

Architecture:
    - Ground Truth: Direct function calls (e.g., currency_format())
    - System Under Test: FluentBundle with FTL messages
    - Contract: Outputs must match exactly

Why These Tests Matter:
    - Unit tests verify functions work in isolation
    - Integration tests verify FluentBundle works
    - Contract tests verify the integration layer passes locale correctly

This test suite would have caught the CURRENCY() locale bug immediately.
"""

from datetime import UTC, datetime
from typing import Literal, cast

import pytest

from ftllexengine import FluentBundle
from ftllexengine.runtime.functions import currency_format, datetime_format, number_format

# Test locale set - representative sample of supported locales
# Babel supports 200+ locales; these are common ones for testing
TEST_LOCALES: frozenset[str] = frozenset({
    "en", "zh", "hi", "es", "fr", "ar", "bn", "pt", "ru", "ja",
    "de", "jv", "ko", "vi", "te", "tr", "ta", "mr", "ur", "it",
    "th", "gu", "pl", "uk", "kn", "or", "ml", "my", "pa", "lv",
})


class TestNumberLocaleContract:
    """NUMBER() in FluentBundle must match direct number_format() output.

    Contract: For any locale and value, NUMBER($val) in FluentBundle must
    produce the same output as number_format(val, locale).
    """

    @pytest.mark.parametrize("locale", TEST_LOCALES)
    @pytest.mark.parametrize("value", [0, 1.5, 123.45, 1234567.89, -42])
    def test_number_basic_contract(self, locale: str, value: int | float) -> None:
        """NUMBER() respects bundle locale (contract test)."""
        # Ground truth: Direct function call
        expected = number_format(value, locale)

        # System under test: FluentBundle (disable BIDI for fair comparison)
        bundle = FluentBundle(locale, use_isolating=False)
        bundle.add_resource("num = { NUMBER($val) }")
        actual, errors = bundle.format_pattern("num", {"val": value})

        # Contract: Exact match required
        assert actual == expected, (
            f"Locale {locale}, value {value}: "
            f"FluentBundle='{actual}' != Direct='{expected}'"
        )
        assert len(errors) == 0

    @pytest.mark.parametrize("locale", ["en-US", "de-DE", "lv-LV", "ja-JP"])
    def test_number_with_fraction_digits_contract(self, locale: str) -> None:
        """NUMBER() with minimumFractionDigits respects locale."""
        value = 42.1
        expected = number_format(value, locale, minimum_fraction_digits=3)

        bundle = FluentBundle(locale, use_isolating=False)
        bundle.add_resource("num = { NUMBER($val, minimumFractionDigits: 3) }")
        actual, errors = bundle.format_pattern("num", {"val": value})

        assert actual == expected
        assert len(errors) == 0


class TestCurrencyLocaleContract:
    """CURRENCY() in FluentBundle must match direct currency_format() output.

    Contract: For any locale, currency, and amount, CURRENCY() in FluentBundle
    must produce the same output as currency_format(amount, locale, currency=...).

    This is the test that would have caught the CURRENCY() locale bug!
    """

    @pytest.mark.parametrize("locale", ["en-US", "lv-LV", "de-DE", "ja-JP", "ar-SA"])
    @pytest.mark.parametrize("currency", ["EUR", "USD", "GBP", "JPY"])
    @pytest.mark.parametrize("amount", [0, 1.5, 123.45, 9999.99])
    def test_currency_locale_contract(
        self, locale: str, currency: str, amount: int | float
    ) -> None:
        """CURRENCY() respects bundle locale (contract test).

        This test FAILS before the resolver.py fix and PASSES after.
        """
        # Ground truth: Direct function call
        expected = currency_format(amount, locale, currency=currency)

        # System under test: FluentBundle (disable BIDI for fair comparison)
        bundle = FluentBundle(locale, use_isolating=False)
        bundle.add_resource(f'price = {{ CURRENCY($amt, currency: "{currency}") }}')
        actual, errors = bundle.format_pattern("price", {"amt": amount})

        # Contract: Exact match required
        assert actual == expected, (
            f"Locale {locale}, {currency} {amount}: "
            f"FluentBundle='{actual}' != Direct='{expected}'"
        )
        assert len(errors) == 0

    @pytest.mark.parametrize("locale", ["en-US", "de-DE", "lv-LV"])
    def test_currency_display_modes_contract(self, locale: str) -> None:
        """CURRENCY() currencyDisplay parameter respects locale."""
        amount = 100.0

        for display_mode in ["symbol", "code", "name"]:
            # Ground truth
            expected = currency_format(
                amount,
                locale,
                currency="EUR",
                currency_display=cast(Literal["symbol", "code", "name"], display_mode),
            )

            # System under test (disable BIDI for fair comparison)
            bundle = FluentBundle(locale, use_isolating=False)
            bundle.add_resource(
                f'price = {{ CURRENCY($amt, currency: "EUR", currencyDisplay: "{display_mode}") }}'
            )
            actual, errors = bundle.format_pattern("price", {"amt": amount})

            # Contract
            assert actual == expected, (
                f"Locale {locale}, display={display_mode}: "
                f"FluentBundle='{actual}' != Direct='{expected}'"
            )
            assert len(errors) == 0


class TestDateTimeLocaleContract:
    """DATETIME() in FluentBundle must match direct datetime_format() output.

    Contract: For any locale and date style, DATETIME() in FluentBundle must
    produce the same output as datetime_format(dt, locale, date_style=...).
    """

    @pytest.mark.parametrize("locale", TEST_LOCALES)
    @pytest.mark.parametrize("date_style", ["short", "medium", "long", "full"])
    def test_datetime_locale_contract(self, locale: str, date_style: str) -> None:
        """DATETIME() respects bundle locale (contract test)."""
        dt = datetime(2025, 12, 2, 14, 30, tzinfo=UTC)

        # Ground truth
        expected = datetime_format(
            dt, locale, date_style=cast(Literal["short", "medium", "long", "full"], date_style)
        )

        # System under test (disable BIDI for fair comparison)
        bundle = FluentBundle(locale, use_isolating=False)
        bundle.add_resource(f'when = {{ DATETIME($dt, dateStyle: "{date_style}") }}')
        actual, errors = bundle.format_pattern("when", {"dt": dt})

        # Contract
        assert actual == expected, (
            f"Locale {locale}, dateStyle={date_style}: "
            f"FluentBundle='{actual}' != Direct='{expected}'"
        )
        assert len(errors) == 0


class TestContractTestMetaValidation:
    """Meta-tests: Verify contract tests would catch locale injection bugs."""

    def test_contract_would_catch_currency_bug(self) -> None:
        """Verify contract test catches CURRENCY() locale bug.

        This test demonstrates that the contract testing approach WOULD have
        caught the resolver.py locale injection bug before it shipped.

        If resolver.py:307 didn't include "CURRENCY", this test would fail.
        """
        # Test case that would fail with the bug
        locale = "lv-LV"  # Latvian locale
        amount = 123.45
        currency = "EUR"

        # Ground truth: Latvian format has symbol AFTER amount with space
        expected = currency_format(amount, locale, currency=currency)
        # Expected format: "123,45 €" (comma separator, symbol after)

        # System under test (disable BIDI for fair comparison)
        bundle = FluentBundle(locale, use_isolating=False)
        bundle.add_resource('price = { CURRENCY($amt, currency: "EUR") }')
        actual, errors = bundle.format_pattern("price", {"amt": amount})

        # This assertion FAILS if CURRENCY not in resolver.py:307
        # It PASSES after the fix
        assert actual == expected, (
            f"CURRENCY() locale bug detected! "
            f"Expected Latvian format '{expected}', got '{actual}'"
        )
        assert len(errors) == 0

        # Verify we actually got the Latvian format, not US format
        assert "€" in actual  # Symbol present
        assert "," in actual or "45" in actual  # Latvian uses comma separator
        # US format would be: "€123.45" (symbol before, period separator)
        # Latvian format is: "123,45 €" (symbol after, comma separator)
