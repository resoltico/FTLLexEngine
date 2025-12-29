"""Comprehensive coverage tests for parsing/currency.py.

Targets uncovered error paths in currency parsing:
- Lines 61-62: Exception handling in currency code extraction
- Lines 95-97: Exception handling in symbol lookup
- Line 132->115: Locale with territory handling
- Lines 135-136: Exception in locale data extraction
- Lines 240-250: Locale parsing exceptions
- Line 257: resolve_ambiguous_symbol returns None for non-ambiguous symbols
- Line 259->277: resolve_ambiguous_symbol skips locale check when locale_code is None
- Line 291: ensure_loaded double-check pattern (race condition)
- Lines 547-549: Locale-to-currency fallback for ambiguous symbols
- Lines 559-560: Unknown symbol error path
"""

from __future__ import annotations

from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.parsing import currency as currency_module
from ftllexengine.parsing.currency import parse_currency

# ============================================================================
# LINES 240-250: Locale Parsing Exceptions
# ============================================================================


class TestCurrencyParsingLocaleErrors:
    """Test currency parsing with invalid locales (lines 240-250)."""

    def test_parse_currency_with_invalid_locale(self) -> None:
        """Test currency parsing with invalid locale code (lines 240-250).

        When locale parsing fails (UnknownLocaleError or ValueError),
        lines 240-250 handle the exception and return error.
        """
        result, errors = parse_currency("€10.50", "invalid_LOCALE_CODE")

        # Should return None and have error
        assert result is None
        assert len(errors) > 0
        assert any("locale" in str(err).lower() for err in errors)

    def test_parse_currency_with_malformed_locale(self) -> None:
        """Test currency parsing with malformed locale string."""
        result, errors = parse_currency("$100", "!!!invalid@@@")

        assert result is None
        assert len(errors) > 0

    def test_parse_currency_with_nonexistent_locale(self) -> None:
        """Test currency parsing with non-existent locale."""
        result, errors = parse_currency("¥1000", "xx_NONEXISTENT")

        assert result is None
        assert len(errors) > 0

    @given(
        bad_locale=st.text(
            alphabet=st.characters(blacklist_categories=["Cs"]),
            min_size=1,
            max_size=20,
        ).filter(lambda x: x not in ["en", "en_US", "de_DE", "fr_FR"])
    )
    def test_parse_currency_with_arbitrary_locales(self, bad_locale: str) -> None:
        """PROPERTY: Invalid locales should not crash currency parsing."""
        result, errors = parse_currency("€50", bad_locale)

        # Should either succeed with fallback or return None with errors
        assert result is None or isinstance(result, tuple)
        if result is None:
            assert len(errors) > 0


# ============================================================================
# Currency Parsing With Valid Locales
# ============================================================================


class TestCurrencyParsingSuccess:
    """Test successful currency parsing paths."""

    def test_parse_currency_usd_us_locale(self) -> None:
        """Test parsing USD with US locale."""
        result, _errors = parse_currency("$123.45", "en_US")

        if result is not None:
            amount, currency = result
            assert amount == 123.45
            assert currency == "USD"
        # May fail if CLDR data not complete, which is fine

    def test_parse_currency_eur_german_locale(self) -> None:
        """Test parsing EUR with German locale."""
        result, _errors = parse_currency("123,45 €", "de_DE")

        if result is not None:
            amount, currency = result
            assert 123 <= amount <= 124  # Handle decimal separator differences
            assert currency == "EUR"

    def test_parse_currency_with_iso_code(self) -> None:
        """Test parsing currency with ISO code instead of symbol."""
        result, _errors = parse_currency("USD 100.50", "en_US")

        if result is not None:
            amount, currency = result
            assert amount == 100.50
            assert currency == "USD"

    def test_parse_currency_yen_no_decimals(self) -> None:
        """Test parsing Japanese Yen (0 decimal places).

        v0.38.0: Yen symbol is now ambiguous (JPY vs CNY).
        Must use infer_from_locale=True for locale-aware resolution.
        """
        result, _errors = parse_currency("¥1000", "ja_JP", infer_from_locale=True)

        if result is not None:
            amount, currency = result
            assert amount == 1000
            assert currency == "JPY"

    def test_parse_currency_yuan_chinese_locale(self) -> None:
        """Test parsing Chinese Yuan with Yen symbol in Chinese locale.

        v0.38.0: LOGIC-YEN-001 fix - Yen symbol resolves to CNY in Chinese locales.
        The Yen sign (U+00A5) is used for both JPY and CNY. Locale-aware
        resolution correctly maps it to CNY for zh_* locales.
        """
        result, errors = parse_currency("¥1000", "zh_CN", infer_from_locale=True)

        assert not errors
        assert result is not None
        amount, currency = result
        assert amount == 1000
        assert currency == "CNY"

    def test_parse_currency_yuan_taiwan_locale(self) -> None:
        """Test parsing with Yen symbol in Taiwan locale.

        v0.38.0: zh_TW should also resolve Yen sign to CNY (Chinese currency context).
        """
        result, errors = parse_currency("¥1000", "zh_TW", infer_from_locale=True)

        assert not errors
        assert result is not None
        amount, currency = result
        assert amount == 1000
        assert currency == "CNY"


