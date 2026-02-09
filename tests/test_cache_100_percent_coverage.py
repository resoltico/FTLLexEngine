"""Tests to achieve 100% coverage for IntegrityCache.

This test module specifically targets uncovered lines to achieve complete
coverage of src/ftllexengine/runtime/cache.py.

Target lines:
- Line 178: error.content_hash handling in _compute_checksum
- Lines 567-570: get_audit_log() when audit disabled
- Lines 749-750, 755, 760: Property getters (corruption_detected, write_once, strict)
"""

from __future__ import annotations

from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.cache import IntegrityCache, IntegrityCacheEntry


class TestIntegrityCacheEntryContentHash:
    """Test IntegrityCacheEntry checksum computation with error.content_hash."""

    def test_compute_checksum_uses_error_content_hash(self) -> None:
        """_compute_checksum uses error.content_hash when available (line 175-176)."""
        # Create FrozenFluentError which has content_hash attribute
        error = FrozenFluentError("Test error", ErrorCategory.REFERENCE)

        # Create entry with error that has content_hash
        entry = IntegrityCacheEntry.create("formatted text", (error,), sequence=1)

        # Verify entry was created successfully with checksum
        assert entry.checksum is not None
        assert len(entry.checksum) == 16  # BLAKE2b-128

        # Verify entry validates correctly
        assert entry.verify() is True

    def test_compute_checksum_without_content_hash(self) -> None:
        """_compute_checksum handles errors without content_hash (line 178)."""

        # Create custom error without content_hash attribute
        class CustomError(Exception):
            """Custom error without content_hash."""

            def __init__(self, message: str) -> None:
                super().__init__(message)
                self.message = message

            def __str__(self) -> str:
                return self.message

        # Create custom error
        custom_error = CustomError("Custom error message")

        # Create entry with error that does NOT have content_hash
        # This will trigger the else branch on line 178
        entry = IntegrityCacheEntry.create(
            "formatted text", (custom_error,), sequence=1  # type: ignore[arg-type]
        )

        # Verify entry was created successfully
        assert entry.checksum is not None
        assert len(entry.checksum) == 16  # BLAKE2b-128

        # Verify entry validates correctly
        assert entry.verify() is True

    def test_compute_checksum_with_multiple_errors_content_hash(self) -> None:
        """_compute_checksum uses content_hash for multiple errors."""
        # Create multiple FrozenFluentErrors
        error1 = FrozenFluentError("Error 1", ErrorCategory.REFERENCE)
        error2 = FrozenFluentError("Error 2", ErrorCategory.RESOLUTION)
        error3 = FrozenFluentError("Error 3", ErrorCategory.CYCLIC)

        # Create entry with multiple errors
        entry = IntegrityCacheEntry.create(
            "formatted text", (error1, error2, error3), sequence=1
        )

        # Verify entry was created and validates
        assert entry.checksum is not None
        assert entry.verify() is True

    @given(
        st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=50)
    def test_property_checksum_deterministic_with_errors(
        self, error_count: int
    ) -> None:
        """PROPERTY: Checksum is deterministic when all inputs match.

        Checksums now include metadata (created_at, sequence) for complete audit
        trail integrity. To test determinism, we verify the same entry validates
        correctly, not that different entries have the same checksum.
        """
        # Create multiple FrozenFluentErrors
        errors = tuple(
            FrozenFluentError(f"Error {i}", ErrorCategory.REFERENCE)
            for i in range(error_count)
        )

        # Create entry with errors
        entry = IntegrityCacheEntry.create("formatted", errors, sequence=1)

        # Checksum should be valid (deterministic computation matches stored value)
        assert entry.verify() is True

        # Creating second entry with SAME sequence but at different time
        # produces different checksum (created_at differs)
        entry2 = IntegrityCacheEntry.create("formatted", errors, sequence=1)
        # Checksums differ because created_at timestamps are different
        # This is correct behavior for audit trail integrity
        assert entry.verify() is True
        assert entry2.verify() is True
        event(f"error_count={error_count}")

    def test_cache_put_get_with_frozen_errors(self) -> None:
        """Cache operations work correctly with FrozenFluentError.content_hash."""
        cache = IntegrityCache(strict=False)

        # Create FrozenFluentErrors
        error1 = FrozenFluentError("Reference error", ErrorCategory.REFERENCE)
        error2 = FrozenFluentError("Resolution error", ErrorCategory.RESOLUTION)
        errors = (error1, error2)

        # Put entry with FrozenFluentErrors
        cache.put("msg", None, None, "en", True, "formatted text", errors)

        # Get entry back
        entry = cache.get("msg", None, None, "en", True)
        assert entry is not None
        assert entry.formatted == "formatted text"
        assert entry.errors == errors
        assert entry.verify() is True


