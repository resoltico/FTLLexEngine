"""Hypothesis property-based tests for diagnostics and error handling.

Critical areas tested:
- FrozenFluentError construction and categorization
- Error message formatting consistency
- Diagnostic code assignment
- Error recovery and accumulation
- Exception construction with Diagnostic objects
"""

from __future__ import annotations

import pytest
from hypothesis import assume, event, given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import (
    Diagnostic,
    ErrorCategory,
    ErrorTemplate,
    FrozenFluentError,
)
from ftllexengine.diagnostics.codes import DiagnosticCode, SourceSpan

pytestmark = pytest.mark.fuzz

# ============================================================================
# HYPOTHESIS STRATEGIES
# ============================================================================

# Error message strategy - any non-empty text
error_messages = st.text(min_size=1, max_size=200)

# Message IDs and reference names
identifiers = st.from_regex(r"[a-z][a-z0-9_-]*", fullmatch=True)

# Line and column numbers for SourceSpan
line_numbers = st.integers(min_value=1, max_value=10000)
column_numbers = st.integers(min_value=0, max_value=200)
byte_offsets = st.integers(min_value=0, max_value=100000)


# ============================================================================
# PROPERTY TESTS - FROZEN FLUENT ERROR CONSTRUCTION
# ============================================================================


class TestFrozenFluentErrorConstruction:
    """Property tests for FrozenFluentError exception construction."""

    @given(message=error_messages)
    @settings(max_examples=100)
    def test_error_with_string_message(self, message: str) -> None:
        """PROPERTY: FrozenFluentError can be constructed with string message."""
        event(f"msg_len={len(message)}")
        error = FrozenFluentError(message, ErrorCategory.REFERENCE)

        assert str(error) == message
        assert error.diagnostic is None

    @given(message=error_messages)
    @settings(max_examples=100)
    def test_error_preserves_message(self, message: str) -> None:
        """PROPERTY: Error message is preserved in exception."""
        error = FrozenFluentError(message, ErrorCategory.RESOLUTION)

        # Message must be retrievable
        assert message in str(error)
        event(f"msg_len={len(message)}")

    @given(
        msg_id=identifiers,
        line=line_numbers,
        col=column_numbers,
        start=byte_offsets,
    )
    @settings(max_examples=50)
    def test_error_with_diagnostic_object(
        self, msg_id: str, line: int, col: int, start: int
    ) -> None:
        """PROPERTY: FrozenFluentError can be constructed with Diagnostic object."""
        end = start + len(msg_id)
        span = SourceSpan(start=start, end=end, line=line, column=col)
        message_text = f"Unknown message: {msg_id}"
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message=message_text,
            span=span,
        )

        error = FrozenFluentError(
            str(diagnostic), ErrorCategory.REFERENCE, diagnostic=diagnostic
        )

        assert error.diagnostic is not None
        assert error.diagnostic.code == DiagnosticCode.MESSAGE_NOT_FOUND
        assert msg_id in str(error)
        event(f"id_len={len(msg_id)}")


# ============================================================================
# PROPERTY TESTS - ERROR CATEGORIZATION
# ============================================================================


class TestErrorCategorization:
    """Property tests for FrozenFluentError categorization via ErrorCategory."""

    @given(message=error_messages)
    @settings(max_examples=50)
    def test_reference_category(self, message: str) -> None:
        """PROPERTY: FrozenFluentError with REFERENCE category is catchable."""
        error = FrozenFluentError(message, ErrorCategory.REFERENCE)

        assert error.category == ErrorCategory.REFERENCE
        assert isinstance(error, Exception)
        event("category=reference")

    @given(message=error_messages)
    @settings(max_examples=50)
    def test_resolution_category(self, message: str) -> None:
        """PROPERTY: FrozenFluentError with RESOLUTION category is catchable."""
        error = FrozenFluentError(message, ErrorCategory.RESOLUTION)

        assert error.category == ErrorCategory.RESOLUTION
        assert isinstance(error, Exception)
        event("category=resolution")

    @given(message=error_messages)
    @settings(max_examples=50)
    def test_cyclic_category(self, message: str) -> None:
        """PROPERTY: FrozenFluentError with CYCLIC category is catchable."""
        error = FrozenFluentError(message, ErrorCategory.CYCLIC)

        assert error.category == ErrorCategory.CYCLIC
        assert isinstance(error, Exception)
        event("category=cyclic")

    @given(message=error_messages)
    @settings(max_examples=50)
    def test_parse_category(self, message: str) -> None:
        """PROPERTY: FrozenFluentError with PARSE category is catchable."""
        error = FrozenFluentError(message, ErrorCategory.PARSE)

        assert error.category == ErrorCategory.PARSE
        assert isinstance(error, Exception)
        event("category=parse")

    @given(message=error_messages)
    @settings(max_examples=50)
    def test_formatting_category(self, message: str) -> None:
        """PROPERTY: FrozenFluentError with FORMATTING category is catchable."""
        error = FrozenFluentError(message, ErrorCategory.FORMATTING)

        assert error.category == ErrorCategory.FORMATTING
        assert isinstance(error, Exception)
        event("category=formatting")


