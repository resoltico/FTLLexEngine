"""Property-based tests for FrozenFluentError integrity guarantees.

Tests the data integrity features of the FrozenFluentError class:
- BLAKE2b-128 content hashing (determinism, collision resistance)
- Immutability enforcement (no mutation after construction)
- Sealed type enforcement (no subclassing)
- Content-based equality and hashability
- verify_integrity() method correctness

These tests verify financial-grade data safety properties using Hypothesis
property-based testing.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, event, example, given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    ErrorCategory,
    FrozenErrorContext,
    FrozenFluentError,
)
from ftllexengine.integrity import ImmutabilityViolationError

# =============================================================================
# Strategies for generating test data
# =============================================================================


@st.composite
def error_categories(draw: st.DrawFn) -> ErrorCategory:
    """Generate random ErrorCategory values."""
    return draw(st.sampled_from(list(ErrorCategory)))


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
            parse_type=draw(st.text(min_size=1, max_size=20)),
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


@pytest.mark.fuzz
class TestContentHashDeterminism:
    """Content hash must be deterministic - same inputs always produce same hash."""

    @given(
        message=error_messages(),
        category=error_categories(),
    )
    @settings(max_examples=100)
    def test_same_inputs_produce_same_hash(
        self, message: str, category: ErrorCategory
    ) -> None:
        """Property: Identical errors have identical content hashes."""
        error1 = FrozenFluentError(message, category)
        error2 = FrozenFluentError(message, category)

        event(f"msg_len={len(message)}")
        assert error1.content_hash == error2.content_hash
        assert error1 == error2
        event("outcome=hash_determinism_success")

    @given(
        message=error_messages(),
        category=error_categories(),
        diagnostic=optional_diagnostics(),
        context=optional_contexts(),
    )
    @settings(max_examples=100)
    def test_same_inputs_with_optional_fields(
        self,
        message: str,
        category: ErrorCategory,
        diagnostic: Diagnostic | None,
        context: FrozenErrorContext | None,
    ) -> None:
        """Property: Identical errors with optional fields have identical hashes."""
        error1 = FrozenFluentError(message, category, diagnostic, context)
        error2 = FrozenFluentError(message, category, diagnostic, context)

        has_diag = diagnostic is not None
        has_ctx = context is not None
        event(f"has_diagnostic={has_diag}")
        event(f"has_context={has_ctx}")
        assert error1.content_hash == error2.content_hash
        assert error1 == error2

    @given(error=frozen_fluent_errors())
    @settings(max_examples=100)
    def test_hash_is_16_bytes(self, error: FrozenFluentError) -> None:
        """Property: Content hash is always 16 bytes (BLAKE2b-128)."""
        event(f"category={error.category.name}")
        assert len(error.content_hash) == 16


@pytest.mark.fuzz
class TestContentHashCollisionResistance:
    """Different inputs should produce different hashes (high probability)."""

    @given(
        message1=error_messages(),
        message2=error_messages(),
        category=error_categories(),
    )
    @settings(max_examples=100)
    def test_different_messages_different_hashes(
        self, message1: str, message2: str, category: ErrorCategory
    ) -> None:
        """Property: Different messages produce different hashes."""
        assume(message1 != message2)

        error1 = FrozenFluentError(message1, category)
        error2 = FrozenFluentError(message2, category)

        event(f"msg1_len={len(message1)}")
        event(f"msg2_len={len(message2)}")
        assert error1.content_hash != error2.content_hash
        assert error1 != error2
        event("outcome=hash_collision_resistance")

    @given(
        message=error_messages(),
        category1=error_categories(),
        category2=error_categories(),
    )
    @settings(max_examples=100)
    def test_different_categories_different_hashes(
        self, message: str, category1: ErrorCategory, category2: ErrorCategory
    ) -> None:
        """Property: Different categories produce different hashes."""
        assume(category1 != category2)

        error1 = FrozenFluentError(message, category1)
        error2 = FrozenFluentError(message, category2)

        event(f"cat1={category1.name}")
        event(f"cat2={category2.name}")
        assert error1.content_hash != error2.content_hash
        assert error1 != error2


# =============================================================================
# Immutability Enforcement
# =============================================================================


@pytest.mark.fuzz
class TestImmutabilityEnforcement:
    """FrozenFluentError must reject all mutations after construction."""

    @given(error=frozen_fluent_errors())
    @settings(max_examples=50)
    def test_cannot_modify_message(self, error: FrozenFluentError) -> None:
        """Property: Cannot modify message after construction."""
        with pytest.raises(ImmutabilityViolationError):
            error._message = "modified"
        event(f"msg_len={len(error.message)}")
        event("outcome=immutability_enforced")

    @given(error=frozen_fluent_errors())
    @settings(max_examples=50)
    def test_cannot_modify_category(self, error: FrozenFluentError) -> None:
        """Property: Cannot modify category after construction."""
        with pytest.raises(ImmutabilityViolationError):
            error._category = ErrorCategory.PARSE
        event(f"category={error.category.name}")

    @given(error=frozen_fluent_errors())
    @settings(max_examples=50)
    def test_cannot_modify_diagnostic(self, error: FrozenFluentError) -> None:
        """Property: Cannot modify diagnostic after construction."""
        with pytest.raises(ImmutabilityViolationError):
            error._diagnostic = None
        has_diag = error.diagnostic is not None
        event(f"has_diagnostic={has_diag}")

    @given(error=frozen_fluent_errors())
    @settings(max_examples=50)
    def test_cannot_modify_context(self, error: FrozenFluentError) -> None:
        """Property: Cannot modify context after construction."""
        with pytest.raises(ImmutabilityViolationError):
            error._context = None
        has_ctx = error.context is not None
        event(f"has_context={has_ctx}")

    @given(error=frozen_fluent_errors())
    @settings(max_examples=50)
    def test_cannot_modify_content_hash(self, error: FrozenFluentError) -> None:
        """Property: Cannot modify content hash after construction."""
        with pytest.raises(ImmutabilityViolationError):
            error._content_hash = b"fake"
        event(f"category={error.category.name}")

    @given(error=frozen_fluent_errors())
    @settings(max_examples=50)
    def test_cannot_delete_attributes(self, error: FrozenFluentError) -> None:
        """Property: Cannot delete any attributes."""
        with pytest.raises(ImmutabilityViolationError):
            del error._message
        event(f"category={error.category.name}")


# =============================================================================
# Sealed Type Enforcement
# =============================================================================


class TestSealedTypeEnforcement:
    """FrozenFluentError must reject subclassing at runtime."""

    def test_cannot_subclass(self) -> None:
        """FrozenFluentError cannot be subclassed."""
        with pytest.raises(TypeError, match="cannot be subclassed"):
            # pylint: disable=unused-variable,subclassed-final-class
            class MaliciousError(FrozenFluentError):  # type: ignore[misc]
                pass


# =============================================================================
# Integrity Verification
# =============================================================================


@pytest.mark.fuzz
class TestVerifyIntegrity:
    """verify_integrity() must correctly detect corruption."""

    @given(error=frozen_fluent_errors())
    @settings(max_examples=100)
    def test_fresh_error_passes_integrity_check(
        self, error: FrozenFluentError
    ) -> None:
        """Property: Freshly constructed errors always pass integrity check."""
        event(f"category={error.category.name}")
        assert error.verify_integrity() is True
        event("outcome=integrity_check_passed")

    @given(error=frozen_fluent_errors())
    @settings(max_examples=100)
    def test_integrity_is_idempotent(self, error: FrozenFluentError) -> None:
        """Property: verify_integrity() can be called multiple times."""
        event(f"category={error.category.name}")
        assert error.verify_integrity() is True
        assert error.verify_integrity() is True
        assert error.verify_integrity() is True


# =============================================================================
# Hashability and Set/Dict Usage
# =============================================================================


@pytest.mark.fuzz
class TestHashability:
    """FrozenFluentError must be usable in sets and as dict keys."""

    @given(error=frozen_fluent_errors())
    @settings(max_examples=50)
    def test_error_is_hashable(self, error: FrozenFluentError) -> None:
        """Property: Errors are hashable (can use hash())."""
        h = hash(error)
        assert isinstance(h, int)
        event(f"category={error.category.name}")

    @given(error=frozen_fluent_errors())
    @settings(max_examples=50)
    def test_hash_is_stable(self, error: FrozenFluentError) -> None:
        """Property: Hash is stable across multiple calls."""
        h1 = hash(error)
        h2 = hash(error)
        h3 = hash(error)
        assert h1 == h2 == h3
        event(f"category={error.category.name}")

    @given(
        message=error_messages(),
        category=error_categories(),
    )
    @settings(max_examples=50)
    def test_equal_errors_have_equal_hashes(
        self, message: str, category: ErrorCategory
    ) -> None:
        """Property: Equal errors have equal hashes (hash contract)."""
        error1 = FrozenFluentError(message, category)
        error2 = FrozenFluentError(message, category)

        assert error1 == error2
        assert hash(error1) == hash(error2)
        event(f"category={category.name}")

    @given(
        errors=st.lists(frozen_fluent_errors(), min_size=1, max_size=20, unique=True)
    )
    @settings(max_examples=50)
    def test_errors_can_be_added_to_set(
        self, errors: list[FrozenFluentError]
    ) -> None:
        """Property: Errors can be stored in sets."""
        error_set = set(errors)
        assert len(error_set) <= len(errors)
        event(f"set_size={len(error_set)}")

    @given(
        errors=st.lists(frozen_fluent_errors(), min_size=1, max_size=20, unique=True)
    )
    @settings(max_examples=50)
    def test_errors_can_be_dict_keys(
        self, errors: list[FrozenFluentError]
    ) -> None:
        """Property: Errors can be used as dict keys."""
        error_dict = {e: i for i, e in enumerate(errors)}
        assert len(error_dict) <= len(errors)
        event(f"dict_size={len(error_dict)}")


# =============================================================================
# Equality Semantics
# =============================================================================


@pytest.mark.fuzz
class TestEquality:
    """FrozenFluentError equality must be based on content."""

    @given(error=frozen_fluent_errors())
    @settings(max_examples=50)
    def test_error_equals_itself(self, error: FrozenFluentError) -> None:
        """Property: Errors are equal to themselves (reflexivity)."""
        same_ref = error
        assert error == same_ref
        event(f"category={error.category.name}")

    @given(
        message=error_messages(),
        category=error_categories(),
    )
    @settings(max_examples=50)
    def test_identical_errors_are_equal(
        self, message: str, category: ErrorCategory
    ) -> None:
        """Property: Identical errors are equal (symmetry)."""
        error1 = FrozenFluentError(message, category)
        error2 = FrozenFluentError(message, category)

        assert error1 == error2
        assert error2 == error1
        event(f"category={category.name}")

    @given(error=frozen_fluent_errors())
    @settings(max_examples=50)
    def test_error_not_equal_to_string(self, error: FrozenFluentError) -> None:
        """Property: Errors are not equal to strings."""
        assert (error == error.message) is False
        event(f"category={error.category.name}")

    @given(error=frozen_fluent_errors())
    @settings(max_examples=50)
    def test_error_not_equal_to_none(self, error: FrozenFluentError) -> None:
        """Property: Errors are not equal to None (tests __eq__ method)."""
        # pylint: disable=singleton-comparison
        assert (error == None) is False  # noqa: E711
        event(f"category={error.category.name}")


# =============================================================================
# Property Access
# =============================================================================


@pytest.mark.fuzz
class TestPropertyAccess:
    """FrozenFluentError properties must be accessible."""

    @given(
        message=error_messages(),
        category=error_categories(),
    )
    @settings(max_examples=50)
    def test_message_property(self, message: str, category: ErrorCategory) -> None:
        """Property: message property returns the message."""
        error = FrozenFluentError(message, category)
        assert error.message == message
        event(f"msg_len={len(message)}")

    @given(
        message=error_messages(),
        category=error_categories(),
    )
    @settings(max_examples=50)
    def test_category_property(self, message: str, category: ErrorCategory) -> None:
        """Property: category property returns the category."""
        error = FrozenFluentError(message, category)
        assert error.category == category
        event(f"category={category.name}")

    @given(
        message=error_messages(),
        category=error_categories(),
        diagnostic=optional_diagnostics(),
    )
    @settings(max_examples=50)
    def test_diagnostic_property(
        self,
        message: str,
        category: ErrorCategory,
        diagnostic: Diagnostic | None,
    ) -> None:
        """Property: diagnostic property returns the diagnostic."""
        error = FrozenFluentError(message, category, diagnostic=diagnostic)
        assert error.diagnostic == diagnostic
        has_diag = diagnostic is not None
        event(f"has_diagnostic={has_diag}")

    @given(
        message=error_messages(),
        category=error_categories(),
        context=optional_contexts(),
    )
    @settings(max_examples=50)
    def test_context_property(
        self,
        message: str,
        category: ErrorCategory,
        context: FrozenErrorContext | None,
    ) -> None:
        """Property: context property returns the context."""
        error = FrozenFluentError(message, category, context=context)
        assert error.context == context
        has_ctx = context is not None
        event(f"has_context={has_ctx}")


# =============================================================================
# Context Convenience Properties
# =============================================================================


@pytest.mark.fuzz
class TestContextConvenienceProperties:
    """FrozenFluentError convenience properties for context fields."""

    @given(
        message=error_messages(),
        category=error_categories(),
    )
    @settings(max_examples=50)
    def test_context_properties_empty_without_context(
        self, message: str, category: ErrorCategory
    ) -> None:
        """Property: Context convenience properties return empty strings without context."""
        error = FrozenFluentError(message, category)

        assert error.fallback_value == ""
        assert error.input_value == ""
        assert error.locale_code == ""
        assert error.parse_type == ""
        event(f"category={category.name}")

    @given(
        message=error_messages(),
        category=error_categories(),
    )
    @settings(max_examples=50)
    def test_context_properties_with_context(
        self, message: str, category: ErrorCategory
    ) -> None:
        """Property: Context convenience properties return context values."""
        context = FrozenErrorContext(
            input_value="test_input",
            locale_code="en_US",
            parse_type="number",
            fallback_value="{!NUMBER}",
        )
        error = FrozenFluentError(message, category, context=context)

        assert error.fallback_value == "{!NUMBER}"
        assert error.input_value == "test_input"
        assert error.locale_code == "en_US"
        assert error.parse_type == "number"
        event(f"category={category.name}")


# =============================================================================
# String Representation
# =============================================================================


@pytest.mark.fuzz
class TestStringRepresentation:
    """FrozenFluentError must have sensible string representation."""

    @given(error=frozen_fluent_errors())
    @settings(max_examples=50)
    def test_str_returns_message(self, error: FrozenFluentError) -> None:
        """Property: str() returns the error message."""
        assert str(error) == error.message
        event(f"msg_len={len(error.message)}")

    @given(error=frozen_fluent_errors())
    @settings(max_examples=50)
    def test_repr_is_valid(self, error: FrozenFluentError) -> None:
        """Property: repr() returns a valid representation."""
        r = repr(error)
        assert isinstance(r, str)
        assert "FrozenFluentError" in r
        assert "message=" in r
        assert "category=" in r
        event(f"category={error.category.name}")


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Edge case tests for FrozenFluentError."""

    def test_empty_message(self) -> None:
        """FrozenFluentError accepts empty message."""
        error = FrozenFluentError("", ErrorCategory.REFERENCE)
        assert error.message == ""
        assert error.verify_integrity() is True

    def test_unicode_message(self) -> None:
        """FrozenFluentError handles Unicode messages."""
        error = FrozenFluentError("Error: \u4e2d\u6587\u6587\u672c", ErrorCategory.PARSE)
        assert error.verify_integrity() is True

    def test_emoji_message(self) -> None:
        """FrozenFluentError handles emoji in messages."""
        error = FrozenFluentError("Error \U0001F44D occurred", ErrorCategory.FORMATTING)
        assert error.verify_integrity() is True

    @example(message="Test")
    @given(message=st.text())
    @settings(max_examples=100)
    def test_arbitrary_text_messages(self, message: str) -> None:
        """Property: FrozenFluentError handles arbitrary text."""
        error = FrozenFluentError(message, ErrorCategory.RESOLUTION)
        assert error.verify_integrity() is True
        assert error.message == message
        event(f"msg_len={len(message)}")

    def test_all_categories_work(self) -> None:
        """All ErrorCategory values can be used."""
        for category in ErrorCategory:
            error = FrozenFluentError("test", category)
            assert error.category == category
            assert error.verify_integrity() is True


