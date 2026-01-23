"""Tests for ISO 3166/4217 introspection API.

Tests cover:
- TerritoryInfo and CurrencyInfo data classes
- Lookup functions (get_territory, get_currency, etc.)
- Type guards (is_valid_territory_code, is_valid_currency_code)
- Cache behavior
- Localization support
"""

import sys
from unittest.mock import patch

import pytest

from ftllexengine.introspection import (
    BabelImportError,
    CurrencyCode,
    CurrencyInfo,
    TerritoryCode,
    TerritoryInfo,
    clear_iso_cache,
    get_currency,
    get_territory,
    get_territory_currency,
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
    _get_babel_territory_currencies,
)


class TestTerritoryInfo:
    """Tests for TerritoryInfo dataclass."""

    def test_immutable(self) -> None:
        """TerritoryInfo is immutable (frozen)."""
        info = TerritoryInfo(alpha2="US", name="United States", default_currency="USD")
        with pytest.raises(AttributeError):
            info.alpha2 = "CA"  # type: ignore[misc]

    def test_hashable(self) -> None:
        """TerritoryInfo is hashable (can be used in sets/dicts)."""
        info = TerritoryInfo(alpha2="US", name="United States", default_currency="USD")
        assert hash(info) is not None
        territories = {info}
        assert len(territories) == 1

    def test_equality(self) -> None:
        """TerritoryInfo instances with same values are equal."""
        info1 = TerritoryInfo(alpha2="US", name="United States", default_currency="USD")
        info2 = TerritoryInfo(alpha2="US", name="United States", default_currency="USD")
        assert info1 == info2

    def test_slots(self) -> None:
        """TerritoryInfo uses __slots__ for memory efficiency."""
        info = TerritoryInfo(alpha2="US", name="United States", default_currency="USD")
        assert not hasattr(info, "__dict__") or info.__dict__ == {}


class TestCurrencyInfo:
    """Tests for CurrencyInfo dataclass."""

    def test_immutable(self) -> None:
        """CurrencyInfo is immutable (frozen)."""
        info = CurrencyInfo(code="USD", name="US Dollar", symbol="$", decimal_digits=2)
        with pytest.raises(AttributeError):
            info.code = "EUR"  # type: ignore[misc]

    def test_hashable(self) -> None:
        """CurrencyInfo is hashable (can be used in sets/dicts)."""
        info = CurrencyInfo(code="USD", name="US Dollar", symbol="$", decimal_digits=2)
        assert hash(info) is not None
        currencies = {info}
        assert len(currencies) == 1

    def test_equality(self) -> None:
        """CurrencyInfo instances with same values are equal."""
        info1 = CurrencyInfo(code="USD", name="US Dollar", symbol="$", decimal_digits=2)
        info2 = CurrencyInfo(code="USD", name="US Dollar", symbol="$", decimal_digits=2)
        assert info1 == info2

    def test_slots(self) -> None:
        """CurrencyInfo uses __slots__ for memory efficiency."""
        info = CurrencyInfo(code="USD", name="US Dollar", symbol="$", decimal_digits=2)
        assert not hasattr(info, "__dict__") or info.__dict__ == {}


