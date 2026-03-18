"""Generic boundary validation primitives for constructor and API entry points.

Provides typed, fail-fast validators for use at system entry points —
constructor arguments, configuration fields, API parameters — where silent
acceptance of blank or mis-typed values would propagate errors deep into the
processing pipeline.

Boundary validation contract (applied in order):
    1. Type check: reject the wrong Python type with TypeError.
    2. Value check: reject out-of-range or empty values with ValueError.
    3. Return the canonical form so callers need no post-validation normalization.

All functions in this module are pure, stateless, and have no external
dependencies. Safe for parser-only installations.

Python 3.14+.
"""

from __future__ import annotations

__all__ = [
    "require_non_empty_str",
    "require_positive_int",
]


def require_non_empty_str(value: object, field_name: str) -> str:
    """Validate that a boundary value is a non-blank string.

    Strips surrounding whitespace, rejects non-str types with TypeError, and
    rejects blank-after-strip values with ValueError. Returns the stripped
    string so callers receive a canonical, whitespace-free value without a
    separate strip() call.

    Use at every constructor or API entry point that requires a non-blank
    string field. This eliminates the type-check / strip / blank-check pattern
    that every downstream system would otherwise reimplement independently.

    Args:
        value: Raw boundary value to validate. Accepts any Python object;
            non-str values always raise TypeError.
        field_name: Human-readable field label used in error messages.

    Returns:
        Stripped, non-empty string.

    Raises:
        TypeError: If value is not a str instance.
        ValueError: If value is empty or contains only whitespace.

    Example:
        >>> require_non_empty_str("  hello  ", "name")
        'hello'
        >>> require_non_empty_str("", "name")
        Traceback (most recent call last):
            ...
        ValueError: name cannot be blank
        >>> require_non_empty_str(42, "name")
        Traceback (most recent call last):
            ...
        TypeError: name must be str, got int
    """
    if not isinstance(value, str):
        msg = f"{field_name} must be str, got {type(value).__name__}"
        raise TypeError(msg)
    stripped = value.strip()
    if not stripped:
        msg = f"{field_name} cannot be blank"
        raise ValueError(msg)
    return stripped


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
        >>> require_positive_int(42, "size")
        42
        >>> require_positive_int(0, "size")
        Traceback (most recent call last):
            ...
        ValueError: size must be positive
        >>> require_positive_int(-1, "size")
        Traceback (most recent call last):
            ...
        ValueError: size must be positive
        >>> require_positive_int(True, "size")
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
