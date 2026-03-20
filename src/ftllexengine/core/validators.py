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
from decimal import Decimal

__all__ = [
    "coerce_tuple",
    "normalize_optional_decimal_range",
    "normalize_optional_str",
    "require_decimal_range",
    "require_int",
    "require_int_in_range",
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


def normalize_optional_str(value: object, field_name: str) -> str | None:
    """Normalize an optional string field: None passthrough over require_non_empty_str.

    If value is None, returns None. Otherwise delegates to require_non_empty_str
    with identical TypeError and ValueError behavior: strips surrounding whitespace,
    rejects non-str types, and rejects blank-after-strip values.

    Use at constructor or API entry points that accept an optional non-blank string
    field. Eliminates the None-check / require_non_empty_str pattern that every
    optional text field would otherwise reimplement independently.

    Args:
        value: Raw boundary value to validate. None returns None; non-str values
            (other than None) raise TypeError; blank or whitespace-only str raises
            ValueError.
        field_name: Human-readable field label used in error messages.

    Returns:
        None if value is None, otherwise the stripped, non-empty string.

    Raises:
        TypeError: If value is not None and not a str instance.
        ValueError: If value is a str that is empty or contains only whitespace.

    Example:
        >>> normalize_optional_str(None, "description")
        >>> normalize_optional_str("  hello  ", "description")
        'hello'
        >>> normalize_optional_str("", "description")
        Traceback (most recent call last):
            ...
        ValueError: description cannot be blank
        >>> normalize_optional_str(42, "description")
        Traceback (most recent call last):
            ...
        TypeError: description must be str, got int
    """
    if value is None:
        return None
    return require_non_empty_str(value, field_name)


def require_decimal_range(
    value: object,
    lo: Decimal,
    hi: Decimal,
    field_name: str,
) -> Decimal:
    """Validate that a boundary value is a finite Decimal within an inclusive range.

    Rejects bool with TypeError (consistent with numeric validators — bool is not a
    Decimal subtype but the explicit check produces a uniform error message), rejects
    non-Decimal types with TypeError, rejects non-finite values (Infinity, NaN) with
    ValueError, and rejects values outside [lo, hi] with ValueError.

    Use at constructor or API entry points that require a Decimal constrained to a
    numeric range — tax rates, ratios, proportions, financial factors. Eliminates the
    None-guard / bool-guard / isinstance / finiteness / range-check chain that every
    Decimal-constrained field would otherwise reimplement.

    Args:
        value: Raw boundary value to validate. Accepts any Python object; non-Decimal
            and bool values always raise TypeError.
        lo: Inclusive lower bound (must be a finite Decimal; caller's responsibility).
        hi: Inclusive upper bound (must be a finite Decimal; lo <= hi precondition).
        field_name: Human-readable field label used in error messages.

    Returns:
        The validated Decimal, identical to the input value.

    Raises:
        TypeError: If value is bool or not a Decimal instance.
        ValueError: If value is not finite (Infinity, NaN).
        ValueError: If value is outside the inclusive range [lo, hi].

    Example:
        >>> from decimal import Decimal
        >>> require_decimal_range(Decimal("0.5"), Decimal("0"), Decimal("1"), "rate")
        Decimal('0.5')
        >>> require_decimal_range(Decimal("1.5"), Decimal("0"), Decimal("1"), "rate")
        Traceback (most recent call last):
            ...
        ValueError: rate must be in range [0, 1]
        >>> require_decimal_range(42, Decimal("0"), Decimal("1"), "rate")
        Traceback (most recent call last):
            ...
        TypeError: rate must be Decimal, got int
    """
    if isinstance(value, bool):
        msg = f"{field_name} must be Decimal, got bool"
        raise TypeError(msg)
    if not isinstance(value, Decimal):
        msg = f"{field_name} must be Decimal, got {type(value).__name__}"
        raise TypeError(msg)
    if not value.is_finite():
        msg = f"{field_name} must be finite"
        raise ValueError(msg)
    if not (lo <= value <= hi):
        msg = f"{field_name} must be in range [{lo}, {hi}]"
        raise ValueError(msg)
    return value


def normalize_optional_decimal_range(
    value: object,
    lo: Decimal,
    hi: Decimal,
    field_name: str,
) -> Decimal | None:
    """Normalize an optional Decimal range field: None passthrough over require_decimal_range.

    If value is None, returns None. Otherwise delegates to require_decimal_range
    with identical TypeError and ValueError behavior: rejects bool, non-Decimal types,
    non-finite values, and out-of-range values.

    Use at constructor or API entry points that accept an optional Decimal constrained
    to a numeric range — optional tax rates, optional ratios, optional financial factors.

    Args:
        value: Raw boundary value to validate. None returns None; bool and non-Decimal
            values (other than None) raise TypeError; non-finite or out-of-range Decimals
            raise ValueError.
        lo: Inclusive lower bound (must be a finite Decimal; caller's responsibility).
        hi: Inclusive upper bound (must be a finite Decimal; lo <= hi precondition).
        field_name: Human-readable field label used in error messages.

    Returns:
        None if value is None, otherwise the validated Decimal unchanged.

    Raises:
        TypeError: If value is not None and is bool or not a Decimal instance.
        ValueError: If value is a Decimal that is not finite or is outside [lo, hi].

    Example:
        >>> from decimal import Decimal
        >>> normalize_optional_decimal_range(None, Decimal("0"), Decimal("1"), "rate")
        >>> normalize_optional_decimal_range(
        ...     Decimal("0.25"), Decimal("0"), Decimal("1"), "rate"
        ... )
        Decimal('0.25')
        >>> normalize_optional_decimal_range(
        ...     Decimal("2"), Decimal("0"), Decimal("1"), "rate"
        ... )
        Traceback (most recent call last):
            ...
        ValueError: rate must be in range [0, 1]
    """
    if value is None:
        return None
    return require_decimal_range(value, lo, hi, field_name)


def require_int_in_range(
    value: object,
    lo: int,
    hi: int,
    field_name: str,
) -> int:
    """Validate that a boundary value is an integer within an inclusive range [lo, hi].

    Rejects bool with TypeError (bool is an int subtype but semantically wrong for
    numeric-quantity fields), rejects non-int types with TypeError, and rejects values
    outside [lo, hi] with ValueError.

    Use at constructor or API entry points that require an integer constrained to a
    specific range — page sizes, pool capacities, fiscal-period-adjacent integers.
    Eliminates the bool-guard / isinstance / range-check chain that every bounded
    integer field would otherwise reimplement.

    Args:
        value: Raw boundary value to validate. Accepts any Python object; non-int
            and bool values always raise TypeError.
        lo: Inclusive lower bound (int; lo <= hi precondition).
        hi: Inclusive upper bound (int; lo <= hi precondition).
        field_name: Human-readable field label used in error messages.

    Returns:
        The validated integer, identical to the input value.

    Raises:
        TypeError: If value is bool or not an int instance.
        ValueError: If value is outside the inclusive range [lo, hi].

    Example:
        >>> require_int_in_range(5, 1, 10, "page_size")
        5
        >>> require_int_in_range(0, 1, 10, "page_size")
        Traceback (most recent call last):
            ...
        ValueError: page_size must be in range [1, 10]
        >>> require_int_in_range(True, 1, 10, "page_size")
        Traceback (most recent call last):
            ...
        TypeError: page_size must be int, got bool
    """
    if isinstance(value, bool):
        msg = f"{field_name} must be int, got bool"
        raise TypeError(msg)
    if not isinstance(value, int):
        msg = f"{field_name} must be int, got {type(value).__name__}"
        raise TypeError(msg)
    if not (lo <= value <= hi):
        msg = f"{field_name} must be in range [{lo}, {hi}]"
        raise ValueError(msg)
    return value
