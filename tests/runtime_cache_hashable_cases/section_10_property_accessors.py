# mypy: ignore-errors
"""Split test cases from tests/test_runtime_cache_hashable.py."""

from dataclasses import replace

from ftllexengine.integrity import CacheCorruptionError, WriteConflictError
from tests.runtime_cache_hashable_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# SECTION 10: PROPERTY ACCESSORS
# ============================================================================


class TestIntegrityCacheProperties:
    """Test IntegrityCache property accessors for size, hit/miss counters, and limits."""

    def test_len_and_size_consistent(self) -> None:
        """len(cache) and cache.size return the same current entry count."""
        cache = IntegrityCache()
        assert len(cache) == 0
        cache.put("msg1", None, None, "en", use_isolating=True, formatted="result1", errors=())
        assert len(cache) == 1
        assert cache.size == 1
        cache.put("msg2", None, None, "en", use_isolating=True, formatted="result2", errors=())
        assert len(cache) == 2
        assert cache.size == 2

    def test_maxsize_property(self) -> None:
        """maxsize property returns the configured maximum size."""
        cache = IntegrityCache(maxsize=500)
        assert cache.maxsize == 500

    def test_max_entry_payload_bytes_property(self) -> None:
        """max_entry_payload_bytes property returns the configured weight limit."""
        cache = IntegrityCache(max_entry_payload_bytes=5000)
        assert cache.max_entry_payload_bytes == 5000

    def test_hits_increments_on_cache_hit(self) -> None:
        """hits property increments each time get() finds an entry."""
        cache = IntegrityCache()
        cache.put("msg", None, None, "en", use_isolating=True, formatted="result", errors=())
        cache.get("msg", None, None, "en", use_isolating=True)
        assert cache.hits == 1
        cache.get("msg", None, None, "en", use_isolating=True)
        assert cache.hits == 2

    def test_misses_increments_on_cache_miss(self) -> None:
        """misses increments only for true cache misses, not unhashable bypasses."""
        cache = IntegrityCache()
        cache.get("msg1", None, None, "en", use_isolating=True)
        assert cache.misses == 1
        cache.get("msg2", None, None, "en", use_isolating=True)
        assert cache.misses == 2

    def test_misses_not_incremented_for_unhashable_rejection(self) -> None:
        """Invalid key input is rejected and does not count as a cache miss.

        A key-contract failure is not an ordinary miss: the cache refuses the
        operation before any lookup slot is consulted.
        """
        cache = IntegrityCache()

        class UnknownType:
            pass

        with pytest.raises(CacheKeySerializationError):
            cache.get("msg", {"x": UnknownType()}, None, "en", use_isolating=True)  # type: ignore[dict-item]
        assert cache.unhashable_skips == 1
        assert cache.misses == 0

    def test_hit_rate_excludes_unhashable_rejections(self) -> None:
        """hit_rate is computed over hashable interactions only: hits / (hits + misses).

        Key-contract rejections do not count as misses, so they do not dilute the
        rate. A cache with one hashable hit and one rejected lookup reports
        hit_rate=100.0, not 50.0.
        """
        cache = IntegrityCache()
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())
        cache.get("msg", None, None, "en", use_isolating=True)  # hit

        class UnknownType:
            pass

        with pytest.raises(CacheKeySerializationError):
            cache.get("msg", {"x": UnknownType()}, None, "en", use_isolating=True)  # type: ignore[dict-item]

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 0
        assert stats["unhashable_skips"] == 1
        assert stats["hit_rate"] == 100.0

    def test_hit_rate_zero_on_all_true_misses(self) -> None:
        """hit_rate is 0.0 when all interactions are true misses (no unhashable)."""
        cache = IntegrityCache()
        cache.get("absent", None, None, "en", use_isolating=True)
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.0

    def test_hit_rate_correct_mixed_hits_and_misses(self) -> None:
        """hit_rate is accurate across hits, misses, and rejected key input."""
        cache = IntegrityCache()
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())
        cache.get("msg", None, None, "en", use_isolating=True)   # hit
        cache.get("msg", None, None, "en", use_isolating=True)   # hit
        cache.get("absent", None, None, "en", use_isolating=True)  # miss

        class UnknownType:
            pass

        with pytest.raises(CacheKeySerializationError):
            cache.get("msg", {"x": UnknownType()}, None, "en", use_isolating=True)  # type: ignore[dict-item]

        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["unhashable_skips"] == 1
        # hit_rate = 2 / (2 + 1) * 100 = 66.67%
        assert stats["hit_rate"] == round(2 / 3 * 100, 2)

    def test_unhashable_skips_increments_on_rejection(self) -> None:
        """unhashable_skips increments for both get() and put() rejections."""
        cache = IntegrityCache()

        class UnknownType:
            pass

        get_args: dict[str, object] = {"data": UnknownType()}
        with pytest.raises(CacheKeySerializationError):
            cache.get("msg", get_args, None, "en", use_isolating=True)  # type: ignore[arg-type]
        assert cache.unhashable_skips == 1
        put_args: dict[str, object] = {"data": UnknownType()}
        with pytest.raises(CacheKeySerializationError):
            cache.put(
                "msg",
                put_args,
                None,
                "en",
                use_isolating=True,
                formatted="result",
                errors=(),
            )  # type: ignore[arg-type]
        assert cache.unhashable_skips == 2

    def test_oversize_skips_increments_on_oversize_entry(self) -> None:
        """oversize_skips increments when formatted string exceeds max_entry_payload_bytes."""
        cache = IntegrityCache(max_entry_payload_bytes=10)
        cache.put("msg1", None, None, "en", use_isolating=True, formatted="x" * 100, errors=())
        assert cache.oversize_skips == 1
        cache.put("msg2", None, None, "en", use_isolating=True, formatted="y" * 50, errors=())
        assert cache.oversize_skips == 2

    def test_corruption_and_integrity_event_properties(self) -> None:
        """Integrity counters reflect detected corruption events."""
        cache = IntegrityCache()
        cache.put("msg", None, None, "en", use_isolating=True, formatted="result", errors=())

        key = next(iter(cache._cache))
        entry = cache._cache[key]
        cache._cache[key] = replace(entry, formatted="corrupted")

        with pytest.raises(CacheCorruptionError):
            cache.get("msg", None, None, "en", use_isolating=True)

        assert cache.corruption_detected == 1
        assert cache.integrity_events_emitted == 1

    def test_write_once_and_idempotent_properties(self) -> None:
        """Write-once counters distinguish benign and conflicting rewrites."""
        cache = IntegrityCache(write_once=True)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="value", errors=())
        cache.put("msg", None, None, "en", use_isolating=True, formatted="value", errors=())

        with pytest.raises(WriteConflictError):
            cache.put(
                "msg",
                None,
                None,
                "en",
                use_isolating=True,
                formatted="other",
                errors=(),
            )

        assert cache.idempotent_writes == 1
        assert cache.write_once_conflicts == 1
        assert cache.write_once is True

    def test_error_bloat_and_combined_payload_properties(self) -> None:
        """Skip counters expose count- and payload-based rejections separately."""
        cache = IntegrityCache(max_entry_payload_bytes=200, max_errors_per_entry=1)
        count_errors = (
            FrozenFluentError("first", ErrorCategory.REFERENCE),
            FrozenFluentError("second", ErrorCategory.REFERENCE),
        )
        cache.put(
            "count",
            None,
            None,
            "en",
            use_isolating=True,
            formatted="value",
            errors=count_errors,
        )
        payload_error = FrozenFluentError("x" * 180, ErrorCategory.REFERENCE)
        cache.put(
            "payload",
            None,
            None,
            "en",
            use_isolating=True,
            formatted="x" * 80,
            errors=(payload_error,),
        )

        assert cache.error_bloat_skips == 1
        assert cache.combined_payload_skips == 1

    def test_uncacheable_function_skip_property(self) -> None:
        """The cache exposes intentional non-cacheable bypass counts."""
        cache = IntegrityCache(enable_debug_log=True)
        cache.note_uncacheable_result(
            "msg",
            {"value": "x"},
            None,
            "en",
            use_isolating=True,
        )

        assert cache.uncacheable_function_skips == 1
        assert cache.get_debug_log()[0].operation == "BYPASS_NONCACHEABLE_FUNCTION"

    @given(
        st.integers(min_value=1, max_value=1000),
        st.integers(min_value=1, max_value=10000),
        st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=50)
    def test_property_constructor_parameters_stored_correctly(
        self,
        maxsize: int,
        max_entry_payload_bytes: int,
        max_errors_per_entry: int,
    ) -> None:
        """PROPERTY: Constructor parameters are stored and reflected by properties."""
        cache = IntegrityCache(
            maxsize=maxsize,
            max_entry_payload_bytes=max_entry_payload_bytes,
            max_errors_per_entry=max_errors_per_entry,
        )
        assert cache.maxsize == maxsize
        assert cache.max_entry_payload_bytes == max_entry_payload_bytes
        assert cache.size == 0
        assert cache.hits == 0
        assert cache.misses == 0
        event(f"maxsize={maxsize}")

    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=50)
    def test_property_primitive_args_always_cacheable(self, text: str) -> None:
        """PROPERTY: All primitive FluentValue types produce valid, retrievable entries."""
        cache = IntegrityCache()

        args_list: list[dict[str, FluentValue]] = [
            {"text": text},
            {"num": 42},
            {"decimal": Decimal("3.14")},
            {"flag": True},
            {"val": None},
        ]
        for args in args_list:
            cache.put("msg", args, None, "en", use_isolating=True, formatted="result", errors=())
            entry = cache.get("msg", args, None, "en", use_isolating=True)
            assert entry is not None
            assert entry.as_result() == ("result", ())

        event(f"text_len={len(text)}")
