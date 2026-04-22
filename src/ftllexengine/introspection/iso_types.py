"""Type definitions for ISO territory and currency introspection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NewType

__all__ = [
    "CurrencyCode",
    "CurrencyInfo",
    "TerritoryCode",
    "TerritoryInfo",
]


TerritoryCode = NewType("TerritoryCode", str)
"""ISO 3166-1 alpha-2 territory code (e.g., 'US', 'LV', 'DE').

Nominal subtype of str. Use is_valid_territory_code() to narrow a plain str
to TerritoryCode; both branches are then reachable, preventing false
unreachable diagnostics at validation sites.
"""


CurrencyCode = NewType("CurrencyCode", str)
"""ISO 4217 currency code (e.g., 'USD', 'EUR', 'GBP').

Nominal subtype of str. Use is_valid_currency_code() to narrow a plain str
to CurrencyCode; both branches are then reachable, preventing false
unreachable diagnostics at validation sites.
"""


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
        official_languages: BCP-47 language codes of official languages for this
            territory (e.g., ('en',) for 'US', ('fr', 'nl', 'de') for 'BE').
            Empty tuple if no language data is available in CLDR.
    """

    alpha2: TerritoryCode
    name: str
    currencies: tuple[CurrencyCode, ...]
    official_languages: tuple[str, ...]


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
