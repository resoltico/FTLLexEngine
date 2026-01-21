"""Tests for IntegrityCache checksum verification, write-once, and audit logging.

Financial-grade integrity verification tests:
- BLAKE2b-128 checksum computation and verification
- Corruption detection (strict/non-strict modes)
- Write-once semantics (strict/non-strict modes)
- Audit logging operations
"""

from __future__ import annotations

import contextlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.integrity import CacheCorruptionError, WriteConflictError
from ftllexengine.runtime.cache import IntegrityCache, IntegrityCacheEntry, WriteLogEntry

# ============================================================================
# CHECKSUM VERIFICATION TESTS
# ============================================================================


class TestChecksumComputation:
    """Test BLAKE2b-128 checksum computation."""

    def test_checksum_computed_on_create(self) -> None:
        """IntegrityCacheEntry.create() computes checksum."""
        entry = IntegrityCacheEntry.create("Hello", (), sequence=1)
        assert entry.checksum is not None
        assert len(entry.checksum) == 16  # BLAKE2b-128 = 16 bytes

    def test_different_metadata_different_checksum(self) -> None:
        """Different metadata (sequence, timestamp) produces different checksums.

        Checksums now include created_at and sequence for complete audit trail integrity.
        Identical content with different metadata produces different checksums.
        """
        entry1 = IntegrityCacheEntry.create("Hello", (), sequence=1)
        entry2 = IntegrityCacheEntry.create("Hello", (), sequence=2)
        # Checksums differ because sequence is different (and created_at likely differs)
        assert entry1.checksum != entry2.checksum

    def test_different_content_different_checksum(self) -> None:
        """Different content produces different checksums."""
        entry1 = IntegrityCacheEntry.create("Hello", (), sequence=1)
        entry2 = IntegrityCacheEntry.create("World", (), sequence=1)
        assert entry1.checksum != entry2.checksum

    def test_errors_affect_checksum(self) -> None:
        """Errors are included in checksum computation."""
        error = FrozenFluentError("Test error", ErrorCategory.REFERENCE)
        entry_no_errors = IntegrityCacheEntry.create("Hello", (), sequence=1)
        entry_with_errors = IntegrityCacheEntry.create("Hello", (error,), sequence=1)
        assert entry_no_errors.checksum != entry_with_errors.checksum

    def test_verify_returns_true_for_valid_entry(self) -> None:
        """verify() returns True for uncorrupted entry."""
        entry = IntegrityCacheEntry.create("Hello", (), sequence=1)
        assert entry.verify() is True

    def test_entry_to_tuple_preserves_content(self) -> None:
        """to_tuple() returns correct (formatted, errors) pair."""
        errors = (FrozenFluentError("Test", ErrorCategory.REFERENCE),)
        entry = IntegrityCacheEntry.create("Hello", errors, sequence=1)
        assert entry.to_tuple() == ("Hello", errors)

    @given(st.text(min_size=0, max_size=1000))
    @settings(max_examples=50)
    def test_checksum_validates_correctly(self, text: str) -> None:
        """PROPERTY: Checksum validation is deterministic for same entry.

        Checksums now include metadata (created_at, sequence) for complete audit
        trail integrity. Different entries with same content will have different
        checksums due to different timestamps. We verify that each entry's
        checksum validates correctly.
        """
        entry = IntegrityCacheEntry.create(text, (), sequence=1)
        # Each entry should validate its own checksum correctly
        assert entry.verify() is True


# ============================================================================
# CORRUPTION DETECTION TESTS
# ============================================================================


