"""Function call bridge between Python and FTL calling conventions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ftllexengine.core.value_types import FluentNumber, FluentValue
from ftllexengine.diagnostics import ErrorCategory, ErrorTemplate, FrozenFluentError

from .function_decorator import (
    _FTL_REQUIRES_LOCALE_ATTR as _DECORATOR_REQUIRES_LOCALE_ATTR,
)
from .function_decorator import (
    fluent_function,
)
from .function_registry_helpers import (
    build_function_signature,
    call_registered_function,
    to_camel_case,
)
from .function_registry_introspection import (
    _FunctionRegistryIntrospectionMixin,
)
from .value_types import FluentFunction, FunctionSignature

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

_FTL_REQUIRES_LOCALE_ATTR = _DECORATOR_REQUIRES_LOCALE_ATTR

__all__ = [
    "FluentFunction",
    "FluentNumber",
    "FluentValue",
    "FunctionRegistry",
    "FunctionSignature",
    "fluent_function",
]


class FunctionRegistry(_FunctionRegistryIntrospectionMixin):
    """Manages Python ↔ FTL function calling convention bridge.

    Provides automatic parameter name conversion:
        - FTL uses camelCase (minimumFractionDigits)
        - Python uses snake_case (minimum_fraction_digits)

    The registry handles the conversion transparently.

    Supports dict-like introspection:
        - list_functions(): List all registered function names
        - get_function_info(name): Get function metadata
        - __iter__: Iterate over function names
        - __len__: Count registered functions
        - __contains__: Check if function exists (supports 'in' operator)

    Freezing:
        Registries can be frozen via freeze() to prevent further modifications.
        Once frozen, register() will raise TypeError. This is used by
        get_shared_registry() to protect the shared singleton from accidental
        modification.

    Memory Optimization:
        Uses __slots__ for memory efficiency (avoids per-instance __dict__).

    Example:
        >>> registry = FunctionRegistry()  # doctest: +SKIP
        >>> registry.register(my_func, ftl_name="CUSTOM")  # doctest: +SKIP
        >>> "CUSTOM" in registry  # doctest: +SKIP
        True
        >>> len(registry)  # doctest: +SKIP
        1
        >>> for name in registry:  # doctest: +SKIP
        ...     print(name)
        CUSTOM
    """

    __slots__ = ("_frozen", "_functions")

    def __init__(self) -> None:
        """Initialize empty function registry."""
        self._functions: dict[str, FunctionSignature] = {}
        self._frozen: bool = False

    def register(
        self,
        func: Callable[..., FluentValue],
        *,
        ftl_name: str | None = None,
        param_map: dict[str, str] | None = None,
    ) -> None:
        """Register Python function for FTL use.

        Args:
            func: Python function to register
            ftl_name: Function name in FTL (default: func.__name__.upper())
            param_map: Custom parameter mappings (overrides auto-generation)

        Raises:
            TypeError: If registry is frozen (via freeze() method).
            TypeError: If func has inject_locale=True but signature is incompatible.
                      Functions marked with inject_locale=True must have at least
                      2 positional parameters to receive (value, locale_code).

        Example:
            >>> def number_format(value, *, minimum_fraction_digits=0):  # doctest: +SKIP
            ...     return str(value)
            >>> registry = FunctionRegistry()  # doctest: +SKIP
            >>> registry.register(number_format, ftl_name="NUMBER")  # doctest: +SKIP
            FTL: `{ $x NUMBER(minimumFractionDigits: 2) }`
            Python: `number_format(x, minimum_fraction_digits=2)`
        """
        if self._frozen:
            msg = (
                "Cannot modify frozen registry. "
                "Use create_default_registry() to get a mutable copy."
            )
            raise TypeError(msg)

        signature_metadata = build_function_signature(
            func,
            ftl_name=ftl_name,
            param_map=param_map,
        )
        self._functions[signature_metadata.ftl_name] = signature_metadata

    def call(
        self,
        ftl_name: str,
        positional: Sequence[FluentValue],
        named: Mapping[str, FluentValue],
    ) -> FluentValue:
        """Call Python function with FTL arguments.

        Converts FTL camelCase parameters to Python snake_case parameters.

        Args:
            ftl_name: Function name from FTL (e.g., "NUMBER")
            positional: Positional arguments
            named: Named arguments from FTL (camelCase)

        Returns:
            Function result as FluentValue (str, int, Decimal, datetime, date,
            FluentNumber, or None). float is not a valid FluentValue.
            The resolver will format non-string values to strings for final output.

        Raises:
            FrozenFluentError: If function not found (category=REFERENCE)
            FrozenFluentError: If function execution fails (category=RESOLUTION)
        """
        if ftl_name not in self._functions:
            diag = ErrorTemplate.function_not_found(ftl_name)
            raise FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag)

        return call_registered_function(
            self._functions[ftl_name],
            ftl_name=ftl_name,
            positional=positional,
            named=named,
        )

    def freeze(self) -> None:
        """Freeze registry to prevent further modifications.

        Once frozen, calling register() will raise TypeError.
        This is used by get_shared_registry() to protect the shared
        singleton from accidental modification.

        Freezing is irreversible. To get a mutable registry with the
        same functions, use copy() which creates an unfrozen copy.
        """
        self._frozen = True

    @property
    def frozen(self) -> bool:
        """Check if registry is frozen (read-only).

        Returns:
            True if registry is frozen and cannot be modified.
        """
        return self._frozen

    def copy(self) -> FunctionRegistry:
        """Create an unfrozen copy of this registry."""
        new_registry = FunctionRegistry()
        new_registry._functions = self._functions.copy()
        return new_registry

    @staticmethod
    def _to_camel_case(snake_case: str) -> str:
        """Convert Python snake_case to FTL camelCase."""
        return to_camel_case(snake_case)
