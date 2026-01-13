"""Babel compatibility layer for optional dependency handling.

Provides centralized, lazy import infrastructure for Babel to ensure consistent
error messaging and import behavior across all Babel-dependent modules.

Design Rationale:
    FTLLexEngine supports two installation modes:
    - Parser-only: `pip install ftllexengine` (no external dependencies)
    - Full runtime: `pip install ftllexengine[babel]` (includes Babel for formatting)

    This module ensures that:
    1. Parser-only installations never trigger Babel imports
    2. Runtime modules get consistent, helpful error messages when Babel is missing
    3. Babel types are available for TYPE_CHECKING without runtime import

Usage Pattern:
    # At module top-level (for type hints only):
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from babel import Locale

    # At function call site (for runtime use):
    from ftllexengine.core.babel_compat import require_babel

    def my_function(locale_code: str) -> None:
        require_babel("my_function")  # Raises ImportError if Babel missing
        from babel import Locale  # Safe to import Babel now
        ...

Python 3.13+.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from babel import Locale
    from babel.core import UnknownLocaleError as UnknownLocaleErrorType

__all__ = [
    "BabelImportError",
    "get_babel_dates",
    "get_babel_numbers",
    "get_locale_class",
    "get_unknown_locale_error",
    "is_babel_available",
    "require_babel",
]


@lru_cache(maxsize=1)
def _check_babel_available() -> bool:
    """Check if Babel is installed (computed once, cached via lru_cache)."""
    try:
        import babel  # noqa: F401, PLC0415  # pylint: disable=unused-import

        return True
    except ImportError:
        return False


class BabelImportError(ImportError):
    """Raised when Babel is required but not installed.

    Provides a consistent, helpful error message directing users to install
    the Babel dependency.
    """

    def __init__(self, feature: str) -> None:
        """Create error with feature-specific message.

        Args:
            feature: Name of the feature/function requiring Babel
        """
        message = (
            f"{feature} requires Babel for CLDR locale data. "
            "Install with: pip install ftllexengine[babel]"
        )
        super().__init__(message)
        self.feature = feature


def is_babel_available() -> bool:
    """Check if Babel is installed.

    This is the public API for checking Babel availability. Uses cached result
    to avoid repeated import attempts.

    Returns:
        True if Babel is installed and importable, False otherwise.

    Example:
        >>> if is_babel_available():
        ...     # Use Babel features
        ...     pass
        ... else:
        ...     # Fall back to non-Babel behavior
        ...     pass
    """
    return _check_babel_available()


def require_babel(feature: str) -> None:
    """Assert that Babel is available, raising BabelImportError if not.

    Use at the entry point of functions/methods that require Babel.
    This provides fail-fast behavior with a clear error message.

    Args:
        feature: Name of the feature requiring Babel (for error message)

    Raises:
        BabelImportError: If Babel is not installed

    Example:
        >>> def format_currency(value: Decimal, locale: str) -> str:
        ...     require_babel("format_currency")
        ...     # Now safe to use Babel...
    """
    if not _check_babel_available():
        raise BabelImportError(feature)


def get_locale_class() -> type[Locale]:
    """Get the Babel Locale class.

    Use when you need the class itself (for isinstance checks, etc.)
    rather than an instance.

    Returns:
        The Babel Locale class

    Raises:
        BabelImportError: If Babel is not installed
    """
    require_babel("get_locale_class")
    from babel import Locale  # noqa: PLC0415

    return Locale


def get_unknown_locale_error() -> type[UnknownLocaleErrorType]:
    """Get the Babel UnknownLocaleError exception class.

    Use for exception handling when you need to catch UnknownLocaleError.

    Returns:
        The Babel UnknownLocaleError class

    Raises:
        BabelImportError: If Babel is not installed
    """
    require_babel("get_unknown_locale_error")
    from babel.core import UnknownLocaleError  # noqa: PLC0415

    return UnknownLocaleError


def get_babel_numbers() -> Any:
    """Get the Babel numbers module.

    Returns the babel.numbers module for number formatting functions.

    Returns:
        The babel.numbers module

    Raises:
        BabelImportError: If Babel is not installed
    """
    require_babel("get_babel_numbers")
    from babel import numbers  # noqa: PLC0415

    return numbers


def get_babel_dates() -> Any:
    """Get the Babel dates module.

    Returns the babel.dates module for date/time formatting functions.

    Returns:
        The babel.dates module

    Raises:
        BabelImportError: If Babel is not installed
    """
    require_babel("get_babel_dates")
    from babel import dates  # noqa: PLC0415

    return dates
