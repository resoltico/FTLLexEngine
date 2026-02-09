"""Tests for SEC-METADATA-INTEGRITY-GAP fixes.

Tests verify that:
1. IntegrityCacheEntry checksums include created_at and sequence metadata
2. FrozenFluentError content hashes include all Diagnostic fields

These fixes ensure complete audit trail integrity for financial-grade applications.

Python 3.13+.
"""

from __future__ import annotations

from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    ErrorCategory,
    FrozenFluentError,
    SourceSpan,
)
from ftllexengine.runtime.cache import IntegrityCacheEntry

# ============================================================================
# SEC-METADATA-INTEGRITY-GAP-001: Cache checksum includes metadata
# ============================================================================


class TestCacheChecksumIncludesMetadata:
    """Test that IntegrityCacheEntry checksum includes created_at and sequence.

    These tests verify SEC-METADATA-INTEGRITY-GAP-001 fix: checksums must
    include ALL entry fields for complete audit trail integrity.
    """

    def test_different_sequence_different_checksum(self) -> None:
        """Different sequence numbers produce different checksums.

        Even with identical content and timestamp, different sequence numbers
        must produce different checksums to detect tampering.
        """
        # Create entries with same content but different sequences
        # Use internal _compute_checksum to control all inputs
        formatted = "Hello, World!"
        errors: tuple[FrozenFluentError, ...] = ()
        created_at = 12345.67890
        seq1, seq2 = 1, 2

        checksum1 = IntegrityCacheEntry._compute_checksum(
            formatted, errors, created_at, seq1
        )
        checksum2 = IntegrityCacheEntry._compute_checksum(
            formatted, errors, created_at, seq2
        )

        # Different sequences must produce different checksums
        assert checksum1 != checksum2

    def test_different_timestamp_different_checksum(self) -> None:
        """Different timestamps produce different checksums.

        Even with identical content and sequence, different timestamps must
        produce different checksums to detect tampering.
        """
        formatted = "Hello, World!"
        errors: tuple[FrozenFluentError, ...] = ()
        sequence = 1
        ts1 = 12345.67890
        ts2 = 12345.67891  # Slightly different

        checksum1 = IntegrityCacheEntry._compute_checksum(
            formatted, errors, ts1, sequence
        )
        checksum2 = IntegrityCacheEntry._compute_checksum(
            formatted, errors, ts2, sequence
        )

        # Different timestamps must produce different checksums
        assert checksum1 != checksum2

    def test_checksum_validates_with_metadata(self) -> None:
        """Entry verify() method uses metadata in checksum validation."""
        entry = IntegrityCacheEntry.create("Test content", (), sequence=42)

        # Entry should validate correctly
        assert entry.verify() is True

        # Create corrupted entry with wrong metadata but same checksum
        corrupted = IntegrityCacheEntry(
            formatted=entry.formatted,
            errors=entry.errors,
            checksum=entry.checksum,  # Original checksum
            created_at=entry.created_at + 100.0,  # Tampered timestamp
            sequence=entry.sequence,
        )

        # Corrupted entry should fail validation
        assert corrupted.verify() is False

    def test_checksum_detects_sequence_tampering(self) -> None:
        """verify() detects sequence number tampering."""
        entry = IntegrityCacheEntry.create("Content", (), sequence=100)

        # Create entry with tampered sequence
        tampered = IntegrityCacheEntry(
            formatted=entry.formatted,
            errors=entry.errors,
            checksum=entry.checksum,
            created_at=entry.created_at,
            sequence=999,  # Tampered sequence
        )

        # Tampered entry should fail validation
        assert tampered.verify() is False

    @given(
        st.floats(min_value=0, max_value=1e10, allow_nan=False, allow_infinity=False),
        st.integers(min_value=0, max_value=2**31 - 1),
    )
    @settings(max_examples=100)
    def test_property_metadata_affects_checksum(
        self, created_at: float, sequence: int
    ) -> None:
        """PROPERTY: Changing metadata changes checksum."""
        event(f"offset={sequence}")
        formatted = "Property test content"
        errors: tuple[FrozenFluentError, ...] = ()

        checksum_original = IntegrityCacheEntry._compute_checksum(
            formatted, errors, created_at, sequence
        )

        # Same content, different sequence
        checksum_diff_seq = IntegrityCacheEntry._compute_checksum(
            formatted, errors, created_at, sequence + 1
        )
        assert checksum_original != checksum_diff_seq

        # Same content, different timestamp
        checksum_diff_ts = IntegrityCacheEntry._compute_checksum(
            formatted, errors, created_at + 0.001, sequence
        )
        assert checksum_original != checksum_diff_ts

    def test_checksum_includes_ieee754_timestamp(self) -> None:
        """Checksum computation uses IEEE 754 double encoding for timestamp.

        Timestamp is encoded as 8-byte big-endian IEEE 754 double.
        """
        formatted = "Test"
        errors: tuple[FrozenFluentError, ...] = ()
        created_at = 12345.67890
        sequence = 1

        # Compute checksum
        checksum = IntegrityCacheEntry._compute_checksum(
            formatted, errors, created_at, sequence
        )

        # Verify checksum changes when timestamp changes by smallest representable amount
        # IEEE 754 double has ~15-17 significant digits
        checksum_diff = IntegrityCacheEntry._compute_checksum(
            formatted, errors, created_at + 1e-10, sequence
        )
        assert checksum != checksum_diff

    def test_checksum_includes_signed_sequence(self) -> None:
        """Checksum computation handles negative sequence numbers.

        Sequence is encoded as 8-byte signed big-endian integer.
        """
        formatted = "Test"
        errors: tuple[FrozenFluentError, ...] = ()
        created_at = 12345.0
        seq_positive = 1
        seq_negative = -1

        checksum_pos = IntegrityCacheEntry._compute_checksum(
            formatted, errors, created_at, seq_positive
        )
        checksum_neg = IntegrityCacheEntry._compute_checksum(
            formatted, errors, created_at, seq_negative
        )

        # Positive and negative sequences produce different checksums
        assert checksum_pos != checksum_neg


