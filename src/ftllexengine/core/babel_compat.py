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

from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from babel import Locale
    from babel.core import UnknownLocaleError as UnknownLocaleErrorType


# pylint: disable=redefined-builtin,unnecessary-ellipsis
# Reason: Protocol definitions mirror Babel's API which uses 'format' parameter name
# Ellipsis (...) is the standard Protocol method body per PEP 544
class BabelNumbersProtocol(Protocol):
    """Protocol for Babel numbers module interface.

    Defines the subset of babel.numbers API actually used by FTLLexEngine.
    Provides type safety without requiring full Babel type stubs.
    """

    def format_decimal(
        self,
        number: int | float | Decimal,
        format: str | None = None,
        locale: Locale | str | None = None,
    ) -> str:
        """Format decimal number with locale-specific formatting."""
        ...

    def format_currency(
        self,
        number: int | float | Decimal,
        currency: str,
        format: str | None = None,
        locale: Locale | str | None = None,
        currency_digits: bool = True,
        format_type: Literal["standard", "accounting", "name"] = "standard",
    ) -> str:
        """Format currency with locale-specific formatting."""
        ...

    def format_percent(
        self,
        number: int | float | Decimal,
        format: str | None = None,
        locale: Locale | str | None = None,
    ) -> str:
        """Format percentage with locale-specific formatting."""
        ...


class BabelDatesProtocol(Protocol):
    """Protocol for Babel dates module interface.

    Defines the subset of babel.dates API actually used by FTLLexEngine.
    Provides type safety without requiring full Babel type stubs.
    """

    def format_datetime(
        self,
        datetime_obj: datetime,
        format: str = "medium",
        tzinfo: Any | None = None,
        locale: Locale | str | None = None,
    ) -> str:
        """Format datetime with locale-specific formatting."""
        ...

    def format_date(
        self,
        date_or_datetime: date | datetime,
        format: str = "medium",
        locale: Locale | str | None = None,
    ) -> str:
        """Format date with locale-specific formatting."""
        ...

    def format_time(
        self,
        time: datetime,
        format: str = "medium",
        tzinfo: Any | None = None,
        locale: Locale | str | None = None,
    ) -> str:
        """Format time with locale-specific formatting."""
        ...
# pylint: enable=redefined-builtin,unnecessary-ellipsis


__all__ = [
    "BabelDatesProtocol",
    "BabelImportError",
    "BabelNumbersProtocol",
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


def get_babel_numbers() -> BabelNumbersProtocol:
    """Get the Babel numbers module.

    Returns the babel.numbers module for number formatting functions.

    Returns:
        The babel.numbers module (typed via BabelNumbersProtocol)

    Raises:
        BabelImportError: If Babel is not installed
    """
    require_babel("get_babel_numbers")
    from babel import numbers  # noqa: PLC0415

    return numbers


def get_babel_dates() -> BabelDatesProtocol:
    """Get the Babel dates module.

    Returns the babel.dates module for date/time formatting functions.

    Returns:
        The babel.dates module (typed via BabelDatesProtocol)

    Raises:
        BabelImportError: If Babel is not installed
    """
    require_babel("get_babel_dates")
    from babel import dates  # noqa: PLC0415

    return dates
