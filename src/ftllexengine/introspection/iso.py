"""ISO 3166/4217 introspection API via Babel CLDR data.

Provides type-safe access to ISO standards data for territories and currencies.
All types are immutable, hashable, and thread-safe. Results are cached for
performance.

Requires Babel installation for full functionality:
    pip install ftllexengine[babel]

Without Babel, functions raise BabelImportError with installation guidance.

Python 3.13+. Babel is optional dependency.
"""

from __future__ import annotations

from functools import lru_cache

# TypeIs (PEP 742) is available unconditionally on Python 3.13+, which is the
# minimum supported version. The import is placed here at module level so that
# typing.get_type_hints() callers resolve the name from this module's globals.
from typing import TypeIs

from ftllexengine.constants import (
    ISO_4217_DECIMAL_DIGITS,
    ISO_4217_DEFAULT_DECIMALS,
    ISO_4217_VALID_CODES,
    MAX_CURRENCY_CACHE_SIZE,
    MAX_LOCALE_CACHE_SIZE,
    MAX_TERRITORY_CACHE_SIZE,
)
from ftllexengine.core.babel_compat import BabelImportError
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

# ruff: noqa: RUF022 - __all__ organized by category for readability
__all__ = [
    # NewType wrappers
    "TerritoryCode",
    "CurrencyCode",
    # Data classes
    "TerritoryInfo",
    "CurrencyInfo",
    # Lookup functions
    "get_territory",
    "get_currency",
    "get_currency_decimal_digits",
    "list_territories",
    "list_currencies",
    "get_territory_currencies",
    # Type guards
    "is_valid_territory_code",
    "is_valid_currency_code",
    # Boundary validators
    "require_currency_code",
    "require_territory_code",
    # Cache management
    "clear_iso_cache",
    # Exceptions
    "BabelImportError",
]

# CACHED LOOKUP FUNCTIONS
# ============================================================================


@lru_cache(maxsize=MAX_TERRITORY_CACHE_SIZE)
def _get_territory_impl(
    code_upper: str,
    locale_norm: str,
) -> TerritoryInfo | None:
    """Internal cached implementation for get_territory.

    Args:
        code_upper: Pre-uppercased ISO 3166-1 alpha-2 code.
        locale_norm: Pre-normalized locale string.

    Returns:
        TerritoryInfo if found, None if unknown code.
    """
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
    """Look up ISO 3166-1 territory by alpha-2 code.

    Args:
        code: ISO 3166-1 alpha-2 code (e.g., 'US', 'LV'). Case-insensitive.
        locale: Locale for name localization (default: 'en'). Accepts BCP-47
            (en-US) or POSIX (en_US) formats; normalized internally.

    Returns:
        TerritoryInfo if found, None if unknown code.

    Raises:
        BabelImportError: If Babel not installed.

    Thread-safe. Results cached per normalized (code, locale) pair.
    """
    # Guard: ISO 3166-1 alpha-2 codes are exactly 2 characters before uppercasing.
    # str.upper() can expand single characters (e.g., 'ß' → 'SS'), so checking the
    # raw length prevents a length-1 input from matching a valid 2-char territory code
    # via Unicode casefold expansion. This keeps get_territory consistent with the
    # is_valid_territory_code type guard, which also checks len(value) == 2.
    if len(code) != 2:
        return None
    return _get_territory_impl(code.upper(), normalize_locale(locale))


