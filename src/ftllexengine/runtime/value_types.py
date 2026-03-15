"""Runtime function protocol and signature types.

Defines the calling-convention types used by the runtime function registry:
    - FluentFunction: Protocol for Fluent-callable Python functions
    - FunctionSignature: Immutable function metadata with camelCase param mapping

FluentNumber, FluentValue, and make_fluent_number have been moved to
``ftllexengine.core.value_types`` so that the ``parsing`` layer can use them
without importing from ``runtime``. They remain importable from this module
for any internal code that references them via ``runtime.value_types``; the
canonical path is now ``ftllexengine.core.value_types``.

Python 3.13+. Zero external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol

from ftllexengine.core.value_types import (
    FluentNumber,
    FluentValue,
    make_fluent_number,
)

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "FluentFunction",
    "FluentNumber",
    "FluentValue",
    "FunctionSignature",
    "make_fluent_number",
]


class FluentFunction(Protocol):
    """Protocol for Fluent-callable functions.

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
