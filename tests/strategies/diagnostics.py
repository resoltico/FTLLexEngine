"""Hypothesis strategies for diagnostics domain testing.

Provides reusable, event-emitting strategies for generating diagnostic
data structures: SourceSpan, FrozenErrorContext, Diagnostic, ErrorCategory,
DiagnosticCode, ValidationError, ValidationWarning, and ValidationResult.

Event-Emitting Strategies (HypoFuzz-Optimized):
    These strategies emit hypothesis.event() calls for coverage-guided fuzzing:
    - diag_span_size: SourceSpan size classification (zero|small|medium|large)
    - diag_ctx_fields: FrozenErrorContext field population (none|partial|all)
    - diag_severity: Diagnostic severity level (error|warning)
    - diag_has_span: Whether Diagnostic has SourceSpan (true|false)
    - diag_code_range: DiagnosticCode range classification
    - diag_error_cat: ErrorCategory variant
    - diag_verr_location: ValidationError location presence
    - diag_vwarn_severity: ValidationWarning severity level
    - diag_vresult_valid: ValidationResult validity
"""

from __future__ import annotations

from hypothesis import event
from hypothesis import strategies as st

from ftllexengine.diagnostics.codes import (
    Diagnostic,
    DiagnosticCode,
    ErrorCategory,
    FrozenErrorContext,
    SourceSpan,
)
from ftllexengine.diagnostics.validation import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
    WarningSeverity,
)
from ftllexengine.syntax.ast import Annotation


@st.composite
def source_spans(draw: st.DrawFn) -> SourceSpan:
    """Generate arbitrary SourceSpan instances.

    Events emitted:
    - diag_span_size={zero|small|medium|large}: Span size classification
    """
    start = draw(st.integers(min_value=0, max_value=100000))
    end = draw(st.integers(min_value=start, max_value=start + 10000))
    line = draw(st.integers(min_value=1, max_value=10000))
    column = draw(st.integers(min_value=1, max_value=1000))
    span_size = end - start
    if span_size == 0:
        label = "zero"
    elif span_size < 100:
        label = "small"
    elif span_size < 1000:
        label = "medium"
    else:
        label = "large"
    event(f"diag_span_size={label}")
    return SourceSpan(start=start, end=end, line=line, column=column)


@st.composite
def frozen_error_contexts(draw: st.DrawFn) -> FrozenErrorContext:
    """Generate arbitrary FrozenErrorContext instances.

    Events emitted:
    - diag_ctx_fields={none|partial|all}: How many fields are non-empty
    """
    input_value = draw(st.text(min_size=0, max_size=100))
    locale_code = draw(st.text(min_size=0, max_size=20))
    parse_type = draw(st.text(min_size=0, max_size=20))
    fallback_value = draw(st.text(min_size=0, max_size=100))
    non_empty = sum(
        1 for v in (input_value, locale_code, parse_type, fallback_value) if v
    )
    if non_empty == 0:
        label = "none"
    elif non_empty == 4:
        label = "all"
    else:
        label = "partial"
    event(f"diag_ctx_fields={label}")
    return FrozenErrorContext(
        input_value=input_value,
        locale_code=locale_code,
        parse_type=parse_type,
        fallback_value=fallback_value,
    )


@st.composite
def error_categories(draw: st.DrawFn) -> ErrorCategory:
    """Generate arbitrary ErrorCategory enum values.

    Events emitted:
    - diag_error_cat={category}: The selected error category
    """
    category = draw(st.sampled_from(list(ErrorCategory)))
    event(f"diag_error_cat={category.value}")
    return category


@st.composite
def diagnostic_codes(draw: st.DrawFn) -> DiagnosticCode:
    """Generate arbitrary DiagnosticCode enum values.

    Events emitted:
    - diag_code_range={range}: Code range classification
    """
    code = draw(st.sampled_from(list(DiagnosticCode)))
    if code.value < 2000:
        label = "reference"
    elif code.value < 3000:
        label = "resolution"
    elif code.value < 4000:
        label = "syntax"
    elif code.value < 5000:
        label = "parsing"
    else:
        label = "validation"
    event(f"diag_code_range={label}")
    return code