# ============================================================================
# PROPERTY TESTS - DIAGNOSTIC CONSTRUCTION
# ============================================================================


class TestDiagnosticConstruction:
    """Property tests for Diagnostic object construction."""

    @given(
        message=error_messages,
        line=line_numbers,
        col=column_numbers,
        start=byte_offsets,
    )
    @settings(max_examples=100)
    def test_diagnostic_stores_all_fields(
        self, message: str, line: int, col: int, start: int
    ) -> None:
        """PROPERTY: Diagnostic preserves all constructor arguments."""
        end = start + 10
        span = SourceSpan(start=start, end=end, line=line, column=col)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message=message,
            span=span,
        )

        assert diagnostic.code == DiagnosticCode.MESSAGE_NOT_FOUND
        assert diagnostic.message == message
        assert diagnostic.span is not None
        assert diagnostic.span.line == line
        assert diagnostic.span.column == col
        event(f"msg_len={len(message)}")

    @given(
        message=error_messages,
        line=line_numbers,
        col=column_numbers,
        start=byte_offsets,
    )
    @settings(max_examples=50)
    def test_diagnostic_format_contains_location(
        self, message: str, line: int, col: int, start: int
    ) -> None:
        """PROPERTY: Formatted diagnostic includes line and column."""
        end = start + 10
        span = SourceSpan(start=start, end=end, line=line, column=col)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message=message,
            span=span,
        )

        formatted = diagnostic.format_error()

        # Must contain location information
        assert str(line) in formatted
        assert str(col) in formatted
        event(f"line={line}")

    @given(
        message=error_messages,
        line=line_numbers,
        col=column_numbers,
        start=byte_offsets,
    )
    @settings(max_examples=50)
    def test_diagnostic_format_contains_escaped_message(
        self, message: str, line: int, col: int, start: int
    ) -> None:
        """PROPERTY: Formatted diagnostic includes escaped error message.

        The formatter escapes control characters to prevent log
        injection, so the escaped message must appear in the output.
        """
        end = start + 10
        span = SourceSpan(start=start, end=end, line=line, column=col)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message=message,
            span=span,
        )

        formatted = diagnostic.format_error()

        escaped = (
            message
            .replace("\x1b", "\\x1b")
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("\t", "\\t")
        )
        assert escaped in formatted
        event(f"msg_len={len(message)}")


# ============================================================================
# PROPERTY TESTS - DIAGNOSTIC CODES
# ============================================================================


class TestDiagnosticCodes:
    """Property tests for diagnostic code enumeration."""

    def test_diagnostic_codes_are_unique(self) -> None:
        """PROPERTY: All diagnostic codes have unique values."""
        codes = [
            DiagnosticCode.MESSAGE_NOT_FOUND,
            DiagnosticCode.TERM_NOT_FOUND,
            DiagnosticCode.FUNCTION_NOT_FOUND,
            DiagnosticCode.VARIABLE_NOT_PROVIDED,
            DiagnosticCode.CYCLIC_REFERENCE,
            DiagnosticCode.NO_VARIANTS,
            DiagnosticCode.MESSAGE_NO_VALUE,
        ]

        # All codes must be unique
        assert len(codes) == len(set(codes))

    @given(
        msg_id=identifiers,
        line=line_numbers,
        col=column_numbers,
        start=byte_offsets,
    )
    @settings(max_examples=50)
    def test_each_code_produces_valid_diagnostic(
        self, msg_id: str, line: int, col: int, start: int
    ) -> None:
        """PROPERTY: Each diagnostic code can create valid Diagnostic."""
        end = start + len(msg_id)
        span = SourceSpan(start=start, end=end, line=line, column=col)
        codes = [
            DiagnosticCode.MESSAGE_NOT_FOUND,
            DiagnosticCode.TERM_NOT_FOUND,
            DiagnosticCode.FUNCTION_NOT_FOUND,
            DiagnosticCode.VARIABLE_NOT_PROVIDED,
            DiagnosticCode.CYCLIC_REFERENCE,
            DiagnosticCode.NO_VARIANTS,
            DiagnosticCode.MESSAGE_NO_VALUE,
        ]

        for code in codes:
            diagnostic = Diagnostic(
                code=code,
                message=f"Test error for {msg_id}",
                span=span,
            )

            assert diagnostic.code == code
            assert diagnostic.span is not None
            assert diagnostic.span.line == line
            assert diagnostic.span.column == col
        event(f"id_len={len(msg_id)}")


