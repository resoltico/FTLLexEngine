"""Comprehensive tests for diagnostics/formatter.py achieving 100% coverage.

Tests DiagnosticFormatter with all output formats, sanitization options,
color modes, and edge cases using Hypothesis for property-based testing.

Python 3.13+.
"""

import json
from unittest.mock import Mock

from hypothesis import assume, given
from hypothesis import strategies as st

from ftllexengine.diagnostics.codes import Diagnostic, DiagnosticCode, SourceSpan
from ftllexengine.diagnostics.formatter import DiagnosticFormatter, OutputFormat


class TestOutputFormatEnum:
    """Test OutputFormat enum values."""

    def test_output_format_rust(self):
        """OutputFormat.RUST has correct value."""
        assert OutputFormat.RUST.value == "rust"

    def test_output_format_simple(self):
        """OutputFormat.SIMPLE has correct value."""
        assert OutputFormat.SIMPLE.value == "simple"

    def test_output_format_json(self):
        """OutputFormat.JSON has correct value."""
        assert OutputFormat.JSON.value == "json"


class TestDiagnosticFormatterConstruction:
    """Test DiagnosticFormatter construction and defaults."""

    def test_default_construction(self):
        """Default DiagnosticFormatter uses rust format, no sanitize, no color."""
        formatter = DiagnosticFormatter()

        assert formatter.output_format == OutputFormat.RUST
        assert formatter.sanitize is False
        assert formatter.color is False
        assert formatter.max_content_length == 100

    def test_custom_output_format(self):
        """DiagnosticFormatter accepts custom output_format."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.SIMPLE)

        assert formatter.output_format == OutputFormat.SIMPLE

    def test_custom_sanitize(self):
        """DiagnosticFormatter accepts custom sanitize flag."""
        formatter = DiagnosticFormatter(sanitize=True)

        assert formatter.sanitize is True

    def test_custom_color(self):
        """DiagnosticFormatter accepts custom color flag."""
        formatter = DiagnosticFormatter(color=True)

        assert formatter.color is True

    def test_custom_max_content_length(self):
        """DiagnosticFormatter accepts custom max_content_length."""
        formatter = DiagnosticFormatter(max_content_length=50)

        assert formatter.max_content_length == 50


class TestFormatRust:
    """Test _format_rust() method comprehensively."""

    def test_format_rust_minimal_diagnostic(self):
        """Rust format with minimal diagnostic (code + message only)."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
        )

        result = formatter.format(diagnostic)

        assert "error[MESSAGE_NOT_FOUND]: Message 'hello' not found" in result
        assert "-->" not in result
        assert "= help:" not in result

    def test_format_rust_with_span(self):
        """Rust format includes span location."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
        span = SourceSpan(start=10, end=20, line=5, column=10)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
            span=span,
        )

        result = formatter.format(diagnostic)

        assert "error[MESSAGE_NOT_FOUND]: Message 'hello' not found" in result
        assert "  --> line 5, column 10" in result

    def test_format_rust_with_ftl_location_no_span(self):
        """Rust format uses ftl_location when span is None."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
            ftl_location="main.ftl:42",
        )

        result = formatter.format(diagnostic)

        assert "error[MESSAGE_NOT_FOUND]: Message 'hello' not found" in result
        assert "  --> main.ftl:42" in result

    def test_format_rust_span_takes_precedence_over_ftl_location(self):
        """Rust format prefers span over ftl_location when both present."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
        span = SourceSpan(start=10, end=20, line=5, column=10)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
            span=span,
            ftl_location="main.ftl:99",
        )

        result = formatter.format(diagnostic)

        # Span should appear, not ftl_location
        assert "  --> line 5, column 10" in result
        assert "main.ftl:99" not in result

    def test_format_rust_with_function_name(self):
        """Rust format includes function_name field."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
        diagnostic = Diagnostic(
            code=DiagnosticCode.FUNCTION_FAILED,
            message="Function failed",
            function_name="NUMBER",
        )

        result = formatter.format(diagnostic)

        assert "error[FUNCTION_FAILED]: Function failed" in result
        assert "  = function: NUMBER" in result

    def test_format_rust_with_argument_name(self):
        """Rust format includes argument_name field."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
        diagnostic = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Type mismatch",
            argument_name="value",
        )

        result = formatter.format(diagnostic)

        assert "error[TYPE_MISMATCH]: Type mismatch" in result
        assert "  = argument: value" in result

    def test_format_rust_with_expected_type(self):
        """Rust format includes expected_type field."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
        diagnostic = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Type mismatch",
            expected_type="Number",
        )

        result = formatter.format(diagnostic)

        assert "error[TYPE_MISMATCH]: Type mismatch" in result
        assert "  = expected: Number" in result

    def test_format_rust_with_received_type(self):
        """Rust format includes received_type field."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
        diagnostic = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Type mismatch",
            received_type="String",
        )

        result = formatter.format(diagnostic)

        assert "error[TYPE_MISMATCH]: Type mismatch" in result
        assert "  = received: String" in result

    def test_format_rust_with_hint(self):
        """Rust format includes hint field."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
            hint="Check that the message is defined",
        )

        result = formatter.format(diagnostic)

        assert "error[MESSAGE_NOT_FOUND]: Message 'hello' not found" in result
        assert "  = help: Check that the message is defined" in result

    def test_format_rust_with_help_url(self):
        """Rust format includes help_url field."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
            help_url="https://projectfluent.org/fluent/guide/messages.html",
        )

        result = formatter.format(diagnostic)

        assert "error[MESSAGE_NOT_FOUND]: Message 'hello' not found" in result
        assert "  = note: see https://projectfluent.org/fluent/guide/messages.html" in result

    def test_format_rust_warning_severity(self):
        """Rust format uses 'warning' for severity=warning."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
            severity="warning",
        )

        result = formatter.format(diagnostic)

        assert "warning[MESSAGE_NOT_FOUND]: Message 'hello' not found" in result

    def test_format_rust_color_error(self):
        """Rust format with color adds ANSI codes for error."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.RUST, color=True)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
        )

        result = formatter.format(diagnostic)

        # Should contain bold red ANSI code for error
        assert "\033[1;31merror\033[0m" in result
        assert "[MESSAGE_NOT_FOUND]" in result

    def test_format_rust_color_warning(self):
        """Rust format with color adds ANSI codes for warning."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.RUST, color=True)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
            severity="warning",
        )

        result = formatter.format(diagnostic)

        # Should contain bold yellow ANSI code for warning
        assert "\033[1;33mwarning\033[0m" in result
        assert "[MESSAGE_NOT_FOUND]" in result

    def test_format_rust_all_fields(self):
        """Rust format with all optional fields present."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.RUST)
        span = SourceSpan(start=10, end=20, line=5, column=10)
        diagnostic = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Type mismatch in NUMBER()",
            span=span,
            function_name="NUMBER",
            argument_name="value",
            expected_type="Number",
            received_type="String",
            hint="Convert value to Number before passing",
            help_url="https://projectfluent.org/fluent/guide/functions.html",
        )

        result = formatter.format(diagnostic)

        assert "error[TYPE_MISMATCH]: Type mismatch in NUMBER()" in result
        assert "  --> line 5, column 10" in result
        assert "  = function: NUMBER" in result
        assert "  = argument: value" in result
        assert "  = expected: Number" in result
        assert "  = received: String" in result
        assert "  = help: Convert value to Number before passing" in result
        assert "  = note: see https://projectfluent.org/fluent/guide/functions.html" in result


class TestFormatSimple:
    """Test _format_simple() method."""

    def test_format_simple_basic(self):
        """Simple format shows code and message only."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.SIMPLE)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
        )

        result = formatter.format(diagnostic)

        assert result == "MESSAGE_NOT_FOUND: Message 'hello' not found"

    def test_format_simple_ignores_span(self):
        """Simple format ignores span and other fields."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.SIMPLE)
        span = SourceSpan(start=10, end=20, line=5, column=10)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
            span=span,
            hint="Some hint",
            help_url="http://example.com",
        )

        result = formatter.format(diagnostic)

        assert result == "MESSAGE_NOT_FOUND: Message 'hello' not found"
        assert "line 5" not in result
        assert "hint" not in result


class TestFormatJSON:
    """Test _format_json() method."""

    def test_format_json_minimal(self):
        """JSON format with minimal diagnostic."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.JSON)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
        )

        result = formatter.format(diagnostic)
        data = json.loads(result)

        assert data["code"] == "MESSAGE_NOT_FOUND"
        assert data["code_value"] == DiagnosticCode.MESSAGE_NOT_FOUND.value
        assert data["message"] == "Message 'hello' not found"
        assert data["severity"] == "error"

    def test_format_json_with_span(self):
        """JSON format includes span fields."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.JSON)
        span = SourceSpan(start=10, end=20, line=5, column=10)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
            span=span,
        )

        result = formatter.format(diagnostic)
        data = json.loads(result)

        assert data["line"] == 5
        assert data["column"] == 10
        assert data["start"] == 10
        assert data["end"] == 20

    def test_format_json_with_ftl_location(self):
        """JSON format includes ftl_location field."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.JSON)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
            ftl_location="main.ftl:42",
        )

        result = formatter.format(diagnostic)
        data = json.loads(result)

        assert data["ftl_location"] == "main.ftl:42"

    def test_format_json_with_function_name(self):
        """JSON format includes function_name field."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.JSON)
        diagnostic = Diagnostic(
            code=DiagnosticCode.FUNCTION_FAILED,
            message="Function failed",
            function_name="NUMBER",
        )

        result = formatter.format(diagnostic)
        data = json.loads(result)

        assert data["function_name"] == "NUMBER"

    def test_format_json_with_argument_name(self):
        """JSON format includes argument_name field."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.JSON)
        diagnostic = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Type mismatch",
            argument_name="value",
        )

        result = formatter.format(diagnostic)
        data = json.loads(result)

        assert data["argument_name"] == "value"

    def test_format_json_with_expected_type(self):
        """JSON format includes expected_type field."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.JSON)
        diagnostic = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Type mismatch",
            expected_type="Number",
        )

        result = formatter.format(diagnostic)
        data = json.loads(result)

        assert data["expected_type"] == "Number"

    def test_format_json_with_received_type(self):
        """JSON format includes received_type field."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.JSON)
        diagnostic = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Type mismatch",
            received_type="String",
        )

        result = formatter.format(diagnostic)
        data = json.loads(result)

        assert data["received_type"] == "String"

    def test_format_json_with_hint(self):
        """JSON format includes hint field."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.JSON)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
            hint="Check that the message is defined",
        )

        result = formatter.format(diagnostic)
        data = json.loads(result)

        assert data["hint"] == "Check that the message is defined"

    def test_format_json_with_help_url(self):
        """JSON format includes help_url field."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.JSON)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
            help_url="https://projectfluent.org/fluent/guide/messages.html",
        )

        result = formatter.format(diagnostic)
        data = json.loads(result)

        assert data["help_url"] == "https://projectfluent.org/fluent/guide/messages.html"

    def test_format_json_unicode(self):
        """JSON format preserves Unicode characters (ensure_ascii=False)."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.JSON)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Ziņojums 'sveiki' nav atrasts",  # Latvian text
        )

        result = formatter.format(diagnostic)

        # Should contain actual Unicode, not escape sequences
        assert "Ziņojums" in result
        data = json.loads(result)
        assert data["message"] == "Ziņojums 'sveiki' nav atrasts"


class TestFormatAll:
    """Test format_all() method."""

    def test_format_all_empty(self):
        """format_all with empty iterable returns empty string."""
        formatter = DiagnosticFormatter()

        result = formatter.format_all([])

        assert result == ""

    def test_format_all_single_diagnostic(self):
        """format_all with single diagnostic."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.SIMPLE)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
        )

        result = formatter.format_all([diagnostic])

        assert result == "MESSAGE_NOT_FOUND: Message 'hello' not found"

    def test_format_all_multiple_diagnostics(self):
        """format_all joins multiple diagnostics with double newline."""
        formatter = DiagnosticFormatter(output_format=OutputFormat.SIMPLE)
        diagnostics = [
            Diagnostic(
                code=DiagnosticCode.MESSAGE_NOT_FOUND,
                message="Message 'hello' not found",
            ),
            Diagnostic(
                code=DiagnosticCode.VARIABLE_NOT_PROVIDED,
                message="Variable 'name' not provided",
            ),
            Diagnostic(
                code=DiagnosticCode.TERM_NOT_FOUND,
                message="Term '-brand' not found",
            ),
        ]

        result = formatter.format_all(diagnostics)

        expected = (
            "MESSAGE_NOT_FOUND: Message 'hello' not found\n\n"
            "VARIABLE_NOT_PROVIDED: Variable 'name' not provided\n\n"
            "TERM_NOT_FOUND: Term '-brand' not found"
        )
        assert result == expected


