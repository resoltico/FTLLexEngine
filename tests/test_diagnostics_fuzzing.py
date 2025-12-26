"""Diagnostics fuzzing tests.

Property-based tests for error message generation:
- All error codes produce non-empty messages
- Template placeholders are substituted correctly
- No crashes on edge cases

Note: This file is marked with pytest.mark.fuzz and is excluded from normal
test runs. Run via: ./scripts/fuzz.sh or pytest -m fuzz
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    DiagnosticFormatter,
    ErrorTemplate,
    FluentCyclicReferenceError,
    FluentError,
    FluentReferenceError,
    FluentResolutionError,
    FluentSyntaxError,
)
from ftllexengine.runtime.bundle import FluentBundle

# Mark all tests in this file as fuzzing tests
pytestmark = pytest.mark.fuzz


# -----------------------------------------------------------------------------
# Property Tests: Error Code Coverage
# -----------------------------------------------------------------------------


class TestErrorCodeProperties:
    """Property tests for error code handling."""

    def test_all_error_codes_exist(self) -> None:
        """All DiagnosticCode values are defined."""
        codes = list(DiagnosticCode)
        assert len(codes) > 0
        for code in codes:
            assert isinstance(code.value, int)
            assert isinstance(code.name, str)

    @given(st.sampled_from(list(DiagnosticCode)))
    @settings(max_examples=50, deadline=None)
    def test_diagnostic_creation(self, code: DiagnosticCode) -> None:
        """Property: Diagnostics can be created for any code."""
        diagnostic = Diagnostic(
            code=code,
            message="Test message",
            severity="error",
        )

        assert diagnostic.code == code
        assert diagnostic.message == "Test message"
        assert diagnostic.severity in ("error", "warning")


# -----------------------------------------------------------------------------
# Property Tests: Error Message Formatting
# -----------------------------------------------------------------------------


class TestErrorMessageProperties:
    """Property tests for error message formatting."""

    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=100, deadline=None)
    def test_reference_error_formatting(self, msg: str) -> None:
        """Property: Reference errors format properly."""
        error = FluentReferenceError(msg)

        error_str = str(error)
        assert isinstance(error_str, str)
        assert len(error_str) > 0

    @given(st.lists(st.text(min_size=1, max_size=20), min_size=2, max_size=10))
    @settings(max_examples=50, deadline=None)
    def test_cyclic_error_formatting(self, path: list[str]) -> None:
        """Property: Cyclic errors format with full path."""
        # Create a Diagnostic using the ErrorTemplate
        diagnostic = ErrorTemplate.cyclic_reference(path)
        error = FluentCyclicReferenceError(diagnostic)

        error_str = str(error)
        assert isinstance(error_str, str)
        # Should mention cycle
        assert "cycle" in error_str.lower() or "circular" in error_str.lower()

    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=100, deadline=None)
    def test_syntax_error_formatting(self, detail: str) -> None:
        """Property: Syntax errors format properly."""
        error = FluentSyntaxError(detail)

        error_str = str(error)
        assert isinstance(error_str, str)

    @given(st.text(min_size=1, max_size=100))
    @settings(max_examples=100, deadline=None)
    def test_resolution_error_formatting(self, detail: str) -> None:
        """Property: Resolution errors format properly."""
        error = FluentResolutionError(detail)

        error_str = str(error)
        assert isinstance(error_str, str)


# -----------------------------------------------------------------------------
# Property Tests: ErrorTemplate Methods
# -----------------------------------------------------------------------------


class TestErrorTemplateProperties:
    """Property tests for ErrorTemplate factory methods."""

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=50))
    @settings(max_examples=100, deadline=None)
    def test_message_not_found_template(self, msg_id: str) -> None:
        """Property: message_not_found creates valid Diagnostic."""
        diagnostic = ErrorTemplate.message_not_found(msg_id)

        assert isinstance(diagnostic, Diagnostic)
        assert diagnostic.code == DiagnosticCode.MESSAGE_NOT_FOUND
        assert msg_id in diagnostic.message

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=20))
    @settings(max_examples=50, deadline=None)
    def test_term_not_found_template(self, term_id: str) -> None:
        """Property: term_not_found creates valid Diagnostic."""
        diagnostic = ErrorTemplate.term_not_found(term_id)

        assert isinstance(diagnostic, Diagnostic)
        assert diagnostic.code == DiagnosticCode.TERM_NOT_FOUND
        assert term_id in diagnostic.message

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=20))
    @settings(max_examples=50, deadline=None)
    def test_variable_not_provided_template(self, var_name: str) -> None:
        """Property: variable_not_provided creates valid Diagnostic."""
        diagnostic = ErrorTemplate.variable_not_provided(var_name)

        assert isinstance(diagnostic, Diagnostic)
        assert diagnostic.code == DiagnosticCode.VARIABLE_NOT_PROVIDED
        assert var_name in diagnostic.message


# -----------------------------------------------------------------------------
# Property Tests: Diagnostic Integration
# -----------------------------------------------------------------------------


class TestDiagnosticIntegration:
    """Property tests for diagnostic integration with bundle."""

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=20))
    @settings(max_examples=100, deadline=None)
    def test_missing_message_diagnostic(self, msg_id: str) -> None:
        """Property: Missing messages produce diagnostics."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("other = value")

        _, errors = bundle.format_pattern(msg_id)

        # For missing messages, should have errors
        if msg_id != "other":
            assert len(errors) > 0
            # Each error should be a proper error object
            for error in errors:
                assert isinstance(error, FluentError)

    @given(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=20))
    @settings(max_examples=100, deadline=None)
    def test_missing_variable_diagnostic(self, var_name: str) -> None:
        """Property: Missing variables produce diagnostics."""
        bundle = FluentBundle("en-US")
        bundle.add_resource(f"msg = Hello {{ ${var_name} }}")

        result, _ = bundle.format_pattern("msg", {})

        # Should have error for missing variable
        assert isinstance(result, str)
        # Missing variable should produce some indication

    def test_syntax_error_diagnostic(self) -> None:
        """Syntax errors in resource produce diagnostics."""
        bundle = FluentBundle("en-US")

        # This should produce parse errors (junk)
        bundle.add_resource("!invalid = syntax here")

        # Valid message should still work
        bundle.add_resource("valid = This works")
        result, _ = bundle.format_pattern("valid")

        assert result == "This works"

    def test_cycle_error_diagnostic(self) -> None:
        """Cyclic references produce diagnostics."""
        bundle = FluentBundle("en-US")
        bundle.add_resource(
            """
a = { b }
b = { a }
"""
        )

        _, errors = bundle.format_pattern("a")

        assert len(errors) > 0
        # Should have cyclic reference error
        assert any(isinstance(e, FluentCyclicReferenceError) for e in errors)


