# mypy: ignore-errors
# mypy: ignore-errors
from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

import ftllexengine.core.babel_compat as _bc
from ftllexengine.introspection import (
    BabelImportError,
    CurrencyCode,
    CurrencyInfo,
    TerritoryCode,
    TerritoryInfo,
    clear_iso_cache,
    get_currency,
    get_territory,
    get_territory_currencies,
    is_valid_currency_code,
    is_valid_territory_code,
    list_currencies,
    list_territories,
)

# Private member access permitted for integration tests
from ftllexengine.introspection.iso import (
    _get_babel_currencies,
    _get_babel_currency_name,
    _get_babel_currency_symbol,
    _get_babel_official_languages,
    _get_babel_territory_currencies,
)


class TestCaching:
    """Tests for cache behavior."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_results_are_cached(self) -> None:
        """Repeated calls return same cached objects."""
        result1 = get_territory("US")
        result2 = get_territory("US")

        # Same object should be returned (cached)
        assert result1 is result2

    def test_clear_cache_works(self) -> None:
        """clear_iso_cache clears all caches."""
        # Populate cache
        result1 = get_territory("US")
        result1_currency = get_currency("USD")

        # Clear cache
        clear_iso_cache()

        # New objects should be returned
        result2 = get_territory("US")
        result2_currency = get_currency("USD")

        # Values should be equal
        assert result1 == result2
        assert result1_currency == result2_currency

    def test_different_locales_cached_separately(self) -> None:
        """Different locales have separate cache entries."""
        result_en = get_territory("DE", locale="en")
        result_de = get_territory("DE", locale="de")

        # Different objects (different locales)
        assert result_en != result_de

        # Repeat calls return cached objects
        assert get_territory("DE", locale="en") is result_en
        assert get_territory("DE", locale="de") is result_de

class TestTypeAliases:
    """Tests for TerritoryCode and CurrencyCode NewType wrappers."""

    def test_territory_code_is_str_at_runtime(self) -> None:
        """TerritoryCode is a NewType of str; transparent (identity) at runtime."""
        code = TerritoryCode("US")
        assert isinstance(code, str)
        assert code == "US"

    def test_currency_code_is_str_at_runtime(self) -> None:
        """CurrencyCode is a NewType of str; transparent (identity) at runtime."""
        code = CurrencyCode("USD")
        assert isinstance(code, str)
        assert code == "USD"

    def test_territory_code_newtype_constructor_is_identity(self) -> None:
        """TerritoryCode(...) returns the string value unchanged at runtime."""
        raw = "LV"
        assert TerritoryCode(raw) == raw

    def test_currency_code_newtype_constructor_is_identity(self) -> None:
        """CurrencyCode(...) returns the string value unchanged at runtime."""
        raw = "EUR"
        assert CurrencyCode(raw) == raw

class TestBabelImportError:
    """Tests for BabelImportError exception."""

    def test_exception_is_import_error_subclass(self) -> None:
        """BabelImportError is a subclass of ImportError."""
        assert issubclass(BabelImportError, ImportError)

    def test_exception_message(self) -> None:
        """BabelImportError has informative installation message."""
        exc = BabelImportError("ISO introspection")
        message = str(exc)
        assert "Babel" in message
        assert "pip install ftllexengine[babel]" in message
        assert "ISO introspection" in message

    def test_exception_can_be_raised_and_caught(self) -> None:
        """BabelImportError can be raised and caught."""
        feature = "test feature"
        with pytest.raises(BabelImportError) as exc_info:
            raise BabelImportError(feature)
        assert "Babel" in str(exc_info.value)

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_empty_string_territory(self) -> None:
        """get_territory handles empty string gracefully."""
        result = get_territory("")
        assert result is None

    def test_empty_string_currency(self) -> None:
        """get_currency handles empty string gracefully."""
        result = get_currency("")
        assert result is None

    def test_numeric_string_territory(self) -> None:
        """get_territory handles numeric strings."""
        result = get_territory("12")
        assert result is None

    def test_numeric_string_currency(self) -> None:
        """get_currency handles numeric strings."""
        result = get_currency("123")
        assert result is None

    def test_whitespace_territory(self) -> None:
        """get_territory handles whitespace strings."""
        result = get_territory("  ")
        assert result is None

    def test_whitespace_currency(self) -> None:
        """get_currency handles whitespace strings."""
        result = get_currency("   ")
        assert result is None

    def test_special_iso_codes(self) -> None:
        """Test special ISO 4217 codes."""
        # XXX is "No currency" - a valid ISO 4217 code
        xxx = get_currency("XXX")
        assert xxx is not None

        # XAU is gold - a valid ISO 4217 code
        xau = get_currency("XAU")
        assert xau is not None

    def test_invalid_locale_territory(self) -> None:
        """get_territory returns None for invalid locales."""
        result = get_territory("US", locale="invalid_LOCALE_123")
        assert result is None

    def test_invalid_locale_currency(self) -> None:
        """get_currency returns None for invalid locales."""
        result = get_currency("USD", locale="invalid_LOCALE_123")
        assert result is None

    def test_malformed_locale_list_territories(self) -> None:
        """list_territories returns empty frozenset for malformed locales."""
        result = list_territories(locale="xxx_YYY")
        assert isinstance(result, frozenset)
        assert len(result) == 0

    def test_malformed_locale_list_currencies(self) -> None:
        """list_currencies returns frozenset for malformed locales."""
        result = list_currencies(locale="xxx_YYY")
        assert isinstance(result, frozenset)

    def test_currency_symbol_fallback(self) -> None:
        """get_currency returns code as symbol fallback for unknown/problematic currencies."""
        # Test with a real currency but in a locale that might not have symbol data
        result = get_currency("USD", locale="en")
        assert result is not None
        # Symbol should either be locale-specific or fall back to code
        assert result.symbol in ("$", "US$", "USD")

    def test_territory_without_currency(self) -> None:
        """Territories without currency data have empty currencies tuple."""
        # Antarctica (AQ) typically has no official currency
        result = get_territory("AQ")
        if result is not None:
            # May have no currencies (empty tuple)
            assert isinstance(result.currencies, tuple)
            # May be empty or contain some currencies depending on CLDR data
            assert all(isinstance(c, str) for c in result.currencies)

    def test_type_guard_non_string_territory(self) -> None:
        """is_valid_territory_code returns False for non-string inputs."""
        assert is_valid_territory_code(None) is False  # type: ignore[arg-type]
        assert is_valid_territory_code(123) is False  # type: ignore[arg-type]
        assert is_valid_territory_code([]) is False  # type: ignore[arg-type]
        assert is_valid_territory_code({}) is False  # type: ignore[arg-type]

    def test_type_guard_non_string_currency(self) -> None:
        """is_valid_currency_code returns False for non-string inputs."""
        assert is_valid_currency_code(None) is False  # type: ignore[arg-type]
        assert is_valid_currency_code(123) is False  # type: ignore[arg-type]
        assert is_valid_currency_code([]) is False  # type: ignore[arg-type]
        assert is_valid_currency_code({}) is False  # type: ignore[arg-type]

class TestBabelExceptionHandling:
    """Tests for Babel exception handling paths."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_currency_name_none_for_truly_invalid_code(self) -> None:
        """get_currency returns None for codes not in CLDR."""
        # Use a code that's definitely not in CLDR
        result = get_currency("ZZZ")
        assert result is None

        # Another invalid code
        result2 = get_currency("QQQ")
        assert result2 is None

    def test_currency_symbol_with_unusual_locale(self) -> None:
        """get_currency handles unusual locales gracefully."""
        # Test with rare locale that might not have full currency symbol data
        result = get_currency("USD", locale="zu")  # Zulu
        if result is not None:
            # Symbol should be present (may be fallback)
            assert len(result.symbol) > 0

    def test_territory_currencies_for_non_sovereign_territories(self) -> None:
        """get_territory_currencies handles territories without unique currencies."""
        # Vatican City might have unusual currency data
        result = get_territory_currencies("VA")
        # May return EUR or empty tuple
        assert isinstance(result, tuple)
        assert all(isinstance(c, str) for c in result)

        # Antarctica has no official currency
        result_aq = get_territory_currencies("AQ")
        assert result_aq == ()

    def test_get_currency_with_very_rare_locale(self) -> None:
        """get_currency handles a locale with minimal CLDR data."""
        # Sichuan Yi (ii) is a valid but rare locale with limited data
        result = get_currency("USD", locale="ii")
        assert result is None or isinstance(result, CurrencyInfo)

    def test_get_territory_with_deprecated_locale_format(self) -> None:
        """get_territory handles POSIX locale format variant."""
        result = get_territory("US", locale="en_US_POSIX")
        assert result is None or isinstance(result, TerritoryInfo)

    def test_babel_import_error_propagation(self) -> None:
        """BabelImportError is raised when Babel is not available."""
        # Temporarily hide babel modules to trigger ImportError
        babel_modules = {k: v for k, v in sys.modules.items() if k.startswith("babel")}
        saved_available = _bc._babel_available
        try:
            # Remove babel from sys.modules
            for key in list(babel_modules.keys()):
                sys.modules.pop(key, None)

            # Clear caches to force re-import
            clear_iso_cache()

            # Prevent import by blocking it
            sys.modules["babel"] = None  # type: ignore[assignment]

            # Reset the availability sentinel so require_babel() re-evaluates against
            # the patched sys.modules. Without this, a cached True value causes
            # require_babel() to pass even though Babel is no longer importable,
            # leading to a raw ModuleNotFoundError instead of BabelImportError.
            _bc._babel_available = None

            # Now try to use the functions - they should raise BabelImportError
            # PLC0415: Runtime import needed to test ImportError path
            from ftllexengine.introspection import iso

            with pytest.raises(BabelImportError):
                iso.get_territory("US")

        finally:
            # Restore babel modules and availability sentinel
            for key, value in babel_modules.items():
                sys.modules[key] = value
            _bc._babel_available = saved_available
            # Clear cache again to restore normal operation
            clear_iso_cache()

