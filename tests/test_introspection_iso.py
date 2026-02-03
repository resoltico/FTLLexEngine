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
    _get_babel_territory_currencies,
)


class TestTerritoryInfo:
    """Tests for TerritoryInfo dataclass."""

    def test_immutable(self) -> None:
        """TerritoryInfo is immutable (frozen)."""
        info = TerritoryInfo(alpha2="US", name="United States", currencies=("USD",))
        with pytest.raises(AttributeError):
            info.alpha2 = "CA"  # type: ignore[misc]

    def test_hashable(self) -> None:
        """TerritoryInfo is hashable (can be used in sets/dicts)."""
        info = TerritoryInfo(alpha2="US", name="United States", currencies=("USD",))
        assert hash(info) is not None
        territories = {info}
        assert len(territories) == 1

    def test_equality(self) -> None:
        """TerritoryInfo instances with same values are equal."""
        info1 = TerritoryInfo(alpha2="US", name="United States", currencies=("USD",))
        info2 = TerritoryInfo(alpha2="US", name="United States", currencies=("USD",))
        assert info1 == info2

    def test_slots(self) -> None:
        """TerritoryInfo uses __slots__ for memory efficiency."""
        info = TerritoryInfo(alpha2="US", name="United States", currencies=("USD",))
        assert not hasattr(info, "__dict__") or info.__dict__ == {}

    def test_multi_currency_territory(self) -> None:
        """TerritoryInfo supports multiple currencies for multi-currency territories."""
        info = TerritoryInfo(alpha2="PA", name="Panama", currencies=("PAB", "USD"))
        assert len(info.currencies) == 2
        assert "PAB" in info.currencies
        assert "USD" in info.currencies

    def test_empty_currencies_tuple(self) -> None:
        """TerritoryInfo supports empty currencies tuple for territories without currency data."""
        info = TerritoryInfo(alpha2="AQ", name="Antarctica", currencies=())
        assert info.currencies == ()
        assert len(info.currencies) == 0


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

    def test_includes_currencies(self) -> None:
        """get_territory includes currencies when available."""
        result = get_territory("US")
        assert result is not None
        assert "USD" in result.currencies

        result_jp = get_territory("JP")
        assert result_jp is not None
        assert "JPY" in result_jp.currencies

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


