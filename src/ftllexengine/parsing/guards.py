"""Type guard functions for parsing result type narrowing.

All parse_* functions return tuple[result, list[FluentParseError]].
Type guards check the result component to narrow types for mypy.

Provides TypeIs-based type guards for mypy to narrow parsing result types safely.
Particularly useful with mypy --strict for financial applications.

Python 3.13+ with TypeIs support (PEP 742).

Note: All guards accept None and return False. This simplifies the pattern from
`if not errors and is_valid_decimal(result)` to just `if is_valid_decimal(result)`.

Example:
    >>> from ftllexengine.parsing import parse_decimal
    >>> from ftllexengine.parsing.guards import is_valid_decimal
    >>> result, errors = parse_decimal("1,234.56", "en_US")
    >>> if is_valid_decimal(result):
    ...     # mypy knows result is finite Decimal
    ...     amount = result.quantize(Decimal("0.01"))
"""

import math
from datetime import date, datetime
from decimal import Decimal
from typing import TypeIs

__all__ = [
    "is_valid_currency",
    "is_valid_date",
    "is_valid_datetime",
    "is_valid_decimal",
    "is_valid_number",
]


def is_valid_decimal(value: Decimal | None) -> TypeIs[Decimal]:
    """Type guard: Check if parsed decimal is valid (not None/NaN/Infinity).

    Safe to call directly on parse_decimal() result without checking errors first.
    Returns False for None, NaN, and Infinity values.

    Args:
        value: Decimal from parse_decimal() result tuple (may be None on error)

    Returns:
        True if value is a finite Decimal, False otherwise

    Example:
        >>> result, errors = parse_decimal("1,234.56", "en_US")
        >>> if is_valid_decimal(result):
        ...     # Type-safe: mypy knows result is finite Decimal
        ...     total = result * Decimal("1.21")  # Add VAT
    """
    return value is not None and value.is_finite()


def is_valid_number(value: float | None) -> TypeIs[float]:
    """Type guard: Check if parsed number is valid (not None/NaN/Infinity).

    Safe to call directly on parse_number() result without checking errors first.
    Returns False for None, NaN, and Infinity values.

    Args:
        value: Float from parse_number() result tuple (may be None on error)

    Returns:
        True if value is a finite float, False otherwise

    Example:
        >>> result, errors = parse_number("1,234.56", "en_US")
        >>> if is_valid_number(result):
        ...     # Type-safe: mypy knows result is finite float
        ...     total = result * 1.21
    """
    return value is not None and math.isfinite(value)


def is_valid_currency(
    value: tuple[Decimal, str] | None,
) -> TypeIs[tuple[Decimal, str]]:
    """Type guard: Check if parsed currency is valid (not None, finite amount).

    Safe to call directly on parse_currency() result without checking errors first.
    Rejects None and verifies amount is finite.

    Args:
        value: Currency tuple from parse_currency() result (may be None on error)

    Returns:
        True if value is (Decimal, str) with finite amount, False otherwise

    Example:
        >>> result, errors = parse_currency("EUR1,234.56", "en_US")
        >>> if is_valid_currency(result):
        ...     # Type-safe: mypy knows result is tuple[Decimal, str]
        ...     amount, currency = result
        ...     total = amount * Decimal("1.21")
    """
    return value is not None and value[0].is_finite()


def is_valid_date(value: date | None) -> TypeIs[date]:
    """Type guard: Check if parsed date is valid (not None).

    Safe to call directly on parse_date() result without checking errors first.

    Args:
        value: Date from parse_date() result tuple (may be None on error)

    Returns:
        True if value is a date object, False otherwise

    Example:
        >>> result, errors = parse_date("2025-01-28", "en_US")
        >>> if is_valid_date(result):
        ...     # Type-safe: mypy knows result is date
        ...     year = result.year
    """
    return value is not None


def is_valid_datetime(value: datetime | None) -> TypeIs[datetime]:
    """Type guard: Check if parsed datetime is valid (not None).

    Safe to call directly on parse_datetime() result without checking errors first.

    Args:
        value: Datetime from parse_datetime() result tuple (may be None on error)

    Returns:
        True if value is a datetime object, False otherwise

    Example:
        >>> result, errors = parse_datetime("2025-01-28 14:30", "en_US")
        >>> if is_valid_datetime(result):
        ...     # Type-safe: mypy knows result is datetime
        ...     timestamp = result.timestamp()
    """
    return value is not None
