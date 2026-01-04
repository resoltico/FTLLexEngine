"""Core utilities shared across syntax and runtime layers.

This package provides foundational utilities that both the syntax layer
(parsing, serialization) and runtime layer (resolution, formatting) depend on.
By isolating these utilities here, we maintain a clean dependency graph:

    core <- syntax <- runtime

Exports:
    DepthGuard: Context manager for recursion depth limiting
    DepthLimitExceededError: Exception raised when depth limit exceeded
    FormattingError: Exception raised when locale formatting fails
    BabelImportError: Exception raised when Babel is required but not installed
    require_babel: Assert Babel availability with clear error messaging
    get_babel_locale: Cached Babel Locale retrieval with lazy import

Python 3.13+.
"""

from .babel_compat import BabelImportError, get_babel_locale, require_babel
from .depth_guard import DepthGuard, DepthLimitExceededError
from .errors import FormattingError

__all__ = [
    "BabelImportError",
    "DepthGuard",
    "DepthLimitExceededError",
    "FormattingError",
    "get_babel_locale",
    "require_babel",
]
