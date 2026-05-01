# mypy: ignore-errors
from __future__ import annotations

from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    ErrorCategory,
    FrozenErrorContext,
    FrozenFluentError,
)
from ftllexengine.runtime.cache import (
    IntegrityCache,
    IntegrityCacheEntry,
    _estimate_error_weight,
)

# Sentinel key_hash for unit tests that verify checksum mechanics but do not
# need meaningful key binding (all-zeros = "unbound test entry").
_NO_KEY_HASH: bytes = b"\x00" * 8

# ============================================================================
# CHECKSUM VERIFICATION TESTS
# ============================================================================



class TestIntegrityCacheEntryContentHash:
    """Test IntegrityCacheEntry checksum computation with error.content_hash."""

    def test_compute_checksum_uses_error_content_hash(self) -> None:
        """_compute_checksum uses error.content_hash when available."""
        error = FrozenFluentError("Test error", ErrorCategory.REFERENCE)
        entry = IntegrityCacheEntry.create(
            "formatted text", (error,), sequence=1, key_hash=_NO_KEY_HASH
        )
        assert entry.checksum is not None
        assert len(entry.checksum) == 16  # BLAKE2b-128
        assert entry.verify() is True

    def test_compute_checksum_with_multiple_errors_content_hash(self) -> None:
        """_compute_checksum uses content_hash for multiple errors."""
        errors = (
            FrozenFluentError("Error 1", ErrorCategory.REFERENCE),
            FrozenFluentError("Error 2", ErrorCategory.RESOLUTION),
            FrozenFluentError("Error 3", ErrorCategory.CYCLIC),
        )
        entry = IntegrityCacheEntry.create(
            "formatted text", errors, sequence=1, key_hash=_NO_KEY_HASH
        )
        assert entry.checksum is not None
        assert entry.verify() is True

    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=50)
    def test_property_checksum_deterministic_with_errors(self, error_count: int) -> None:
        """PROPERTY: Checksum is deterministic; each entry validates against itself.

        Checksums include metadata (created_at, sequence) for complete audit trail
        integrity, so two independently created entries with the same content will
        have different checksums. Each entry does self-validate correctly.
        """
        errors = tuple(
            FrozenFluentError(f"Error {i}", ErrorCategory.REFERENCE)
            for i in range(error_count)
        )
        entry = IntegrityCacheEntry.create("formatted", errors, sequence=1, key_hash=_NO_KEY_HASH)
        assert entry.verify() is True
        entry2 = IntegrityCacheEntry.create("formatted", errors, sequence=1, key_hash=_NO_KEY_HASH)
        assert entry2.verify() is True
        event(f"error_count={error_count}")

    def test_cache_put_get_with_frozen_errors(self) -> None:
        """Cache operations work correctly with FrozenFluentError.content_hash."""
        cache = IntegrityCache(strict=False)
        errors = (
            FrozenFluentError("Reference error", ErrorCategory.REFERENCE),
            FrozenFluentError("Resolution error", ErrorCategory.RESOLUTION),
        )
        cache.put("msg", None, None, "en", use_isolating=True, formatted="formatted text", errors=errors)
        entry = cache.get("msg", None, None, "en", use_isolating=True)
        assert entry is not None
        assert entry.formatted == "formatted text"
        assert entry.errors == errors
        assert entry.verify() is True

class TestIntegrityCacheAuditLogDisabled:
    """Test get_audit_log() returns empty tuple when audit logging is disabled."""

    def test_get_audit_log_returns_empty_when_disabled_by_default(self) -> None:
        """get_audit_log() returns empty tuple when audit disabled (default)."""
        cache = IntegrityCache(strict=False)
        cache.put("msg1", None, None, "en", use_isolating=True, formatted="result1", errors=())
        cache.get("msg1", None, None, "en", use_isolating=True)
        cache.put("msg2", None, None, "en", use_isolating=True, formatted="result2", errors=())
        audit_log = cache.get_audit_log()
        assert audit_log == ()
        assert isinstance(audit_log, tuple)

    def test_get_audit_log_returns_empty_when_disabled_explicit(self) -> None:
        """get_audit_log() returns empty tuple when enable_audit=False explicitly."""
        cache = IntegrityCache(enable_audit=False, strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="result", errors=())
        cache.get("msg", None, None, "en", use_isolating=True)
        assert cache.get_audit_log() == ()

    @given(
        st.integers(min_value=1, max_value=20),
        st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=30)
    def test_property_audit_log_always_empty_when_disabled(
        self, put_count: int, get_count: int
    ) -> None:
        """PROPERTY: get_audit_log() always returns empty tuple when disabled."""
        cache = IntegrityCache(enable_audit=False, strict=False)
        for i in range(put_count):
            cache.put(f"msg{i}", None, None, "en", use_isolating=True, formatted=f"result{i}", errors=())
        for i in range(get_count):
            cache.get(f"msg{i % put_count}", None, None, "en", use_isolating=True)
        audit_log = cache.get_audit_log()
        assert audit_log == ()
        assert len(audit_log) == 0
        event(f"put_count={put_count}")

