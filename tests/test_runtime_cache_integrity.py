"""Tests for IntegrityCache checksum verification, write-once, audit logging,
error content hash handling, error weight estimation, and property getters.

Financial-grade integrity verification tests:
- BLAKE2b-128 checksum computation and verification
- Corruption detection (strict/non-strict modes)
- Write-once semantics (strict/non-strict modes)
- Audit logging operations
- error.content_hash usage in checksum computation
- Fallback hashing for non-standard error objects
- _estimate_error_weight with context, diagnostic, and resolution path
- IntegrityCacheEntry.verify() defense-in-depth against corrupted errors
- Property getters (corruption_detected, write_once, strict)
- write_once_conflicts counter (true conflicts, both strict and non-strict)
- combined_weight_skips counter (distinct from oversize_skips and error_bloat_skips)
"""

from __future__ import annotations

import contextlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC
from decimal import Decimal
from typing import Literal

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.constants import DEFAULT_MAX_ENTRY_WEIGHT
from ftllexengine.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    ErrorCategory,
    FrozenErrorContext,
    FrozenFluentError,
)
from ftllexengine.integrity import CacheCorruptionError, WriteConflictError
from ftllexengine.runtime import FluentBundle
from ftllexengine.runtime.cache import (
    IntegrityCache,
    IntegrityCacheEntry,
    WriteLogEntry,
    _estimate_error_weight,
)
from ftllexengine.runtime.cache_config import CacheConfig

# Sentinel key_hash for unit tests that verify checksum mechanics but do not
# need meaningful key binding (all-zeros = "unbound test entry").
_NO_KEY_HASH: bytes = b"\x00" * 8

# ============================================================================
# CHECKSUM VERIFICATION TESTS
# ============================================================================


