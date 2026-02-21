"""Babel compatibility layer — the sole gateway for all Babel imports.

All Babel imports in FTLLexEngine MUST go through this module. No other
module may import directly from ``babel`` or its subpackages. This enforces
a single point of control for optional-dependency management.

Design Rationale:
    FTLLexEngine supports two installation modes:
    - Parser-only: ``pip install ftllexengine`` (no external dependencies)
    - Full runtime: ``pip install ftllexengine[babel]`` (includes Babel for formatting)

    This module ensures that:
    1. Parser-only installations never trigger Babel imports
    2. All Babel-dependent modules get consistent, helpful error messages when
       Babel is missing
    3. Babel types are available for TYPE_CHECKING without runtime import
    4. The ``# noqa: PLC0415 - Babel-optional`` suppression is confined to this
       single file rather than scattered across call sites

Usage Pattern:
    # At module top-level (for type hints only, no runtime cost):
    from typing import TYPE_CHECKING
    if TYPE_CHECKING:
        from babel import Locale

    # At module top-level (for runtime use — safe, Babel not imported yet):
    from ftllexengine.core.babel_compat import get_locale_class, require_babel

    # Inside a Babel-dependent function:
    def my_function(locale_code: str) -> None:
        require_babel("my_function")        # Raises BabelImportError if missing
        Locale = get_locale_class()         # Returns the Babel Locale class
        locale = Locale.parse(locale_code)

Python 3.13+.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from babel import Locale, UnknownLocaleError
    from babel.numbers import NumberFormatError

__all__ = [
    "BabelImportError",
    "get_babel_dates",
    "get_babel_numbers",
    "get_cldr_version",
    "get_global_data_func",
    "get_locale_class",
    "get_locale_identifiers_func",
    "get_number_format_error_class",
    "get_parse_decimal_func",
    "get_unknown_locale_error_class",
    "is_babel_available",
    "require_babel",
]

# Module-level sentinel for Babel availability (computed once on first check).
_babel_available: bool | None = None


def _check_babel_available() -> bool:
    """Check if Babel is installed (computed once, cached via sentinel)."""
    global _babel_available  # noqa: PLW0603  # pylint: disable=global-statement
    if _babel_available is None:
        try:
            import babel  # noqa: F401, PLC0415  # pylint: disable=unused-import

            _babel_available = True
        except ImportError:
            _babel_available = False
    return _babel_available


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

    Uses cached result to avoid repeated import attempts.

    Returns:
        True if Babel is installed and importable, False otherwise.
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
    """
    if not _check_babel_available():
        raise BabelImportError(feature)


def get_locale_class() -> type[Locale]:
    """Get the Babel Locale class.

    Use when you need the class itself (for isinstance checks, Locale.parse(), etc.)
    rather than an instance.

    Returns:
        The Babel Locale class

    Raises:
        BabelImportError: If Babel is not installed
    """
    require_babel("Locale")
    try:
        from babel import Locale  # noqa: PLC0415 - Babel-optional

        return Locale
    except ImportError as exc:
        feature = "Locale"
        raise BabelImportError(feature) from exc


def get_unknown_locale_error_class() -> type[UnknownLocaleError]:
    """Get the Babel UnknownLocaleError exception class.

    Use in except clauses and isinstance() checks for locale parsing failures.

    Returns:
        The Babel UnknownLocaleError class

    Raises:
        BabelImportError: If Babel is not installed
    """
    require_babel("UnknownLocaleError")
    try:
        from babel import UnknownLocaleError  # noqa: PLC0415 - Babel-optional

        return UnknownLocaleError
    except ImportError as exc:
        feature = "UnknownLocaleError"
        raise BabelImportError(feature) from exc


