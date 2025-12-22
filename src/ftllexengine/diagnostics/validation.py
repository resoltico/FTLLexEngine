"""Unified validation result for Fluent resource validation.

Consolidates all validation feedback from different stages:
- Parser-level: Syntax annotations from AST parsing
- Syntax-level: Structured validation errors
- Semantic-level: Structured validation warnings

Python 3.13+.
"""

from dataclasses import dataclass

from ftllexengine.syntax.ast import Annotation

__all__ = [
    "ValidationError",
    "ValidationResult",
    "ValidationWarning",
]


# ============================================================================
# VALIDATION ERROR & WARNING TYPES
# ============================================================================


# Maximum content length before truncation when sanitizing
_SANITIZE_MAX_CONTENT_LENGTH: int = 100


@dataclass(frozen=True, slots=True)
class ValidationError:
    """Structured syntax error from FTL validation.

    Attributes:
        code: Error code (e.g., "parse-error", "malformed-entry")
        message: Human-readable error message
        content: The unparseable FTL content
        line: Line number where error occurred (1-indexed, optional)
        column: Column number where error occurred (1-indexed, optional)

    Security Note:
        The `content` field may contain FTL source that should not be exposed
        to end users in multi-tenant applications. Use format(sanitize=True)
        to truncate or redact content before logging or displaying errors.
    """

    code: str
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
            >>> error = ValidationError("parse-error", "Syntax error", "secret data here")
            >>> error.format(sanitize=True)  # Truncates to 100 chars
            >>> error.format(sanitize=True, redact_content=True)  # Redacts entirely
        """
        if sanitize:
            if redact_content:
                content_display = "[content redacted]"
            elif len(self.content) > _SANITIZE_MAX_CONTENT_LENGTH:
                content_display = self.content[:_SANITIZE_MAX_CONTENT_LENGTH] + "..."
            else:
                content_display = self.content
        else:
            content_display = self.content

        location = ""
        if self.line is not None:
            location = f" at line {self.line}"
            if self.column is not None:
                location += f", column {self.column}"

        return f"[{self.code}]{location}: {self.message} (content: {content_display!r})"


@dataclass(frozen=True, slots=True)
class ValidationWarning:
    """Structured semantic warning from FTL validation.

    Attributes:
        code: Warning code (e.g., "duplicate-id", "undefined-reference")
        message: Human-readable warning message
        context: Additional context (e.g., the duplicate ID name)
    """

    code: str
    message: str
    context: str | None = None


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
        errors: Syntax/parse validation errors
        warnings: Semantic validation warnings
        annotations: Parser-level AST annotations

    Example:
        >>> result = ValidationResult.valid()
        >>> result.is_valid
        True
        >>> result.error_count
        0

        >>> # With errors
        >>> result = ValidationResult.invalid(
        ...     errors=(ValidationError(
        ...         code="parse-error",
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
        """Get total number of errors (syntax + parser).

        Returns:
            Count of errors and annotations combined
        """
        return len(self.errors) + len(self.annotations)

    @property
    def warning_count(self) -> int:
        """Get number of semantic warnings.

        Returns:
            Count of warnings
        """
        return len(self.warnings)

    @staticmethod
    def valid() -> "ValidationResult":
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
    ) -> "ValidationResult":
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
    def from_annotations(annotations: tuple[Annotation, ...]) -> "ValidationResult":
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
        lines: list[str] = []

        # Format errors with sanitization
        if self.errors:
            lines.append(f"Errors ({len(self.errors)}):")
            for error in self.errors:
                lines.append(f"  {error.format(sanitize=sanitize, redact_content=redact_content)}")

        # Format annotations (parser-level errors)
        if self.annotations:
            lines.append(f"Annotations ({len(self.annotations)}):")
            for annotation in self.annotations:
                # Annotations have code and message but content may contain source
                content = annotation.message
                if sanitize and len(content) > _SANITIZE_MAX_CONTENT_LENGTH:
                    content = content[:_SANITIZE_MAX_CONTENT_LENGTH] + "..."
                lines.append(f"  [{annotation.code}]: {content}")

        # Format warnings if requested
        if include_warnings and self.warnings:
            lines.append(f"Warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                context = f" ({warning.context})" if warning.context else ""
                lines.append(f"  [{warning.code}]: {warning.message}{context}")

        if not lines:
            return "Validation passed: no errors or warnings"

        return "\n".join(lines)