class TestChecksumComputation:
    """Test BLAKE2b-128 checksum computation."""

    def test_checksum_computed_on_create(self) -> None:
        """IntegrityCacheEntry.create() computes checksum."""
        entry = IntegrityCacheEntry.create("Hello", (), sequence=1, key_hash=_NO_KEY_HASH)
        assert entry.checksum is not None
        assert len(entry.checksum) == 16  # BLAKE2b-128 = 16 bytes

    def test_different_metadata_different_checksum(self) -> None:
        """Different metadata (sequence, timestamp) produces different checksums.

        Checksums now include created_at and sequence for complete audit trail integrity.
        Identical content with different metadata produces different checksums.
        """
        entry1 = IntegrityCacheEntry.create("Hello", (), sequence=1, key_hash=_NO_KEY_HASH)
        entry2 = IntegrityCacheEntry.create("Hello", (), sequence=2, key_hash=_NO_KEY_HASH)
        # Checksums differ because sequence is different (and created_at likely differs)
        assert entry1.checksum != entry2.checksum

    def test_different_content_different_checksum(self) -> None:
        """Different content produces different checksums."""
        entry1 = IntegrityCacheEntry.create("Hello", (), sequence=1, key_hash=_NO_KEY_HASH)
        entry2 = IntegrityCacheEntry.create("World", (), sequence=1, key_hash=_NO_KEY_HASH)
        assert entry1.checksum != entry2.checksum

    def test_errors_affect_checksum(self) -> None:
        """Errors are included in checksum computation."""
        error = FrozenFluentError("Test error", ErrorCategory.REFERENCE)
        entry_no_errors = IntegrityCacheEntry.create("Hello", (), sequence=1, key_hash=_NO_KEY_HASH)
        entry_with_errors = IntegrityCacheEntry.create(
            "Hello", (error,), sequence=1, key_hash=_NO_KEY_HASH
        )
        assert entry_no_errors.checksum != entry_with_errors.checksum

    def test_verify_returns_true_for_valid_entry(self) -> None:
        """verify() returns True for uncorrupted entry."""
        entry = IntegrityCacheEntry.create("Hello", (), sequence=1, key_hash=_NO_KEY_HASH)
        assert entry.verify() is True

    def test_entry_as_result_preserves_content(self) -> None:
        """as_result() returns correct (formatted, errors) pair."""
        errors = (FrozenFluentError("Test", ErrorCategory.REFERENCE),)
        entry = IntegrityCacheEntry.create("Hello", errors, sequence=1, key_hash=_NO_KEY_HASH)
        assert entry.as_result() == ("Hello", errors)

    @given(st.text(min_size=0, max_size=1000))
    @settings(max_examples=50)
    def test_checksum_validates_correctly(self, text: str) -> None:
        """PROPERTY: Checksum validation is deterministic for same entry.

        Checksums now include metadata (created_at, sequence) for complete audit
        trail integrity. Different entries with same content will have different
        checksums due to different timestamps. We verify that each entry's
        checksum validates correctly.
        """
        entry = IntegrityCacheEntry.create(text, (), sequence=1, key_hash=_NO_KEY_HASH)
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
            key_hash=original_entry.key_hash,
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
            key_hash=entry.key_hash,
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
            key_hash=entry.key_hash,
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
            key_hash=entry.key_hash,
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

    def test_write_once_conflict_counter_incremented_before_raise(self) -> None:
        """write_once_conflicts is incremented before WriteConflictError is raised."""
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", True, "Hello", ())

        with contextlib.suppress(WriteConflictError):
            cache.put("msg", None, None, "en", True, "World", ())

        # Counter must be observable even after an exception was raised
        assert cache.write_once_conflicts == 1


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

    def test_write_once_conflict_counter_incremented(self) -> None:
        """True write-once conflicts increment write_once_conflicts counter."""
        cache = IntegrityCache(write_once=True, strict=False)
        cache.put("msg", None, None, "en", True, "Hello", ())

        # Different content for same key = true conflict
        cache.put("msg", None, None, "en", True, "World", ())

        stats = cache.get_stats()
        assert stats["write_once_conflicts"] == 1

    def test_write_once_conflict_counter_multiple(self) -> None:
        """write_once_conflicts accumulates across repeated true conflicts."""
        cache = IntegrityCache(write_once=True, strict=False)
        cache.put("msg", None, None, "en", True, "Hello", ())

        for i in range(5):
            cache.put("msg", None, None, "en", True, f"World-{i}", ())

        assert cache.write_once_conflicts == 5

    def test_write_once_conflict_not_incremented_for_idempotent(self) -> None:
        """Idempotent writes do NOT increment write_once_conflicts."""
        cache = IntegrityCache(write_once=True, strict=False)
        cache.put("msg", None, None, "en", True, "Hello", ())
        cache.put("msg", None, None, "en", True, "Hello", ())  # Idempotent

        assert cache.write_once_conflicts == 0
        assert cache.idempotent_writes == 1

    def test_write_once_conflict_counter_preserved_on_clear(self) -> None:
        """clear() preserves cumulative write_once_conflicts counter."""
        cache = IntegrityCache(write_once=True, strict=False)
        cache.put("msg", None, None, "en", True, "Hello", ())
        cache.put("msg", None, None, "en", True, "World", ())  # Conflict

        assert cache.write_once_conflicts == 1
        cache.clear()
        assert cache.write_once_conflicts == 1


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
            key_hash=entry.key_hash,
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
        assert "write_once_conflicts" in stats
        assert "combined_weight_skips" in stats

        # Verify types
        assert isinstance(stats["corruption_detected"], int)
        assert isinstance(stats["sequence"], int)
        assert isinstance(stats["write_once"], bool)
        assert isinstance(stats["strict"], bool)
        assert isinstance(stats["audit_enabled"], bool)
        assert isinstance(stats["audit_entries"], int)
        assert isinstance(stats["write_once_conflicts"], int)
        assert isinstance(stats["combined_weight_skips"], int)

        # Verify values reflect configuration
        assert stats["write_once"] is True
        assert stats["strict"] is True
        assert stats["audit_enabled"] is True
        assert stats["write_once_conflicts"] == 0
        assert stats["combined_weight_skips"] == 0

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
                key_hash=entry.key_hash,
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
        entry = IntegrityCacheEntry.create("Hello", (), sequence=1, key_hash=_NO_KEY_HASH)
        content_hash = entry.content_hash
        assert content_hash is not None
        assert len(content_hash) == 16  # BLAKE2b-128

    def test_identical_content_same_hash(self) -> None:
        """Entries with identical content have identical content hashes.

        This is critical for idempotent write detection: concurrent threads
        computing the same formatted result should produce matching content hashes.
        """
        entry1 = IntegrityCacheEntry.create("Hello", (), sequence=1, key_hash=_NO_KEY_HASH)
        entry2 = IntegrityCacheEntry.create("Hello", (), sequence=2, key_hash=_NO_KEY_HASH)

        # Full checksums differ (include metadata)
        assert entry1.checksum != entry2.checksum

        # Content hashes are identical
        assert entry1.content_hash == entry2.content_hash

    def test_different_content_different_hash(self) -> None:
        """Entries with different content have different content hashes."""
        entry1 = IntegrityCacheEntry.create("Hello", (), sequence=1, key_hash=_NO_KEY_HASH)
        entry2 = IntegrityCacheEntry.create("World", (), sequence=1, key_hash=_NO_KEY_HASH)

        assert entry1.content_hash != entry2.content_hash

    def test_errors_affect_content_hash(self) -> None:
        """Errors are included in content hash computation."""
        error = FrozenFluentError("Test error", ErrorCategory.REFERENCE)
        entry_no_errors = IntegrityCacheEntry.create("Hello", (), sequence=1, key_hash=_NO_KEY_HASH)
        entry_with_errors = IntegrityCacheEntry.create(
            "Hello", (error,), sequence=1, key_hash=_NO_KEY_HASH
        )

        assert entry_no_errors.content_hash != entry_with_errors.content_hash

    @given(st.text(min_size=0, max_size=500))
    @settings(max_examples=30)
    def test_content_hash_deterministic(self, text: str) -> None:
        """PROPERTY: Content hash is deterministic for same content."""
        entry1 = IntegrityCacheEntry.create(text, (), sequence=1, key_hash=_NO_KEY_HASH)
        entry2 = IntegrityCacheEntry.create(text, (), sequence=999, key_hash=_NO_KEY_HASH)

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

    def test_idempotent_counter_preserved_on_clear(self) -> None:
        """Idempotent counter is cumulative across clear() calls."""
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", True, "Hello", ())
        cache.put("msg", None, None, "en", True, "Hello", ())  # Idempotent

        assert cache.idempotent_writes == 1

        # clear() removes entries but does NOT reset cumulative metrics.
        cache.clear()

        assert cache.idempotent_writes == 1

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


