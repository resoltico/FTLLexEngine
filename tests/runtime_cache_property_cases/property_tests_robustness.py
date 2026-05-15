# mypy: ignore-errors
"""Split test cases from tests/test_runtime_cache_property.py."""

from tests.runtime_cache_property_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PROPERTY TESTS - ROBUSTNESS
# ============================================================================


@pytest.mark.fuzz
class TestCacheRobustness:
    """Test cache robustness with various input types."""

    @given(
        args=st.dictionaries(
            st.text(min_size=1),
            st.one_of(
                st.integers(),
                st.decimals(allow_nan=False, allow_infinity=False),
                st.text(),
                st.booleans(),
                st.none(),
            ),
            max_size=10,  # Keep practical bound for dict size
        ),
    )
    @settings(max_examples=200)
    def test_cache_handles_various_arg_types(
        self, args: dict[str, int | Decimal | str | bool | None]
    ) -> None:
        """ROBUSTNESS: Cache handles various argument types."""
        cache = IntegrityCache(maxsize=100 )

        # Should not crash with various arg types
        try:
            cache.put("msg", args, None, "en_US", use_isolating=True, formatted="result", errors=())
            entry = cache.get("msg", args, None, "en_US", use_isolating=True)
            # If put succeeded, get should return the value
            if entry is not None:
                assert entry.as_result() == ("result", ())
        except (TypeError, ValueError):
            # Some types may not be hashable - acceptable
            pass
        event(f"arg_types={len(args)}")

    @given(
        msg_ids=st.lists(message_ids, min_size=1, max_size=50),
        maxsize=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=50)
    def test_cache_handles_duplicate_puts(
        self,
        msg_ids: list[str],
        maxsize: int,
    ) -> None:
        """ROBUSTNESS: Cache handles duplicate puts gracefully."""
        cache = IntegrityCache(maxsize=maxsize )

        # Put same message multiple times
        for msg_id in msg_ids:
            cache.put(msg_id, None, None, "en_US", use_isolating=True, formatted=f"result_{msg_id}", errors=())

        # Cache should still respect maxsize
        assert cache.get_stats()["size"] <= maxsize
        event(f"duplicates={len(msg_ids)}")

    @given(maxsize=st.integers(min_value=1, max_value=100))
    @settings(max_examples=50)
    def test_cache_stats_never_negative(self, maxsize: int) -> None:
        """ROBUSTNESS: Cache stats are never negative."""
        cache = IntegrityCache(maxsize=maxsize )

        # Perform various operations
        cache.put("msg", None, None, "en_US", use_isolating=True, formatted="result", errors=())
        cache.get("msg", None, None, "en_US", use_isolating=True)
        cache.get("missing", None, None, "en_US", use_isolating=True)
        cache.clear()

        stats = cache.get_stats()
        assert stats["size"] >= 0
        assert stats["hits"] >= 0
        assert stats["misses"] >= 0
        assert stats["maxsize"] > 0
        event(f"maxsize={maxsize}")