class TestCorruptionDetectionStrictMode:
    """Test corruption detection in strict mode (fail-fast)."""

    def test_strict_mode_raises_on_corruption(self) -> None:
        """strict=True raises CacheCorruptionError on checksum mismatch."""
        cache = IntegrityCache(strict=True)
        cache.put("msg", None, None, "en", True, "Hello", ())

        # Simulate corruption by directly modifying internal state
        key = next(iter(cache._cache.keys()))
        original_entry = cache._cache[key]

        # Create corrupted entry with wrong checksum
        corrupted = IntegrityCacheEntry(
            formatted="Corrupted!",
            errors=original_entry.errors,
            checksum=original_entry.checksum,  # Wrong checksum for new content
            created_at=original_entry.created_at,
            sequence=original_entry.sequence,
        )
        cache._cache[key] = corrupted

        with pytest.raises(CacheCorruptionError) as exc_info:
            cache.get("msg", None, None, "en", True)

        assert "corruption detected" in str(exc_info.value).lower()
        assert exc_info.value.context is not None
        assert exc_info.value.context.component == "cache"

    def test_strict_mode_corruption_counter_incremented(self) -> None:
        """Corruption detection increments corruption_detected counter."""
        cache = IntegrityCache(strict=True)
        cache.put("msg", None, None, "en", True, "Hello", ())

        # Corrupt entry
        key = next(iter(cache._cache.keys()))
        entry = cache._cache[key]
        corrupted = IntegrityCacheEntry(
            formatted="Corrupted",
            errors=entry.errors,
            checksum=entry.checksum,
            created_at=entry.created_at,
            sequence=entry.sequence,
        )
        cache._cache[key] = corrupted

        with contextlib.suppress(CacheCorruptionError):
            cache.get("msg", None, None, "en", True)

        stats = cache.get_stats()
        assert stats["corruption_detected"] == 1


class TestCorruptionDetectionNonStrictMode:
    """Test corruption detection in non-strict mode (silent eviction)."""

    def test_non_strict_evicts_corrupted_entry(self) -> None:
        """strict=False silently evicts corrupted entry."""
        cache = IntegrityCache(strict=False)
        cache.put("msg", None, None, "en", True, "Hello", ())

        # Verify entry exists
        assert cache.get("msg", None, None, "en", True) is not None

        # Corrupt entry
        key = next(iter(cache._cache.keys()))
        entry = cache._cache[key]
        corrupted = IntegrityCacheEntry(
            formatted="Corrupted",
            errors=entry.errors,
            checksum=entry.checksum,
            created_at=entry.created_at,
            sequence=entry.sequence,
        )
        cache._cache[key] = corrupted

        # Get returns None (not an exception)
        result = cache.get("msg", None, None, "en", True)
        assert result is None

        # Entry was evicted
        stats = cache.get_stats()
        assert stats["size"] == 0
        assert stats["corruption_detected"] == 1

    def test_non_strict_records_miss_on_corruption(self) -> None:
        """Corrupted entry results in cache miss."""
        cache = IntegrityCache(strict=False)
        cache.put("msg", None, None, "en", True, "Hello", ())

        # First get is a hit
        cache.get("msg", None, None, "en", True)
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 0

        # Corrupt entry
        key = next(iter(cache._cache.keys()))
        entry = cache._cache[key]
        corrupted = IntegrityCacheEntry(
            formatted="Corrupted",
            errors=entry.errors,
            checksum=entry.checksum,
            created_at=entry.created_at,
            sequence=entry.sequence,
        )
        cache._cache[key] = corrupted

        # Second get is a miss (corruption detected, entry evicted)
        cache.get("msg", None, None, "en", True)
        stats = cache.get_stats()
        assert stats["misses"] == 1  # Corruption triggers miss


# ============================================================================
# WRITE-ONCE SEMANTICS TESTS
# ============================================================================


