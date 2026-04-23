"""Fluent runtime package.

Exposes parser-safe runtime types unconditionally and gates locale-formatting
helpers plus bundle classes behind the Babel-enabled runtime.

Python 3.13+.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ftllexengine._optional_exports import (
    RUNTIME_BABEL_OPTIONAL_ATTRS as _BABEL_OPTIONAL_ATTRS,
)
from ftllexengine._optional_exports import (
    load_runtime_babel_optional_exports,
    raise_missing_babel_symbol,
)
from ftllexengine.core.babel_compat import is_babel_available
from ftllexengine.diagnostics import ValidationResult

from .cache import CacheAuditLogEntry, WriteLogEntry
from .cache_config import CacheConfig
from .function_bridge import FluentNumber, FunctionRegistry, fluent_function
from .value_types import make_fluent_number

if TYPE_CHECKING:
    from .async_bundle import AsyncFluentBundle
    from .bundle import FluentBundle
    from .functions import (
        create_default_registry,
        currency_format,
        datetime_format,
        get_shared_registry,
        number_format,
    )
    from .plural_rules import select_plural_category

_BABEL_AVAILABLE = is_babel_available()

if _BABEL_AVAILABLE:
    globals().update(load_runtime_babel_optional_exports())


def __getattr__(name: str) -> object:
    """Raise a targeted missing-symbol error for Babel-backed runtime symbols."""
    return raise_missing_babel_symbol(
        module_name=__name__,
        name=name,
        optional_attrs=_BABEL_OPTIONAL_ATTRS,
        parser_only_hint=(
            "Parser-only usage keeps CacheConfig, FluentNumber, FunctionRegistry, "
            "fluent_function, make_fluent_number, ValidationResult, and cache entry types "
            "importable. Locale-formatting helpers require the full runtime extra."
        ),
    )


__all__ = [
    "AsyncFluentBundle",
    "CacheAuditLogEntry",
    "CacheConfig",
    "FluentBundle",
    "FluentNumber",
    "FunctionRegistry",
    "ValidationResult",
    "WriteLogEntry",
    "create_default_registry",
    "currency_format",
    "datetime_format",
    "fluent_function",
    "get_shared_registry",
    "make_fluent_number",
    "number_format",
    "select_plural_category",
]

if not _BABEL_AVAILABLE:
    __all__ = [name for name in __all__ if name not in _BABEL_OPTIONAL_ATTRS]
