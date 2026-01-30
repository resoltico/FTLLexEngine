"""Introspection capabilities for FTL messages and ISO standards data.

This package provides two introspection domains:

1. Message Introspection (ftllexengine.introspection.message):
   - Variable extraction from FTL patterns
   - Function call detection
   - Message/term reference tracking
   - No external dependencies

2. ISO Standards Introspection (ftllexengine.introspection.iso):
   - ISO 3166-1 territory codes and names
   - ISO 4217 currency codes, symbols, and decimal places
   - Requires Babel for CLDR data

Python 3.13+.
"""

# ruff: noqa: I001 - Imports grouped by domain (message, iso) for readability
# ruff: noqa: RUF022 - __all__ organized by category for readability

# Message introspection - public API (always available)
from .message import (
    FunctionCallInfo,
    MessageIntrospection,
    ReferenceInfo,
    VariableInfo,
    clear_introspection_cache,
    extract_references,
    extract_references_by_attribute,
    extract_variables,
    introspect_message,
)

# ISO introspection - public API (always importable; functions raise if no Babel)
from .iso import (
    BabelImportError,
    CurrencyCode,
    CurrencyInfo,
    TerritoryCode,
    TerritoryInfo,
    clear_iso_cache,
    get_currency,
    get_territory,
    get_territory_currencies,
    is_valid_currency_code,
    is_valid_territory_code,
    list_currencies,
    list_territories,
)

__all__ = [
    # Message introspection types
    "FunctionCallInfo",
    "MessageIntrospection",
    "ReferenceInfo",
    "VariableInfo",
    # Message introspection functions
    "clear_introspection_cache",
    "extract_references",
    "extract_references_by_attribute",
    "extract_variables",
    "introspect_message",
    # ISO introspection exceptions
    "BabelImportError",
    # ISO type aliases
    "TerritoryCode",
    "CurrencyCode",
    # ISO data classes
    "TerritoryInfo",
    "CurrencyInfo",
    # ISO lookup functions
    "get_territory",
    "get_currency",
    "list_territories",
    "list_currencies",
    "get_territory_currencies",
    # ISO type guards
    "is_valid_territory_code",
    "is_valid_currency_code",
    # ISO cache management
    "clear_iso_cache",
]
