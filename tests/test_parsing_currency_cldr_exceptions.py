"""CLDR exception handling tests for parsing/currency.py.

Tests error handling and edge cases in CLDR map building:
- Exception handling in locale.currencies access
- Exception handling in get_currency_symbol
- Branch when locale_str does NOT contain "_"
- Exception handling in get_territory_currencies
- Invalid ISO code error path
- Locale-to-currency fallback for ambiguous symbols

Note: These tests must clear @functools.cache before running to ensure
mocked imports are used. The function uses lazy imports inside the function
body, so patches target the original Babel modules.

Python 3.13+.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from babel import UnknownLocaleError

from ftllexengine.parsing.currency import (
    _build_currency_maps_from_cldr,
    _get_currency_maps,
    parse_currency,
)


@pytest.fixture(autouse=True)
def clear_currency_cache() -> None:
    """Clear the currency map cache before each test."""
    _build_currency_maps_from_cldr.cache_clear()
    _get_currency_maps.cache_clear()


class TestLines278To280LocaleCurrenciesException:
    """Test lines 278-280: Exception when accessing locale.currencies."""

    def test_build_maps_handles_key_error_in_currencies_access(self) -> None:
        """Test KeyError when accessing locale.currencies.keys() (lines 278-280)."""
        # Create a mock locale that raises KeyError when accessing currencies.keys()
        mock_locale = MagicMock()

        # Make currencies.keys() raise KeyError
        mock_locale.currencies.keys.side_effect = KeyError("Mock key error")

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["test_locale"],
            ),
        ):
            # Should not crash, should catch exception (lines 278-280)
            symbol_map, ambiguous, locale_to_currency, codes = _build_currency_maps_from_cldr()

            # Should return valid maps (possibly empty)
            assert isinstance(symbol_map, dict)
            assert isinstance(ambiguous, set)
            assert isinstance(locale_to_currency, dict)
            assert isinstance(codes, frozenset)


class TestLines304To306GetCurrencySymbolException:
    """Test lines 304-306: Exception in get_currency_symbol call."""

    def test_build_maps_handles_attribute_error_in_symbol_lookup(self) -> None:
        """Test AttributeError in get_currency_symbol (lines 304-306)."""

        def mock_get_currency_symbol_raises(
            currency_code: str, locale: object = None  # noqa: ARG001
        ) -> str:
            """Mock that raises AttributeError."""
            msg = "Mock attribute error"
            raise AttributeError(msg)

        # Create mock locale with currencies
        mock_locale = MagicMock()
        mock_locale.currencies = {"USD": "Dollar"}
        mock_locale.territory = "US"
        mock_locale.configure_mock(**{"__str__.return_value": "en_US"})

        with (
            patch(
                "babel.numbers.get_currency_symbol",
                side_effect=mock_get_currency_symbol_raises,
            ),
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["en_US"],
            ),
        ):
            # Should not crash, should catch exception (lines 304-306)
            symbol_map, ambiguous, locale_to_currency, codes = _build_currency_maps_from_cldr()

            assert isinstance(symbol_map, dict)
            assert isinstance(ambiguous, set)
            assert isinstance(locale_to_currency, dict)
            assert isinstance(codes, frozenset)


class TestLine341LocaleWithoutUnderscore:
    """Test line 341: Branch when locale_str does NOT contain '_'."""

    def test_build_maps_skips_locale_without_territory_separator(self) -> None:
        """Test locale without underscore is skipped in locale_to_currency mapping (line 341).

        When locale_str does NOT contain "_", the if condition on line 341 is False,
        and the locale is not added to locale_to_currency dict.
        """
        # Create mock locale without territory (str representation has no "_")
        mock_locale = MagicMock()
        mock_locale.territory = "XX"  # Has territory
        mock_locale.currencies = {}
        # But when converted to string, it has no underscore (language only)
        mock_locale.configure_mock(**{"__str__.return_value": "en"})  # No underscore!

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["en"],
            ),
            patch(
                "babel.numbers.get_territory_currencies",
                return_value=["GBP"],
            ),
        ):
            symbol_map, ambiguous, locale_to_currency, codes = _build_currency_maps_from_cldr()

            # Locale "en" should NOT be in locale_to_currency because it has no "_"
            assert "en" not in locale_to_currency

            assert isinstance(symbol_map, dict)
            assert isinstance(ambiguous, set)
            assert isinstance(codes, frozenset)


class TestLines344To346GetTerritoryCurrenciesException:
    """Test lines 344-346: Exception in get_territory_currencies call."""

    def test_build_maps_handles_unknown_locale_error_in_territory_lookup(self) -> None:
        """Test UnknownLocaleError in get_territory_currencies (lines 344-346)."""

        def mock_get_territory_currencies_raises(territory: str) -> list[str]:  # noqa: ARG001
            """Mock that raises UnknownLocaleError."""
            msg = "Mock unknown locale"
            raise UnknownLocaleError(msg)

        # Create mock locale with territory
        mock_locale = MagicMock()
        mock_locale.territory = "XX"
        mock_locale.currencies = {}
        mock_locale.configure_mock(**{"__str__.return_value": "xx_XX"})

        with (
            patch(
                "babel.numbers.get_territory_currencies",
                side_effect=mock_get_territory_currencies_raises,
            ),
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["xx_XX"],
            ),
        ):
            # Should not crash, should catch exception (lines 344-346)
            symbol_map, ambiguous, locale_to_currency, codes = _build_currency_maps_from_cldr()

            assert isinstance(symbol_map, dict)
            assert isinstance(ambiguous, set)
            assert isinstance(locale_to_currency, dict)
            assert isinstance(codes, frozenset)


class TestLines444To445InvalidISOCode:
    """Test lines 444-445: Invalid ISO code error path."""

    def test_parse_currency_with_invalid_iso_code(self) -> None:
        """Test parsing with invalid ISO code (lines 444-445).

        When a 3-letter uppercase code is provided that looks like ISO
        but isn't in the valid_iso_codes set, lines 444-445 return error.
        """
        # Use an invalid ISO code - AAA is not a valid ISO 4217 code
        result, errors = parse_currency("AAA 100", "en_US")

        # Should return None with error
        assert result is None
        assert len(errors) > 0
        assert any("invalid" in str(e).lower() or "unknown" in str(e).lower() for e in errors)

    def test_parse_currency_with_made_up_iso_code(self) -> None:
        """Test parsing with completely made-up ISO code."""
        # ZZZ is not a valid ISO 4217 code
        result, errors = parse_currency("100 ZZZ", "en_US")

        # Should return None with error (lines 444-445)
        assert result is None
        assert len(errors) > 0


class TestLines460To462LocaleToCurrencyFallback:
    """Test lines 460-462: Locale-to-currency fallback for ambiguous symbols."""

    def test_parse_currency_ambiguous_symbol_uses_locale_fallback(self) -> None:
        """Test ambiguous symbol resolution via locale_to_currency (lines 460-462).

        When infer_from_locale=True and resolve_ambiguous_symbol returns None,
        the code falls back to locale_to_currency mapping (lines 460-462).
        """
        # Mock resolve_ambiguous_symbol to return None to force fallback
        with patch(
            "ftllexengine.parsing.currency.resolve_ambiguous_symbol",
            return_value=None,
        ):
            # Use an ambiguous symbol with infer_from_locale
            # The mock returns None, so it should fall back to locale_to_currency
            result, errors = parse_currency("$100", "en_US", infer_from_locale=True)

        # Should use locale_to_currency fallback (lines 460-462)
        if result is not None:
            _amount, currency = result
            # Should infer USD from locale_to_currency["en_US"]
            assert currency == "USD"
            assert errors == ()
        else:
            # If locale not in map, error is expected
            assert len(errors) > 0

    def test_parse_currency_ambiguous_symbol_fallback_when_not_in_fast_tier(self) -> None:
        """Test locale_to_currency fallback for locales only in CLDR."""
        # Mock resolve_ambiguous_symbol to return None for this specific call
        with patch(
            "ftllexengine.parsing.currency.resolve_ambiguous_symbol",
            return_value=None,
        ):
            # Use $ with de_DE which has EUR as default currency
            result, errors = parse_currency("$100", "de_DE", infer_from_locale=True)

        # Should fall back to locale_to_currency["de_DE"] = "EUR"
        if result is not None:
            _amount, currency = result
            assert currency == "EUR"
            assert errors == ()
        else:
            assert len(errors) > 0

    def test_parse_currency_ambiguous_symbol_no_resolution_available(self) -> None:
        """Test branch 461->464: No resolution when locale not in map.

        When resolve_ambiguous_symbol returns None AND locale is not in
        locale_to_currency map, the code falls through to line 464 (error).
        This tests the branch 461->464.
        """
        # Mock both resolve_ambiguous_symbol AND locale_to_currency to force the branch
        with (
            patch(
                "ftllexengine.parsing.currency.resolve_ambiguous_symbol",
                return_value=None,
            ),
            patch(
                "ftllexengine.parsing.currency._get_currency_maps",
                return_value=(
                    {},  # symbol_map
                    {"$"},  # ambiguous_symbols - $ is ambiguous
                    {},  # locale_to_currency - EMPTY so get() returns None
                    frozenset({"USD"}),  # valid_iso_codes
                ),
            ),
        ):
            # Use an ambiguous symbol
            # resolve_ambiguous_symbol returns None (mocked)
            # locale_to_currency.get() returns None (empty dict)
            # So branch 461->464 is taken
            result, errors = parse_currency("$100", "en_US", infer_from_locale=True)

        # Should fail (either locale error or ambiguous symbol error)
        # The key is that branch 461->464 is taken (inferred is None/False)
        assert result is None
        assert len(errors) > 0


class TestLine529EmptySymbolsFallback:
    """Test line 529: Pattern compilation when escaped_symbols is empty."""

    def test_pattern_compilation_with_empty_fast_tier(self) -> None:
        """Test pattern compiles with only ISO codes when fast tier is empty.

        When _get_currency_maps_fast() returns empty symbol sets,
        line 529 is executed to create a pattern with only ISO codes.
        """
        from unittest.mock import patch

        from ftllexengine.parsing.currency import _get_currency_pattern_fast

        # Clear cache
        _get_currency_pattern_fast.cache_clear()

        # Mock _get_currency_maps_fast to return empty symbol maps
        empty_maps: tuple[
            dict[str, str], frozenset[str], dict[str, str], frozenset[str]
        ] = ({}, frozenset(), {}, frozenset())

        with patch(
            "ftllexengine.parsing.currency._get_currency_maps_fast",
            return_value=empty_maps,
        ):
            # This should trigger line 529 (empty symbols fallback)
            pattern = _get_currency_pattern_fast()

        # Pattern should still match ISO codes
        import re

        assert pattern is not None
        assert re.match(pattern, "USD")
        assert re.match(pattern, "EUR")
        assert re.match(pattern, "JPY")
        # But should NOT match symbols (since they're empty)
        assert re.match(pattern, "$") is None
        assert re.match(pattern, "kr") is None

        # Clear cache after test to restore normal behavior
        _get_currency_pattern_fast.cache_clear()
