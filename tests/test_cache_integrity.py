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
from datetime import UTC

import pytest
from hypothesis import event, given, settings
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
        event(f"text_len={len(text)}")


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
        assert exc_info.value.new_seq == 2  # Would-be sequence of rejected entry

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
        """Audit log records WRITE_ONCE_CONFLICT for different content writes."""
        cache = IntegrityCache(write_once=True, enable_audit=True, strict=False)
        cache.put("msg", None, None, "en", True, "First", ())
        cache.put("msg", None, None, "en", True, "Second", ())  # Conflict (different content)

        audit_log = cache._audit_log
        assert audit_log is not None

        # pylint: disable=not-an-iterable
        operations = [entry.operation for entry in audit_log]
        assert "WRITE_ONCE_CONFLICT" in operations


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


# ============================================================================
# CONTENT HASH TESTS
# ============================================================================


class TestContentHash:
    """Test content-only hash computation for idempotent write detection."""

    def test_content_hash_computed(self) -> None:
        """IntegrityCacheEntry has content_hash property."""
        entry = IntegrityCacheEntry.create("Hello", (), sequence=1)
        content_hash = entry.content_hash
        assert content_hash is not None
        assert len(content_hash) == 16  # BLAKE2b-128

    def test_identical_content_same_hash(self) -> None:
        """Entries with identical content have identical content hashes.

        This is critical for idempotent write detection: concurrent threads
        computing the same formatted result should produce matching content hashes.
        """
        entry1 = IntegrityCacheEntry.create("Hello", (), sequence=1)
        entry2 = IntegrityCacheEntry.create("Hello", (), sequence=2)

        # Full checksums differ (include metadata)
        assert entry1.checksum != entry2.checksum

        # Content hashes are identical
        assert entry1.content_hash == entry2.content_hash

    def test_different_content_different_hash(self) -> None:
        """Entries with different content have different content hashes."""
        entry1 = IntegrityCacheEntry.create("Hello", (), sequence=1)
        entry2 = IntegrityCacheEntry.create("World", (), sequence=1)

        assert entry1.content_hash != entry2.content_hash

    def test_errors_affect_content_hash(self) -> None:
        """Errors are included in content hash computation."""
        error = FrozenFluentError("Test error", ErrorCategory.REFERENCE)
        entry_no_errors = IntegrityCacheEntry.create("Hello", (), sequence=1)
        entry_with_errors = IntegrityCacheEntry.create("Hello", (error,), sequence=1)

        assert entry_no_errors.content_hash != entry_with_errors.content_hash

    @given(st.text(min_size=0, max_size=500))
    @settings(max_examples=30)
    def test_content_hash_deterministic(self, text: str) -> None:
        """PROPERTY: Content hash is deterministic for same content."""
        entry1 = IntegrityCacheEntry.create(text, (), sequence=1)
        entry2 = IntegrityCacheEntry.create(text, (), sequence=999)

        assert entry1.content_hash == entry2.content_hash
        event(f"text_len={len(text)}")


# ============================================================================
# IDEMPOTENT WRITE TESTS
# ============================================================================


