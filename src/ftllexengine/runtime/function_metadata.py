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

Python 3.13+. Zero external dependencies.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ftllexengine.runtime.function_bridge import FunctionRegistry


class FunctionCategory(StrEnum):
    """Category classification for Fluent functions.

    StrEnum provides automatic string conversion: str(FunctionCategory.FORMATTING) == "formatting"
    """

    FORMATTING = "formatting"
    TEXT = "text"
    CUSTOM = "custom"


@dataclass(frozen=True)
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


def get_expected_positional_args(ftl_name: str) -> int | None:
    """Get expected positional argument count for a built-in function.

    Used for arity validation before locale injection to prevent
    TypeError from incorrect argument positioning.

    Args:
        ftl_name: FTL function name (e.g., "NUMBER", "CURRENCY")

    Returns:
        Expected positional arg count (from FTL, before locale injection),
        or None if not a built-in function.

    Example:
        >>> get_expected_positional_args("NUMBER")
        1
        >>> get_expected_positional_args("CUSTOM")
        None
    """
    metadata = BUILTIN_FUNCTIONS.get(ftl_name)
    return metadata.expected_positional_args if metadata else None


def should_inject_locale(func_name: str, function_registry: "FunctionRegistry") -> bool:
    """Check if locale should be injected for this function call.

    This is the CORRECT way to check locale injection, handling both
    built-in functions and custom functions with the same name.

    Uses function attributes (set at registration time) to determine locale
    requirements, avoiding circular imports between this module and functions.py.

    Args:
        func_name: FTL function name (e.g., "NUMBER", "CURRENCY")
        function_registry: FunctionRegistry instance to check

    Returns:
        True if locale should be injected, False otherwise

    Logic:
        1. Check if function name is a built-in that needs locale
        2. Get the callable from registry and check its _ftl_requires_locale attribute
        3. Only inject if the callable has the locale requirement marker

    Example:
        >>> # Built-in NUMBER function
        >>> should_inject_locale("NUMBER", bundle._function_registry)
        True

        >>> # Custom function with locale requirement
        >>> def my_format(value, *, _locale=None): ...
        >>> my_format._ftl_requires_locale = True
        >>> bundle.add_function("MY_FORMAT", my_format)
        >>> should_inject_locale("MY_FORMAT", bundle._function_registry)
        True

        >>> # Custom function without locale requirement (default)
        >>> bundle.add_function("SIMPLE", lambda x: str(x))
        >>> should_inject_locale("SIMPLE", bundle._function_registry)
        False
    """
    # Check if the function exists in the registry
    if not function_registry.has_function(func_name):
        return False

    # Get the callable from the registry
    bundle_callable = function_registry.get_callable(func_name)
    if bundle_callable is None:
        return False

    # Check if the callable has the locale requirement marker
    # Both built-in functions (marked at module load) and custom functions
    # (explicitly marked by user) can have _ftl_requires_locale = True
    # This allows custom functions to receive locale context when needed.
    return getattr(bundle_callable, "_ftl_requires_locale", False) is True
