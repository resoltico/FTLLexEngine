# mypy: ignore-errors
# mypy: ignore-errors
from __future__ import annotations

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    ErrorCategory,
    FrozenErrorContext,
    FrozenFluentError,
    SourceSpan,
)
from ftllexengine.integrity import ImmutabilityViolationError
from tests.strategies.diagnostics import error_categories

# =============================================================================
# Strategies for generating test data
# =============================================================================


@st.composite
def error_messages(draw: st.DrawFn) -> str:
    """Generate valid error messages."""
    return draw(st.text(min_size=1, max_size=200))


@st.composite
def optional_diagnostics(draw: st.DrawFn) -> Diagnostic | None:
    """Generate optional Diagnostic objects."""
    if draw(st.booleans()):
        code = draw(st.sampled_from(list(DiagnosticCode)))
        message = draw(st.text(min_size=1, max_size=100))
        return Diagnostic(code=code, message=message, severity="error")
    return None


@st.composite
def optional_contexts(draw: st.DrawFn) -> FrozenErrorContext | None:
    """Generate optional FrozenErrorContext objects."""
    if draw(st.booleans()):
        return FrozenErrorContext(
            input_value=draw(st.text(min_size=0, max_size=50)),
            locale_code=draw(st.text(min_size=1, max_size=10)),
            parse_type=draw(st.sampled_from(
                ["", "currency", "date", "datetime", "decimal", "number"]
            )),
            fallback_value=draw(st.text(min_size=0, max_size=50)),
        )
    return None


@st.composite
def frozen_fluent_errors(draw: st.DrawFn) -> FrozenFluentError:
    """Generate FrozenFluentError instances."""
    return FrozenFluentError(
        message=draw(error_messages()),
        category=draw(error_categories()),
        diagnostic=draw(optional_diagnostics()),
        context=draw(optional_contexts()),
    )


# =============================================================================
# Content Hash Properties
# =============================================================================



