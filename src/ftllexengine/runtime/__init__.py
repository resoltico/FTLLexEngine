"""Fluent runtime package.

Exposes parser-safe runtime types unconditionally and gates locale-formatting
helpers plus bundle classes behind the Babel-enabled runtime.

Python 3.13+.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ftllexengine._optional_exports import (
    babel_optional_attr_set,
    babel_optional_attr_tuple,
    load_babel_optional_export,
    raise_missing_babel_symbol,
)
from ftllexengine.core.babel_compat import is_babel_available
from ftllexengine.diagnostics import ValidationResult

from .cache import CacheAuditLogEntry, WriteLogEntry
from .cache_config import CacheConfig
from .function_bridge import FluentNumber, FunctionRegistry, fluent_function
from .value_types import make_fluent_number

if TYPE_CHECKING:
    from .async_bundle import AsyncFluentBundle as AsyncFluentBundle
    from .bundle import FluentBundle as FluentBundle
    from .functions import (
        create_default_registry as create_default_registry,
    )
    from .functions import (
        currency_format as currency_format,
    )
    from .functions import (
        datetime_format as datetime_format,
    )
    from .functions import (
        get_shared_registry as get_shared_registry,
    )
    from .functions import (
        number_format as number_format,
    )
    from .plural_rules import select_plural_category as select_plural_category

_BABEL_AVAILABLE = is_babel_available()
_BABEL_OPTIONAL_ATTRS = babel_optional_attr_set(__name__)
_BABEL_OPTIONAL_NAMES = babel_optional_attr_tuple(__name__)


def __getattr__(name: str) -> object:
    """Raise a targeted missing-symbol error for Babel-backed runtime symbols."""
    if _BABEL_AVAILABLE and name in _BABEL_OPTIONAL_ATTRS:
        value = load_babel_optional_export(__name__, name)
        globals()[name] = value
        return value
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



__all__: list[str] = [
    "CacheAuditLogEntry",
    "CacheConfig",
    "FluentNumber",
    "FunctionRegistry",
    "ValidationResult",
    "WriteLogEntry",
    "fluent_function",
    "make_fluent_number",
]
__all__[0:0] = list(_BABEL_OPTIONAL_NAMES)

if not _BABEL_AVAILABLE:
    __all__ = [name for name in __all__ if name not in _BABEL_OPTIONAL_ATTRS]
