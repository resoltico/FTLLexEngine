"""Core error types shared across syntax and runtime layers.

Re-exports FrozenFluentError from diagnostics for import compatibility.

Python 3.13+.
"""

# Re-export FrozenFluentError for any code that was importing from here
from ftllexengine.diagnostics import (
    ErrorCategory,
    FrozenErrorContext,
    FrozenFluentError,
)

__all__ = [
    "ErrorCategory",
    "FrozenErrorContext",
    "FrozenFluentError",
]