class TestWriteOnceStrictMode:
    """Test write-once semantics in strict mode."""

    def test_write_once_allows_first_write(self) -> None:
        """First write to a key succeeds."""
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", True, "Hello", ())

        entry = cache.get("msg", None, None, "en", True)
        assert entry is not None
        assert entry.formatted == "Hello"

    def test_write_once_strict_raises_on_second_write(self) -> None:
        """Second write to same key raises WriteConflictError in strict mode."""
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", True, "Hello", ())

        with pytest.raises(WriteConflictError) as exc_info:
            cache.put("msg", None, None, "en", True, "World", ())

        assert "write-once violation" in str(exc_info.value).lower()
        assert exc_info.value.existing_seq == 1
        assert exc_info.value.new_seq == 1  # Sequence before attempted put

    def test_write_once_preserves_original_value(self) -> None:
        """Write-once rejection preserves original cached value."""
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", True, "Original", ())

        with contextlib.suppress(WriteConflictError):
            cache.put("msg", None, None, "en", True, "Updated", ())

        entry = cache.get("msg", None, None, "en", True)
        assert entry is not None
        assert entry.formatted == "Original"


class TestWriteOnceNonStrictMode:
    """Test write-once semantics in non-strict mode."""

    def test_write_once_non_strict_silently_skips(self) -> None:
        """Second write silently skipped in non-strict mode."""
        cache = IntegrityCache(write_once=True, strict=False)
        cache.put("msg", None, None, "en", True, "Hello", ())

        # No exception raised
        cache.put("msg", None, None, "en", True, "World", ())

        # Original value preserved
        entry = cache.get("msg", None, None, "en", True)
        assert entry is not None
        assert entry.formatted == "Hello"

    def test_write_once_allows_different_keys(self) -> None:
        """Write-once allows writes to different keys."""
        cache = IntegrityCache(write_once=True, strict=False)
        cache.put("msg1", None, None, "en", True, "First", ())
        cache.put("msg2", None, None, "en", True, "Second", ())

        entry1 = cache.get("msg1", None, None, "en", True)
        entry2 = cache.get("msg2", None, None, "en", True)
        assert entry1 is not None
        assert entry1.formatted == "First"
        assert entry2 is not None
        assert entry2.formatted == "Second"


class TestWriteOnceDisabled:
    """Test behavior when write-once is disabled (default)."""

    def test_default_allows_overwrites(self) -> None:
        """Default cache allows overwriting entries."""
        cache = IntegrityCache(write_once=False, strict=False)
        cache.put("msg", None, None, "en", True, "Hello", ())
        cache.put("msg", None, None, "en", True, "World", ())

        entry = cache.get("msg", None, None, "en", True)
        assert entry is not None
        assert entry.formatted == "World"


# ============================================================================
# AUDIT LOGGING TESTS
# ============================================================================


