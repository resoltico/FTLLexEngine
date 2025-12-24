"""Deprecation utilities for FTLLexEngine.

Provides standardized deprecation warnings and decorators for marking
deprecated APIs with clear migration guidance.

Policy:
    - Deprecated features remain functional for at least 2 minor versions
    - Deprecation warnings include version where feature will be removed
    - Warnings include migration guidance pointing to replacement

Python 3.13+.
"""

import functools
import warnings
from collections.abc import Callable
from typing import ParamSpec, TypeVar

__all__ = [
    "deprecated",
    "deprecated_parameter",
    "warn_deprecated",
]

P = ParamSpec("P")
R = TypeVar("R")


def warn_deprecated(
    feature: str,
    *,
    removal_version: str,
    alternative: str | None = None,
    stacklevel: int = 2,
) -> None:
    """Issue a deprecation warning with standardized message format.

    Args:
        feature: Name of the deprecated feature
        removal_version: Version when feature will be removed (e.g., "1.0.0")
        alternative: Suggested replacement (optional)
        stacklevel: Stack level for warning (default: 2, caller's caller)

    Note:
        Uses DeprecationWarning (not FutureWarning) per Python convention.
        DeprecationWarning is filtered by default for end users but visible
        during development when running with -W default or pytest.

    Example:
        >>> warn_deprecated(
        ...     "parse_string()",
        ...     removal_version="1.0.0",
        ...     alternative="FluentParserV1.parse()",
        ... )
        # Issues: DeprecationWarning: parse_string() is deprecated and will be
        # removed in version 1.0.0. Use FluentParserV1.parse() instead.
    """
    msg = f"{feature} is deprecated and will be removed in version {removal_version}."
    if alternative:
        msg += f" Use {alternative} instead."

    warnings.warn(msg, DeprecationWarning, stacklevel=stacklevel)


def deprecated(
    *,
    removal_version: str,
    alternative: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to mark a function or method as deprecated.

    Emits DeprecationWarning on each call with standardized deprecation message.
    Preserves function signature and docstring.

    Args:
        removal_version: Version when feature will be removed (e.g., "1.0.0")
        alternative: Suggested replacement API (optional)

    Returns:
        Decorator function

    Example:
        >>> @deprecated(removal_version="1.0.0", alternative="new_function()")
        ... def old_function(x: int) -> int:
        ...     return x * 2
        >>>
        >>> old_function(5)  # Issues DeprecationWarning
        10
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            warn_deprecated(
                f"{func.__qualname__}()",
                removal_version=removal_version,
                alternative=alternative,
                stacklevel=3,
            )
            return func(*args, **kwargs)

        # Append deprecation notice to docstring
        deprecation_note = (
            f"\n\n.. deprecated::\n"
            f"    This function is deprecated and will be removed in version {removal_version}."
        )
        if alternative:
            deprecation_note += f"\n    Use :func:`{alternative}` instead."

        if wrapper.__doc__:
            wrapper.__doc__ += deprecation_note
        else:
            wrapper.__doc__ = deprecation_note.strip()

        return wrapper

    return decorator


def deprecated_parameter(
    param_name: str,
    *,
    removal_version: str,
    alternative: str | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator to mark a specific parameter as deprecated.

    Emits DeprecationWarning when the deprecated parameter is used.

    Args:
        param_name: Name of the deprecated parameter
        removal_version: Version when parameter will be removed
        alternative: Suggested replacement parameter (optional)

    Returns:
        Decorator function

    Example:
        >>> @deprecated_parameter("old_param", removal_version="1.0.0", alternative="new_param")
        ... def my_function(x: int, old_param: bool = False, new_param: bool = False) -> int:
        ...     return x * 2
        >>>
        >>> my_function(5, old_param=True)  # Issues DeprecationWarning
        10
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            if param_name in kwargs:
                feature = f"Parameter '{param_name}' of {func.__qualname__}()"
                warn_deprecated(
                    feature,
                    removal_version=removal_version,
                    alternative=f"'{alternative}'" if alternative else None,
                    stacklevel=3,
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator
