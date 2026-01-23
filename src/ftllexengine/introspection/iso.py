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
from functools import cache
from typing import TYPE_CHECKING, TypeIs

from ftllexengine.constants import ISO_4217_DECIMAL_DIGITS, ISO_4217_DEFAULT_DECIMALS

if TYPE_CHECKING:
    pass

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
    "get_territory_currency",
    # Type guards
    "is_valid_territory_code",
    "is_valid_currency_code",
    # Cache management
    "clear_iso_cache",
    # Exceptions
    "BabelImportError",
]


# ============================================================================
# EXCEPTIONS
# ============================================================================


class BabelImportError(ImportError):
    """Raised when Babel is required but not installed.

    Provides installation guidance to users.
    """

    def __init__(self) -> None:
        super().__init__(
            "Babel is required for ISO introspection features. "
            "Install with: pip install ftllexengine[babel]"
        )


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
        default_currency: Primary currency code or None if unknown.
    """

    alpha2: TerritoryCode
    name: str
    default_currency: CurrencyCode | None


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
        raise BabelImportError from e
    return Locale.parse(locale_str)


def _get_babel_territories(locale_str: str) -> dict[str, str]:
    """Get territory names from Babel for a locale."""
    locale = _get_babel_locale(locale_str)
    return locale.territories  # type: ignore[attr-defined, no-any-return]


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
        raise BabelImportError from e
    try:
        # Validate code exists in CLDR currency data before getting name
        # Babel returns input code if not found, so we check explicitly
        locale = Locale.parse(locale_str)
        if code.upper() not in locale.currencies:
            return None
        return get_currency_name(code, locale=locale_str)
    except Exception:  # pylint: disable=broad-exception-caught
        # Babel may raise various exceptions for invalid locales
        return None


def _get_babel_currency_symbol(code: str, locale_str: str) -> str:
    """Get localized currency symbol from Babel."""
    try:
        from babel.numbers import get_currency_symbol  # noqa: PLC0415
    except ImportError as e:
        raise BabelImportError from e
    try:
        return get_currency_symbol(code, locale=locale_str)
    except Exception:  # pylint: disable=broad-exception-caught
        # Babel may raise various exceptions for unknown codes or invalid locales
        return code


def _get_babel_territory_currencies(territory: str) -> list[str]:
    """Get currencies used by a territory from Babel.

    Returns list of currently active legal tender currencies.
    """
    try:
        from babel.core import get_global  # noqa: PLC0415
    except ImportError as e:
        raise BabelImportError from e
    try:
        # Data format: list of (code, start_date, end_date, tender)
        # end_date=None means still active; tender=True means legal tender
        territory_currencies = get_global("territory_currencies")
        currencies_info = territory_currencies.get(territory, [])

        # Return currently active tender currencies (end_date is None, tender is True)
        return [c[0] for c in currencies_info if c[2] is None and c[3]]
    except Exception:  # pylint: disable=broad-exception-caught
        # Babel data structure may change; degrade gracefully
        return []


# ============================================================================
# CACHED LOOKUP FUNCTIONS
# ============================================================================


@cache
def get_territory(
    code: str,
    locale: str = "en",
) -> TerritoryInfo | None:
    """Look up ISO 3166-1 territory by alpha-2 code.

    Args:
        code: ISO 3166-1 alpha-2 code (e.g., 'US', 'LV'). Case-insensitive.
        locale: Locale for name localization (default: 'en').

    Returns:
        TerritoryInfo if found, None if unknown code.

    Raises:
        BabelImportError: If Babel not installed.

    Thread-safe. Results cached per (code, locale) pair.
    """
    code_upper = code.upper()
    territories = _get_babel_territories(locale)

    if code_upper not in territories:
        return None

    name = territories[code_upper]
    default_currency = get_territory_currency(code_upper)

    return TerritoryInfo(
        alpha2=code_upper,
        name=name,
        default_currency=default_currency,
    )


@cache
def get_currency(
    code: str,
    locale: str = "en",
) -> CurrencyInfo | None:
    """Look up ISO 4217 currency by code.

    Args:
        code: ISO 4217 currency code (e.g., 'USD', 'EUR'). Case-insensitive.
        locale: Locale for name/symbol localization (default: 'en').

    Returns:
        CurrencyInfo if found, None if unknown code.

    Raises:
        BabelImportError: If Babel not installed.

    Thread-safe. Results cached per (code, locale) pair.
    """
    code_upper = code.upper()
    name = _get_babel_currency_name(code_upper, locale)

    if name is None:
        return None

    symbol = _get_babel_currency_symbol(code_upper, locale)
    decimal_digits = ISO_4217_DECIMAL_DIGITS.get(code_upper, ISO_4217_DEFAULT_DECIMALS)

    return CurrencyInfo(
        code=code_upper,
        name=name,
        symbol=symbol,
        decimal_digits=decimal_digits,
    )


@cache
def list_territories(
    locale: str = "en",
) -> frozenset[TerritoryInfo]:
    """List all known ISO 3166-1 territories.

    Args:
        locale: Locale for name localization (default: 'en').

    Returns:
        Frozen set of all TerritoryInfo objects.

    Raises:
        BabelImportError: If Babel not installed.

    Thread-safe. Result cached per locale.
    """
    territories = _get_babel_territories(locale)
    result: set[TerritoryInfo] = set()

    for code, name in territories.items():
        # Filter to alpha-2 codes only (2 uppercase letters)
        if len(code) == 2 and code.isalpha() and code.isupper():
            default_currency = get_territory_currency(code)
            result.add(
                TerritoryInfo(
                    alpha2=code,
                    name=name,
                    default_currency=default_currency,
                )
            )

    return frozenset(result)


@cache
def list_currencies(
    locale: str = "en",
) -> frozenset[CurrencyInfo]:
    """List all known ISO 4217 currencies.

    Args:
        locale: Locale for name/symbol localization (default: 'en').

    Returns:
        Frozen set of all CurrencyInfo objects.

    Raises:
        BabelImportError: If Babel not installed.

    Thread-safe. Result cached per locale.
    """
    # Get all currency codes from Babel (English locale has complete list)
    currencies_en = _get_babel_currencies()
    result: set[CurrencyInfo] = set()

    for code in currencies_en:
        # Filter to valid ISO 4217 codes (3 uppercase letters)
        if len(code) == 3 and code.isalpha() and code.isupper():
            info = get_currency(code, locale)
            if info is not None:
                result.add(info)

    return frozenset(result)


@cache
def get_territory_currency(territory: str) -> CurrencyCode | None:
    """Get default currency for a territory.

    Args:
        territory: ISO 3166-1 alpha-2 code. Case-insensitive.

    Returns:
        ISO 4217 currency code or None if unknown.

    Raises:
        BabelImportError: If Babel not installed.

    Thread-safe. Result cached.
    """
    territory_upper = territory.upper()
    currencies = _get_babel_territory_currencies(territory_upper)

    if not currencies:
        return None

    # Return first active tender currency
    return currencies[0]


# ============================================================================
# TYPE GUARDS (PEP 742)
# ============================================================================


def is_valid_territory_code(value: str) -> TypeIs[TerritoryCode]:
    """Check if string is a valid ISO 3166-1 alpha-2 code.

    Validates against Babel's CLDR territory database.

    Args:
        value: String to check.

    Returns:
        True if value is a known ISO 3166-1 alpha-2 code.

    Raises:
        BabelImportError: If Babel not installed.
    """
    if not isinstance(value, str) or len(value) != 2:
        return False
    # BabelImportError propagates naturally from get_territory
    return get_territory(value) is not None


def is_valid_currency_code(value: str) -> TypeIs[CurrencyCode]:
    """Check if string is a valid ISO 4217 currency code.

    Validates against Babel's CLDR currency database.

    Args:
        value: String to check.

    Returns:
        True if value is a known ISO 4217 currency code.

    Raises:
        BabelImportError: If Babel not installed.
    """
    if not isinstance(value, str) or len(value) != 3:
        return False
    # BabelImportError propagates naturally from get_currency
    return get_currency(value) is not None


# ============================================================================
# CACHE MANAGEMENT
# ============================================================================


def clear_iso_cache() -> None:
    """Clear all ISO introspection caches.

    Call this if you need to free memory or after locale configuration changes.
    Thread-safe.
    """
    get_territory.cache_clear()
    get_currency.cache_clear()
    list_territories.cache_clear()
    list_currencies.cache_clear()
    get_territory_currency.cache_clear()