class TestDecimalNegativeZeroCollisionPrevention:
    """Test that Decimal("0") and Decimal("-0") produce distinct cache keys.

    Python's Decimal("0") == Decimal("-0"), but locale-aware formatting may
    distinguish them (e.g., "-0" vs "0"). The cache must treat them as distinct.
    """

    def test_zero_and_negative_zero_distinct_keys(self) -> None:
        """Decimal("0") and Decimal("-0") produce distinct cache keys."""
        key_pos = IntegrityCache._make_hashable(Decimal("0"))
        key_neg = IntegrityCache._make_hashable(Decimal("-0"))

        # They're equal in Python
        assert Decimal("0") == Decimal("-0")

        # But distinct in cache keys (via str representation)
        assert key_pos != key_neg
        assert key_pos == ("__decimal__", "0")
        assert key_neg == ("__decimal__", "-0")


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


# ============================================================================
# ENTRY CONTENT HASH AND CHECKSUM COMPUTATION
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
        cache.put("msg", None, None, "en", True, "formatted text", errors)
        entry = cache.get("msg", None, None, "en", True)
        assert entry is not None
        assert entry.formatted == "formatted text"
        assert entry.errors == errors
        assert entry.verify() is True


# ============================================================================
# AUDIT LOG PUBLIC API (get_audit_log)
# ============================================================================