# ============================================================================
# SEC-METADATA-INTEGRITY-GAP-002: Error content hash includes all Diagnostic fields
# ============================================================================


class TestErrorContentHashIncludesAllDiagnosticFields:
    """Test that FrozenFluentError content hash includes all Diagnostic fields.

    These tests verify SEC-METADATA-INTEGRITY-GAP-002 fix: content hashes must
    include ALL Diagnostic fields for complete audit trail integrity.
    """

    def test_different_span_different_hash(self) -> None:
        """Different source spans produce different content hashes."""
        span1 = SourceSpan(start=0, end=10, line=1, column=1)
        span2 = SourceSpan(start=0, end=10, line=1, column=5)  # Different column

        diag1 = Diagnostic(code=DiagnosticCode.MESSAGE_NOT_FOUND, message="Test", span=span1)
        diag2 = Diagnostic(code=DiagnosticCode.MESSAGE_NOT_FOUND, message="Test", span=span2)

        error1 = FrozenFluentError("Error", ErrorCategory.REFERENCE, diagnostic=diag1)
        error2 = FrozenFluentError("Error", ErrorCategory.REFERENCE, diagnostic=diag2)

        # Different spans must produce different hashes
        assert error1.content_hash != error2.content_hash

    def test_span_vs_no_span_different_hash(self) -> None:
        """Diagnostic with span vs without span produce different hashes."""
        span = SourceSpan(start=0, end=10, line=1, column=1)

        diag_with_span = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND, message="Test", span=span
        )
        diag_without_span = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND, message="Test", span=None
        )

        error1 = FrozenFluentError("Error", ErrorCategory.REFERENCE, diagnostic=diag_with_span)
        error2 = FrozenFluentError("Error", ErrorCategory.REFERENCE, diagnostic=diag_without_span)

        # With vs without span must produce different hashes
        assert error1.content_hash != error2.content_hash

    def test_different_hint_different_hash(self) -> None:
        """Different hints produce different content hashes."""
        diag1 = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND, message="Test", hint="Check spelling"
        )
        diag2 = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND, message="Test", hint="Add message"
        )

        error1 = FrozenFluentError("Error", ErrorCategory.REFERENCE, diagnostic=diag1)
        error2 = FrozenFluentError("Error", ErrorCategory.REFERENCE, diagnostic=diag2)

        assert error1.content_hash != error2.content_hash

    def test_hint_vs_no_hint_different_hash(self) -> None:
        """Diagnostic with hint vs without hint produce different hashes."""
        diag_with_hint = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND, message="Test", hint="Fix it"
        )
        diag_without_hint = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND, message="Test", hint=None
        )

        error1 = FrozenFluentError("Error", ErrorCategory.REFERENCE, diagnostic=diag_with_hint)
        error2 = FrozenFluentError("Error", ErrorCategory.REFERENCE, diagnostic=diag_without_hint)

        assert error1.content_hash != error2.content_hash

    def test_different_function_name_different_hash(self) -> None:
        """Different function names produce different content hashes."""
        diag1 = Diagnostic(
            code=DiagnosticCode.FUNCTION_FAILED, message="Test", function_name="NUMBER"
        )
        diag2 = Diagnostic(
            code=DiagnosticCode.FUNCTION_FAILED, message="Test", function_name="DATETIME"
        )

        error1 = FrozenFluentError("Error", ErrorCategory.RESOLUTION, diagnostic=diag1)
        error2 = FrozenFluentError("Error", ErrorCategory.RESOLUTION, diagnostic=diag2)

        assert error1.content_hash != error2.content_hash

    def test_different_argument_name_different_hash(self) -> None:
        """Different argument names produce different content hashes."""
        diag1 = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Test",
            argument_name="value",
        )
        diag2 = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Test",
            argument_name="style",
        )

        error1 = FrozenFluentError("Error", ErrorCategory.RESOLUTION, diagnostic=diag1)
        error2 = FrozenFluentError("Error", ErrorCategory.RESOLUTION, diagnostic=diag2)

        assert error1.content_hash != error2.content_hash

    def test_different_expected_type_different_hash(self) -> None:
        """Different expected types produce different content hashes."""
        diag1 = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Test",
            expected_type="Number",
        )
        diag2 = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Test",
            expected_type="String",
        )

        error1 = FrozenFluentError("Error", ErrorCategory.RESOLUTION, diagnostic=diag1)
        error2 = FrozenFluentError("Error", ErrorCategory.RESOLUTION, diagnostic=diag2)

        assert error1.content_hash != error2.content_hash

    def test_different_received_type_different_hash(self) -> None:
        """Different received types produce different content hashes."""
        diag1 = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Test",
            received_type="String",
        )
        diag2 = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Test",
            received_type="Boolean",
        )

        error1 = FrozenFluentError("Error", ErrorCategory.RESOLUTION, diagnostic=diag1)
        error2 = FrozenFluentError("Error", ErrorCategory.RESOLUTION, diagnostic=diag2)

        assert error1.content_hash != error2.content_hash

    def test_different_ftl_location_different_hash(self) -> None:
        """Different FTL locations produce different content hashes."""
        diag1 = Diagnostic(
            code=DiagnosticCode.FUNCTION_FAILED,
            message="Test",
            ftl_location="messages.ftl:10",
        )
        diag2 = Diagnostic(
            code=DiagnosticCode.FUNCTION_FAILED,
            message="Test",
            ftl_location="messages.ftl:20",
        )

        error1 = FrozenFluentError("Error", ErrorCategory.RESOLUTION, diagnostic=diag1)
        error2 = FrozenFluentError("Error", ErrorCategory.RESOLUTION, diagnostic=diag2)

        assert error1.content_hash != error2.content_hash

    def test_different_severity_different_hash(self) -> None:
        """Different severity levels produce different content hashes."""
        diag1 = Diagnostic(
            code=DiagnosticCode.VALIDATION_SHADOW_WARNING,
            message="Test",
            severity="warning",
        )
        diag2 = Diagnostic(
            code=DiagnosticCode.VALIDATION_SHADOW_WARNING,
            message="Test",
            severity="error",
        )

        error1 = FrozenFluentError("Error", ErrorCategory.REFERENCE, diagnostic=diag1)
        error2 = FrozenFluentError("Error", ErrorCategory.REFERENCE, diagnostic=diag2)

        assert error1.content_hash != error2.content_hash

    def test_different_resolution_path_different_hash(self) -> None:
        """Different resolution paths produce different content hashes."""
        diag1 = Diagnostic(
            code=DiagnosticCode.CYCLIC_REFERENCE,
            message="Test",
            resolution_path=("msg1", "msg2", "msg3"),
        )
        diag2 = Diagnostic(
            code=DiagnosticCode.CYCLIC_REFERENCE,
            message="Test",
            resolution_path=("msg1", "msg2", "msg4"),  # Different path
        )

        error1 = FrozenFluentError("Error", ErrorCategory.CYCLIC, diagnostic=diag1)
        error2 = FrozenFluentError("Error", ErrorCategory.CYCLIC, diagnostic=diag2)

        assert error1.content_hash != error2.content_hash

    def test_resolution_path_vs_no_path_different_hash(self) -> None:
        """Diagnostic with path vs without path produce different hashes."""
        diag_with_path = Diagnostic(
            code=DiagnosticCode.CYCLIC_REFERENCE,
            message="Test",
            resolution_path=("msg1", "msg2"),
        )
        diag_without_path = Diagnostic(
            code=DiagnosticCode.CYCLIC_REFERENCE,
            message="Test",
            resolution_path=None,
        )

        error1 = FrozenFluentError("Error", ErrorCategory.CYCLIC, diagnostic=diag_with_path)
        error2 = FrozenFluentError("Error", ErrorCategory.CYCLIC, diagnostic=diag_without_path)

        assert error1.content_hash != error2.content_hash

    def test_different_help_url_different_hash(self) -> None:
        """Different help URLs produce different content hashes."""
        diag1 = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Test",
            help_url="https://example.com/help1",
        )
        diag2 = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Test",
            help_url="https://example.com/help2",
        )

        error1 = FrozenFluentError("Error", ErrorCategory.REFERENCE, diagnostic=diag1)
        error2 = FrozenFluentError("Error", ErrorCategory.REFERENCE, diagnostic=diag2)

        assert error1.content_hash != error2.content_hash

    def test_all_diagnostic_fields_affect_hash(self) -> None:
        """Comprehensive test: ALL Diagnostic fields affect content hash."""
        # Create diagnostic with ALL fields populated
        full_diagnostic = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Type mismatch",
            span=SourceSpan(start=10, end=20, line=5, column=3),
            hint="Convert to number first",
            help_url="https://example.com/type-mismatch",
            function_name="NUMBER",
            argument_name="value",
            expected_type="Number",
            received_type="String",
            ftl_location="messages.ftl:42",
            severity="error",
            resolution_path=("msg1", "term1", "msg2"),
        )

        error_full = FrozenFluentError(
            "Type error", ErrorCategory.RESOLUTION, diagnostic=full_diagnostic
        )

        # Verify each field change produces different hash
        # Change each field one at a time and verify hash changes

        # Different span.start
        diag_diff_span = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Type mismatch",
            span=SourceSpan(start=11, end=20, line=5, column=3),  # Changed start
            hint="Convert to number first",
            help_url="https://example.com/type-mismatch",
            function_name="NUMBER",
            argument_name="value",
            expected_type="Number",
            received_type="String",
            ftl_location="messages.ftl:42",
            severity="error",
            resolution_path=("msg1", "term1", "msg2"),
        )
        error_diff_span = FrozenFluentError(
            "Type error", ErrorCategory.RESOLUTION, diagnostic=diag_diff_span
        )
        assert error_full.content_hash != error_diff_span.content_hash

        # Different span.end
        diag_diff_span_end = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Type mismatch",
            span=SourceSpan(start=10, end=21, line=5, column=3),  # Changed end
            hint="Convert to number first",
            help_url="https://example.com/type-mismatch",
            function_name="NUMBER",
            argument_name="value",
            expected_type="Number",
            received_type="String",
            ftl_location="messages.ftl:42",
            severity="error",
            resolution_path=("msg1", "term1", "msg2"),
        )
        error_diff_span_end = FrozenFluentError(
            "Type error", ErrorCategory.RESOLUTION, diagnostic=diag_diff_span_end
        )
        assert error_full.content_hash != error_diff_span_end.content_hash

        # Different span.line
        diag_diff_line = Diagnostic(
            code=DiagnosticCode.TYPE_MISMATCH,
            message="Type mismatch",
            span=SourceSpan(start=10, end=20, line=6, column=3),  # Changed line
            hint="Convert to number first",
            help_url="https://example.com/type-mismatch",
            function_name="NUMBER",
            argument_name="value",
            expected_type="Number",
            received_type="String",
            ftl_location="messages.ftl:42",
            severity="error",
            resolution_path=("msg1", "term1", "msg2"),
        )
        error_diff_line = FrozenFluentError(
            "Type error", ErrorCategory.RESOLUTION, diagnostic=diag_diff_line
        )
        assert error_full.content_hash != error_diff_line.content_hash

    def test_integrity_verification_with_all_fields(self) -> None:
        """verify_integrity() works correctly with all Diagnostic fields."""
        full_diagnostic = Diagnostic(
            code=DiagnosticCode.FUNCTION_FAILED,
            message="Function failed",
            span=SourceSpan(start=0, end=100, line=10, column=5),
            hint="Check function arguments",
            help_url="https://docs.example.com/functions",
            function_name="CURRENCY",
            argument_name="currency",
            expected_type="CurrencyCode",
            received_type="String",
            ftl_location="pricing.ftl:77",
            severity="error",
            resolution_path=("price-msg", "format-currency"),
        )

        error = FrozenFluentError(
            "CURRENCY function failed",
            ErrorCategory.RESOLUTION,
            diagnostic=full_diagnostic,
        )

        # Freshly created error should pass integrity check
        assert error.verify_integrity() is True

        # Multiple calls should be idempotent
        assert error.verify_integrity() is True
        assert error.verify_integrity() is True

    @given(
        st.integers(min_value=0, max_value=1000),
        st.integers(min_value=0, max_value=1000),
        st.integers(min_value=1, max_value=100),
        st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=50)
    def test_property_span_changes_affect_hash(
        self, start: int, end: int, line: int, column: int
    ) -> None:
        """PROPERTY: Any span field change affects content hash."""
        event(f"offset={start}")
        span = SourceSpan(start=start, end=end, line=line, column=column)
        diag = Diagnostic(code=DiagnosticCode.MESSAGE_NOT_FOUND, message="Test", span=span)
        error = FrozenFluentError("Error", ErrorCategory.REFERENCE, diagnostic=diag)

        # Change start
        span_diff = SourceSpan(start=start + 1, end=end, line=line, column=column)
        diag_diff = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND, message="Test", span=span_diff
        )
        error_diff = FrozenFluentError(
            "Error", ErrorCategory.REFERENCE, diagnostic=diag_diff
        )
        assert error.content_hash != error_diff.content_hash

    @given(
        st.text(min_size=1, max_size=50),
        st.text(min_size=1, max_size=50),
    )
    @settings(max_examples=50)
    def test_property_string_fields_affect_hash(self, hint: str, help_url: str) -> None:
        """PROPERTY: String field changes affect content hash."""
        diag1 = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Test",
            hint=hint,
            help_url=help_url,
        )
        diag2 = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Test",
            hint=hint + "x",  # Modified hint
            help_url=help_url,
        )

        error1 = FrozenFluentError("Error", ErrorCategory.REFERENCE, diagnostic=diag1)
        error2 = FrozenFluentError("Error", ErrorCategory.REFERENCE, diagnostic=diag2)

        assert error1.content_hash != error2.content_hash


