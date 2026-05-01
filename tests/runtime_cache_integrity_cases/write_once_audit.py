# mypy: ignore-errors
from __future__ import annotations

import contextlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from ftllexengine.integrity import WriteConflictError
from ftllexengine.runtime.cache import (
    IntegrityCache,
    IntegrityCacheEntry,
    WriteLogEntry,
)

# Sentinel key_hash for unit tests that verify checksum mechanics but do not
# need meaningful key binding (all-zeros = "unbound test entry").
_NO_KEY_HASH: bytes = b"\x00" * 8

# ============================================================================
# CHECKSUM VERIFICATION TESTS
# ============================================================================



class TestWriteOnceStrictMode:
    """Test write-once semantics in strict mode."""

    def test_write_once_allows_first_write(self) -> None:
        """First write to a key succeeds."""
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

        entry = cache.get("msg", None, None, "en", use_isolating=True)
        assert entry is not None
        assert entry.formatted == "Hello"

    def test_write_once_strict_raises_on_second_write(self) -> None:
        """Second write to same key raises WriteConflictError in strict mode."""
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

        with pytest.raises(WriteConflictError) as exc_info:
            cache.put("msg", None, None, "en", use_isolating=True, formatted="World", errors=())

        assert "write-once violation" in str(exc_info.value).lower()
        assert exc_info.value.existing_seq == 1
        assert exc_info.value.new_seq == 2  # Would-be sequence of rejected entry

    def test_write_once_preserves_original_value(self) -> None:
        """Write-once rejection preserves original cached value."""
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Original", errors=())

        with contextlib.suppress(WriteConflictError):
            cache.put("msg", None, None, "en", use_isolating=True, formatted="Updated", errors=())

        entry = cache.get("msg", None, None, "en", use_isolating=True)
        assert entry is not None
        assert entry.formatted == "Original"

    def test_write_once_conflict_counter_incremented_before_raise(self) -> None:
        """write_once_conflicts is incremented before WriteConflictError is raised."""
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

        with contextlib.suppress(WriteConflictError):
            cache.put("msg", None, None, "en", use_isolating=True, formatted="World", errors=())

        # Counter must be observable even after an exception was raised
        assert cache.write_once_conflicts == 1

