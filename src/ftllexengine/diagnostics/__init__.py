"""Diagnostic system for Fluent errors.

Provides structured error diagnostics with codes, spans, hints, and help URLs.
Inspired by Rust compiler diagnostics and Elm error messages.

Python 3.13+. Zero external dependencies.
"""

from .codes import Diagnostic, DiagnosticCode, SourceSpan
from .errors import (
    FluentCyclicReferenceError,
    FluentError,
    FluentParseError,
    FluentReferenceError,
    FluentResolutionError,
)
from .formatter import DiagnosticFormatter, OutputFormat
from .templates import ErrorTemplate
from .validation import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
    WarningSeverity,
)

__all__ = [
    "Diagnostic",
    "DiagnosticCode",
    "DiagnosticFormatter",
    "ErrorTemplate",
    "FluentCyclicReferenceError",
    "FluentError",
    "FluentParseError",
    "FluentReferenceError",
    "FluentResolutionError",
    "OutputFormat",
    "SourceSpan",
    "ValidationError",
    "ValidationResult",
    "ValidationWarning",
    "WarningSeverity",
]
