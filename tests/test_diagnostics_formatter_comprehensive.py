"""Property-based tests for diagnostics/formatter.py.

Tests DiagnosticFormatter across all output formats, sanitization modes,
color options, and validation result formatting using Hypothesis strategies
and real domain types. No Mocks.

Python 3.13+.
"""

import json

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.diagnostics.codes import (
    Diagnostic,
    DiagnosticCode,
    SourceSpan,
)
from ftllexengine.diagnostics.formatter import (
    DiagnosticFormatter,
    OutputFormat,
)
from ftllexengine.diagnostics.validation import (
    ValidationError,
    ValidationResult,
    ValidationWarning,
)
from ftllexengine.syntax.ast import Annotation
from tests.strategies.diagnostics import (
    diagnostic_formatters,
    diagnostics,
    validation_errors,
    validation_results,
    validation_warnings,
)

# ---------------------------------------------------------------------------
# Text generation helpers (no control chars for predictable assertions)
# ---------------------------------------------------------------------------

_safe_text = st.text(
    st.characters(
        categories=("L", "N", "P", "S", "Z"),
        exclude_characters="\x00",
    ),
    min_size=1,
    max_size=200,
)

_safe_short_text = st.text(
    st.characters(
        categories=("L", "N", "P", "S", "Z"),
        exclude_characters="\x00",
    ),
    min_size=1,
    max_size=50,
)


# ===================================================================
# Property: format() dispatches to all three output format methods
# ===================================================================


@given(diagnostic=diagnostics(), formatter=diagnostic_formatters())
def test_format_dispatches_all_formats(
    diagnostic: Diagnostic,
    formatter: DiagnosticFormatter,
) -> None:
    """format() produces non-empty output for every format x diagnostic."""
    result = formatter.format(diagnostic)
    assert isinstance(result, str)
    assert len(result) > 0
    event(f"format={formatter.output_format.value}")
    event(f"severity={diagnostic.severity}")


# ===================================================================
# Property: code name always appears in output
# ===================================================================


@given(diagnostic=diagnostics(), formatter=diagnostic_formatters())
def test_code_name_present_in_output(
    diagnostic: Diagnostic,
    formatter: DiagnosticFormatter,
) -> None:
    """Every formatted diagnostic contains its DiagnosticCode name."""
    result = formatter.format(diagnostic)
    assert diagnostic.code.name in result
    event(f"format={formatter.output_format.value}")


# ===================================================================
# Property: Rust format structure
# ===================================================================


@given(diagnostic=diagnostics())
def test_rust_format_structure(diagnostic: Diagnostic) -> None:
    """Rust format starts with severity[CODE]: message."""
    formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
    result = formatter.format(diagnostic)
    first_line = result.split("\n")[0]

    expected_sev = (
        "warning" if diagnostic.severity == "warning" else "error"
    )
    assert first_line.startswith(f"{expected_sev}[{diagnostic.code.name}]")
    event(f"severity={diagnostic.severity}")

    has_span = diagnostic.span is not None
    has_loc = diagnostic.ftl_location is not None
    if has_span:
        assert "  --> line " in result
        event("location=span")
    elif has_loc:
        assert "  --> " in result
        event("location=ftl_location")
    else:
        assert "  --> " not in result
        event("location=none")


# ===================================================================
# Property: Rust format optional fields
# ===================================================================


@given(diagnostic=diagnostics())
def test_rust_format_optional_fields(diagnostic: Diagnostic) -> None:
    """Rust format includes optional fields only when set."""
    formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
    result = formatter.format(diagnostic)

    field_count = 0
    if diagnostic.function_name:
        assert "  = function: " in result
        field_count += 1
    if diagnostic.argument_name:
        assert "  = argument: " in result
        field_count += 1
    if diagnostic.expected_type:
        assert "  = expected: " in result
        field_count += 1
    if diagnostic.received_type:
        assert "  = received: " in result
        field_count += 1
    if diagnostic.hint:
        assert "  = help: " in result
        field_count += 1
    if diagnostic.help_url:
        assert "  = note: see " in result
        field_count += 1
    event(f"optional_field_count={min(field_count, 3)}")


