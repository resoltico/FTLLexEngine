"""Currency parsing with locale awareness.

API: parse_currency() returns tuple[tuple[Decimal, str] | None, tuple[FrozenFluentError, ...]].
Parse errors returned in tuple. Raises BabelImportError if Babel not installed.

Thread-safe. Uses Babel for currency symbol mapping and number parsing.
All currency data sourced from Unicode CLDR via Babel.

Babel Dependency:
    This module requires Babel for CLDR data. Import is deferred to function call
    time to support parser-only installations. Clear error message provided when
    Babel is missing.

Data Architecture:
    - Fast Tier: Hardcoded common currencies for merge-priority and Babel-absent fallback
    - Full Tier: Complete CLDR scan (lazy-loaded via @functools.cache on first access)
    - Merged maps: Fast tier overrides full tier for unambiguous symbol assignments

Symbol Detection:
    Uses a single regex pattern built from the complete merged symbol set (fast tier +
    CLDR). Symbols are sorted longest-first to guarantee correct detection of multi-char
    symbols (e.g., "Rs" before "R", "kr." before "kr", "$AU" before "$"). The CLDR scan
    cost (~200-500ms) is incurred once per process on first parse_currency() call, then
    cached via @functools.cache.

Architecture:
    Uses @functools.cache for thread-safe, lazy-loaded CLDR data access.
    - Locale-aware symbol resolution for ambiguous symbols via resolve_ambiguous_symbol()
    - Consistent with dates.py pattern for CLDR data access

Python 3.13+.
"""
# ruff: noqa: ERA001 - Section comments in data structures are documentation, not dead code

import functools
import re
from decimal import Decimal
from typing import Any

from ftllexengine.core.babel_compat import (
    get_babel_numbers,
    get_locale_class,
    get_locale_identifiers_func,
    get_number_format_error_class,
    get_parse_decimal_func,
    get_unknown_locale_error_class,
    is_babel_available,
    require_babel,
)
from ftllexengine.core.locale_utils import normalize_locale
from ftllexengine.diagnostics import ErrorCategory, FrozenErrorContext, FrozenFluentError
from ftllexengine.diagnostics.templates import ErrorTemplate

__all__ = ["clear_currency_caches", "parse_currency"]

# ISO 4217 currency codes are exactly 3 uppercase ASCII letters.
# This is per the ISO 4217 standard and is guaranteed not to change.
ISO_CURRENCY_CODE_LENGTH: int = 3

# =============================================================================
# FAST TIER: Common currencies with unambiguous symbols (no CLDR scan required)
# =============================================================================
# These symbols map to exactly one currency worldwide.
# Loaded immediately at import time (zero CLDR overhead).
_FAST_TIER_UNAMBIGUOUS_SYMBOLS: dict[str, str] = {
    # European currencies
    "\u20ac": "EUR",  # Euro sign
    # NOTE: Pound sign (U+00A3) is in ambiguous set (GBP, EGP, GIP, etc.)
    "\u20a4": "ITL",  # Lira sign (historical)
    # Asian currencies (truly unambiguous symbols)
    # NOTE: Yen sign (U+00A5) is NOT here - it's ambiguous (JPY vs CNY)
    "\u20b9": "INR",  # Indian Rupee
    "\u20a9": "KRW",  # Korean Won
    "\u20ab": "VND",  # Vietnamese Dong
    "\u20ae": "MNT",  # Mongolian Tugrik
    "\u20b1": "PHP",  # Philippine Peso
    "\u20b4": "UAH",  # Ukrainian Hryvnia
    "\u20b8": "KZT",  # Kazakhstani Tenge
    "\u20ba": "TRY",  # Turkish Lira
    "\u20bd": "RUB",  # Russian Ruble
    "\u20be": "GEL",  # Georgian Lari
    "\u20bf": "BTC",  # Bitcoin (cryptocurrency)
    # Americas (unambiguous)
    "\u20b2": "PYG",  # Paraguayan Guarani
    # Middle East
    "\u20aa": "ILS",  # Israeli New Shekel
    "\u20bc": "AZN",  # Azerbaijani Manat
    # African currencies
    "\u20a6": "NGN",  # Nigerian Naira
    "\u20b5": "GHS",  # Ghanaian Cedi
    # Text symbols (less common but unambiguous)
    "zl": "PLN",     # Polish Zloty (text form)
    "Ft": "HUF",     # Hungarian Forint
    "Ls": "LVL",     # Latvian Lats (historical, pre-Euro)
    "Lt": "LTL",     # Lithuanian Litas (historical, pre-Euro)
}

