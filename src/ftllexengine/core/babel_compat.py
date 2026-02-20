"""Babel compatibility layer for optional dependency handling.

Provides centralized, lazy import infrastructure for Babel to ensure consistent
error messaging and import behavior across all Babel-dependent modules.

Design Rationale:
    FTLLexEngine supports two installation modes:
    - Parser-only: ``pip install ftllexengine`` (no external dependencies)
    - Full runtime: ``pip install ftllexengine[babel]`` (includes Babel for formatting)

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
        require_babel("my_function")  # Raises BabelImportError if missing
        from babel import Locale  # Safe to import now
        ...

Python 3.13+.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from babel import Locale

__all__ = [
    "BabelImportError",
    "get_cldr_version",
    "get_locale_class",
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

    Use when you need the class itself (for isinstance checks, etc.)
    rather than an instance.

    Returns:
        The Babel Locale class

    Raises:
        BabelImportError: If Babel is not installed
    """
    require_babel("get_locale_class")
    from babel import Locale  # noqa: PLC0415 - Babel-optional

    return Locale


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
    from babel.core import (  # noqa: PLC0415 - Babel-optional
        get_cldr_version as babel_get_cldr_version,
    )

    return babel_get_cldr_version()