# ===================================================================
# Property: Color mode adds ANSI codes
# ===================================================================


@given(
    diagnostic=diagnostics(),
    color=st.booleans(),
)
def test_rust_color_ansi_codes(
    diagnostic: Diagnostic,
    color: bool,
) -> None:
    """Color mode adds ANSI escape codes; non-color mode omits them."""
    formatter = DiagnosticFormatter(
        output_format=OutputFormat.RUST,
        color=color,
    )
    result = formatter.format(diagnostic)

    if color:
        assert "\033[" in result
        if diagnostic.severity == "warning":
            assert "\033[1;33m" in result
        else:
            assert "\033[1;31m" in result
    else:
        assert "\033[" not in result
    event(f"color={color}")
    event(f"severity={diagnostic.severity}")


# ===================================================================
# Property: Simple format is single-line CODE: message
# ===================================================================


@given(diagnostic=diagnostics())
def test_simple_format_single_line(diagnostic: Diagnostic) -> None:
    """Simple format is CODE: escaped_message (no embedded newlines)."""
    formatter = DiagnosticFormatter(output_format=OutputFormat.SIMPLE)
    result = formatter.format(diagnostic)

    # No raw newlines (escaped \n is fine)
    assert "\n" not in result
    assert result.startswith(f"{diagnostic.code.name}: ")
    event(f"msg_len={'long' if len(diagnostic.message) > 100 else 'short'}")


# ===================================================================
# Property: JSON format is valid JSON with required keys
# ===================================================================


@given(diagnostic=diagnostics())
def test_json_format_valid_json(diagnostic: Diagnostic) -> None:
    """JSON format produces valid JSON with required fields."""
    formatter = DiagnosticFormatter(output_format=OutputFormat.JSON)
    result = formatter.format(diagnostic)
    data = json.loads(result)

    assert data["code"] == diagnostic.code.name
    assert data["code_value"] == diagnostic.code.value
    assert data["severity"] == diagnostic.severity

    span = diagnostic.span
    has_span = span is not None
    if span is not None:
        assert data["line"] == span.line
        assert data["column"] == span.column
        assert data["start"] == span.start
        assert data["end"] == span.end
    event(f"json_has_span={has_span}")


# ===================================================================
# Property: JSON optional fields mirror diagnostic fields
# ===================================================================


@given(diagnostic=diagnostics())
def test_json_format_optional_fields(diagnostic: Diagnostic) -> None:
    """JSON format includes optional fields when set on diagnostic."""
    formatter = DiagnosticFormatter(output_format=OutputFormat.JSON)
    data = json.loads(formatter.format(diagnostic))

    optional_present = 0
    if diagnostic.ftl_location:
        assert data["ftl_location"] == diagnostic.ftl_location
        optional_present += 1
    if diagnostic.function_name:
        assert data["function_name"] == diagnostic.function_name
        optional_present += 1
    if diagnostic.argument_name:
        assert data["argument_name"] == diagnostic.argument_name
        optional_present += 1
    if diagnostic.expected_type:
        assert data["expected_type"] == diagnostic.expected_type
        optional_present += 1
    if diagnostic.received_type:
        assert data["received_type"] == diagnostic.received_type
        optional_present += 1
    if diagnostic.hint:
        assert "hint" in data
        optional_present += 1
    if diagnostic.help_url:
        assert data["help_url"] == diagnostic.help_url
        optional_present += 1
    event(f"json_optional_count={min(optional_present, 4)}")


# ===================================================================
# Property: JSON preserves Unicode (ensure_ascii=False)
# ===================================================================


