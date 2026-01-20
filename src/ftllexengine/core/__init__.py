"""Core utilities shared across syntax and runtime layers.

This package provides foundational utilities that both the syntax layer
(parsing, serialization) and runtime layer (resolution, formatting) depend on.
By isolating these utilities here, we maintain a clean dependency graph:

    core <- syntax <- runtime

Exports:
    DepthGuard: Context manager for recursion depth limiting
    depth_clamp: Utility function for clamping depth values against recursion limit
    BabelImportError: Exception raised when Babel is required but not installed
    require_babel: Assert Babel availability with clear error messaging
    ErrorCategory: Enum for error classification (re-export from diagnostics)
    FrozenErrorContext: Context for parse/formatting errors (re-export)
    FrozenFluentError: Immutable error type (re-export from diagnostics)

Python 3.13+.
"""

from .babel_compat import BabelImportError, require_babel
from .depth_guard import DepthGuard, depth_clamp
from .errors import ErrorCategory, FrozenErrorContext, FrozenFluentError

__all__ = [
    "BabelImportError",
    "DepthGuard",
    "ErrorCategory",
    "FrozenErrorContext",
    "FrozenFluentError",
    "depth_clamp",
    "require_babel",
]
