# mypy: ignore-errors
"""Split test cases from tests/test_runtime_cache_hashable.py."""

from tests.runtime_cache_hashable_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# SECTION 10: PROPERTY ACCESSORS
# ============================================================================


class TestIntegrityCacheProperties:
    """Test IntegrityCache property accessors for size, hit/miss counters, and limits."""

    def test_len_and_size_consistent(self) -> None:
        """len(cache) and cache.size return the same current entry count."""
        cache = IntegrityCache(strict=False)
        assert len(cache) == 0
        cache.put("msg1", None, None, "en", use_isolating=True, formatted="result1", errors=())
        assert len(cache) == 1
        assert cache.size == 1
        cache.put("msg2", None, None, "en", use_isolating=True, formatted="result2", errors=())
        assert len(cache) == 2
        assert cache.size == 2

    def test_maxsize_property(self) -> None:
        """maxsize property returns the configured maximum size."""
        cache = IntegrityCache(strict=False, maxsize=500)
        assert cache.maxsize == 500

    def test_max_entry_weight_property(self) -> None:
        """max_entry_weight property returns the configured weight limit."""
        cache = IntegrityCache(strict=False, max_entry_weight=5000)
        assert cache.max_entry_weight == 5000

    def test_hits_increments_on_cache_hit(self) -> None:
        """hits property increments each time get() finds an entry."""
        cache = IntegrityCache(strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="result", errors=())
        cache.get("msg", None, None, "en", use_isolating=True)
        assert cache.hits == 1
        cache.get("msg", None, None, "en", use_isolating=True)
        assert cache.hits == 2

    def test_misses_increments_on_cache_miss(self) -> None:
        """misses increments only for true cache misses, not unhashable bypasses."""
        cache = IntegrityCache(strict=False)
        cache.get("msg1", None, None, "en", use_isolating=True)
        assert cache.misses == 1
        cache.get("msg2", None, None, "en", use_isolating=True)
        assert cache.misses == 2

    def test_misses_not_incremented_for_unhashable_bypass(self) -> None:
        """Unhashable args bypass the cache entirely; misses is not incremented.

        An unhashable bypass is not a cache miss: no key was constructed or
        looked up. Only unhashable_skips reflects the event. Conflating them
        would deflate hit_rate and mislead operators about cache efficiency.
        """
        cache = IntegrityCache(strict=False)

        class UnknownType:
            pass

        cache.get("msg", {"x": UnknownType()}, None, "en", use_isolating=True)  # type: ignore[dict-item]
        assert cache.unhashable_skips == 1
        assert cache.misses == 0

    def test_hit_rate_excludes_unhashable_bypasses(self) -> None:
        """hit_rate is computed over hashable interactions only: hits / (hits + misses).

        Unhashable bypasses do not count as misses, so they do not dilute the
        rate. A cache with one hashable hit and one unhashable bypass reports
        hit_rate=100.0, not 50.0.
        """
        cache = IntegrityCache(strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())
        cache.get("msg", None, None, "en", use_isolating=True)  # hit

        class UnknownType:
            pass

        cache.get("msg", {"x": UnknownType()}, None, "en", use_isolating=True)  # type: ignore[dict-item]

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 0
        assert stats["unhashable_skips"] == 1
        assert stats["hit_rate"] == 100.0

    def test_hit_rate_zero_on_all_true_misses(self) -> None:
        """hit_rate is 0.0 when all interactions are true misses (no unhashable)."""
        cache = IntegrityCache(strict=False)
        cache.get("absent", None, None, "en", use_isolating=True)
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.0

    def test_hit_rate_correct_mixed_hits_and_misses(self) -> None:
        """hit_rate is accurate across a mix of hits, misses, and unhashable bypasses."""
        cache = IntegrityCache(strict=False)
        cache.put("msg", None, None, "en", use_isolating=True, formatted="Hello", errors=())
        cache.get("msg", None, None, "en", use_isolating=True)   # hit
        cache.get("msg", None, None, "en", use_isolating=True)   # hit
        cache.get("absent", None, None, "en", use_isolating=True)  # miss

        class UnknownType:
            pass

        cache.get("msg", {"x": UnknownType()}, None, "en", use_isolating=True)  # type: ignore[dict-item]

        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["unhashable_skips"] == 1
        # hit_rate = 2 / (2 + 1) * 100 = 66.67%
        assert stats["hit_rate"] == round(2 / 3 * 100, 2)

    def test_unhashable_skips_increments_on_skip(self) -> None:
        """unhashable_skips increments for both get() and put() skips."""
        cache = IntegrityCache(strict=False)

        class UnknownType:
            pass

        get_args: dict[str, object] = {"data": UnknownType()}
        cache.get("msg", get_args, None, "en", use_isolating=True)  # type: ignore[arg-type]
        assert cache.unhashable_skips == 1
        put_args: dict[str, object] = {"data": UnknownType()}
        cache.put("msg", put_args, None, "en", use_isolating=True, formatted="result", errors=())  # type: ignore[arg-type]
        assert cache.unhashable_skips == 2

    def test_oversize_skips_increments_on_oversize_entry(self) -> None:
        """oversize_skips increments when formatted string exceeds max_entry_weight."""
        cache = IntegrityCache(strict=False, max_entry_weight=10)
        cache.put("msg1", None, None, "en", use_isolating=True, formatted="x" * 100, errors=())
        assert cache.oversize_skips == 1
        cache.put("msg2", None, None, "en", use_isolating=True, formatted="y" * 50, errors=())
        assert cache.oversize_skips == 2

    @given(
        st.integers(min_value=1, max_value=1000),
        st.integers(min_value=1, max_value=10000),
        st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=50)
    def test_property_constructor_parameters_stored_correctly(
        self,
        maxsize: int,
        max_entry_weight: int,
        max_errors_per_entry: int,
    ) -> None:
        """PROPERTY: Constructor parameters are stored and reflected by properties."""
        cache = IntegrityCache(
            strict=False,
            maxsize=maxsize,
            max_entry_weight=max_entry_weight,
            max_errors_per_entry=max_errors_per_entry,
        )
        assert cache.maxsize == maxsize
        assert cache.max_entry_weight == max_entry_weight
        assert cache.size == 0
        assert cache.hits == 0
        assert cache.misses == 0
        event(f"maxsize={maxsize}")

    @given(st.text(min_size=0, max_size=100))
    @settings(max_examples=50)
    def test_property_primitive_args_always_cacheable(self, text: str) -> None:
        """PROPERTY: All primitive FluentValue types produce valid, retrievable entries."""
        cache = IntegrityCache(strict=False)

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
