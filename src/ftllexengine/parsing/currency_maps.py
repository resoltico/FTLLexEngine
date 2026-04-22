"""Currency map data and CLDR-backed lookup helpers."""

from __future__ import annotations

import functools
from typing import Any

from ftllexengine.core.babel_compat import (
    get_babel_numbers,
    get_locale_class,
    get_locale_identifiers_func,
    get_unknown_locale_error_class,
    is_babel_available,
)
from ftllexengine.core.locale_utils import normalize_locale

ISO_CURRENCY_CODE_LENGTH: int = 3

_FAST_TIER_UNAMBIGUOUS_SYMBOLS: dict[str, str] = {
    "\u20ac": "EUR",
    "\u20a4": "ITL",
    "\u20b9": "INR",
    "\u20a9": "KRW",
    "\u20ab": "VND",
    "\u20ae": "MNT",
    "\u20b1": "PHP",
    "\u20b4": "UAH",
    "\u20b8": "KZT",
    "\u20ba": "TRY",
    "\u20bd": "RUB",
    "\u20be": "GEL",
    "\u20bf": "BTC",
    "\u20b2": "PYG",
    "\u20aa": "ILS",
    "\u20bc": "AZN",
    "\u20a6": "NGN",
    "\u20b5": "GHS",
    "zl": "PLN",
    "Ft": "HUF",
    "Ls": "LVL",
    "Lt": "LTL",
}

_FAST_TIER_AMBIGUOUS_SYMBOLS: frozenset[str] = frozenset(
    {
        "$",
        "kr",
        "R",
        "R$",
        "S/",
        "\u00a5",
        "\u00a3",
    }
)

_AMBIGUOUS_SYMBOL_LOCALE_RESOLUTION: dict[tuple[str, str], str] = {
    ("\u00a5", "zh"): "CNY",
    ("$", "en_us"): "USD",
    ("$", "en_ca"): "CAD",
    ("$", "en_au"): "AUD",
    ("$", "en_nz"): "NZD",
    ("$", "en_sg"): "SGD",
    ("$", "en_hk"): "HKD",
    ("$", "es_mx"): "MXN",
    ("$", "es_ar"): "ARS",
    ("$", "es_cl"): "CLP",
    ("$", "es_co"): "COP",
    ("\u00a3", "en_gb"): "GBP",
    ("\u00a3", "en"): "GBP",
    ("\u00a3", "ar_eg"): "EGP",
    ("\u00a3", "ar"): "EGP",
    ("\u00a3", "en_gi"): "GIP",
    ("\u00a3", "en_fk"): "FKP",
    ("\u00a3", "en_sh"): "SHP",
    ("\u00a3", "en_ss"): "SSP",
}

_AMBIGUOUS_SYMBOL_DEFAULTS: dict[str, str] = {
    "\u00a5": "JPY",
    "\u00a3": "GBP",
    "$": "USD",
    "kr": "SEK",
    "R": "ZAR",
    "R$": "BRL",
    "S/": "PEN",
}

_FAST_TIER_LOCALE_CURRENCIES: dict[str, str] = {
    "en_us": "USD",
    "es_us": "USD",
    "en_ca": "CAD",
    "fr_ca": "CAD",
    "es_mx": "MXN",
    "de_de": "EUR",
    "de_at": "EUR",
    "fr_fr": "EUR",
    "it_it": "EUR",
    "es_es": "EUR",
    "pt_pt": "EUR",
    "nl_nl": "EUR",
    "fi_fi": "EUR",
    "el_gr": "EUR",
    "et_ee": "EUR",
    "lt_lt": "EUR",
    "lv_lv": "EUR",
    "sk_sk": "EUR",
    "sl_si": "EUR",
    "en_gb": "GBP",
    "de_ch": "CHF",
    "fr_ch": "CHF",
    "it_ch": "CHF",
    "sv_se": "SEK",
    "no_no": "NOK",
    "da_dk": "DKK",
    "pl_pl": "PLN",
    "cs_cz": "CZK",
    "hu_hu": "HUF",
    "ro_ro": "RON",
    "bg_bg": "BGN",
    "hr_hr": "HRK",
    "uk_ua": "UAH",
    "ru_ru": "RUB",
    "is_is": "ISK",
    "ja_jp": "JPY",
    "zh_cn": "CNY",
    "zh_tw": "TWD",
    "zh_hk": "HKD",
    "ko_kr": "KRW",
    "hi_in": "INR",
    "th_th": "THB",
    "vi_vn": "VND",
    "id_id": "IDR",
    "ms_my": "MYR",
    "fil_ph": "PHP",
    "en_sg": "SGD",
    "en_au": "AUD",
    "en_nz": "NZD",
    "ar_sa": "SAR",
    "ar_eg": "EGP",
    "ar_ae": "AED",
    "he_il": "ILS",
    "tr_tr": "TRY",
    "en_za": "ZAR",
    "pt_br": "BRL",
    "es_ar": "ARS",
    "es_cl": "CLP",
    "es_co": "COP",
    "es_pe": "PEN",
}

