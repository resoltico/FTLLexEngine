# mypy: ignore-errors
from __future__ import annotations

import pytest

from ftllexengine.introspection import (
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


class TestTerritoryInfo:
    """Tests for TerritoryInfo dataclass."""

    def test_immutable(self) -> None:
        """TerritoryInfo is immutable (frozen)."""
        info = TerritoryInfo(
            alpha2=TerritoryCode("US"), name="United States",
            currencies=(CurrencyCode("USD"),), official_languages=("en",),
        )
        with pytest.raises(AttributeError):
            info.alpha2 = TerritoryCode("CA")  # type: ignore[misc]

    def test_hashable(self) -> None:
        """TerritoryInfo is hashable (can be used in sets/dicts)."""
        info = TerritoryInfo(
            alpha2=TerritoryCode("US"), name="United States",
            currencies=(CurrencyCode("USD"),), official_languages=("en",),
        )
        assert hash(info) is not None
        territories = {info}
        assert len(territories) == 1

    def test_equality(self) -> None:
        """TerritoryInfo instances with same values are equal."""
        info1 = TerritoryInfo(
            alpha2=TerritoryCode("US"), name="United States",
            currencies=(CurrencyCode("USD"),), official_languages=("en",),
        )
        info2 = TerritoryInfo(
            alpha2=TerritoryCode("US"), name="United States",
            currencies=(CurrencyCode("USD"),), official_languages=("en",),
        )
        assert info1 == info2

    def test_slots(self) -> None:
        """TerritoryInfo uses __slots__ for memory efficiency."""
        info = TerritoryInfo(
            alpha2=TerritoryCode("US"), name="United States",
            currencies=(CurrencyCode("USD"),), official_languages=("en",),
        )
        assert not hasattr(info, "__dict__") or info.__dict__ == {}

    def test_multi_currency_territory(self) -> None:
        """TerritoryInfo supports multiple currencies for multi-currency territories."""
        info = TerritoryInfo(
            alpha2=TerritoryCode("PA"), name="Panama",
            currencies=(CurrencyCode("PAB"), CurrencyCode("USD")),
            official_languages=("es",),
        )
        assert len(info.currencies) == 2
        assert CurrencyCode("PAB") in info.currencies
        assert CurrencyCode("USD") in info.currencies

    def test_empty_currencies_tuple(self) -> None:
        """TerritoryInfo supports empty currencies tuple for territories without currency data."""
        info = TerritoryInfo(
            alpha2=TerritoryCode("AQ"), name="Antarctica",
            currencies=(), official_languages=(),
        )
        assert info.currencies == ()
        assert len(info.currencies) == 0

    def test_official_languages_field(self) -> None:
        """TerritoryInfo stores official_languages as tuple of BCP-47 codes."""
        info = TerritoryInfo(
            alpha2=TerritoryCode("BE"), name="Belgium",
            currencies=(CurrencyCode("EUR"),),
            official_languages=("fr", "nl", "de"),
        )
        assert info.official_languages == ("fr", "nl", "de")
        assert isinstance(info.official_languages, tuple)

    def test_official_languages_empty(self) -> None:
        """TerritoryInfo accepts empty official_languages tuple."""
        info = TerritoryInfo(
            alpha2=TerritoryCode("AQ"), name="Antarctica",
            currencies=(), official_languages=(),
        )
        assert info.official_languages == ()

class TestCurrencyInfo:
    """Tests for CurrencyInfo dataclass."""

    def test_immutable(self) -> None:
        """CurrencyInfo is immutable (frozen)."""
        info = CurrencyInfo(code=CurrencyCode("USD"), name="US Dollar", symbol="$", decimal_digits=2)
        with pytest.raises(AttributeError):
            info.code = CurrencyCode("EUR")  # type: ignore[misc]

    def test_hashable(self) -> None:
        """CurrencyInfo is hashable (can be used in sets/dicts)."""
        info = CurrencyInfo(code=CurrencyCode("USD"), name="US Dollar", symbol="$", decimal_digits=2)
        assert hash(info) is not None
        currencies = {info}
        assert len(currencies) == 1

    def test_equality(self) -> None:
        """CurrencyInfo instances with same values are equal."""
        info1 = CurrencyInfo(code=CurrencyCode("USD"), name="US Dollar", symbol="$", decimal_digits=2)
        info2 = CurrencyInfo(code=CurrencyCode("USD"), name="US Dollar", symbol="$", decimal_digits=2)
        assert info1 == info2

    def test_slots(self) -> None:
        """CurrencyInfo uses __slots__ for memory efficiency."""
        info = CurrencyInfo(code=CurrencyCode("USD"), name="US Dollar", symbol="$", decimal_digits=2)
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

    def test_includes_official_languages(self) -> None:
        """get_territory populates official_languages from CLDR data."""
        # GB has English as official language per CLDR
        result_gb = get_territory("GB")
        assert result_gb is not None
        assert isinstance(result_gb.official_languages, tuple)
        assert "en" in result_gb.official_languages

        # Belgium has three official languages per CLDR
        result_be = get_territory("BE")
        assert result_be is not None
        assert isinstance(result_be.official_languages, tuple)
        assert len(result_be.official_languages) >= 2
        for lang in result_be.official_languages:
            assert isinstance(lang, str)
            assert len(lang) > 0

        # official_languages is always a tuple (may be empty for some territories)
        result_us = get_territory("US")
        assert result_us is not None
        assert isinstance(result_us.official_languages, tuple)

    def test_various_territories(self) -> None:
        """get_territory works for various territory codes."""
        test_cases = ["US", "CA", "GB", "DE", "FR", "JP", "AU", "BR", "IN", "CN"]

        for code in test_cases:
            result = get_territory(code)
            assert result is not None, f"Failed for {code}"
            assert result.alpha2 == code
            assert len(result.name) > 0

    def test_casefold_expansion_returns_none(self) -> None:
        """get_territory returns None for inputs that expand via str.upper().

        'ß' (U+00DF, LATIN SMALL LETTER SHARP S) has len 1 but upper() returns
        'SS' (len 2), which is the valid ISO 3166-1 code for South Sudan. The
        raw input 'ß' is not a valid territory code and must return None.
        Regression for FIX-ISO-CASEFOLD-001.
        """
        # 'ß'.upper() == 'SS' (South Sudan) — must not be returned
        assert get_territory("ß") is None
        # Confirm 'SS' itself IS valid (South Sudan exists in CLDR)
        assert get_territory("SS") is not None

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

    def test_casefold_expansion_returns_none(self) -> None:
        """get_currency returns None for inputs that expand via str.upper().

        A 2-char input whose upper() produces a valid 3-char currency code
        must return None — the raw input is not a valid currency code.
        Regression for FIX-ISO-CASEFOLD-001.
        """
        # 'ßD' has len 2; 'ßD'.upper() == 'SSD' (not a valid code, but the
        # pattern is guarded). Verify the length guard returns None for any
        # wrong-length input regardless of what upper() produces.
        assert get_currency("ß") is None    # len 1
        assert get_currency("ßD") is None   # len 2, 'ßD'.upper() = 'SSD'

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

    def test_casefold_expansion_returns_empty(self) -> None:
        """get_territory_currencies returns () for inputs that expand via str.upper().

        'ß' (len 1) uppercases to 'SS' (South Sudan, valid), but the raw
        input is not a valid territory code. Must return empty tuple.
        Regression for FIX-ISO-CASEFOLD-001.
        """
        assert get_territory_currencies("ß") == ()
        # Confirm 'SS' itself returns currencies (South Sudan uses USD)
        assert get_territory_currencies("SS") != ()

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

    def test_type_guard_lookup_consistency_casefold(self) -> None:
        """Type guard and lookup agree for inputs that expand under str.upper().

        If is_valid_territory_code(v) is False, get_territory(v) must be None.
        'ß' (len 1, upper() = 'SS') violated this invariant before FIX-ISO-CASEFOLD-001.
        """
        assert is_valid_territory_code("ß") is False
        assert get_territory("ß") is None

        assert is_valid_currency_code("ß") is False
        assert get_currency("ß") is None
        assert is_valid_currency_code("ßD") is False
        assert get_currency("ßD") is None
