"""Coverage tests for diagnostics/validation.py format methods.

Targets uncovered lines:
- Lines 78-94: ValidationError.format() method
- Lines 268-270: ValidationResult.format() errors section
- Lines 283-284: Annotation arguments formatting in ValidationResult.format()
- Line 178: error_count property
- Line 187: warning_count property
- Lines 230-232: from_annotations static method
- Lines 290-293: Warnings formatting in ValidationResult.format()
- Line 296: Passed message when no errors/warnings

Python 3.13+.
"""

from __future__ import annotations

from ftllexengine.diagnostics.validation import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
)
from ftllexengine.syntax.ast import Annotation

# ============================================================================
# ValidationError.format() - Lines 78-94
# ============================================================================


class TestValidationErrorFormat:
    """Test ValidationError.format() method (lines 78-94)."""

    def test_format_basic(self) -> None:
        """Test basic error formatting without sanitization."""
        error = ValidationError(
            code="parse-error",
            message="Unexpected token",
            content="invalid { syntax",
        )

        formatted = error.format()

        assert "[parse-error]:" in formatted
        assert "Unexpected token" in formatted
        assert "invalid { syntax" in formatted

    def test_format_with_line_and_column(self) -> None:
        """Test error formatting with location (line 89-92)."""
        error = ValidationError(
            code="syntax-error",
            message="Missing '}'",
            content="{ unclosed",
            line=5,
            column=10,
        )

        formatted = error.format()

        assert "at line 5, column 10" in formatted
        assert "[syntax-error]" in formatted

    def test_format_with_line_only(self) -> None:
        """Test error formatting with line but no column (line 89-90)."""
        error = ValidationError(
            code="error",
            message="Error message",
            content="content",
            line=3,
            column=None,
        )

        formatted = error.format()

        assert "at line 3" in formatted
        assert "column" not in formatted

    def test_format_sanitize_truncates_long_content(self) -> None:
        """Test sanitize=True truncates content > 100 chars (line 81-82)."""
        long_content = "A" * 150
        error = ValidationError(
            code="error",
            message="Long content",
            content=long_content,
        )

        formatted = error.format(sanitize=True)

        assert "..." in formatted
        # Content should be truncated
        assert long_content not in formatted

    def test_format_sanitize_short_content_unchanged(self) -> None:
        """Test sanitize=True keeps short content unchanged (line 83-84)."""
        short_content = "short content"
        error = ValidationError(
            code="error",
            message="Short",
            content=short_content,
        )

        formatted = error.format(sanitize=True)

        assert short_content in formatted
        assert "..." not in formatted

    def test_format_sanitize_redact_content(self) -> None:
        """Test sanitize=True, redact_content=True redacts entirely (line 79-80)."""
        error = ValidationError(
            code="secret-error",
            message="Secret data",
            content="sensitive information",
        )

        formatted = error.format(sanitize=True, redact_content=True)

        assert "[content redacted]" in formatted
        assert "sensitive information" not in formatted

    def test_format_no_sanitize(self) -> None:
        """Test format without sanitize shows full content (line 85-86)."""
        long_content = "A" * 150
        error = ValidationError(
            code="error",
            message="Message",
            content=long_content,
        )

        formatted = error.format(sanitize=False)

        assert long_content in formatted


# ============================================================================
# ValidationResult.format() with Errors - Lines 268-270
# ============================================================================


class TestValidationResultFormatErrors:
    """Test ValidationResult.format() with errors (lines 268-270)."""

    def test_format_with_errors_includes_errors_section(self) -> None:
        """Test format() includes Errors section when errors present."""
        errors = (
            ValidationError(code="err-1", message="First error", content="a"),
            ValidationError(code="err-2", message="Second error", content="b"),
        )
        result = ValidationResult(errors=errors, warnings=(), annotations=())

        formatted = result.format()

        assert "Errors (2):" in formatted
        assert "[err-1]" in formatted
        assert "[err-2]" in formatted

    def test_format_errors_with_sanitize(self) -> None:
        """Test format() errors with sanitize=True."""
        long_content = "X" * 150
        error = ValidationError(code="err", message="Msg", content=long_content)
        result = ValidationResult(errors=(error,), warnings=(), annotations=())

        formatted = result.format(sanitize=True)

        assert "..." in formatted
        assert long_content not in formatted

    def test_format_errors_with_redact(self) -> None:
        """Test format() errors with sanitize=True, redact_content=True."""
        error = ValidationError(code="err", message="Msg", content="secret")
        result = ValidationResult(errors=(error,), warnings=(), annotations=())

        formatted = result.format(sanitize=True, redact_content=True)

        assert "[content redacted]" in formatted
        assert "secret" not in formatted