class TestIdempotentWrites:
    """Test idempotent write detection for thundering herd scenarios.

    In write_once mode, concurrent writes with identical content (formatted + errors)
    are treated as idempotent operations, not conflicts. This prevents false-positive
    WriteConflictError during thundering herds where multiple threads resolve the
    same message simultaneously.
    """

    def test_idempotent_write_succeeds_in_strict_mode(self) -> None:
        """Identical content is allowed in write_once + strict mode.

        Thundering herd scenario: Multiple threads resolve same message,
        all compute identical results. Second thread should succeed silently.
        """
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", True, "Hello", ())

        # Second put with IDENTICAL content should succeed (idempotent)
        cache.put("msg", None, None, "en", True, "Hello", ())

        # Verify entry unchanged
        entry = cache.get("msg", None, None, "en", True)
        assert entry is not None
        assert entry.formatted == "Hello"
        assert entry.sequence == 1  # Original sequence preserved

    def test_different_content_raises_conflict(self) -> None:
        """Different content raises WriteConflictError in strict mode."""
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", True, "Hello", ())

        with pytest.raises(WriteConflictError):
            cache.put("msg", None, None, "en", True, "World", ())

    def test_idempotent_write_counter_incremented(self) -> None:
        """Idempotent writes increment the idempotent_writes counter."""
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", True, "Hello", ())

        # Perform idempotent writes
        for _ in range(5):
            cache.put("msg", None, None, "en", True, "Hello", ())

        stats = cache.get_stats()
        assert stats["idempotent_writes"] == 5

    def test_idempotent_writes_property(self) -> None:
        """idempotent_writes property returns correct count."""
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", True, "Hello", ())

        assert cache.idempotent_writes == 0

        cache.put("msg", None, None, "en", True, "Hello", ())
        assert cache.idempotent_writes == 1

    def test_idempotent_with_errors(self) -> None:
        """Idempotent detection includes errors in comparison."""
        error = FrozenFluentError("Test error", ErrorCategory.REFERENCE)
        cache = IntegrityCache(write_once=True, strict=True)

        cache.put("msg", None, None, "en", True, "Hello", (error,))

        # Same content WITH same error = idempotent
        cache.put("msg", None, None, "en", True, "Hello", (error,))
        assert cache.idempotent_writes == 1

        # Same text but WITHOUT error = conflict
        with pytest.raises(WriteConflictError):
            cache.put("msg", None, None, "en", True, "Hello", ())

    def test_idempotent_non_strict_mode(self) -> None:
        """Idempotent writes also work in non-strict mode."""
        cache = IntegrityCache(write_once=True, strict=False)
        cache.put("msg", None, None, "en", True, "Hello", ())

        # Idempotent write
        cache.put("msg", None, None, "en", True, "Hello", ())

        # Different content silently ignored (non-strict)
        cache.put("msg", None, None, "en", True, "World", ())

        stats = cache.get_stats()
        assert stats["idempotent_writes"] == 1  # Only one idempotent

        # Original value preserved
        entry = cache.get("msg", None, None, "en", True)
        assert entry is not None
        assert entry.formatted == "Hello"

    def test_idempotent_counter_reset_on_clear(self) -> None:
        """Idempotent counter reset when cache is cleared."""
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", True, "Hello", ())
        cache.put("msg", None, None, "en", True, "Hello", ())  # Idempotent

        assert cache.idempotent_writes == 1

        cache.clear()

        assert cache.idempotent_writes == 0

    def test_audit_records_idempotent_writes(self) -> None:
        """Audit log records WRITE_ONCE_IDEMPOTENT operations."""
        cache = IntegrityCache(write_once=True, strict=True, enable_audit=True)
        cache.put("msg", None, None, "en", True, "Hello", ())
        cache.put("msg", None, None, "en", True, "Hello", ())  # Idempotent

        audit_log = cache._audit_log
        assert audit_log is not None

        # pylint: disable=not-an-iterable
        operations = [entry.operation for entry in audit_log]
        assert "WRITE_ONCE_IDEMPOTENT" in operations

    def test_audit_records_conflict(self) -> None:
        """Audit log records WRITE_ONCE_CONFLICT for different content."""
        cache = IntegrityCache(write_once=True, strict=False, enable_audit=True)
        cache.put("msg", None, None, "en", True, "Hello", ())
        cache.put("msg", None, None, "en", True, "World", ())  # Conflict (non-strict)

        audit_log = cache._audit_log
        assert audit_log is not None

        # pylint: disable=not-an-iterable
        operations = [entry.operation for entry in audit_log]
        assert "WRITE_ONCE_CONFLICT" in operations


