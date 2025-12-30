"""Metadata system for built-in Fluent functions.

This module provides explicit metadata for built-in functions, replacing
magic tuples with declarative configuration.

Architecture:
    - FunctionMetadata: Dataclass with explicit properties
    - BUILTIN_FUNCTIONS: Centralized registry of built-in function metadata
    - Helper functions for type-safe queries

Design Goals:
    - Explicit over implicit (no magic tuples)
    - Self-validating (import-time checks)
    - Type-safe (mypy --strict compliant)
    - Future-proof (easy to extend)

Note:
    The `should_inject_locale()` and `get_expected_positional_args()` functions
    live in FunctionRegistry as instance methods. Use:
    - registry.should_inject_locale(ftl_name)
    - registry.get_expected_positional_args(ftl_name)

Python 3.13+. Zero external dependencies.
"""

from dataclasses import dataclass
from enum import StrEnum

__all__ = ["BUILTIN_FUNCTIONS", "FunctionCategory", "FunctionMetadata"]


class FunctionCategory(StrEnum):
    """Category classification for Fluent functions.

    StrEnum provides automatic string conversion: str(FunctionCategory.FORMATTING) == "formatting"
    """

    FORMATTING = "formatting"
    TEXT = "text"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class FunctionMetadata:
    """Metadata for a built-in Fluent function.

    Attributes:
        python_name: Python function name (snake_case)
        ftl_name: FTL function name (UPPERCASE)
        requires_locale: Whether function needs bundle locale injected
        expected_positional_args: Expected number of positional args from FTL (before locale)
        category: Function category for documentation

    Example:
        >>> NUMBER_META = FunctionMetadata(
        ...     python_name="number_format",
        ...     ftl_name="NUMBER",
        ...     requires_locale=True,
        ...     expected_positional_args=1,
        ...     category=FunctionCategory.FORMATTING,
        ... )
    """

    python_name: str
    ftl_name: str
    requires_locale: bool
    expected_positional_args: int = 1
    category: FunctionCategory = FunctionCategory.FORMATTING


# Centralized metadata registry for built-in functions
# This is the SINGLE SOURCE OF TRUTH for which functions need locale injection
BUILTIN_FUNCTIONS: dict[str, FunctionMetadata] = {
    "NUMBER": FunctionMetadata(
        python_name="number_format",
        ftl_name="NUMBER",
        requires_locale=True,
        expected_positional_args=1,
        category=FunctionCategory.FORMATTING,
    ),
    "DATETIME": FunctionMetadata(
        python_name="datetime_format",
        ftl_name="DATETIME",
        requires_locale=True,
        expected_positional_args=1,
        category=FunctionCategory.FORMATTING,
    ),
    "CURRENCY": FunctionMetadata(
        python_name="currency_format",
        ftl_name="CURRENCY",
        requires_locale=True,
        expected_positional_args=1,
        category=FunctionCategory.FORMATTING,
    ),
}


def requires_locale_injection(func_name: str) -> bool:
    """Check if function requires locale injection (type-safe).

    This is the proper way to check if a function needs locale injection,
    replacing the old magic tuple approach.

    Args:
        func_name: FTL function name (e.g., "NUMBER", "CURRENCY")

    Returns:
        True if function requires locale injection, False otherwise

    Example:
        >>> requires_locale_injection("NUMBER")
        True
        >>> requires_locale_injection("CUSTOM")
        False
    """
    metadata = BUILTIN_FUNCTIONS.get(func_name)
    return metadata.requires_locale if metadata else False


def is_builtin_function(func_name: str) -> bool:
    """Check if function is a built-in Fluent function.

    Args:
        func_name: FTL function name

    Returns:
        True if function is built-in, False otherwise

    Example:
        >>> is_builtin_function("NUMBER")
        True
        >>> is_builtin_function("CUSTOM")
        False
    """
    return func_name in BUILTIN_FUNCTIONS


def get_python_name(ftl_name: str) -> str | None:
    """Get Python function name for FTL function name.

    Args:
        ftl_name: FTL function name (e.g., "NUMBER")

    Returns:
        Python function name (e.g., "number_format") or None if not found

    Example:
        >>> get_python_name("NUMBER")
        'number_format'
        >>> get_python_name("CUSTOM")
        None
    """
    metadata = BUILTIN_FUNCTIONS.get(ftl_name)
    return metadata.python_name if metadata else None