# Ambiguous symbols that require locale context or explicit currency code.
# These are NOT in the fast tier unambiguous map - they require context.
_FAST_TIER_AMBIGUOUS_SYMBOLS: frozenset[str] = frozenset({
    "$",     # USD, CAD, AUD, NZD, SGD, HKD, MXN, ARS, CLP, COP, etc.
    "kr",    # SEK, NOK, DKK, ISK
    "R",     # ZAR, BRL (R$), INR (historical)
    "R$",    # BRL
    "S/",    # PEN
    "\u00a5",  # Yen/Yuan sign - JPY (Japanese) or CNY (Chinese)
    "\u00a3",  # Pound sign - GBP (British), EGP (Egyptian), GIP (Gibraltar), etc.
})

# Locale-aware resolution for ambiguous symbols.
# Maps (symbol, locale_prefix) -> currency_code for context-sensitive resolution.
# Keys use lowercase normalized locale format (BCP-47 is case-insensitive).
_AMBIGUOUS_SYMBOL_LOCALE_RESOLUTION: dict[tuple[str, str], str] = {
    # Yen/Yuan sign: CNY for Chinese locales, JPY otherwise
    ("\u00a5", "zh"): "CNY",  # Chinese locales use Yuan
    # Dollar sign: locale-specific resolution
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
    # Pound sign: locale-specific resolution
    ("\u00a3", "en_gb"): "GBP",  # British Pound
    ("\u00a3", "en"): "GBP",     # English locales default to British
    ("\u00a3", "ar_eg"): "EGP",  # Egyptian Pound
    ("\u00a3", "ar"): "EGP",     # Arabic locales default to Egyptian
    ("\u00a3", "en_gi"): "GIP",  # Gibraltar Pound
    ("\u00a3", "en_fk"): "FKP",  # Falkland Islands Pound
    ("\u00a3", "en_sh"): "SHP",  # Saint Helena Pound
    ("\u00a3", "en_ss"): "SSP",  # South Sudanese Pound
}

# Default resolution for ambiguous symbols when locale doesn't match
_AMBIGUOUS_SYMBOL_DEFAULTS: dict[str, str] = {
    "\u00a5": "JPY",  # Default to JPY for non-Chinese locales
    "\u00a3": "GBP",  # Default to GBP when locale not recognized
    "$": "USD",       # Default to USD when locale not recognized
    "kr": "SEK",      # Default to SEK for Nordic kr
    "R": "ZAR",       # Default to ZAR for R
    "R$": "BRL",      # R$ is unambiguous as BRL
    "S/": "PEN",      # S/ is unambiguous as PEN
}

# Common locale-to-currency mappings for fast tier (no CLDR scan needed)
# Keys use lowercase normalized locale format (BCP-47 is case-insensitive).
_FAST_TIER_LOCALE_CURRENCIES: dict[str, str] = {
    # North America
    "en_us": "USD", "es_us": "USD",
    "en_ca": "CAD", "fr_ca": "CAD",
    "es_mx": "MXN",
    # Europe - Eurozone
    "de_de": "EUR", "de_at": "EUR",
    "fr_fr": "EUR", "it_it": "EUR",
    "es_es": "EUR", "pt_pt": "EUR",
    "nl_nl": "EUR", "fi_fi": "EUR",
    "el_gr": "EUR", "et_ee": "EUR",
    "lt_lt": "EUR", "lv_lv": "EUR",
    "sk_sk": "EUR", "sl_si": "EUR",
    # Europe - Non-Eurozone
    "en_gb": "GBP", "de_ch": "CHF", "fr_ch": "CHF", "it_ch": "CHF",
    "sv_se": "SEK", "no_no": "NOK", "da_dk": "DKK",
    "pl_pl": "PLN", "cs_cz": "CZK", "hu_hu": "HUF",
    "ro_ro": "RON", "bg_bg": "BGN", "hr_hr": "HRK",
    "uk_ua": "UAH", "ru_ru": "RUB", "is_is": "ISK",
    # Asia-Pacific
    "ja_jp": "JPY", "zh_cn": "CNY", "zh_tw": "TWD", "zh_hk": "HKD",
    "ko_kr": "KRW", "hi_in": "INR", "th_th": "THB",
    "vi_vn": "VND", "id_id": "IDR", "ms_my": "MYR",
    "fil_ph": "PHP", "en_sg": "SGD", "en_au": "AUD", "en_nz": "NZD",
    # Middle East / Africa
    "ar_sa": "SAR", "ar_eg": "EGP", "ar_ae": "AED",
    "he_il": "ILS", "tr_tr": "TRY",
    "en_za": "ZAR", "pt_br": "BRL",
    # South America
    "es_ar": "ARS", "es_cl": "CLP", "es_co": "COP", "es_pe": "PEN",
}