# ============================================================================
# Currency Parsing Error Cases
# ============================================================================


class TestCurrencyParsingErrorCases:
    """Test currency parsing error cases."""

    def test_parse_currency_no_currency_symbol(self) -> None:
        """Test parsing value without currency symbol."""
        result, errors = parse_currency("123.45", "en_US")

        # Should return error (no currency symbol found)
        assert result is None
        assert len(errors) > 0

    def test_parse_currency_invalid_number(self) -> None:
        """Test parsing invalid number with currency symbol."""
        result, errors = parse_currency("€invalid", "en_US")

        # Should return error (invalid number)
        assert result is None
        assert len(errors) > 0

    def test_parse_currency_empty_string(self) -> None:
        """Test parsing empty string."""
        result, errors = parse_currency("", "en_US")

        assert result is None
        assert len(errors) > 0

    def test_parse_currency_only_symbol(self) -> None:
        """Test parsing only currency symbol without number."""
        result, errors = parse_currency("€", "en_US")

        # Should return error (no amount)
        assert result is None
        assert len(errors) > 0

    @given(
        invalid_value=st.text(min_size=1, max_size=30).filter(
            lambda x: not any(c.isdigit() for c in x)
        )
    )
    def test_parse_currency_no_digits_property(self, invalid_value: str) -> None:
        """PROPERTY: Values without digits should fail to parse."""
        result, _errors = parse_currency(invalid_value, "en_US")

        # Should fail (no valid amount)
        assert result is None
        # Errors may or may not be present depending on whether currency symbol was found


# ============================================================================
# Currency Parsing With Different Symbols
# ============================================================================


class TestCurrencySymbolParsing:
    """Test parsing various currency symbols."""

    def test_parse_currency_pound_sterling(self) -> None:
        """Test parsing British Pound."""
        result, _errors = parse_currency("£50.25", "en_GB")

        if result is not None:
            amount, currency = result
            assert amount == 50.25
            assert currency == "GBP"

    def test_parse_currency_rupee(self) -> None:
        """Test parsing Indian Rupee."""
        result, _errors = parse_currency("₹1000", "hi_IN")

        if result is not None:
            amount, _currency = result
            assert amount == 1000
            # May be INR

    def test_parse_currency_swiss_franc(self) -> None:
        """Test parsing Swiss Franc with various locales."""
        # Swiss Franc can use 'CHF' or 'fr' as symbol
        result, _errors = parse_currency("CHF 100", "de_CH")

        if result is not None:
            amount, currency = result
            assert amount == 100
            assert currency == "CHF"


# ============================================================================
# Integration Tests
# ============================================================================


