"""Fluent runtime package.

Provides message resolution, built-in functions, and the FluentBundle API.
Depends on syntax package for parsing.

Python 3.13+.
"""

from ftllexengine.diagnostics import ValidationResult

from .bundle import FluentBundle
from .function_bridge import FunctionRegistry
from .functions import (
    create_default_registry,
    currency_format,
    datetime_format,
    get_shared_registry,
    number_format,
)
from .plural_rules import select_plural_category
from .resolver import FluentResolver, ResolutionContext

__all__ = [
    "FluentBundle",
    "FluentResolver",
    "FunctionRegistry",
    "ResolutionContext",
    "ValidationResult",
    "create_default_registry",
    "currency_format",
    "datetime_format",
    "get_shared_registry",
    "number_format",
    "select_plural_category",
]