@st.composite
def diagnostics(draw: st.DrawFn) -> Diagnostic:
    """Generate arbitrary Diagnostic instances with all field combinations.

    Events emitted:
    - diag_severity={error|warning}: Diagnostic severity
    - diag_has_span={true|false}: Whether span is present
    """
    code = draw(st.sampled_from(list(DiagnosticCode)))
    message = draw(st.text(min_size=1, max_size=200))
    span = draw(st.none() | source_spans())
    hint = draw(st.none() | st.text(min_size=1, max_size=100))
    help_url = draw(st.none() | st.text(min_size=1, max_size=100))
    function_name = draw(
        st.none() | st.text(min_size=1, max_size=50)
    )
    argument_name = draw(
        st.none() | st.text(min_size=1, max_size=50)
    )
    expected_type = draw(
        st.none() | st.text(min_size=1, max_size=50)
    )
    received_type = draw(
        st.none() | st.text(min_size=1, max_size=50)
    )
    ftl_location = draw(
        st.none() | st.text(min_size=1, max_size=100)
    )
    severity = draw(st.sampled_from(["error", "warning"]))
    resolution_path = draw(
        st.none()
        | st.lists(
            st.text(min_size=1, max_size=30), min_size=1, max_size=10
        ).map(tuple)
    )
    event(f"diag_severity={severity}")
    has_span = span is not None
    event(f"diag_has_span={has_span}")
    return Diagnostic(
        code=code,
        message=message,
        span=span,
        hint=hint,
        help_url=help_url,
        function_name=function_name,
        argument_name=argument_name,
        expected_type=expected_type,
        received_type=received_type,
        ftl_location=ftl_location,
        severity=severity,  # type: ignore[arg-type]
        resolution_path=resolution_path,
    )


@st.composite
def validation_errors(draw: st.DrawFn) -> ValidationError:
    """Generate arbitrary ValidationError instances.

    Events emitted:
    - diag_verr_location={with|without}: Whether location fields present
    """
    code = draw(st.text(min_size=1, max_size=50))
    message = draw(st.text(min_size=1, max_size=200))
    content = draw(st.text(min_size=0, max_size=500))
    line = draw(st.none() | st.integers(min_value=1, max_value=10000))
    column = draw(
        st.none() | st.integers(min_value=1, max_value=1000)
    )
    has_loc = line is not None
    event(f"diag_verr_location={'with' if has_loc else 'without'}")
    return ValidationError(
        code=code,
        message=message,
        content=content,
        line=line,
        column=column,
    )


@st.composite
def validation_warnings(draw: st.DrawFn) -> ValidationWarning:
    """Generate arbitrary ValidationWarning instances.

    Events emitted:
    - diag_vwarn_severity={critical|warning|info}: Warning severity
    """
    code = draw(st.text(min_size=1, max_size=50))
    message = draw(st.text(min_size=1, max_size=200))
    context = draw(st.none() | st.text(min_size=0, max_size=100))
    line = draw(st.none() | st.integers(min_value=1, max_value=10000))
    column = draw(
        st.none() | st.integers(min_value=1, max_value=1000)
    )
    severity = draw(st.sampled_from(list(WarningSeverity)))
    event(f"diag_vwarn_severity={severity.value}")
    return ValidationWarning(
        code=code,
        message=message,
        context=context,
        line=line,
        column=column,
        severity=severity,
    )


@st.composite
def annotation_nodes(draw: st.DrawFn) -> Annotation:
    """Generate arbitrary Annotation instances."""
    code = draw(st.text(min_size=1, max_size=50))
    message = draw(st.text(min_size=1, max_size=200))
    arguments = draw(
        st.none()
        | st.lists(
            st.tuples(
                st.text(min_size=1, max_size=30),
                st.text(min_size=0, max_size=100),
            ),
            min_size=0,
            max_size=5,
        ).map(tuple)
    )
    return Annotation(code=code, message=message, arguments=arguments)


@st.composite
def validation_results(draw: st.DrawFn) -> ValidationResult:
    """Generate arbitrary ValidationResult instances.

    Events emitted:
    - diag_vresult_valid={true|false}: Whether result is valid
    """
    errors = draw(
        st.lists(validation_errors(), min_size=0, max_size=5).map(tuple)
    )
    warnings = draw(
        st.lists(validation_warnings(), min_size=0, max_size=5).map(tuple)
    )
    annots = draw(
        st.lists(annotation_nodes(), min_size=0, max_size=5).map(tuple)
    )
    result = ValidationResult(
        errors=errors, warnings=warnings, annotations=annots
    )
    is_valid = result.is_valid
    event(f"diag_vresult_valid={is_valid}")
    return result