class TestCompleteBranchCoverage:
    """Tests to achieve 100% branch coverage for errors.py."""

    def test_setattr_unfrozen_branch(self) -> None:
        """Test __setattr__ when _frozen is False (line 176 coverage).

        This tests the defensive else branch in __setattr__ that allows
        attribute setting when the object is not yet frozen. While this
        branch is not normally reached (since __init__ uses object.__setattr__
        directly), it exists as a defensive measure.

        This test forcibly unfreezes an error to exercise the branch.
        """
        error = FrozenFluentError("test", ErrorCategory.REFERENCE)

        # Verify object is initially frozen
        assert error.verify_integrity() is True

        # Forcibly unfreeze using object.__setattr__ to bypass immutability
        object.__setattr__(error, "_frozen", False)

        # Now call the instance's __setattr__ DIRECTLY - should reach line 176
        # Must use the class method, not object.__setattr__
        FrozenFluentError.__setattr__(error, "_message", "modified")

        # Verify the change took effect (since we unfroze it)
        assert error._message == "modified"

        # Re-freeze for cleanup
        object.__setattr__(error, "_frozen", True)

    def test_eq_with_non_error_type_returns_not_implemented(self) -> None:
        """Test __eq__ returns NotImplemented for non-FrozenFluentError types.

        The __eq__ method should return NotImplemented (not False) when
        comparing with objects that are not FrozenFluentError instances.
        This allows Python to try the comparison from the other object's
        perspective.
        """
        error = FrozenFluentError("test", ErrorCategory.REFERENCE)

        # Test with various non-FrozenFluentError types
        # Direct dunder call required to verify NotImplemented return value
        # (using == operator would convert NotImplemented to False)
        result = error.__eq__(42)  # pylint: disable=unnecessary-dunder-call
        assert result is NotImplemented

        result = error.__eq__("string")  # pylint: disable=unnecessary-dunder-call
        assert result is NotImplemented

        result = error.__eq__({"dict": "value"})  # pylint: disable=unnecessary-dunder-call
        assert result is NotImplemented

        result = error.__eq__([1, 2, 3])  # pylint: disable=unnecessary-dunder-call
        assert result is NotImplemented

        # The actual equality operator should return False (Python's default)
        assert (error == 42) is False
        assert (error == "string") is False

    def test_compute_content_hash_with_all_fields(self) -> None:
        """Test _compute_content_hash with all optional fields populated.

        This ensures the hash computation includes all diagnostic and context
        fields when present, achieving full branch coverage in the hash
        computation logic.
        """
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Test diagnostic message",
        )
        context = FrozenErrorContext(
            input_value="test input",
            locale_code="en_US",
            parse_type="number",
            fallback_value="fallback",
        )

        error1 = FrozenFluentError(
            "test message",
            ErrorCategory.FORMATTING,
            diagnostic=diagnostic,
            context=context,
        )

        # Create another with same values
        error2 = FrozenFluentError(
            "test message",
            ErrorCategory.FORMATTING,
            diagnostic=diagnostic,
            context=context,
        )

        # Hashes should be identical
        assert error1.content_hash == error2.content_hash

        # Verify hash includes all fields by changing each one
        error3 = FrozenFluentError(
            "different message",  # Changed
            ErrorCategory.FORMATTING,
            diagnostic=diagnostic,
            context=context,
        )
        assert error1.content_hash != error3.content_hash

        diagnostic2 = Diagnostic(
            code=DiagnosticCode.TERM_NOT_FOUND,  # Different code
            message="Test diagnostic message",
        )
        error4 = FrozenFluentError(
            "test message",
            ErrorCategory.FORMATTING,
            diagnostic=diagnostic2,  # Changed
            context=context,
        )
        assert error1.content_hash != error4.content_hash

        context2 = FrozenErrorContext(
            input_value="different input",  # Changed
            locale_code="en_US",
            parse_type="number",
            fallback_value="fallback",
        )
        error5 = FrozenFluentError(
            "test message",
            ErrorCategory.FORMATTING,
            diagnostic=diagnostic,
            context=context2,  # Changed
        )
        assert error1.content_hash != error5.content_hash

    def test_hash_with_surrogates_in_text(self) -> None:
        """Test content hash computation with invalid Unicode surrogates.

        The hash function uses surrogatepass error handling to ensure it can
        hash any Python string, including those with unpaired surrogates from
        malformed user input.
        """
        # Create error with unpaired surrogate (invalid Unicode)
        # Python allows these in strings but they're not valid UTF-8
        message_with_surrogate = "Error: \ud800 invalid"

        error = FrozenFluentError(message_with_surrogate, ErrorCategory.PARSE)

        # Should successfully compute hash without raising UnicodeEncodeError
        assert len(error.content_hash) == 16
        assert error.verify_integrity() is True

        # Test with surrogate in context fields
        context = FrozenErrorContext(
            input_value="\ud800 surrogate input",
            locale_code="en_US",
            parse_type="currency",
            fallback_value="\ud800\udc00 surrogate fallback",
        )
        error_with_context = FrozenFluentError(
            "test",
            ErrorCategory.FORMATTING,
            context=context,
        )
        assert len(error_with_context.content_hash) == 16
        assert error_with_context.verify_integrity() is True

    @given(
        message=st.text(),
        category=error_categories(),
    )
    @settings(max_examples=50)
    def test_repr_contains_all_constructor_args(
        self, message: str, category: ErrorCategory
    ) -> None:
        """Property: __repr__ includes all constructor arguments for debugging."""
        error = FrozenFluentError(message, category)
        r = repr(error)

        # Should contain class name
        assert "FrozenFluentError" in r

        # Should contain all field names
        assert "message=" in r
        assert "category=" in r
        assert "diagnostic=" in r
        assert "context=" in r

        # Message should be represented (possibly truncated in repr)
        # Category should be shown
        assert category.name in r or str(category) in r
        event(f"category={category.name}")

    def test_hash_with_diagnostic_span(self) -> None:
        """Test content hash computation with Diagnostic containing SourceSpan.

        This exercises lines 196-199 in _compute_content_hash where span
        fields are hashed when diagnostic.span is not None.
        """
        # Create diagnostic WITH span
        diagnostic_with_span = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Test message",
            span=SourceSpan(start=10, end=20, line=5, column=3),
            severity="error",
        )

        error1 = FrozenFluentError(
            "test",
            ErrorCategory.REFERENCE,
            diagnostic=diagnostic_with_span,
        )

        # Create another with same span
        error2 = FrozenFluentError(
            "test",
            ErrorCategory.REFERENCE,
            diagnostic=diagnostic_with_span,
        )

        # Should have identical hashes
        assert error1.content_hash == error2.content_hash

        # Create diagnostic with different span values
        diagnostic_different_span = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Test message",
            span=SourceSpan(start=100, end=200, line=10, column=15),
            severity="error",
        )

        error3 = FrozenFluentError(
            "test",
            ErrorCategory.REFERENCE,
            diagnostic=diagnostic_different_span,
        )

        # Should have different hash
        assert error1.content_hash != error3.content_hash

        # Verify integrity
        assert error1.verify_integrity() is True
        assert error3.verify_integrity() is True

    def test_hash_with_diagnostic_optional_fields(self) -> None:
        """Test content hash computation with all Diagnostic optional fields.

        This exercises line 215 in _compute_content_hash where optional
        string fields (hint, help_url, etc.) are hashed when not None.
        """
        # Create diagnostic with ALL optional string fields populated
        diagnostic_full = Diagnostic(
            code=DiagnosticCode.FUNCTION_FAILED,
            message="Function error",
            hint="Check your arguments",
            help_url="https://example.com/help",
            function_name="NUMBER",
            argument_name="value",
            expected_type="int | Decimal",
            received_type="str",
            ftl_location="messages.ftl:42",
            severity="error",
        )

        error1 = FrozenFluentError(
            "test",
            ErrorCategory.RESOLUTION,
            diagnostic=diagnostic_full,
        )

        # Create another with same fields
        error2 = FrozenFluentError(
            "test",
            ErrorCategory.RESOLUTION,
            diagnostic=diagnostic_full,
        )

        # Should have identical hashes
        assert error1.content_hash == error2.content_hash

        # Change one optional field
        diagnostic_changed = Diagnostic(
            code=DiagnosticCode.FUNCTION_FAILED,
            message="Function error",
            hint="Different hint",  # Changed
            help_url="https://example.com/help",
            function_name="NUMBER",
            argument_name="value",
            expected_type="int | Decimal",
            received_type="str",
            ftl_location="messages.ftl:42",
            severity="error",
        )

        error3 = FrozenFluentError(
            "test",
            ErrorCategory.RESOLUTION,
            diagnostic=diagnostic_changed,
        )

        # Should have different hash
        assert error1.content_hash != error3.content_hash

        # Verify integrity
        assert error1.verify_integrity() is True
        assert error3.verify_integrity() is True

    def test_hash_with_diagnostic_resolution_path(self) -> None:
        """Test content hash computation with Diagnostic resolution_path.

        This exercises lines 225-228 in _compute_content_hash where
        resolution_path tuple elements are hashed when not None.
        """
        # Create diagnostic with resolution_path
        diagnostic_with_path = Diagnostic(
            code=DiagnosticCode.CYCLIC_REFERENCE,
            message="Cyclic reference detected",
            resolution_path=("message1", "message2", "message3"),
            severity="error",
        )

        error1 = FrozenFluentError(
            "test",
            ErrorCategory.CYCLIC,
            diagnostic=diagnostic_with_path,
        )

        # Create another with same path
        error2 = FrozenFluentError(
            "test",
            ErrorCategory.CYCLIC,
            diagnostic=diagnostic_with_path,
        )

        # Should have identical hashes
        assert error1.content_hash == error2.content_hash

        # Create diagnostic with different resolution_path
        diagnostic_different_path = Diagnostic(
            code=DiagnosticCode.CYCLIC_REFERENCE,
            message="Cyclic reference detected",
            resolution_path=("message1", "message4", "message5"),  # Different
            severity="error",
        )

        error3 = FrozenFluentError(
            "test",
            ErrorCategory.CYCLIC,
            diagnostic=diagnostic_different_path,
        )

        # Should have different hash
        assert error1.content_hash != error3.content_hash

        # Create diagnostic with empty resolution_path
        diagnostic_empty_path = Diagnostic(
            code=DiagnosticCode.CYCLIC_REFERENCE,
            message="Cyclic reference detected",
            resolution_path=(),  # Empty tuple
            severity="error",
        )

        error4 = FrozenFluentError(
            "test",
            ErrorCategory.CYCLIC,
            diagnostic=diagnostic_empty_path,
        )

        # Should have different hash from non-empty path
        assert error1.content_hash != error4.content_hash

        # Verify integrity
        assert error1.verify_integrity() is True
        assert error3.verify_integrity() is True
        assert error4.verify_integrity() is True

    def test_setattr_allows_python_exception_attributes(self) -> None:
        """Test __setattr__ allows Python exception mechanism attributes.

        This exercises lines 254-255 in __setattr__ where Python's exception
        handling attributes (__traceback__, __context__, __cause__,
        __suppress_context__) are allowed even after freeze.
        """
        error = FrozenFluentError("test", ErrorCategory.REFERENCE)

        # Python exception attributes should be settable even after freeze
        # These are set by Python's exception handling mechanism
        import sys

        # Create a dummy traceback by raising and catching
        tb = None
        try:
            msg = "dummy"
            raise ValueError(msg)
        except ValueError:
            tb = sys.exc_info()[2]

        # Should NOT raise ImmutabilityViolationError
        error.__traceback__ = tb
        assert error.__traceback__ is tb

        # Test __context__ (exception chaining)
        context_error = ValueError("context")
        error.__context__ = context_error
        assert error.__context__ is context_error

        # Test __cause__ (explicit exception chaining)
        cause_error = RuntimeError("cause")
        error.__cause__ = cause_error
        assert error.__cause__ is cause_error

        # Test __suppress_context__
        error.__suppress_context__ = True
        assert error.__suppress_context__ is True

        # Verify error is still frozen for other attributes
        with pytest.raises(ImmutabilityViolationError):
            error._message = "modified"

        # Verify integrity is maintained
        assert error.verify_integrity() is True

    def test_notes_attribute_allowed_for_python_311_compatibility(self) -> None:
        """__notes__ attribute can be set for Python 3.11+ exception groups.

        Python 3.11 added __notes__ for Exception Groups (PEP 654/678).
        FrozenFluentError must allow this attribute to be set even after freeze
        to support exception enrichment via add_note() and exception groups.
        """
        error = FrozenFluentError("test", ErrorCategory.RESOLUTION)

        # Simulate what Python's add_note() does internally
        # (it sets __notes__ attribute if not present, then appends)
        error.__notes__ = []
        error.__notes__.append("additional context")
        error.__notes__.append("more info")

        # Verify notes were set
        assert hasattr(error, "__notes__")
        assert error.__notes__ == ["additional context", "more info"]

        # Verify error is still frozen for other attributes
        with pytest.raises(ImmutabilityViolationError):
            error._message = "modified"

        # Verify integrity is maintained
        assert error.verify_integrity() is True

    def test_delattr_raises_immutability_violation(self) -> None:
        """__delattr__ rejects all attribute deletions after construction."""
        error = FrozenFluentError("test", ErrorCategory.REFERENCE)
        with pytest.raises(ImmutabilityViolationError):
            del error._message
        with pytest.raises(ImmutabilityViolationError):
            del error._category

    def test_hash_returns_int_from_content_hash(self) -> None:
        """__hash__ derives from all 16 bytes of BLAKE2b-128 content hash.

        Python's hash() protocol calls int.__hash__() on the returned integer,
        reducing it via Mersenne prime modulus to a platform-sized hash value.
        We verify the full 128-bit integer is used, not a truncated subset.
        """
        error = FrozenFluentError("test", ErrorCategory.REFERENCE)
        h = hash(error)
        # __hash__ returns int.from_bytes(content_hash, "big") (all 16 bytes);
        # Python's hash() then applies int.__hash__() which reduces via modulus.
        # Compute the same reduction independently to verify full-hash derivation.
        expected = hash(int.from_bytes(error.content_hash, "big"))
        assert h == expected

    def test_eq_compares_content_hash_for_matching_errors(self) -> None:
        """__eq__ returns True for errors with identical content."""
        error1 = FrozenFluentError("test", ErrorCategory.REFERENCE)
        error2 = FrozenFluentError("test", ErrorCategory.REFERENCE)
        assert error1 == error2

    def test_eq_compares_content_hash_for_different_errors(self) -> None:
        """__eq__ returns False for errors with different content."""
        error1 = FrozenFluentError("msg1", ErrorCategory.REFERENCE)
        error2 = FrozenFluentError("msg2", ErrorCategory.REFERENCE)
        assert error1 != error2

    def test_convenience_properties_return_empty_without_context(
        self,
    ) -> None:
        """Convenience properties return empty string when context is None."""
        error = FrozenFluentError("test", ErrorCategory.REFERENCE)
        assert error.context is None
        assert error.fallback_value == ""
        assert error.input_value == ""
        assert error.locale_code == ""
        assert error.parse_type == ""

    def test_convenience_properties_delegate_to_context(self) -> None:
        """Convenience properties return context field values when present."""
        ctx = FrozenErrorContext(
            input_value="42abc",
            locale_code="de_DE",
            parse_type="number",
            fallback_value="{!NUMBER}",
        )
        error = FrozenFluentError(
            "test", ErrorCategory.PARSE, context=ctx
        )
        assert error.fallback_value == "{!NUMBER}"
        assert error.input_value == "42abc"
        assert error.locale_code == "de_DE"
        assert error.parse_type == "number"