@lru_cache(maxsize=MAX_CURRENCY_CACHE_SIZE)
def _get_currency_impl(
    code_upper: str,
    locale_norm: str,
) -> CurrencyInfo | None:
    """Internal cached implementation for get_currency.

    Args:
        code_upper: Pre-uppercased ISO 4217 currency code.
        locale_norm: Pre-normalized locale string.

    Returns:
        CurrencyInfo if found, None if unknown code.
    """
    name = _get_babel_currency_name(code_upper, locale_norm)

    if name is None:
        return None

    symbol = _get_babel_currency_symbol(code_upper, locale_norm)

    # ISO 4217 standard is the authoritative source for currency decimal precision.
    # Babel's CLDR data may differ from ISO 4217 for specific currencies (e.g., IQD:
    # Babel reports 0 decimals, ISO 4217 specifies 3). For financial-grade accuracy,
    # the hardcoded ISO 4217 data is used as the source of truth.
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
    """Look up ISO 4217 currency by code.

    Args:
        code: ISO 4217 currency code (e.g., 'USD', 'EUR'). Case-insensitive.
        locale: Locale for name/symbol localization (default: 'en'). Accepts
            BCP-47 (en-US) or POSIX (en_US) formats; normalized internally.

    Returns:
        CurrencyInfo if found, None if unknown code.

    Raises:
        BabelImportError: If Babel not installed.

    Thread-safe. Results cached per normalized (code, locale) pair.
    """
    # Guard: ISO 4217 currency codes are exactly 3 characters before uppercasing.
    # str.upper() can expand single characters (e.g., 'ß' → 'SS'), so a 2-char
    # input could produce a valid 3-char code via casefold expansion. Checking the
    # raw length keeps get_currency consistent with is_valid_currency_code.
    if len(code) != 3:
        return None
    return _get_currency_impl(code.upper(), normalize_locale(locale))


def get_currency_decimal_digits(code: str) -> int | None:
    """Return ISO 4217 standard decimal precision for a currency code.

    Babel-free: queries the embedded ISO 4217 tables directly without any
    locale lookup. No Babel installation required. Safe to call in
    parser-only installs (``pip install ftllexengine`` without ``[babel]``).

    Decimal precision is a currency-level ISO 4217 property, not a locale
    property: KWD always has 3 decimal places, JPY always has 0, USD/EUR
    always have 2, regardless of display locale.

    Validation is against ``ISO_4217_VALID_CODES``, the embedded authoritative
    code set. Only codes present in that set yield a precision value. Codes
    not listed return None regardless of Babel availability.

    **ISO 4217 vs CLDR divergence:** This function follows the ISO 4217
    standard, not Babel's CLDR usage data. The two sources differ for
    some currencies where minor units exist in the standard but are not
    used in practice:

    - ``IQD`` (Iraqi Dinar): ISO 4217 specifies **3** decimal places (fils).
      Babel/CLDR reports 0 because fils are not used in daily commerce.
      Callers mixing this function with ``babel.numbers.get_currency_precision``
      will observe a discrepancy for IQD. This function returns the
      ISO-standard value (3).
    - ``MGA`` (Malagasy Ariary): ISO 4217 assigns exponent 2, but the actual
      subdivision is 1/5 (1 ariary = 5 iraimbilanja), not 1/100. This
      function returns 2 per the ISO standard; financial systems formatting
      MGA should be aware that the subdivision is non-decimal.

    Args:
        code: ISO 4217 currency code (e.g., 'USD', 'EUR'). Case-insensitive.

    Returns:
        Number of decimal digits (0 for JPY, 2 for USD/EUR, 3 for KWD), or
        None if the code is not a currently active ISO 4217 currency code.
        Historical or retired codes (e.g. SLL, ZWL, TMM, TRL) return None —
        they are absent from ``ISO_4217_VALID_CODES``, which covers only active
        standards. Babel's ``get_currency()`` may still return data for these
        historical codes via CLDR; the two functions have different scopes by
        design.

    Thread-safe. No Babel dependency. O(1) constant-time lookup against
    process-immutable tables.

    Examples:
        >>> get_currency_decimal_digits("KWD")  # doctest: +SKIP
        3
        >>> get_currency_decimal_digits("JPY")  # doctest: +SKIP
        0
        >>> get_currency_decimal_digits("EUR")  # doctest: +SKIP
        2
        >>> get_currency_decimal_digits("IQD")  # doctest: +SKIP
        3
        >>> get_currency_decimal_digits("XYZ") is None  # doctest: +SKIP
        True
    """
    # ISO 4217 codes are exactly 3 characters before uppercasing.
    # Mirrors the raw-length guard in get_currency() to prevent casefold expansion.
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
    """Internal cached implementation for list_territories.

    Args:
        locale_norm: Pre-normalized locale string.

    Returns:
        Frozen set of all TerritoryInfo objects.
    """
    territories = _get_babel_territories(locale_norm)
    result: set[TerritoryInfo] = set()

    for code, name in territories.items():
        # Filter to alpha-2 codes only (2 uppercase letters)
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
    """List all known ISO 3166-1 territories.

    Args:
        locale: Locale for name localization (default: 'en'). Accepts BCP-47
            (en-US) or POSIX (en_US) formats; normalized internally.

    Returns:
        Frozen set of all TerritoryInfo objects.

    Raises:
        BabelImportError: If Babel not installed.

    Thread-safe. Result cached per normalized locale.
    """
    return _list_territories_impl(normalize_locale(locale))