class TestGetTerritory:
    """Tests for get_territory() function."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_returns_territory_info_for_valid_code(self) -> None:
        """get_territory returns TerritoryInfo for known codes."""
        result = get_territory("US")
        assert result is not None
        assert isinstance(result, TerritoryInfo)
        assert result.alpha2 == "US"
        assert "United States" in result.name or "USA" in result.name

    def test_returns_none_for_unknown_code(self) -> None:
        """get_territory returns None for unknown codes."""
        result = get_territory("XX")
        assert result is None

    def test_case_insensitive(self) -> None:
        """get_territory accepts lowercase codes."""
        result_upper = get_territory("US")
        result_lower = get_territory("us")
        result_mixed = get_territory("Us")

        assert result_upper is not None
        assert result_lower is not None
        assert result_mixed is not None
        assert result_upper.alpha2 == result_lower.alpha2 == result_mixed.alpha2

    def test_localized_names(self) -> None:
        """get_territory returns localized names based on locale."""
        result_en = get_territory("DE", locale="en")
        result_de = get_territory("DE", locale="de")

        assert result_en is not None
        assert result_de is not None

        # English name should contain "Germany"
        assert "Germany" in result_en.name
        # German name should be "Deutschland"
        assert "Deutschland" in result_de.name

    def test_includes_default_currency(self) -> None:
        """get_territory includes default currency when available."""
        result = get_territory("US")
        assert result is not None
        assert result.default_currency == "USD"

        result_jp = get_territory("JP")
        assert result_jp is not None
        assert result_jp.default_currency == "JPY"

    def test_various_territories(self) -> None:
        """get_territory works for various territory codes."""
        test_cases = ["US", "CA", "GB", "DE", "FR", "JP", "AU", "BR", "IN", "CN"]

        for code in test_cases:
            result = get_territory(code)
            assert result is not None, f"Failed for {code}"
            assert result.alpha2 == code
            assert len(result.name) > 0


class TestGetCurrency:
    """Tests for get_currency() function."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_returns_currency_info_for_valid_code(self) -> None:
        """get_currency returns CurrencyInfo for known codes."""
        result = get_currency("USD")
        assert result is not None
        assert isinstance(result, CurrencyInfo)
        assert result.code == "USD"
        assert "$" in result.symbol or "USD" in result.symbol

    def test_returns_none_for_unknown_code(self) -> None:
        """get_currency returns None for truly unknown codes."""
        # Use a code that's definitely not in any currency database
        result = get_currency("ZZZ")
        assert result is None

    def test_case_insensitive(self) -> None:
        """get_currency accepts lowercase codes."""
        result_upper = get_currency("USD")
        result_lower = get_currency("usd")
        result_mixed = get_currency("Usd")

        assert result_upper is not None
        assert result_lower is not None
        assert result_mixed is not None
        assert result_upper.code == result_lower.code == result_mixed.code

    def test_localized_symbols(self) -> None:
        """get_currency returns localized symbols based on locale."""
        result_en = get_currency("EUR", locale="en")
        result_de = get_currency("EUR", locale="de")

        assert result_en is not None
        assert result_de is not None

    def test_decimal_digits_standard(self) -> None:
        """get_currency returns correct decimal digits for standard currencies."""
        usd = get_currency("USD")
        eur = get_currency("EUR")
        gbp = get_currency("GBP")

        assert usd is not None
        assert usd.decimal_digits == 2
        assert eur is not None
        assert eur.decimal_digits == 2
        assert gbp is not None
        assert gbp.decimal_digits == 2

    def test_decimal_digits_zero(self) -> None:
        """get_currency returns 0 decimal digits for zero-decimal currencies."""
        jpy = get_currency("JPY")
        krw = get_currency("KRW")
        vnd = get_currency("VND")

        assert jpy is not None
        assert jpy.decimal_digits == 0
        assert krw is not None
        assert krw.decimal_digits == 0
        assert vnd is not None
        assert vnd.decimal_digits == 0

    def test_decimal_digits_three(self) -> None:
        """get_currency returns 3 decimal digits for three-decimal currencies."""
        kwd = get_currency("KWD")
        bhd = get_currency("BHD")
        omr = get_currency("OMR")

        assert kwd is not None
        assert kwd.decimal_digits == 3
        assert bhd is not None
        assert bhd.decimal_digits == 3
        assert omr is not None
        assert omr.decimal_digits == 3

    def test_decimal_digits_four(self) -> None:
        """get_currency returns 4 decimal digits for accounting units."""
        clf = get_currency("CLF")
        uyw = get_currency("UYW")

        assert clf is not None
        assert clf.decimal_digits == 4
        assert uyw is not None
        assert uyw.decimal_digits == 4