class TestIntegrityCacheAuditLogEnabled:
    """Test get_audit_log() returns tuple of entries when audit logging is enabled."""

    def test_get_audit_log_returns_tuple_when_enabled(self) -> None:
        """get_audit_log() returns tuple with entries when enable_audit=True."""
        cache = IntegrityCache(enable_audit=True, strict=False)
        cache.put("msg1", None, None, "en", use_isolating=True, formatted="result1", errors=())
        cache.get("msg1", None, None, "en", use_isolating=True)
        cache.get("msg2", None, None, "en", use_isolating=True)  # Miss
        audit_log = cache.get_audit_log()
        assert isinstance(audit_log, tuple)
        assert len(audit_log) >= 3  # PUT + HIT + MISS

    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=20)
    def test_property_audit_log_returns_tuple_when_enabled(self, op_count: int) -> None:
        """PROPERTY: get_audit_log() returns tuple of at least op_count entries."""
        cache = IntegrityCache(enable_audit=True, strict=False)
        for i in range(op_count):
            cache.put(f"msg{i}", None, None, "en", use_isolating=True, formatted=f"result{i}", errors=())
        audit_log = cache.get_audit_log()
        assert isinstance(audit_log, tuple)
        assert len(audit_log) >= op_count
        event(f"op_count={op_count}")

class TestIntegrityCachePropertyGetters:
    """Test property getters for complete coverage."""

    def test_corruption_detected_property(self) -> None:
        """corruption_detected property reflects detected corruption count."""
        cache = IntegrityCache(strict=False)
        assert cache.corruption_detected == 0

        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())
        key = next(iter(cache._cache.keys()))
        original_entry = cache._cache[key]
        corrupted = IntegrityCacheEntry(
            formatted="Corrupted!",
            errors=original_entry.errors,
            checksum=original_entry.checksum,
            created_at=original_entry.created_at,
            sequence=original_entry.sequence,
            key_hash=original_entry.key_hash,
        )
        cache._cache[key] = corrupted
        cache.get("msg", None, None, "en", use_isolating=True)
        assert cache.corruption_detected == 1

    def test_write_once_property(self) -> None:
        """write_once property reflects constructor argument."""
        assert IntegrityCache(write_once=False, strict=False).write_once is False
        assert IntegrityCache(write_once=True, strict=False).write_once is True

    def test_strict_property(self) -> None:
        """strict property reflects constructor argument."""
        assert IntegrityCache(strict=False).strict is False
        assert IntegrityCache(strict=True).strict is True

    @given(st.booleans(), st.booleans())
    @settings(max_examples=4)
    def test_property_write_once_strict_reflect_constructor(
        self, write_once: bool, strict: bool
    ) -> None:
        """PROPERTY: write_once and strict properties reflect constructor args."""
        cache = IntegrityCache(write_once=write_once, strict=strict)
        assert cache.write_once == write_once
        assert cache.strict == strict
        wo = "write_once" if write_once else "normal"
        event(f"mode={wo}")

    def test_corruption_detected_accumulates_across_multiple(self) -> None:
        """corruption_detected accumulates across multiple corruption events."""
        cache = IntegrityCache(strict=False)
        cache.put("msg1", None, None, "en", use_isolating=True, formatted="One", errors=())
        cache.put("msg2", None, None, "en", use_isolating=True, formatted="Two", errors=())
        cache.put("msg3", None, None, "en", use_isolating=True, formatted="Three", errors=())
        for key in list(cache._cache.keys()):
            entry = cache._cache[key]
            cache._cache[key] = IntegrityCacheEntry(
                formatted="Corrupted",
                errors=entry.errors,
                checksum=entry.checksum,
                created_at=entry.created_at,
                sequence=entry.sequence,
                key_hash=entry.key_hash,
            )
        cache.get("msg1", None, None, "en", use_isolating=True)
        assert cache.corruption_detected == 1
        cache.get("msg2", None, None, "en", use_isolating=True)
        assert cache.corruption_detected == 2
        cache.get("msg3", None, None, "en", use_isolating=True)
        assert cache.corruption_detected == 3

    def test_error_bloat_skips_property(self) -> None:
        """error_bloat_skips property reflects excess-error-count skip count."""
        cache = IntegrityCache(strict=False, max_errors_per_entry=2)
        errors = tuple(
            FrozenFluentError(f"err-{i}", ErrorCategory.REFERENCE) for i in range(3)
        )
        assert cache.error_bloat_skips == 0

        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=errors)
        assert cache.error_bloat_skips == 1

    def test_combined_weight_skips_property_initial_zero(self) -> None:
        """combined_weight_skips property starts at zero."""
        cache = IntegrityCache(strict=False)
        assert cache.combined_weight_skips == 0

    def test_combined_weight_skips_property_incremented(self) -> None:
        """combined_weight_skips property reflects combined-weight skip count."""
        # max_entry_weight=200: formatted (100 chars) passes check 1,
        # but combined with error overhead (100 base + 150 msg = 250), total=350 fails.
        cache = IntegrityCache(strict=False, max_entry_weight=200)
        error = FrozenFluentError("x" * 150, ErrorCategory.REFERENCE)
        assert cache.combined_weight_skips == 0

        cache.put("msg", None, None, "en", use_isolating=True, formatted="x" * 100, errors=(error,))
        assert cache.combined_weight_skips == 1

    def test_write_once_conflicts_property_initial_zero(self) -> None:
        """write_once_conflicts property starts at zero."""
        cache = IntegrityCache(write_once=True, strict=False)
        assert cache.write_once_conflicts == 0

    def test_write_once_conflicts_property_incremented(self) -> None:
        """write_once_conflicts property reflects true conflict count."""
        cache = IntegrityCache(write_once=True, strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())
        assert cache.write_once_conflicts == 0

        cache.put("msg", None, None, "en", use_isolating=True, formatted="World", errors=())
        assert cache.write_once_conflicts == 1