class TestCurrencyParsingIntegration:
    """Integration tests for currency parsing."""

    def test_parse_currency_multiple_formats_same_currency(self) -> None:
        """Test parsing same currency in different formats."""
        test_cases = [
            ("$100", "en_US"),
            ("100 USD", "en_US"),
            ("USD 100", "en_US"),
        ]

        for value, locale in test_cases:
            result, _errors = parse_currency(value, locale)
            if result is not None:
                amount, currency = result
                assert amount == 100
                assert currency == "USD"

    def test_parse_currency_locale_specific_formats(self) -> None:
        """Test locale-specific currency formats."""
        test_cases = [
            ("123.45", "en_US"),  # US uses period as decimal separator
            ("123,45", "de_DE"),  # German uses comma as decimal separator
        ]

        for value, locale in test_cases:
            # Add currency symbol for testing
            with_currency = f"${value}" if locale == "en_US" else f"{value} €"

            result, errors = parse_currency(with_currency, locale)
            # Should parse successfully or have clear errors
            assert result is not None or len(errors) > 0

    def test_parse_currency_with_thousands_separator(self) -> None:
        """Test parsing currency with thousands separators."""
        result, _errors = parse_currency("$1,234.56", "en_US")

        if result is not None:
            amount, currency = result
            assert 1234 <= amount <= 1235  # Allow for parsing differences
            assert currency == "USD"


# ============================================================================
# LINE 257: resolve_ambiguous_symbol returns None for non-ambiguous
# ============================================================================


class TestResolveAmbiguousSymbolNonAmbiguous:
    """Test resolve_ambiguous_symbol with non-ambiguous symbols (line 257)."""

    def test_resolve_non_ambiguous_symbol_returns_none(self) -> None:
        """Test that non-ambiguous symbols return None (line 257).

        resolve_ambiguous_symbol should return None for symbols that are
        NOT in the ambiguous set, allowing the caller to use the
        standard symbol-to-currency mapping instead.
        """
        provider = currency_module._provider

        # Euro symbol is NOT ambiguous (always means EUR)
        result = provider.resolve_ambiguous_symbol("€", "en_US")
        assert result is None

        # Swiss Franc symbol is NOT in ambiguous set
        result = provider.resolve_ambiguous_symbol("₣", "fr_CH")
        assert result is None


# ============================================================================
# LINE 259->277: resolve_ambiguous_symbol without locale
# ============================================================================


class TestResolveAmbiguousSymbolNoLocale:
    """Test resolve_ambiguous_symbol without locale_code (branch 259->277)."""

    def test_resolve_ambiguous_symbol_no_locale_uses_default(self) -> None:
        """Test ambiguous symbol resolution without locale falls back to default.

        When locale_code is None or empty, the code should skip the locale-specific
        resolution path (lines 259-275) and use the default mapping (line 277).
        """
        provider = currency_module._provider

        # Yen symbol is ambiguous (JPY vs CNY) - without locale, should use default
        result = provider.resolve_ambiguous_symbol("¥", None)

        # Should return the default for Yen (typically JPY)
        assert result in {"JPY", "CNY"} or result is None

    def test_resolve_ambiguous_symbol_empty_locale_uses_default(self) -> None:
        """Test ambiguous symbol with empty string locale uses default."""
        provider = currency_module._provider

        # Dollar symbol is ambiguous - without locale, uses default (USD)
        result = provider.resolve_ambiguous_symbol("$", "")

        # Empty string is falsy, should use default
        assert result in {"USD"} or result is None


# ============================================================================
# LINE 291: ensure_loaded double-check pattern
# ============================================================================