# =============================================================================
# Exception Behavior
# =============================================================================


@pytest.mark.fuzz
class TestExceptionBehavior:
    """FrozenFluentError must behave like a proper exception."""

    @given(error=frozen_fluent_errors())
    @settings(max_examples=50)
    def test_can_be_raised(self, error: FrozenFluentError) -> None:
        """Property: FrozenFluentError can be raised and caught."""
        with pytest.raises(FrozenFluentError) as exc_info:
            raise error
        assert exc_info.value is error
        event(f"category={error.category.name}")

    @given(error=frozen_fluent_errors())
    @settings(max_examples=50)
    def test_can_be_caught_as_exception(self, error: FrozenFluentError) -> None:
        """Property: FrozenFluentError can be caught as Exception."""
        with pytest.raises(Exception) as exc_info:  # noqa: PT011
            raise error
        assert exc_info.value is error
        event(f"category={error.category.name}")

    @given(error=frozen_fluent_errors())
    @settings(max_examples=50)
    def test_exception_args(self, error: FrozenFluentError) -> None:
        """Property: Exception args contain the message."""
        assert error.args == (error.message,)
        event(f"category={error.category.name}")


# =============================================================================
# Complete Branch Coverage Tests
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
            parse_type="\udc00 surrogate type",
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
        from ftllexengine.diagnostics.codes import SourceSpan  # noqa: PLC0415

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
            expected_type="int | float",
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
            expected_type="int | float",
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
        import sys  # noqa: PLC0415

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
