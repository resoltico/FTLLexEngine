"""Bi-directional localization and fiscal calendar arithmetic.

This module provides:
1. Parse locale-aware display strings back to Python types
2. Fiscal calendar arithmetic for financial date calculations

Exception Contract:
    - Parse errors (malformed input, unknown locale): Returned in error tuple
    - Configuration errors (missing Babel): Raises BabelImportError

Parsing functions require Babel for CLDR data. If Babel is not installed,
functions raise BabelImportError with installation instructions.
Fiscal calendar functions do NOT require Babel.

Public API:
    Type Aliases:
        ParseResult[T] - Generic type for parsing function returns:
                         tuple[T | None, tuple[FrozenFluentError, ...]]

    Parsing Functions:
        parse_decimal - Returns ParseResult[Decimal]
        parse_date - Returns ParseResult[date]
        parse_datetime - Returns ParseResult[datetime]
        parse_currency - Returns ParseResult[tuple[Decimal, str]]

    Type Guards:
        is_valid_decimal - TypeIs guard for finite Decimal
        is_valid_currency - TypeIs guard for tuple[Decimal, str] (not None)
        is_valid_date - TypeIs guard for date (not None)
        is_valid_datetime - TypeIs guard for datetime (not None)

    Fiscal Calendar:
        FiscalCalendar - Configuration for fiscal year boundaries
        FiscalDelta - Immutable period delta (years, quarters, months, days)
        FiscalPeriod - Immutable fiscal period identifier
        MonthEndPolicy - Enum for month-end date handling
        fiscal_quarter - Get fiscal quarter for a date
        fiscal_year - Get fiscal year for a date
        fiscal_month - Get fiscal month for a date
        fiscal_year_start - Get first day of a fiscal year
        fiscal_year_end - Get last day of a fiscal year

    Cache Lifecycle:
        clear_date_caches - Clear cached CLDR date/datetime patterns
        clear_currency_caches - Clear cached CLDR currency data

Examples:
    Parsing:
        >>> from ftllexengine.parsing import parse_decimal, is_valid_decimal
        >>> result, errors = parse_decimal("1 234,56", "lv_LV")
        >>> if not errors and is_valid_decimal(result):
        ...     total = result.quantize(Decimal("0.01"))

    Fiscal Calendar:
        >>> from ftllexengine.parsing import FiscalCalendar, FiscalDelta
        >>> cal = FiscalCalendar(start_month=4)  # UK fiscal year
        >>> cal.fiscal_quarter(date(2024, 7, 15))  # Returns 2 (Q2)
        >>> delta = FiscalDelta(months=1)
        >>> delta.add_to(date(2024, 1, 31))  # Returns date(2024, 2, 29)

Python 3.13+. Parsing uses Babel CLDR patterns; fiscal uses stdlib only.
"""

from ftllexengine.core.fiscal import (
    FiscalCalendar,
    FiscalDelta,
    FiscalPeriod,
    MonthEndPolicy,
    fiscal_month,
    fiscal_quarter,
    fiscal_year,
    fiscal_year_end,
    fiscal_year_start,
)
from ftllexengine.diagnostics import FrozenFluentError

from .currency import clear_currency_caches, parse_currency
from .dates import clear_date_caches, parse_date, parse_datetime
from .guards import (
    is_valid_currency,
    is_valid_date,
    is_valid_datetime,
    is_valid_decimal,
)
from .numbers import parse_decimal

# Type alias for parsing function return values (defined after imports to satisfy linting)
type ParseResult[T] = tuple[T | None, tuple[FrozenFluentError, ...]]
"""Generic type alias for parsing function return values.

All parse_* functions return this pattern:
- First element: Parsed value (None on failure)
- Second element: Tuple of errors (empty on success)

Example:
    >>> result, errors = parse_decimal("1,234.56", "en_US")
    >>> if not errors:
    ...     print(f"Parsed: {result}")
"""

# ruff: noqa: RUF022 - __all__ organized by category for readability
__all__ = [
    # Type alias
    "ParseResult",
    # Cache lifecycle
    "clear_currency_caches",
    "clear_date_caches",
    # Type guards
    "is_valid_currency",
    "is_valid_date",
    "is_valid_datetime",
    "is_valid_decimal",
    # Parsing functions
    "parse_currency",
    "parse_date",
    "parse_datetime",
    "parse_decimal",
    # Fiscal calendar
    "FiscalCalendar",
    "FiscalDelta",
    "FiscalPeriod",
    "MonthEndPolicy",
    "fiscal_month",
    "fiscal_quarter",
    "fiscal_year",
    "fiscal_year_end",
    "fiscal_year_start",
]
