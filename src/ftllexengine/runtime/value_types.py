"""Core value types for the Fluent runtime.

Defines the fundamental types used throughout the resolution system:
    - FluentNumber: Formatted number preserving numeric identity
    - FluentValue: Union of all Fluent-compatible value types
    - FluentFunction: Protocol for Fluent-callable functions
    - FunctionSignature: Immutable function metadata with calling conventions

These types are imported by resolver, function_bridge, localization, and
cache modules. Extracted from function_bridge.py to separate value types
from registry machinery.

Python 3.13+. Zero external dependencies.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Protocol

__all__ = [
    "FluentFunction",
    "FluentNumber",
    "FluentValue",
    "FunctionSignature",
]

# Attribute name for marking functions that require locale injection.
# Used by FunctionRegistry.should_inject_locale() and @fluent_function decorator.
_FTL_REQUIRES_LOCALE_ATTR: str = "_ftl_requires_locale"


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
        value: Original numeric value for matching
        formatted: Locale-formatted string for display
        precision: Visible fraction digit count (CLDR v operand), computed from
            the formatted string. This is the ACTUAL count of digits after the
            decimal separator, not the minimum_fraction_digits parameter.
            None if not specified (raw variable interpolation).

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
        - FluentNumber(1.5, "1.5", precision=1) - one visible fraction digit
        - FluentNumber(1, "1.00", precision=2) - two visible fraction digits
        - FluentNumber(1, "1", precision=0) - no visible fraction digits
    """

    value: int | float | Decimal
    formatted: str
    precision: int | None = None

    def __str__(self) -> str:
        """Return formatted string for output."""
        return self.formatted

    def __contains__(self, item: str) -> bool:
        """Support membership testing on formatted string."""
        return item in self.formatted

    def __len__(self) -> int:
        """Return length of formatted string."""
        return len(self.formatted)

    def __repr__(self) -> str:
        """Return detailed representation for debugging."""
        return (
            f"FluentNumber(value={self.value!r}, "
            f"formatted={self.formatted!r})"
        )


# Type alias for Fluent-compatible function values.
# This is the CANONICAL definition - imported by resolver, localization, cache.
# Note: Includes both datetime.date and datetime.datetime for flexibility.
# FluentNumber added for NUMBER() identity preservation in select expressions.
#
# Collections Support:
#   Sequence[FluentValue] and Mapping[str, FluentValue] are supported for custom
#   functions that need to pass structured data. The cache (_make_hashable) and
#   resolver handle these types correctly. Collections are recursively typed.
type FluentValue = (
    str
    | int
    | float
    | bool
    | Decimal
    | datetime
    | date
    | FluentNumber
    | None
    | Sequence["FluentValue"]
    | Mapping[str, "FluentValue"]
)


class FluentFunction(Protocol):
    """Protocol for Fluent-compatible functions.

    Functions must accept:
    - value: The primary value to format (positional)
    - locale_code: The locale code (positional)
    - **kwargs: Named arguments (keyword-only)

    And return a FluentValue (typically str, but may return numeric types for
    functions that produce values for further processing like NUMBER).
    """

    def __call__(
        self,
        value: FluentValue,
        locale_code: str,
        /,
        **kwargs: FluentValue,
    ) -> FluentValue:
        ...  # pragma: no cover  # Protocol stub - not executable


@dataclass(frozen=True, slots=True)
class FunctionSignature:
    """Function metadata with calling convention mappings.

    Attributes:
        python_name: Function name in Python (snake_case)
        ftl_name: Function name in FTL files (UPPERCASE)
        param_mapping: Immutable mapping of FTL camelCase to Python snake_case
            params. Stored as sorted tuple of (ftl_param, python_param) pairs
            for full immutability.
        callable: The actual Python function
        param_dict: Read-only dict view of param_mapping for O(1) lookup.
            Computed once at construction, exposed as MappingProxyType to
            prevent mutation while avoiding per-call dict reconstruction.

    Immutability:
        All fields are immutable. param_mapping uses tuple instead of dict to
        ensure FunctionSignature objects can be safely shared across registries
        without risk of mutation via retained references. param_dict is a
        MappingProxyType wrapping a dict built from param_mapping at init.
    """

    python_name: str
    ftl_name: str
    param_mapping: tuple[tuple[str, str], ...]
    callable: Callable[..., FluentValue]
    param_dict: MappingProxyType[str, str] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        """Compute cached dict view from param_mapping."""
        object.__setattr__(
            self, "param_dict", MappingProxyType(dict(self.param_mapping))
        )
