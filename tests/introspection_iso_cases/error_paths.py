# mypy: ignore-errors
# ruff: noqa: ARG001
# mypy: ignore-errors
from __future__ import annotations

from unittest.mock import patch

import pytest

from ftllexengine.introspection import (
    CurrencyInfo,
    TerritoryInfo,
    clear_iso_cache,
    get_currency,
    get_territory,
    get_territory_currencies,
    list_currencies,
    list_territories,
)

# Private member access permitted for integration tests
from ftllexengine.introspection.iso import (
    _get_babel_currency_name,
    _get_babel_currency_symbol,
)


class TestExceptionNarrowing:
    """Tests for narrowed exception handling in Babel wrappers."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_value_error_is_caught(self) -> None:
        """ValueError from Babel should be caught and handled gracefully."""
        # Invalid locale formats trigger ValueError in Babel
        # The function should return None rather than propagating
        result = get_territory("US", locale="invalid")
        # Should either work or return None, not raise
        assert result is None or isinstance(result, TerritoryInfo)

    def test_lookup_error_is_caught(self) -> None:
        """LookupError (UnknownLocaleError) from Babel should be handled."""
        # Test with a locale that doesn't exist in CLDR
        try:
            result = get_currency("USD", locale="xyz_ABC")
            # Should return None or result, not raise
            assert result is None or isinstance(result, CurrencyInfo)
        except LookupError:
            pytest.fail("LookupError should be caught, not propagated")

    def test_attribute_key_error_handled(self) -> None:
        """AttributeError and KeyError from data access should be handled."""
        # These are handled internally; we verify by checking edge case inputs
        # that might trigger such errors in Babel's data access
        result = get_territory("XX")  # Unknown territory
        assert result is None

        result2 = get_currency("ZZZ")  # Unknown currency
        assert result2 is None

    def test_name_error_propagates(self) -> None:
        """NameError (programming bug) propagates rather than being suppressed.

        The narrowed exception catch list (ValueError, LookupError, KeyError,
        AttributeError) excludes NameError; it must propagate uncaught.
        """
        def mock_locale_parse(locale_str: str) -> object:
            msg = "name 'undefined_var' is not defined"
            raise NameError(msg)

        with (
            patch("babel.Locale.parse", side_effect=mock_locale_parse),
            pytest.raises(NameError),
        ):
            _get_babel_currency_name("USD", "en")

class TestUnknownLocaleErrorHandling:
    """Tests for UnknownLocaleError handling (fuzzer-discovered regression).

    Babel's UnknownLocaleError inherits from Exception, not LookupError.
    These tests verify the defensive exception handling catches it properly.
    """

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_very_long_invalid_locale_get_currency(self) -> None:
        """get_currency handles very long invalid locales gracefully.

        Regression test: fuzzer discovered UnknownLocaleError leak with
        locale='x' * 100. Previously raised babel.core.UnknownLocaleError.
        """
        # Fuzzer-discovered input
        long_locale = "x" * 100
        result = get_currency("USD", locale=long_locale)
        # Should return None (graceful degradation), not raise
        assert result is None

    def test_very_long_invalid_locale_get_territory(self) -> None:
        """get_territory handles very long invalid locales gracefully.

        Regression test for defensive exception handling.
        """
        long_locale = "x" * 100
        result = get_territory("US", locale=long_locale)
        # Should return None (graceful degradation), not raise
        assert result is None

    def test_garbage_locale_get_currency(self) -> None:
        """get_currency handles garbage locale strings gracefully."""
        garbage_locales = [
            "!@#$%^",
            "123456789",
            "\x00\x01\x02",
            "a" * 500,
            "xx_YY_ZZ_AA_BB",
        ]
        for locale in garbage_locales:
            result = get_currency("USD", locale=locale)
            # Should return None, not raise
            assert result is None, f"Failed for locale: {locale!r}"

    def test_garbage_locale_get_territory(self) -> None:
        """get_territory handles garbage locale strings gracefully."""
        garbage_locales = [
            "!@#$%^",
            "123456789",
            "\x00\x01\x02",
            "a" * 500,
            "xx_YY_ZZ_AA_BB",
        ]
        for locale in garbage_locales:
            result = get_territory("US", locale=locale)
            # Should return None, not raise
            assert result is None, f"Failed for locale: {locale!r}"

    def test_currency_symbol_fallback_on_invalid_locale(self) -> None:
        """_get_babel_currency_symbol returns code as fallback for invalid locale."""
        # When locale is invalid, the function should return the code as fallback
        result = _get_babel_currency_symbol("USD", "x" * 100)
        assert result == "USD"  # Falls back to code

    def test_currency_name_none_on_invalid_locale(self) -> None:
        """_get_babel_currency_name returns None for invalid locale."""
        result = _get_babel_currency_name("USD", "x" * 100)
        assert result is None

    def test_list_territories_empty_on_invalid_locale(self) -> None:
        """list_territories returns empty set for invalid locales."""
        long_locale = "x" * 100
        result = list_territories(locale=long_locale)
        # Should return empty frozenset, not raise
        assert isinstance(result, frozenset)
        assert len(result) == 0

    def test_list_currencies_with_invalid_locale(self) -> None:
        """list_currencies handles invalid locales gracefully."""
        long_locale = "x" * 100
        result = list_currencies(locale=long_locale)
        # Should return frozenset (may be empty), not raise
        assert isinstance(result, frozenset)

class TestClearAllCachesIntegration:
    """Tests for clear_module_caches integration with ISO caches."""

    def test_clear_module_caches_includes_iso_cache(self) -> None:
        """clear_module_caches should clear ISO introspection caches."""
        from ftllexengine import clear_module_caches
        from ftllexengine.introspection.iso import (
            _get_territory_impl,
        )

        # Populate ISO cache
        get_territory("US")
        get_currency("USD")
        list_territories()

        # pylint: disable=no-value-for-parameter
        # Note: cache_info() is a method added by @lru_cache decorator, not
        # related to the function's parameters. Pylint doesn't understand this.

        # Verify cache is populated
        info_before = _get_territory_impl.cache_info()
        assert info_before.currsize > 0

        # Clear ALL caches (not just ISO)
        clear_module_caches()

        # Verify ISO cache is now empty
        info_after = _get_territory_impl.cache_info()
        assert info_after.currsize == 0

class TestListCurrenciesConsistency:
    """Tests for list_currencies() consistency across locales."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_same_currency_count_across_locales(self) -> None:
        """list_currencies returns same number of currencies for all locales.

        Currencies without localized names fall back to English names rather
        than being excluded, ensuring consistent result sets across locales.
        """
        result_en = list_currencies(locale="en")
        result_de = list_currencies(locale="de")
        result_fr = list_currencies(locale="fr")

        # All locales should return the same number of currencies
        assert len(result_en) == len(result_de), (
            f"Currency count differs: en={len(result_en)}, de={len(result_de)}"
        )
        assert len(result_en) == len(result_fr), (
            f"Currency count differs: en={len(result_en)}, fr={len(result_fr)}"
        )

    def test_same_currency_codes_across_locales(self) -> None:
        """list_currencies returns same currency codes regardless of locale.

        The code set is identical across locales; only names/symbols differ.
        """
        codes_en = {c.code for c in list_currencies(locale="en")}
        codes_de = {c.code for c in list_currencies(locale="de")}
        codes_ja = {c.code for c in list_currencies(locale="ja")}

        assert codes_en == codes_de, "Codes differ: en vs de"
        assert codes_en == codes_ja, "Codes differ: en vs ja"

    def test_fallback_name_for_rare_locale(self) -> None:
        """Currencies with no localized name use English name as fallback.

        For locales with incomplete CLDR coverage, the English name should
        be used rather than excluding the currency.
        """
        # Use a rare locale that might have incomplete coverage
        result = list_currencies(locale="zu")  # Zulu

        # Should still include major currencies
        codes = {c.code for c in result}
        assert "USD" in codes
        assert "EUR" in codes
        assert "JPY" in codes

