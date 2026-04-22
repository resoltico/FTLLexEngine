"""Lazy Babel bridge helpers for ISO introspection."""

from __future__ import annotations

from functools import lru_cache

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


def _get_babel_locale(locale_str: str) -> object:
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


def _get_babel_territories(locale_str: str) -> dict[str, str]:
    """Get territory names from Babel for a locale."""
    try:
        locale = _get_babel_locale(locale_str)
        return locale.territories  # type: ignore[attr-defined, no-any-return]
    except (ValueError, LookupError, KeyError, AttributeError):
        return {}
    except Exception as exc:
        if _is_unknown_locale_error(exc):
            return {}
        raise


@lru_cache(maxsize=1)
def _get_babel_currencies() -> dict[str, str]:
    """Get English currency names from Babel. Result is invariant; cached once."""
    locale = _get_babel_locale("en")
    return locale.currencies  # type: ignore[attr-defined, no-any-return]


def _get_babel_currency_name(code: str, locale_str: str) -> str | None:
    """Get localized currency name from Babel."""
    locale_class = get_locale_class()
    babel_numbers = get_babel_numbers()
    try:
        locale = locale_class.parse(locale_str)
        if code.upper() not in locale.currencies:
            return None
        return str(babel_numbers.get_currency_name(code, locale=locale_str))
    except (ValueError, LookupError, KeyError, AttributeError):
        return None
    except Exception as exc:
        if _is_unknown_locale_error(exc):
            return None
        raise


def _get_babel_currency_symbol(code: str, locale_str: str) -> str:
    """Get localized currency symbol from Babel."""
    babel_numbers = get_babel_numbers()
    try:
        return str(babel_numbers.get_currency_symbol(code, locale=locale_str))
    except (ValueError, LookupError, KeyError, AttributeError):
        return code
    except Exception as exc:
        if _is_unknown_locale_error(exc):
            return code
        raise


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