class TestIntegrityCacheAuditLogDisabled:
    """Test get_audit_log() returns empty tuple when audit logging is disabled."""

    def test_get_audit_log_returns_empty_when_disabled_by_default(self) -> None:
        """get_audit_log() returns empty tuple when audit disabled (default)."""
        cache = IntegrityCache(strict=False)
        cache.put("msg1", None, None, "en", True, "result1", ())
        cache.get("msg1", None, None, "en", True)
        cache.put("msg2", None, None, "en", True, "result2", ())
        audit_log = cache.get_audit_log()
        assert audit_log == ()
        assert isinstance(audit_log, tuple)

    def test_get_audit_log_returns_empty_when_disabled_explicit(self) -> None:
        """get_audit_log() returns empty tuple when enable_audit=False explicitly."""
        cache = IntegrityCache(enable_audit=False, strict=False)
        cache.put("msg", None, None, "en", True, "result", ())
        cache.get("msg", None, None, "en", True)
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
            cache.put(f"msg{i}", None, None, "en", True, f"result{i}", ())
        for i in range(get_count):
            cache.get(f"msg{i % put_count}", None, None, "en", True)
        audit_log = cache.get_audit_log()
        assert audit_log == ()
        assert len(audit_log) == 0
        event(f"put_count={put_count}")


class TestIntegrityCacheAuditLogEnabled:
    """Test get_audit_log() returns tuple of entries when audit logging is enabled."""

    def test_get_audit_log_returns_tuple_when_enabled(self) -> None:
        """get_audit_log() returns tuple with entries when enable_audit=True."""
        cache = IntegrityCache(enable_audit=True, strict=False)
        cache.put("msg1", None, None, "en", True, "result1", ())
        cache.get("msg1", None, None, "en", True)
        cache.get("msg2", None, None, "en", True)  # Miss
        audit_log = cache.get_audit_log()
        assert isinstance(audit_log, tuple)
        assert len(audit_log) >= 3  # PUT + HIT + MISS

    @given(st.integers(min_value=1, max_value=10))
    @settings(max_examples=20)
    def test_property_audit_log_returns_tuple_when_enabled(self, op_count: int) -> None:
        """PROPERTY: get_audit_log() returns tuple of at least op_count entries."""
        cache = IntegrityCache(enable_audit=True, strict=False)
        for i in range(op_count):
            cache.put(f"msg{i}", None, None, "en", True, f"result{i}", ())
        audit_log = cache.get_audit_log()
        assert isinstance(audit_log, tuple)
        assert len(audit_log) >= op_count
        event(f"op_count={op_count}")


# ============================================================================
# PROPERTY GETTERS (corruption_detected, write_once, strict)
# ============================================================================


class TestIntegrityCachePropertyGetters:
    """Test property getters for complete coverage."""

    def test_corruption_detected_property(self) -> None:
        """corruption_detected property reflects detected corruption count."""
        cache = IntegrityCache(strict=False)
        assert cache.corruption_detected == 0

        cache.put("msg", None, None, "en", True, "Hello", ())
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
        cache.get("msg", None, None, "en", True)
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
        cache.put("msg1", None, None, "en", True, "One", ())
        cache.put("msg2", None, None, "en", True, "Two", ())
        cache.put("msg3", None, None, "en", True, "Three", ())
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
        cache.get("msg1", None, None, "en", True)
        assert cache.corruption_detected == 1
        cache.get("msg2", None, None, "en", True)
        assert cache.corruption_detected == 2
        cache.get("msg3", None, None, "en", True)
        assert cache.corruption_detected == 3

    def test_error_bloat_skips_property(self) -> None:
        """error_bloat_skips property reflects excess-error-count skip count."""
        cache = IntegrityCache(strict=False, max_errors_per_entry=2)
        errors = tuple(
            FrozenFluentError(f"err-{i}", ErrorCategory.REFERENCE) for i in range(3)
        )
        assert cache.error_bloat_skips == 0

        cache.put("msg", None, None, "en", True, "Hello", errors)
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

        cache.put("msg", None, None, "en", True, "x" * 100, (error,))
        assert cache.combined_weight_skips == 1

    def test_write_once_conflicts_property_initial_zero(self) -> None:
        """write_once_conflicts property starts at zero."""
        cache = IntegrityCache(write_once=True, strict=False)
        assert cache.write_once_conflicts == 0

    def test_write_once_conflicts_property_incremented(self) -> None:
        """write_once_conflicts property reflects true conflict count."""
        cache = IntegrityCache(write_once=True, strict=False)
        cache.put("msg", None, None, "en", True, "Hello", ())
        assert cache.write_once_conflicts == 0

        cache.put("msg", None, None, "en", True, "World", ())
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
            cache.put(f"msg{i}", None, None, "en", True, f"result{i}", ())
        assert cache.size == 5
        assert cache.maxsize == 10
        assert cache.hits == 0
        assert cache.misses == 0
        assert cache.corruption_detected == 0
        assert cache.write_once is False
        assert cache.strict is False
        for i in range(5):
            entry = cache.get(f"msg{i}", None, None, "en", True)
            assert entry is not None
        assert cache.hits == 5
        assert cache.get_audit_log() == ()


