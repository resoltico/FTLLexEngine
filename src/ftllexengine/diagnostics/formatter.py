"""Diagnostic formatting service.

Centralizes diagnostic output formatting with configurable options.
Python 3.13+. Zero external dependencies.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, assert_never

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

    Central Formatting Authority:
        This class is the single source of truth for diagnostic formatting.
        ValidationError.format(), ValidationWarning.format(), and
        ValidationResult.format() all delegate to this class to ensure
        consistent output style across all diagnostic types.

    Attributes:
        output_format: Output style (rust, simple, json)
        sanitize: Truncate content to prevent information leakage
        redact_content: When sanitize=True, completely redact instead of truncate
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
    redact_content: bool = False
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
            case _:
                assert_never(self.output_format)

    def format_all(self, diagnostics: Iterable[Diagnostic]) -> str:
        """Format multiple diagnostics.

        Args:
            diagnostics: Iterable of diagnostics to format

        Returns:
            Formatted string with all diagnostics separated by newlines
        """
        return "\n\n".join(self.format(d) for d in diagnostics)

    def format_validation_result(
        self,
        result: ValidationResult,
        *,
        include_warnings: bool = True,
    ) -> str:
        """Format a ValidationResult with all errors, warnings, and annotations.

        Central formatting method for ValidationResult. Called by
        ValidationResult.format() to ensure consistent output.

        Args:
            result: ValidationResult to format
            include_warnings: If True (default), include warnings in output

        Returns:
            Formatted string with summary and details
        """
        parts: list[str] = []

        # Summary line
        if result.is_valid and (not include_warnings or not result.warnings):
            parts.append("Validation passed: no errors or warnings")
        elif result.is_valid:
            parts.append(f"Validation passed with {result.warning_count} warning(s)")
        else:
            parts.append(
                f"Validation failed: {result.error_count} error(s), "
                f"{result.warning_count} warning(s)"
            )

        # Format errors
        if result.errors:
            parts.append(f"\nErrors ({len(result.errors)}):")
            for error in result.errors:
                formatted = self.format_error(error)
                parts.append(f"  {formatted}")

        # Format annotations (parser messages)
        if result.annotations:
            parts.append(f"\nAnnotations ({len(result.annotations)}):")
            for annotation in result.annotations:
                formatted = self._format_annotation(annotation)
                parts.append(f"  {formatted}")

        # Format warnings if requested
        if include_warnings and result.warnings:
            parts.append(f"\nWarnings ({len(result.warnings)}):")
            for warning in result.warnings:
                formatted = self.format_warning(warning)
                parts.append(f"  {formatted}")

        return "\n".join(parts)

    def format_error(self, error: object) -> str:
        """Format a ValidationError object.

        Central formatting method for ValidationError. Called by
        ValidationError.format() to ensure consistent output.

        Args:
            error: ValidationError-like object with code, message, content, line, column

        Returns:
            Formatted error string with location and content
        """
        # Direct attribute access for known type; getattr fallback for duck typing
        from .validation import ValidationError  # noqa: PLC0415

        if isinstance(error, ValidationError):
            code = error.code
            message = error.message
            content: str | None = error.content
            line = error.line
            column = error.column
        else:
            code = getattr(error, "code", "UNKNOWN")
            message = getattr(error, "message", str(error))
            content = getattr(error, "content", None)
            line = getattr(error, "line", None)
            column = getattr(error, "column", None)

        # Build location string
        location = ""
        if line is not None:
            location = f" at line {line}"
            if column is not None:
                location += f", column {column}"

        # Build content display with sanitization
        content_str = ""
        if content is not None:
            content_display = self._maybe_sanitize_content(content)
            content_str = f" (content: {content_display!r})"

        return f"[{code}]{location}: {message}{content_str}"

    def format_warning(self, warning: object) -> str:
        """Format a ValidationWarning object.

        Central formatting method for ValidationWarning. Called by
        ValidationWarning.format() to ensure consistent output.

        Args:
            warning: ValidationWarning-like object with code, message, context, line, column

        Returns:
            Formatted warning string with location and context
        """
        # Direct attribute access for known type; getattr fallback for duck typing
        from .validation import ValidationWarning  # noqa: PLC0415

        if isinstance(warning, ValidationWarning):
            code = warning.code
            message = warning.message
            context = warning.context
            line = warning.line
            column = warning.column
        else:
            code = getattr(warning, "code", "UNKNOWN")
            message = getattr(warning, "message", str(warning))
            context = getattr(warning, "context", None)
            line = getattr(warning, "line", None)
            column = getattr(warning, "column", None)

        # Build location string
        location = ""
        if line is not None:
            location = f" at line {line}"
            if column is not None:
                location += f", column {column}"

        # Build context string
        context_str = f" (context: {context!r})" if context else ""

        return f"[{code}]{location}: {message}{context_str}"

    def _format_annotation(self, annotation: object) -> str:
        """Format an AST Annotation object.

        Args:
            annotation: Annotation object with code, message, arguments

        Returns:
            Formatted annotation string
        """
        code = getattr(annotation, "code", "UNKNOWN")
        message = getattr(annotation, "message", str(annotation))
        arguments = getattr(annotation, "arguments", None)

        # Sanitize and escape message to prevent log injection
        message = self._escape_control_chars(self._maybe_sanitize(message))

        # Include arguments tuple if present
        if arguments:
            args_str = ", ".join(f"{k}={v!r}" for k, v in arguments)
            return f"[{code}]: {message} ({args_str})"
        return f"[{code}]: {message}"

    def _severity_str(self, severity: str) -> str:
        """Format severity label with optional ANSI color.

        Args:
            severity: "error" or "warning"

        Returns:
            Plain or ANSI-colored severity string
        """
        if not self.color:
            return severity
        if severity == "error":
            return f"\033[1;31m{severity}\033[0m"  # Bold red
        return f"\033[1;33m{severity}\033[0m"  # Bold yellow

    def _format_rust(self, diagnostic: Diagnostic) -> str:
        """Format diagnostic in Rust compiler style.

        Example output:
            error[MESSAGE_NOT_FOUND]: Message 'hello' not found
              --> line 5, column 10
              = help: Check that the message is defined
              = note: see https://projectfluent.org/fluent/guide/messages.html
        """
        severity = diagnostic.severity if diagnostic.severity == "warning" else "error"
        severity_str = self._severity_str(severity)

        # Escape control characters in all user-influenced fields to prevent
        # log injection (fake diagnostic lines via embedded newlines)
        message = self._escape_control_chars(diagnostic.message)
        parts = [f"{severity_str}[{diagnostic.code.name}]: {message}"]

        if diagnostic.span:
            parts.append(f"  --> line {diagnostic.span.line}, column {diagnostic.span.column}")
        elif diagnostic.ftl_location:
            parts.append(f"  --> {self._escape_control_chars(diagnostic.ftl_location)}")

        if diagnostic.function_name:
            parts.append(f"  = function: {self._escape_control_chars(diagnostic.function_name)}")

        if diagnostic.argument_name:
            parts.append(f"  = argument: {self._escape_control_chars(diagnostic.argument_name)}")

        if diagnostic.expected_type:
            parts.append(f"  = expected: {self._escape_control_chars(diagnostic.expected_type)}")

        if diagnostic.received_type:
            parts.append(f"  = received: {self._escape_control_chars(diagnostic.received_type)}")

        if diagnostic.resolution_path:
            path_str = " -> ".join(diagnostic.resolution_path)
            parts.append(
                f"  = resolution path: {self._escape_control_chars(path_str)}"
            )

        if diagnostic.hint:
            hint = self._escape_control_chars(self._maybe_sanitize(diagnostic.hint))
            parts.append(f"  = help: {hint}")

        if diagnostic.help_url:
            parts.append(f"  = note: see {self._escape_control_chars(diagnostic.help_url)}")

        return "\n".join(parts)

    def _format_simple(self, diagnostic: Diagnostic) -> str:
        """Format diagnostic in single-line format.

        Example output:
            MESSAGE_NOT_FOUND: Message 'hello' not found
        """
        message = self._escape_control_chars(self._maybe_sanitize(diagnostic.message))
        return f"{diagnostic.code.name}: {message}"

    def _format_json(self, diagnostic: Diagnostic) -> str:
        """Format diagnostic as JSON.

        Example output:
            {"code": "MESSAGE_NOT_FOUND", "message": "...", "severity": "error"}
        """
        import json  # noqa: PLC0415

        data: dict[str, str | int | list[str] | None] = {
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

        if diagnostic.resolution_path:
            data["resolution_path"] = list(diagnostic.resolution_path)

        if diagnostic.hint:
            data["hint"] = self._maybe_sanitize(diagnostic.hint)

        if diagnostic.help_url:
            data["help_url"] = diagnostic.help_url

        return json.dumps(data, ensure_ascii=False)

    @staticmethod
    def _escape_control_chars(text: str) -> str:
        """Escape control characters to prevent log injection.

        Newlines, carriage returns, and tabs in diagnostic fields can inject
        fake diagnostic lines into structured text output. This escapes them
        to their visible escape-sequence representations.

        Args:
            text: Text to escape

        Returns:
            Text with control characters replaced by escape sequences
        """
        return (
            text
            .replace("\x1b", "\\x1b")
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("\t", "\\t")
        )

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

    def _maybe_sanitize_content(self, content: str) -> str:
        """Sanitize content field with optional redaction.

        Handles both truncation and complete redaction based on formatter options.

        Args:
            content: Content string to possibly sanitize

        Returns:
            Original, truncated, or redacted content
        """
        if not self.sanitize:
            return content

        if self.redact_content:
            return "[content redacted]"

        if len(content) > self.max_content_length:
            return content[: self.max_content_length] + "..."

        return content