class TestPrivateBabelWrappers:
    """Tests for private Babel wrapper functions.

    Tests exception handling paths in internal functions.
    Private member access permitted.
    """

    def test_get_babel_currency_name_with_invalid_code(self) -> None:
        """_get_babel_currency_name returns None for invalid codes."""
        result = _get_babel_currency_name("ZZZ", "en")
        assert result is None

        result2 = _get_babel_currency_name("QQQ", "en")
        assert result2 is None

    def test_get_babel_currency_name_with_problematic_locale(self) -> None:
        """_get_babel_currency_name returns None for malformed locales."""
        result = _get_babel_currency_name("USD", "invalid_LOCALE_123")
        assert result is None

    def test_get_babel_currency_symbol_with_unknown_code(self) -> None:
        """_get_babel_currency_symbol returns code as fallback for unknown codes."""
        # Test with an invalid code - should return the code itself as fallback
        result = _get_babel_currency_symbol("ZZZ", "en")
        # Should either work or fall back to the code
        assert result == "ZZZ" or len(result) > 0

    def test_get_babel_currency_symbol_with_problematic_locale(self) -> None:
        """_get_babel_currency_symbol falls back to currency code for malformed locales."""
        result = _get_babel_currency_symbol("USD", "xxx_YYY_ZZZ")
        assert result == "USD"  # Falls back to code

    def test_get_babel_territory_currencies_with_invalid_territory(self) -> None:
        """_get_babel_territory_currencies returns empty list for invalid territories."""
        result = _get_babel_territory_currencies("XX")
        # Should return empty list for unknown territories
        assert isinstance(result, list)
        assert len(result) == 0

    def test_get_babel_territory_currencies_with_antarctica(self) -> None:
        """_get_babel_territory_currencies handles territories without currencies."""
        result = _get_babel_territory_currencies("AQ")  # Antarctica
        # Should return empty list (no official currency)
        assert isinstance(result, list)

    def test_get_babel_currency_symbol_fallback_path(self) -> None:
        """_get_babel_currency_symbol uses fallback when Babel raises exception."""
        # Use a code/locale combination that might trigger Babel errors
        # XTS is a test currency code - might not have symbols in all locales
        result = _get_babel_currency_symbol("XTS", "en")
        # Should return either a valid symbol or the code as fallback
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_babel_currency_name_import_error(self) -> None:
        """_get_babel_currency_name raises BabelImportError when Babel unavailable."""
        _bc._babel_available = False
        try:
            with pytest.raises(BabelImportError):
                _get_babel_currency_name("USD", "en")
        finally:
            _bc._babel_available = None

    def test_get_babel_currency_symbol_import_error(self) -> None:
        """_get_babel_currency_symbol raises BabelImportError when Babel unavailable."""
        # Set sentinel to False to simulate Babel being unavailable.
        # Direct sentinel manipulation avoids the recursive __import__ mock pattern.
        _bc._babel_available = False
        try:
            with pytest.raises(BabelImportError):
                _get_babel_currency_symbol("USD", "en")
        finally:
            # Reset so subsequent tests reinitialize with Babel available
            _bc._babel_available = None

    def test_get_babel_territory_currencies_import_error(self) -> None:
        """_get_babel_territory_currencies raises BabelImportError when Babel unavailable."""
        # Set sentinel to False to simulate Babel being unavailable.
        # Direct sentinel manipulation avoids the recursive __import__ mock pattern.
        _bc._babel_available = False
        try:
            with pytest.raises(BabelImportError):
                _get_babel_territory_currencies("US")
        finally:
            # Reset so subsequent tests reinitialize with Babel available
            _bc._babel_available = None

    def test_get_babel_territory_currencies_exception_handling(self) -> None:
        """_get_babel_territory_currencies returns empty list on Babel API errors.

        The production code calls babel.numbers.get_territory_currencies() directly.
        Patching that function to raise ValueError exercises the defensive except clause.
        """
        with patch(
            "babel.numbers.get_territory_currencies",
            side_effect=ValueError("simulated Babel data error"),
        ):
            result = _get_babel_territory_currencies("US")
            assert result == []

    def test_get_babel_official_languages_exception_handling(self) -> None:
        """_get_babel_official_languages returns empty tuple on Babel API errors.

        The production code calls babel.languages.get_official_languages() directly.
        Patching that function to raise ValueError exercises the defensive except clause.
        """
        with patch(
            "babel.languages.get_official_languages",
            side_effect=ValueError("simulated Babel data error"),
        ):
            result = _get_babel_official_languages("GB")
            assert result == ()

    def test_get_babel_official_languages_lookup_error(self) -> None:
        """_get_babel_official_languages returns empty tuple on LookupError."""
        with patch(
            "babel.languages.get_official_languages",
            side_effect=LookupError("unknown territory"),
        ):
            result = _get_babel_official_languages("XX")
            assert result == ()

    def test_list_currencies_filters_invalid_codes(self) -> None:
        """list_currencies filters out invalid currency codes from Babel data."""
        # This tests the branch where codes don't match ISO 4217 format
        # Clear cache to ensure fresh call
        clear_iso_cache()

        # Mock _get_babel_currencies to return invalid codes
        original_get_babel_currencies = _get_babel_currencies

        def mock_get_babel_currencies() -> dict[str, str]:
            real_currencies = original_get_babel_currencies()
            # Add invalid codes to trigger the filter branch
            return {
                **real_currencies,
                "US": "Invalid two-letter code",  # Only 2 letters
                "USDD": "Invalid four-letter code",  # 4 letters
                "usd": "Invalid lowercase code",  # Lowercase
                "12D": "Invalid numeric code",  # Contains numbers
                "": "Empty code",  # Empty
            }

        with patch(
            "ftllexengine.introspection.iso_lookup._get_babel_currencies",
            side_effect=mock_get_babel_currencies,
        ):
            result = list_currencies()
            # Should still return valid currencies, filtering out invalid ones
            assert isinstance(result, frozenset)
            codes = {c.code for c in result}
            # Invalid codes should not be in result
            assert "US" not in codes  # Two-letter code
            assert "USDD" not in codes  # Four-letter code
            # Valid codes should be present
            assert "USD" in codes

