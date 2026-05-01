"""Tests for runtime.function_bridge: FunctionRegistry, FunctionSignature, edge cases."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.function_bridge import (
    _FTL_REQUIRES_LOCALE_ATTR,
    FluentValue,
    FunctionRegistry,
    FunctionSignature,
    fluent_function,
)

# ============================================================================
# HELPER FUNCTIONS FOR TESTING
# ============================================================================


def sample_function(value: int, *, minimum_fraction_digits: int = 0) -> str:
    """Sample function with snake_case parameters."""
    return f"{value:.{minimum_fraction_digits}f}"


def simple_function(text: str) -> str:
    """Simple function with single parameter."""
    return text.upper()


def positional_only_function(value: int, /) -> str:
    """Function with positional-only parameter."""
    return str(value * 2)


def mixed_params_function(
    value: int, /, *, use_grouping: bool = False, date_style: str = "short"
) -> str:
    """Function with mixed parameter types."""
    result = str(value)
    if use_grouping:
        result = f"{value:,}"
    return f"{result} ({date_style})"

__all__ = [
    "_FTL_REQUIRES_LOCALE_ATTR",
    "Any",
    "Decimal",
    "ErrorCategory",
    "FluentValue",
    "FrozenFluentError",
    "FunctionRegistry",
    "FunctionSignature",
    "fluent_function",
    "mixed_params_function",
    "positional_only_function",
    "pytest",
    "sample_function",
    "simple_function",
]