class TestIntegrityCacheEdgeCases:
    """Additional edge cases for complete coverage."""

    def test_entry_with_empty_errors_differs_from_entry_with_error(self) -> None:
        """Entries with empty vs non-empty errors tuples have distinct checksums."""
        error = FrozenFluentError("Test", ErrorCategory.REFERENCE)
        entry1 = IntegrityCacheEntry.create("text", (), sequence=1, key_hash=_NO_KEY_HASH)
        entry2 = IntegrityCacheEntry.create("text", (error,), sequence=2, key_hash=_NO_KEY_HASH)
        assert entry1.checksum != entry2.checksum

    def test_cache_stats_includes_all_integrity_fields(self) -> None:
        """get_stats() includes corruption_detected, write_once, strict, audit_enabled."""
        cache = IntegrityCache(write_once=True, strict=True, enable_audit=False)
        stats = cache.get_stats()
        assert "corruption_detected" in stats
        assert "write_once" in stats
        assert "strict" in stats
        assert "audit_enabled" in stats
        assert stats["corruption_detected"] == 0
        assert stats["write_once"] is True
        assert stats["strict"] is True
        assert stats["audit_enabled"] is False

    def test_multiple_operations_exercise_all_properties(self) -> None:
        """Exercise all properties through multiple cache operations."""
        cache = IntegrityCache(
            maxsize=10, write_once=False, strict=False, enable_audit=False
        )
        for i in range(5):
            cache.put(f"msg{i}", None, None, "en", use_isolating=True, formatted=f"result{i}", errors=())
        assert cache.size == 5
        assert cache.maxsize == 10
        assert cache.hits == 0
        assert cache.misses == 0
        assert cache.corruption_detected == 0
        assert cache.write_once is False
        assert cache.strict is False
        for i in range(5):
            entry = cache.get(f"msg{i}", None, None, "en", use_isolating=True)
            assert entry is not None
        assert cache.hits == 5
        assert cache.get_audit_log() == ()