# Fast tier valid ISO codes (subset for quick validation before full CLDR)
_FAST_TIER_VALID_CODES: frozenset[str] = frozenset({
    "USD", "EUR", "GBP", "JPY", "CNY", "CHF", "CAD", "AUD", "NZD",
    "HKD", "SGD", "SEK", "NOK", "DKK", "ISK", "PLN", "CZK", "HUF",
    "RON", "BGN", "HRK", "UAH", "RUB", "TRY", "ILS", "INR", "KRW",
    "THB", "VND", "IDR", "MYR", "PHP", "TWD", "SAR", "AED", "EGP",
    "ZAR", "BRL", "ARS", "CLP", "COP", "PEN", "MXN", "KZT", "GEL",
    "AZN", "NGN", "GHS", "BTC",
})

# Curated list of locales for currency symbol lookup.
# Selected to cover major world currencies and regional variants.
# Add locales here to support additional currency symbol mappings.
_SYMBOL_LOOKUP_LOCALE_IDS: tuple[str, ...] = (
    "en_US", "en_GB", "en_CA", "en_AU", "en_NZ", "en_SG", "en_HK", "en_IN",
    "de_DE", "de_CH", "de_AT", "fr_FR", "fr_CH", "fr_CA",
    "es_ES", "es_MX", "es_AR", "it_IT", "it_CH", "nl_NL", "pt_PT", "pt_BR",
    "ja_JP", "zh_CN", "zh_TW", "zh_HK", "ko_KR",
    "ru_RU", "pl_PL", "sv_SE", "no_NO", "da_DK", "fi_FI",
    "tr_TR", "ar_SA", "ar_EG", "he_IL", "hi_IN",
    "th_TH", "vi_VN", "id_ID", "ms_MY", "fil_PH",
    "lv_LV", "et_EE", "lt_LT", "cs_CZ", "sk_SK", "hu_HU",
    "ro_RO", "bg_BG", "hr_HR", "sl_SI", "sr_RS",
    "uk_UA", "ka_GE", "az_AZ", "kk_KZ", "is_IS",
)

# =============================================================================
# Locale-Aware Symbol Resolution
# =============================================================================


def resolve_ambiguous_symbol(
    symbol: str,
    locale_code: str | None = None,
) -> str | None:
    """Resolve ambiguous symbol to currency code with locale context.

    Resolution order:
    1. Exact locale match in _AMBIGUOUS_SYMBOL_LOCALE_RESOLUTION
    2. Locale prefix match (e.g., "zh" for "zh_CN", "zh_TW")
    3. Default from _AMBIGUOUS_SYMBOL_DEFAULTS

    Args:
        symbol: The currency symbol to resolve
        locale_code: Optional locale for context-sensitive resolution

    Returns:
        ISO 4217 currency code, or None if symbol not in ambiguous set
    """
    if symbol not in _FAST_TIER_AMBIGUOUS_SYMBOLS:
        return None

    if locale_code:
        # Normalize locale for lookup
        normalized = normalize_locale(locale_code)

        # Try exact locale match first
        exact_key = (symbol, normalized)
        if exact_key in _AMBIGUOUS_SYMBOL_LOCALE_RESOLUTION:
            return _AMBIGUOUS_SYMBOL_LOCALE_RESOLUTION[exact_key]

        # Try locale prefix match (language code only)
        # e.g., "zh" matches "zh_CN", "zh_TW", "zh_HK"
        if "_" in normalized:
            lang_prefix = normalized.split("_")[0]
            prefix_key = (symbol, lang_prefix)
            if prefix_key in _AMBIGUOUS_SYMBOL_LOCALE_RESOLUTION:
                return _AMBIGUOUS_SYMBOL_LOCALE_RESOLUTION[prefix_key]

    # Fall back to default
    return _AMBIGUOUS_SYMBOL_DEFAULTS.get(symbol)