_FAST_TIER_VALID_CODES: frozenset[str] = frozenset(
    {
        "USD",
        "EUR",
        "GBP",
        "JPY",
        "CNY",
        "CHF",
        "CAD",
        "AUD",
        "NZD",
        "HKD",
        "SGD",
        "SEK",
        "NOK",
        "DKK",
        "ISK",
        "PLN",
        "CZK",
        "HUF",
        "RON",
        "BGN",
        "HRK",
        "UAH",
        "RUB",
        "TRY",
        "ILS",
        "INR",
        "KRW",
        "THB",
        "VND",
        "IDR",
        "MYR",
        "PHP",
        "TWD",
        "SAR",
        "AED",
        "EGP",
        "ZAR",
        "BRL",
        "ARS",
        "CLP",
        "COP",
        "PEN",
        "MXN",
        "KZT",
        "GEL",
        "AZN",
        "NGN",
        "GHS",
        "BTC",
    }
)

_SYMBOL_LOOKUP_LOCALE_IDS: tuple[str, ...] = (
    "en_US",
    "en_GB",
    "en_CA",
    "en_AU",
    "en_NZ",
    "en_SG",
    "en_HK",
    "en_IN",
    "de_DE",
    "de_CH",
    "de_AT",
    "fr_FR",
    "fr_CH",
    "fr_CA",
    "es_ES",
    "es_MX",
    "es_AR",
    "it_IT",
    "it_CH",
    "nl_NL",
    "pt_PT",
    "pt_BR",
    "ja_JP",
    "zh_CN",
    "zh_TW",
    "zh_HK",
    "ko_KR",
    "ru_RU",
    "pl_PL",
    "sv_SE",
    "no_NO",
    "da_DK",
    "fi_FI",
    "tr_TR",
    "ar_SA",
    "ar_EG",
    "he_IL",
    "hi_IN",
    "th_TH",
    "vi_VN",
    "id_ID",
    "ms_MY",
    "fil_PH",
    "lv_LV",
    "et_EE",
    "lt_LT",
    "cs_CZ",
    "sk_SK",
    "hu_HU",
    "ro_RO",
    "bg_BG",
    "hr_HR",
    "sl_SI",
    "sr_RS",
    "uk_UA",
    "ka_GE",
    "az_AZ",
    "kk_KZ",
    "is_IS",
)


def resolve_ambiguous_symbol(
    symbol: str,
    locale_code: str | None = None,
) -> str | None:
    """Resolve ambiguous currency symbols using locale context when available."""
    if symbol not in _FAST_TIER_AMBIGUOUS_SYMBOLS:
        return None

    if locale_code:
        normalized = normalize_locale(locale_code)
        exact_key = (symbol, normalized)
        if exact_key in _AMBIGUOUS_SYMBOL_LOCALE_RESOLUTION:
            return _AMBIGUOUS_SYMBOL_LOCALE_RESOLUTION[exact_key]

        if "_" in normalized:
            lang_prefix = normalized.split("_")[0]
            prefix_key = (symbol, lang_prefix)
            if prefix_key in _AMBIGUOUS_SYMBOL_LOCALE_RESOLUTION:
                return _AMBIGUOUS_SYMBOL_LOCALE_RESOLUTION[prefix_key]

    return _AMBIGUOUS_SYMBOL_DEFAULTS.get(symbol)


def _collect_all_currencies(
    locale_ids: list[str],
    locale_parse: Any,
    unknown_locale_error: type[Exception],
) -> set[str]:
    all_currencies: set[str] = set()
    for locale_id in locale_ids:
        try:
            locale = locale_parse(locale_id)
            if hasattr(locale, "currencies") and locale.currencies:
                all_currencies.update(locale.currencies.keys())
        except (unknown_locale_error, ValueError, AttributeError, KeyError):
            continue
    return all_currencies


