# mypy: ignore-errors
# mypy: ignore-errors
from __future__ import annotations

import threading
from datetime import UTC
from decimal import Decimal

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import (
    ErrorCategory,
    FrozenFluentError,
)
from ftllexengine.integrity import WriteConflictError
from ftllexengine.runtime.cache import (
    IntegrityCache,
    IntegrityCacheEntry,
)

# Sentinel key_hash for unit tests that verify checksum mechanics but do not
# need meaningful key binding (all-zeros = "unbound test entry").
_NO_KEY_HASH: bytes = b"\x00" * 8

# ============================================================================
# CHECKSUM VERIFICATION TESTS
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
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

        # Second put with IDENTICAL content should succeed (idempotent)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

        # Verify entry unchanged
        entry = cache.get("msg", None, None, "en", use_isolating=True)
        assert entry is not None
        assert entry.formatted == "Hello"
        assert entry.sequence == 1  # Original sequence preserved

    def test_different_content_raises_conflict(self) -> None:
        """Different content raises WriteConflictError in strict mode."""
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

        with pytest.raises(WriteConflictError):
            cache.put("msg", None, None, "en", use_isolating=True, formatted="World", errors=())

    def test_idempotent_write_counter_incremented(self) -> None:
        """Idempotent writes increment the idempotent_writes counter."""
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

        # Perform idempotent writes
        for _ in range(5):
            cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

        stats = cache.get_stats()
        assert stats["idempotent_writes"] == 5

    def test_idempotent_writes_property(self) -> None:
        """idempotent_writes property returns correct count."""
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

        assert cache.idempotent_writes == 0

        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())
        assert cache.idempotent_writes == 1

    def test_idempotent_with_errors(self) -> None:
        """Idempotent detection includes errors in comparison."""
        error = FrozenFluentError("Test error", ErrorCategory.REFERENCE)
        cache = IntegrityCache(write_once=True, strict=True)

        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=(error,))

        # Same content WITH same error = idempotent
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=(error,))
        assert cache.idempotent_writes == 1

        # Same text but WITHOUT error = conflict
        with pytest.raises(WriteConflictError):
            cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

    def test_idempotent_non_strict_mode(self) -> None:
        """Idempotent writes also work in non-strict mode."""
        cache = IntegrityCache(write_once=True, strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

        # Idempotent write
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

        # Different content silently ignored (non-strict)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="World", errors=())

        stats = cache.get_stats()
        assert stats["idempotent_writes"] == 1  # Only one idempotent

        # Original value preserved
        entry = cache.get("msg", None, None, "en", use_isolating=True)
        assert entry is not None
        assert entry.formatted == "Hello"

    def test_idempotent_counter_preserved_on_clear(self) -> None:
        """Idempotent counter is cumulative across clear() calls."""
        cache = IntegrityCache(write_once=True, strict=True)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())  # Idempotent

        assert cache.idempotent_writes == 1

        # clear() removes entries but does NOT reset cumulative metrics.
        cache.clear()

        assert cache.idempotent_writes == 1

    def test_audit_records_idempotent_writes(self) -> None:
        """Audit log records WRITE_ONCE_IDEMPOTENT operations."""
        cache = IntegrityCache(write_once=True, strict=True, enable_audit=True)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())  # Idempotent

        audit_log = cache._audit_log
        assert audit_log is not None

        # pylint: disable=not-an-iterable
        operations = [entry.operation for entry in audit_log]
        assert "WRITE_ONCE_IDEMPOTENT" in operations

    def test_audit_records_conflict(self) -> None:
        """Audit log records WRITE_ONCE_CONFLICT for different content."""
        cache = IntegrityCache(write_once=True, strict=False, enable_audit=True)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())
        cache.put("msg", None, None, "en", use_isolating=True, formatted="World", errors=())  # Conflict (non-strict)

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
                cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())
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
                cache.put("msg", None, None, "en", use_isolating=True, formatted=f"Value {i}", errors=())
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

class TestDatetimeTimezoneCollisionPrevention:
    """Test that datetime objects with different timezones produce distinct cache keys.

    Two datetime objects can represent the same UTC instant but have different tzinfo.
    Python's datetime equality considers them equal, but they format to different
    local time strings. The cache must distinguish them.
    """

    def test_same_utc_instant_different_timezone_distinct_keys(self) -> None:
        """Datetimes with same UTC instant but different tzinfo produce distinct keys."""
        from datetime import datetime, timedelta, timezone

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
        from datetime import datetime

        dt_naive = datetime(2024, 1, 1, 12, 0, 0)  # noqa: DTZ001 - naive datetime by design
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
        key_pos = IntegrityCache._make_hashable(Decimal(0))
        key_neg = IntegrityCache._make_hashable(Decimal("-0"))

        # They're equal in Python
        assert Decimal(0) == Decimal("-0")

        # But distinct in cache keys (via str representation)
        assert key_pos != key_neg
        assert key_pos == ("__decimal__", "0")
        assert key_neg == ("__decimal__", "-0")

class TestSequenceMappingABCSupport:
    """Test that Sequence and Mapping ABCs are supported, not just list/tuple/dict."""

    def test_userlist_accepted(self) -> None:
        """UserList (Sequence ABC) is accepted and type-tagged."""
        from collections import UserList

        values = UserList([1, 2, 3])
        result = IntegrityCache._make_hashable(values)

        # Should be tagged as __seq__ (generic Sequence)
        assert isinstance(result, tuple)
        assert result[0] == "__seq__"
        # Inner values are type-tagged
        assert result[1] == (("__int__", 1), ("__int__", 2), ("__int__", 3))

    def test_chainmap_accepted(self) -> None:
        """ChainMap (Mapping ABC) is accepted with __mapping__ tag."""
        from collections import ChainMap

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
