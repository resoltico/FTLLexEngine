"""Core utilities shared across syntax and runtime layers.

This package provides foundational utilities that both the syntax layer
(parsing, serialization) and runtime layer (resolution, formatting) depend on.
By isolating these utilities here, we maintain a clean dependency graph:

    core <- syntax <- runtime

Exports:
    DepthGuard: Context manager for recursion depth limiting
    DepthLimitExceededError: Exception raised when depth limit exceeded
    FormattingError: Exception raised when locale formatting fails

Python 3.13+.
"""

from .depth_guard import DepthGuard, DepthLimitExceededError
from .errors import FormattingError

__all__ = ["DepthGuard", "DepthLimitExceededError", "FormattingError"]
