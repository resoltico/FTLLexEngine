"""ISO type guards and boundary validators."""

from __future__ import annotations

from functools import lru_cache
from typing import TypeIs

from ftllexengine.constants import MAX_LOCALE_CACHE_SIZE
from ftllexengine.core.locale_utils import normalize_locale
from ftllexengine.introspection.iso_lookup import (
    _list_currencies_impl,
    _list_territories_impl,
)
from ftllexengine.introspection.iso_types import CurrencyCode, TerritoryCode


@lru_cache(maxsize=MAX_LOCALE_CACHE_SIZE)
def _territory_codes_impl(locale_norm: str) -> frozenset[str]:
    """Internal cached implementation returning all valid territory codes."""
    return frozenset(t.alpha2 for t in _list_territories_impl(locale_norm))


@lru_cache(maxsize=MAX_LOCALE_CACHE_SIZE)
def _currency_codes_impl(locale_norm: str) -> frozenset[str]:
    """Internal cached implementation returning all valid currency codes."""
    return frozenset(c.code for c in _list_currencies_impl(locale_norm))


def is_valid_territory_code(value: str) -> TypeIs[TerritoryCode]:
    """Check if string is a valid ISO 3166-1 alpha-2 code."""
    if not isinstance(value, str) or len(value) != 2:
        return False
    return value.upper() in _territory_codes_impl(normalize_locale("en"))


def is_valid_currency_code(value: str) -> TypeIs[CurrencyCode]:
    """Check if string is a valid ISO 4217 currency code."""
    if not isinstance(value, str) or len(value) != 3:
        return False
    return value.upper() in _currency_codes_impl(normalize_locale("en"))


def require_currency_code(value: object, field_name: str) -> CurrencyCode:
    """Validate and normalize a boundary value to a canonical ISO 4217 currency code."""
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
    """Validate and normalize a boundary value to a canonical ISO 3166-1 alpha-2 code."""
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