class TestAuditLogging:
    """Test audit logging functionality."""

    def test_audit_disabled_by_default(self) -> None:
        """Audit logging is disabled by default."""
        cache = IntegrityCache()
        cache.put("msg", None, None, "en", True, "Hello", ())
        cache.get("msg", None, None, "en", True)

        stats = cache.get_stats()
        assert stats["audit_enabled"] is False
        assert stats["audit_entries"] == 0

    def test_audit_enabled_records_operations(self) -> None:
        """Audit logging records operations when enabled."""
        cache = IntegrityCache(enable_audit=True, strict=False)
        cache.put("msg", None, None, "en", True, "Hello", ())
        cache.get("msg", None, None, "en", True)
        cache.get("msg2", None, None, "en", True)  # Miss

        stats = cache.get_stats()
        assert stats["audit_enabled"] is True
        assert stats["audit_entries"] >= 3  # PUT + HIT + MISS

    def test_audit_log_entry_structure(self) -> None:
        """Audit log entries have correct structure."""
        cache = IntegrityCache(enable_audit=True, strict=False)
        cache.put("msg", None, None, "en", True, "Hello", ())

        # Access internal audit log for verification
        audit_log = cache._audit_log
        assert audit_log is not None
        assert len(audit_log) >= 1

        entry = audit_log[0]  # pylint: disable=unsubscriptable-object
        assert isinstance(entry, WriteLogEntry)
        assert entry.operation == "PUT"
        assert isinstance(entry.key_hash, str)
        assert isinstance(entry.timestamp, float)
        assert entry.sequence >= 0
        assert isinstance(entry.checksum_hex, str)

    def test_audit_log_records_all_operation_types(self) -> None:
        """Audit log records HIT, MISS, PUT, EVICT operations."""
        cache = IntegrityCache(maxsize=2, enable_audit=True, strict=False)

        # PUT 3 entries to trigger eviction
        cache.put("msg1", None, None, "en", True, "One", ())
        cache.put("msg2", None, None, "en", True, "Two", ())
        cache.put("msg3", None, None, "en", True, "Three", ())  # Evicts msg1

        # HIT
        cache.get("msg2", None, None, "en", True)

        # MISS
        cache.get("nonexistent", None, None, "en", True)

        audit_log = cache._audit_log
        assert audit_log is not None

        # pylint: disable=not-an-iterable
        operations = {entry.operation for entry in audit_log}
        assert "PUT" in operations
        assert "EVICT" in operations
        assert "HIT" in operations
        assert "MISS" in operations

    def test_audit_log_max_entries_enforced(self) -> None:
        """Audit log respects max_audit_entries limit."""
        cache = IntegrityCache(enable_audit=True, max_audit_entries=5, strict=False)

        # Generate more operations than max_audit_entries
        for i in range(10):
            cache.put(f"msg{i}", None, None, "en", True, f"Value {i}", ())

        audit_log = cache._audit_log
        assert audit_log is not None
        assert len(audit_log) <= 5

    def test_audit_log_not_cleared_on_cache_clear(self) -> None:
        """Audit log preserved when cache is cleared (historical record)."""
        cache = IntegrityCache(enable_audit=True, strict=False)
        cache.put("msg", None, None, "en", True, "Hello", ())

        audit_log_before = len(cache._audit_log or [])
        cache.clear()
        audit_log_after = len(cache._audit_log or [])

        assert audit_log_after >= audit_log_before

    def test_audit_records_write_once_rejection(self) -> None:
        """Audit log records WRITE_ONCE_REJECTED operations."""
        cache = IntegrityCache(write_once=True, enable_audit=True, strict=False)
        cache.put("msg", None, None, "en", True, "First", ())
        cache.put("msg", None, None, "en", True, "Second", ())  # Rejected

        audit_log = cache._audit_log
        assert audit_log is not None

        # pylint: disable=not-an-iterable
        operations = [entry.operation for entry in audit_log]
        assert "WRITE_ONCE_REJECTED" in operations


class TestAuditLoggingCorruption:
    """Test audit logging of corruption events."""

    def test_audit_records_corruption(self) -> None:
        """Audit log records CORRUPTION operations."""
        cache = IntegrityCache(enable_audit=True, strict=False)
        cache.put("msg", None, None, "en", True, "Hello", ())

        # Corrupt entry
        key = next(iter(cache._cache.keys()))
        entry = cache._cache[key]
        corrupted = IntegrityCacheEntry(
            formatted="Corrupted",
            errors=entry.errors,
            checksum=entry.checksum,
            created_at=entry.created_at,
            sequence=entry.sequence,
        )
        cache._cache[key] = corrupted

        # Trigger corruption detection
        cache.get("msg", None, None, "en", True)

        audit_log = cache._audit_log
        assert audit_log is not None

        # pylint: disable=not-an-iterable
        operations = [entry.operation for entry in audit_log]
        assert "CORRUPTION" in operations


# ============================================================================
# SEQUENCE NUMBER TESTS
# ============================================================================


