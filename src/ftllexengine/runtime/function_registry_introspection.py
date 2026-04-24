"""Introspection mixin for FunctionRegistry."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .function_decorator import _FTL_REQUIRES_LOCALE_ATTR
from .function_metadata import BUILTIN_FUNCTIONS, FunctionMetadata

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from ftllexengine.core.value_types import FluentValue

    from .value_types import FunctionSignature


class _FunctionRegistryState(Protocol):
    """Structural contract implemented by FunctionRegistry."""

    _functions: dict[str, FunctionSignature]


class _FunctionRegistryIntrospectionMixin:
    """Read-only and copy helpers for FunctionRegistry."""

    def has_function(self: _FunctionRegistryState, ftl_name: str) -> bool:
        """Check if function is registered."""
        return ftl_name in self._functions

    def get_python_name(self: _FunctionRegistryState, ftl_name: str) -> str | None:
        """Get Python function name for FTL function."""
        sig = self._functions.get(ftl_name)
        return sig.python_name if sig else None

    def list_functions(self: _FunctionRegistryState) -> list[str]:
        """List all registered FTL function names."""
        return list(self._functions.keys())

    def get_function_info(
        self: _FunctionRegistryState, ftl_name: str
    ) -> FunctionSignature | None:
        """Get function metadata by FTL name."""
        return self._functions.get(ftl_name)

    def get_callable(
        self: _FunctionRegistryState, ftl_name: str
    ) -> Callable[..., FluentValue] | None:
        """Get the underlying callable for a registered function."""
        sig = self._functions.get(ftl_name)
        return sig.callable if sig else None

    def __iter__(self: _FunctionRegistryState) -> Iterator[str]:
        """Iterate over registered FTL function names."""
        return iter(self._functions)

    def __len__(self: _FunctionRegistryState) -> int:
        """Count registered functions."""
        return len(self._functions)

    def __contains__(self: _FunctionRegistryState, ftl_name: str) -> bool:
        """Check if function is registered using the ``in`` operator."""
        return ftl_name in self._functions

    def __repr__(self: _FunctionRegistryState) -> str:
        """Return string representation for debugging."""
        return f"FunctionRegistry(functions={len(self._functions)})"

    def should_inject_locale(self: _FunctionRegistryState, ftl_name: str) -> bool:
        """Check if locale should be injected for this function call."""
        if ftl_name not in self._functions:
            return False

        callable_func = self._functions[ftl_name].callable
        return getattr(callable_func, _FTL_REQUIRES_LOCALE_ATTR, False) is True

    def get_expected_positional_args(
        self: _FunctionRegistryState, ftl_name: str
    ) -> int | None:
        """Get expected positional argument count for a built-in function."""
        metadata = BUILTIN_FUNCTIONS.get(ftl_name)
        return metadata.expected_positional_args if metadata else None

    def get_builtin_metadata(
        self: _FunctionRegistryState, ftl_name: str
    ) -> FunctionMetadata | None:
        """Get metadata for a built-in function."""
        return BUILTIN_FUNCTIONS.get(ftl_name)