def get_cldr_version() -> str:
    """Get Unicode CLDR version from Babel.

    Returns the CLDR version string used by Babel for locale data.
    Useful for debugging locale-specific formatting differences and
    verifying deployment environments.

    Returns:
        CLDR version string (e.g., "47").

    Raises:
        BabelImportError: If Babel is not installed.

    Thread Safety:
        Thread-safe. No mutable state.
    """
    require_babel("get_cldr_version")
    try:
        from babel.core import (  # noqa: PLC0415 - Babel-optional
            get_cldr_version as babel_get_cldr_version,
        )

        return babel_get_cldr_version()
    except ImportError as exc:  # pragma: no cover
        feature = "get_cldr_version"
        raise BabelImportError(feature) from exc


def get_babel_numbers() -> Any:
    """Get the babel.numbers module.

    Provides access to all babel.numbers formatting and parsing functions.
    Return type is ``Any`` so call sites can access any module attribute
    without mypy attr-defined errors.

    Returns:
        The babel.numbers module

    Raises:
        BabelImportError: If Babel is not installed
    """
    require_babel("babel.numbers")
    try:
        from babel import numbers  # noqa: PLC0415 - Babel-optional

        return numbers
    except ImportError as exc:  # pragma: no cover
        feature = "babel.numbers"
        raise BabelImportError(feature) from exc


def get_babel_dates() -> Any:
    """Get the babel.dates module.

    Provides access to all babel.dates formatting functions.
    Return type is ``Any`` so call sites can access any module attribute
    without mypy attr-defined errors.

    Returns:
        The babel.dates module

    Raises:
        BabelImportError: If Babel is not installed
    """
    require_babel("babel.dates")
    try:
        from babel import dates  # noqa: PLC0415 - Babel-optional

        return dates
    except ImportError as exc:  # pragma: no cover
        feature = "babel.dates"
        raise BabelImportError(feature) from exc


def get_global_data_func() -> Any:
    """Get the babel.core.get_global function.

    Used to access CLDR global data tables (e.g., territory_currencies).
    Return type is ``Any`` for flexibility across different CLDR data shapes.

    Returns:
        The babel.core.get_global callable

    Raises:
        BabelImportError: If Babel is not installed
    """
    require_babel("babel.core.get_global")
    try:
        from babel.core import get_global  # noqa: PLC0415 - Babel-optional

        return get_global
    except ImportError as exc:  # pragma: no cover
        feature = "babel.core.get_global"
        raise BabelImportError(feature) from exc


def get_number_format_error_class() -> type[NumberFormatError]:
    """Get the babel.numbers.NumberFormatError exception class.

    Use in except clauses for number parsing failures.

    Returns:
        The babel.numbers.NumberFormatError class

    Raises:
        BabelImportError: If Babel is not installed
    """
    require_babel("NumberFormatError")
    try:
        from babel.numbers import NumberFormatError  # noqa: PLC0415 - Babel-optional

        return NumberFormatError
    except ImportError as exc:  # pragma: no cover
        feature = "NumberFormatError"
        raise BabelImportError(feature) from exc


def get_parse_decimal_func() -> Any:
    """Get the babel.numbers.parse_decimal function.

    Use for locale-aware decimal string parsing.
    Return type is ``Any`` to avoid binding to a specific callable signature.

    Returns:
        The babel.numbers.parse_decimal callable

    Raises:
        BabelImportError: If Babel is not installed
    """
    require_babel("babel.numbers.parse_decimal")
    try:
        from babel.numbers import parse_decimal  # noqa: PLC0415 - Babel-optional

        return parse_decimal
    except ImportError as exc:  # pragma: no cover
        feature = "babel.numbers.parse_decimal"
        raise BabelImportError(feature) from exc


def get_locale_identifiers_func() -> Any:
    """Get the babel.localedata.locale_identifiers function.

    Returns an iterator of all locale identifiers known to Babel.
    Return type is ``Any`` to avoid binding to a specific callable signature.

    Returns:
        The babel.localedata.locale_identifiers callable

    Raises:
        BabelImportError: If Babel is not installed
    """
    require_babel("babel.localedata.locale_identifiers")
    try:
        from babel.localedata import locale_identifiers  # noqa: PLC0415 - Babel-optional

        return locale_identifiers
    except ImportError as exc:  # pragma: no cover
        feature = "babel.localedata.locale_identifiers"
        raise BabelImportError(feature) from exc