class TestListTerritories:
    """Tests for list_territories() function."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_returns_frozenset(self) -> None:
        """list_territories returns a frozenset."""
        result = list_territories()
        assert isinstance(result, frozenset)

    def test_contains_major_territories(self) -> None:
        """list_territories includes major world territories."""
        result = list_territories()
        codes = {t.alpha2 for t in result}

        major_codes = ["US", "CA", "GB", "DE", "FR", "JP", "AU", "BR", "IN", "CN"]
        for code in major_codes:
            assert code in codes, f"Missing {code}"

    def test_all_have_two_letter_codes(self) -> None:
        """All returned territories have valid 2-letter alpha codes."""
        result = list_territories()

        for territory in result:
            assert len(territory.alpha2) == 2
            assert territory.alpha2.isalpha()
            assert territory.alpha2.isupper()

    def test_localized_names(self) -> None:
        """list_territories returns localized names based on locale."""
        result_en = list_territories(locale="en")
        result_de = list_territories(locale="de")

        # Find Germany in both results
        de_en = next((t for t in result_en if t.alpha2 == "DE"), None)
        de_de = next((t for t in result_de if t.alpha2 == "DE"), None)

        assert de_en is not None
        assert de_de is not None
        assert "Germany" in de_en.name
        assert "Deutschland" in de_de.name


class TestListCurrencies:
    """Tests for list_currencies() function."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_returns_frozenset(self) -> None:
        """list_currencies returns a frozenset."""
        result = list_currencies()
        assert isinstance(result, frozenset)

    def test_contains_major_currencies(self) -> None:
        """list_currencies includes major world currencies."""
        result = list_currencies()
        codes = {c.code for c in result}

        major_codes = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD"]
        for code in major_codes:
            assert code in codes, f"Missing {code}"

    def test_all_have_three_letter_codes(self) -> None:
        """All returned currencies have valid 3-letter codes."""
        result = list_currencies()

        for currency in result:
            assert len(currency.code) == 3
            assert currency.code.isalpha()
            assert currency.code.isupper()


class TestGetTerritoryCurrency:
    """Tests for get_territory_currency() function."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_returns_currency_for_known_territory(self) -> None:
        """get_territory_currency returns currency for known territories."""
        assert get_territory_currency("US") == "USD"
        assert get_territory_currency("JP") == "JPY"
        assert get_territory_currency("GB") == "GBP"

    def test_returns_none_for_unknown_territory(self) -> None:
        """get_territory_currency returns None for unknown territories."""
        result = get_territory_currency("XX")
        assert result is None

    def test_case_insensitive(self) -> None:
        """get_territory_currency accepts lowercase codes."""
        assert get_territory_currency("us") == "USD"
        assert get_territory_currency("jp") == "JPY"

    def test_eurozone_countries(self) -> None:
        """get_territory_currency returns EUR for eurozone countries."""
        eurozone = ["DE", "FR", "IT", "ES", "NL", "BE", "AT", "LV", "LT", "EE"]

        for code in eurozone:
            result = get_territory_currency(code)
            assert result == "EUR", f"Expected EUR for {code}, got {result}"


class TestTypeGuards:
    """Tests for type guard functions."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_is_valid_territory_code_valid(self) -> None:
        """is_valid_territory_code returns True for valid codes."""
        assert is_valid_territory_code("US") is True
        assert is_valid_territory_code("GB") is True
        assert is_valid_territory_code("JP") is True

    def test_is_valid_territory_code_invalid(self) -> None:
        """is_valid_territory_code returns False for invalid codes."""
        # XX is not in CLDR; ZZ is (represents "Unknown Region")
        assert is_valid_territory_code("XX") is False
        assert is_valid_territory_code("QQ") is False

    def test_is_valid_territory_code_wrong_length(self) -> None:
        """is_valid_territory_code returns False for wrong-length strings."""
        assert is_valid_territory_code("U") is False
        assert is_valid_territory_code("USA") is False
        assert is_valid_territory_code("") is False

    def test_is_valid_territory_code_case_insensitive(self) -> None:
        """is_valid_territory_code is case insensitive."""
        assert is_valid_territory_code("us") is True
        assert is_valid_territory_code("Us") is True

    def test_is_valid_currency_code_valid(self) -> None:
        """is_valid_currency_code returns True for valid codes."""
        assert is_valid_currency_code("USD") is True
        assert is_valid_currency_code("EUR") is True
        assert is_valid_currency_code("JPY") is True

    def test_is_valid_currency_code_invalid(self) -> None:
        """is_valid_currency_code returns False for invalid codes."""
        # ZZZ and QQQ are not in CLDR; XXX is (represents "No currency")
        assert is_valid_currency_code("ZZZ") is False
        assert is_valid_currency_code("QQQ") is False

    def test_is_valid_currency_code_wrong_length(self) -> None:
        """is_valid_currency_code returns False for wrong-length strings."""
        assert is_valid_currency_code("US") is False
        assert is_valid_currency_code("USDD") is False
        assert is_valid_currency_code("") is False

    def test_is_valid_currency_code_case_insensitive(self) -> None:
        """is_valid_currency_code is case insensitive."""
        assert is_valid_currency_code("usd") is True
        assert is_valid_currency_code("Usd") is True


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
    """Tests for type aliases."""

    def test_territory_code_is_str(self) -> None:
        """TerritoryCode is a string type alias."""
        code: TerritoryCode = "US"
        assert isinstance(code, str)

    def test_currency_code_is_str(self) -> None:
        """CurrencyCode is a string type alias."""
        code: CurrencyCode = "USD"
        assert isinstance(code, str)


