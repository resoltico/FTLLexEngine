# mypy: ignore-errors
"""Split test cases from tests/test_runtime_cache_property.py."""

from tests.runtime_cache_property_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PROPERTY TESTS - BASIC INVARIANTS
# ============================================================================


@pytest.mark.fuzz

class TestCacheInvariants:
    """Test fundamental IntegrityCache invariants."""

    @given(maxsize=st.integers(min_value=1, max_value=10000))
    @settings(max_examples=100)
    def test_cache_maxsize_enforced(self, maxsize: int) -> None:
        """INVARIANT: Cache never exceeds maxsize."""
        cache = IntegrityCache(maxsize=maxsize )

        # Add more than maxsize entries
        for i in range(maxsize + 10):
            cache.put(
                f"msg_{i}",
                None,
                None,
                "en_US",
                use_isolating=True,
                formatted=f"result_{i}",
                errors=(),
            )

        # Cache should not exceed maxsize
        assert cache.get_stats()["size"] <= maxsize
        event(f"maxsize={maxsize}")

    @given(
        msg_id=message_ids,
        locale=locale_codes,
        args=args_strategy,
        attr=attributes,
        value=cache_values,
    )
    @settings(max_examples=200)
    def test_get_after_put_returns_value(
        self,
        msg_id: str,
        locale: str,
        args: dict[str, int | Decimal | str] | None,
        attr: str | None,
        value: tuple[str, tuple[()]],
    ) -> None:
        """PROPERTY: get(k) after put(k, v) returns v."""
        cache = IntegrityCache(maxsize=100 )

        formatted, errors = value
        cache.put(msg_id, args, attr, locale, use_isolating=True, formatted=formatted, errors=errors)
        entry = cache.get(msg_id, args, attr, locale, use_isolating=True)

        assert entry is not None
        assert entry.as_result() == value
        has_args = args is not None
        event(f"has_args={has_args}")

    @given(
        msg_id=message_ids,
        locale=locale_codes,
    )
    @settings(max_examples=100)
    def test_get_without_put_returns_none(
        self,
        msg_id: str,
        locale: str,
    ) -> None:
        """PROPERTY: get(k) without put(k) returns None."""
        cache = IntegrityCache(maxsize=100 )

        result = cache.get(msg_id, None, None, locale, use_isolating=True)

        assert result is None
        event(f"locale={locale}")

    @given(maxsize=st.integers(min_value=1, max_value=100))
    @settings(max_examples=50)
    def test_clear_resets_cache_to_empty(self, maxsize: int) -> None:
        """PROPERTY: clear() empties cache and resets counters."""
        cache = IntegrityCache(maxsize=maxsize )

        # Add some entries
        for i in range(min(10, maxsize)):
            cache.put(f"msg_{i}", None, None, "en_US", use_isolating=True, formatted=f"result_{i}", errors=())

        # Clear
        cache.clear()

        # Cache should be empty
        stats = cache.get_stats()
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        event(f"maxsize={maxsize}")

    @given(
        msg_id=message_ids,
        locale=locale_codes,
        value=cache_values,
    )
    @settings(max_examples=100)
    def test_hit_counter_increments_on_cache_hit(
        self,
        msg_id: str,
        locale: str,
        value: tuple[str, tuple[()]],
    ) -> None:
        """PROPERTY: Cache hits increment hit counter."""
        cache = IntegrityCache(maxsize=100 )

        formatted, errors = value
        cache.put(msg_id, None, None, locale, use_isolating=True, formatted=formatted, errors=errors)

        # First get - cache hit
        initial_stats = cache.get_stats()
        cache.get(msg_id, None, None, locale, use_isolating=True)

        stats_after_hit = cache.get_stats()
        assert stats_after_hit["hits"] == initial_stats["hits"] + 1
        event(f"locale={locale}")

    @given(
        msg_id=message_ids,
        locale=locale_codes,
    )
    @settings(max_examples=100)
    def test_miss_counter_increments_on_cache_miss(
        self,
        msg_id: str,
        locale: str,
    ) -> None:
        """PROPERTY: Cache misses increment miss counter."""
        cache = IntegrityCache(maxsize=100 )

        initial_stats = cache.get_stats()
        cache.get(msg_id, None, None, locale, use_isolating=True)  # Cache miss

        stats_after_miss = cache.get_stats()
        assert stats_after_miss["misses"] == initial_stats["misses"] + 1
        event(f"locale={locale}")