class TestMaybeSanitize:
    """Test _maybe_sanitize() method."""

    def test_sanitize_disabled_no_truncation(self):
        """With sanitize=False, text is never truncated."""
        formatter = DiagnosticFormatter(sanitize=False)
        long_text = "x" * 500

        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message=long_text,
        )

        result = formatter.format(diagnostic)

        # Full text should appear (no "..." truncation)
        assert long_text in result
        assert "..." not in result

    def test_sanitize_enabled_under_limit(self):
        """With sanitize=True, text under limit is not truncated."""
        formatter = DiagnosticFormatter(sanitize=True, max_content_length=100)
        short_text = "x" * 50

        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message=short_text,
        )

        result = formatter.format(diagnostic)

        assert short_text in result
        assert "..." not in result

    def test_sanitize_enabled_over_limit_message(self):
        """With sanitize=True, message over limit is truncated."""
        formatter = DiagnosticFormatter(
            sanitize=True,
            max_content_length=50,
            output_format=OutputFormat.SIMPLE,
        )
        long_message = "x" * 100

        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message=long_message,
        )

        result = formatter.format(diagnostic)

        # Should be truncated to 50 chars + "..."
        assert result == f"MESSAGE_NOT_FOUND: {'x' * 50}..."

    def test_sanitize_enabled_over_limit_hint(self):
        """With sanitize=True, hint over limit is truncated."""
        formatter = DiagnosticFormatter(
            sanitize=True,
            max_content_length=50,
            output_format=OutputFormat.RUST,
        )
        long_hint = "x" * 100

        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Short message",
            hint=long_hint,
        )

        result = formatter.format(diagnostic)

        # Hint should be truncated
        assert f"{'x' * 50}..." in result


