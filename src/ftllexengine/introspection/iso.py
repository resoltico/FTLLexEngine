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

from dataclasses import dataclass
from functools import lru_cache
from typing import TypeIs

from ftllexengine.constants import (
    ISO_4217_DECIMAL_DIGITS,
    ISO_4217_DEFAULT_DECIMALS,
    MAX_CURRENCY_CACHE_SIZE,
    MAX_LOCALE_CACHE_SIZE,
    MAX_TERRITORY_CACHE_SIZE,
)
from ftllexengine.core.babel_compat import BabelImportError
from ftllexengine.core.locale_utils import normalize_locale

# ruff: noqa: RUF022 - __all__ organized by category for readability
__all__ = [
    # Type aliases
    "TerritoryCode",
    "CurrencyCode",
    # Data classes
    "TerritoryInfo",
    "CurrencyInfo",
    # Lookup functions
    "get_territory",
    "get_currency",
    "list_territories",
    "list_currencies",
    "get_territory_currencies",
    # Type guards
    "is_valid_territory_code",
    "is_valid_currency_code",
    # Cache management
    "clear_iso_cache",
    # Exceptions
    "BabelImportError",
]

_BABEL_FEATURE = "ISO introspection"


# ============================================================================
# TYPE ALIASES (PEP 695)
# ============================================================================

type TerritoryCode = str
"""ISO 3166-1 alpha-2 territory code (e.g., 'US', 'LV', 'DE')."""

type CurrencyCode = str
"""ISO 4217 currency code (e.g., 'USD', 'EUR', 'GBP')."""


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass(frozen=True, slots=True)
class TerritoryInfo:
    """ISO 3166-1 territory data with localized name.

    Immutable, thread-safe, hashable. Safe for use as dict key or set member.

    Attributes:
        alpha2: ISO 3166-1 alpha-2 code (e.g., 'US', 'DE').
        name: Localized display name (depends on locale used for lookup).
        currencies: All active legal tender currencies for this territory.
            Multi-currency territories (e.g., Panama: PAB, USD) have multiple entries.
            Empty tuple if no currency data available.
    """

    alpha2: TerritoryCode
    name: str
    currencies: tuple[CurrencyCode, ...]


@dataclass(frozen=True, slots=True)
class CurrencyInfo:
    """ISO 4217 currency data with localized presentation.

    Immutable, thread-safe, hashable. Safe for use as dict key or set member.

    Attributes:
        code: ISO 4217 currency code (e.g., 'USD', 'EUR').
        name: Localized display name (depends on locale used for lookup).
        symbol: Locale-specific symbol (e.g., '$', 'EUR', 'USD').
        decimal_digits: Standard decimal places (0, 2, 3, or 4).
    """

    code: CurrencyCode
    name: str
    symbol: str
    decimal_digits: int


# ============================================================================
# BABEL INTERFACE (LAZY IMPORT)
# ============================================================================


def _get_babel_locale(locale_str: str) -> object:
    """Get Babel Locale object, raising BabelImportError if unavailable."""
    try:
        from babel import Locale  # noqa: PLC0415
    except ImportError as e:
        raise BabelImportError(_BABEL_FEATURE) from e
    return Locale.parse(locale_str)


def _get_babel_territories(locale_str: str) -> dict[str, str]:
    """Get territory names from Babel for a locale.

    Returns empty dict if locale is invalid or data unavailable.
    """
    try:
        locale = _get_babel_locale(locale_str)
        return locale.territories  # type: ignore[attr-defined, no-any-return]
    except (ValueError, LookupError, KeyError, AttributeError):
        # Standard library exceptions from invalid data
        return {}
    except Exception as exc:
        # Babel's UnknownLocaleError inherits directly from Exception
        # (not LookupError). Import and check by type for precision.
        try:
            from babel.core import UnknownLocaleError  # noqa: PLC0415
        except ImportError:
            raise exc from None  # Babel unavailable; propagate original error
        if isinstance(exc, UnknownLocaleError):
            return {}
        raise  # Re-raise unexpected errors (logic bugs)


def _get_babel_currencies() -> dict[str, str]:
    """Get currency names from Babel (English)."""
    locale = _get_babel_locale("en")
    return locale.currencies  # type: ignore[attr-defined, no-any-return]


