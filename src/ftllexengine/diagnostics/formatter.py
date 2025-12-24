"""Diagnostic formatting service.

Centralizes diagnostic output formatting with configurable options.
Python 3.13+. Zero external dependencies.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from .codes import Diagnostic

if TYPE_CHECKING:
    from .validation import ValidationResult

__all__ = [
    "DiagnosticFormatter",
    "OutputFormat",
]


class OutputFormat(StrEnum):
    """Output format options for diagnostic formatting."""

    RUST = "rust"  # Rust compiler-style output (default)
    SIMPLE = "simple"  # Single-line format
    JSON = "json"  # JSON format for tooling integration


@dataclass(frozen=True, slots=True)
class DiagnosticFormatter:
    """Diagnostic formatting service.

    Centralizes formatting of Diagnostic objects into human-readable
    or machine-readable output. Supports multiple output formats and
    sanitization options.

    Attributes:
        output_format: Output style (rust, simple, json)
        sanitize: Truncate content to prevent information leakage
        color: Enable ANSI color codes (for terminal output)
        max_content_length: Maximum content length when sanitizing

    Example:
        >>> formatter = DiagnosticFormatter()
        >>> diagnostic = ErrorTemplate.message_not_found("hello")
        >>> print(formatter.format(diagnostic))
        error[MESSAGE_NOT_FOUND]: Message 'hello' not found
          = help: Check that the message is defined in the loaded resources
          = note: see https://projectfluent.org/fluent/guide/messages.html

        >>> formatter = DiagnosticFormatter(output_format=OutputFormat.SIMPLE)
        >>> print(formatter.format(diagnostic))
        MESSAGE_NOT_FOUND: Message 'hello' not found

        >>> formatter = DiagnosticFormatter(output_format=OutputFormat.JSON)
        >>> print(formatter.format(diagnostic))
        {"code": "MESSAGE_NOT_FOUND", "message": "Message 'hello' not found", ...}
    """

    output_format: OutputFormat = OutputFormat.RUST
    sanitize: bool = False
    color: bool = False
    max_content_length: int = 100

    def format(self, diagnostic: Diagnostic) -> str:
        """Format a single diagnostic.

        Args:
            diagnostic: Diagnostic to format

        Returns:
            Formatted diagnostic string
        """
        match self.output_format:
            case OutputFormat.RUST:
                return self._format_rust(diagnostic)
            case OutputFormat.SIMPLE:
                return self._format_simple(diagnostic)
            case OutputFormat.JSON:
                return self._format_json(diagnostic)

    def format_all(self, diagnostics: Iterable[Diagnostic]) -> str:
        """Format multiple diagnostics.

        Args:
            diagnostics: Iterable of diagnostics to format

        Returns:
            Formatted string with all diagnostics separated by newlines
        """
        return "\n\n".join(self.format(d) for d in diagnostics)

    def format_validation_result(self, result: "ValidationResult") -> str:
        """Format a ValidationResult with all errors, warnings, and annotations.

        Args:
            result: ValidationResult to format

        Returns:
            Formatted string with summary and details
        """
        parts: list[str] = []

        # Summary line
        if result.is_valid:
            parts.append("Validation passed")
        else:
            parts.append(
                f"Validation failed: {result.error_count} error(s), "
                f"{result.warning_count} warning(s)"
            )

        # Format errors
        if result.errors:
            parts.append("\nErrors:")
            for error in result.errors:
                formatted = self._format_validation_error(error)
                parts.append(f"  {formatted}")

        # Format warnings
        if result.warnings:
            parts.append("\nWarnings:")
            for warning in result.warnings:
                parts.append(f"  {warning.format()}")

        # Format annotations (parser messages)
        if result.annotations:
            parts.append("\nAnnotations:")
            for annotation in result.annotations:
                parts.append(f"  [{annotation.code}] {annotation.message}")

        return "\n".join(parts)

    def _format_validation_error(self, error: object) -> str:
        """Format a ValidationError object.

        Args:
            error: ValidationError-like object with code, message, line, column

        Returns:
            Formatted error string
        """
        # Access attributes safely for duck typing
        code = getattr(error, "code", "UNKNOWN")
        message = getattr(error, "message", str(error))
        line = getattr(error, "line", None)
        column = getattr(error, "column", None)

        if line is not None and column is not None:
            return f"[{code}] at line {line}, column {column}: {message}"
        if line is not None:
            return f"[{code}] at line {line}: {message}"
        return f"[{code}]: {message}"

    def _format_rust(self, diagnostic: Diagnostic) -> str:
        """Format diagnostic in Rust compiler style.

        Example output:
            error[MESSAGE_NOT_FOUND]: Message 'hello' not found
              --> line 5, column 10
              = help: Check that the message is defined
              = note: see https://projectfluent.org/fluent/guide/messages.html
        """
        severity = diagnostic.severity if diagnostic.severity == "warning" else "error"

        # Apply color if enabled
        if self.color:
            if severity == "error":
                severity_str = f"\033[1;31m{severity}\033[0m"  # Bold red
            else:
                severity_str = f"\033[1;33m{severity}\033[0m"  # Bold yellow
        else:
            severity_str = severity

        parts = [f"{severity_str}[{diagnostic.code.name}]: {diagnostic.message}"]

        if diagnostic.span:
            parts.append(f"  --> line {diagnostic.span.line}, column {diagnostic.span.column}")
        elif diagnostic.ftl_location:
            parts.append(f"  --> {diagnostic.ftl_location}")

        if diagnostic.function_name:
            parts.append(f"  = function: {diagnostic.function_name}")

        if diagnostic.argument_name:
            parts.append(f"  = argument: {diagnostic.argument_name}")

        if diagnostic.expected_type:
            parts.append(f"  = expected: {diagnostic.expected_type}")

        if diagnostic.received_type:
            parts.append(f"  = received: {diagnostic.received_type}")

        if diagnostic.hint:
            hint = self._maybe_sanitize(diagnostic.hint)
            parts.append(f"  = help: {hint}")

        if diagnostic.help_url:
            parts.append(f"  = note: see {diagnostic.help_url}")

        return "\n".join(parts)

    def _format_simple(self, diagnostic: Diagnostic) -> str:
        """Format diagnostic in single-line format.

        Example output:
            MESSAGE_NOT_FOUND: Message 'hello' not found
        """
        message = self._maybe_sanitize(diagnostic.message)
        return f"{diagnostic.code.name}: {message}"

    def _format_json(self, diagnostic: Diagnostic) -> str:
        """Format diagnostic as JSON.

        Example output:
            {"code": "MESSAGE_NOT_FOUND", "message": "...", "severity": "error"}
        """
        import json  # noqa: PLC0415

        data: dict[str, str | int | None] = {
            "code": diagnostic.code.name,
            "code_value": diagnostic.code.value,
            "message": self._maybe_sanitize(diagnostic.message),
            "severity": diagnostic.severity,
        }

        # Add optional fields if present
        if diagnostic.span:
            data["line"] = diagnostic.span.line
            data["column"] = diagnostic.span.column
            data["start"] = diagnostic.span.start
            data["end"] = diagnostic.span.end

        if diagnostic.ftl_location:
            data["ftl_location"] = diagnostic.ftl_location

        if diagnostic.function_name:
            data["function_name"] = diagnostic.function_name

        if diagnostic.argument_name:
            data["argument_name"] = diagnostic.argument_name

        if diagnostic.expected_type:
            data["expected_type"] = diagnostic.expected_type

        if diagnostic.received_type:
            data["received_type"] = diagnostic.received_type

        if diagnostic.hint:
            data["hint"] = self._maybe_sanitize(diagnostic.hint)

        if diagnostic.help_url:
            data["help_url"] = diagnostic.help_url

        return json.dumps(data, ensure_ascii=False)

    def _maybe_sanitize(self, text: str) -> str:
        """Truncate text if sanitization is enabled.

        Args:
            text: Text to possibly truncate

        Returns:
            Original or truncated text
        """
        if self.sanitize and len(text) > self.max_content_length:
            return text[: self.max_content_length] + "..."
        return text