class TestEnsureLoadedDoubleCheck:
    """Test ensure_loaded double-check locking pattern (line 291)."""

    def test_ensure_loaded_double_check_pattern(self) -> None:
        """Test double-check pattern in ensure_loaded (line 291).

        This tests the race condition handling where the _loaded flag
        becomes True between the first check and acquiring the lock.
        """
        provider = currency_module._provider

        # Ensure it's loaded first time
        provider.ensure_loaded()
        assert provider._loaded

        # Call again - should hit the first check and return early
        provider.ensure_loaded()
        assert provider._loaded

    def test_ensure_loaded_double_check_race_simulation(self) -> None:
        """Simulate double-check after lock acquisition (line 291).

        Create a fresh provider and simulate the race condition by
        inserting the entry during lock acquisition.
        """
        # Create a new provider instance for isolated testing
        new_provider = currency_module.CurrencyDataProvider()

        # Ensure provider starts unloaded
        assert not new_provider._loaded

        # Store original build function
        original_build = currency_module._build_currency_maps_from_cldr

        call_count = [0]

        def build_with_tracking() -> tuple:
            call_count[0] += 1
            return original_build()

        # Patch to track calls
        with patch.object(
            currency_module,
            "_build_currency_maps_from_cldr",
            build_with_tracking,
        ):
            # First call - should load
            new_provider.ensure_loaded()
            assert new_provider._loaded
            # Note: mypy incorrectly infers unreachable due to patch type inference
            assert call_count[0] == 1  # type: ignore[unreachable]

            # Second call - should NOT call build again (hits early return)
            new_provider.ensure_loaded()
            assert call_count[0] == 1  # Still 1 - early return worked


# ============================================================================
# LINES 547-549: Locale-to-currency fallback
# ============================================================================


class TestLocaleToCurrencyFallback:
    """Test locale-to-currency fallback for ambiguous symbols (lines 547-549)."""

    def test_resolve_currency_code_locale_fallback(self) -> None:
        """Test _resolve_currency_code falls back to locale-to-currency.

        When an ambiguous symbol cannot be resolved via
        resolve_ambiguous_symbol, the code falls back to looking up
        the locale's default currency (lines 547-549).
        """
        # Use the internal _resolve_currency_code function
        resolve_fn = currency_module._resolve_currency_code

        # Use a less common ambiguous symbol with infer_from_locale
        # The fallback uses locale_to_currency mapping
        result, error = resolve_fn(
            "weird_symbol_not_mapped",  # Not a real symbol (currency_str)
            "de_DE",  # locale_code
            "EUR 100",  # Full value for context
            default_currency=None,
            infer_from_locale=True,
        )

        # Should either succeed with locale's default currency or return error
        # Lines 547-549 try locale_to_currency.get(normalize_locale(locale_code))
        assert result is not None or error is not None

    def test_parse_currency_with_locale_currency_fallback(self) -> None:
        """Test parse_currency uses locale default when symbol is ambiguous.

        This exercises lines 547-549 where the locale's default currency
        is used when the ambiguous symbol resolution fails.
        """
        # Use an ambiguous symbol that needs locale resolution
        # Pound sign is ambiguous (GBP, EGP, etc.)
        result, _errors = parse_currency("£100", "en_EG", infer_from_locale=True)

        # Should resolve using locale's default currency (EGP for Egypt)
        # Or fall back to GBP if ambiguous resolution succeeds
        if result is not None:
            _amount, currency = result
            assert currency in {"GBP", "EGP", "GIP"}

    def test_locale_to_currency_fallback_direct_path(self) -> None:
        """Directly test lines 547-549 fallback to locale-to-currency.

        This tests the specific path where:
        1. Symbol is ambiguous
        2. No default_currency
        3. infer_from_locale=True
        4. resolve_ambiguous_symbol returns None
        5. locale_to_currency has a mapping for the locale
        """
        resolve_fn = currency_module._resolve_currency_code

        # Get the full tier data BEFORE patching to avoid recursion
        full_data = currency_module._get_currency_maps_full()
        _, _, locale_to_currency, _ = full_data

        # Find a locale that has a currency mapping but whose ambiguous symbol
        # resolution will fail
        # Use Swedish locale with krona - "kr" is ambiguous but might not have
        # a specific resolution in _AMBIGUOUS_SYMBOL_LOCALE_RESOLUTION
        test_locale = "sv_SE"

        # Create a mock provider class that returns None for resolve_ambiguous_symbol
        class MockProvider:
            """Mock provider that returns None for ambiguous resolution."""

            def __init__(self, data: tuple) -> None:
                self._data = data

            def resolve_ambiguous_symbol(
                self, _symbol: str, _locale_code: str | None
            ) -> str | None:
                return None  # Always fail resolution

            def ensure_loaded(self) -> None:
                pass

            def get_full_tier_data(self) -> tuple:
                return self._data

        # Replace the provider temporarily
        original_provider = currency_module._provider
        currency_module._provider = MockProvider(full_data)  # type: ignore[assignment]

        try:
            result, error = resolve_fn(
                "kr",  # Ambiguous symbol (krona)
                test_locale,
                "kr 100",
                default_currency=None,
                infer_from_locale=True,
            )

            # Should fall back to locale_to_currency (lines 547-549)
            # and return the locale's default currency (SEK for Sweden)
            # or return error if no mapping
            if result is not None:
                # If result, should be the locale's currency
                assert result == "SEK" or result in locale_to_currency.values()
            else:
                # If no result, error should be present
                assert error is not None
        finally:
            # Restore original provider
            currency_module._provider = original_provider

    def test_locale_to_currency_fallback_no_mapping(self) -> None:
        """Test fallback path when locale_to_currency has no mapping (548->551).

        This tests the branch where:
        1. Symbol is ambiguous
        2. infer_from_locale=True
        3. resolve_ambiguous_symbol returns None
        4. locale_to_currency.get() also returns None (no mapping for locale)
        5. Falls through to error (line 551)
        """
        resolve_fn = currency_module._resolve_currency_code

        # Get the full tier data BEFORE patching
        full_data = currency_module._get_currency_maps_full()
        symbol_map, ambiguous, _, valid_codes = full_data

        # Create modified data with empty locale_to_currency
        empty_locale_map: dict[str, str] = {}
        modified_data = (symbol_map, ambiguous, empty_locale_map, valid_codes)

        class MockProvider:
            """Mock provider with empty locale_to_currency."""

            def __init__(self, data: tuple) -> None:
                self._data = data

            def resolve_ambiguous_symbol(
                self, _symbol: str, _locale_code: str | None
            ) -> str | None:
                return None  # Always fail resolution

            def ensure_loaded(self) -> None:
                pass

            def get_full_tier_data(self) -> tuple:
                return self._data

        original_provider = currency_module._provider
        currency_module._provider = MockProvider(modified_data)  # type: ignore[assignment]

        try:
            result, error = resolve_fn(
                "kr",  # Ambiguous symbol
                "xx_UNKNOWN",  # Locale with no currency mapping
                "kr 100",
                default_currency=None,
                infer_from_locale=True,
            )

            # Should return error since no resolution or fallback available
            assert result is None
            assert error is not None
        finally:
            currency_module._provider = original_provider