class TestSequenceNumbers:
    """Test monotonically increasing sequence numbers."""

    def test_sequence_increments_on_put(self) -> None:
        """Sequence number increments with each put."""
        cache = IntegrityCache(strict=False)
        cache.put("msg1", None, None, "en", True, "One", ())
        cache.put("msg2", None, None, "en", True, "Two", ())
        cache.put("msg3", None, None, "en", True, "Three", ())

        entry1 = cache.get("msg1", None, None, "en", True)
        entry2 = cache.get("msg2", None, None, "en", True)
        entry3 = cache.get("msg3", None, None, "en", True)

        assert entry1 is not None
        assert entry1.sequence == 1
        assert entry2 is not None
        assert entry2.sequence == 2
        assert entry3 is not None
        assert entry3.sequence == 3

    def test_sequence_not_reset_on_clear(self) -> None:
        """Sequence number continues after cache clear (audit trail integrity)."""
        cache = IntegrityCache(strict=False)
        cache.put("msg1", None, None, "en", True, "One", ())
        cache.put("msg2", None, None, "en", True, "Two", ())

        stats_before = cache.get_stats()
        assert stats_before["sequence"] == 2

        cache.clear()

        cache.put("msg3", None, None, "en", True, "Three", ())

        entry = cache.get("msg3", None, None, "en", True)
        assert entry is not None
        assert entry.sequence == 3


# ============================================================================
# CONCURRENT INTEGRITY TESTS
# ============================================================================


class TestConcurrentIntegrity:
    """Test integrity under concurrent access."""

    def test_concurrent_puts_maintain_integrity(self) -> None:
        """Concurrent puts produce valid checksums."""
        cache = IntegrityCache(maxsize=100, strict=False)

        def put_entry(i: int) -> None:
            cache.put(f"msg{i}", None, None, "en", True, f"Value {i}", ())

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(put_entry, i) for i in range(100)]
            for future in as_completed(futures):
                future.result()

        # All entries should have valid checksums
        for i in range(100):
            entry = cache.get(f"msg{i}", None, None, "en", True)
            if entry is not None:
                assert entry.verify(), f"Entry msg{i} failed checksum verification"

    def test_write_once_thread_safety(self) -> None:
        """Write-once semantics are thread-safe."""
        cache = IntegrityCache(write_once=True, strict=False)
        success_count = 0
        lock = threading.Lock()

        def try_put() -> None:
            nonlocal success_count
            try:
                cache.put("msg", None, None, "en", True, "Value", ())
                with lock:
                    success_count += 1
            except WriteConflictError:
                pass  # Expected for some threads

        threads = [threading.Thread(target=try_put) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Only one entry should exist
        stats = cache.get_stats()
        assert stats["size"] == 1


# ============================================================================
# STATS VERIFICATION TESTS
# ============================================================================


class TestIntegrityStats:
    """Test integrity-related statistics."""

    def test_stats_includes_integrity_fields(self) -> None:
        """get_stats() includes all integrity-related fields."""
        cache = IntegrityCache(
            write_once=True,
            strict=True,
            enable_audit=True,
        )

        stats = cache.get_stats()

        # Verify integrity-specific fields exist
        assert "corruption_detected" in stats
        assert "sequence" in stats
        assert "write_once" in stats
        assert "strict" in stats
        assert "audit_enabled" in stats
        assert "audit_entries" in stats

        # Verify types
        assert isinstance(stats["corruption_detected"], int)
        assert isinstance(stats["sequence"], int)
        assert isinstance(stats["write_once"], bool)
        assert isinstance(stats["strict"], bool)
        assert isinstance(stats["audit_enabled"], bool)
        assert isinstance(stats["audit_entries"], int)

        # Verify values reflect configuration
        assert stats["write_once"] is True
        assert stats["strict"] is True
        assert stats["audit_enabled"] is True

    def test_corruption_counter_accumulates(self) -> None:
        """corruption_detected counter accumulates across multiple corruptions."""
        cache = IntegrityCache(strict=False)

        for i in range(3):
            cache.put(f"msg{i}", None, None, "en", True, f"Value {i}", ())

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
        for i in range(3):
            cache.get(f"msg{i}", None, None, "en", True)

        stats = cache.get_stats()
        assert stats["corruption_detected"] == 3