@given(
    message=st.text(
        st.characters(categories=("L", "N")),
        min_size=1,
        max_size=50,
    ),
)
def test_json_unicode_preservation(message: str) -> None:
    """JSON format preserves non-ASCII characters without escaping."""
    formatter = DiagnosticFormatter(output_format=OutputFormat.JSON)
    diagnostic = Diagnostic(
        code=DiagnosticCode.MESSAGE_NOT_FOUND,
        message=message,
    )
    data = json.loads(formatter.format(diagnostic))
    assert data["message"] == message
    has_non_ascii = any(ord(c) > 127 for c in message)
    event(f"has_non_ascii={has_non_ascii}")


# ===================================================================
# Property: format_all joins with double newline
# ===================================================================


@given(
    diag_list=st.lists(diagnostics(), min_size=0, max_size=5),
)
def test_format_all_double_newline_join(
    diag_list: list[Diagnostic],
) -> None:
    """format_all joins diagnostics with double newlines."""
    formatter = DiagnosticFormatter(output_format=OutputFormat.SIMPLE)
    result = formatter.format_all(diag_list)

    if not diag_list:
        assert result == ""
    else:
        parts = result.split("\n\n")
        assert len(parts) == len(diag_list)
    event(f"list_size={len(diag_list)}")


# ===================================================================
# Property: Sanitization truncation bound (_maybe_sanitize)
# ===================================================================


@given(
    message=st.text(min_size=1, max_size=300),
    max_length=st.integers(min_value=10, max_value=100),
)
def test_sanitize_truncation_bound(
    message: str,
    max_length: int,
) -> None:
    """Sanitized message never exceeds max_content_length + 3."""
    formatter = DiagnosticFormatter(
        sanitize=True,
        max_content_length=max_length,
        output_format=OutputFormat.SIMPLE,
    )
    diagnostic = Diagnostic(
        code=DiagnosticCode.MESSAGE_NOT_FOUND,
        message=message,
    )
    result = formatter.format(diagnostic)
    msg_part = result.split(": ", 1)[1]

    truncated = len(message) > max_length
    if truncated:
        # After truncation + escape: bound is 2*(max_length) + 3
        # because control chars (\n -> \\n) can double each char.
        assert len(msg_part) <= 2 * max_length + 3
        assert msg_part.endswith("...")
    event(f"truncated={truncated}")


# ===================================================================
# Property: _escape_control_chars escapes \n, \r, \t
# ===================================================================


@given(
    text=st.text(
        st.characters(categories=("L", "Cc")),
        min_size=0,
        max_size=100,
    ),
)
def test_escape_control_chars_no_raw_controls(text: str) -> None:
    """Escaped text contains no raw newlines, returns, or tabs."""
    escaped = DiagnosticFormatter._escape_control_chars(text)
    assert "\n" not in escaped
    assert "\r" not in escaped
    assert "\t" not in escaped
    has_controls = "\n" in text or "\r" in text or "\t" in text
    event(f"had_controls={has_controls}")


# ===================================================================
# Property: format_error with real ValidationError types
# ===================================================================


@given(error=validation_errors())
def test_format_error_with_real_types(error: ValidationError) -> None:
    """format_error handles real ValidationError instances."""
    formatter = DiagnosticFormatter()
    result = formatter.format_error(error)

    assert f"[{error.code}]" in result
    assert error.message in result

    has_line = error.line is not None
    has_col = error.column is not None
    if has_line:
        assert f"at line {error.line}" in result
        if has_col:
            assert f"column {error.column}" in result
    event(f"error_location={'line_col' if has_col else ('line' if has_line else 'none')}")


# ===================================================================
# Property: format_error with line but no column
# ===================================================================


