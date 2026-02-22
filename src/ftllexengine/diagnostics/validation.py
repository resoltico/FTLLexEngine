"""Unified validation result for Fluent resource validation.

Consolidates all validation feedback from different stages:
- Parser-level: Syntax annotations from AST parsing
- Syntax-level: Structured validation errors
- Semantic-level: Structured validation warnings

Formatting Architecture:
    All .format() methods delegate to DiagnosticFormatter to ensure
    consistent output style. The formatter is created on-demand with
    the appropriate options (sanitize, redact_content).

Python 3.13+.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from ftllexengine.diagnostics.codes import DiagnosticCode
from ftllexengine.syntax.ast import Annotation

if TYPE_CHECKING:
    from .formatter import DiagnosticFormatter

__all__ = [
    "ValidationError",
    "ValidationResult",
    "ValidationWarning",
    "WarningSeverity",
]


class WarningSeverity(StrEnum):
    """Severity levels for validation warnings.

    Provides semantic differentiation between warning types:
    - CRITICAL: Will cause runtime failure (e.g., undefined reference)
    - WARNING: May cause issues (e.g., duplicate ID, missing value)
    - INFO: Informational only (e.g., style suggestions)

    Use severity to filter or prioritize warnings in tooling:
        critical_warnings = [w for w in warnings if w.severity == WarningSeverity.CRITICAL]
    """

    CRITICAL = "critical"  # Will cause runtime failure
    WARNING = "warning"  # May cause issues
    INFO = "info"  # Informational only


# ============================================================================
# VALIDATION ERROR & WARNING TYPES
# ============================================================================


def _get_formatter(
    *,
    sanitize: bool = False,
    redact_content: bool = False,
) -> DiagnosticFormatter:
    """Create DiagnosticFormatter with specified options.

    Local import to avoid circular dependency at module load time.
    """
    from .formatter import DiagnosticFormatter  # noqa: PLC0415 - circular

    return DiagnosticFormatter(sanitize=sanitize, redact_content=redact_content)


@dataclass(frozen=True, slots=True)
class ValidationError:
    """Structured syntax error from FTL validation.

    Attributes:
        code: Typed diagnostic code identifying the error class.
        message: Human-readable error message.
        content: The unparseable FTL content.
        line: Line number where error occurred (1-indexed, optional).
        column: Column number where error occurred (1-indexed, optional).

    Security Note:
        The `content` field may contain FTL source that should not be exposed
        to end users in multi-tenant applications. Use format(sanitize=True)
        to truncate or redact content before logging or displaying errors.
    """

    code: DiagnosticCode
    message: str
    content: str
    line: int | None = None
    column: int | None = None

    def format(
        self,
        *,
        sanitize: bool = False,
        redact_content: bool = False,
    ) -> str:
        """Format error as human-readable string.

        Delegates to DiagnosticFormatter for consistent output style.

        Args:
            sanitize: If True, truncate content to prevent information leakage.
                     Useful for multi-tenant applications where FTL content
                     may contain tenant-specific patterns.
            redact_content: If True (and sanitize=True), completely redact
                           content instead of truncating. More secure but
                           less useful for debugging.

        Returns:
            Formatted error string with optional content sanitization.

        Examples:
            >>> error = ValidationError(DiagnosticCode.PARSE_JUNK, "Syntax error", "bad ftl")
            >>> error.format(sanitize=True)  # Truncates to 100 chars
            >>> error.format(sanitize=True, redact_content=True)  # Redacts entirely
        """
        formatter = _get_formatter(sanitize=sanitize, redact_content=redact_content)
        return formatter.format_error(self)


@dataclass(frozen=True, slots=True)
class ValidationWarning:
    """Structured semantic warning from FTL validation.

    Attributes:
        code: Typed diagnostic code identifying the warning class.
        message: Human-readable warning message.
        context: Additional context (e.g., the duplicate ID name).
        line: Line number where warning occurred (1-indexed, optional).
        column: Column number where warning occurred (1-indexed, optional).
        severity: Warning severity level (CRITICAL, WARNING, INFO).

    The optional line/column fields enable IDE integration (LSP servers)
    to display warning squiggles at the correct source location.

    Severity levels:
        CRITICAL: Will cause runtime failure (e.g., undefined reference to message)
        WARNING: May cause issues (e.g., duplicate ID overwrites previous)
        INFO: Informational only (e.g., unused term)
    """

    code: DiagnosticCode
    message: str
    context: str | None = None
    line: int | None = None
    column: int | None = None
    severity: WarningSeverity = WarningSeverity.WARNING

    def format(
        self,
        *,
        sanitize: bool = False,
        redact_content: bool = False,
    ) -> str:
        """Format warning as human-readable string.

        Delegates to DiagnosticFormatter for consistent output style.

        Args:
            sanitize: If True, truncate context to prevent information leakage.
                     Useful for multi-tenant applications where context may
                     contain tenant-specific message or term identifiers.
            redact_content: If True (and sanitize=True), completely redact
                           context instead of truncating.

        Returns:
            Formatted warning string with optional location and context information.
        """
        formatter = _get_formatter(sanitize=sanitize, redact_content=redact_content)
        return formatter.format_warning(self)


# ============================================================================
# UNIFIED VALIDATION RESULT
# ============================================================================


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Unified validation result for all validation levels.

    Consolidates feedback from:
    - Parser: AST annotations (syntax errors, malformed tokens)
    - Syntax validator: Structural validation errors
    - Semantic validator: Semantic warnings (duplicates, references, etc.)

    Immutable result object for thread-safe validation feedback.

    Attributes:
        errors: Syntax/parse validation errors.
        warnings: Semantic validation warnings.
        annotations: Parser-level AST annotations.

    Example:
        >>> result = ValidationResult.valid()
        >>> result.is_valid
        True
        >>> result.error_count
        0

        >>> # With errors
        >>> result = ValidationResult.invalid(
        ...     errors=(ValidationError(
        ...         code=DiagnosticCode.PARSE_JUNK,
        ...         message="Expected '=' but found EOF",
        ...         content="msg",
        ...         line=1,
        ...         column=4
        ...     ),)
        ... )
        >>> result.is_valid
        False
        >>> result.error_count
        1
    """

    errors: tuple[ValidationError, ...]
    warnings: tuple[ValidationWarning, ...]
    annotations: tuple[Annotation, ...]

    @property
    def is_valid(self) -> bool:
        """Check if validation passed (no errors or annotations).

        Warnings do not affect validity - they're informational.

        Returns:
            True if no errors or annotations found
        """
        return len(self.errors) == 0 and len(self.annotations) == 0

    @property
    def error_count(self) -> int:
        """Get number of syntax/structural validation errors.

        Returns:
            Count of ValidationError instances in ``errors``
        """
        return len(self.errors)

    @property
    def annotation_count(self) -> int:
        """Get number of parser-level annotations (parse errors).

        Returns:
            Count of Annotation instances in ``annotations``
        """
        return len(self.annotations)

    @property
    def warning_count(self) -> int:
        """Get number of semantic warnings.

        Returns:
            Count of warnings
        """
        return len(self.warnings)

    @staticmethod
    def valid() -> ValidationResult:
        """Create a valid result with no errors, warnings, or annotations.

        Returns:
            ValidationResult with empty tuples for all fields
        """
        return ValidationResult(errors=(), warnings=(), annotations=())

    @staticmethod
    def invalid(
        errors: tuple[ValidationError, ...] = (),
        warnings: tuple[ValidationWarning, ...] = (),
        annotations: tuple[Annotation, ...] = (),
    ) -> ValidationResult:
        """Create an invalid result with errors and/or annotations.

        Args:
            errors: Tuple of validation errors (default: empty)
            warnings: Tuple of validation warnings (default: empty)
            annotations: Tuple of parser annotations (default: empty)

        Returns:
            ValidationResult with provided errors/warnings/annotations
        """
        return ValidationResult(
            errors=errors, warnings=warnings, annotations=annotations
        )

    @staticmethod
    def from_annotations(annotations: tuple[Annotation, ...]) -> ValidationResult:
        """Create result from parser-level annotations only.

        Convenience factory for semantic validator usage.

        Args:
            annotations: Tuple of AST annotations

        Returns:
            ValidationResult with annotations, empty errors/warnings
        """
        if annotations:
            return ValidationResult(errors=(), warnings=(), annotations=annotations)
        return ValidationResult.valid()

    def format(
        self,
        *,
        sanitize: bool = False,
        redact_content: bool = False,
        include_warnings: bool = True,
    ) -> str:
        """Format validation result as human-readable string.

        Delegates to DiagnosticFormatter for consistent output style.

        Args:
            sanitize: If True, truncate error content to prevent information
                     leakage. Useful for multi-tenant applications where FTL
                     content may contain tenant-specific patterns.
            redact_content: If True (and sanitize=True), completely redact
                           error content instead of truncating.
            include_warnings: If True (default), include warnings in output.

        Returns:
            Formatted string with errors, annotations, and optionally warnings.

        Security Note:
            In multi-tenant applications, set sanitize=True to prevent leaking
            FTL source content in error messages. For maximum security, also
            set redact_content=True.

        Examples:
            >>> result.format()  # Full output for debugging
            >>> result.format(sanitize=True)  # Truncated content
            >>> result.format(sanitize=True, redact_content=True)  # No content
        """
        formatter = _get_formatter(sanitize=sanitize, redact_content=redact_content)
        return formatter.format_validation_result(self, include_warnings=include_warnings)
