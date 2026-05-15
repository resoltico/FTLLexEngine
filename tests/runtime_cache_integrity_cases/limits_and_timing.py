# mypy: ignore-errors
from __future__ import annotations

import pytest

from ftllexengine.constants import DEFAULT_MAX_ENTRY_PAYLOAD_BYTES
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime import FluentBundle
from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.runtime.cache_config import CacheConfig

_FG = 0


def _put(cache: IntegrityCache, message_id: str, *, formatted: str, errors=()) -> None:
    cache.put(
        message_id,
        None,
        None,
        "en",
        use_isolating=True,
        function_generation=_FG,
        formatted=formatted,
        errors=errors,
    )


class TestPayloadByteLimit:
    """The cache payload budget should be explicit and deterministic."""

    def test_default_payload_limit_matches_constant(self) -> None:
        cache = IntegrityCache()
        assert cache.max_entry_payload_bytes == DEFAULT_MAX_ENTRY_PAYLOAD_BYTES

    def test_invalid_payload_limit_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="max_entry_payload_bytes must be int"):
            IntegrityCache(max_entry_payload_bytes=True)
        with pytest.raises(ValueError, match="max_entry_payload_bytes must be positive"):
            IntegrityCache(max_entry_payload_bytes=0)

    def test_invalid_integrity_event_sink_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="integrity_event_sink must implement"):
            IntegrityCache(integrity_event_sink=object())  # type: ignore[arg-type]

    def test_invalid_debug_fingerprint_key_contract_is_rejected(self) -> None:
        with pytest.raises(TypeError, match="debug_fingerprint_key must be bytes or None"):
            IntegrityCache(debug_fingerprint_key="not-bytes")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="debug_fingerprint_key must contain at least 16 bytes"):
            IntegrityCache(debug_fingerprint_key=b"short")

    def test_oversize_formatted_result_is_not_cached(self) -> None:
        cache = IntegrityCache(max_entry_payload_bytes=10)
        _put(cache, "msg", formatted="x" * 20)

        stats = cache.get_stats()
        assert stats["oversize_skips"] == 1
        assert stats["size"] == 0

    def test_combined_payload_limit_is_tracked_separately(self) -> None:
        cache = IntegrityCache(max_entry_payload_bytes=200)
        error = FrozenFluentError("x" * 180, ErrorCategory.REFERENCE)
        _put(cache, "msg", formatted="x" * 80, errors=(error,))

        stats = cache.get_stats()
        assert stats["combined_payload_skips"] == 1
        assert stats["oversize_skips"] == 0


class TestBundleUsesPayloadBudget:
    """Bundles should propagate payload-byte cache limits into their internal cache."""

    def test_bundle_cache_uses_payload_limit(self) -> None:
        bundle = FluentBundle("en", cache=CacheConfig(max_entry_payload_bytes=50))
        long_text = "x" * 100
        bundle.add_resource(f"msg = {long_text}")

        result, errors = bundle.format_pattern("msg")

        assert result == long_text
        assert errors == ()
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["oversize_skips"] == 1
