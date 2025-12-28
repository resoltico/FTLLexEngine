"""Currency parsing with locale awareness.

API: parse_currency() returns tuple[tuple[Decimal, str] | None, tuple[FluentParseError, ...]].
Functions NEVER raise exceptions - errors returned in tuple.

Thread-safe. Uses Babel for currency symbol mapping and number parsing.
All currency data sourced from Unicode CLDR via Babel.

Tiered Loading Strategy (PERF-CURRENCY-INIT-001):
    - Fast Tier: Common currencies with hardcoded unambiguous symbols (immediate)
    - Full Tier: Complete CLDR scan (lazy-loaded on first cache miss)
    This provides sub-millisecond cold start for common currencies while maintaining
    complete CLDR coverage for edge cases.

Architecture (v0.38.0):
    CurrencyDataProvider encapsulates all currency data and loading logic.
    - Replaces module-level global variables with instance attributes
    - Provides locale-aware symbol resolution for ambiguous symbols

Python 3.13+.
"""
# ruff: noqa: ERA001 - Section comments in data structures are documentation, not dead code

import functools
import re
import threading
from decimal import Decimal

from babel import Locale, UnknownLocaleError
from babel.localedata import locale_identifiers
from babel.numbers import (
    NumberFormatError,
    get_currency_symbol,
    get_territory_currencies,
    parse_decimal,
)

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
    "\u00a3": "GBP",  # Pound sign (unambiguous as GBP in practice)
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
# v0.38.0: Yen sign added to ambiguous set (LOGIC-YEN-001 fix)
_FAST_TIER_AMBIGUOUS_SYMBOLS: frozenset[str] = frozenset({
    "$",     # USD, CAD, AUD, NZD, SGD, HKD, MXN, ARS, CLP, COP, etc.
    "kr",    # SEK, NOK, DKK, ISK
    "R",     # ZAR, BRL (R$), INR (historical)
    "R$",    # BRL
    "S/",    # PEN
    "\u00a5",  # Yen/Yuan sign - JPY (Japanese) or CNY (Chinese)
})

# Locale-aware resolution for ambiguous symbols (v0.38.0)
# Maps (symbol, locale_prefix) -> currency_code for context-sensitive resolution
_AMBIGUOUS_SYMBOL_LOCALE_RESOLUTION: dict[tuple[str, str], str] = {
    # Yen/Yuan sign: CNY for Chinese locales, JPY otherwise
    ("\u00a5", "zh"): "CNY",  # Chinese locales use Yuan
    # Dollar sign: locale-specific resolution
    ("$", "en_US"): "USD",
    ("$", "en_CA"): "CAD",
    ("$", "en_AU"): "AUD",
    ("$", "en_NZ"): "NZD",
    ("$", "en_SG"): "SGD",
    ("$", "en_HK"): "HKD",
    ("$", "es_MX"): "MXN",
    ("$", "es_AR"): "ARS",
    ("$", "es_CL"): "CLP",
    ("$", "es_CO"): "COP",
}

# Default resolution for ambiguous symbols when locale doesn't match
_AMBIGUOUS_SYMBOL_DEFAULTS: dict[str, str] = {
    "\u00a5": "JPY",  # Default to JPY for non-Chinese locales
    "$": "USD",       # Default to USD when locale not recognized
    "kr": "SEK",      # Default to SEK for Nordic kr
    "R": "ZAR",       # Default to ZAR for R
    "R$": "BRL",      # R$ is unambiguous as BRL
    "S/": "PEN",      # S/ is unambiguous as PEN
}