def _build_symbol_mappings(
    all_currencies: set[str],
    locale_ids: list[str],
    locale_parse: Any,
    unknown_locale_error: type[Exception],
    get_currency_symbol: Any,
) -> tuple[dict[str, str], set[str]]:
    symbol_to_codes: dict[str, set[str]] = {}
    symbol_lookup_locales = [
        locale_parse(locale_id)
        for locale_id in _SYMBOL_LOOKUP_LOCALE_IDS
        if locale_id in locale_ids
    ]

    for currency_code in all_currencies:
        for locale in symbol_lookup_locales:
            try:
                symbol = get_currency_symbol(currency_code, locale=locale)
                is_iso_format = (
                    len(symbol) == ISO_CURRENCY_CODE_LENGTH
                    and symbol.isupper()
                    and symbol.isalpha()
                )
                if symbol and symbol != currency_code and not is_iso_format:
                    symbol_to_codes.setdefault(symbol, set()).add(currency_code)
            except (unknown_locale_error, ValueError, AttributeError, KeyError):
                continue

    unambiguous_map: dict[str, str] = {}
    ambiguous_set: set[str] = set()
    for symbol, codes in symbol_to_codes.items():
        if len(codes) == 1:
            unambiguous_map[symbol] = next(iter(codes))
        else:
            ambiguous_set.add(symbol)

    return unambiguous_map, ambiguous_set


def _build_locale_currency_map(
    locale_ids: list[str],
    locale_parse: Any,
    unknown_locale_error: type[Exception],
    get_territory_currencies: Any,
) -> dict[str, str]:
    locale_to_currency: dict[str, str] = {}
    for locale_id in locale_ids:
        try:
            locale = locale_parse(locale_id)
            if not locale.territory:
                continue
            territory_currencies = get_territory_currencies(locale.territory)
            if territory_currencies:
                locale_str = str(locale)
                if "_" in locale_str:
                    locale_to_currency[locale_str] = territory_currencies[0]
        except (unknown_locale_error, ValueError, AttributeError, KeyError):
            continue
    return locale_to_currency


@functools.cache
def _build_currency_maps_from_cldr() -> tuple[
    dict[str, str], set[str], dict[str, str], frozenset[str]
]:
    if not is_babel_available():
        return ({}, set(), {}, frozenset())

    locale_class = get_locale_class()
    unknown_locale_error_class = get_unknown_locale_error_class()
    locale_identifiers_fn = get_locale_identifiers_func()
    babel_numbers = get_babel_numbers()
    get_currency_symbol = babel_numbers.get_currency_symbol
    get_territory_currencies = babel_numbers.get_territory_currencies

    all_locale_ids = list(locale_identifiers_fn())
    all_currencies = _collect_all_currencies(
        all_locale_ids, locale_class.parse, unknown_locale_error_class
    )
    unambiguous_map, ambiguous_set = _build_symbol_mappings(
        all_currencies,
        all_locale_ids,
        locale_class.parse,
        unknown_locale_error_class,
        get_currency_symbol,
    )
    locale_to_currency = _build_locale_currency_map(
        all_locale_ids,
        locale_class.parse,
        unknown_locale_error_class,
        get_territory_currencies,
    )
    return (unambiguous_map, ambiguous_set, locale_to_currency, frozenset(all_currencies))


def _get_currency_maps_fast() -> tuple[
    dict[str, str], frozenset[str], dict[str, str], frozenset[str]
]:
    return (
        _FAST_TIER_UNAMBIGUOUS_SYMBOLS,
        _FAST_TIER_AMBIGUOUS_SYMBOLS,
        _FAST_TIER_LOCALE_CURRENCIES,
        _FAST_TIER_VALID_CODES,
    )


def _get_currency_maps_full() -> tuple[dict[str, str], set[str], dict[str, str], frozenset[str]]:
    return _build_currency_maps_from_cldr()


@functools.cache
def _get_currency_maps() -> tuple[dict[str, str], set[str], dict[str, str], frozenset[str]]:
    fast_symbols, fast_ambiguous, fast_locales, fast_codes = _get_currency_maps_fast()
    full_symbols, full_ambiguous, full_locales, full_codes = _get_currency_maps_full()
    return (
        {**full_symbols, **fast_symbols},
        full_ambiguous | set(fast_ambiguous),
        {**full_locales, **fast_locales},
        full_codes | fast_codes,
    )


def clear_currency_caches() -> None:
    """Clear cached currency map data."""
    _get_currency_maps.cache_clear()
    _build_currency_maps_from_cldr.cache_clear()