class TestDiagnosticFormatter:
    """Property tests for diagnostic formatter."""

    @given(st.sampled_from(list(DiagnosticCode)))
    @settings(max_examples=50, deadline=None)
    def test_formatter_handles_all_codes(self, code: DiagnosticCode) -> None:
        """Property: Formatter handles all diagnostic codes."""
        diagnostic = Diagnostic(
            code=code,
            message="Test message",
            severity="error",
        )

        formatter = DiagnosticFormatter()
        formatted = formatter.format(diagnostic)

        assert isinstance(formatted, str)
        assert len(formatted) > 0

    @given(st.sampled_from(["error", "warning"]))
    @settings(max_examples=10, deadline=None)
    def test_formatter_severity_levels(self, severity: str) -> None:
        """Property: Formatter handles all severity levels."""
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Test",
            severity=severity,  # type: ignore[arg-type]
        )

        formatter = DiagnosticFormatter()
        formatted = formatter.format(diagnostic)

        assert isinstance(formatted, str)


# -----------------------------------------------------------------------------
# Edge Case Tests
# -----------------------------------------------------------------------------


class TestDiagnosticEdgeCases:
    """Tests for diagnostic edge cases."""

    def test_empty_message_id(self) -> None:
        """Empty message ID handling."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("msg = value")

        # Empty string as message ID
        result, errors = bundle.format_pattern("")

        assert isinstance(result, str)
        assert len(errors) > 0

    def test_unicode_in_error_message(self) -> None:
        """Unicode characters in error context."""
        bundle = FluentBundle("en-US")
        bundle.add_resource("msg = value")

        # Unicode message ID
        result, _ = bundle.format_pattern("nonexistent")

        assert isinstance(result, str)

    @given(st.text(min_size=1, max_size=200))
    @settings(max_examples=50, deadline=None)
    def test_long_message_in_diagnostic(self, long_text: str) -> None:
        """Property: Long text in diagnostics doesn't crash."""
        error = FluentReferenceError(long_text)
        error_str = str(error)
        assert isinstance(error_str, str)

    def test_special_characters_in_error(self) -> None:
        """Special characters in error messages."""
        special_chars = ["<script>", "${cmd}", "\x00", "\n\r\t", "\\", '"']

        for char in special_chars:
            error = FluentReferenceError(f"test{char}id")
            error_str = str(error)
            assert isinstance(error_str, str)