class TestIdempotentWritesConcurrency:
    """Test idempotent writes under concurrent access (thundering herd)."""

    def test_concurrent_identical_writes_no_exceptions(self) -> None:
        """Concurrent writes with identical content all succeed (no exceptions).

        This is the thundering herd scenario: multiple threads resolve same
        message simultaneously, all compute identical results. Without idempotent
        detection, N-1 threads would crash with WriteConflictError.
        """
        cache = IntegrityCache(write_once=True, strict=True)
        errors: list[Exception] = []

        def put_identical() -> None:
            try:
                cache.put("msg", None, None, "en", True, "Hello", ())
            except Exception as e:  # pylint: disable=broad-exception-caught
                errors.append(e)

        # 20 threads all trying to cache same value
        threads = [threading.Thread(target=put_identical) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # NO exceptions should occur (all are idempotent or first write)
        assert len(errors) == 0, f"Got {len(errors)} exceptions: {errors}"

        # Only one entry should exist
        stats = cache.get_stats()
        assert stats["size"] == 1

        # Idempotent counter should reflect concurrent writes minus first
        assert stats["idempotent_writes"] == 19  # 20 threads - 1 first write

    def test_concurrent_different_writes_raises_conflicts(self) -> None:
        """Concurrent writes with DIFFERENT content raise conflicts."""
        cache = IntegrityCache(write_once=True, strict=True)
        conflict_count = 0
        lock = threading.Lock()

        def put_different(i: int) -> None:
            nonlocal conflict_count
            try:
                cache.put("msg", None, None, "en", True, f"Value {i}", ())
            except WriteConflictError:
                with lock:
                    conflict_count += 1

        # 10 threads all trying to cache DIFFERENT values
        threads = [threading.Thread(target=put_different, args=(i,)) for i in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Most writes should fail (conflict)
        assert conflict_count >= 9  # At least 9 conflicts (1 succeeds)

        # Only one entry should exist
        stats = cache.get_stats()
        assert stats["size"] == 1


# ============================================================================
# CACHE KEY COLLISION PREVENTION TESTS (v0.93.0)
# ============================================================================


class TestDatetimeTimezoneCollisionPrevention:
    """Test that datetime objects with different timezones produce distinct cache keys.

    Two datetime objects can represent the same UTC instant but have different tzinfo.
    Python's datetime equality considers them equal, but they format to different
    local time strings. The cache must distinguish them.
    """

    def test_same_utc_instant_different_timezone_distinct_keys(self) -> None:
        """Datetimes with same UTC instant but different tzinfo produce distinct keys."""
        from datetime import datetime, timedelta, timezone  # noqa: PLC0415

        # 12:00 UTC
        dt_utc = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        # 07:00 EST (UTC-5) = 12:00 UTC - SAME INSTANT
        dt_est = datetime(2024, 1, 1, 7, 0, 0, tzinfo=timezone(timedelta(hours=-5)))

        # Verify they represent the same instant (Python equality)
        assert dt_utc == dt_est

        # But they should produce DIFFERENT cache keys
        key_utc = IntegrityCache._make_hashable(dt_utc)
        key_est = IntegrityCache._make_hashable(dt_est)
        assert key_utc != key_est

    def test_naive_datetime_distinguished_from_aware(self) -> None:
        """Naive datetime is distinguished from aware datetime."""
        from datetime import datetime  # noqa: PLC0415

        dt_naive = datetime(2024, 1, 1, 12, 0, 0)  # noqa: DTZ001
        dt_aware = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

        key_naive = IntegrityCache._make_hashable(dt_naive)
        key_aware = IntegrityCache._make_hashable(dt_aware)

        # Different tz_key means different cache keys
        assert key_naive != key_aware
        assert isinstance(key_naive, tuple)
        assert isinstance(key_aware, tuple)
        assert key_naive[2] == "__naive__"
        assert key_aware[2] == "UTC"


class TestFloatNegativeZeroCollisionPrevention:
    """Test that 0.0 and -0.0 produce distinct cache keys.

    Python's 0.0 == -0.0, but locale-aware formatting may distinguish them
    (e.g., "-0" vs "0"). The cache must treat them as distinct values.
    """

    def test_zero_and_negative_zero_distinct_keys(self) -> None:
        """0.0 and -0.0 produce distinct cache keys."""
        key_pos = IntegrityCache._make_hashable(0.0)
        key_neg = IntegrityCache._make_hashable(-0.0)

        # They're equal in Python
        assert 0.0 == -0.0

        # But distinct in cache keys (via str representation)
        assert key_pos != key_neg
        assert key_pos == ("__float__", "0.0")
        assert key_neg == ("__float__", "-0.0")


class TestSequenceMappingABCSupport:
    """Test that Sequence and Mapping ABCs are supported, not just list/tuple/dict."""

    def test_userlist_accepted(self) -> None:
        """UserList (Sequence ABC) is accepted and type-tagged."""
        from collections import UserList  # noqa: PLC0415

        values = UserList([1, 2, 3])
        result = IntegrityCache._make_hashable(values)

        # Should be tagged as __seq__ (generic Sequence)
        assert isinstance(result, tuple)
        assert result[0] == "__seq__"
        # Inner values are type-tagged
        assert result[1] == (("__int__", 1), ("__int__", 2), ("__int__", 3))

    def test_chainmap_accepted(self) -> None:
        """ChainMap (Mapping ABC) is accepted with __mapping__ tag."""
        from collections import ChainMap  # noqa: PLC0415

        values: ChainMap[str, int] = ChainMap({"a": 1}, {"b": 2})
        result = IntegrityCache._make_hashable(values)

        # Should be tagged tuple with __mapping__ prefix
        assert isinstance(result, tuple)
        assert result[0] == "__mapping__"
        # ChainMap flattens to view of first-found keys
        inner = result[1]
        assert isinstance(inner, tuple)
        assert ("a", ("__int__", 1)) in inner
        assert ("b", ("__int__", 2)) in inner

    def test_list_still_tagged_as_list(self) -> None:
        """Regular list still uses __list__ tag, not __seq__."""
        result = IntegrityCache._make_hashable([1, 2])
        assert isinstance(result, tuple)
        assert result[0] == "__list__"

    def test_tuple_still_tagged_as_tuple(self) -> None:
        """Regular tuple still uses __tuple__ tag, not __seq__."""
        result = IntegrityCache._make_hashable((1, 2))
        assert isinstance(result, tuple)
        assert result[0] == "__tuple__"