def _get_babel_currency_name(code: str, locale_str: str) -> str | None:
    """Get localized currency name from Babel.

    Returns None if the currency code is not found in CLDR data.
    """
    try:
        from babel import Locale  # noqa: PLC0415
        from babel.numbers import get_currency_name  # noqa: PLC0415
    except ImportError as e:
        raise BabelImportError(_BABEL_FEATURE) from e
    try:
        # Validate code exists in CLDR currency data before getting name
        # Babel returns input code if not found, so we check explicitly
        locale = Locale.parse(locale_str)
        if code.upper() not in locale.currencies:
            return None
        return get_currency_name(code, locale=locale_str)
    except (ValueError, LookupError, KeyError, AttributeError):
        # Babel raises ValueError/LookupError for invalid locales,
        # KeyError/AttributeError for missing data. Logic bugs (NameError,
        # TypeError) propagate to fail fast in financial-grade contexts.
        return None
    except Exception as exc:
        # Babel's UnknownLocaleError inherits directly from Exception
        # (not LookupError). Import and check by type for precision.
        try:
            from babel.core import UnknownLocaleError  # noqa: PLC0415
        except ImportError:
            raise exc from None  # Babel unavailable; propagate original error
        if isinstance(exc, UnknownLocaleError):
            return None
        raise  # Re-raise unexpected errors (logic bugs)


def _get_babel_currency_symbol(code: str, locale_str: str) -> str:
    """Get localized currency symbol from Babel."""
    try:
        from babel.numbers import get_currency_symbol  # noqa: PLC0415
    except ImportError as e:
        raise BabelImportError(_BABEL_FEATURE) from e
    try:
        return get_currency_symbol(code, locale=locale_str)
    except (ValueError, LookupError, KeyError, AttributeError):
        # Babel raises ValueError/LookupError for invalid locales,
        # KeyError/AttributeError for unknown codes. Logic bugs propagate.
        return code
    except Exception as exc:
        # Babel's UnknownLocaleError inherits directly from Exception
        # (not LookupError). Import and check by type for precision.
        try:
            from babel.core import UnknownLocaleError  # noqa: PLC0415
        except ImportError:
            raise exc from None  # Babel unavailable; propagate original error
        if isinstance(exc, UnknownLocaleError):
            return code
        raise  # Re-raise unexpected errors (logic bugs)


def _get_babel_territory_currencies(territory: str) -> list[str]:
    """Get currencies used by a territory from Babel.

    Returns list of currently active legal tender currencies.
    """
    try:
        from babel.core import get_global  # noqa: PLC0415
    except ImportError as e:
        raise BabelImportError(_BABEL_FEATURE) from e
    try:
        # Data format: list of (code, start_date, end_date, tender)
        # end_date=None means still active; tender=True means legal tender
        territory_currencies = get_global("territory_currencies")
        currencies_info = territory_currencies.get(territory, [])

        # Return currently active tender currencies (end_date is None, tender is True)
        return [c[0] for c in currencies_info if c[2] is None and c[3]]
    except (ValueError, LookupError, KeyError, AttributeError):
        # Babel raises ValueError/LookupError for invalid locales,
        # KeyError/AttributeError for data access. Logic bugs propagate.
        return []


# ============================================================================
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

    return TerritoryInfo(
        alpha2=code_upper,
        name=name,
        currencies=tuple(currencies),
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
        code=code_upper,
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
    return _get_currency_impl(code.upper(), normalize_locale(locale))


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
            result.add(
                TerritoryInfo(
                    alpha2=code,
                    name=name,
                    currencies=tuple(currencies),
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
                        code=code,
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
    return tuple(currencies)


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


def clear_iso_cache() -> None:
    """Clear all ISO introspection caches.

    Call this if you need to free memory or after locale configuration changes.
    Thread-safe.
    """
    _get_territory_impl.cache_clear()
    _get_currency_impl.cache_clear()
    _list_territories_impl.cache_clear()
    _list_currencies_impl.cache_clear()
    _get_territory_currencies_impl.cache_clear()
    _territory_codes_impl.cache_clear()
    _currency_codes_impl.cache_clear()