def _collect_all_currencies(
    locale_ids: list[str],
    locale_parse: Any,
    unknown_locale_error: type[Exception],
) -> set[str]:
    """Collect all currency codes from CLDR by scanning all locales.

    Ensures complete currency coverage (JPY, KRW, CNY, etc.).

    Args:
        locale_ids: All available CLDR locale identifiers.
        locale_parse: Babel's Locale.parse function.
        unknown_locale_error: Babel's UnknownLocaleError class.

    Returns:
        Set of all ISO 4217 currency codes found in CLDR.
    """
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
    """Build symbol-to-currency mappings, separating ambiguous from unambiguous.

    For each currency, finds all symbols it uses across a curated locale sample.
    A symbol is ambiguous if multiple currencies use it.

    Args:
        all_currencies: All ISO 4217 codes from CLDR.
        locale_ids: All available CLDR locale identifiers.
        locale_parse: Babel's Locale.parse function.
        unknown_locale_error: Babel's UnknownLocaleError class.
        get_currency_symbol: Babel's get_currency_symbol function.

    Returns:
        Tuple of (unambiguous_map, ambiguous_set):
        - unambiguous_map: Symbol -> single ISO 4217 code
        - ambiguous_set: Symbols mapping to multiple currencies
    """
    symbol_to_codes: dict[str, set[str]] = {}

    symbol_lookup_locales = [
        locale_parse(lid) for lid in _SYMBOL_LOOKUP_LOCALE_IDS
        if lid in locale_ids
    ]

    for currency_code in all_currencies:
        for locale in symbol_lookup_locales:
            try:
                symbol = get_currency_symbol(
                    currency_code, locale=locale,
                )
                is_iso_format = (
                    len(symbol) == ISO_CURRENCY_CODE_LENGTH
                    and symbol.isupper()
                    and symbol.isalpha()
                )
                if symbol and symbol != currency_code and not is_iso_format:
                    if symbol not in symbol_to_codes:
                        symbol_to_codes[symbol] = set()
                    symbol_to_codes[symbol].add(currency_code)
            except (
                unknown_locale_error, ValueError, AttributeError, KeyError,
            ):
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
    """Build locale-to-default-currency mapping from CLDR territory data.

    Args:
        locale_ids: All available CLDR locale identifiers.
        locale_parse: Babel's Locale.parse function.
        unknown_locale_error: Babel's UnknownLocaleError class.
        get_territory_currencies: Babel's get_territory_currencies function.

    Returns:
        Mapping of locale code -> default ISO 4217 currency code.
    """
    locale_to_currency: dict[str, str] = {}
    for locale_id in locale_ids:
        try:
            locale = locale_parse(locale_id)
            if not locale.territory:
                continue
            territory_currencies = get_territory_currencies(
                locale.territory,
            )
            if territory_currencies:
                locale_str = str(locale)
                if "_" in locale_str:
                    locale_to_currency[locale_str] = territory_currencies[0]
        except (
            unknown_locale_error, ValueError, AttributeError, KeyError,
        ):
            continue
    return locale_to_currency


@functools.cache
def _build_currency_maps_from_cldr() -> tuple[
    dict[str, str], set[str], dict[str, str], frozenset[str]
]:
    """Build currency maps from Unicode CLDR data via Babel.

    Thread-safe via functools.cache internal locking.
    Called once per process lifetime; subsequent calls return cached result.

    Orchestrates three sub-operations:
    1. Collect all currency codes from CLDR locale scan
    2. Build symbol-to-currency mappings (unambiguous vs ambiguous)
    3. Build locale-to-default-currency mapping from territory data

    Returns:
        Tuple of (symbol_to_code, ambiguous_symbols, locale_to_currency, valid_codes):
        - symbol_to_code: Unambiguous currency symbol -> ISO 4217 code
        - ambiguous_symbols: Symbols that map to multiple currencies
        - locale_to_currency: Locale code -> default ISO 4217 currency code
        - valid_codes: Frozenset of all valid ISO 4217 currency codes from CLDR
        Returns empty maps if Babel is not installed (fast tier still available).
    """
    if not is_babel_available():
        # Babel not installed - return empty maps, fast tier still available
        return ({}, set(), {}, frozenset())

    locale_class = get_locale_class()
    unknown_locale_error_class = get_unknown_locale_error_class()
    locale_identifiers_fn = get_locale_identifiers_func()
    babel_numbers = get_babel_numbers()
    get_currency_symbol = babel_numbers.get_currency_symbol
    get_territory_currencies = babel_numbers.get_territory_currencies

    all_locale_ids = list(locale_identifiers_fn())

    all_currencies = _collect_all_currencies(
        all_locale_ids, locale_class.parse, unknown_locale_error_class,
    )

    unambiguous_map, ambiguous_set = _build_symbol_mappings(
        all_currencies, all_locale_ids,
        locale_class.parse, unknown_locale_error_class, get_currency_symbol,
    )

    locale_to_currency = _build_locale_currency_map(
        all_locale_ids,
        locale_class.parse, unknown_locale_error_class, get_territory_currencies,
    )

    return (
        unambiguous_map, ambiguous_set,
        locale_to_currency, frozenset(all_currencies),
    )