@lru_cache(maxsize=MAX_LOCALE_CACHE_SIZE)
def _list_currencies_impl(
    locale_norm: str,
) -> frozenset[CurrencyInfo]:
    """Internal cached implementation for list_currencies.

    Returns complete ISO 4217 currency set regardless of locale. When a currency
    lacks a localized name in the target locale, falls back to English name.
    This ensures consistent result sets across locales for financial applications.

    Args:
        locale_norm: Pre-normalized locale string.

    Returns:
        Frozen set of all CurrencyInfo objects.
    """
    # Get all currency codes and English names from Babel
    currencies_en = _get_babel_currencies()
    result: set[CurrencyInfo] = set()

    for code, english_name in currencies_en.items():
        # Filter to valid ISO 4217 codes (3 uppercase letters)
        if len(code) == 3 and code.isalpha() and code.isupper():
            # Try to get localized info
            info = _get_currency_impl(code, locale_norm)
            if info is not None:
                result.add(info)
            else:
                # Fallback: use English name when localized name unavailable
                # This ensures complete currency list regardless of locale coverage
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
    """List all known ISO 4217 currencies.

    Returns the complete ISO 4217 currency set regardless of locale. Currencies
    are localized where CLDR data is available; otherwise, English names are
    used as fallback. This ensures consistent result sets across all locales
    for financial applications.

    Args:
        locale: Locale for name/symbol localization (default: 'en'). Accepts
            BCP-47 (en-US) or POSIX (en_US) formats; normalized internally.

    Returns:
        Frozen set of all CurrencyInfo objects. The set is complete and
        consistent regardless of locale - same currencies returned for
        all locales, only names/symbols differ based on CLDR coverage.

    Raises:
        BabelImportError: If Babel not installed.

    Thread-safe. Result cached per normalized locale.
    """
    return _list_currencies_impl(normalize_locale(locale))


@lru_cache(maxsize=MAX_TERRITORY_CACHE_SIZE)
def _get_territory_currencies_impl(territory_upper: str) -> tuple[CurrencyCode, ...]:
    """Internal cached implementation for get_territory_currencies.

    Args:
        territory_upper: Pre-uppercased ISO 3166-1 alpha-2 code.

    Returns:
        Tuple of all active legal tender ISO 4217 currency codes.
        Empty tuple if territory unknown or has no currency data.
    """
    currencies = _get_babel_territory_currencies(territory_upper)
    return tuple(CurrencyCode(c) for c in currencies)


def get_territory_currencies(territory: str) -> tuple[CurrencyCode, ...]:
    """Get all active legal tender currencies for a territory.

    Multi-currency territories (e.g., Panama with PAB and USD) return
    all currencies currently in use. The order reflects CLDR precedence
    (typically the most commonly used currency first).

    Args:
        territory: ISO 3166-1 alpha-2 code. Case-insensitive.

    Returns:
        Tuple of all active ISO 4217 currency codes for the territory.
        Empty tuple if territory unknown or has no currency data.

    Raises:
        BabelImportError: If Babel not installed.

    Thread-safe. Result cached per normalized territory code.
    """
    # Guard: ISO 3166-1 alpha-2 codes are exactly 2 characters before uppercasing.
    # Mirrors the guard in get_territory to prevent casefold expansion mismatches.
    if len(territory) != 2:
        return ()
    return _get_territory_currencies_impl(territory.upper())


