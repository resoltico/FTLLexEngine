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

from collections.abc import Sequence

__all__ = [
    "coerce_tuple",
    "require_int",
    "require_non_empty_str",
    "require_non_negative_int",
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


def require_int(value: object, field_name: str) -> int:
    """Validate that a boundary value is an integer, with no range constraint.

    Rejects non-int types (including bool, which is an int subtype but
    semantically distinct) with TypeError. Returns the validated int unchanged
    with no positivity or non-negativity check.

    Use at deserialization boundaries or input boundaries where the domain
    model applies range validation separately — fields like fiscal_year,
    quarter, and month where any integer type is acceptable but float, str,
    or bool is not. This is more semantically precise than require_positive_int
    when positivity is not a property of the boundary, only the type is.

    Args:
        value: Raw boundary value to validate. Accepts any Python object;
            non-int values (including bool) always raise TypeError.
        field_name: Human-readable field label used in error messages.

    Returns:
        The validated integer, identical to the input value. No range check.

    Raises:
        TypeError: If value is not an int instance, or if value is bool
            (bool is an int subtype but is rejected as semantically wrong
            for numeric fields).

    Example:
        >>> require_int(0, "year")
        0
        >>> require_int(-5, "offset")
        -5
        >>> require_int(True, "year")
        Traceback (most recent call last):
            ...
        TypeError: year must be int, got bool
        >>> require_int("2024", "year")
        Traceback (most recent call last):
            ...
        TypeError: year must be int, got str
    """
    if isinstance(value, bool):
        msg = f"{field_name} must be int, got bool"
        raise TypeError(msg)
    if not isinstance(value, int):
        msg = f"{field_name} must be int, got {type(value).__name__}"
        raise TypeError(msg)
    return value


def require_non_negative_int(value: object, field_name: str) -> int:
    """Validate that a boundary value is a non-negative integer (>= 0).

    Rejects non-int types (including bool, which is an int subtype but
    semantically distinct) with TypeError, and rejects negative values with
    ValueError. Zero is valid. Returns the validated int unchanged.

    Use at every constructor or API entry point that requires a zero-or-positive
    integer field — zero-based indices, counts that may legitimately be zero,
    or offset fields where negative values indicate an error but zero is valid.
    Distinct from require_positive_int (which rejects zero) and require_int
    (which applies no range constraint at all).

    Args:
        value: Raw boundary value to validate. Accepts any Python object;
            non-int values (including bool) always raise TypeError.
        field_name: Human-readable field label used in error messages.

    Returns:
        The validated non-negative integer, identical to the input value.

    Raises:
        TypeError: If value is not an int instance, or if value is bool
            (bool is an int subtype but is rejected as semantically wrong
            for numeric-quantity fields).
        ValueError: If value is negative.

    Example:
        >>> require_non_negative_int(0, "index")
        0
        >>> require_non_negative_int(5, "index")
        5
        >>> require_non_negative_int(-1, "index")
        Traceback (most recent call last):
            ...
        ValueError: index must be non-negative
        >>> require_non_negative_int(True, "index")
        Traceback (most recent call last):
            ...
        TypeError: index must be int, got bool
    """
    if isinstance(value, bool):
        msg = f"{field_name} must be int, got bool"
        raise TypeError(msg)
    if not isinstance(value, int):
        msg = f"{field_name} must be int, got {type(value).__name__}"
        raise TypeError(msg)
    if value < 0:
        msg = f"{field_name} must be non-negative"
        raise ValueError(msg)
    return value


def coerce_tuple[T](value: object, field_name: str) -> tuple[T, ...]:
    """Coerce a non-str Sequence to an immutable tuple.

    Accepts any non-str Sequence (list, tuple, range, etc.) and returns
    tuple(value). Rejects str (which is a Sequence but semantically a scalar
    at this boundary) and non-Sequence values with TypeError.

    Use in frozen dataclass __post_init__ methods that accept caller-provided
    sequences for immutable tuple fields. This eliminates the repeated
    isinstance / tuple() coercion pattern that every frozen dataclass author
    would otherwise reimplement independently.

    The element type T is caller-asserted: the function does not verify that
    each element is an instance of T at runtime. This is an unchecked coercion
    analogous to cast() — the caller is responsible for runtime element
    correctness.

    Args:
        value: Raw boundary value to coerce. Accepts any non-str Sequence;
            str and non-Sequence values always raise TypeError.
        field_name: Human-readable field label used in error messages.

    Returns:
        An immutable tuple containing the elements of value.

    Raises:
        TypeError: If value is str (str is a Sequence but semantically wrong
            for sequence-coercion fields).
        TypeError: If value is not a Sequence (e.g., int, None, a generator).

    Example:
        >>> coerce_tuple([1, 2, 3], "items")
        (1, 2, 3)
        >>> coerce_tuple((4, 5), "ids")
        (4, 5)
        >>> coerce_tuple("hello", "items")
        Traceback (most recent call last):
            ...
        TypeError: items must be a non-str Sequence, got str
        >>> coerce_tuple(42, "items")
        Traceback (most recent call last):
            ...
        TypeError: items must be a Sequence, got int
    """
    if isinstance(value, str):
        msg = f"{field_name} must be a non-str Sequence, got str"
        raise TypeError(msg)
    if not isinstance(value, Sequence):
        msg = f"{field_name} must be a Sequence, got {type(value).__name__}"
        raise TypeError(msg)
    return tuple(value)