def _get_currency_maps_fast() -> tuple[
    dict[str, str], frozenset[str], dict[str, str], frozenset[str]
]:
    """Get fast tier currency maps (no CLDR scan, immediate).

    Returns:
        Tuple of (symbol_to_code, ambiguous_symbols, locale_to_currency, valid_codes)
        from the fast tier (hardcoded common currencies).
    """
    return (
        _FAST_TIER_UNAMBIGUOUS_SYMBOLS,
        _FAST_TIER_AMBIGUOUS_SYMBOLS,
        _FAST_TIER_LOCALE_CURRENCIES,
        _FAST_TIER_VALID_CODES,
    )


def _get_currency_maps_full() -> tuple[dict[str, str], set[str], dict[str, str], frozenset[str]]:
    """Get full CLDR currency maps (lazy-loaded on first call).

    Thread-safe via functools.cache on _build_currency_maps_from_cldr.

    Returns:
        Tuple of (symbol_to_code, ambiguous_symbols, locale_to_currency, valid_codes)
        from complete CLDR data.
    """
    return _build_currency_maps_from_cldr()


@functools.cache
def _get_currency_maps() -> tuple[dict[str, str], set[str], dict[str, str], frozenset[str]]:
    """Get merged currency maps (fast tier + full CLDR).

    Thread-safe via functools.cache internal locking.
    Called once per process lifetime; subsequent calls return cached result.

    Tiered Loading Strategy:
        - Fast tier data is always included (zero overhead)
        - Full CLDR data is merged in (loaded lazily on first call to this function)

    Returns:
        Tuple of (symbol_to_code, ambiguous_symbols, locale_to_currency, valid_codes):
        - symbol_to_code: Unambiguous currency symbol → ISO 4217 code
        - ambiguous_symbols: Symbols that map to multiple currencies
        - locale_to_currency: Locale code → default ISO 4217 currency code
        - valid_codes: Frozenset of all valid ISO 4217 currency codes from CLDR
    """
    # Get both tiers
    fast_symbols, fast_ambiguous, fast_locales, fast_codes = _get_currency_maps_fast()
    full_symbols, full_ambiguous, full_locales, full_codes = _get_currency_maps_full()

    # Merge: fast tier has priority for unambiguous symbols
    merged_symbols = {**full_symbols, **fast_symbols}  # fast overwrites full
    merged_ambiguous = full_ambiguous | set(fast_ambiguous)
    merged_locales = {**full_locales, **fast_locales}  # fast overwrites full
    merged_codes = full_codes | fast_codes

    return merged_symbols, merged_ambiguous, merged_locales, merged_codes


def _is_valid_iso_4217_format(code: str) -> bool:
    """Check if code matches ISO 4217 format: exactly 3 uppercase ASCII letters.

    This validates format only, not existence in CLDR database.
    Per ISO 4217 standard, currency codes are exactly 3 uppercase ASCII letters.
    """
    return (
        len(code) == ISO_CURRENCY_CODE_LENGTH
        and code.isascii()
        and code.isupper()
        and code.isalpha()
    )