class TestIntegrityCacheAuditLogDisabled:
    """Test get_audit_log() when audit logging is disabled."""

    def test_get_audit_log_returns_empty_when_disabled(self) -> None:
        """get_audit_log() returns empty tuple when audit disabled (line 569)."""
        # Create cache with audit disabled (default)
        cache = IntegrityCache(strict=False)

        # Perform some operations
        cache.put("msg1", None, None, "en", True, "result1", ())
        cache.get("msg1", None, None, "en", True)
        cache.put("msg2", None, None, "en", True, "result2", ())

        # get_audit_log() should return empty tuple
        audit_log = cache.get_audit_log()
        assert audit_log == ()
        assert isinstance(audit_log, tuple)
        assert len(audit_log) == 0

    def test_get_audit_log_disabled_explicit(self) -> None:
        """get_audit_log() returns empty tuple when enable_audit=False."""
        cache = IntegrityCache(enable_audit=False, strict=False)

        # Perform operations
        cache.put("msg", None, None, "en", True, "result", ())
        cache.get("msg", None, None, "en", True)

        # Should return empty tuple
        audit_log = cache.get_audit_log()
        assert audit_log == ()

    @given(
        st.integers(min_value=1, max_value=20),
        st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=30)
    def test_property_audit_log_empty_when_disabled(
        self, put_count: int, get_count: int
    ) -> None:
        """PROPERTY: get_audit_log() always returns empty tuple when disabled."""
        cache = IntegrityCache(enable_audit=False, strict=False)

        # Perform many operations
        for i in range(put_count):
            cache.put(f"msg{i}", None, None, "en", True, f"result{i}", ())

        for i in range(get_count):
            cache.get(f"msg{i % put_count}", None, None, "en", True)

        # Audit log should still be empty
        audit_log = cache.get_audit_log()
        assert audit_log == ()
        assert len(audit_log) == 0
        event(f"put_count={put_count}")


class TestIntegrityCacheAuditLogEnabled:
    """Test get_audit_log() when audit logging is enabled."""

    def test_get_audit_log_returns_tuple_when_enabled(self) -> None:
        """get_audit_log() returns tuple of entries when audit enabled (line 570)."""
        # Create cache with audit enabled
        cache = IntegrityCache(enable_audit=True, strict=False)

        # Perform operations
        cache.put("msg1", None, None, "en", True, "result1", ())
        cache.get("msg1", None, None, "en", True)
        cache.get("msg2", None, None, "en", True)  # Miss

        # get_audit_log() should return tuple with entries
        audit_log = cache.get_audit_log()
        assert isinstance(audit_log, tuple)
        assert len(audit_log) >= 3  # PUT + HIT + MISS

    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=20)
    def test_property_audit_log_returns_tuple_when_enabled(self, op_count: int) -> None:
        """PROPERTY: get_audit_log() returns tuple when audit enabled."""
        cache = IntegrityCache(enable_audit=True, strict=False)

        # Perform operations
        for i in range(op_count):
            cache.put(f"msg{i}", None, None, "en", True, f"result{i}", ())

        # get_audit_log() should return tuple
        audit_log = cache.get_audit_log()
        assert isinstance(audit_log, tuple)
        assert len(audit_log) >= op_count
        event(f"op_count={op_count}")