@given(
    code=_safe_short_text,
    message=_safe_short_text,
    content=_safe_short_text,
    line=st.integers(min_value=1, max_value=10000),
)
def test_format_error_line_no_column(
    code: str,
    message: str,
    content: str,
    line: int,
) -> None:
    """format_error shows line without column when column is None."""
    error = ValidationError(
        code=code, message=message, content=content,
        line=line, column=None,
    )
    formatter = DiagnosticFormatter()
    result = formatter.format_error(error)
    assert f"at line {line}" in result
    assert ", column " not in result
    event("outcome=line_no_column")


# ===================================================================
# Property: format_warning with real ValidationWarning types
# ===================================================================


@given(warning=validation_warnings())
def test_format_warning_with_real_types(
    warning: ValidationWarning,
) -> None:
    """format_warning handles real ValidationWarning instances."""
    formatter = DiagnosticFormatter()
    result = formatter.format_warning(warning)

    assert f"[{warning.code}]" in result
    assert warning.message in result

    has_line = warning.line is not None
    has_col = warning.column is not None
    if has_line:
        assert f"at line {warning.line}" in result
        if has_col:
            assert f"column {warning.column}" in result
    if warning.context:
        assert f"(context: {warning.context!r})" in result
    event(f"warning_location={'line_col' if has_col else ('line' if has_line else 'none')}")


# ===================================================================
# Property: format_warning with line but no column (branch 216->220)
# ===================================================================


@given(
    code=_safe_short_text,
    message=_safe_short_text,
    line=st.integers(min_value=1, max_value=10000),
    context=st.none() | _safe_short_text,
)
def test_format_warning_line_no_column(
    code: str,
    message: str,
    line: int,
    context: str | None,
) -> None:
    """format_warning with line set and column None (branch coverage)."""
    warning = ValidationWarning(
        code=code, message=message,
        line=line, column=None, context=context,
    )
    formatter = DiagnosticFormatter()
    result = formatter.format_warning(warning)
    assert f"at line {line}" in result
    assert ", column " not in result.split(":")[0]
    has_ctx = context is not None and len(context) > 0
    event(f"has_context={has_ctx}")


# ===================================================================
# Property: _maybe_sanitize_content with redact mode (lines 394-400)
# ===================================================================


@given(
    content=st.text(min_size=1, max_size=300),
    max_length=st.integers(min_value=10, max_value=100),
)
def test_sanitize_content_redact(
    content: str,
    max_length: int,
) -> None:
    """redact_content=True replaces content with redaction marker."""
    formatter = DiagnosticFormatter(
        sanitize=True,
        redact_content=True,
        max_content_length=max_length,
    )
    result = formatter._maybe_sanitize_content(content)
    assert result == "[content redacted]"
    event("outcome=redacted")


@given(
    content=st.text(min_size=1, max_size=300),
    max_length=st.integers(min_value=10, max_value=100),
)
def test_sanitize_content_truncate(
    content: str,
    max_length: int,
) -> None:
    """sanitize=True truncates content when over max_content_length."""
    formatter = DiagnosticFormatter(
        sanitize=True,
        redact_content=False,
        max_content_length=max_length,
    )
    result = formatter._maybe_sanitize_content(content)

    if len(content) > max_length:
        assert result == content[:max_length] + "..."
        event("outcome=truncated")
    else:
        assert result == content
        event("outcome=passthrough")


@given(content=st.text(min_size=1, max_size=300))
def test_sanitize_content_disabled(content: str) -> None:
    """sanitize=False returns content unchanged."""
    formatter = DiagnosticFormatter(sanitize=False)
    result = formatter._maybe_sanitize_content(content)
    assert result == content
    event("outcome=not_sanitized")


# ===================================================================
# Property: format_error with content shows sanitized content
# ===================================================================