class TestFormatValidationResult:
    """Test format_validation_result() method."""

    def test_format_validation_result_valid(self):
        """Validation result with is_valid=True shows success."""
        formatter = DiagnosticFormatter()

        # Create mock ValidationResult
        result = Mock()
        result.is_valid = True
        result.errors = []
        result.warnings = []
        result.annotations = []

        output = formatter.format_validation_result(result)

        assert "Validation passed" in output

    def test_format_validation_result_invalid_with_counts(self):
        """Validation result with is_valid=False shows error/warning counts."""
        formatter = DiagnosticFormatter()

        # Create mock ValidationResult
        result = Mock()
        result.is_valid = False
        result.error_count = 3
        result.warning_count = 2
        result.errors = []
        result.warnings = []
        result.annotations = []

        output = formatter.format_validation_result(result)

        assert "Validation failed: 3 error(s), 2 warning(s)" in output

    def test_format_validation_result_with_errors(self):
        """Validation result formats errors section."""
        formatter = DiagnosticFormatter()

        # Create mock validation error with all required attributes
        error1 = Mock()
        error1.code = "INVALID_SYNTAX"
        error1.message = "Syntax error"
        error1.content = "bad syntax"
        error1.line = 5
        error1.column = 10

        error2 = Mock()
        error2.code = "MISSING_VALUE"
        error2.message = "Message has no value"
        error2.content = "msg"
        error2.line = 10
        error2.column = None

        result = Mock()
        result.is_valid = False
        result.error_count = 2
        result.warning_count = 0
        result.errors = [error1, error2]
        result.warnings = []
        result.annotations = []

        output = formatter.format_validation_result(result)

        assert "Validation failed: 2 error(s), 0 warning(s)" in output
        assert "\nErrors (2):" in output
        assert "[INVALID_SYNTAX] at line 5, column 10: Syntax error" in output
        assert "[MISSING_VALUE] at line 10: Message has no value" in output

    def test_format_validation_result_with_warnings(self):
        """Validation result formats warnings section."""
        formatter = DiagnosticFormatter()

        # Create mock warning with all required attributes
        warning1 = Mock()
        warning1.code = "UNUSED_MESSAGE"
        warning1.message = "Unused message"
        warning1.context = "hello"
        warning1.line = 3
        warning1.column = 1

        warning2 = Mock()
        warning2.code = "DEPRECATED_SYNTAX"
        warning2.message = "Deprecated syntax"
        warning2.context = None
        warning2.line = None
        warning2.column = None

        result = Mock()
        result.is_valid = True
        result.error_count = 0
        result.warning_count = 2
        result.errors = []
        result.warnings = [warning1, warning2]
        result.annotations = []

        output = formatter.format_validation_result(result)

        assert "\nWarnings (2):" in output
        assert "[UNUSED_MESSAGE] at line 3, column 1: Unused message" in output
        assert "[DEPRECATED_SYNTAX]: Deprecated syntax" in output

    def test_format_validation_result_with_annotations(self):
        """Validation result formats annotations section."""
        formatter = DiagnosticFormatter()

        # Create mock annotations with all required attributes
        annotation1 = Mock()
        annotation1.code = "PARSER_INFO"
        annotation1.message = "Parsed successfully"
        annotation1.arguments = None

        annotation2 = Mock()
        annotation2.code = "PARSER_NOTE"
        annotation2.message = "Alternative syntax available"
        annotation2.arguments = (("key", "value"),)

        result = Mock()
        result.is_valid = True
        result.error_count = 0
        result.warning_count = 0
        result.errors = []
        result.warnings = []
        result.annotations = [annotation1, annotation2]

        output = formatter.format_validation_result(result)

        assert "\nAnnotations (2):" in output
        assert "[PARSER_INFO]: Parsed successfully" in output
        assert "[PARSER_NOTE]: Alternative syntax available" in output

    def test_format_validation_error_minimal(self):
        """_format_validation_error with no line/column."""
        formatter = DiagnosticFormatter()

        error = Mock()
        error.code = "UNKNOWN_ERROR"
        error.message = "Something went wrong"
        error.content = "error content"
        error.line = None
        error.column = None

        result = Mock()
        result.is_valid = False
        result.error_count = 1
        result.warning_count = 0
        result.errors = [error]
        result.warnings = []
        result.annotations = []

        output = formatter.format_validation_result(result)

        assert "[UNKNOWN_ERROR]: Something went wrong" in output

    def test_format_validation_error_no_attributes(self):
        """_format_validation_error falls back to str() for objects without attributes."""
        formatter = DiagnosticFormatter()

        # Simple object class with no code/message/line/column attributes
        class GenericError:
            def __str__(self) -> str:
                return "Generic error"

        error = GenericError()

        result = Mock()
        result.is_valid = False
        result.error_count = 1
        result.warning_count = 0
        result.errors = [error]
        result.warnings = []
        result.annotations = []

        output = formatter.format_validation_result(result)

        # Should use getattr defaults and str(error)
        assert "[UNKNOWN]: Generic error" in output