class TestEstimateErrorWeightWithContext:
    """Test _estimate_error_weight with errors containing FrozenErrorContext.

    Covers the branch where error.context fields are processed.
    """

    def test_error_weight_with_context(self) -> None:
        """Error with context includes all context field lengths in weight."""
        context = FrozenErrorContext(
            input_value="test_input_value",
            locale_code="en_US",
            parse_type="number",
            fallback_value="{!NUMBER}",
        )
        error = FrozenFluentError(
            "Parse error", ErrorCategory.FORMATTING, context=context
        )
        weight = _estimate_error_weight(error)
        expected_weight = (
            100  # _ERROR_BASE_OVERHEAD
            + len("Parse error")
            + len("test_input_value")
            + len("en_US")
            + len("number")
            + len("{!NUMBER}")
        )
        assert weight == expected_weight

    def test_error_weight_without_context(self) -> None:
        """Error without context only includes base overhead plus message length."""
        error = FrozenFluentError("Simple error", ErrorCategory.REFERENCE)
        weight = _estimate_error_weight(error)
        assert weight == 100 + len("Simple error")

    @given(
        input_val=st.text(min_size=0, max_size=100),
        locale=st.text(min_size=0, max_size=20),
        parse_type=st.sampled_from(
            ["", "currency", "date", "datetime", "decimal", "number"]
        ),
        fallback=st.text(min_size=0, max_size=50),
    )
    @settings(max_examples=50)
    def test_property_error_weight_accounts_for_all_context_fields(
        self,
        input_val: str,
        locale: str,
        parse_type: str,
        fallback: str,
    ) -> None:
        """PROPERTY: Error weight correctly accounts for all context field lengths."""
        context = FrozenErrorContext(
            input_value=input_val,
            locale_code=locale,
            parse_type=parse_type,
            fallback_value=fallback,
        )
        error = FrozenFluentError("Test", ErrorCategory.FORMATTING, context=context)
        weight = _estimate_error_weight(error)
        expected = (
            100
            + len("Test")
            + len(input_val)
            + len(locale)
            + len(parse_type)
            + len(fallback)
        )
        assert weight == expected
        event(f"context_len={len(input_val) + len(locale)}")

class TestEstimateErrorWeightDiagnosticBranches:
    """Test _estimate_error_weight with diagnostic fields including resolution_path."""

    def test_error_weight_diagnostic_without_resolution_path(self) -> None:
        """Error with diagnostic but no resolution_path skips path length processing."""
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message="Reference error",
        )
        error = FrozenFluentError(
            "Message not found", ErrorCategory.REFERENCE, diagnostic=diagnostic
        )
        weight = _estimate_error_weight(error)
        expected = 100 + len("Message not found") + len("Reference error")
        assert weight == expected

    def test_error_weight_diagnostic_with_resolution_path(self) -> None:
        """Error with diagnostic and resolution_path includes path element lengths."""
        diagnostic = Diagnostic(
            code=DiagnosticCode.CYCLIC_REFERENCE,
            message="Reference error",
            resolution_path=("message1", "term1", "message2"),
        )
        error = FrozenFluentError(
            "Circular reference", ErrorCategory.CYCLIC, diagnostic=diagnostic
        )
        weight = _estimate_error_weight(error)
        expected = (
            100
            + len("Circular reference")
            + len("Reference error")
            + len("message1")
            + len("term1")
            + len("message2")
        )
        assert weight == expected

    def test_error_weight_diagnostic_with_all_optional_fields(self) -> None:
        """Error with diagnostic containing all optional fields includes them in weight."""
        diagnostic = Diagnostic(
            code=DiagnosticCode.INVALID_ARGUMENT,
            message="Invalid argument",
            hint="Use NUMBER() function",
            help_url="https://example.com/help",
            function_name="CURRENCY",
            argument_name="minimumFractionDigits",
            expected_type="int",
            received_type="str",
            ftl_location="message.ftl:42",
        )
        error = FrozenFluentError(
            "Function call error", ErrorCategory.FORMATTING, diagnostic=diagnostic
        )
        weight = _estimate_error_weight(error)
        expected = (
            100
            + len("Function call error")
            + len("Invalid argument")
            + len("Use NUMBER() function")
            + len("https://example.com/help")
            + len("CURRENCY")
            + len("minimumFractionDigits")
            + len("int")
            + len("str")
            + len("message.ftl:42")
        )
        assert weight == expected