class TestWriteOnceNonStrictMode:
    """Test write-once semantics in non-strict mode."""

    def test_write_once_non_strict_silently_skips(self) -> None:
        """Second write silently skipped in non-strict mode."""
        cache = IntegrityCache(write_once=True, strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

        # No exception raised
        cache.put("msg", None, None, "en", use_isolating=True, formatted="World", errors=())

        # Original value preserved
        entry = cache.get("msg", None, None, "en", use_isolating=True)
        assert entry is not None
        assert entry.formatted == "Hello"

    def test_write_once_allows_different_keys(self) -> None:
        """Write-once allows writes to different keys."""
        cache = IntegrityCache(write_once=True, strict=False)
        cache.put("msg1", None, None, "en", use_isolating=True, formatted="First", errors=())
        cache.put("msg2", None, None, "en", use_isolating=True, formatted="Second", errors=())

        entry1 = cache.get("msg1", None, None, "en", use_isolating=True)
        entry2 = cache.get("msg2", None, None, "en", use_isolating=True)
        assert entry1 is not None
        assert entry1.formatted == "First"
        assert entry2 is not None
        assert entry2.formatted == "Second"

    def test_write_once_conflict_counter_incremented(self) -> None:
        """True write-once conflicts increment write_once_conflicts counter."""
        cache = IntegrityCache(write_once=True, strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

        # Different content for same key = true conflict
        cache.put("msg", None, None, "en", use_isolating=True, formatted="World", errors=())

        stats = cache.get_stats()
        assert stats["write_once_conflicts"] == 1

    def test_write_once_conflict_counter_multiple(self) -> None:
        """write_once_conflicts accumulates across repeated true conflicts."""
        cache = IntegrityCache(write_once=True, strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

        for i in range(5):
            cache.put("msg", None, None, "en", use_isolating=True, formatted=f"World-{i}", errors=())

        assert cache.write_once_conflicts == 5

    def test_write_once_conflict_not_incremented_for_idempotent(self) -> None:
        """Idempotent writes do NOT increment write_once_conflicts."""
        cache = IntegrityCache(write_once=True, strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())  # Idempotent

        assert cache.write_once_conflicts == 0
        assert cache.idempotent_writes == 1

    def test_write_once_conflict_counter_preserved_on_clear(self) -> None:
        """clear() preserves cumulative write_once_conflicts counter."""
        cache = IntegrityCache(write_once=True, strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())
        cache.put("msg", None, None, "en", use_isolating=True, formatted="World", errors=())  # Conflict

        assert cache.write_once_conflicts == 1
        cache.clear()
        assert cache.write_once_conflicts == 1

class TestWriteOnceDisabled:
    """Test behavior when write-once is disabled (default)."""

    def test_default_allows_overwrites(self) -> None:
        """Default cache allows overwriting entries."""
        cache = IntegrityCache(write_once=False, strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())
        cache.put("msg", None, None, "en", use_isolating=True, formatted="World", errors=())

        entry = cache.get("msg", None, None, "en", use_isolating=True)
        assert entry is not None
        assert entry.formatted == "World"

class TestAuditLogging:
    """Test audit logging functionality."""

    def test_audit_disabled_by_default(self) -> None:
        """Audit logging is disabled by default."""
        cache = IntegrityCache()
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())
        cache.get("msg", None, None, "en", use_isolating=True)

        stats = cache.get_stats()
        assert stats["audit_enabled"] is False
        assert stats["audit_entries"] == 0

    def test_audit_enabled_records_operations(self) -> None:
        """Audit logging records operations when enabled."""
        cache = IntegrityCache(enable_audit=True, strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())
        cache.get("msg", None, None, "en", use_isolating=True)
        cache.get("msg2", None, None, "en", use_isolating=True)  # Miss

        stats = cache.get_stats()
        assert stats["audit_enabled"] is True
        assert stats["audit_entries"] >= 3  # PUT + HIT + MISS

    def test_audit_log_entry_structure(self) -> None:
        """Audit log entries have correct structure."""
        cache = IntegrityCache(enable_audit=True, strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

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
        cache.put("msg1", None, None, "en", use_isolating=True, formatted="One", errors=())
        cache.put("msg2", None, None, "en", use_isolating=True, formatted="Two", errors=())
        cache.put("msg3", None, None, "en", use_isolating=True, formatted="Three", errors=())  # Evicts msg1

        # HIT
        cache.get("msg2", None, None, "en", use_isolating=True)

        # MISS
        cache.get("nonexistent", None, None, "en", use_isolating=True)

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
            cache.put(f"msg{i}", None, None, "en", use_isolating=True, formatted=f"Value {i}", errors=())

        audit_log = cache._audit_log
        assert audit_log is not None
        assert len(audit_log) <= 5

    def test_audit_log_not_cleared_on_cache_clear(self) -> None:
        """Audit log preserved when cache is cleared (historical record)."""
        cache = IntegrityCache(enable_audit=True, strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

        audit_log_before = len(cache._audit_log or [])
        cache.clear()
        audit_log_after = len(cache._audit_log or [])

        assert audit_log_after >= audit_log_before

    def test_audit_records_write_once_rejection(self) -> None:
        """Audit log records WRITE_ONCE_CONFLICT for different content writes."""
        cache = IntegrityCache(write_once=True, enable_audit=True, strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="First", errors=())
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Second", errors=())  # Conflict (different content)

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
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

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
        cache.get("msg", None, None, "en", use_isolating=True)

        audit_log = cache._audit_log
        assert audit_log is not None

        # pylint: disable=not-an-iterable
        operations = [entry.operation for entry in audit_log]
        assert "CORRUPTION" in operations

class TestSequenceNumbers:
    """Test monotonically increasing sequence numbers."""

    def test_sequence_increments_on_put(self) -> None:
        """Sequence number increments with each put."""
        cache = IntegrityCache(strict=False)
        cache.put("msg1", None, None, "en", use_isolating=True, formatted="One", errors=())
        cache.put("msg2", None, None, "en", use_isolating=True, formatted="Two", errors=())
        cache.put("msg3", None, None, "en", use_isolating=True, formatted="Three", errors=())

        entry1 = cache.get("msg1", None, None, "en", use_isolating=True)
        entry2 = cache.get("msg2", None, None, "en", use_isolating=True)
        entry3 = cache.get("msg3", None, None, "en", use_isolating=True)

        assert entry1 is not None
        assert entry1.sequence == 1
        assert entry2 is not None
        assert entry2.sequence == 2
        assert entry3 is not None
        assert entry3.sequence == 3

    def test_sequence_not_reset_on_clear(self) -> None:
        """Sequence number continues after cache clear (audit trail integrity)."""
        cache = IntegrityCache(strict=False)
        cache.put("msg1", None, None, "en", use_isolating=True, formatted="One", errors=())
        cache.put("msg2", None, None, "en", use_isolating=True, formatted="Two", errors=())

        stats_before = cache.get_stats()
        assert stats_before["sequence"] == 2

        cache.clear()

        cache.put("msg3", None, None, "en", use_isolating=True, formatted="Three", errors=())

        entry = cache.get("msg3", None, None, "en", use_isolating=True)
        assert entry is not None
        assert entry.sequence == 3

class TestConcurrentIntegrity:
    """Test integrity under concurrent access."""

    def test_concurrent_puts_maintain_integrity(self) -> None:
        """Concurrent puts produce valid checksums."""
        cache = IntegrityCache(maxsize=100, strict=False)

        def put_entry(i: int) -> None:
            cache.put(f"msg{i}", None, None, "en", use_isolating=True, formatted=f"Value {i}", errors=())

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(put_entry, i) for i in range(100)]
            for future in as_completed(futures):
                future.result()

        # All entries should have valid checksums
        for i in range(100):
            entry = cache.get(f"msg{i}", None, None, "en", use_isolating=True)
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
                cache.put("msg", None, None, "en", use_isolating=True, formatted="Value", errors=())
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
            cache.put(f"msg{i}", None, None, "en", use_isolating=True, formatted=f"Value {i}", errors=())

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
            cache.get(f"msg{i}", None, None, "en", use_isolating=True)

        stats = cache.get_stats()
        assert stats["corruption_detected"] == 3
