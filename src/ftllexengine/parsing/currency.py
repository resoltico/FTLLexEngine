"""Currency parsing with locale awareness.

API: parse_currency() returns tuple[tuple[Decimal, str] | None, tuple[FluentParseError, ...]].
Functions NEVER raise exceptions - errors returned in tuple.

Thread-safe. Uses Babel for currency symbol mapping and number parsing.
All currency data sourced from Unicode CLDR via Babel, loaded lazily on first use.

Python 3.13+.
"""

import functools
import re
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

# ISO 4217 currency codes are exactly 3 uppercase ASCII letters.
# This is per the ISO 4217 standard and is guaranteed not to change.
ISO_CURRENCY_CODE_LENGTH: int = 3

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


@functools.cache
def _get_currency_maps() -> tuple[dict[str, str], set[str], dict[str, str], frozenset[str]]:
    """Lazy-load CLDR currency maps on first use.

    Thread-safe via functools.cache internal locking.
    Called once per process lifetime; subsequent calls return cached result.

    Returns:
        Tuple of (symbol_to_code, ambiguous_symbols, locale_to_currency, valid_codes):
        - symbol_to_code: Unambiguous currency symbol → ISO 4217 code
        - ambiguous_symbols: Symbols that map to multiple currencies
        - locale_to_currency: Locale code → default ISO 4217 currency code
        - valid_codes: Frozenset of all valid ISO 4217 currency codes from CLDR
    """
    return _build_currency_maps_from_cldr()


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

    # Determine if this is an ISO code (3 uppercase letters per ISO 4217) or a symbol
    # ISO codes are always unambiguous; symbols need lookup in CLDR maps
    is_iso_code = (len(currency_str) == ISO_CURRENCY_CODE_LENGTH
                   and currency_str.isupper() and currency_str.isalpha())

    # Get currency maps (includes valid ISO 4217 codes for validation)
    symbol_map, ambiguous_symbols, locale_to_currency, valid_iso_codes = _get_currency_maps()

    if not is_iso_code:

        # It's a symbol - check if ambiguous
        if currency_str in ambiguous_symbols:
            # Ambiguous symbols require explicit handling
            if default_currency:
                currency_code = default_currency
            elif infer_from_locale:
                # Normalize locale for lookup: keys are Babel format (en_US)
                # but input may be BCP-47 format (en-US)
                inferred_currency = locale_to_currency.get(normalize_locale(locale_code))
                if inferred_currency is None:
                    diagnostic = ErrorTemplate.parse_currency_ambiguous(currency_str, value)
                    errors.append(
                        FluentParseError(
                            diagnostic,
                            input_value=value,
                            locale_code=locale_code,
                            parse_type="currency",
                        )
                    )
                    return (None, tuple(errors))
                currency_code = inferred_currency
            else:
                # No default provided - error for ambiguous symbol
                diagnostic = ErrorTemplate.parse_currency_ambiguous(currency_str, value)
                errors.append(
                    FluentParseError(
                        diagnostic,
                        input_value=value,
                        locale_code=locale_code,
                        parse_type="currency",
                    )
                )
                return (None, tuple(errors))
        else:
            # Unambiguous symbol - use mapping
            mapped_currency = symbol_map.get(currency_str)
            if mapped_currency is None:
                diagnostic = ErrorTemplate.parse_currency_symbol_unknown(currency_str, value)
                errors.append(
                    FluentParseError(
                        diagnostic,
                        input_value=value,
                        locale_code=locale_code,
                        parse_type="currency",
                    )
                )
                return (None, tuple(errors))
            currency_code = mapped_currency
    else:
        # ISO code (3 uppercase letters) - validate against CLDR data
        if currency_str not in valid_iso_codes:
            diagnostic = ErrorTemplate.parse_currency_code_invalid(currency_str, value)
            errors.append(
                FluentParseError(
                    diagnostic,
                    input_value=value,
                    locale_code=locale_code,
                    parse_type="currency",
                )
            )
            return (None, tuple(errors))
        currency_code = currency_str

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
