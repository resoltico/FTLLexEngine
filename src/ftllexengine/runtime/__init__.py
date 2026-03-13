"""Fluent runtime package.

Provides message resolution, built-in functions, manual FluentNumber helpers,
custom function extension points, cache audit entry aliases, the public RWLock
concurrency primitive, and the FluentBundle API.
Depends on syntax package for parsing.

Python 3.13+.
"""

from ftllexengine.diagnostics import ValidationResult

from .bundle import FluentBundle
from .cache import CacheAuditLogEntry, WriteLogEntry
from .cache_config import CacheConfig
from .function_bridge import FluentNumber, FunctionRegistry, fluent_function
from .functions import (
    create_default_registry,
    currency_format,
    datetime_format,
    get_shared_registry,
    number_format,
)
from .plural_rules import select_plural_category
from .resolution_context import ResolutionContext
from .resolver import FluentResolver
from .rwlock import RWLock
from .value_types import make_fluent_number

__all__ = [
    "CacheAuditLogEntry",
    "CacheConfig",
    "FluentBundle",
    "FluentNumber",
    "FluentResolver",
    "FunctionRegistry",
    "RWLock",
    "ResolutionContext",
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