def _resolve_currency_code(
    currency_str: str,
    locale_code: str,
    value: str,
    *,
    default_currency: str | None,
    infer_from_locale: bool,
) -> tuple[str | None, FrozenFluentError | None]:
    """Resolve currency string to ISO code with error handling.

    Helper function to reduce statement count in parse_currency.

    Args:
        currency_str: Currency symbol or ISO code from input
        locale_code: BCP 47 locale identifier
        value: Original input value (for error messages)
        default_currency: Explicit currency for ambiguous symbols
        infer_from_locale: Whether to infer currency from locale

    Returns:
        Tuple of (currency_code, error) - one will be None
    """
    is_iso_code = _is_valid_iso_4217_format(currency_str)

    symbol_map, ambiguous_symbols, locale_to_currency, valid_iso_codes = _get_currency_maps()

    if is_iso_code:
        # ISO code - validate against CLDR data
        if currency_str not in valid_iso_codes:
            diagnostic = ErrorTemplate.parse_currency_code_invalid(currency_str, value)
            context = FrozenErrorContext(
                input_value=str(value), locale_code=locale_code, parse_type="currency"
            )
            error = FrozenFluentError(
                str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
            )
            return (None, error)
        return (currency_str, None)

    # It's a symbol - check if ambiguous
    if currency_str in ambiguous_symbols:
        if default_currency:
            # Validate default_currency is a valid ISO 4217 format
            if not _is_valid_iso_4217_format(default_currency):
                diagnostic = ErrorTemplate.parse_currency_code_invalid(default_currency, value)
                context = FrozenErrorContext(
                    input_value=str(value), locale_code=locale_code, parse_type="currency"
                )
                error = FrozenFluentError(
                    str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
                )
                return (None, error)
            return (default_currency, None)
        if infer_from_locale:
            # Locale-aware resolution for ambiguous symbols
            resolved = resolve_ambiguous_symbol(currency_str, locale_code)
            if resolved:
                return (resolved, None)
            # Fall back to locale-to-currency mapping
            inferred = locale_to_currency.get(normalize_locale(locale_code))
            if inferred:
                return (inferred, None)
        # No resolution available
        diagnostic = ErrorTemplate.parse_currency_ambiguous(currency_str, value)
        context = FrozenErrorContext(
            input_value=str(value), locale_code=locale_code, parse_type="currency"
        )
        error = FrozenFluentError(
            str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
        )
        return (None, error)

    # Unambiguous symbol - use mapping
    mapped = symbol_map.get(currency_str)
    if mapped is None:
        diagnostic = ErrorTemplate.parse_currency_symbol_unknown(currency_str, value)
        context = FrozenErrorContext(
            input_value=str(value), locale_code=locale_code, parse_type="currency"
        )
        error = FrozenFluentError(
            str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
        )
        return (None, error)
    return (mapped, None)


@functools.cache
def _get_currency_pattern() -> re.Pattern[str]:
    """Compile currency detection regex from merged symbol maps.

    Builds a single pattern from the complete merged symbol set (fast tier +
    CLDR). Symbols are sorted longest-first to guarantee correct detection of
    multi-char symbols before their prefixes (e.g., "Rs" before "R", "kr."
    before "kr", "$AU" before "$").

    Thread-safe via functools.cache internal locking.
    Called once per process lifetime; subsequent calls return cached result.

    Returns:
        Compiled regex pattern matching:
        - ISO 4217 3-letter currency codes (e.g., EUR, USD, JPY) - matched first
        - All symbols from merged currency maps (unambiguous and ambiguous)

    Pattern Priority:
        1. ISO codes (3 uppercase ASCII letters) - matched first to avoid
           partial symbol matches (e.g., 'F' matching before 'FFF')
        2. Longer symbols matched before shorter to prevent partial matches
           (e.g., "Rs" before "R", "kr." before "kr")
    """
    symbol_map, ambiguous, _, _ = _get_currency_maps()

    # Collect all symbols from both maps
    all_symbols: set[str] = set(symbol_map.keys()) | ambiguous

    # Sort by length descending to match longer symbols first
    # This prevents "R" matching before "Rs" or "kr" before "kr."
    sorted_symbols = sorted(all_symbols, key=len, reverse=True)

    # Escape special regex characters in symbols
    escaped_symbols = [re.escape(sym) for sym in sorted_symbols]

    # Build pattern: ISO codes FIRST, then symbols
    # ISO codes first ensures 'FFF' matches as code, not partial symbol match
    if escaped_symbols:
        symbols_pattern = "|".join(escaped_symbols)
        pattern = rf"([A-Z]{{{ISO_CURRENCY_CODE_LENGTH}}}|{symbols_pattern})"
    else:
        # Fallback if no symbols found (shouldn't happen with CLDR)
        pattern = rf"([A-Z]{{{ISO_CURRENCY_CODE_LENGTH}}})"

    return re.compile(pattern)


def _detect_currency_symbol(
    value: str,
    locale_code: str,
) -> tuple[re.Match[str] | None, FrozenFluentError | None]:
    """Detect currency symbol or ISO code in input string.

    Uses a single longest-match-first regex built from the complete merged
    symbol set (fast tier + CLDR). This guarantees multi-char symbols are
    matched before their single-char prefixes (e.g., "Rs" before "R").

    Args:
        value: Currency string to search.
        locale_code: BCP 47 locale identifier (for error context).

    Returns:
        Tuple of (match, error) - exactly one is None.
    """
    pattern = _get_currency_pattern()
    match = pattern.search(value)

    if not match:
        diagnostic = ErrorTemplate.parse_currency_failed(
            value, locale_code, "No currency symbol or code found",
        )
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="currency",
        )
        error = FrozenFluentError(
            str(diagnostic),
            ErrorCategory.PARSE,
            diagnostic=diagnostic,
            context=context,
        )
        return (None, error)

    return (match, None)