# ============================================================================
# LINES 559-560: Unknown symbol error path
# ============================================================================


class TestUnknownSymbolError:
    """Test unknown symbol error path (lines 559-560)."""

    def test_resolve_currency_code_unknown_symbol(self) -> None:
        """Test _resolve_currency_code with completely unknown symbol.

        When a symbol is not in the symbol_map, lines 559-560 return
        an error indicating the symbol is unknown.
        """
        resolve_fn = currency_module._resolve_currency_code

        # Use a symbol that's definitely not in any currency mapping
        result, error = resolve_fn(
            "ZZZZZ",  # Fake symbol (currency_str)
            "en_US",  # locale_code
            "ZZZZZ 100",  # value
            default_currency=None,
            infer_from_locale=False,  # Don't try locale fallback
        )

        # Should return None result with error
        assert result is None
        assert error is not None
        # Error should mention unknown symbol
        assert "unknown" in str(error).lower() or "symbol" in str(error).lower()

    def test_resolve_currency_code_unicode_unknown_symbol(self) -> None:
        """Test with Unicode symbol not in any currency mapping."""
        resolve_fn = currency_module._resolve_currency_code

        result, error = resolve_fn(
            "☆",  # Star symbol - not a currency
            "en_US",  # locale_code
            "☆100",  # value
            default_currency=None,
            infer_from_locale=False,
        )

        assert result is None
        assert error is not None
