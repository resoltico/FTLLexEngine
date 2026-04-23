"""ISO 3166/4217 introspection API via Babel CLDR data.

Provides type-safe access to ISO standards data for territories and currencies.
All types are immutable, hashable, and thread-safe. Results are cached for
performance.

Requires Babel installation for full functionality:
    pip install ftllexengine[babel]

Parser-only installs may still use `get_currency_decimal_digits()` because it
reads embedded ISO 4217 tables instead of CLDR locale data.

Python 3.13+. Babel is optional dependency.
"""

from __future__ import annotations

# ruff: noqa: SLF001 - facade intentionally re-exports tested private cache helpers
from ftllexengine.core.babel_compat import BabelImportError
from ftllexengine.introspection import iso_babel as _iso_babel
from ftllexengine.introspection import iso_lookup as _iso_lookup
from ftllexengine.introspection import iso_validation as _iso_validation
from ftllexengine.introspection.iso_cache import clear_iso_cache
from ftllexengine.introspection.iso_types import (
    CurrencyCode,
    CurrencyInfo,
    TerritoryCode,
    TerritoryInfo,
)

_get_babel_currencies = _iso_babel._get_babel_currencies
_get_babel_currency_name = _iso_babel._get_babel_currency_name
_get_babel_currency_symbol = _iso_babel._get_babel_currency_symbol
_get_babel_official_languages = _iso_babel._get_babel_official_languages
_get_babel_territories = _iso_babel._get_babel_territories
_get_babel_territory_currencies = _iso_babel._get_babel_territory_currencies

_get_currency_impl = _iso_lookup._get_currency_impl
_get_territory_currencies_impl = _iso_lookup._get_territory_currencies_impl
_get_territory_impl = _iso_lookup._get_territory_impl
_list_currencies_impl = _iso_lookup._list_currencies_impl
_list_territories_impl = _iso_lookup._list_territories_impl
get_currency = _iso_lookup.get_currency
get_currency_decimal_digits = _iso_lookup.get_currency_decimal_digits
get_territory = _iso_lookup.get_territory
get_territory_currencies = _iso_lookup.get_territory_currencies
list_currencies = _iso_lookup.list_currencies
list_territories = _iso_lookup.list_territories

_currency_codes_impl = _iso_validation._currency_codes_impl
_territory_codes_impl = _iso_validation._territory_codes_impl
is_valid_currency_code = _iso_validation.is_valid_currency_code
is_valid_territory_code = _iso_validation.is_valid_territory_code
require_currency_code = _iso_validation.require_currency_code
require_territory_code = _iso_validation.require_territory_code

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