class TestCacheEntryVerifyWithCorruptedError:
    """Test IntegrityCacheEntry.verify() when error.verify_integrity() returns False.

    Exercises the defense-in-depth check where entry verification recurses into
    each contained error's own verify_integrity() method.
    """

    def test_verify_returns_false_when_error_message_corrupted(self) -> None:
        """IntegrityCacheEntry.verify() returns False when error is memory-corrupted.

        Simulates memory corruption: error._message is changed without updating
        the stored _content_hash, causing verify_integrity() to return False.
        """
        error = FrozenFluentError("Test error 2", ErrorCategory.REFERENCE)
        entry = IntegrityCacheEntry.create("Result", (error,), sequence=1, key_hash=_NO_KEY_HASH)
        object.__setattr__(error, "_frozen", False)
        object.__setattr__(error, "_message", "corrupted message")
        object.__setattr__(error, "_frozen", True)
        assert error.verify_integrity() is False
        assert entry.verify() is False

    def test_verify_detects_corruption_defense_in_depth(self) -> None:
        """IntegrityCacheEntry.verify() provides defense-in-depth error verification."""
        error = FrozenFluentError("Original message", ErrorCategory.REFERENCE)
        entry = IntegrityCacheEntry.create("Result", (error,), sequence=1, key_hash=_NO_KEY_HASH)
        assert entry.verify() is True
        object.__setattr__(error, "_frozen", False)
        object.__setattr__(error, "_message", "Corrupted by memory error")
        object.__setattr__(error, "_frozen", True)
        assert error.verify_integrity() is False
        assert entry.verify() is False

    def test_verify_returns_true_when_all_errors_valid(self) -> None:
        """IntegrityCacheEntry.verify() returns True when all errors pass integrity."""
        errors = (
            FrozenFluentError("Error 1", ErrorCategory.REFERENCE),
            FrozenFluentError("Error 2", ErrorCategory.FORMATTING),
            FrozenFluentError("Error 3", ErrorCategory.CYCLIC),
        )
        entry = IntegrityCacheEntry.create("Result", errors, sequence=1, key_hash=_NO_KEY_HASH)
        assert entry.verify() is True

    def test_verify_returns_false_if_any_error_corrupted(self) -> None:
        """IntegrityCacheEntry.verify() returns False if any single error is corrupted."""
        error1 = FrozenFluentError("Error 1", ErrorCategory.REFERENCE)
        error2 = FrozenFluentError("Error 2", ErrorCategory.FORMATTING)
        error3 = FrozenFluentError("Error 3", ErrorCategory.CYCLIC)
        entry = IntegrityCacheEntry.create(
            "Result", (error1, error2, error3), sequence=1, key_hash=_NO_KEY_HASH
        )
        object.__setattr__(error2, "_frozen", False)
        object.__setattr__(error2, "_content_hash", b"bad_hash_xxxxxxx")
        object.__setattr__(error2, "_frozen", True)
        assert entry.verify() is False

class TestErrorWeightAndVerifyIntegration:
    """Integration tests combining error weight estimation and verification."""

    def test_large_error_with_context_and_diagnostic(self) -> None:
        """Error with both context and diagnostic computes correct weight."""
        context = FrozenErrorContext(
            input_value="very long input value that would increase weight significantly",
            locale_code="en_US",
            parse_type="currency",
            fallback_value="{!CURRENCY}",
        )
        diagnostic = Diagnostic(
            code=DiagnosticCode.PARSE_DECIMAL_FAILED,
            message="Failed to parse number",
            hint="Check number format",
            resolution_path=("step1", "step2", "step3"),
        )
        error = FrozenFluentError(
            "Complex error message",
            ErrorCategory.FORMATTING,
            diagnostic=diagnostic,
            context=context,
        )
        weight = _estimate_error_weight(error)
        expected = (
            100
            + len("Complex error message")
            + len("Failed to parse number")
            + len("Check number format")
            + len("step1") + len("step2") + len("step3")
            + len("very long input value that would increase weight significantly")
            + len("en_US")
            + len("currency")
            + len("{!CURRENCY}")
        )
        assert weight == expected
        assert error.verify_integrity() is True
        entry = IntegrityCacheEntry.create("Result", (error,), sequence=1, key_hash=_NO_KEY_HASH)
        assert entry.verify() is True

    @given(
        message=st.text(min_size=1, max_size=100),
        input_val=st.text(min_size=0, max_size=50),
        locale=st.text(min_size=0, max_size=10),
    )
    @settings(max_examples=50)
    def test_property_weight_estimation_deterministic(
        self, message: str, input_val: str, locale: str
    ) -> None:
        """PROPERTY: Weight estimation is deterministic and positive."""
        context = FrozenErrorContext(
            input_value=input_val,
            locale_code=locale,
            parse_type="number",
            fallback_value="fallback",
        )
        error = FrozenFluentError(message, ErrorCategory.FORMATTING, context=context)
        weight1 = _estimate_error_weight(error)
        weight2 = _estimate_error_weight(error)
        assert weight1 == weight2
        assert weight1 > 0
        min_weight = len(message) + len(input_val) + len(locale) + len("number") + len("fallback")
        assert weight1 >= min_weight
        event(f"weight={weight1}")