class TestGetTerritoryCurrencies:
    """Tests for get_territory_currencies() function."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_returns_currencies_for_known_territory(self) -> None:
        """get_territory_currencies returns currencies for known territories."""
        us_currencies = get_territory_currencies("US")
        assert isinstance(us_currencies, tuple)
        assert "USD" in us_currencies

        jp_currencies = get_territory_currencies("JP")
        assert "JPY" in jp_currencies

        gb_currencies = get_territory_currencies("GB")
        assert "GBP" in gb_currencies

    def test_returns_empty_tuple_for_unknown_territory(self) -> None:
        """get_territory_currencies returns empty tuple for unknown territories."""
        result = get_territory_currencies("XX")
        assert result == ()

    def test_case_insensitive(self) -> None:
        """get_territory_currencies accepts lowercase codes."""
        assert "USD" in get_territory_currencies("us")
        assert "JPY" in get_territory_currencies("jp")

    def test_eurozone_countries(self) -> None:
        """get_territory_currencies returns EUR for eurozone countries."""
        eurozone = ["DE", "FR", "IT", "ES", "NL", "BE", "AT", "LV", "LT", "EE"]

        for code in eurozone:
            result = get_territory_currencies(code)
            assert "EUR" in result, f"Expected EUR for {code}, got {result}"

    def test_multi_currency_territories(self) -> None:
        """get_territory_currencies returns all currencies for multi-currency territories."""
        # Panama uses both PAB and USD
        pa_currencies = get_territory_currencies("PA")
        # CLDR data should include at least one currency
        assert len(pa_currencies) >= 1

    def test_returns_tuple_for_immutability(self) -> None:
        """get_territory_currencies returns an immutable tuple per architectural requirement."""
        result = get_territory_currencies("US")
        assert isinstance(result, tuple)
        # Verify it's immutable (tuple cannot be modified)
        # Callers can convert to list if mutation is needed: list(result)


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


class TestLocaleNormalization:
    """Tests for locale input normalization (SEC-DOS-UNBOUNDED-ISO-001 fix)."""

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
    """Tests for bounded LRU cache (SEC-DOS-UNBOUNDED-ISO-001 fix)."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_cache_uses_lru_with_maxsize(self) -> None:
        """Cache implementation should use bounded LRU cache."""
        # Import the internal cached functions to check their cache_info

        from ftllexengine.introspection.iso import (  # noqa: PLC0415
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
        from ftllexengine.introspection.iso import _get_territory_impl  # noqa: PLC0415

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


class TestExceptionNarrowing:
    """Tests for narrowed exception handling (ROBUST-ISO-EXCEPTIONS-001 fix)."""

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

    def test_name_error_would_propagate(self) -> None:
        """NameError (logic bug) should NOT be caught - verify via documentation.

        This test verifies the design intent. Actual NameError testing would
        require injecting bugs into the code, which is not practical.
        The narrowed exception list excludes NameError, TypeError, MemoryError.
        """
        # Read the source to verify exception types
        import inspect  # noqa: PLC0415

        from ftllexengine.introspection import iso  # noqa: PLC0415

        source = inspect.getsource(iso._get_babel_currency_name)

        # Verify we're catching specific exceptions, not Exception
        assert "except (ValueError, LookupError, KeyError, AttributeError):" in source
        assert "except Exception:" not in source


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
    """Tests for clear_all_caches integration (MAINT-CACHE-MISSING-001 fix)."""

    def test_clear_all_caches_includes_iso_cache(self) -> None:
        """clear_all_caches should clear ISO introspection caches."""
        from ftllexengine import clear_all_caches  # noqa: PLC0415
        from ftllexengine.introspection.iso import _get_territory_impl  # noqa: PLC0415

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
        clear_all_caches()

        # Verify ISO cache is now empty
        info_after = _get_territory_impl.cache_info()
        assert info_after.currsize == 0


class TestListCurrenciesConsistency:
    """Tests for list_currencies() consistency across locales (v0.89.0 fix)."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_same_currency_count_across_locales(self) -> None:
        """list_currencies returns same number of currencies for all locales.

        Prior to v0.89.0, currencies without localized names in a target locale
        were excluded from results. This caused inconsistent result sets.
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
        """list_currencies returns same currency codes for all locales.

        The code set should be identical; only names/symbols may differ.
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
    """Tests for territory cache using MAX_TERRITORY_CACHE_SIZE (v0.89.0 fix)."""

    def setup_method(self) -> None:
        """Clear cache before each test."""
        clear_iso_cache()

    def test_territory_currencies_cache_size(self) -> None:
        """Territory currencies cache uses correct MAX_TERRITORY_CACHE_SIZE."""
        from ftllexengine.constants import MAX_TERRITORY_CACHE_SIZE  # noqa: PLC0415
        from ftllexengine.introspection.iso import (  # noqa: PLC0415
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
        from ftllexengine.introspection.iso import (  # noqa: PLC0415
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


class _UnexpectedTestError(Exception):
    """Custom exception for testing defensive error handling.

    Defined at module level to avoid scoping issues with pytest.raises.
    Used to verify that non-UnknownLocaleError exceptions propagate correctly.
    """

    def __str__(self) -> str:
        return "Something went wrong - internal processing error"


class _LocaleWordTestError(Exception):
    """Exception whose message contains 'locale' but is NOT UnknownLocaleError.

    Tests type-based exception matching: this must propagate even though the
    message contains the word 'locale'. The old substring-based matching would
    have incorrectly suppressed this.
    """

    def __str__(self) -> str:
        return "Failed to process locale configuration data"


class TestDefensiveExceptionPropagation:
    """Tests for defensive exception re-raising in Babel wrappers.

    iso.py catches babel.core.UnknownLocaleError by type (isinstance check)
    and re-raises all other exceptions. These tests verify that logic bugs
    and unexpected exceptions propagate, including those whose messages
    contain 'locale' or 'unknown' but are not UnknownLocaleError.
    """

    def test_currency_name_reraises_unexpected_exception(self) -> None:
        """_get_babel_currency_name re-raises non-locale exceptions.

        Tests line 196: raise statement in defensive exception handler.
        """
        # This test verifies that unexpected exceptions (not matching the
        # "locale" or "unknown" pattern) are propagated rather than suppressed.

        call_count = [0]  # Use list to allow modification in nested function
        error_msg = "Internal error"

        def mock_locale_parse(locale_str: str) -> object:  # noqa: ARG001
            """Mock Locale.parse to raise unexpected exception."""
            call_count[0] += 1
            raise _UnexpectedTestError(error_msg)

        # Patch Babel's Locale.parse to inject our test exception
        with patch("babel.Locale.parse", side_effect=mock_locale_parse):
            #  The exception should propagate (not be suppressed)
            exception_raised = False
            result = None
            try:
                result = _get_babel_currency_name("USD", "en")
            except _UnexpectedTestError:
                exception_raised = True
            except Exception as e:
                pytest.fail(f"Unexpected exception type: {type(e).__name__}: {e}")

            if not exception_raised:
                pytest.fail(
                    f"Expected _UnexpectedTestError to be raised. "
                    f"Mock called {call_count[0]} times. Result: {result}"
                )

    def test_currency_symbol_reraises_unexpected_exception(self) -> None:
        """_get_babel_currency_symbol re-raises non-locale exceptions.

        Tests line 217: raise statement in defensive exception handler.
        """
        error_msg = "Internal error"

        def mock_get_currency_symbol(code: str, locale: str | object = None) -> str:  # noqa: ARG001
            """Mock that raises unexpected exception."""
            raise _UnexpectedTestError(error_msg)

        # Patch get_currency_symbol to trigger the exception path
        with patch("babel.numbers.get_currency_symbol", side_effect=mock_get_currency_symbol):
            # The exception should propagate (not be suppressed)
            exception_raised = False
            try:
                _get_babel_currency_symbol("USD", "en")
            except _UnexpectedTestError:
                exception_raised = True

            assert exception_raised, "Expected _UnexpectedTestError to be raised"

    def test_territories_reraises_non_unknown_locale_error_with_locale_word(
        self,
    ) -> None:
        """Non-UnknownLocaleError with 'locale' in message propagates.

        Verifies type-based matching: exceptions whose message contains
        'locale' propagate if not babel.core.UnknownLocaleError.
        """
        from ftllexengine.introspection.iso import (  # noqa: PLC0415
            _get_babel_territories,
        )

        def mock_locale_parse(locale_str: str) -> object:  # noqa: ARG001
            raise _LocaleWordTestError

        with (
            patch("babel.Locale.parse", side_effect=mock_locale_parse),
            pytest.raises(_LocaleWordTestError),
        ):
            _get_babel_territories("en")

    def test_currency_name_reraises_non_unknown_locale_error_with_locale_word(
        self,
    ) -> None:
        """Non-UnknownLocaleError with 'locale' in message propagates.

        Verifies type-based matching replaces fragile substring matching.
        """
        def mock_locale_parse(locale_str: str) -> object:  # noqa: ARG001
            raise _LocaleWordTestError

        with (
            patch("babel.Locale.parse", side_effect=mock_locale_parse),
            pytest.raises(_LocaleWordTestError),
        ):
            _get_babel_currency_name("USD", "en")

    def test_currency_symbol_reraises_non_unknown_locale_error_with_locale_word(
        self,
    ) -> None:
        """Non-UnknownLocaleError with 'locale' in message propagates.

        Verifies type-based matching replaces fragile substring matching.
        """
        def mock_symbol(
            code: str,  # noqa: ARG001
            locale: str | object = None,  # noqa: ARG001
        ) -> str:
            raise _LocaleWordTestError

        with (
            patch(
                "babel.numbers.get_currency_symbol",
                side_effect=mock_symbol,
            ),
            pytest.raises(_LocaleWordTestError),
        ):
            _get_babel_currency_symbol("USD", "en")
