# mypy: ignore-errors
from __future__ import annotations

import contextlib

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.diagnostics import (
    ErrorCategory,
    FrozenFluentError,
)
from ftllexengine.integrity import CacheCorruptionError
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

class TestCorruptionDetectionStrictMode:
    """Test corruption detection in strict mode (fail-fast)."""

    def test_strict_mode_raises_on_corruption(self) -> None:
        """strict=True raises CacheCorruptionError on checksum mismatch."""
        cache = IntegrityCache(strict=True)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

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
            cache.get("msg", None, None, "en", use_isolating=True)

        assert "corruption detected" in str(exc_info.value).lower()
        assert exc_info.value.context is not None
        assert exc_info.value.context.component == "cache"

    def test_strict_mode_corruption_counter_incremented(self) -> None:
        """Corruption detection increments corruption_detected counter."""
        cache = IntegrityCache(strict=True)
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

        with contextlib.suppress(CacheCorruptionError):
            cache.get("msg", None, None, "en", use_isolating=True)

        stats = cache.get_stats()
        assert stats["corruption_detected"] == 1

class TestCorruptionDetectionNonStrictMode:
    """Test corruption detection in non-strict mode (silent eviction)."""

    def test_non_strict_evicts_corrupted_entry(self) -> None:
        """strict=False silently evicts corrupted entry."""
        cache = IntegrityCache(strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

        # Verify entry exists
        assert cache.get("msg", None, None, "en", use_isolating=True) is not None

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
        result = cache.get("msg", None, None, "en", use_isolating=True)
        assert result is None

        # Entry was evicted
        stats = cache.get_stats()
        assert stats["size"] == 0
        assert stats["corruption_detected"] == 1

    def test_non_strict_records_miss_on_corruption(self) -> None:
        """Corrupted entry results in cache miss."""
        cache = IntegrityCache(strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())

        # First get is a hit
        cache.get("msg", None, None, "en", use_isolating=True)
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
        cache.get("msg", None, None, "en", use_isolating=True)
        stats = cache.get_stats()
        assert stats["misses"] == 1  # Corruption triggers miss

class TestKeyBindingConfusion:
    """Cover the key-binding confusion check (lines 652-670).

    The key-binding check fires when an entry's stored key_hash doesn't match
    the hash of the lookup key.  This is distinct from a checksum mismatch:
    the entry is internally consistent (verify() passes) but is stored under
    the wrong key slot — a sign of active tampering or memory corruption.

    Strategy: put an entry under key B, inject it into the slot for key A,
    then call get(key A).  verify() passes (entry_b is internally valid) but
    the key_hash bound to key B != _compute_key_hash(key A).
    """

    @staticmethod
    def _inject_key_confused_entry(cache: IntegrityCache) -> None:
        """Put msg-b, then move its entry into the msg-a slot."""
        cache.put("msg-b", None, None, "en", use_isolating=True, formatted="Hello B", errors=())
        key_b: tuple = ("msg-b", (), None, "en", True)
        key_a: tuple = ("msg-a", (), None, "en", True)
        # Inject entry_b under key_a — checksum is valid but key_hash is wrong
        cache._cache[key_a] = cache._cache[key_b]

    def test_key_confusion_strict_raises(self) -> None:
        """strict=True raises CacheCorruptionError on key-binding mismatch."""
        cache = IntegrityCache(strict=True)
        self._inject_key_confused_entry(cache)

        with pytest.raises(CacheCorruptionError) as exc_info:
            cache.get("msg-a", None, None, "en", use_isolating=True)

        assert "key confusion" in str(exc_info.value).lower()
        assert exc_info.value.context is not None
        assert exc_info.value.context.component == "cache"
        assert exc_info.value.context.operation == "get"

    def test_key_confusion_strict_increments_counter(self) -> None:
        """Key-binding confusion increments corruption_detected counter."""
        cache = IntegrityCache(strict=True)
        self._inject_key_confused_entry(cache)

        with contextlib.suppress(CacheCorruptionError):
            cache.get("msg-a", None, None, "en", use_isolating=True)

        assert cache.get_stats()["corruption_detected"] == 1

    def test_key_confusion_non_strict_returns_none(self) -> None:
        """strict=False evicts the confused entry and returns None."""
        cache = IntegrityCache(strict=False)
        self._inject_key_confused_entry(cache)

        result = cache.get("msg-a", None, None, "en", use_isolating=True)

        assert result is None
        stats = cache.get_stats()
        assert stats["corruption_detected"] == 1
        assert stats["misses"] == 1

    def test_key_confusion_non_strict_evicts_entry(self) -> None:
        """Non-strict key confusion removes the confused entry from the cache."""
        cache = IntegrityCache(strict=False)
        self._inject_key_confused_entry(cache)

        key_a: tuple = ("msg-a", (), None, "en", True)
        assert key_a in cache._cache  # Injected entry is present

        cache.get("msg-a", None, None, "en", use_isolating=True)

        assert key_a not in cache._cache