# ============================================================================
# VALIDATION CODE SETS (Cache Pollution Prevention)
# ============================================================================
#
# Security Design: Validation functions must NOT call get_territory/get_currency
# because those functions cache individual lookup results (including None for
# invalid codes). An attacker could fill the LRU cache with None entries by
# validating random strings, evicting legitimate cached lookups.
#
# Solution: Validation uses membership checks against pre-cached code sets.
# The _list_territories_impl/_list_currencies_impl functions cache the COMPLETE
# set once per locale, so validation queries hit this single cached set without
# polluting the individual lookup caches.
#
# ============================================================================


@lru_cache(maxsize=MAX_LOCALE_CACHE_SIZE)
def _territory_codes_impl(locale_norm: str) -> frozenset[str]:
    """Internal cached implementation returning all valid territory codes.

    Extracts alpha-2 codes from the full territory list for O(1) validation.
    Cached per locale because territory codes are locale-independent, but the
    underlying _list_territories_impl is locale-keyed.

    Args:
        locale_norm: Pre-normalized locale string.

    Returns:
        Frozen set of all valid ISO 3166-1 alpha-2 codes.
    """
    return frozenset(t.alpha2 for t in _list_territories_impl(locale_norm))


@lru_cache(maxsize=MAX_LOCALE_CACHE_SIZE)
def _currency_codes_impl(locale_norm: str) -> frozenset[str]:
    """Internal cached implementation returning all valid currency codes.

    Extracts currency codes from the full currency list for O(1) validation.
    Cached per locale because currency codes are locale-independent, but the
    underlying _list_currencies_impl is locale-keyed.

    Args:
        locale_norm: Pre-normalized locale string.

    Returns:
        Frozen set of all valid ISO 4217 currency codes.
    """
    return frozenset(c.code for c in _list_currencies_impl(locale_norm))


# ============================================================================
# TYPE GUARDS (PEP 742)
# ============================================================================


def is_valid_territory_code(value: str) -> TypeIs[TerritoryCode]:
    """Check if string is a valid ISO 3166-1 alpha-2 code.

    Validates against Babel's CLDR territory database using O(1) set membership.
    Does NOT cache invalid inputs (cache pollution prevention).

    Args:
        value: String to check.

    Returns:
        True if value is a known ISO 3166-1 alpha-2 code.

    Raises:
        BabelImportError: If Babel not installed.
    """
    if not isinstance(value, str) or len(value) != 2:
        return False
    # Use membership check against cached code set (prevents cache pollution).
    # normalize_locale("en") is used because territory codes are locale-independent;
    # we just need any valid locale to trigger the Babel lookup once.
    return value.upper() in _territory_codes_impl(normalize_locale("en"))


def is_valid_currency_code(value: str) -> TypeIs[CurrencyCode]:
    """Check if string is a valid ISO 4217 currency code.

    Validates against Babel's CLDR currency database using O(1) set membership.
    Does NOT cache invalid inputs (cache pollution prevention).

    Args:
        value: String to check.

    Returns:
        True if value is a known ISO 4217 currency code.

    Raises:
        BabelImportError: If Babel not installed.
    """
    if not isinstance(value, str) or len(value) != 3:
        return False
    # Use membership check against cached code set (prevents cache pollution).
    # normalize_locale("en") is used because currency codes are locale-independent;
    # we just need any valid locale to trigger the Babel lookup once.
    return value.upper() in _currency_codes_impl(normalize_locale("en"))


# ============================================================================
# CACHE MANAGEMENT
# ============================================================================


