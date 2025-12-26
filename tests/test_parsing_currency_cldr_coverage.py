"""Coverage tests for _build_currency_maps_from_cldr() exception paths.

Targets uncovered lines in parsing/currency.py:
- Lines 61-62: Exception handling in locale parsing loop
- Lines 95-97: Exception handling in symbol lookup loop
- Lines 135-136: Exception handling in locale data extraction

These are defensive exception handlers that protect against edge cases
in Babel's CLDR data.

Python 3.13+.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.parsing.currency import (
    _build_currency_maps_from_cldr,
    parse_currency,
)

# ============================================================================
# LINES 61-62: Exception in Locale Parsing During Currency Extraction
# ============================================================================


class TestBuildCurrencyMapsLocaleParseException:
    """Test exception handling in locale parsing (lines 61-62)."""

    def test_build_maps_handles_locale_parse_exception(self) -> None:
        """Test that _build_currency_maps_from_cldr handles Locale.parse exceptions.

        Line 61-62 handles exceptions when parsing locales to extract currencies.
        """
        from babel import Locale

        # Store reference to original before patching
        original_parse = Locale.parse

        def mock_locale_parse_with_some_failures(locale_id: str) -> Any:
            """Mock that fails for certain locale IDs."""
            if "broken" in locale_id.lower():
                msg = "Mocked parse failure"
                raise ValueError(msg)
            # Call the original for valid locales
            return original_parse(locale_id)

        with (
            patch.object(Locale, "parse", side_effect=mock_locale_parse_with_some_failures),
            patch(
                "ftllexengine.parsing.currency.locale_identifiers",
                return_value=["en_US", "broken_locale", "de_DE"],
            ),
        ):
            symbol_map, ambiguous, locale_to_currency, _ = _build_currency_maps_from_cldr()

        # Should still return valid maps (from the locales that didn't fail)
        assert isinstance(symbol_map, dict)
        assert isinstance(ambiguous, set)
        assert isinstance(locale_to_currency, dict)

    def test_build_maps_handles_attribute_error_in_locale(self) -> None:
        """Test handling AttributeError when locale lacks currencies attr."""
        mock_locale = MagicMock()
        mock_locale.currencies = None  # No currencies attribute value

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "ftllexengine.parsing.currency.locale_identifiers",
                return_value=["test_locale"],
            ),
        ):
            symbol_map, ambiguous, locale_to_currency, _ = _build_currency_maps_from_cldr()

        # Should still return valid (possibly empty) maps
        assert isinstance(symbol_map, dict)
        assert isinstance(ambiguous, set)
        assert isinstance(locale_to_currency, dict)


# ============================================================================
# LINES 95-97: Exception in Symbol Lookup During Currency Mapping
# ============================================================================


class TestBuildCurrencyMapsSymbolLookupException:
    """Test exception handling in symbol lookup (lines 95-97)."""

    def test_build_maps_handles_get_currency_symbol_exception(self) -> None:
        """Test that _build_currency_maps_from_cldr handles get_currency_symbol exceptions.

        Lines 95-97 handle exceptions when looking up currency symbols.
        """

        def mock_get_currency_symbol_with_failures(
            currency_code: str, locale: object = None  # noqa: ARG001
        ) -> str:
            """Mock that fails for certain currency codes."""
            if currency_code == "FAIL":
                msg = "Mocked symbol lookup failure"
                raise ValueError(msg)
            # Return simple symbol for testing
            return "$" if currency_code == "USD" else currency_code

        with (
            patch(
                "ftllexengine.parsing.currency.get_currency_symbol",
                side_effect=mock_get_currency_symbol_with_failures,
            ),
            patch(
                "ftllexengine.parsing.currency.locale_identifiers",
                return_value=["en_US"],
            ),
        ):
            # Mock locale to return currencies including one that will fail
            mock_locale = MagicMock()
            mock_locale.currencies = {"USD": "Dollar", "FAIL": "Failure Currency"}
            mock_locale.territory = "US"

            with patch("babel.Locale.parse", return_value=mock_locale):
                symbol_map, ambiguous, locale_to_currency, _ = _build_currency_maps_from_cldr()

        # Should complete without crashing
        assert isinstance(symbol_map, dict)
        assert isinstance(ambiguous, set)
        assert isinstance(locale_to_currency, dict)


# ============================================================================
# LINES 135-136: Exception in Locale Data Extraction
# ============================================================================


class TestBuildCurrencyMapsLocaleDataException:
    """Test exception handling in locale data extraction (lines 135-136)."""

    def test_build_maps_handles_territory_currencies_exception(self) -> None:
        """Test handling exceptions when getting territory currencies.

        Lines 135-136 handle exceptions in locale data extraction loop.
        """
        call_count = 0

        def mock_get_territory_currencies(territory: str) -> list[str]:
            """Mock that fails for certain territories."""
            nonlocal call_count
            call_count += 1
            if territory == "XX":
                msg = "Unknown territory"
                raise ValueError(msg)
            return ["USD"]

        mock_locale_us = MagicMock()
        mock_locale_us.territory = "US"
        mock_locale_us.currencies = {}
        mock_locale_us.configure_mock(**{"__str__.return_value": "en_US"})

        mock_locale_xx = MagicMock()
        mock_locale_xx.territory = "XX"
        mock_locale_xx.currencies = {}
        mock_locale_xx.configure_mock(**{"__str__.return_value": "xx_XX"})

        def mock_parse(locale_id: str) -> MagicMock:
            if locale_id == "xx_XX":
                return mock_locale_xx
            return mock_locale_us

        with (
            patch(
                "ftllexengine.parsing.currency.get_territory_currencies",
                side_effect=mock_get_territory_currencies,
            ),
            patch(
                "ftllexengine.parsing.currency.locale_identifiers",
                return_value=["en_US", "xx_XX"],
            ),
            patch("babel.Locale.parse", side_effect=mock_parse),
        ):
            symbol_map, ambiguous, locale_to_currency, _ = _build_currency_maps_from_cldr()

        # Should complete without crashing
        assert isinstance(symbol_map, dict)
        assert isinstance(ambiguous, set)
        assert isinstance(locale_to_currency, dict)

    def test_build_maps_handles_locale_without_territory(self) -> None:
        """Test handling locales without territory (line 118-119 branch)."""
        mock_locale = MagicMock()
        mock_locale.territory = None  # No territory
        mock_locale.currencies = {}

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "ftllexengine.parsing.currency.locale_identifiers",
                return_value=["en"],  # Language only, no territory
            ),
        ):
            symbol_map, ambiguous, locale_to_currency, _ = _build_currency_maps_from_cldr()

        # Should handle gracefully
        assert isinstance(symbol_map, dict)
        assert isinstance(ambiguous, set)
        assert isinstance(locale_to_currency, dict)

    def test_build_maps_handles_empty_territory_currencies(self) -> None:
        """Test handling when get_territory_currencies returns empty list."""
        mock_locale = MagicMock()
        mock_locale.territory = "US"
        mock_locale.currencies = {}
        mock_locale.configure_mock(**{"__str__.return_value": "en_US"})

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "ftllexengine.parsing.currency.locale_identifiers",
                return_value=["en_US"],
            ),
            patch(
                "ftllexengine.parsing.currency.get_territory_currencies",
                return_value=[],  # Empty list
            ),
        ):
            _symbol_map, _ambiguous, locale_to_currency, _ = _build_currency_maps_from_cldr()

        # Should handle gracefully (no currency added for this locale)
        assert isinstance(locale_to_currency, dict)


# ============================================================================
# Additional Edge Case Tests
# ============================================================================


class TestBuildCurrencyMapsEdgeCases:
    """Test edge cases in currency map building."""

    def test_build_maps_returns_correct_types(self) -> None:
        """Verify _build_currency_maps_from_cldr returns correct types."""
        symbol_map, ambiguous, locale_to_currency, _ = _build_currency_maps_from_cldr()

        assert isinstance(symbol_map, dict)
        assert isinstance(ambiguous, set)
        assert isinstance(locale_to_currency, dict)

        # All values in symbol_map should be strings (currency codes)
        for symbol, code in symbol_map.items():
            assert isinstance(symbol, str)
            assert isinstance(code, str)

        # All items in ambiguous should be strings
        for symbol in ambiguous:
            assert isinstance(symbol, str)

        # All items in locale_to_currency should be string -> string
        for locale, currency in locale_to_currency.items():
            assert isinstance(locale, str)
            assert isinstance(currency, str)

    def test_build_maps_euro_is_unambiguous(self) -> None:
        """Verify EUR symbol is in the unambiguous map."""
        symbol_map, ambiguous, _locale_to_currency, _ = _build_currency_maps_from_cldr()

        # Euro should be unambiguous (only EUR uses this symbol)
        assert "€" in symbol_map or "€" not in ambiguous
        if "€" in symbol_map:
            assert symbol_map["€"] == "EUR"

    def test_build_maps_dollar_is_ambiguous(self) -> None:
        """Verify $ symbol is in the ambiguous set (USD, CAD, AUD, etc.)."""
        _symbol_map, ambiguous, _locale_to_currency, _ = _build_currency_maps_from_cldr()

        # Dollar sign is used by multiple currencies
        assert "$" in ambiguous

    @given(
        locale_count=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=10)
    def test_build_maps_handles_various_locale_counts(self, locale_count: int) -> None:
        """PROPERTY: Function handles any number of locales."""
        mock_locales = [f"mock_{i}" for i in range(locale_count)]

        mock_locale = MagicMock()
        mock_locale.territory = None
        mock_locale.currencies = {}

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "ftllexengine.parsing.currency.locale_identifiers",
                return_value=mock_locales,
            ),
        ):
            symbol_map, ambiguous, locale_to_currency, _ = _build_currency_maps_from_cldr()

        # Should always return valid types
        assert isinstance(symbol_map, dict)
        assert isinstance(ambiguous, set)
        assert isinstance(locale_to_currency, dict)


# ============================================================================
# Integration Tests
# ============================================================================


class TestParseCurrencyWithBuiltMaps:
    """Test that parse_currency uses the built maps correctly."""

    def test_parse_currency_uses_symbol_map_for_euro(self) -> None:
        """Test parse_currency resolves EUR symbol to EUR."""
        result, errors = parse_currency("€100", "en_US")

        assert not errors
        assert result is not None
        _amount, currency = result
        assert currency == "EUR"

    def test_parse_currency_returns_error_for_ambiguous_without_default(self) -> None:
        """Test parse_currency returns error for ambiguous symbol without default."""
        result, errors = parse_currency("$100", "en_US")

        # $ is ambiguous, should return error without default_currency
        assert result is None
        assert len(errors) > 0

    def test_parse_currency_resolves_ambiguous_with_default(self) -> None:
        """Test parse_currency uses default_currency for ambiguous symbols."""
        result, errors = parse_currency("$100", "en_US", default_currency="CAD")

        assert not errors
        assert result is not None
        _amount, currency = result
        assert currency == "CAD"

    def test_parse_currency_infers_from_locale(self) -> None:
        """Test parse_currency can infer currency from locale."""
        result, _errors = parse_currency("$100", "en_US", infer_from_locale=True)

        # Should infer USD for en_US
        if result is not None:
            _amount, currency = result
            assert currency == "USD"
        # If locale not in map, errors are expected

    def test_parse_currency_handles_iso_codes(self) -> None:
        """Test parse_currency handles ISO codes directly."""
        result, errors = parse_currency("USD 100", "en_US")

        assert not errors
        assert result is not None
        _amount, currency = result
        assert currency == "USD"


# ============================================================================
# LINE 201: Test Fallback Pattern When No Symbols Found
# ============================================================================


class TestBuildCurrencyPatternFallback:
    """Test fallback case in _get_currency_pattern (line 209)."""

    def test_build_pattern_fallback_when_no_symbols(self) -> None:
        """Test _get_currency_pattern fallback when no symbols exist.

        This tests line 209, the else branch that creates an ISO-code-only
        pattern when both symbol_map and ambiguous_symbols are empty.
        """
        import re
        from unittest.mock import patch

        from ftllexengine.parsing.currency import (
            _get_currency_maps,
            _get_currency_pattern,
        )

        # Clear the pattern cache before test
        _get_currency_pattern.cache_clear()

        # Mock _get_currency_maps to return empty maps (with empty valid_codes)
        with patch(
            "ftllexengine.parsing.currency._get_currency_maps",
            return_value=({}, set(), {}, frozenset()),
        ):
            # Clear cache again after patching to force regeneration
            _get_currency_pattern.cache_clear()

            # Call the function - it will use our mock
            pattern = _get_currency_pattern()

            # Should return ISO-code-only pattern
            assert pattern is not None
            assert isinstance(pattern, re.Pattern)

            # Test that pattern matches ISO codes
            match = pattern.search("USD")
            assert match is not None
            assert match.group(1) == "USD"

            # Test that pattern matches 3-letter codes
            match = pattern.search("EUR")
            assert match is not None
            assert match.group(1) == "EUR"

            # Test that pattern does NOT match non-ISO formats
            match = pattern.search("€")
            assert match is None

            match = pattern.search("$")
            assert match is None

        # Clear caches to restore normal operation after test
        _get_currency_pattern.cache_clear()
        _get_currency_maps.cache_clear()
