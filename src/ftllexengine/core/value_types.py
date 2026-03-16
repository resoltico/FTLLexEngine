"""Core value types shared across syntax, parsing, and runtime layers.

Defines the fundamental types used throughout the entire system:
    - FluentNumber: Formatted number preserving numeric identity and precision
    - make_fluent_number: Public helper for manual FluentNumber construction
    - FluentValue: Union of all Fluent-compatible value types

Placing these types in ``core`` rather than ``runtime`` reflects the
dependency graph: both the ``parsing`` layer (``parse_fluent_number``)
and the ``runtime`` layer (resolver, NUMBER/CURRENCY functions, cache)
need them. Defining them in ``runtime`` would create an upward import
from ``parsing`` into ``runtime``, violating the layer hierarchy:

    core <- parsing <- runtime

All helpers in this module are pure Python with zero external dependencies.
The visible-precision inference logic is encapsulated here so that
``parse_fluent_number``, ``number_format``, and ``currency_format`` all
derive precision by the same algorithm.

Python 3.13+. Zero external dependencies.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

# Financial precision contract: float is explicitly excluded from FluentValue.
# float is IEEE 754 and cannot represent most decimal fractions exactly.
# For financial applications, callers must use int or Decimal.
# Decimal(str(float_val)) is the correct conversion pattern when interoperating
# with existing float-typed values at system boundaries.

__all__ = [
    "FluentNumber",
    "FluentValue",
    "make_fluent_number",
]

_DECIMAL_SEPARATORS: tuple[str, ...] = (".", ",", "\u066b")
_GROUPING_SEPARATORS: frozenset[str] = frozenset({
    " ",
    "'",
    ",",
    ".",
    "_",
    "\u00a0",
    "\u066c",
    "\u202f",
})
_NUMERIC_SEGMENT_CHARS: frozenset[str] = frozenset({
    " ",
    "'",
    "(",
    ")",
    "+",
    ",",
    "-",
    ".",
    "_",
    "\u00a0",
    "\u066b",
    "\u066c",
    "\u202f",
})


@dataclass(frozen=True, slots=True)
class FluentNumber:
    """Wrapper for formatted numbers preserving numeric identity and precision.

    When NUMBER() formats a value, the result needs to:
    1. Display the formatted string in output (e.g., "1,234.56")
    2. Still match plural categories in select expressions (e.g., [one], [other])
    3. Preserve precision metadata for CLDR plural rules (v operand)

    FluentNumber carries all three pieces of information, allowing the resolver to:
    - Use __str__ for final output (formatted string)
    - Use .value and .precision for plural category matching

    Attributes:
        value: Original numeric value for matching. Always int or Decimal — never
            float and never bool. IEEE 754 floating-point cannot represent most
            decimal fractions exactly. Callers with float-typed values must convert
            at the system boundary using Decimal(str(float_val)) before calling
            number_format(). bool is a subtype of int but carries no numeric
            localization semantics and is rejected to prevent silent misuse
            (e.g., NUMBER(True) yielding "true" instead of a numeric format).
        formatted: Locale-formatted string for display
        precision: Visible fraction digit count (CLDR v operand), computed from
            the formatted string. This is the ACTUAL count of digits after the
            decimal separator, not the minimum_fraction_digits parameter.
            None if not specified (raw variable interpolation).
            Must be >= 0 when set; negative precision has no CLDR meaning.

    Example:
        >>> fn = FluentNumber(value=1, formatted="1.00", precision=2)
        >>> str(fn)  # Used in output
        '1.00'
        >>> fn.value  # Used for plural matching
        1
        >>> fn.precision  # CLDR v operand: 2 visible fraction digits
        2

    Precision Semantics:
        The precision field reflects what is VISIBLE in the formatted output:
        - FluentNumber(Decimal("1.5"), "1.5", precision=1) - one visible fraction digit
        - FluentNumber(1, "1.00", precision=2) - two visible fraction digits
        - FluentNumber(1, "1", precision=0) - no visible fraction digits
    """

    value: int | Decimal
    formatted: str
    precision: int | None = None

    def __post_init__(self) -> None:
        """Enforce invariants on FluentNumber construction.

        Raises:
            TypeError: If value is bool (bool is int subtype but has no numeric
                localization semantics; passing True/False to NUMBER() is a misuse).
            TypeError: If value is not int or Decimal (defense-in-depth; the type
                annotation already constrains this but runtime callers can bypass it).
            ValueError: If precision is set and negative (CLDR v operand is a
                non-negative count of visible fraction digits; negative values have
                no meaning and indicate a construction error).
        """
        if isinstance(self.value, bool):
            msg = (
                "FluentNumber.value must be int or Decimal, not bool. "
                "bool carries no numeric localization semantics. "
                "Use int(your_bool) explicitly if you need 0 or 1."
            )
            raise TypeError(msg)
        if not isinstance(self.value, (int, Decimal)):
            msg = (  # type: ignore[unreachable]
                f"FluentNumber.value must be int or Decimal, "
                f"got {type(self.value).__name__}"
            )
            raise TypeError(msg)
        if self.precision is not None and self.precision < 0:
            msg = (
                f"FluentNumber.precision must be >= 0, "
                f"got {self.precision}. CLDR v operand counts visible "
                f"fraction digits and is always non-negative."
            )
            raise ValueError(msg)

    @property
    def decimal_value(self) -> Decimal:
        """Exact Decimal representation of the underlying numeric value.

        Coerces int to Decimal for uniform downstream handling. Decimal
        values are returned as-is without copying (they are immutable).
        float is structurally excluded from FluentNumber.value, so this
        property always yields an exact decimal number.

        Financial applications should use this property instead of
        accessing .value directly, as it guarantees a uniform Decimal
        type regardless of whether value is int or Decimal.

        Returns:
            Exact Decimal equivalent of value. For int inputs, the
            conversion is exact (all integers are representable as
            Decimal). For Decimal inputs, the original object is
            returned unchanged.

        Example:
            >>> fn = FluentNumber(value=42, formatted="42", precision=0)
            >>> fn.decimal_value
            Decimal('42')
            >>> fn2 = FluentNumber(value=Decimal("1234.50"), formatted="1,234.50", precision=2)
            >>> fn2.decimal_value
            Decimal('1234.50')
        """
        if isinstance(self.value, Decimal):
            return self.value
        return Decimal(self.value)

    def __str__(self) -> str:
        """Return formatted string for output."""
        return self.formatted

    def __repr__(self) -> str:
        """Return detailed representation for debugging."""
        return (
            f"FluentNumber(value={self.value!r}, "
            f"formatted={self.formatted!r}, "
            f"precision={self.precision!r})"
        )


# Type alias for Fluent-compatible function values.
# This is the CANONICAL definition — imported by resolver, localization, cache,
# parsing, and any other layer that deals with Fluent values.
# Note: Includes both datetime.date and datetime.datetime for flexibility.
# FluentNumber added for NUMBER() identity preservation in select expressions.
#
# float is deliberately absent. IEEE 754 floating-point cannot represent most
# decimal fractions exactly (e.g., 0.1 + 0.2 != 0.3). Financial applications
# must use int (for whole amounts) or Decimal (for fractional amounts).
# At system boundaries, convert with Decimal(str(float_val)).
#
# bool is absent from the explicit union. bool is a subtype of int, so type
# checkers already accept bool where int is expected. The explicit omission
# signals intent: bool carries no numeric localization semantics. NUMBER() and
# CURRENCY() reject bool at runtime (FluentNumber.__post_init__ raises TypeError).
# For string interpolation of True/False, callers must convert explicitly:
#   str(flag)  — renders as "True" / "False"
#   int(flag)  — renders as 0 / 1
#
# Collections Support:
#   Sequence[FluentValue] and Mapping[str, FluentValue] are supported for custom
#   functions that need to pass structured data. The cache (_make_hashable) and
#   resolver handle these types correctly. Collections are recursively typed.
type FluentValue = (
    str
    | int
    | Decimal
    | datetime
    | date
    | FluentNumber
    | None
    | Sequence["FluentValue"]
    | Mapping[str, "FluentValue"]
)


# ---------------------------------------------------------------------------
# Visible-precision helpers (private — used by make_fluent_number, number_format,
# currency_format; not part of the public API).
# ---------------------------------------------------------------------------

def _compute_visible_precision(
    formatted: str,
    decimal_symbol: str,
    *,
    max_fraction_digits: int | None = None,
) -> int:
    """Count visible fraction digits in a formatted number string."""
    if decimal_symbol not in formatted:
        return 0

    _, fraction_part = formatted.rsplit(decimal_symbol, 1)

    count = 0
    for char in fraction_part:
        if char.isdigit():
            count += 1
        else:
            break

    if max_fraction_digits is not None and count > max_fraction_digits:
        count = max_fraction_digits

    return count


def _visible_precision_from_value(value: int | Decimal) -> int:
    """Derive visible precision from the numeric value itself."""
    if isinstance(value, int):
        return 0

    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < 0:
        return -exponent
    return 0


def _iter_numeric_segments(formatted: str) -> tuple[str, ...]:
    """Extract digit-containing numeric segments from a formatted string."""
    segments: list[str] = []
    current: list[str] = []
    saw_digit = False

    for char in formatted:
        if char.isdigit() or char in _NUMERIC_SEGMENT_CHARS:
            current.append(char)
            saw_digit = saw_digit or char.isdigit()
            continue

        if saw_digit:
            segments.append("".join(current).strip())
        current = []
        saw_digit = False

    if saw_digit:
        segments.append("".join(current).strip())

    return tuple(segment for segment in segments if any(char.isdigit() for char in segment))


def _normalize_digit(char: str) -> str:
    """Convert a Unicode digit to its ASCII decimal representation."""
    return str(unicodedata.decimal(char))


def _unwrap_parenthesized_negative(segment: str) -> tuple[str, bool]:
    """Strip balanced wrapping parentheses used for negative values."""
    stripped = segment.strip()
    negative = stripped.startswith("(") and stripped.endswith(")")
    if negative:
        return (stripped[1:-1].strip(), True)
    return (stripped, False)


def _normalize_numeric_text(
    segment: str,
    *,
    decimal_symbol: str | None,
) -> str | None:
    """Normalize a numeric segment to Decimal-compatible ASCII text."""
    normalized: list[str] = []
    saw_sign = False

    for char in segment:
        if char.isdigit():
            normalized.append(_normalize_digit(char))
            continue

        if char in "+-":
            if normalized or saw_sign:
                continue
            normalized.append(char)
            saw_sign = True
            continue

        if decimal_symbol is not None and char == decimal_symbol:
            normalized.append(".")
            continue

        if char in _GROUPING_SEPARATORS or char in _DECIMAL_SEPARATORS:
            continue

        if char in {"(", ")"}:
            continue

        return None

    return "".join(normalized)


def _parse_numeric_segment(
    segment: str,
    *,
    decimal_symbol: str | None,
) -> Decimal | None:
    """Parse a numeric segment using the provided decimal separator."""
    stripped, negative = _unwrap_parenthesized_negative(segment)
    number_text = _normalize_numeric_text(stripped, decimal_symbol=decimal_symbol)
    if number_text is None:
        return None

    if number_text in {"", "+", "-", ".", "+.", "-."}:
        return None

    try:
        parsed = Decimal(number_text)
    except InvalidOperation:
        return None

    if negative and not number_text.startswith("-"):
        parsed = -parsed
    return parsed


def _infer_visible_precision(value: int | Decimal, formatted: str) -> int:
    """Infer visible precision by reconciling a formatted string with its value."""
    target = Decimal(value)

    for segment in _iter_numeric_segments(formatted):
        separators: list[str] = []
        for char in segment:
            if char in _DECIMAL_SEPARATORS and char not in separators:
                separators.append(char)

        for decimal_symbol in separators:
            parsed = _parse_numeric_segment(segment, decimal_symbol=decimal_symbol)
            if parsed == target:
                return _compute_visible_precision(segment, decimal_symbol)

        parsed_without_decimal = _parse_numeric_segment(segment, decimal_symbol=None)
        if parsed_without_decimal == target:
            return 0

    return _visible_precision_from_value(value)


def _make_fluent_number(
    value: int | Decimal,
    *,
    formatted: str,
    decimal_symbol: str | None = None,
    max_fraction_digits: int | None = None,
) -> FluentNumber:
    """Construct a FluentNumber using shared visible-precision rules."""
    precision = (
        _compute_visible_precision(
            formatted,
            decimal_symbol,
            max_fraction_digits=max_fraction_digits,
        )
        if decimal_symbol is not None
        else _infer_visible_precision(value, formatted)
    )
    return FluentNumber(value=value, formatted=formatted, precision=precision)


def make_fluent_number(
    value: int | Decimal,
    *,
    formatted: str | None = None,
) -> FluentNumber:
    """Construct a FluentNumber from a domain numeric value.

    Uses the provided formatted string when present, inferring the visible
    precision that Fluent plural rules need for selector matching. When no
    formatted string is supplied, the helper preserves the numeric string form
    of the source value and derives precision from that representation.

    Args:
        value: Numeric value. Must be int or Decimal (not float, not bool).
        formatted: Optional pre-rendered locale string. When supplied, visible
            precision is inferred from the rendered form. When omitted, the
            canonical str() representation of value is used.

    Returns:
        FluentNumber carrying value, formatted string, and inferred precision.

    Raises:
        TypeError: If value is bool or not int/Decimal.
        ValueError: If the inferred precision is negative (indicates a bug in
            the formatted string, not a valid locale output).

    Example:
        >>> make_fluent_number(Decimal("1234.50"), formatted="1 234,50")
        FluentNumber(value=Decimal('1234.50'), formatted='1 234,50', precision=2)
        >>> make_fluent_number(42)
        FluentNumber(value=42, formatted='42', precision=0)
    """
    rendered = str(value) if formatted is None else formatted
    return _make_fluent_number(value, formatted=rendered)
