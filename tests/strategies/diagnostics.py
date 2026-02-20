"""Hypothesis strategies for diagnostics domain testing.

Provides reusable, event-emitting strategies for generating diagnostic
data structures: SourceSpan, FrozenErrorContext, Diagnostic, ErrorCategory,
DiagnosticCode, ValidationError, ValidationWarning, ValidationResult,
DiagnosticFormatter, and FrozenFluentError.

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
    - diag_fmt_format: DiagnosticFormatter output format (rust|simple|json)
    - diag_fmt_sanitize: DiagnosticFormatter sanitize mode (off|truncate|redact)
    - diag_frozen_error_variant: FrozenFluentError variant (plain|with_diag|with_ctx|full)
"""

from __future__ import annotations

from typing import Literal

from hypothesis import event
from hypothesis import strategies as st

from ftllexengine.diagnostics.codes import (
    Diagnostic,
    DiagnosticCode,
    ErrorCategory,
    FrozenErrorContext,
    SourceSpan,
)
from ftllexengine.diagnostics.errors import FrozenFluentError
from ftllexengine.diagnostics.formatter import (
    DiagnosticFormatter,
    OutputFormat,
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

    Bucket-first: draws size category then generates matching span,
    ensuring uniform distribution across categories.

    Events emitted:
    - diag_span_size={zero|small|medium|large}: Span size classification
    """
    label = draw(
        st.sampled_from(["zero", "small", "medium", "large"])
    )
    start = draw(st.integers(min_value=0, max_value=100000))
    match label:
        case "zero":
            end = start
        case "small":
            offset = draw(st.integers(min_value=1, max_value=99))
            end = start + offset
        case "medium":
            offset = draw(
                st.integers(min_value=100, max_value=999)
            )
            end = start + offset
        case _:  # large
            offset = draw(
                st.integers(min_value=1000, max_value=10000)
            )
            end = start + offset
    line = draw(st.integers(min_value=1, max_value=10000))
    column = draw(st.integers(min_value=1, max_value=1000))
    event(f"diag_span_size={label}")
    return SourceSpan(start=start, end=end, line=line, column=column)


@st.composite
def frozen_error_contexts(draw: st.DrawFn) -> FrozenErrorContext:
    """Generate arbitrary FrozenErrorContext instances.

    Bucket-first: draws field population category then generates
    matching fields, ensuring uniform distribution.

    Events emitted:
    - diag_ctx_fields={none|partial|all}: How many fields are non-empty
    """
    label = draw(st.sampled_from(["none", "partial", "all"]))
    match label:
        case "none":
            input_value = ""
            locale_code = ""
            parse_type = ""
            fallback_value = ""
        case "all":
            input_value = draw(st.text(min_size=1, max_size=100))
            locale_code = draw(st.text(min_size=1, max_size=20))
            parse_type = draw(st.text(min_size=1, max_size=20))
            fallback_value = draw(
                st.text(min_size=1, max_size=100)
            )
        case _:  # partial: 1-3 non-empty fields
            # Draw which fields are non-empty (1-3 of 4)
            flags = draw(
                st.lists(
                    st.booleans(), min_size=4, max_size=4
                ).filter(lambda b: 0 < sum(b) < 4)
            )
            input_value = (
                draw(st.text(min_size=1, max_size=100))
                if flags[0]
                else ""
            )
            locale_code = (
                draw(st.text(min_size=1, max_size=20))
                if flags[1]
                else ""
            )
            parse_type = (
                draw(st.text(min_size=1, max_size=20))
                if flags[2]
                else ""
            )
            fallback_value = (
                draw(st.text(min_size=1, max_size=100))
                if flags[3]
                else ""
            )
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
    severity: Literal["error", "warning"] = draw(
        st.sampled_from(["error", "warning"])
    )
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
        severity=severity,
        resolution_path=resolution_path,
    )


@st.composite
def validation_errors(draw: st.DrawFn) -> ValidationError:
    """Generate arbitrary ValidationError instances.

    Events emitted:
    - diag_verr_location={with|without}: Whether location fields present
    """
    code = draw(st.sampled_from(list(DiagnosticCode)))
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
    code = draw(st.sampled_from(list(DiagnosticCode)))
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

    Bucket-first: draws validity category then generates matching
    data, ensuring 50/50 valid/invalid distribution.

    Events emitted:
    - diag_vresult_valid={True|False}: Whether result is valid
    """
    make_valid = draw(st.booleans())
    warnings = draw(
        st.lists(
            validation_warnings(), min_size=0, max_size=5
        ).map(tuple)
    )
    if make_valid:
        errors: tuple[ValidationError, ...] = ()
        annots: tuple[Annotation, ...] = ()
    else:
        errors = draw(
            st.lists(
                validation_errors(), min_size=0, max_size=5
            ).map(tuple)
        )
        annots = draw(
            st.lists(
                annotation_nodes(), min_size=0, max_size=5
            ).map(tuple)
        )
        # Ensure at least one error or annotation for invalid
        if not errors and not annots:
            errors = (draw(validation_errors()),)
    result = ValidationResult(
        errors=errors, warnings=warnings, annotations=annots
    )
    event(f"diag_vresult_valid={result.is_valid}")
    return result


@st.composite
def diagnostic_formatters(
    draw: st.DrawFn,
) -> DiagnosticFormatter:
    """Generate DiagnosticFormatter instances with varied configurations.

    Bucket-first: draws output format and sanitize mode independently,
    then generates matching formatter, ensuring uniform distribution
    across all configuration combinations.

    Events emitted:
    - diag_fmt_format={rust|simple|json}: Output format
    - diag_fmt_sanitize={off|truncate|redact}: Sanitize mode
    """
    fmt = draw(st.sampled_from(list(OutputFormat)))
    event(f"diag_fmt_format={fmt.value}")

    sanitize = draw(st.booleans())
    redact = draw(st.booleans()) if sanitize else False
    sanitize_label = (
        "redact" if redact else ("truncate" if sanitize else "off")
    )
    event(f"diag_fmt_sanitize={sanitize_label}")

    color = draw(st.booleans())
    max_len = draw(st.integers(min_value=10, max_value=500))

    return DiagnosticFormatter(
        output_format=fmt,
        sanitize=sanitize,
        redact_content=redact,
        color=color,
        max_content_length=max_len,
    )


@st.composite
def frozen_fluent_errors(
    draw: st.DrawFn,
) -> FrozenFluentError:
    """Generate FrozenFluentError instances with varied constructor combinations.

    Bucket-first: draws variant category then generates matching arguments,
    ensuring uniform distribution across all constructor parameter combinations.

    Events emitted:
    - diag_frozen_error_variant={plain|with_diag|with_ctx|full}: Constructor variant
    """
    message = draw(st.text(min_size=1, max_size=200))
    category = draw(error_categories())
    variant = draw(
        st.sampled_from(["plain", "with_diag", "with_ctx", "full"])
    )
    event(f"diag_frozen_error_variant={variant}")
    match variant:
        case "plain":
            return FrozenFluentError(message, category)
        case "with_diag":
            diag = draw(diagnostics())
            return FrozenFluentError(message, category, diagnostic=diag)
        case "with_ctx":
            ctx = draw(frozen_error_contexts())
            return FrozenFluentError(message, category, context=ctx)
        case _:  # full
            diag = draw(diagnostics())
            ctx = draw(frozen_error_contexts())
            return FrozenFluentError(
                message, category, diagnostic=diag, context=ctx
            )