class TestTerritoryCacheSize:
    """Tests for territory cache bounded by MAX_TERRITORY_CACHE_SIZE."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_territory_currencies_cache_size(self) -> None:
        """Territory currencies cache uses correct MAX_TERRITORY_CACHE_SIZE."""
        from ftllexengine.constants import (
            MAX_TERRITORY_CACHE_SIZE,
        )
        from ftllexengine.introspection.iso import (
            _get_territory_currencies_impl,
        )

        # pylint: disable=no-value-for-parameter
        info = _get_territory_currencies_impl.cache_info()
        assert info.maxsize == MAX_TERRITORY_CACHE_SIZE
        # Should be 300 (enough for all ~249 territories)
        assert info.maxsize >= 249

    def test_no_cache_thrashing_on_full_iteration(self) -> None:
        """Iterating all territories should not cause cache thrashing.

        With MAX_TERRITORY_CACHE_SIZE >= 249, all territories fit in cache.
        """
        from ftllexengine.introspection.iso import (
            _get_territory_currencies_impl,
        )

        clear_iso_cache()

        # Iterate all territories
        territories = list_territories()
        for t in territories:
            _ = get_territory_currencies(t.alpha2)

        # pylint: disable=no-value-for-parameter
        info = _get_territory_currencies_impl.cache_info()

        # No evictions should have occurred (all fit in cache)
        # Eviction count is misses - currsize when cache is full
        assert info.maxsize is not None  # This cache is bounded
        assert info.currsize <= info.maxsize
        # All unique territories should be cached
        unique_territories = {t.alpha2 for t in territories}
        assert info.currsize >= len(unique_territories) - 1  # Allow small margin