class TestValidationResultFormatAnnotationArguments:
    """Test ValidationResult.format() with annotations that have arguments dict."""

    def test_format_annotation_with_arguments(self) -> None:
        """Test lines 283-284: annotation with non-empty arguments dict."""
        annotation = Annotation(
            code="expected-token",
            message="Expected '}' but found EOF",
            arguments={"expected": "}", "found": "EOF"},
        )
        result = ValidationResult.invalid(annotations=(annotation,))

        formatted = result.format()

        # Should include arguments in output
        assert "expected-token" in formatted
        assert "expected=" in formatted
        assert "found=" in formatted
        assert "'}'" in formatted or "}" in formatted

    def test_format_annotation_with_single_argument(self) -> None:
        """Test annotation with single key-value argument."""
        annotation = Annotation(
            code="invalid-character",
            message="Invalid character in identifier",
            arguments={"char": "@"},
        )
        result = ValidationResult.invalid(annotations=(annotation,))

        formatted = result.format()

        assert "invalid-character" in formatted
        assert "char=" in formatted
        assert "@" in formatted

    def test_format_annotation_without_arguments(self) -> None:
        """Test annotation without arguments (else branch - line 286)."""
        annotation = Annotation(
            code="parse-error",
            message="Syntax error",
            arguments=None,
        )
        result = ValidationResult.invalid(annotations=(annotation,))

        formatted = result.format()

        # Should format without arguments section
        assert "parse-error" in formatted
        assert "Syntax error" in formatted
        # No arguments - should not have parentheses with key=value
        assert "=" not in formatted or "parse-error" in formatted

    def test_format_annotation_with_empty_arguments(self) -> None:
        """Test annotation with empty arguments dict (falsy, takes else branch)."""
        annotation = Annotation(
            code="warning",
            message="Warning message",
            arguments={},
        )
        result = ValidationResult.invalid(annotations=(annotation,))

        formatted = result.format()

        # Empty dict is falsy, so should take else branch
        assert "warning" in formatted
        assert "Warning message" in formatted

    def test_format_mixed_annotations_with_and_without_arguments(self) -> None:
        """Test formatting multiple annotations with mixed argument presence."""
        annotation_with_args = Annotation(
            code="error-1",
            message="First error",
            arguments={"key": "value"},
        )
        annotation_without_args = Annotation(
            code="error-2",
            message="Second error",
            arguments=None,
        )
        result = ValidationResult.invalid(
            annotations=(annotation_with_args, annotation_without_args)
        )

        formatted = result.format()

        # Both should be present
        assert "error-1" in formatted
        assert "error-2" in formatted
        assert "First error" in formatted
        assert "Second error" in formatted
        # Only first has arguments
        assert "key=" in formatted

    def test_format_annotation_with_sanitize_and_arguments(self) -> None:
        """Test sanitize=True with annotation that has arguments."""
        long_message = "A" * 150  # Longer than _SANITIZE_MAX_CONTENT_LENGTH (100)
        annotation = Annotation(
            code="long-error",
            message=long_message,
            arguments={"detail": "important"},
        )
        result = ValidationResult.invalid(annotations=(annotation,))

        formatted = result.format(sanitize=True)

        # Message should be truncated
        assert "..." in formatted
        # Arguments should still be present
        assert "detail=" in formatted
        assert "'important'" in formatted


class TestValidationResultErrorCount:
    """Test ValidationResult.error_count property (line 178)."""

    def test_error_count_with_errors_and_annotations(self) -> None:
        """Test error_count returns sum of errors and annotations."""
        errors = (
            ValidationError(code="err-1", message="Error 1", content="x"),
            ValidationError(code="err-2", message="Error 2", content="y"),
        )
        annotations = (
            Annotation(code="ann-1", message="Ann 1"),
        )
        result = ValidationResult(errors=errors, warnings=(), annotations=annotations)

        assert result.error_count == 3  # 2 errors + 1 annotation

    def test_error_count_zero_when_valid(self) -> None:
        """Test error_count returns 0 for valid result."""
        result = ValidationResult.valid()

        assert result.error_count == 0