# ============================================================================
# PROPERTY TESTS - ERROR TEMPLATE
# ============================================================================


class TestErrorTemplate:
    """Property tests for ErrorTemplate functionality."""

    @given(msg_id=identifiers)
    @settings(max_examples=100)
    def test_message_not_found_template(self, msg_id: str) -> None:
        """PROPERTY: Message not found template produces consistent diagnostics."""
        diagnostic = ErrorTemplate.message_not_found(msg_id)

        assert isinstance(diagnostic, Diagnostic)
        assert diagnostic.code == DiagnosticCode.MESSAGE_NOT_FOUND
        assert msg_id in diagnostic.message
        event("template=message_not_found")

    @given(term_id=identifiers)
    @settings(max_examples=100)
    def test_term_not_found_template(self, term_id: str) -> None:
        """PROPERTY: Term not found template produces consistent diagnostics."""
        diagnostic = ErrorTemplate.term_not_found(term_id)

        assert isinstance(diagnostic, Diagnostic)
        assert diagnostic.code == DiagnosticCode.TERM_NOT_FOUND
        assert term_id in diagnostic.message
        event("template=term_not_found")

    @given(var_name=identifiers)
    @settings(max_examples=100)
    def test_variable_not_provided_template(self, var_name: str) -> None:
        """PROPERTY: Variable not provided template produces diagnostics."""
        diagnostic = ErrorTemplate.variable_not_provided(var_name)

        assert isinstance(diagnostic, Diagnostic)
        assert diagnostic.code == DiagnosticCode.VARIABLE_NOT_PROVIDED
        assert var_name in diagnostic.message
        event("template=variable_not_provided")

    @given(path=st.lists(identifiers, min_size=2, max_size=5))
    @settings(max_examples=100)
    def test_cyclic_reference_template(self, path: list[str]) -> None:
        """PROPERTY: Cyclic reference template handles resolution paths."""
        diagnostic = ErrorTemplate.cyclic_reference(path)

        assert isinstance(diagnostic, Diagnostic)
        assert diagnostic.code == DiagnosticCode.CYCLIC_REFERENCE
        # All identifiers in path should appear in message
        for identifier in path:
            assert identifier in diagnostic.message
        event(f"path_len={len(path)}")


# ============================================================================
# PROPERTY TESTS - ERROR MESSAGE CONSISTENCY
# ============================================================================


class TestErrorMessageConsistency:
    """Property tests for error message format consistency."""

    @given(msg_id=identifiers)
    @settings(max_examples=100)
    def test_reference_diagnostics_mention_identifier(
        self, msg_id: str
    ) -> None:
        """PROPERTY: Reference diagnostics always mention the identifier."""
        diagnostics = [
            ErrorTemplate.message_not_found(msg_id),
            ErrorTemplate.term_not_found(msg_id),
            ErrorTemplate.variable_not_provided(msg_id),
        ]

        for diagnostic in diagnostics:
            assert msg_id in diagnostic.message.lower()
        event(f"id_len={len(msg_id)}")

    @given(path=st.lists(identifiers, min_size=2, max_size=3))
    @settings(max_examples=50)
    def test_cyclic_diagnostics_indicate_cycle(
        self, path: list[str]
    ) -> None:
        """PROPERTY: Cyclic reference diagnostics indicate circular dependency."""
        diagnostic = ErrorTemplate.cyclic_reference(path)

        msg_lower = diagnostic.message.lower()
        # Should mention cycle/circular/cyclic
        assert any(
            word in msg_lower for word in ["cycle", "cyclic", "circular"]
        )
        event(f"path_len={len(path)}")

    @given(
        msg_id1=identifiers,
        msg_id2=identifiers,
    )
    @settings(max_examples=50)
    def test_same_template_same_format(
        self, msg_id1: str, msg_id2: str
    ) -> None:
        """PROPERTY: Same template produces consistently formatted messages."""
        assume(msg_id1 != msg_id2)
        # Ensure IDs are distinct enough that replacing doesn't cause false matches
        assume(msg_id1 not in msg_id2 and msg_id2 not in msg_id1)

        diag1 = ErrorTemplate.message_not_found(msg_id1)
        diag2 = ErrorTemplate.message_not_found(msg_id2)

        # Both should have same diagnostic code
        assert diag1.code == diag2.code

        # Both messages should follow same format (contain identifier)
        assert msg_id1 in diag1.message
        assert msg_id2 in diag2.message
        event("outcome=format_consistent")


# ============================================================================
# PROPERTY TESTS - ERROR RECOVERY
# ============================================================================


