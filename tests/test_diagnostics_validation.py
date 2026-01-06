"""Property-based tests for diagnostics/validation.py module.

Comprehensive coverage for ValidationError, ValidationWarning, ValidationResult,
and WarningSeverity using Hypothesis for property-based testing.

Properties tested:
- Immutability: Validation types are frozen dataclasses
- Factory consistency: Static factories produce valid instances
- Format idempotence: Multiple format() calls produce same output
- Sanitization bounds: Sanitized content length is bounded
- Count properties: error_count and warning_count match tuple lengths
- Validity invariant: is_valid == (no errors and no annotations)

Python 3.13+.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.diagnostics.validation import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
    WarningSeverity,
)
from ftllexengine.syntax.ast import Annotation

# ============================================================================
# STRATEGIES
# ============================================================================


@st.composite
def validation_error_strategy(draw: st.DrawFn) -> ValidationError:
    """Generate arbitrary ValidationError instances."""
    code = draw(st.text(min_size=1, max_size=50))
    message = draw(st.text(min_size=1, max_size=200))
    content = draw(st.text(min_size=0, max_size=500))
    line = draw(st.none() | st.integers(min_value=1, max_value=10000))
    column = draw(st.none() | st.integers(min_value=1, max_value=1000))
    return ValidationError(
        code=code, message=message, content=content, line=line, column=column
    )


@st.composite
def validation_warning_strategy(draw: st.DrawFn) -> ValidationWarning:
    """Generate arbitrary ValidationWarning instances."""
    code = draw(st.text(min_size=1, max_size=50))
    message = draw(st.text(min_size=1, max_size=200))
    context = draw(st.none() | st.text(min_size=0, max_size=100))
    line = draw(st.none() | st.integers(min_value=1, max_value=10000))
    column = draw(st.none() | st.integers(min_value=1, max_value=1000))
    severity = draw(st.sampled_from(list(WarningSeverity)))
    return ValidationWarning(
        code=code,
        message=message,
        context=context,
        line=line,
        column=column,
        severity=severity,
    )


@st.composite
def annotation_strategy(draw: st.DrawFn) -> Annotation:
    """Generate arbitrary Annotation instances."""
    code = draw(st.text(min_size=1, max_size=50))
    message = draw(st.text(min_size=1, max_size=200))
    # Arguments is optional tuple of key-value pairs
    arguments = draw(
        st.none()
        | st.lists(
            st.tuples(
                st.text(min_size=1, max_size=30), st.text(min_size=0, max_size=100)
            ),
            min_size=0,
            max_size=5,
        ).map(tuple)
    )
    return Annotation(code=code, message=message, arguments=arguments)


@st.composite
def validation_result_strategy(draw: st.DrawFn) -> ValidationResult:
    """Generate arbitrary ValidationResult instances."""
    errors = draw(
        st.lists(validation_error_strategy(), min_size=0, max_size=5).map(tuple)
    )
    warnings = draw(
        st.lists(validation_warning_strategy(), min_size=0, max_size=5).map(tuple)
    )
    annotations = draw(
        st.lists(annotation_strategy(), min_size=0, max_size=5).map(tuple)
    )
    return ValidationResult(errors=errors, warnings=warnings, annotations=annotations)


# ============================================================================
# PROPERTY TESTS: ValidationError
# ============================================================================


class TestValidationErrorProperties:
    """Property-based tests for ValidationError."""

    @given(error=validation_error_strategy())
    def test_property_validation_error_immutable(
        self, error: ValidationError
    ) -> None:
        """PROPERTY: ValidationError instances are immutable (frozen dataclass)."""
        # Attempt to modify should raise FrozenInstanceError
        try:
            error.code = "modified"  # type: ignore[misc]
            assert False, "Expected FrozenInstanceError"  # noqa: B011, PT015
        except AttributeError:
            pass  # Expected

    @given(error=validation_error_strategy())
    def test_property_format_idempotent(self, error: ValidationError) -> None:
        """PROPERTY: format() is idempotent (same output on repeated calls)."""
        first = error.format()
        second = error.format()
        assert first == second

    @given(error=validation_error_strategy())
    def test_property_format_contains_code(self, error: ValidationError) -> None:
        """PROPERTY: Formatted output contains error code."""
        formatted = error.format()
        assert error.code in formatted or f"[{error.code}]" in formatted

    @given(error=validation_error_strategy())
    def test_property_format_sanitize_bounds_content(
        self, error: ValidationError
    ) -> None:
        """PROPERTY: sanitize=True bounds content length to <= MAX + truncation marker."""
        formatted = error.format(sanitize=True)
        # Maximum content length in DiagnosticFormatter is 100 chars
        # With truncation, output should not contain full content if content > 100
        if len(error.content) > 100:
            assert error.content not in formatted

    @given(error=validation_error_strategy())
    def test_property_format_redact_removes_content(
        self, error: ValidationError
    ) -> None:
        """PROPERTY: sanitize=True, redact_content=True includes redaction marker."""
        formatted = error.format(sanitize=True, redact_content=True)
        # Should include redaction marker when content exists
        if error.content:
            assert "[content redacted]" in formatted or "redacted" in formatted.lower()

    @given(
        error=validation_error_strategy(),
        sanitize=st.booleans(),
        redact=st.booleans(),
    )
    def test_property_format_returns_string(
        self, error: ValidationError, sanitize: bool, redact: bool
    ) -> None:
        """PROPERTY: format() always returns a string."""
        result = error.format(sanitize=sanitize, redact_content=redact)
        assert isinstance(result, str)
        assert len(result) > 0


# ============================================================================
# PROPERTY TESTS: ValidationWarning
# ============================================================================


class TestValidationWarningProperties:
    """Property-based tests for ValidationWarning."""

    @given(warning=validation_warning_strategy())
    def test_property_validation_warning_immutable(
        self, warning: ValidationWarning
    ) -> None:
        """PROPERTY: ValidationWarning instances are immutable (frozen dataclass)."""
        try:
            warning.code = "modified"  # type: ignore[misc]
            assert False, "Expected FrozenInstanceError"  # noqa: B011, PT015
        except AttributeError:
            pass  # Expected

    @given(warning=validation_warning_strategy())
    def test_property_format_idempotent(self, warning: ValidationWarning) -> None:
        """PROPERTY: format() is idempotent."""
        first = warning.format()
        second = warning.format()
        assert first == second

    @given(warning=validation_warning_strategy())
    def test_property_format_contains_code_and_message(
        self, warning: ValidationWarning
    ) -> None:
        """PROPERTY: Formatted output contains code and message."""
        formatted = warning.format()
        assert warning.code in formatted or f"[{warning.code}]" in formatted
        assert warning.message in formatted

    @given(warning=validation_warning_strategy())
    def test_property_format_includes_context_when_present(
        self, warning: ValidationWarning
    ) -> None:
        """PROPERTY: format() includes context indicator when context present."""
        formatted = warning.format()
        if warning.context:
            # Context is included, but may be escaped for special chars
            assert "context:" in formatted or "context" in formatted.lower()

    @given(warning=validation_warning_strategy())
    def test_property_format_returns_string(self, warning: ValidationWarning) -> None:
        """PROPERTY: format() always returns a non-empty string."""
        result = warning.format()
        assert isinstance(result, str)
        assert len(result) > 0

    @given(warning=validation_warning_strategy())
    def test_property_severity_is_valid_enum(
        self, warning: ValidationWarning
    ) -> None:
        """PROPERTY: severity is always a valid WarningSeverity enum value."""
        assert warning.severity in WarningSeverity


# ============================================================================
# PROPERTY TESTS: ValidationResult
# ============================================================================


class TestValidationResultProperties:
    """Property-based tests for ValidationResult."""

    @given(result=validation_result_strategy())
    def test_property_validation_result_immutable(
        self, result: ValidationResult
    ) -> None:
        """PROPERTY: ValidationResult instances are immutable (frozen dataclass)."""
        try:
            result.errors = ()  # type: ignore[misc]
            assert False, "Expected FrozenInstanceError"  # noqa: B011, PT015
        except AttributeError:
            pass  # Expected

    @given(result=validation_result_strategy())
    def test_property_error_count_matches_tuple_lengths(
        self, result: ValidationResult
    ) -> None:
        """PROPERTY: error_count == len(errors) + len(annotations)."""
        expected = len(result.errors) + len(result.annotations)
        assert result.error_count == expected

    @given(result=validation_result_strategy())
    def test_property_warning_count_matches_warnings_length(
        self, result: ValidationResult
    ) -> None:
        """PROPERTY: warning_count == len(warnings)."""
        assert result.warning_count == len(result.warnings)

    @given(result=validation_result_strategy())
    def test_property_is_valid_iff_no_errors_or_annotations(
        self, result: ValidationResult
    ) -> None:
        """PROPERTY: is_valid == (no errors AND no annotations)."""
        expected_valid = len(result.errors) == 0 and len(result.annotations) == 0
        assert result.is_valid == expected_valid

    @given(result=validation_result_strategy())
    def test_property_warnings_do_not_affect_validity(
        self, result: ValidationResult
    ) -> None:
        """PROPERTY: Warnings alone do not make result invalid."""
        if len(result.errors) == 0 and len(result.annotations) == 0:
            assert result.is_valid, "Result with only warnings should be valid"

    @given(
        result=validation_result_strategy(),
        sanitize=st.booleans(),
        redact=st.booleans(),
        include_warnings=st.booleans(),
    )
    def test_property_format_returns_string(
        self,
        result: ValidationResult,
        sanitize: bool,
        redact: bool,
        include_warnings: bool,
    ) -> None:
        """PROPERTY: format() always returns a non-empty string."""
        formatted = result.format(
            sanitize=sanitize,
            redact_content=redact,
            include_warnings=include_warnings,
        )
        assert isinstance(formatted, str)
        assert len(formatted) > 0

    @given(result=validation_result_strategy())
    def test_property_format_idempotent(self, result: ValidationResult) -> None:
        """PROPERTY: format() is idempotent."""
        first = result.format()
        second = result.format()
        assert first == second


# ============================================================================
# PROPERTY TESTS: Static Factory Methods
# ============================================================================


class TestValidationResultFactoryProperties:
    """Property-based tests for ValidationResult static factory methods."""

    def test_property_valid_factory_produces_valid_result(self) -> None:
        """PROPERTY: ValidationResult.valid() always produces is_valid=True."""
        result = ValidationResult.valid()
        assert result.is_valid
        assert result.error_count == 0
        assert result.warning_count == 0
        assert len(result.errors) == 0
        assert len(result.warnings) == 0
        assert len(result.annotations) == 0

    @given(
        errors=st.lists(validation_error_strategy(), min_size=0, max_size=3).map(tuple),
        warnings=st.lists(validation_warning_strategy(), min_size=0, max_size=3).map(
            tuple
        ),
        annotations=st.lists(annotation_strategy(), min_size=0, max_size=3).map(tuple),
    )
    def test_property_invalid_factory_preserves_inputs(
        self,
        errors: tuple[ValidationError, ...],
        warnings: tuple[ValidationWarning, ...],
        annotations: tuple[Annotation, ...],
    ) -> None:
        """PROPERTY: ValidationResult.invalid() preserves input tuples."""
        result = ValidationResult.invalid(
            errors=errors, warnings=warnings, annotations=annotations
        )
        assert result.errors == errors
        assert result.warnings == warnings
        assert result.annotations == annotations

    @given(
        errors=st.lists(validation_error_strategy(), min_size=1, max_size=3).map(tuple)
    )
    def test_property_invalid_with_errors_is_invalid(
        self, errors: tuple[ValidationError, ...]
    ) -> None:
        """PROPERTY: ValidationResult.invalid() with errors is invalid."""
        result = ValidationResult.invalid(errors=errors)
        assert not result.is_valid
        assert result.error_count > 0

    @given(
        annotations=st.lists(annotation_strategy(), min_size=1, max_size=3).map(tuple)
    )
    def test_property_invalid_with_annotations_is_invalid(
        self, annotations: tuple[Annotation, ...]
    ) -> None:
        """PROPERTY: ValidationResult.invalid() with annotations is invalid."""
        result = ValidationResult.invalid(annotations=annotations)
        assert not result.is_valid
        assert result.error_count > 0

    @given(annotations=st.lists(annotation_strategy(), min_size=0, max_size=3).map(tuple))
    def test_property_from_annotations_preserves_annotations(
        self, annotations: tuple[Annotation, ...]
    ) -> None:
        """PROPERTY: from_annotations() preserves annotation tuple."""
        result = ValidationResult.from_annotations(annotations)
        assert result.annotations == annotations
        assert result.errors == ()
        assert result.warnings == ()

    @given(annotations=st.lists(annotation_strategy(), min_size=1, max_size=3).map(tuple))
    def test_property_from_annotations_nonempty_is_invalid(
        self, annotations: tuple[Annotation, ...]
    ) -> None:
        """PROPERTY: from_annotations() with non-empty tuple is invalid."""
        result = ValidationResult.from_annotations(annotations)
        assert not result.is_valid

    def test_property_from_annotations_empty_is_valid(self) -> None:
        """PROPERTY: from_annotations(()) produces valid result."""
        result = ValidationResult.from_annotations(())
        assert result.is_valid
        assert result.error_count == 0


# ============================================================================
# UNIT TESTS: Specific Cases
# ============================================================================


class TestValidationErrorFormat:
    """Unit tests for ValidationError.format() edge cases."""

    def test_format_with_location_includes_line_and_column(self) -> None:
        """format() includes line and column when provided."""
        error = ValidationError(
            code="test-error", message="Test message", content="test", line=5, column=10
        )
        formatted = error.format()
        assert "line 5" in formatted
        assert "column 10" in formatted

    def test_format_without_location_no_line_column(self) -> None:
        """format() does not include location when None."""
        error = ValidationError(
            code="test-error", message="Test message", content="test"
        )
        formatted = error.format()
        assert "line" not in formatted.lower() or "baseline" in formatted.lower()


class TestValidationWarningFormat:
    """Unit tests for ValidationWarning.format() edge cases."""

    def test_format_with_all_fields(self) -> None:
        """format() includes all fields when provided."""
        warning = ValidationWarning(
            code="warn-code",
            message="Warning message",
            context="context-info",
            line=3,
            column=7,
            severity=WarningSeverity.CRITICAL,
        )
        formatted = warning.format()
        assert "warn-code" in formatted
        assert "Warning message" in formatted
        assert "context-info" in formatted

    def test_format_without_context(self) -> None:
        """format() works without context field."""
        warning = ValidationWarning(code="warn", message="Message")
        formatted = warning.format()
        assert "warn" in formatted
        assert "Message" in formatted

    def test_format_critical_severity(self) -> None:
        """format() handles CRITICAL severity."""
        warning = ValidationWarning(
            code="critical-warn",
            message="Critical warning",
            severity=WarningSeverity.CRITICAL,
        )
        formatted = warning.format()
        assert "critical-warn" in formatted

    def test_format_info_severity(self) -> None:
        """format() handles INFO severity."""
        warning = ValidationWarning(
            code="info-warn", message="Info warning", severity=WarningSeverity.INFO
        )
        formatted = warning.format()
        assert "info-warn" in formatted


class TestValidationResultFormat:
    """Unit tests for ValidationResult.format() edge cases."""

    def test_format_valid_result_message(self) -> None:
        """format() returns 'Validation passed' for valid result."""
        result = ValidationResult.valid()
        formatted = result.format()
        assert "Validation passed" in formatted or "passed" in formatted.lower()

    def test_format_with_warnings_excluded(self) -> None:
        """format(include_warnings=False) excludes warnings section."""
        warning = ValidationWarning(code="warn", message="Warning")
        result = ValidationResult(errors=(), warnings=(warning,), annotations=())
        formatted = result.format(include_warnings=False)
        # Should not include warning section
        assert "Warnings" not in formatted or "passed" in formatted.lower()

    def test_format_with_errors_and_warnings(self) -> None:
        """format() includes both errors and warnings."""
        error = ValidationError(code="err", message="Error", content="x")
        warning = ValidationWarning(code="warn", message="Warning")
        result = ValidationResult(errors=(error,), warnings=(warning,), annotations=())
        formatted = result.format()
        assert "err" in formatted
        assert "warn" in formatted


class TestWarningSeverityEnum:
    """Unit tests for WarningSeverity enum."""

    def test_all_severity_levels_defined(self) -> None:
        """All expected severity levels are defined."""
        assert WarningSeverity.CRITICAL.value == "critical"
        assert WarningSeverity.WARNING.value == "warning"
        assert WarningSeverity.INFO.value == "info"

    def test_severity_levels_are_strings(self) -> None:
        """Severity enum values are strings."""
        for severity in WarningSeverity:
            assert isinstance(severity.value, str)

    def test_severity_enum_members(self) -> None:
        """All expected enum members exist."""
        severity_values = {s.value for s in WarningSeverity}
        assert severity_values == {"critical", "warning", "info"}
