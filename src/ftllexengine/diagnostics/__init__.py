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
    FluentSyntaxError,
)
from .formatter import DiagnosticFormatter, OutputFormat
from .templates import ErrorTemplate
from .validation import ValidationError, ValidationResult, ValidationWarning

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
    "FluentSyntaxError",
    "OutputFormat",
    "SourceSpan",
    "ValidationError",
    "ValidationResult",
    "ValidationWarning",
]