@given(
    code=_safe_short_text,
    message=_safe_short_text,
    content=st.text(min_size=1, max_size=300),
    redact=st.booleans(),
)
def test_format_error_content_sanitization(
    code: str,
    message: str,
    content: str,
    redact: bool,
) -> None:
    """format_error applies content sanitization through format_error."""
    formatter = DiagnosticFormatter(
        sanitize=True,
        redact_content=redact,
        max_content_length=20,
    )
    error = ValidationError(
        code=code, message=message, content=content,
    )
    result = formatter.format_error(error)

    if redact:
        assert "[content redacted]" in result
        event("outcome=redacted")
    elif len(content) > 20:
        assert "..." in result
        event("outcome=truncated")
    else:
        event("outcome=passthrough")


# ===================================================================
# Property: _format_annotation with real Annotation types
# ===================================================================


@given(
    code=_safe_short_text,
    message=_safe_text,
    has_args=st.booleans(),
)
def test_format_annotation_real_types(
    code: str,
    message: str,
    has_args: bool,
) -> None:
    """_format_annotation with real Annotation objects."""
    args = (("key", "val"),) if has_args else None
    annotation = Annotation(code=code, message=message, arguments=args)

    formatter = DiagnosticFormatter()
    result = formatter._format_annotation(annotation)
    assert f"[{code}]" in result
    if has_args:
        assert "key=" in result
    event(f"has_args={has_args}")


# ===================================================================
# Property: format_validation_result with real ValidationResult
# ===================================================================


@given(vr=validation_results())
def test_format_validation_result_real_types(
    vr: ValidationResult,
) -> None:
    """format_validation_result with real ValidationResult."""
    formatter = DiagnosticFormatter()
    result = formatter.format_validation_result(vr)

    if vr.is_valid and not vr.warnings:
        assert "Validation passed: no errors or warnings" in result
        event("outcome=valid_clean")
    elif vr.is_valid:
        assert "Validation passed with" in result
        event("outcome=valid_with_warnings")
    else:
        assert "Validation failed:" in result
        event("outcome=invalid")


# ===================================================================
# Property: format_validation_result include_warnings=False
# ===================================================================


@given(vr=validation_results())
def test_format_validation_result_exclude_warnings(
    vr: ValidationResult,
) -> None:
    """include_warnings=False suppresses warning section."""
    formatter = DiagnosticFormatter()
    result = formatter.format_validation_result(
        vr, include_warnings=False,
    )
    assert "Warnings (" not in result
    event(f"had_warnings={len(vr.warnings) > 0}")


# ===================================================================
# Property: format_validation_result errors section
# ===================================================================


@given(vr=validation_results())
def test_format_validation_result_errors_section(
    vr: ValidationResult,
) -> None:
    """Errors section appears when errors present."""
    formatter = DiagnosticFormatter()
    result = formatter.format_validation_result(vr)

    if vr.errors:
        assert f"Errors ({len(vr.errors)}):" in result
        for err in vr.errors:
            assert f"[{err.code}]" in result
    event(f"error_count={min(len(vr.errors), 3)}")


# ===================================================================
# Property: format_validation_result annotations section
# ===================================================================


@given(vr=validation_results())
def test_format_validation_result_annotations_section(
    vr: ValidationResult,
) -> None:
    """Annotations section appears when annotations present."""
    formatter = DiagnosticFormatter()
    result = formatter.format_validation_result(vr)

    if vr.annotations:
        assert f"Annotations ({len(vr.annotations)}):" in result
        for ann in vr.annotations:
            assert f"[{ann.code}]" in result
    event(f"annotation_count={min(len(vr.annotations), 3)}")


# ===================================================================
# Property: All DiagnosticCodes format without error
# ===================================================================


@given(
    code=st.sampled_from(list(DiagnosticCode)),
    message=st.text(min_size=1, max_size=100),
    fmt=st.sampled_from(list(OutputFormat)),
)
def test_all_codes_all_formats(
    code: DiagnosticCode,
    message: str,
    fmt: OutputFormat,
) -> None:
    """Every DiagnosticCode x OutputFormat pair formats cleanly."""
    formatter = DiagnosticFormatter(output_format=fmt)
    diagnostic = Diagnostic(code=code, message=message)
    result = formatter.format(diagnostic)
    assert code.name in result
    event(f"format={fmt.value}")

    if code.value < 2000:
        event("code_range=reference")
    elif code.value < 3000:
        event("code_range=resolution")
    else:
        event("code_range=other")