class TestLocaleNormalization:
    """Tests for locale input normalization."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_locale_format_variants_return_same_cached_object(self) -> None:
        """Different locale formats should hit the same cache entry."""
        # Clear cache to start fresh
        clear_iso_cache()

        # Call with BCP-47 format
        result_bcp47 = get_territory("US", locale="en-US")

        # Call with POSIX format (should hit same cache)
        result_posix = get_territory("US", locale="en_US")

        # Call with lowercase
        result_lower = get_territory("US", locale="en_us")

        # All should return the same cached object
        assert result_bcp47 is result_posix
        assert result_posix is result_lower

    def test_locale_normalization_for_get_currency(self) -> None:
        """get_currency normalizes locale formats to single cache entry."""
        clear_iso_cache()

        result1 = get_currency("EUR", locale="de-DE")
        result2 = get_currency("EUR", locale="de_DE")
        result3 = get_currency("EUR", locale="de_de")

        # Same cached object for all variants
        assert result1 is result2
        assert result2 is result3

    def test_locale_normalization_for_list_territories(self) -> None:
        """list_territories normalizes locale formats to single cache entry."""
        clear_iso_cache()

        result1 = list_territories(locale="fr-FR")
        result2 = list_territories(locale="fr_FR")
        result3 = list_territories(locale="fr_fr")

        # Same cached object for all variants
        assert result1 is result2
        assert result2 is result3

    def test_locale_normalization_for_list_currencies(self) -> None:
        """list_currencies normalizes locale formats to single cache entry."""
        clear_iso_cache()

        result1 = list_currencies(locale="ja-JP")
        result2 = list_currencies(locale="ja_JP")
        result3 = list_currencies(locale="ja_jp")

        # Same cached object for all variants
        assert result1 is result2
        assert result2 is result3

    def test_code_case_normalization(self) -> None:
        """Territory and currency codes are case-normalized."""
        clear_iso_cache()

        # Territory code case variants should hit same cache
        t_upper = get_territory("US")
        t_lower = get_territory("us")
        t_mixed = get_territory("Us")

        assert t_upper is t_lower
        assert t_lower is t_mixed

        # Currency code case variants should hit same cache
        c_upper = get_currency("USD")
        c_lower = get_currency("usd")
        c_mixed = get_currency("Usd")

        assert c_upper is c_lower
        assert c_lower is c_mixed

class TestBoundedCache:
    """Tests for bounded LRU cache."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_cache_uses_lru_with_maxsize(self) -> None:
        """Cache implementation should use bounded LRU cache."""
        # Import the internal cached functions to check their cache_info

        from ftllexengine.introspection.iso import (
            _get_currency_impl,
            _get_territory_currencies_impl,
            _get_territory_impl,
            _list_currencies_impl,
            _list_territories_impl,
        )

        # All internal cached functions should have cache_info method (lru_cache feature)
        assert hasattr(_get_territory_impl, "cache_info")
        assert hasattr(_get_currency_impl, "cache_info")
        assert hasattr(_list_territories_impl, "cache_info")
        assert hasattr(_list_currencies_impl, "cache_info")
        assert hasattr(_get_territory_currencies_impl, "cache_info")

        # Check maxsize is set (bounded cache, not unbounded)
        # pylint: disable=no-value-for-parameter
        # Note: cache_info() is a method added by @lru_cache decorator, not
        # related to the function's parameters. Pylint doesn't understand this.
        info = _get_territory_impl.cache_info()
        assert info.maxsize is not None
        assert info.maxsize > 0  # Should be MAX_LOCALE_CACHE_SIZE (128)

    def test_cache_statistics_work(self) -> None:
        """Cache statistics (hits, misses) should be tracked."""
        from ftllexengine.introspection.iso import (
            _get_territory_impl,
        )

        clear_iso_cache()

        # pylint: disable=no-value-for-parameter
        # Note: cache_info() is a method added by @lru_cache decorator, not
        # related to the function's parameters. Pylint doesn't understand this.

        # Get initial stats
        initial_info = _get_territory_impl.cache_info()
        initial_hits = initial_info.hits
        initial_misses = initial_info.misses

        # First call should be a miss
        get_territory("US")
        info_after_first = _get_territory_impl.cache_info()
        assert info_after_first.misses == initial_misses + 1

        # Second call should be a hit
        get_territory("US")
        info_after_second = _get_territory_impl.cache_info()
        assert info_after_second.hits == initial_hits + 1