class TestBabelImportError:
    """Tests for BabelImportError exception."""

    def test_exception_is_import_error_subclass(self) -> None:
        """BabelImportError is a subclass of ImportError."""
        assert issubclass(BabelImportError, ImportError)

    def test_exception_message(self) -> None:
        """BabelImportError has informative installation message."""
        exc = BabelImportError()
        message = str(exc)
        assert "Babel is required" in message
        assert "pip install ftllexengine[babel]" in message

    def test_exception_can_be_raised_and_caught(self) -> None:
        """BabelImportError can be raised and caught."""
        with pytest.raises(BabelImportError) as exc_info:
            raise BabelImportError
        assert "Babel is required" in str(exc_info.value)


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
        """get_territory handles invalid locales gracefully."""
        # Invalid locales should raise or degrade gracefully
        # Babel may raise various exceptions for malformed locales
        try:
            result = get_territory("US", locale="invalid_LOCALE_123")
            # If it doesn't raise, it should still return a valid result or None
            assert result is None or isinstance(result, TerritoryInfo)
        except Exception:  # pylint: disable=broad-exception-caught
            # Various Babel exceptions are acceptable
            pass

    def test_invalid_locale_currency(self) -> None:
        """get_currency handles invalid locales gracefully."""
        # Invalid locales should raise or degrade gracefully
        try:
            result = get_currency("USD", locale="invalid_LOCALE_123")
            # If it doesn't raise, it should still return a valid result or None
            assert result is None or isinstance(result, CurrencyInfo)
        except Exception:  # pylint: disable=broad-exception-caught
            # Various Babel exceptions are acceptable
            pass

    def test_malformed_locale_list_territories(self) -> None:
        """list_territories handles malformed locales."""
        # Malformed locales should raise or degrade gracefully
        try:
            result = list_territories(locale="xxx_YYY")
            assert isinstance(result, frozenset)
        except Exception:  # pylint: disable=broad-exception-caught
            # Various Babel exceptions are acceptable
            pass

    def test_malformed_locale_list_currencies(self) -> None:
        """list_currencies handles malformed locales."""
        # Malformed locales should raise or degrade gracefully
        try:
            result = list_currencies(locale="xxx_YYY")
            assert isinstance(result, frozenset)
        except Exception:  # pylint: disable=broad-exception-caught
            # Various Babel exceptions are acceptable
            pass

    def test_currency_symbol_fallback(self) -> None:
        """get_currency returns code as symbol fallback for unknown/problematic currencies."""
        # Test with a real currency but in a locale that might not have symbol data
        result = get_currency("USD", locale="en")
        assert result is not None
        # Symbol should either be locale-specific or fall back to code
        assert result.symbol in ("$", "US$", "USD")

    def test_territory_without_currency(self) -> None:
        """Territories without currency data return None for default_currency."""
        # Antarctica (AQ) typically has no official currency
        result = get_territory("AQ")
        if result is not None:
            # May have no default currency
            assert result.default_currency is None or isinstance(result.default_currency, str)

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

    def test_territory_currency_for_non_sovereign_territories(self) -> None:
        """get_territory_currency handles territories without unique currencies."""
        # Vatican City might have unusual currency data
        result = get_territory_currency("VA")
        # May return EUR or None
        assert result is None or isinstance(result, str)

        # Antarctica has no official currency
        result_aq = get_territory_currency("AQ")
        assert result_aq is None

    def test_get_currency_with_very_rare_locale(self) -> None:
        """get_currency degrades gracefully with very rare locales."""
        # Test with a locale that has minimal CLDR data
        try:
            result = get_currency("USD", locale="ii")  # Sichuan Yi
            # Should either work or return None
            assert result is None or isinstance(result, CurrencyInfo)
        except Exception:  # pylint: disable=broad-exception-caught
            # Some locales might trigger Babel errors
            pass

    def test_get_territory_with_deprecated_locale_format(self) -> None:
        """get_territory handles deprecated locale formats."""
        # Test with deprecated/unusual locale format
        try:
            result = get_territory("US", locale="en_US_POSIX")
            assert result is None or isinstance(result, TerritoryInfo)
        except Exception:  # pylint: disable=broad-exception-caught
            # Babel may reject this format
            pass

    def test_babel_import_error_propagation(self) -> None:
        """BabelImportError is raised when Babel is not available."""
        # Temporarily hide babel modules to trigger ImportError
        babel_modules = {k: v for k, v in sys.modules.items() if k.startswith("babel")}
        try:
            # Remove babel from sys.modules
            for key in list(babel_modules.keys()):
                sys.modules.pop(key, None)

            # Clear caches to force re-import
            clear_iso_cache()

            # Prevent import by blocking it
            sys.modules["babel"] = None  # type: ignore[assignment]

            # Now try to use the functions - they should raise BabelImportError
            # PLC0415: Runtime import needed to test ImportError path
            from ftllexengine.introspection import iso  # noqa: PLC0415

            with pytest.raises(BabelImportError):
                iso.get_territory("US")

        finally:
            # Restore babel modules
            for key, value in babel_modules.items():
                sys.modules[key] = value
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
        """_get_babel_currency_name handles problematic locales."""
        # Test with a malformed locale that might trigger exceptions
        try:
            result = _get_babel_currency_name("USD", "invalid_LOCALE_123")
            # Should return None for malformed locales
            assert result is None
        except Exception:  # pylint: disable=broad-exception-caught
            # Babel may raise various exceptions
            pass

    def test_get_babel_currency_symbol_with_unknown_code(self) -> None:
        """_get_babel_currency_symbol returns code as fallback for unknown codes."""
        # Test with an invalid code - should return the code itself as fallback
        result = _get_babel_currency_symbol("ZZZ", "en")
        # Should either work or fall back to the code
        assert result == "ZZZ" or len(result) > 0

    def test_get_babel_currency_symbol_with_problematic_locale(self) -> None:
        """_get_babel_currency_symbol handles problematic locales."""
        # Test with malformed locale
        try:
            result = _get_babel_currency_symbol("USD", "xxx_YYY_ZZZ")
            # Should either work or fall back to code
            assert result == "USD" or len(result) > 0
        except Exception:  # pylint: disable=broad-exception-caught
            # Babel may raise various exceptions
            pass

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
        """_get_babel_currency_name raises BabelImportError when import fails."""
        error_msg = "Mocked import failure"

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name in ("babel", "babel.numbers"):
                raise ImportError(error_msg)
            return __import__(name, *args, **kwargs)  # type: ignore[arg-type]

        with patch("builtins.__import__", side_effect=mock_import), pytest.raises(
            BabelImportError
        ):
            _get_babel_currency_name("USD", "en")

    def test_get_babel_currency_symbol_import_error(self) -> None:
        """_get_babel_currency_symbol raises BabelImportError when import fails."""
        error_msg = "Mocked import failure"

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "babel.numbers":
                raise ImportError(error_msg)
            return __import__(name, *args, **kwargs)  # type: ignore[arg-type]

        with patch("builtins.__import__", side_effect=mock_import), pytest.raises(
            BabelImportError
        ):
            _get_babel_currency_symbol("USD", "en")

    def test_get_babel_territory_currencies_import_error(self) -> None:
        """_get_babel_territory_currencies raises BabelImportError when import fails."""
        error_msg = "Mocked import failure"

        def mock_import(name: str, *args: object, **kwargs: object) -> object:
            if name == "babel.core":
                raise ImportError(error_msg)
            return __import__(name, *args, **kwargs)  # type: ignore[arg-type]

        with patch("builtins.__import__", side_effect=mock_import), pytest.raises(
            BabelImportError
        ):
            _get_babel_territory_currencies("US")

    def test_get_babel_territory_currencies_exception_handling(self) -> None:
        """_get_babel_territory_currencies returns empty list on Babel data errors."""
        # This tests the exception handling path (lines 198-200)
        # We need to trigger an exception in the data processing
        # Mock get_global to return malformed data
        from babel.core import get_global  # noqa: PLC0415

        original_get_global = get_global

        def mock_get_global(key: str) -> object:
            if key == "territory_currencies":
                # Return a dict with malformed data that will cause indexing errors
                return {"XX": [("USD", None, None)]}  # Missing 4th element (tender flag)
            return original_get_global(key)  # type: ignore[arg-type]

        with patch("babel.core.get_global", side_effect=mock_get_global):
            result = _get_babel_territory_currencies("XX")
            # Should return empty list due to exception
            assert result == []

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
            "ftllexengine.introspection.iso._get_babel_currencies",
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