# ===================================================================
# Property: Span takes precedence over ftl_location
# ===================================================================


@given(
    message=_safe_short_text,
    span_line=st.integers(min_value=1, max_value=9999),
    span_col=st.integers(min_value=1, max_value=999),
    ftl_loc=_safe_short_text,
)
def test_span_precedence_over_ftl_location(
    message: str,
    span_line: int,
    span_col: int,
    ftl_loc: str,
) -> None:
    """When both span and ftl_location are set, span wins."""
    diagnostic = Diagnostic(
        code=DiagnosticCode.MESSAGE_NOT_FOUND,
        message=message,
        span=SourceSpan(start=0, end=10, line=span_line, column=span_col),
        ftl_location=ftl_loc,
    )
    formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
    result = formatter.format(diagnostic)
    assert f"line {span_line}" in result
    event("outcome=span_wins")


# ===================================================================
# Property: format_error with object lacking content attribute
# ===================================================================


@given(
    message=_safe_short_text,
    line=st.none() | st.integers(min_value=1, max_value=10000),
    column=st.none() | st.integers(min_value=1, max_value=1000),
)
def test_format_error_no_content_attribute(
    message: str,
    line: int | None,
    column: int | None,
) -> None:
    """format_error with object lacking 'content' attribute (duck typing)."""

    class _MinimalError:
        """Error-like object without content field."""

        def __init__(
            self, msg: str, ln: int | None, col: int | None,
        ) -> None:
            self.code = "DUCK_TYPE"
            self.message = msg
            self.line = ln
            self.column = col

        def __str__(self) -> str:
            return self.message

    obj = _MinimalError(message, line, column)
    formatter = DiagnosticFormatter()
    result = formatter.format_error(obj)
    assert "[DUCK_TYPE]" in result
    assert "(content:" not in result
    has_line = line is not None
    event(f"duck_type_line={has_line}")


# ===================================================================
# Property: format_warning with duck-typed object (branch 226-230)
# ===================================================================


@given(
    message=_safe_short_text,
    line=st.none() | st.integers(min_value=1, max_value=10000),
    column=st.none() | st.integers(min_value=1, max_value=1000),
    context=st.none() | _safe_short_text,
)
def test_format_warning_duck_typed(
    message: str,
    line: int | None,
    column: int | None,
    context: str | None,
) -> None:
    """format_warning with non-ValidationWarning duck-typed object."""

    class _MinimalWarning:
        """Warning-like object for duck typing path."""

        def __init__(
            self, msg: str, ln: int | None, col: int | None,
            ctx: str | None,
        ) -> None:
            self.code = "DUCK_WARN"
            self.message = msg
            self.line = ln
            self.column = col
            self.context = ctx

        def __str__(self) -> str:
            return self.message

    obj = _MinimalWarning(message, line, column, context)
    formatter = DiagnosticFormatter()
    result = formatter.format_warning(obj)
    assert "[DUCK_WARN]" in result
    has_line = line is not None
    event(f"duck_warn_line={has_line}")


# ===================================================================
# OutputFormat StrEnum membership
# ===================================================================


def test_output_format_is_str_enum() -> None:
    """OutputFormat values are strings usable as dict keys."""
    for fmt in OutputFormat:
        assert isinstance(fmt, str)
        assert fmt.value == str(fmt)


# ===================================================================
# DiagnosticFormatter frozen immutability
# ===================================================================


def test_formatter_frozen() -> None:
    """DiagnosticFormatter is immutable (frozen dataclass)."""
    formatter = DiagnosticFormatter()
    with pytest.raises(AttributeError):
        formatter.sanitize = True  # type: ignore[misc]
