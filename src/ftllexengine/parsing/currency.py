"""Currency parsing with locale awareness.

API: parse_currency() returns tuple[tuple[Decimal, str] | None, tuple[FluentParseError, ...]].
Parse errors returned in tuple. Raises BabelImportError if Babel not installed.

Thread-safe. Uses Babel for currency symbol mapping and number parsing.
All currency data sourced from Unicode CLDR via Babel.

Babel Dependency:
    This module requires Babel for CLDR data. Import is deferred to function call
    time to support parser-only installations. Clear error message provided when
    Babel is missing.

Tiered Loading Strategy:
    - Fast Tier: Common currencies with hardcoded unambiguous symbols (immediate)
    - Full Tier: Complete CLDR scan (lazy-loaded via @functools.cache on first access)
    This provides sub-millisecond cold start for common currencies while maintaining
    complete CLDR coverage for edge cases.

Performance:
    Cold start latency for the full CLDR scan is approximately 200-500ms depending
    on Babel version and the number of locales installed. This scan runs once per
    process (via @functools.cache) and only triggers when encountering an ambiguous
    currency symbol not resolvable in the fast tier. Most applications using common
    currencies (EUR, USD, GBP, JPY, CNY, INR, etc.) will never trigger the full scan.

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

from ftllexengine.diagnostics import FluentParseError
from ftllexengine.diagnostics.templates import ErrorTemplate
from ftllexengine.locale_utils import normalize_locale

__all__ = ["parse_currency"]

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


@functools.cache
def _build_currency_maps_from_cldr() -> tuple[
    dict[str, str], set[str], dict[str, str], frozenset[str]
]:
    """Build currency maps from Unicode CLDR data via Babel.

    Thread-safe via functools.cache internal locking.
    Called once per process lifetime; subsequent calls return cached result.

    Scans all available locales and currencies in CLDR to build:
    1. Symbol -> ISO code mapping (for unambiguous symbols)
    2. Set of ambiguous symbols (symbols used by multiple currencies)
    3. Locale -> default currency mapping (from territory data)
    4. Set of all valid ISO 4217 currency codes (for validation)

    Returns:
        Tuple of (symbol_to_code, ambiguous_symbols, locale_to_currency, valid_codes):
        - symbol_to_code: Unambiguous currency symbol → ISO 4217 code
        - ambiguous_symbols: Symbols that map to multiple currencies
        - locale_to_currency: Locale code → default ISO 4217 currency code
        - valid_codes: Frozenset of all valid ISO 4217 currency codes from CLDR
        Returns empty maps if Babel is not installed (fast tier still available).
    """
    # Lazy import to support parser-only installations
    try:
        from babel import Locale, UnknownLocaleError  # noqa: PLC0415
        from babel.localedata import locale_identifiers  # noqa: PLC0415
        from babel.numbers import (  # noqa: PLC0415
            get_currency_symbol,
            get_territory_currencies,
        )
    except ImportError:
        # Babel not installed - return empty maps, fast tier still available
        return ({}, set(), {}, frozenset())

    # Step 1: Build symbol → currency codes mapping
    # Key insight: A symbol is ambiguous if multiple currency codes use it
    symbol_to_codes: dict[str, set[str]] = {}

    # Get all currency codes from CLDR by scanning ALL locales
    # This ensures complete currency coverage (JPY, KRW, CNY, etc.)
    # Performance: This runs once at initialization, cached via functools.cache
    all_currencies: set[str] = set()
    all_locale_ids = list(locale_identifiers())

    for locale_id in all_locale_ids:
        try:
            locale = Locale.parse(locale_id)
            if hasattr(locale, "currencies") and locale.currencies:
                all_currencies.update(locale.currencies.keys())
        except (UnknownLocaleError, ValueError, AttributeError, KeyError):
            # Expected failures: invalid locale identifiers, missing currency data
            continue

    # Step 2: For each currency, find all symbols it uses across locales
    # Use curated locale sample for symbol lookup (performance + coverage)
    symbol_lookup_locales = [
        Locale.parse(lid) for lid in _SYMBOL_LOOKUP_LOCALE_IDS
        if lid in all_locale_ids
    ]

    for currency_code in all_currencies:
        for locale in symbol_lookup_locales:
            try:
                symbol = get_currency_symbol(currency_code, locale=locale)

                # Only map real symbols (not the currency code itself)
                # Filter out ISO 4217 codes (3-letter alphabetic) that are just the code itself
                if (symbol and
                    symbol != currency_code and
                    not (len(symbol) == ISO_CURRENCY_CODE_LENGTH
                         and symbol.isupper() and symbol.isalpha())):

                    if symbol not in symbol_to_codes:
                        symbol_to_codes[symbol] = set()
                    symbol_to_codes[symbol].add(currency_code)
            except (UnknownLocaleError, ValueError, AttributeError, KeyError):
                # Expected failures: symbol not available for currency/locale combination
                continue

    # Step 3: Separate unambiguous vs ambiguous symbols
    unambiguous_map: dict[str, str] = {}
    ambiguous_set: set[str] = set()

    for symbol, codes in symbol_to_codes.items():
        if len(codes) == 1:
            # Unambiguous: symbol maps to exactly one currency
            unambiguous_map[symbol] = next(iter(codes))
        else:
            # Ambiguous: symbol used by multiple currencies
            ambiguous_set.add(symbol)

    # Step 4: Build locale → default currency mapping from territory data
    locale_to_currency: dict[str, str] = {}

    # Get all locales with territories
    for locale_id in all_locale_ids:
        try:
            locale = Locale.parse(locale_id)
            if not locale.territory:
                continue

            # Get active currencies for this territory
            # Returns list of currency codes (e.g., ['USD'] for US)
            territory_currencies = get_territory_currencies(locale.territory)

            # Use first currency as default (typically the official/current one)
            if territory_currencies and len(territory_currencies) > 0:
                current_currency = territory_currencies[0]

                # Normalize locale identifier to match our usage
                # Convert from babel format (en_US) to our format
                locale_str = str(locale)
                if "_" in locale_str:  # Has territory
                    locale_to_currency[locale_str] = current_currency

        except (UnknownLocaleError, ValueError, AttributeError, KeyError):
            # Expected failures: invalid locale identifiers, missing territory data
            continue

    return unambiguous_map, ambiguous_set, locale_to_currency, frozenset(all_currencies)


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


def _resolve_currency_code(
    currency_str: str,
    locale_code: str,
    value: str,
    *,
    default_currency: str | None,
    infer_from_locale: bool,
) -> tuple[str | None, FluentParseError | None]:
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
    is_iso_code = (
        len(currency_str) == ISO_CURRENCY_CODE_LENGTH
        and currency_str.isupper()
        and currency_str.isalpha()
    )

    symbol_map, ambiguous_symbols, locale_to_currency, valid_iso_codes = _get_currency_maps()

    if is_iso_code:
        # ISO code - validate against CLDR data
        if currency_str not in valid_iso_codes:
            diagnostic = ErrorTemplate.parse_currency_code_invalid(currency_str, value)
            return (None, FluentParseError(
                diagnostic, input_value=value, locale_code=locale_code, parse_type="currency"
            ))
        return (currency_str, None)

    # It's a symbol - check if ambiguous
    if currency_str in ambiguous_symbols:
        if default_currency:
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
        return (None, FluentParseError(
            diagnostic, input_value=value, locale_code=locale_code, parse_type="currency"
        ))

    # Unambiguous symbol - use mapping
    mapped = symbol_map.get(currency_str)
    if mapped is None:
        diagnostic = ErrorTemplate.parse_currency_symbol_unknown(currency_str, value)
        return (None, FluentParseError(
            diagnostic, input_value=value, locale_code=locale_code, parse_type="currency"
        ))
    return (mapped, None)


@functools.cache
def _get_currency_pattern_fast() -> re.Pattern[str]:
    """Compile fast-tier currency detection regex (no CLDR scan).

    Uses only fast-tier symbols for immediate pattern matching without
    triggering the expensive CLDR scan. Most common currencies (EUR, USD,
    GBP, JPY, etc.) are covered by the fast tier.

    Thread-safe via functools.cache internal locking.

    Returns:
        Compiled regex pattern matching:
        - ISO 4217 3-letter currency codes (e.g., EUR, USD, JPY) - matched first
        - Fast tier symbols only (unambiguous and ambiguous)
    """
    # Use fast tier only - no CLDR scan triggered
    fast_symbols, fast_ambiguous, _, _ = _get_currency_maps_fast()

    # Collect all fast tier symbols
    all_symbols: set[str] = set(fast_symbols.keys()) | fast_ambiguous

    # Sort by length descending to match longer symbols first
    sorted_symbols = sorted(all_symbols, key=len, reverse=True)

    # Escape special regex characters in symbols
    escaped_symbols = [re.escape(sym) for sym in sorted_symbols]

    # Build pattern: ISO codes FIRST, then symbols
    if escaped_symbols:
        symbols_pattern = "|".join(escaped_symbols)
        pattern = rf"([A-Z]{{{ISO_CURRENCY_CODE_LENGTH}}}|{symbols_pattern})"
    else:
        pattern = rf"([A-Z]{{{ISO_CURRENCY_CODE_LENGTH}}})"

    return re.compile(pattern)


@functools.cache
def _get_currency_pattern_full() -> re.Pattern[str]:
    """Compile full CLDR currency detection regex (lazy-loaded).

    Constructs pattern from complete CLDR-derived symbol maps. Only called
    when fast-tier pattern fails to match and full coverage is needed.

    Thread-safe via functools.cache internal locking.
    Called once per process lifetime; subsequent calls return cached result.

    Returns:
        Compiled regex pattern matching:
        - ISO 4217 3-letter currency codes (e.g., EUR, USD, JPY) - matched first
        - All symbols from CLDR currency maps (unambiguous and ambiguous)

    Pattern Priority:
        1. ISO codes (3 uppercase ASCII letters) - matched first to avoid
           partial symbol matches (e.g., 'F' matching before 'FFF')
        2. Longer symbols matched before shorter to prevent partial matches
           (e.g., "kr" before "k", "zl" as complete unit)
    """
    symbol_map, ambiguous, _, _ = _get_currency_maps()

    # Collect all symbols from both maps
    all_symbols: set[str] = set(symbol_map.keys()) | ambiguous

    # Sort by length descending to match longer symbols first
    # This prevents "k" matching before "kr" or "Kc"
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


def parse_currency(
    value: str,
    locale_code: str,
    *,
    default_currency: str | None = None,
    infer_from_locale: bool = False,
) -> tuple[tuple[Decimal, str] | None, tuple[FluentParseError, ...]]:
    """Parse locale-aware currency string to (amount, currency_code).

    Extracts both numeric value and currency code from formatted string.

    Ambiguous currency symbols ($, kr) require explicit default_currency
    or infer_from_locale=True. This prevents silent misidentification
    in multi-currency applications.

    Args:
        value: Currency string (e.g., "100,50 EUR" for lv_LV, "$100" with default_currency)
        locale_code: BCP 47 locale identifier
        default_currency: ISO 4217 code for ambiguous symbols (e.g., "CAD" for "$")
        infer_from_locale: Infer currency from locale if symbol is ambiguous

    Returns:
        Tuple of (result, errors):
        - result: Tuple of (amount, currency_code), or None if parsing failed
        - errors: Tuple of FluentParseError (empty tuple on success)

    Raises:
        BabelImportError: If Babel is not installed

    Examples:
        >>> result, errors = parse_currency("EUR100.50", "en_US")  # Unambiguous symbol
        >>> result
        (Decimal('100.50'), 'EUR')
        >>> errors
        ()

        >>> result, errors = parse_currency("100,50 EUR", "lv_LV")  # Unambiguous symbol
        >>> result
        (Decimal('100.50'), 'EUR')

        >>> result, errors = parse_currency("USD 1,234.56", "en_US")  # ISO code
        >>> result
        (Decimal('1234.56'), 'USD')

        >>> # Ambiguous symbols require explicit currency
        >>> result, errors = parse_currency("$100", "en_US", default_currency="USD")
        >>> result
        (Decimal('100'), 'USD')

        >>> result, errors = parse_currency("$100", "en_CA", default_currency="CAD")
        >>> result
        (Decimal('100'), 'CAD')

        >>> result, errors = parse_currency("$100", "en_CA", infer_from_locale=True)
        >>> result
        (Decimal('100'), 'CAD')

        >>> # Ambiguous symbols without default return error
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
    errors: list[FluentParseError] = []

    # Lazy import to support parser-only installations
    try:
        from babel import Locale, UnknownLocaleError  # noqa: PLC0415
        from babel.numbers import (  # noqa: PLC0415
            NumberFormatError,
            parse_decimal,
        )
    except ImportError as e:
        from ftllexengine.core.babel_compat import BabelImportError  # noqa: PLC0415

        feature = "parse_currency"
        raise BabelImportError(feature) from e

    # Type check: value must be string (runtime defense for untyped callers)
    if not isinstance(value, str):
        diagnostic = ErrorTemplate.parse_currency_failed(  # type: ignore[unreachable]
            str(value), locale_code, f"Expected string, got {type(value).__name__}"
        )
        errors.append(
            FluentParseError(
                diagnostic,
                input_value=str(value),
                locale_code=locale_code,
                parse_type="currency",
            )
        )
        return (None, tuple(errors))

    try:
        locale = Locale.parse(normalize_locale(locale_code))
    except (UnknownLocaleError, ValueError):
        diagnostic = ErrorTemplate.parse_locale_unknown(locale_code)
        errors.append(
            FluentParseError(
                diagnostic,
                input_value=value,
                locale_code=locale_code,
                parse_type="currency",
            )
        )
        return (None, tuple(errors))

    # Extract currency symbol or code using tiered pattern matching.
    # Try fast tier first (no CLDR scan), fall back to full tier if needed.
    # This provides sub-millisecond cold start for common currencies.
    fast_pattern = _get_currency_pattern_fast()
    match = fast_pattern.search(value)

    if not match:
        # Fast tier didn't match - try full CLDR pattern
        # This triggers the CLDR scan only when truly needed
        full_pattern = _get_currency_pattern_full()
        match = full_pattern.search(value)

    if not match:
        diagnostic = ErrorTemplate.parse_currency_failed(
            value, locale_code, "No currency symbol or code found"
        )
        errors.append(
            FluentParseError(
                diagnostic,
                input_value=value,
                locale_code=locale_code,
                parse_type="currency",
            )
        )
        return (None, tuple(errors))

    currency_str = match.group(1)

    # Resolve currency code from symbol or ISO code
    currency_code, resolution_error = _resolve_currency_code(
        currency_str,
        locale_code,
        value,
        default_currency=default_currency,
        infer_from_locale=infer_from_locale,
    )
    if resolution_error is not None:
        errors.append(resolution_error)
        return (None, tuple(errors))
    # Type narrowing: resolution contract guarantees exactly one of (code, error) is None.
    # At this point, resolution_error is None so currency_code is guaranteed non-None.
    assert currency_code is not None  # nosec B101 - type narrowing, not runtime validation

    # Remove currency symbol/code to extract number
    # Use match position to remove ONLY the matched occurrence, not all instances.
    # This prevents corruption if the symbol appears elsewhere in the string
    # (e.g., "Price $100 ($5 tax)" should not become "Price 100 ( 5 tax)").
    number_str = (value[:match.start(1)] + value[match.end(1):]).strip()

    # Parse number using Babel
    try:
        amount = parse_decimal(number_str, locale=locale)
    except NumberFormatError as e:
        diagnostic = ErrorTemplate.parse_amount_invalid(number_str, value, str(e))
        errors.append(
            FluentParseError(
                diagnostic,
                input_value=value,
                locale_code=locale_code,
                parse_type="currency",
            )
        )
        return (None, tuple(errors))

    return ((amount, currency_code), tuple(errors))