class TestErrorRecovery:
    """Property tests for error recovery behavior."""

    @given(
        msg_id=identifiers,
        line=line_numbers,
        col=column_numbers,
        start=byte_offsets,
    )
    @settings(max_examples=50)
    def test_diagnostic_with_span_includes_location(
        self, msg_id: str, line: int, col: int, start: int
    ) -> None:
        """PROPERTY: Diagnostics with span include source location."""
        end = start + len(msg_id)
        span = SourceSpan(start=start, end=end, line=line, column=col)
        message_text = f"Error with {msg_id}"
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message=message_text,
            span=span,
        )

        # format_error() includes span location; __str__ returns only message
        formatted = diagnostic.format_error()
        assert f"line {line}" in formatted
        assert f"column {col}" in formatted
        event(f"id_len={len(msg_id)}")

    @given(messages=st.lists(error_messages, min_size=1, max_size=10))
    @settings(max_examples=50)
    def test_multiple_errors_can_be_collected(
        self, messages: list[str]
    ) -> None:
        """PROPERTY: Multiple errors can be accumulated in a list."""
        errors: list[FrozenFluentError] = [
            FrozenFluentError(msg, ErrorCategory.REFERENCE)
            for msg in messages
        ]

        assert len(errors) == len(messages)

        for error, original_msg in zip(errors, messages, strict=True):
            assert original_msg in str(error)
        event(f"error_count={len(errors)}")


# ============================================================================
# PROPERTY TESTS - EXCEPTION BEHAVIOR
# ============================================================================


class TestExceptionBehavior:
    """Property tests for exception raising and catching."""

    @given(message=error_messages)
    @settings(max_examples=50)
    def test_errors_can_be_raised_and_caught(self, message: str) -> None:
        """PROPERTY: FrozenFluentError can be raised and caught as exception."""
        caught = False
        caught_message = ""

        try:
            raise FrozenFluentError(message, ErrorCategory.REFERENCE)
        except FrozenFluentError as e:
            caught = True
            caught_message = str(e)

        assert caught
        assert caught_message == message
        event("outcome=caught")

    @given(message=error_messages)
    @settings(max_examples=50)
    def test_all_categories_are_catchable(self, message: str) -> None:
        """PROPERTY: All ErrorCategory values are catchable as FrozenFluentError."""
        categories = [
            ErrorCategory.REFERENCE,
            ErrorCategory.RESOLUTION,
            ErrorCategory.CYCLIC,
            ErrorCategory.PARSE,
            ErrorCategory.FORMATTING,
        ]

        for category in categories:
            caught = False
            try:
                raise FrozenFluentError(message, category)
            except FrozenFluentError:
                caught = True

            assert caught
        event(f"categories_tested={len(categories)}")

    @given(msg_id=identifiers)
    @settings(max_examples=50)
    def test_cyclic_error_has_cyclic_category(
        self, msg_id: str
    ) -> None:
        """PROPERTY: Cyclic errors have CYCLIC category."""
        cycle_msg = f"Cycle: {msg_id}"
        error = FrozenFluentError(cycle_msg, ErrorCategory.CYCLIC)

        assert error.category == ErrorCategory.CYCLIC
        event("category=cyclic")


# ============================================================================
# PROPERTY TESTS - DIAGNOSTIC FORMATTING
# ============================================================================


class TestDiagnosticFormatting:
    """Property tests for diagnostic message formatting."""

    @given(
        message=error_messages,
        line=line_numbers,
        col=column_numbers,
        start=byte_offsets,
    )
    @settings(max_examples=100)
    def test_formatted_diagnostic_is_nonempty(
        self, message: str, line: int, col: int, start: int
    ) -> None:
        """PROPERTY: Formatted diagnostics are never empty."""
        end = start + 10
        span = SourceSpan(start=start, end=end, line=line, column=col)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message=message,
            span=span,
        )

        formatted = diagnostic.format_error()

        assert formatted
        assert len(formatted) > 0
        event(f"formatted_len={len(formatted)}")

    @given(
        message=error_messages,
        line=line_numbers,
        col=column_numbers,
        start=byte_offsets,
    )
    @settings(max_examples=50)
    def test_formatted_diagnostic_has_structure(
        self, message: str, line: int, col: int, start: int
    ) -> None:
        """PROPERTY: Formatted diagnostics have consistent structure.

        The formatter escapes control characters to prevent log
        injection, so the escaped message must appear in the output.
        """
        end = start + 10
        span = SourceSpan(start=start, end=end, line=line, column=col)
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message=message,
            span=span,
        )

        formatted = diagnostic.format_error()

        assert isinstance(formatted, str)
        escaped = (
            message
            .replace("\x1b", "\\x1b")
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("\t", "\\t")
        )
        assert escaped in formatted
        assert str(line) in formatted
        assert str(col) in formatted
        event(f"msg_len={len(message)}")
