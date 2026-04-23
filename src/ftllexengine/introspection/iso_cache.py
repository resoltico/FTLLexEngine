"""Cache management helpers for ISO introspection."""

from __future__ import annotations

from ftllexengine.introspection.iso_babel import _get_babel_currencies
from ftllexengine.introspection.iso_lookup import (
    _get_currency_impl,
    _get_territory_currencies_impl,
    _get_territory_impl,
    _list_currencies_impl,
    _list_territories_impl,
)
from ftllexengine.introspection.iso_validation import (
    _currency_codes_impl,
    _territory_codes_impl,
)


def clear_iso_cache() -> None:
    """Clear all ISO introspection caches."""
    _get_babel_currencies.cache_clear()
    _get_territory_impl.cache_clear()
    _get_currency_impl.cache_clear()
    _list_territories_impl.cache_clear()
    _list_currencies_impl.cache_clear()
    _get_territory_currencies_impl.cache_clear()
    _territory_codes_impl.cache_clear()
    _currency_codes_impl.cache_clear()
