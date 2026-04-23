"""ISO lookup and listing helpers backed by Babel CLDR data."""

from __future__ import annotations

from functools import lru_cache

from ftllexengine.constants import (
    ISO_4217_DECIMAL_DIGITS,
    ISO_4217_DEFAULT_DECIMALS,
    ISO_4217_VALID_CODES,
    MAX_CURRENCY_CACHE_SIZE,
    MAX_LOCALE_CACHE_SIZE,
    MAX_TERRITORY_CACHE_SIZE,
)
from ftllexengine.core.locale_utils import normalize_locale
from ftllexengine.introspection.iso_babel import (
    _get_babel_currencies,
    _get_babel_currency_name,
    _get_babel_currency_symbol,
    _get_babel_official_languages,
    _get_babel_territories,
    _get_babel_territory_currencies,
)
from ftllexengine.introspection.iso_types import (
    CurrencyCode,
    CurrencyInfo,
    TerritoryCode,
    TerritoryInfo,
)


@lru_cache(maxsize=MAX_TERRITORY_CACHE_SIZE)
def _get_territory_impl(
    code_upper: str,
    locale_norm: str,
) -> TerritoryInfo | None:
    """Internal cached implementation for get_territory."""
    territories = _get_babel_territories(locale_norm)

    if code_upper not in territories:
        return None

    name = territories[code_upper]
    currencies = get_territory_currencies(code_upper)
    official_languages = _get_babel_official_languages(code_upper)

    return TerritoryInfo(
        alpha2=TerritoryCode(code_upper),
        name=name,
        currencies=currencies,
        official_languages=official_languages,
    )


def get_territory(
    code: str,
    locale: str = "en",
) -> TerritoryInfo | None:
    """Look up ISO 3166-1 territory by alpha-2 code."""
    if len(code) != 2:
        return None
    return _get_territory_impl(code.upper(), normalize_locale(locale))


@lru_cache(maxsize=MAX_CURRENCY_CACHE_SIZE)
def _get_currency_impl(
    code_upper: str,
    locale_norm: str,
) -> CurrencyInfo | None:
    """Internal cached implementation for get_currency."""
    name = _get_babel_currency_name(code_upper, locale_norm)

    if name is None:
        return None

    symbol = _get_babel_currency_symbol(code_upper, locale_norm)
    decimal_digits = ISO_4217_DECIMAL_DIGITS.get(code_upper, ISO_4217_DEFAULT_DECIMALS)

    return CurrencyInfo(
        code=CurrencyCode(code_upper),
        name=name,
        symbol=symbol,
        decimal_digits=decimal_digits,
    )


def get_currency(
    code: str,
    locale: str = "en",
) -> CurrencyInfo | None:
    """Look up ISO 4217 currency by code."""
    if len(code) != 3:
        return None
    return _get_currency_impl(code.upper(), normalize_locale(locale))


def get_currency_decimal_digits(code: str) -> int | None:
    """Return ISO 4217 standard decimal precision for a currency code."""
    if len(code) != 3:
        return None
    code_upper = code.upper()
    if code_upper not in ISO_4217_VALID_CODES:
        return None
    return ISO_4217_DECIMAL_DIGITS.get(code_upper, ISO_4217_DEFAULT_DECIMALS)


@lru_cache(maxsize=MAX_LOCALE_CACHE_SIZE)
def _list_territories_impl(
    locale_norm: str,
) -> frozenset[TerritoryInfo]:
    """Internal cached implementation for list_territories."""
    territories = _get_babel_territories(locale_norm)
    result: set[TerritoryInfo] = set()

    for code, name in territories.items():
        if len(code) == 2 and code.isalpha() and code.isupper():
            currencies = get_territory_currencies(code)
            official_languages = _get_babel_official_languages(code)
            result.add(
                TerritoryInfo(
                    alpha2=TerritoryCode(code),
                    name=name,
                    currencies=currencies,
                    official_languages=official_languages,
                )
            )

    return frozenset(result)


def list_territories(
    locale: str = "en",
) -> frozenset[TerritoryInfo]:
    """List all known ISO 3166-1 territories."""
    return _list_territories_impl(normalize_locale(locale))


@lru_cache(maxsize=MAX_LOCALE_CACHE_SIZE)
def _list_currencies_impl(
    locale_norm: str,
) -> frozenset[CurrencyInfo]:
    """Internal cached implementation for list_currencies."""
    currencies_en = _get_babel_currencies()
    result: set[CurrencyInfo] = set()

    for code, english_name in currencies_en.items():
        if len(code) == 3 and code.isalpha() and code.isupper():
            info = _get_currency_impl(code, locale_norm)
            if info is not None:
                result.add(info)
            else:
                symbol = _get_babel_currency_symbol(code, locale_norm)
                decimal_digits = ISO_4217_DECIMAL_DIGITS.get(
                    code, ISO_4217_DEFAULT_DECIMALS
                )
                result.add(
                    CurrencyInfo(
                        code=CurrencyCode(code),
                        name=english_name,
                        symbol=symbol,
                        decimal_digits=decimal_digits,
                    )
                )

    return frozenset(result)


def list_currencies(
    locale: str = "en",
) -> frozenset[CurrencyInfo]:
    """List all known ISO 4217 currencies."""
    return _list_currencies_impl(normalize_locale(locale))


@lru_cache(maxsize=MAX_TERRITORY_CACHE_SIZE)
def _get_territory_currencies_impl(territory_upper: str) -> tuple[CurrencyCode, ...]:
    """Internal cached implementation for get_territory_currencies."""
    currencies = _get_babel_territory_currencies(territory_upper)
    return tuple(CurrencyCode(c) for c in currencies)


def get_territory_currencies(territory: str) -> tuple[CurrencyCode, ...]:
    """Get all active legal tender currencies for a territory."""
    if len(territory) != 2:
        return ()
    return _get_territory_currencies_impl(territory.upper())
