"""Tests for Phase 4: Rich Diagnostics - Enhanced error objects."""

from ftllexengine.diagnostics import (
    DiagnosticCode,
    ErrorTemplate,
    FluentError,
    FluentResolutionError,
)


class TestDiagnosticEnhancements:
    """Test enhanced Diagnostic class with format-specific fields."""

    def test_diagnostic_with_function_context(self) -> None:
        """Diagnostic includes function name and argument details."""
        diagnostic = ErrorTemplate.type_mismatch(
            function_name="NUMBER",
            argument_name="value",
            expected_type="Number",
            received_type="String",
        )

        assert diagnostic.code == DiagnosticCode.TYPE_MISMATCH
        assert diagnostic.function_name == "NUMBER"
        assert diagnostic.argument_name == "value"
        assert diagnostic.expected_type == "Number"
        assert diagnostic.received_type == "String"

    def test_diagnostic_with_ftl_location(self) -> None:
        """Diagnostic includes FTL file location."""
        diagnostic = ErrorTemplate.type_mismatch(
            function_name="DATETIME",
            argument_name="date",
            expected_type="DateTime",
            received_type="String",
            ftl_location="ui.ftl:509",
        )

        assert diagnostic.ftl_location == "ui.ftl:509"

    def test_diagnostic_severity_error(self) -> None:
        """Diagnostic has error severity by default."""
        diagnostic = ErrorTemplate.invalid_argument(
            function_name="NUMBER",
            argument_name="minimumFractionDigits",
            reason="Must be non-negative",
        )

        assert diagnostic.severity == "error"

    def test_diagnostic_severity_warning(self) -> None:
        """Diagnostic can have warning severity."""
        diagnostic = ErrorTemplate.pattern_invalid(
            function_name="NUMBER",
            pattern="#,##0.00",
            reason="Syntax error",
        )

        assert diagnostic.severity == "error"


class TestEnhancedErrorFormatting:
    """Test enhanced error message formatting with rich context."""

    def test_format_error_with_function_context(self) -> None:
        """Format error includes function name and argument details."""
        diagnostic = ErrorTemplate.type_mismatch(
            function_name="NUMBER",
            argument_name="value",
            expected_type="Number",
            received_type="String",
        )

        formatted = diagnostic.format_error()

        assert "error[TYPE_MISMATCH]" in formatted
        assert "= function: NUMBER" in formatted
        assert "= argument: value" in formatted
        assert "= expected: Number" in formatted
        assert "= received: String" in formatted

    def test_format_error_with_ftl_location(self) -> None:
        """Format error includes FTL file location."""
        diagnostic = ErrorTemplate.type_mismatch(
            function_name="DATETIME",
            argument_name="date",
            expected_type="DateTime",
            received_type="String",
            ftl_location="messages.ftl:42",
        )

        formatted = diagnostic.format_error()

        assert "messages.ftl:42" in formatted

    def test_format_error_with_hint(self) -> None:
        """Format error includes helpful hint."""
        diagnostic = ErrorTemplate.type_mismatch(
            function_name="NUMBER",
            argument_name="value",
            expected_type="Number",
            received_type="String",
        )

        formatted = diagnostic.format_error()

        assert "= help:" in formatted
        assert "Convert 'value' to Number" in formatted


class TestNewDiagnosticCodes:
    """Test new diagnostic codes for format errors."""

    def test_type_mismatch_code(self) -> None:
        """TYPE_MISMATCH code exists and has correct value."""
        assert DiagnosticCode.TYPE_MISMATCH.value == 2006

    def test_invalid_argument_code(self) -> None:
        """INVALID_ARGUMENT code exists and has correct value."""
        assert DiagnosticCode.INVALID_ARGUMENT.value == 2007

    def test_argument_required_code(self) -> None:
        """ARGUMENT_REQUIRED code exists and has correct value."""
        assert DiagnosticCode.ARGUMENT_REQUIRED.value == 2008

    def test_pattern_invalid_code(self) -> None:
        """PATTERN_INVALID code exists and has correct value."""
        assert DiagnosticCode.PATTERN_INVALID.value == 2009


class TestErrorTemplates:
    """Test new error template methods."""

    def test_type_mismatch_template(self) -> None:
        """type_mismatch() creates rich diagnostic."""
        diagnostic = ErrorTemplate.type_mismatch(
            function_name="NUMBER",
            argument_name="value",
            expected_type="Number",
            received_type="String",
        )

        assert "expected Number, got String" in diagnostic.message
        assert diagnostic.function_name == "NUMBER"

    def test_invalid_argument_template(self) -> None:
        """invalid_argument() creates rich diagnostic."""
        diagnostic = ErrorTemplate.invalid_argument(
            function_name="NUMBER",
            argument_name="minimumFractionDigits",
            reason="Must be non-negative",
        )

        assert "Invalid argument" in diagnostic.message
        assert "minimumFractionDigits" in diagnostic.message
        assert diagnostic.function_name == "NUMBER"

    def test_argument_required_template(self) -> None:
        """argument_required() creates rich diagnostic."""
        diagnostic = ErrorTemplate.argument_required(
            function_name="CURRENCY",
            argument_name="currency",
        )

        assert "Required argument" in diagnostic.message
        assert "currency" in diagnostic.message

    def test_pattern_invalid_template(self) -> None:
        """pattern_invalid() creates rich diagnostic."""
        diagnostic = ErrorTemplate.pattern_invalid(
            function_name="NUMBER",
            pattern="#,##0.00",
            reason="Syntax error at position 5",
        )

        assert "Invalid pattern" in diagnostic.message
        assert diagnostic.argument_name == "pattern"


class TestBackwardCompatibility:
    """Test backward compatibility with existing error handling."""

    def test_fluent_error_accepts_diagnostic(self) -> None:
        """FluentError still accepts Diagnostic objects."""
        diagnostic = ErrorTemplate.type_mismatch(
            function_name="NUMBER",
            argument_name="value",
            expected_type="Number",
            received_type="String",
        )

        error = FluentError(diagnostic)
        assert error.diagnostic == diagnostic
        assert "TYPE_MISMATCH" in str(error)

    def test_fluent_resolution_error_with_diagnostic(self) -> None:
        """FluentResolutionError works with rich diagnostics."""
        diagnostic = ErrorTemplate.function_failed("NUMBER", "Invalid value")

        error = FluentResolutionError(diagnostic)
        assert error.diagnostic == diagnostic
        assert error.diagnostic.function_name == "NUMBER"

    def test_string_error_still_works(self) -> None:
        """FluentError still accepts string messages."""
        error = FluentError("Simple error message")
        assert str(error) == "Simple error message"
        assert error.diagnostic is None