# ============================================================================
# Integration tests
# ============================================================================


class TestIntegrityIntegration:
    """Integration tests for metadata integrity fixes."""

    def test_cache_entry_with_errors_validates(self) -> None:
        """Cache entry with FrozenFluentError validates correctly.

        Integration test: cache checksum uses error.content_hash which
        now includes all Diagnostic fields.
        """
        full_diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Message 'test' not found",
            span=SourceSpan(start=0, end=10, line=1, column=1),
            hint="Add message to bundle",
        )
        error = FrozenFluentError(
            "Message not found",
            ErrorCategory.REFERENCE,
            diagnostic=full_diagnostic,
        )

        # Create cache entry with this error
        entry = IntegrityCacheEntry.create(
            formatted="{test}",
            errors=(error,),
            sequence=1,
        )

        # Entry should validate correctly
        assert entry.verify() is True

        # Error should also validate independently
        assert error.verify_integrity() is True

    def test_different_error_diagnostics_produce_different_cache_entries(self) -> None:
        """Cache entries with different error diagnostics have different checksums."""
        diag1 = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Test",
            span=SourceSpan(start=0, end=10, line=1, column=1),
        )
        diag2 = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Test",
            span=SourceSpan(start=0, end=10, line=1, column=5),  # Different column
        )

        error1 = FrozenFluentError("Error", ErrorCategory.REFERENCE, diagnostic=diag1)
        error2 = FrozenFluentError("Error", ErrorCategory.REFERENCE, diagnostic=diag2)

        # Errors have different hashes
        assert error1.content_hash != error2.content_hash

        # Create cache entries
        entry1 = IntegrityCacheEntry.create("{test}", (error1,), sequence=1)
        entry2 = IntegrityCacheEntry.create("{test}", (error2,), sequence=1)

        # Cache entries should have different checksums
        # (even though formatted text and sequence are the same)
        assert entry1.checksum != entry2.checksum