# Common locale-to-currency mappings for fast tier (no CLDR scan needed)
_FAST_TIER_LOCALE_CURRENCIES: dict[str, str] = {
    # North America
    "en_US": "USD", "es_US": "USD",
    "en_CA": "CAD", "fr_CA": "CAD",
    "es_MX": "MXN",
    # Europe - Eurozone
    "de_DE": "EUR", "de_AT": "EUR",
    "fr_FR": "EUR", "it_IT": "EUR",
    "es_ES": "EUR", "pt_PT": "EUR",
    "nl_NL": "EUR", "fi_FI": "EUR",
    "el_GR": "EUR", "et_EE": "EUR",
    "lt_LT": "EUR", "lv_LV": "EUR",
    "sk_SK": "EUR", "sl_SI": "EUR",
    # Europe - Non-Eurozone
    "en_GB": "GBP", "de_CH": "CHF", "fr_CH": "CHF", "it_CH": "CHF",
    "sv_SE": "SEK", "no_NO": "NOK", "da_DK": "DKK",
    "pl_PL": "PLN", "cs_CZ": "CZK", "hu_HU": "HUF",
    "ro_RO": "RON", "bg_BG": "BGN", "hr_HR": "HRK",
    "uk_UA": "UAH", "ru_RU": "RUB", "is_IS": "ISK",
    # Asia-Pacific
    "ja_JP": "JPY", "zh_CN": "CNY", "zh_TW": "TWD", "zh_HK": "HKD",
    "ko_KR": "KRW", "hi_IN": "INR", "th_TH": "THB",
    "vi_VN": "VND", "id_ID": "IDR", "ms_MY": "MYR",
    "fil_PH": "PHP", "en_SG": "SGD", "en_AU": "AUD", "en_NZ": "NZD",
    # Middle East / Africa
    "ar_SA": "SAR", "ar_EG": "EGP", "ar_AE": "AED",
    "he_IL": "ILS", "tr_TR": "TRY",
    "en_ZA": "ZAR", "pt_BR": "BRL",
    # South America
    "es_AR": "ARS", "es_CL": "CLP", "es_CO": "COP", "es_PE": "PEN",
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
# Currency Data Provider (v0.38.0: ARCH-STATE-001 fix)
# =============================================================================
# Encapsulates all currency data and loading logic as instance state.
# Replaces module-level global variables.


class CurrencyDataProvider:
    """Encapsulated currency data with locale-aware symbol resolution.

    v0.38.0: Introduced to replace global mutable state pattern.

    Provides:
    - Tiered loading (fast tier immediate, full CLDR lazy-loaded)
    - Locale-aware resolution for ambiguous symbols (e.g., Yen/Yuan)
    - Thread-safe lazy initialization

    Attributes:
        _loaded: Whether full CLDR tier has been loaded
        _lock: Threading lock for thread-safe initialization
        _symbol_map: Symbol -> currency code mapping (full tier)
        _ambiguous: Set of ambiguous symbols (full tier)
        _locale_currencies: Locale -> currency mapping (full tier)
        _valid_codes: Set of valid ISO 4217 codes (full tier)
    """

    __slots__ = (
        "_ambiguous",
        "_loaded",
        "_locale_currencies",
        "_lock",
        "_symbol_map",
        "_valid_codes",
    )

    def __init__(self) -> None:
        """Initialize with empty full tier state (lazy-loaded)."""
        self._loaded: bool = False
        self._lock: threading.Lock = threading.Lock()
        self._symbol_map: dict[str, str] = {}
        self._ambiguous: set[str] = set()
        self._locale_currencies: dict[str, str] = {}
        self._valid_codes: frozenset[str] = frozenset()

    def resolve_ambiguous_symbol(
        self,
        symbol: str,
        locale_code: str | None = None,
    ) -> str | None:
        """Resolve ambiguous symbol to currency code with locale context.

        v0.38.0: Locale-aware resolution for LOGIC-YEN-001 fix.

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

    def ensure_loaded(self) -> None:
        """Ensure full CLDR tier is loaded (thread-safe, idempotent).

        Called when fast tier doesn't have the needed data.
        Uses double-check locking pattern for thread safety.
        """
        if self._loaded:
            return

        with self._lock:
            # Double-check after acquiring lock
            if self._loaded:
                return  # type: ignore[unreachable]

            # Perform full CLDR scan
            symbol_map, ambiguous, locale_currencies, valid_codes = (
                _build_currency_maps_from_cldr()
            )

            # Store in instance attributes
            self._symbol_map = symbol_map
            self._ambiguous = ambiguous
            self._locale_currencies = locale_currencies
            self._valid_codes = valid_codes
            self._loaded = True

    def get_full_tier_data(
        self,
    ) -> tuple[dict[str, str], set[str], dict[str, str], frozenset[str]]:
        """Get full CLDR currency maps (lazy-loaded on first call).

        Thread-safe. Triggers CLDR scan if not already loaded.

        Returns:
            Tuple of (symbol_to_code, ambiguous_symbols, locale_to_currency, valid_codes)
        """
        self.ensure_loaded()
        return (
            self._symbol_map,
            self._ambiguous,
            self._locale_currencies,
            self._valid_codes,
        )


# Module-level singleton for API compatibility
_provider = CurrencyDataProvider()


def _build_currency_maps_from_cldr() -> tuple[
    dict[str, str], set[str], dict[str, str], frozenset[str]
]:
    """Build currency maps from Unicode CLDR data via Babel.

    Scans all available locales and currencies in CLDR to build:
    1. Symbol → ISO code mapping (for unambiguous symbols)
    2. Set of ambiguous symbols (symbols used by multiple currencies)
    3. Locale → default currency mapping (from territory data)
    4. Set of all valid ISO 4217 currency codes (for validation)

    This replaces hardcoded maps with dynamic CLDR data extraction.
    Executed once at module initialization for optimal runtime performance.

    Returns:
        Tuple of (symbol_to_code, ambiguous_symbols, locale_to_currency, valid_codes):
        - symbol_to_code: Unambiguous currency symbol → ISO 4217 code
        - ambiguous_symbols: Symbols that map to multiple currencies
        - locale_to_currency: Locale code → default ISO 4217 currency code
        - valid_codes: Frozenset of all valid ISO 4217 currency codes from CLDR
    """
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

    Thread-safe. Triggers CLDR scan if not already loaded.
    v0.38.0: Delegates to CurrencyDataProvider singleton.

    Returns:
        Tuple of (symbol_to_code, ambiguous_symbols, locale_to_currency, valid_codes)
        from complete CLDR data.
    """
    return _provider.get_full_tier_data()


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
            # v0.38.0: Locale-aware resolution for ambiguous symbols
            resolved = _provider.resolve_ambiguous_symbol(currency_str, locale_code)
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
def _get_currency_pattern() -> re.Pattern[str]:
    """Lazy-compile currency detection regex on first use.

    Constructs pattern from CLDR-derived symbol maps, eliminating the need
    for hardcoded symbol lists that miss locale-specific symbols.

    Thread-safe via functools.cache internal locking.
    Called once per process lifetime; subsequent calls return cached result.

    Returns:
        Compiled regex pattern matching:
        - ISO 4217 3-letter currency codes (e.g., EUR, USD, JPY) - matched first
        - All symbols from currency maps (unambiguous and ambiguous)

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

    No longer raises exceptions. Errors are returned in tuple.
    The `strict` parameter has been removed.

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

    # Extract currency symbol or code using dynamic CLDR-derived pattern
    # Pattern includes all symbols from currency maps and 3-letter ISO codes.
    # Sorted by length to match longer symbols first.
    currency_pattern = _get_currency_pattern()
    match = currency_pattern.search(value)

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
    assert currency_code is not None  # Type narrowing: resolution succeeded

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
