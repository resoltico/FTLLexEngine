# mypy: ignore-errors
from __future__ import annotations

from dataclasses import replace
from unittest.mock import patch

import pytest

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.integrity import CacheCorruptionError, IntegrityCheckFailedError
from ftllexengine.runtime.cache import IntegrityCache, IntegrityCacheEntry

_FG = 0
_NO_KEY_HASH: bytes = b"\x00" * 16


def _put(cache: IntegrityCache, message_id: str, formatted: str) -> None:
    cache.put(
        message_id,
        None,
        None,
        "en",
        use_isolating=True,
        function_generation=_FG,
        formatted=formatted,
        errors=(),
    )


def _get(cache: IntegrityCache, message_id: str) -> IntegrityCacheEntry | None:
    return cache.get(
        message_id,
        None,
        None,
        "en",
        use_isolating=True,
        function_generation=_FG,
    )


class TestEntryChecksumContract:
    """Entry digests detect accidental mutation and key confusion."""

    def test_entry_create_self_verifies(self) -> None:
        error = FrozenFluentError("problem", ErrorCategory.REFERENCE)
        entry = IntegrityCacheEntry.create("value", (error,), sequence=1, key_hash=_NO_KEY_HASH)

        assert len(entry.checksum) == 16
        assert entry.verify() is True

    def test_same_content_with_different_metadata_has_different_checksum(self) -> None:
        first = IntegrityCacheEntry.create("value", (), sequence=1, key_hash=_NO_KEY_HASH)
        second = IntegrityCacheEntry.create("value", (), sequence=2, key_hash=_NO_KEY_HASH)

        assert first.checksum != second.checksum

    def test_immediate_verification_failure_raises_on_put(self) -> None:
        cache = IntegrityCache()
        with patch.object(IntegrityCacheEntry, "verify", return_value=False), pytest.raises(
            IntegrityCheckFailedError,
            match="immediate verification",
        ):
            _put(cache, "msg", "Hello")


class TestCacheCorruptionDetection:
    """Cache lookups must raise on detected integrity failures."""

    def test_corrupted_entry_raises_cache_corruption_error(self) -> None:
        cache = IntegrityCache()
        _put(cache, "msg", "Hello")

        key = next(iter(cache._cache))
        entry = cache._cache[key]
        cache._cache[key] = replace(entry, formatted="Corrupted")

        with pytest.raises(CacheCorruptionError, match="corruption detected"):
            _get(cache, "msg")

    def test_key_confusion_raises_cache_corruption_error(self) -> None:
        cache = IntegrityCache()
        _put(cache, "msg", "Hello")

        key = next(iter(cache._cache))
        entry = cache._cache[key]
        cache._cache[key] = IntegrityCacheEntry.create(
            entry.formatted,
            entry.errors,
            sequence=entry.sequence,
            key_hash=b"\x01" * 16,
        )

        with pytest.raises(CacheCorruptionError, match="key confusion detected"):
            _get(cache, "msg")
