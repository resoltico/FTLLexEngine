"""Diagnostic system for Fluent errors.

Provides structured error diagnostics with codes, spans, hints, and help URLs.
Inspired by Rust compiler diagnostics and Elm error messages.

Python 3.13+. Zero external dependencies.
"""

from .codes import (
    Diagnostic,
    DiagnosticCode,
    ErrorCategory,
    FrozenErrorContext,
    ParseTypeLiteral,
    SourceSpan,
)
from .errors import FrozenFluentError
from .formatter import DiagnosticFormatter, OutputFormat
from .templates import ErrorTemplate
from .validation import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
    WarningSeverity,
)

# ruff: noqa: RUF022 - __all__ organized by category for readability, not alphabetically
__all__ = [
    # Diagnostic infrastructure
    "Diagnostic",
    "DiagnosticCode",
    "DiagnosticFormatter",
    "ErrorTemplate",
    "OutputFormat",
    "SourceSpan",
    # Error types (immutable, sealed)
    "ErrorCategory",
    "FrozenErrorContext",
    "FrozenFluentError",
    "ParseTypeLiteral",
    # Validation
    "ValidationError",
    "ValidationResult",
    "ValidationWarning",
    "WarningSeverity",
]