class TestIntegrityCachePropertyGetters:
    """Test property getters for complete coverage."""

    def test_corruption_detected_property(self) -> None:
        """corruption_detected property returns counter value (lines 749-750)."""
        cache = IntegrityCache(strict=False)

        # Initially zero
        assert cache.corruption_detected == 0

        # Add entry
        cache.put("msg", None, None, "en", True, "Hello", ())

        # Corrupt entry by directly modifying internal state
        key = next(iter(cache._cache.keys()))
        original_entry = cache._cache[key]
        corrupted = IntegrityCacheEntry(
            formatted="Corrupted!",
            errors=original_entry.errors,
            checksum=original_entry.checksum,
            created_at=original_entry.created_at,
            sequence=original_entry.sequence,
        )
        cache._cache[key] = corrupted

        # Trigger corruption detection
        cache.get("msg", None, None, "en", True)

        # corruption_detected property should reflect detection
        assert cache.corruption_detected == 1

    def test_write_once_property(self) -> None:
        """write_once property returns configuration value (line 755)."""
        # Create cache with write_once=False
        cache_false = IntegrityCache(write_once=False, strict=False)
        assert cache_false.write_once is False

        # Create cache with write_once=True
        cache_true = IntegrityCache(write_once=True, strict=False)
        assert cache_true.write_once is True

    def test_strict_property(self) -> None:
        """strict property returns configuration value (line 760)."""
        # Create cache with strict=False
        cache_false = IntegrityCache(strict=False)
        assert cache_false.strict is False

        # Create cache with strict=True
        cache_true = IntegrityCache(strict=True)
        assert cache_true.strict is True

    @given(st.booleans(), st.booleans())
    @settings(max_examples=4)
    def test_property_write_once_strict_configuration(
        self, write_once: bool, strict: bool
    ) -> None:
        """PROPERTY: write_once and strict properties reflect constructor args."""
        cache = IntegrityCache(write_once=write_once, strict=strict)

        assert cache.write_once == write_once
        assert cache.strict == strict
        wo = "write_once" if write_once else "normal"
        event(f"mode={wo}")

    def test_corruption_detected_accumulates(self) -> None:
        """corruption_detected property accumulates across multiple corruptions."""
        cache = IntegrityCache(strict=False)

        # Add three entries
        cache.put("msg1", None, None, "en", True, "One", ())
        cache.put("msg2", None, None, "en", True, "Two", ())
        cache.put("msg3", None, None, "en", True, "Three", ())

        # Corrupt all entries
        for key in list(cache._cache.keys()):
            entry = cache._cache[key]
            corrupted = IntegrityCacheEntry(
                formatted="Corrupted",
                errors=entry.errors,
                checksum=entry.checksum,
                created_at=entry.created_at,
                sequence=entry.sequence,
            )
            cache._cache[key] = corrupted

        # Trigger corruption detection for each
        cache.get("msg1", None, None, "en", True)
        assert cache.corruption_detected == 1

        cache.get("msg2", None, None, "en", True)
        assert cache.corruption_detected == 2

        cache.get("msg3", None, None, "en", True)
        assert cache.corruption_detected == 3

    def test_properties_thread_safe_access(self) -> None:
        """Property getters use thread-safe lock access."""
        cache = IntegrityCache(write_once=True, strict=True)

        # Access properties (they should acquire lock internally)
        _corruption = cache.corruption_detected
        _write_once = cache.write_once
        _strict = cache.strict

        # Verify values
        assert cache.corruption_detected == 0
        assert cache.write_once is True
        assert cache.strict is True


class TestIntegrityCacheEdgeCases:
    """Additional edge cases for complete coverage."""

    def test_entry_with_empty_errors_tuple(self) -> None:
        """Cache operations work with empty errors tuple."""
        error = FrozenFluentError("Test", ErrorCategory.REFERENCE)
        entry1 = IntegrityCacheEntry.create("text", (), sequence=1)
        entry2 = IntegrityCacheEntry.create("text", (error,), sequence=2)

        # Checksums should differ
        assert entry1.checksum != entry2.checksum

    def test_cache_stats_includes_all_integrity_fields(self) -> None:
        """get_stats() includes corruption_detected and mode flags."""
        cache = IntegrityCache(write_once=True, strict=True, enable_audit=False)

        stats = cache.get_stats()

        # Verify integrity fields present
        assert "corruption_detected" in stats
        assert "write_once" in stats
        assert "strict" in stats
        assert "audit_enabled" in stats

        # Verify values
        assert stats["corruption_detected"] == 0
        assert stats["write_once"] is True
        assert stats["strict"] is True
        assert stats["audit_enabled"] is False

    def test_multiple_operations_all_properties(self) -> None:
        """Exercise all properties through multiple operations."""
        cache = IntegrityCache(
            maxsize=10,
            write_once=False,
            strict=False,
            enable_audit=False,
        )

        # Put some entries
        for i in range(5):
            cache.put(f"msg{i}", None, None, "en", True, f"result{i}", ())

        # Access all properties
        assert cache.size == 5
        assert cache.maxsize == 10
        assert cache.hits == 0
        assert cache.misses == 0
        assert cache.corruption_detected == 0
        assert cache.write_once is False
        assert cache.strict is False

        # Get entries
        for i in range(5):
            entry = cache.get(f"msg{i}", None, None, "en", True)
            assert entry is not None

        assert cache.hits == 5

        # Verify audit log empty
        audit_log = cache.get_audit_log()
        assert audit_log == ()