def require_currency_code(value: object, field_name: str) -> CurrencyCode:
    """Validate and normalize a boundary value to a canonical ISO 4217 currency code.

    Strips surrounding whitespace, rejects non-str types with TypeError, normalizes
    to uppercase, and validates against Babel's CLDR currency database. Returns the
    canonical uppercase CurrencyCode so callers need no post-validation normalization.

    Use at every constructor or API entry point that accepts a currency code field.
    Eliminates the require_non_empty_str + upper() + is_valid_currency_code chain
    that every downstream system would otherwise reimplement independently.

    Args:
        value: Raw boundary value to validate. Accepts any Python object; non-str
            values always raise TypeError; values that are not valid ISO 4217 codes
            raise ValueError.
        field_name: Human-readable field label used in error messages.

    Returns:
        Canonical uppercase CurrencyCode (e.g., CurrencyCode("USD")).

    Raises:
        TypeError: If value is not a str instance.
        ValueError: If value (after stripping and uppercasing) is not a known
            ISO 4217 currency code.
        BabelImportError: If Babel is not installed.

    Example:
        >>> require_currency_code("usd", "currency")  # doctest: +SKIP
        'USD'
        >>> require_currency_code("  EUR  ", "currency")  # doctest: +SKIP
        'EUR'
        >>> require_currency_code("XYZ", "currency")  # doctest: +SKIP
        Traceback (most recent call last):
            ...
        ValueError: currency must be a valid ISO 4217 currency code, got 'XYZ'
        >>> require_currency_code(840, "currency")  # doctest: +SKIP
        Traceback (most recent call last):
            ...
        TypeError: currency must be str, got int
    """
    if not isinstance(value, str):
        msg = f"{field_name} must be str, got {type(value).__name__}"
        raise TypeError(msg)
    stripped = value.strip()
    code = stripped.upper()
    if len(stripped) != 3:
        msg = f"{field_name} must be a valid ISO 4217 currency code, got {value!r}"
        raise ValueError(msg)
    if code not in _currency_codes_impl(normalize_locale("en")):
        msg = f"{field_name} must be a valid ISO 4217 currency code, got {value!r}"
        raise ValueError(msg)
    return CurrencyCode(code)


def require_territory_code(value: object, field_name: str) -> TerritoryCode:
    """Validate and normalize a boundary value to a canonical ISO 3166-1 alpha-2 code.

    Strips surrounding whitespace, rejects non-str types with TypeError, normalizes
    to uppercase, and validates against Babel's CLDR territory database. Returns the
    canonical uppercase TerritoryCode so callers need no post-validation normalization.

    Use at every constructor or API entry point that accepts a territory code field.
    Eliminates the require_non_empty_str + upper() + is_valid_territory_code chain
    that every downstream system would otherwise reimplement independently.

    Args:
        value: Raw boundary value to validate. Accepts any Python object; non-str
            values always raise TypeError; values that are not valid ISO 3166-1
            alpha-2 codes raise ValueError.
        field_name: Human-readable field label used in error messages.

    Returns:
        Canonical uppercase TerritoryCode (e.g., TerritoryCode("US")).

    Raises:
        TypeError: If value is not a str instance.
        ValueError: If value (after stripping and uppercasing) is not a known
            ISO 3166-1 alpha-2 territory code.
        BabelImportError: If Babel is not installed.

    Example:
        >>> require_territory_code("us", "territory")  # doctest: +SKIP
        'US'
        >>> require_territory_code("  DE  ", "territory")  # doctest: +SKIP
        'DE'
        >>> require_territory_code("XX", "territory")  # doctest: +SKIP
        Traceback (most recent call last):
            ...
        ValueError: territory must be a valid ISO 3166-1 alpha-2 territory code, got 'XX'
        >>> require_territory_code(840, "territory")  # doctest: +SKIP
        Traceback (most recent call last):
            ...
        TypeError: territory must be str, got int
    """
    if not isinstance(value, str):
        msg = f"{field_name} must be str, got {type(value).__name__}"
        raise TypeError(msg)
    stripped = value.strip()
    code = stripped.upper()
    if len(stripped) != 2:
        msg = (
            f"{field_name} must be a valid ISO 3166-1 alpha-2 territory code, got {value!r}"
        )
        raise ValueError(msg)
    if code not in _territory_codes_impl(normalize_locale("en")):
        msg = (
            f"{field_name} must be a valid ISO 3166-1 alpha-2 territory code, got {value!r}"
        )
        raise ValueError(msg)
    return TerritoryCode(code)


def clear_iso_cache() -> None:
    """Clear all ISO introspection caches.

    Call this if you need to free memory or after locale configuration changes.
    Thread-safe.
    """
    _get_babel_currencies.cache_clear()
    _get_territory_impl.cache_clear()
    _get_currency_impl.cache_clear()
    _list_territories_impl.cache_clear()
    _list_currencies_impl.cache_clear()
    _get_territory_currencies_impl.cache_clear()
    _territory_codes_impl.cache_clear()
    _currency_codes_impl.cache_clear()
