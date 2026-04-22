"""Domain-specific boundary validators for FTLLexEngine types and entry points.

Provides typed, fail-fast validators for use at system entry points —
constructor arguments, configuration fields, API parameters — where silent
acceptance of mis-typed values would propagate errors deep into the
processing pipeline.

Boundary validation contract (applied in order):
    1. Type check: reject the wrong Python type with TypeError.
    2. Value check: reject out-of-range or empty values with ValueError.
    3. Return the canonical form so callers need no post-validation normalization.

Scope: validators for types FTLLexEngine itself defines (FluentNumber,
date, datetime) plus require_positive_int used by internal CacheConfig
construction. Generic stdlib-type validators (require_int,
require_non_empty_str, coerce_tuple, etc.) are not part of the public
surface — they belong in the caller's own validation layer.

Python 3.13+.
"""

from __future__ import annotations

from datetime import date as _date
from datetime import datetime as _datetime

from .value_types import FluentNumber

__all__ = [
    "require_date",
    "require_datetime",
    "require_fluent_number",
    "require_positive_int",
]


def require_positive_int(value: object, field_name: str) -> int:
    """Validate that a boundary value is a positive integer.

    Rejects non-int types (including bool, which is an int subtype but
    semantically distinct) with TypeError, and rejects zero or negative
    values with ValueError. Returns the validated int unchanged.

    Use at every constructor or API entry point that requires a strictly
    positive integer field (cache sizes, buffer lengths, pool capacities).
    This eliminates the isinstance / positivity-check pattern that every
    downstream class would otherwise reimplement.

    Args:
        value: Raw boundary value to validate. Accepts any Python object;
            non-int values (including bool) always raise TypeError.
        field_name: Human-readable field label used in error messages.

    Returns:
        The validated positive integer, identical to the input value.

    Raises:
        TypeError: If value is not an int instance, or if value is bool
            (bool is an int subtype but is rejected as semantically wrong
            for numeric-quantity fields).
        ValueError: If value is zero or negative.

    Example:
        >>> require_positive_int(42, "size")  # doctest: +SKIP
        42
        >>> require_positive_int(0, "size")  # doctest: +SKIP
        Traceback (most recent call last):
            ...
        ValueError: size must be positive
        >>> require_positive_int(-1, "size")  # doctest: +SKIP
        Traceback (most recent call last):
            ...
        ValueError: size must be positive
        >>> require_positive_int(True, "size")  # doctest: +SKIP
        Traceback (most recent call last):
            ...
        TypeError: size must be int, got bool
    """
    if isinstance(value, bool):
        msg = f"{field_name} must be int, got bool"
        raise TypeError(msg)
    if not isinstance(value, int):
        msg = f"{field_name} must be int, got {type(value).__name__}"
        raise TypeError(msg)
    if value <= 0:
        msg = f"{field_name} must be positive"
        raise ValueError(msg)
    return value