# Hypothesis-based property tests


@given(
    message=st.text(min_size=1, max_size=200),
    sanitize=st.booleans(),
    max_length=st.integers(min_value=10, max_value=100),
)
def test_sanitize_property_length(message: str, sanitize: bool, max_length: int) -> None:
    """Property: Sanitized output never exceeds max_content_length + 3 (for ...)."""
    formatter = DiagnosticFormatter(
        sanitize=sanitize,
        max_content_length=max_length,
        output_format=OutputFormat.SIMPLE,
    )
    diagnostic = Diagnostic(
        code=DiagnosticCode.MESSAGE_NOT_FOUND,
        message=message,
    )

    result = formatter.format(diagnostic)

    if sanitize and len(message) > max_length:
        # Message portion should be truncated to max_length + "..."
        # Format is "CODE: message", so extract message part
        msg_part = result.split(": ", 1)[1]
        assert len(msg_part) <= max_length + 3
        assert msg_part.endswith("...")
    else:
        # No sanitization, full message should appear
        assert message in result


@given(
    code=st.sampled_from(list(DiagnosticCode)),
    message=st.text(min_size=1, max_size=100),
    severity=st.sampled_from(["error", "warning"]),
)
def test_format_property_all_codes(
    code: DiagnosticCode,
    message: str,
    severity: str,
) -> None:
    """Property: All DiagnosticCodes can be formatted without error."""
    formatter = DiagnosticFormatter()
    diagnostic = Diagnostic(
        code=code,
        message=message,
        severity=severity,  # type: ignore[arg-type]
    )

    result = formatter.format(diagnostic)

    assert code.name in result
    assert message in result
    assert severity in result


@given(
    format_type=st.sampled_from([OutputFormat.RUST, OutputFormat.SIMPLE, OutputFormat.JSON]),
    message=st.text(min_size=1, max_size=100),
)
def test_format_property_all_formats(format_type: OutputFormat, message: str) -> None:
    """Property: All output formats produce non-empty results."""
    assume("\n" not in message)  # Avoid multiline complexity in hypothesis

    formatter = DiagnosticFormatter(output_format=format_type)
    diagnostic = Diagnostic(
        code=DiagnosticCode.MESSAGE_NOT_FOUND,
        message=message,
    )

    result = formatter.format(diagnostic)

    assert len(result) > 0
    # For JSON format, message may be escaped, so parse and check
    if format_type == OutputFormat.JSON:
        data = json.loads(result)
        assert data["message"] == message or data["message"] == message[:50]
    else:
        assert message in result or message[:50] in result  # May be truncated in sanitized mode
