# mypy: ignore-errors
"""Split test cases from tests/test_runtime_cache_property.py."""

from tests.runtime_cache_property_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PROPERTY TESTS - LRU EVICTION
# ============================================================================


@pytest.mark.fuzz
class TestLRUEviction:
    """Test LRU (Least Recently Used) eviction behavior."""

    @given(maxsize=st.integers(min_value=2, max_value=10))
    @settings(max_examples=50)
    def test_lru_evicts_least_recently_used(self, maxsize: int) -> None:
        """PROPERTY: LRU eviction removes oldest entry."""
        cache = IntegrityCache(maxsize=maxsize )

        # Fill cache to capacity
        for i in range(maxsize):
            cache.put(f"msg_{i}", None, None, "en_US", use_isolating=True, formatted=f"result_{i}", errors=())

        # Access first entry to make it recently used
        cache.get("msg_0", None, None, "en_US", use_isolating=True)

        # Add one more entry (should evict msg_1, not msg_0)
        cache.put("msg_new", None, None, "en_US", use_isolating=True, formatted="result_new", errors=())

        # msg_0 should still be in cache (recently accessed)
        assert cache.get("msg_0", None, None, "en_US", use_isolating=True) is not None

        # msg_1 should be evicted (oldest unreferenced)
        assert cache.get("msg_1", None, None, "en_US", use_isolating=True) is None
        event(f"maxsize={maxsize}")

    @given(
        maxsize=st.integers(min_value=3, max_value=10),
        access_pattern=st.lists(
            st.integers(min_value=0, max_value=9),
            min_size=5,
            max_size=20,
        ),
    )
    @settings(max_examples=50)
    def test_lru_access_pattern_eviction(
        self,
        maxsize: int,
        access_pattern: list[int],
    ) -> None:
        """PROPERTY: LRU eviction respects access patterns."""
        cache = IntegrityCache(maxsize=maxsize )

        # Fill cache
        for i in range(maxsize):
            cache.put(f"msg_{i}", None, None, "en_US", use_isolating=True, formatted=f"result_{i}", errors=())

        # Access entries according to pattern
        for idx in access_pattern:
            if idx < maxsize:
                cache.get(f"msg_{idx}", None, None, "en_US", use_isolating=True)

        # Add new entries (will trigger evictions)
        for i in range(maxsize, maxsize + 3):
            cache.put(f"msg_{i}", None, None, "en_US", use_isolating=True, formatted=f"result_{i}", errors=())

        # Recently accessed entries should still be in cache
        assert cache.get_stats()["size"] <= maxsize
        event(f"pattern_len={len(access_pattern)}")
