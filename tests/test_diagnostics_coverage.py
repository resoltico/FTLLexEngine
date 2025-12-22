"""Tests for diagnostics/codes.py to achieve 100% coverage.

Focuses on Diagnostic.format_error() branches for span, hint, and help_url.
"""

from ftllexengine.diagnostics.codes import Diagnostic, DiagnosticCode, SourceSpan


class TestDiagnosticFormatError:
    """Test Diagnostic.format_error() coverage for all branches."""

    def test_format_error_with_span(self):
        """Test format_error with span (line 96)."""
        span = SourceSpan(start=10, end=20, line=5, column=10)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'hello' not found",
            span=span,
        )

        result = diagnostic.format_error()

        assert "error[MESSAGE_NOT_FOUND]: Message 'hello' not found" in result
        assert "--> line 5, column 10" in result

    def test_format_error_with_hint(self):
        """Test format_error with hint (lines 98-99)."""
        diagnostic = Diagnostic(
            code=DiagnosticCode.VARIABLE_NOT_PROVIDED,
            message="Variable 'name' not provided",
            hint="Check that the variable is passed in args",
        )

        result = diagnostic.format_error()

        assert "error[VARIABLE_NOT_PROVIDED]: Variable 'name' not provided" in result
        assert "= help: Check that the variable is passed in args" in result

    def test_format_error_with_help_url(self):
        """Test format_error with help_url (lines 101-102)."""
        diagnostic = Diagnostic(
            code=DiagnosticCode.TERM_NOT_FOUND,
            message="Term '-brand' not found",
            help_url="https://projectfluent.org/fluent/guide/terms.html",
        )

        result = diagnostic.format_error()

        assert "error[TERM_NOT_FOUND]: Term '-brand' not found" in result
        assert "= note: see https://projectfluent.org/fluent/guide/terms.html" in result

    def test_format_error_with_all_fields(self):
        """Test format_error with span, hint, and help_url."""
        span = SourceSpan(start=0, end=10, line=1, column=1)
        diagnostic = Diagnostic(
            code=DiagnosticCode.CYCLIC_REFERENCE,
            message="Circular reference detected",
            span=span,
            hint="Break the reference cycle",
            help_url="https://projectfluent.org/fluent/guide/references.html",
        )

        result = diagnostic.format_error()

        assert "error[CYCLIC_REFERENCE]: Circular reference detected" in result
        assert "--> line 1, column 1" in result
        assert "= help: Break the reference cycle" in result
        assert "= note: see https://projectfluent.org/fluent/guide/references.html" in result

    def test_format_error_minimal(self):
        """Test format_error with only required fields."""
        diagnostic = Diagnostic(
            code=DiagnosticCode.UNKNOWN_EXPRESSION,
            message="Unknown expression type",
        )

        result = diagnostic.format_error()

        assert "error[UNKNOWN_EXPRESSION]: Unknown expression type" in result
        assert "-->" not in result
        assert "= help:" not in result
        assert "= note:" not in result
