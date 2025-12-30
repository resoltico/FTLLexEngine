"""Core error types shared across syntax and runtime layers.

Provides error types that need to be importable from both syntax and runtime
packages without creating circular dependencies.

Python 3.13+.
"""

from ftllexengine.diagnostics import FluentResolutionError
from ftllexengine.diagnostics.codes import Diagnostic

__all__ = ["FormattingError"]


class FormattingError(FluentResolutionError):
    """Raised when locale-aware formatting fails.

    This error indicates a failure in number, date, or currency formatting.
    Unlike silent fallbacks, this error propagates to the resolver for
    collection while still providing a usable fallback value.

    The error carries a fallback_value that should be used in the output
    when the formatting fails. This ensures:
    - Error is collected and visible to callers
    - Output still contains usable content (the original value)
    - Debugging information preserved in error message

    Attributes:
        fallback_value: String to use in output when formatting fails
    """

    def __init__(self, message: str | Diagnostic, fallback_value: str) -> None:
        """Initialize FormattingError.

        Args:
            message: Error message string OR Diagnostic object
            fallback_value: Value to use in output when formatting fails
        """
        super().__init__(message)
        self.fallback_value = fallback_value