# ============================================================================
# ERROR WEIGHT ESTIMATION
# ============================================================================


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
        parse_type: Literal["", "currency", "date", "datetime", "decimal", "number"],
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


# ============================================================================
# CACHE ENTRY SIZE LIMIT COVERAGE
# ============================================================================


class TestCacheEntrySizeLimit:
    """IntegrityCache max_entry_weight prevents caching of oversized results."""

    def test_default_max_entry_weight(self) -> None:
        """Default max_entry_weight is DEFAULT_MAX_ENTRY_WEIGHT (10,000 characters)."""
        cache = IntegrityCache(strict=False)
        assert cache.max_entry_weight == DEFAULT_MAX_ENTRY_WEIGHT
        assert cache.max_entry_weight == 10_000

    def test_custom_max_entry_weight(self) -> None:
        """Custom max_entry_weight is stored and returned correctly."""
        cache = IntegrityCache(strict=False, max_entry_weight=1000)
        assert cache.max_entry_weight == 1000

    def test_invalid_max_entry_weight_rejected(self) -> None:
        """Zero and negative max_entry_weight raise ValueError."""
        with pytest.raises(ValueError, match="max_entry_weight must be positive"):
            IntegrityCache(strict=False, max_entry_weight=0)

        with pytest.raises(ValueError, match="max_entry_weight must be positive"):
            IntegrityCache(strict=False, max_entry_weight=-1)

    def test_small_entries_cached(self) -> None:
        """Entries below max_entry_weight are stored and retrievable."""
        cache = IntegrityCache(strict=False, max_entry_weight=1000)

        cache.put("msg", None, None, "en", True, "x" * 100, ())

        assert cache.size == 1
        assert cache.oversize_skips == 0

        cached = cache.get("msg", None, None, "en", True)
        assert cached is not None
        assert cached.as_result() == ("x" * 100, ())

    def test_large_entries_not_cached(self) -> None:
        """Entries exceeding max_entry_weight are skipped and counted."""
        cache = IntegrityCache(strict=False, max_entry_weight=100)

        cache.put("msg", None, None, "en", True, "x" * 200, ())

        assert cache.size == 0
        assert cache.oversize_skips == 1

        cached = cache.get("msg", None, None, "en", True)
        assert cached is None

    def test_boundary_entry_size(self) -> None:
        """Entry exactly at max_entry_weight is cached (inclusive boundary)."""
        cache = IntegrityCache(strict=False, max_entry_weight=100)

        cache.put("msg", None, None, "en", True, "x" * 100, ())

        assert cache.size == 1
        assert cache.oversize_skips == 0

    def test_get_stats_includes_oversize_skips(self) -> None:
        """get_stats() reports oversize_skips and max_entry_weight."""
        cache = IntegrityCache(strict=False, max_entry_weight=50)

        for i in range(5):
            cache.put(f"msg-{i}", None, None, "en", True, "x" * 100, ())

        stats = cache.get_stats()
        assert stats["oversize_skips"] == 5
        assert stats["max_entry_weight"] == 50
        assert stats["size"] == 0

    def test_clear_preserves_oversize_skips(self) -> None:
        """clear() removes entries but preserves cumulative oversize_skips counter."""
        cache = IntegrityCache(strict=False, max_entry_weight=50)

        cache.put("msg", None, None, "en", True, "x" * 100, ())
        assert cache.oversize_skips == 1

        cache.clear()
        assert cache.oversize_skips == 1

    def test_bundle_cache_uses_default_max_entry_weight(self) -> None:
        """FluentBundle's internal cache uses default max_entry_weight."""
        bundle = FluentBundle("en", cache=CacheConfig())
        bundle.add_resource("msg = { $data }")

        small_data = "x" * 100
        bundle.format_pattern("msg", {"data": small_data})

        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] == 1

    @given(st.integers(min_value=1, max_value=1000))
    def test_max_entry_weight_property(self, size: int) -> None:
        """PROPERTY: max_entry_weight is correctly stored and returned."""
        event(f"weight_size={size}")
        cache = IntegrityCache(strict=False, max_entry_weight=size)
        assert cache.max_entry_weight == size

    def test_combined_weight_skips_counter_incremented(self) -> None:
        """Entries skipped due to combined weight increment combined_weight_skips.

        Scenario: formatted string (100 chars) passes check 1 (len <= max_entry_weight=200).
        Error overhead = 100 (base) + 150 (message) = 250. Total = 350 > 200 fails check 3.
        """
        cache = IntegrityCache(strict=False, max_entry_weight=200)
        error = FrozenFluentError("x" * 150, ErrorCategory.REFERENCE)

        cache.put("msg", None, None, "en", True, "x" * 100, (error,))

        stats = cache.get_stats()
        assert stats["combined_weight_skips"] == 1
        assert stats["oversize_skips"] == 0
        assert stats["error_bloat_skips"] == 0
        assert stats["size"] == 0

    def test_combined_weight_skips_distinct_from_oversize_skips(self) -> None:
        """oversize_skips and combined_weight_skips are separate, distinct counters."""
        cache = IntegrityCache(strict=False, max_entry_weight=200)
        heavy_error = FrozenFluentError("x" * 150, ErrorCategory.REFERENCE)

        # Check 1 (oversize): formatted string alone exceeds max_entry_weight
        cache.put("over-msg", None, None, "en", True, "x" * 201, ())

        # Check 3 (combined_weight): formatted OK, but combined total exceeds limit
        cache.put("combined-msg", None, None, "en", True, "x" * 100, (heavy_error,))

        stats = cache.get_stats()
        assert stats["oversize_skips"] == 1
        assert stats["combined_weight_skips"] == 1

    def test_combined_weight_skips_distinct_from_error_bloat_skips(self) -> None:
        """error_bloat_skips and combined_weight_skips are separate, distinct counters."""
        cache = IntegrityCache(strict=False, max_entry_weight=200, max_errors_per_entry=2)
        heavy_error = FrozenFluentError("x" * 150, ErrorCategory.REFERENCE)

        # Check 2 (error_bloat): too many errors by count
        many_errors = tuple(
            FrozenFluentError(f"e-{i}", ErrorCategory.REFERENCE) for i in range(3)
        )
        cache.put("bloat-msg", None, None, "en", True, "Hello", many_errors)

        # Check 3 (combined_weight): error count OK (1 <= 2), combined weight fails
        cache.put("combined-msg", None, None, "en", True, "x" * 100, (heavy_error,))

        stats = cache.get_stats()
        assert stats["error_bloat_skips"] == 1
        assert stats["combined_weight_skips"] == 1

    def test_combined_weight_skips_preserved_on_clear(self) -> None:
        """clear() preserves cumulative combined_weight_skips counter."""
        cache = IntegrityCache(strict=False, max_entry_weight=200)
        error = FrozenFluentError("x" * 150, ErrorCategory.REFERENCE)

        cache.put("msg", None, None, "en", True, "x" * 100, (error,))
        assert cache.combined_weight_skips == 1

        cache.clear()
        assert cache.combined_weight_skips == 1

    def test_get_stats_includes_combined_weight_skips(self) -> None:
        """get_stats() reports combined_weight_skips alongside related skip counters."""
        cache = IntegrityCache(strict=False, max_entry_weight=200)
        error = FrozenFluentError("x" * 150, ErrorCategory.REFERENCE)

        cache.put("msg", None, None, "en", True, "x" * 100, (error,))

        stats = cache.get_stats()
        assert "combined_weight_skips" in stats
        assert stats["combined_weight_skips"] == 1
