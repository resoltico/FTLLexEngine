"""Bi-directional localization parsing.

Parses locale-aware display strings back to Python types.

Exception Contract:
    - Parse errors (malformed input, unknown locale): Returned in error tuple
    - Configuration errors (missing Babel): Raises BabelImportError

Parsing functions require Babel for CLDR data. If Babel is not installed,
functions raise BabelImportError with installation instructions.

Public API:
    Type Aliases:
        ParseResult[T] - Generic type for parsing function returns:
                         tuple[T | None, tuple[FrozenFluentError, ...]]

    Parsing Functions:
        parse_decimal - Returns ParseResult[Decimal]
        parse_fluent_number - Returns ParseResult[FluentNumber]
        parse_date - Returns ParseResult[date]
        parse_datetime - Returns ParseResult[datetime]
        parse_currency - Returns ParseResult[tuple[Decimal, str]]

    Type Guards:
        is_valid_decimal - TypeIs guard for finite Decimal
        is_valid_currency - TypeIs guard for tuple[Decimal, str] (not None)
        is_valid_date - TypeIs guard for date (not None)
        is_valid_datetime - TypeIs guard for datetime (not None)

    Cache Lifecycle:
        clear_date_caches - Clear cached CLDR date/datetime patterns
        clear_currency_caches - Clear cached CLDR currency data

Examples:
    >>> from ftllexengine.parsing import parse_decimal, is_valid_decimal  # doctest: +SKIP
    >>> result, errors = parse_decimal("1 234,56", "lv_LV")  # doctest: +SKIP
    >>> if not errors and is_valid_decimal(result):  # doctest: +SKIP
    ...     total = result.quantize(Decimal("0.01"))

Python 3.13+. Requires Babel for CLDR patterns.
"""

from ftllexengine.diagnostics import ParseResult

from .currency import clear_currency_caches, parse_currency
from .dates import clear_date_caches, parse_date, parse_datetime
from .guards import (
    is_valid_currency,
    is_valid_date,
    is_valid_datetime,
    is_valid_decimal,
)
from .numbers import parse_decimal, parse_fluent_number

__all__ = [
    "ParseResult",
    "clear_currency_caches",
    "clear_date_caches",
    "is_valid_currency",
    "is_valid_date",
    "is_valid_datetime",
    "is_valid_decimal",
    "parse_currency",
    "parse_date",
    "parse_datetime",
    "parse_decimal",
    "parse_fluent_number",
]
