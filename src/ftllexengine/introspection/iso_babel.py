"""Lazy Babel bridge helpers for ISO introspection."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from ftllexengine.core.babel_compat import (
    BabelImportError,
    get_babel_languages,
    get_babel_numbers,
    get_locale_class,
    get_unknown_locale_error_class,
)

__all__ = [
    "_get_babel_currencies",
    "_get_babel_currency_name",
    "_get_babel_currency_symbol",
    "_get_babel_locale",
    "_get_babel_official_languages",
    "_get_babel_territories",
    "_get_babel_territory_currencies",
    "_is_unknown_locale_error",
]

if TYPE_CHECKING:
    from babel import Locale


def _get_babel_locale(locale_str: str) -> Locale:
    """Get Babel Locale object, raising BabelImportError if unavailable."""
    locale_class = get_locale_class()
    return locale_class.parse(locale_str)


def _is_unknown_locale_error(exc: Exception) -> bool:
    """Return True if exc is Babel's UnknownLocaleError."""
    try:
        unknown_locale_error_class = get_unknown_locale_error_class()
    except BabelImportError:
        return False
    return isinstance(exc, unknown_locale_error_class)


def _maybe_unknown_locale_error_class() -> type[Exception] | None:
    """Return Babel's UnknownLocaleError class when available."""
    try:
        return get_unknown_locale_error_class()
    except BabelImportError:
        return None


def _get_babel_territories(locale_str: str) -> dict[str, str]:
    """Get territory names from Babel for a locale."""
    unknown_locale_error = _maybe_unknown_locale_error_class()
    if unknown_locale_error is None:
        try:
            locale = _get_babel_locale(locale_str)
            return dict(locale.territories)
        except (ValueError, LookupError, KeyError, AttributeError):
            return {}

    try:
        locale = _get_babel_locale(locale_str)
        return dict(locale.territories)
    except (ValueError, LookupError, KeyError, AttributeError, unknown_locale_error):
        return {}


@lru_cache(maxsize=1)
def _get_babel_currencies() -> dict[str, str]:
    """Get English currency names from Babel. Result is invariant; cached once."""
    locale = _get_babel_locale("en")
    return dict(locale.currencies)


def _get_babel_currency_name(code: str, locale_str: str) -> str | None:
    """Get localized currency name from Babel."""
    locale_class = get_locale_class()
    babel_numbers = get_babel_numbers()
    unknown_locale_error = _maybe_unknown_locale_error_class()
    if unknown_locale_error is None:
        try:
            locale = locale_class.parse(locale_str)
            if code.upper() not in locale.currencies:
                return None
            return str(babel_numbers.get_currency_name(code, locale=locale_str))
        except (ValueError, LookupError, KeyError, AttributeError):
            return None

    try:
        locale = locale_class.parse(locale_str)
        if code.upper() not in locale.currencies:
            return None
        return str(babel_numbers.get_currency_name(code, locale=locale_str))
    except (ValueError, LookupError, KeyError, AttributeError, unknown_locale_error):
        return None


def _get_babel_currency_symbol(code: str, locale_str: str) -> str:
    """Get localized currency symbol from Babel."""
    babel_numbers = get_babel_numbers()
    unknown_locale_error = _maybe_unknown_locale_error_class()
    if unknown_locale_error is None:
        try:
            return str(babel_numbers.get_currency_symbol(code, locale=locale_str))
        except (ValueError, LookupError, KeyError, AttributeError):
            return code

    try:
        return str(babel_numbers.get_currency_symbol(code, locale=locale_str))
    except (ValueError, LookupError, KeyError, AttributeError, unknown_locale_error):
        return code


def _get_babel_territory_currencies(territory: str) -> list[str]:
    """Get currencies used by a territory from Babel."""
    babel_numbers = get_babel_numbers()
    try:
        return list(babel_numbers.get_territory_currencies(territory, tender=True))
    except (ValueError, LookupError, KeyError, AttributeError):
        return []


def _get_babel_official_languages(territory: str) -> tuple[str, ...]:
    """Get official language codes for a territory from Babel CLDR data."""
    babel_languages = get_babel_languages()
    try:
        return tuple(babel_languages.get_official_languages(territory))
    except (ValueError, LookupError, KeyError, AttributeError):
        return ()