def require_date(value: object, field_name: str) -> _date:
    """Validate that a boundary value is a stdlib date (not datetime).

    Rejects datetime instances with TypeError — datetime is a subclass of date
    but carries a time component, making it semantically distinct from a calendar
    date. Rejects all non-date types with TypeError.

    Use at constructor or API entry points that require a strict calendar date —
    fiscal year boundaries, effective dates, legislative dates. Distinguishing
    date from datetime at boundaries prevents accidental time-component leakage
    into date-only domain models.

    Args:
        value: Raw boundary value to validate. Accepts any Python object; datetime
            and non-date values always raise TypeError.
        field_name: Human-readable field label used in error messages.

    Returns:
        The validated date, identical to the input value.

    Raises:
        TypeError: If value is a datetime (subclass of date but semantically wrong
            for strict calendar-date fields).
        TypeError: If value is not a date instance.

    Example:
        >>> from datetime import date, datetime  # doctest: +SKIP
        >>> require_date(date(2024, 1, 15), "effective_date")  # doctest: +SKIP
        datetime.date(2024, 1, 15)
        >>> require_date(datetime(2024, 1, 15, 9, 0), "effective_date")  # doctest: +SKIP
        Traceback (most recent call last):
            ...
        TypeError: effective_date must be date, got datetime
        >>> require_date("2024-01-15", "effective_date")  # doctest: +SKIP
        Traceback (most recent call last):
            ...
        TypeError: effective_date must be date, got str
    """
    # Check datetime BEFORE date: datetime is a subclass of date, so
    # isinstance(datetime_obj, date) is True. Reject datetime explicitly —
    # a calendar date and a point-in-time are semantically different types.
    if isinstance(value, _datetime):
        msg = f"{field_name} must be date, got datetime"
        raise TypeError(msg)
    if not isinstance(value, _date):
        msg = f"{field_name} must be date, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def require_datetime(value: object, field_name: str) -> _datetime:
    """Validate that a boundary value is a stdlib datetime.

    Rejects plain date instances and all other non-datetime types with TypeError.
    datetime is a subclass of date, so isinstance(date_obj, datetime) is False —
    no special ordering required.

    Use at constructor or API entry points that require a point-in-time value —
    event timestamps, audit records, scheduled execution times.

    Args:
        value: Raw boundary value to validate. Accepts any Python object;
            non-datetime values (including plain date) always raise TypeError.
        field_name: Human-readable field label used in error messages.

    Returns:
        The validated datetime, identical to the input value.

    Raises:
        TypeError: If value is not a datetime instance (including plain date).

    Example:
        >>> from datetime import date, datetime  # doctest: +SKIP
        >>> require_datetime(datetime(2024, 1, 15, 9, 0), "created_at")  # doctest: +SKIP
        datetime.datetime(2024, 1, 15, 9, 0)
        >>> require_datetime(date(2024, 1, 15), "created_at")  # doctest: +SKIP
        Traceback (most recent call last):
            ...
        TypeError: created_at must be datetime, got date
        >>> require_datetime("2024-01-15T09:00:00", "created_at")  # doctest: +SKIP
        Traceback (most recent call last):
            ...
        TypeError: created_at must be datetime, got str
    """
    if not isinstance(value, _datetime):
        msg = f"{field_name} must be datetime, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def require_fluent_number(value: object, field_name: str) -> FluentNumber:
    """Validate that a boundary value is a FluentNumber.

    Rejects all non-FluentNumber values with TypeError. FluentNumber is an
    immutable formatted-number wrapper produced by make_fluent_number() that
    carries both numeric identity (for Fluent plural matching) and a locale-
    formatted string (for display). Domain models accepting monetary or
    locale-formatted amounts should gate on this validator at construction time.

    Args:
        value: Raw boundary value to validate. Accepts any Python object;
            non-FluentNumber values always raise TypeError.
        field_name: Human-readable field label used in error messages.

    Returns:
        The validated FluentNumber, identical to the input value.

    Raises:
        TypeError: If value is not a FluentNumber instance.

    Example:
        >>> from ftllexengine.core.value_types import FluentNumber  # doctest: +SKIP
        >>> from decimal import Decimal  # doctest: +SKIP
        >>> fn = FluentNumber(  # doctest: +SKIP
        ...     value=Decimal("9.99"), formatted="9.99", precision=2
        ... )
        >>> require_fluent_number(fn, "amount")  # doctest: +SKIP
        FluentNumber(value=Decimal('9.99'), formatted='9.99', precision=2)
        >>> require_fluent_number(9.99, "amount")  # doctest: +SKIP
        Traceback (most recent call last):
            ...
        TypeError: amount must be FluentNumber, got float
    """
    if not isinstance(value, FluentNumber):
        msg = f"{field_name} must be FluentNumber, got {type(value).__name__}"
        raise TypeError(msg)
    return value

