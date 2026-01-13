"""Core utilities shared across syntax and runtime layers.

This package provides foundational utilities that both the syntax layer
(parsing, serialization) and runtime layer (resolution, formatting) depend on.
By isolating these utilities here, we maintain a clean dependency graph:

    core <- syntax <- runtime

Exports:
    DepthGuard: Context manager for recursion depth limiting
    DepthLimitExceededError: Exception raised when depth limit exceeded
    depth_clamp: Utility function for clamping depth values against recursion limit
    FormattingError: Exception raised when locale formatting fails
    BabelImportError: Exception raised when Babel is required but not installed
    require_babel: Assert Babel availability with clear error messaging

Python 3.13+.
"""

from .babel_compat import BabelImportError, require_babel
from .depth_guard import DepthGuard, DepthLimitExceededError, depth_clamp
from .errors import FormattingError

__all__ = [
    "BabelImportError",
    "DepthGuard",
    "DepthLimitExceededError",
    "FormattingError",
    "depth_clamp",
    "require_babel",
]
