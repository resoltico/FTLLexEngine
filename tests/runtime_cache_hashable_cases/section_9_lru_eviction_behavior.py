# mypy: ignore-errors
"""Split test cases from tests/test_runtime_cache_hashable.py."""

from tests.runtime_cache_hashable_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# SECTION 9: LRU EVICTION BEHAVIOR
# ============================================================================


class TestIntegrityCacheLRUBehavior:
    """Test IntegrityCache LRU eviction and move-to-end behavior."""

    def test_put_moves_existing_key_to_end_of_lru(self) -> None:
        """put() on existing key marks it as recently used (moves to LRU tail)."""
        cache = IntegrityCache(maxsize=3)
        cache.put("msg1", None, None, "en", use_isolating=True, formatted="result1", errors=())
        cache.put("msg2", None, None, "en", use_isolating=True, formatted="result2", errors=())
        cache.put("msg3", None, None, "en", use_isolating=True, formatted="result3", errors=())
        assert cache.size == 3

        # Updating msg1 moves it to the LRU tail (recently used)
        cache.put("msg1", None, None, "en", use_isolating=True, formatted="updated1", errors=())

        # Adding msg4 should evict msg2 (now the oldest)
        cache.put("msg4", None, None, "en", use_isolating=True, formatted="result4", errors=())
        assert cache.size == 3

        assert cache.get("msg2", None, None, "en", use_isolating=True) is None
        entry1 = cache.get("msg1", None, None, "en", use_isolating=True)
        assert entry1 is not None
        assert entry1.as_result() == ("updated1", ())
        assert cache.get("msg3", None, None, "en", use_isolating=True) is not None
        assert cache.get("msg4", None, None, "en", use_isolating=True) is not None

    def test_put_evicts_lru_entry_when_cache_full(self) -> None:
        """put() evicts the least recently used entry when capacity is reached."""
        cache = IntegrityCache(maxsize=2)
        cache.put("msg1", None, None, "en", use_isolating=True, formatted="result1", errors=())
        cache.put("msg2", None, None, "en", use_isolating=True, formatted="result2", errors=())
        assert cache.size == 2

        cache.put("msg3", None, None, "en", use_isolating=True, formatted="result3", errors=())
        assert cache.size == 2
        assert cache.get("msg1", None, None, "en", use_isolating=True) is None
        assert cache.get("msg2", None, None, "en", use_isolating=True) is not None
        assert cache.get("msg3", None, None, "en", use_isolating=True) is not None