def _parse_currency_amount(
    value: str,
    match: re.Match[str],
    locale: Any,
    locale_code: str,
    parse_decimal_fn: Any,
    number_format_error: type[Exception],
) -> tuple[Decimal | None, FrozenFluentError | None]:
    """Extract and parse the numeric amount from a currency string.

    Removes the matched currency symbol/code and parses the remainder
    as a locale-formatted number.

    Args:
        value: Original currency string.
        match: Regex match containing the currency symbol/code.
        locale: Babel Locale object.
        locale_code: BCP 47 locale identifier (for error context).
        parse_decimal_fn: Babel's parse_decimal function.
        number_format_error: Babel's NumberFormatError class.

    Returns:
        Tuple of (amount, error) - exactly one is None.
    """
    # Remove ONLY the matched occurrence, not all instances.
    # Prevents corruption if the symbol appears elsewhere in the string.
    number_str = (
        value[:match.start(1)] + value[match.end(1):]
    ).strip()

    try:
        amount = parse_decimal_fn(number_str, locale=locale)
    except number_format_error as e:
        diagnostic = ErrorTemplate.parse_amount_invalid(
            number_str, value, str(e),
        )
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="currency",
        )
        error = FrozenFluentError(
            str(diagnostic),
            ErrorCategory.PARSE,
            diagnostic=diagnostic,
            context=context,
        )
        return (None, error)

    return (amount, None)


