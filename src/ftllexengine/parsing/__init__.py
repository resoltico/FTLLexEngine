"""Bi-directional localization: Parse locale-aware display strings back to Python types.

Exception Contract:
    - Parse errors (malformed input, unknown locale): Returned in error tuple
    - Configuration errors (missing Babel): Raises BabelImportError

All parsing functions require Babel for CLDR data. If Babel is not installed,
functions raise BabelImportError with installation instructions.

This module provides the inverse operations to ftllexengine.runtime.functions:
- Formatting: Python data -> locale-aware display string
- Parsing: Locale-aware display string -> Python data

All parsing functions are thread-safe and use Babel for CLDR-compliant parsing.

Public API:
    Type Aliases:
        ParseResult[T] - Generic type for parsing function returns:
                         tuple[T | None, tuple[FluentParseError, ...]]

    Parsing Functions:
        parse_number - Returns ParseResult[float]
        parse_decimal - Returns ParseResult[Decimal]
        parse_date - Returns ParseResult[date]
        parse_datetime - Returns ParseResult[datetime]
        parse_currency - Returns ParseResult[tuple[Decimal, str]]

    Type Guards:
        is_valid_decimal - TypeIs guard for finite Decimal
        is_valid_number - TypeIs guard for finite float
        is_valid_currency - TypeIs guard for tuple[Decimal, str] (not None)
        is_valid_date - TypeIs guard for date (not None)
        is_valid_datetime - TypeIs guard for datetime (not None)

Example:
    >>> from ftllexengine.parsing import parse_decimal, is_valid_decimal
    >>> result, errors = parse_decimal("1 234,56", "lv_LV")
    >>> if not errors and is_valid_decimal(result):
    ...     # mypy knows result is finite Decimal
    ...     total = result.quantize(Decimal("0.01"))

Python 3.13+. Uses Babel CLDR patterns + stdlib for all parsing.
"""

from ftllexengine.diagnostics import FluentParseError

from .currency import parse_currency
from .dates import parse_date, parse_datetime
from .guards import (
    is_valid_currency,
    is_valid_date,
    is_valid_datetime,
    is_valid_decimal,
    is_valid_number,
)
from .numbers import parse_decimal, parse_number

# Type alias for parsing function return values (defined after imports to satisfy linting)
type ParseResult[T] = tuple[T | None, tuple[FluentParseError, ...]]
"""Generic type alias for parsing function return values.

All parse_* functions return this pattern:
- First element: Parsed value (None on failure)
- Second element: Tuple of errors (empty on success)

Example:
    >>> result, errors = parse_decimal("1,234.56", "en_US")
    >>> if not errors:
    ...     print(f"Parsed: {result}")
"""

__all__ = [
    # Type alias
    "ParseResult",
    # Type guards
    "is_valid_currency",
    "is_valid_date",
    "is_valid_datetime",
    "is_valid_decimal",
    "is_valid_number",
    # Parsing functions
    "parse_currency",
    "parse_date",
    "parse_datetime",
    "parse_decimal",
    "parse_number",
]
