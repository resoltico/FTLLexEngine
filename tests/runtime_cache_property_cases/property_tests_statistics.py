# mypy: ignore-errors
"""Split test cases from tests/test_runtime_cache_property.py."""

from tests.runtime_cache_property_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PROPERTY TESTS - STATISTICS
# ============================================================================


@pytest.mark.fuzz
class TestCacheStatistics:
    """Test cache statistics tracking."""

    @given(
        operations=st.lists(
            st.tuples(
                st.sampled_from(["put", "get"]),
                message_ids,
            ),
            min_size=1,
            max_size=50,
        ),
    )
    @settings(max_examples=50)
    def test_hit_rate_consistency(
        self,
        operations: list[tuple[str, str]],
    ) -> None:
        """PROPERTY: hit_rate = hits / (hits + misses)."""
        cache = IntegrityCache(maxsize=20 )

        for op, msg_id in operations:
            if op == "put":
                cache.put(msg_id, None, None, "en_US", use_isolating=True, formatted=f"result_{msg_id}", errors=())
            elif op == "get":
                cache.get(msg_id, None, None, "en_US", use_isolating=True)

        stats = cache.get_stats()
        total = stats["hits"] + stats["misses"]

        if total > 0:
            expected_hit_rate = stats["hits"] / total
            # hit_rate might be percentage (0-100) or decimal (0.0-1.0)
            actual_rate: float = float(stats["hit_rate"])
            if actual_rate > 1.0:  # Percentage format
                actual_rate = actual_rate / 100.0
            assert abs(actual_rate - expected_hit_rate) < 0.01
        event(f"op_count={len(operations)}")

    @given(
        num_entries=st.integers(min_value=0, max_value=50),
        maxsize=st.integers(min_value=10, max_value=100),
    )
    @settings(max_examples=50)
    def test_size_equals_entry_count(
        self,
        num_entries: int,
        maxsize: int,
    ) -> None:
        """PROPERTY: size stat equals actual number of cached entries."""
        cache = IntegrityCache(maxsize=maxsize )

        # Add entries
        for i in range(num_entries):
            cache.put(f"msg_{i}", None, None, "en_US", use_isolating=True, formatted=f"result_{i}", errors=())

        stats = cache.get_stats()
        expected_size = min(num_entries, maxsize)

        assert stats["size"] == expected_size
        event(f"entries={num_entries}")