def parse_currency(
    value: str,
    locale_code: str,
    *,
    default_currency: str | None = None,
    infer_from_locale: bool = False,
) -> tuple[tuple[Decimal, str] | None, tuple[FrozenFluentError, ...]]:
    """Parse locale-aware currency string to (amount, currency_code).

    Extracts both numeric value and currency code from formatted string.

    Ambiguous currency symbols ($, kr) require explicit default_currency
    or infer_from_locale=True. This prevents silent misidentification
    in multi-currency applications.

    Phases:
        1. Validate inputs (type check, locale parse)
        2. Detect currency symbol/code (longest-match-first regex)
        3. Resolve symbol to ISO 4217 code
        4. Parse numeric amount

    Args:
        value: Currency string (e.g., "100,50 EUR" for lv_LV, "$100" with default_currency)
        locale_code: BCP 47 locale identifier
        default_currency: ISO 4217 code for ambiguous symbols (e.g., "CAD" for "$")
        infer_from_locale: Infer currency from locale if symbol is ambiguous

    Returns:
        Tuple of (result, errors):
        - result: Tuple of (amount, currency_code), or None if parsing failed
        - errors: Tuple of FrozenFluentError (empty tuple on success)

    Raises:
        BabelImportError: If Babel is not installed

    Examples:
        >>> result, errors = parse_currency("EUR100.50", "en_US")
        >>> result
        (Decimal('100.50'), 'EUR')
        >>> errors
        ()

        >>> result, errors = parse_currency("100,50 EUR", "lv_LV")
        >>> result
        (Decimal('100.50'), 'EUR')

        >>> result, errors = parse_currency("USD 1,234.56", "en_US")
        >>> result
        (Decimal('1234.56'), 'USD')

        >>> result, errors = parse_currency("$100", "en_US", default_currency="USD")
        >>> result
        (Decimal('100'), 'USD')

        >>> result, errors = parse_currency("$100", "en_CA", default_currency="CAD")
        >>> result
        (Decimal('100'), 'CAD')

        >>> result, errors = parse_currency("$100", "en_CA", infer_from_locale=True)
        >>> result
        (Decimal('100'), 'CAD')

        >>> result, errors = parse_currency("$100", "en_US")
        >>> result is None
        True
        >>> len(errors)
        1

    Note:
        Ambiguous symbols: $ (USD/CAD/AUD/etc), kr (SEK/NOK/DKK/ISK)
        Always use ISO codes (USD, CAD, EUR) for unambiguous parsing.

    Thread Safety:
        Thread-safe. Uses Babel (no global state).
    """
    # Phase 1: Validate inputs
    require_babel("parse_currency")
    locale_class = get_locale_class()
    unknown_locale_error_class = get_unknown_locale_error_class()
    number_format_error_class = get_number_format_error_class()
    parse_decimal = get_parse_decimal_func()

    if not isinstance(value, str):
        diagnostic = ErrorTemplate.parse_currency_failed(  # type: ignore[unreachable]
            str(value),
            locale_code,
            f"Expected string, got {type(value).__name__}",
        )
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="currency",
        )
        return (None, (FrozenFluentError(
            str(diagnostic),
            ErrorCategory.PARSE,
            diagnostic=diagnostic,
            context=context,
        ),))

    try:
        locale = locale_class.parse(normalize_locale(locale_code))
    except (unknown_locale_error_class, ValueError):
        diagnostic = ErrorTemplate.parse_locale_unknown(locale_code)
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="currency",
        )
        return (None, (FrozenFluentError(
            str(diagnostic),
            ErrorCategory.PARSE,
            diagnostic=diagnostic,
            context=context,
        ),))

    # Phase 2: Detect currency symbol/code
    match, detect_error = _detect_currency_symbol(value, locale_code)
    if detect_error is not None or match is None:
        if detect_error is not None:
            return (None, (detect_error,))
        # Defensive: _detect_currency_symbol contract guarantees
        # exactly one of (match, error) is non-None.
        diagnostic = ErrorTemplate.parse_currency_failed(  # pragma: no cover
            value, locale_code, "No currency symbol or code found",
        )
        context = FrozenErrorContext(  # pragma: no cover
            input_value=str(value),
            locale_code=locale_code,
            parse_type="currency",
        )
        return (None, (FrozenFluentError(  # pragma: no cover
            str(diagnostic),
            ErrorCategory.PARSE,
            diagnostic=diagnostic,
            context=context,
        ),))

    currency_str = match.group(1)

    # Phase 3: Resolve symbol to ISO 4217 code
    currency_code, resolution_error = _resolve_currency_code(
        currency_str,
        locale_code,
        value,
        default_currency=default_currency,
        infer_from_locale=infer_from_locale,
    )
    if resolution_error is not None:
        return (None, (resolution_error,))
    if currency_code is None:
        # Defensive: _resolve_currency_code contract guarantees
        # exactly one of (code, error) is non-None.
        diagnostic = ErrorTemplate.parse_currency_failed(  # pragma: no cover
            value, locale_code, "Currency resolution failed",
        )
        context = FrozenErrorContext(  # pragma: no cover
            input_value=str(value),
            locale_code=locale_code,
            parse_type="currency",
        )
        return (None, (FrozenFluentError(  # pragma: no cover
            str(diagnostic),
            ErrorCategory.PARSE,
            diagnostic=diagnostic,
            context=context,
        ),))

    # Phase 4: Parse numeric amount
    amount, amount_error = _parse_currency_amount(
        value,
        match,
        locale,
        locale_code,
        parse_decimal,
        number_format_error_class,
    )
    if amount_error is not None or amount is None:
        if amount_error is not None:
            return (None, (amount_error,))
        # Defensive: _parse_currency_amount contract guarantees
        # exactly one of (amount, error) is non-None.
        diagnostic = ErrorTemplate.parse_currency_failed(  # pragma: no cover
            value, locale_code, "Amount parsing failed",
        )
        context = FrozenErrorContext(  # pragma: no cover
            input_value=str(value),
            locale_code=locale_code,
            parse_type="currency",
        )
        return (None, (FrozenFluentError(  # pragma: no cover
            str(diagnostic),
            ErrorCategory.PARSE,
            diagnostic=diagnostic,
            context=context,
        ),))

    return ((amount, currency_code), ())


def clear_currency_caches() -> None:
    """Clear all currency-related caches.

    Clears cached CLDR currency data from:
    - _build_currency_maps_from_cldr() - symbol-to-currency maps from CLDR scan
    - _get_currency_maps() - merged fast tier + full CLDR maps
    - _get_currency_pattern() - currency detection regex pattern

    Useful for:
    - Memory reclamation in long-running applications
    - Testing scenarios requiring fresh cache state
    - After Babel/CLDR data updates

    Thread-safe via functools.cache internal locking.

    Note:
        This function does NOT require Babel. It clears the caches
        regardless of whether Babel is installed. The fast tier data
        (hardcoded common currencies) remains available immediately after
        clearing; only the full CLDR scan results are invalidated.

    Example:
        >>> from ftllexengine.parsing.currency import clear_currency_caches
        >>> clear_currency_caches()  # Clears all cached currency data
    """
    _build_currency_maps_from_cldr.cache_clear()
    _get_currency_maps.cache_clear()
    _get_currency_pattern.cache_clear()