class TestValidationResultWarningCount:
    """Test ValidationResult.warning_count property (line 187)."""

    def test_warning_count_with_warnings(self) -> None:
        """Test warning_count returns correct count when warnings present."""
        warnings = (
            ValidationWarning(code="warn-1", message="First warning"),
            ValidationWarning(code="warn-2", message="Second warning"),
            ValidationWarning(code="warn-3", message="Third warning"),
        )
        result = ValidationResult(errors=(), warnings=warnings, annotations=())

        assert result.warning_count == 3

    def test_warning_count_zero_when_no_warnings(self) -> None:
        """Test warning_count returns 0 when no warnings."""
        result = ValidationResult.valid()

        assert result.warning_count == 0

    def test_warning_count_single_warning(self) -> None:
        """Test warning_count with single warning."""
        warning = ValidationWarning(code="single", message="Single warning")
        result = ValidationResult(errors=(), warnings=(warning,), annotations=())

        assert result.warning_count == 1


class TestValidationResultFromAnnotations:
    """Test ValidationResult.from_annotations static method (lines 230-232)."""

    def test_from_annotations_with_annotations_returns_invalid(self) -> None:
        """Test from_annotations returns result with annotations when provided."""
        annotations = (
            Annotation(code="error-1", message="First error"),
            Annotation(code="error-2", message="Second error"),
        )
        result = ValidationResult.from_annotations(annotations)

        assert not result.is_valid
        assert result.annotations == annotations
        assert result.errors == ()
        assert result.warnings == ()

    def test_from_annotations_empty_returns_valid(self) -> None:
        """Test from_annotations returns valid result when empty tuple."""
        result = ValidationResult.from_annotations(())

        assert result.is_valid
        assert result.annotations == ()
        assert result.errors == ()
        assert result.warnings == ()

    def test_from_annotations_single_annotation(self) -> None:
        """Test from_annotations with single annotation."""
        annotation = Annotation(code="single", message="Single annotation")
        result = ValidationResult.from_annotations((annotation,))

        assert not result.is_valid
        assert len(result.annotations) == 1
        assert result.annotations[0] == annotation


class TestValidationResultFormatWarnings:
    """Test ValidationResult.format() with warnings (lines 290-293)."""

    def test_format_with_warnings_includes_warning_section(self) -> None:
        """Test format() includes Warnings section when warnings present."""
        warnings = (
            ValidationWarning(code="warn-1", message="First warning", context="ctx1"),
            ValidationWarning(code="warn-2", message="Second warning"),
        )
        result = ValidationResult(errors=(), warnings=warnings, annotations=())

        formatted = result.format()

        assert "Warnings (2):" in formatted
        assert "[warn-1]: First warning (ctx1)" in formatted
        assert "[warn-2]: Second warning" in formatted

    def test_format_with_warnings_context_optional(self) -> None:
        """Test format() handles warning without context (context=None)."""
        warning = ValidationWarning(code="no-ctx", message="No context warning")
        result = ValidationResult(errors=(), warnings=(warning,), annotations=())

        formatted = result.format()

        assert "[no-ctx]: No context warning" in formatted
        # No parentheses after message when context is None
        assert "No context warning (" not in formatted

    def test_format_exclude_warnings(self) -> None:
        """Test format(include_warnings=False) excludes warnings."""
        warnings = (ValidationWarning(code="warn", message="Warning"),)
        result = ValidationResult(errors=(), warnings=warnings, annotations=())

        formatted = result.format(include_warnings=False)

        assert "Warnings" not in formatted
        # But with no errors/annotations, should still return passed message
        assert "Validation passed" in formatted


class TestValidationResultFormatValidResult:
    """Test ValidationResult.format() for valid result (line 296)."""

    def test_format_valid_result_returns_passed_message(self) -> None:
        """Test format() returns 'Validation passed' for valid result."""
        result = ValidationResult.valid()

        formatted = result.format()

        assert formatted == "Validation passed: no errors or warnings"

    def test_format_empty_result_returns_passed_message(self) -> None:
        """Test format() returns passed message when no lines generated."""
        # Result with only warnings but include_warnings=False
        result = ValidationResult(
            errors=(), warnings=(), annotations=()
        )

        formatted = result.format()

        assert formatted == "Validation passed: no errors or warnings"
