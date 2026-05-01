# mypy: ignore-errors
"""Split test cases from tests/test_runtime_cache_property.py."""

from tests.runtime_cache_property_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PROPERTY TESTS - INIT PARAMETERS
# ============================================================================


@pytest.mark.fuzz
class TestIntegrityCacheHypothesisProperties:
    """Property-based tests for IntegrityCache using Hypothesis."""

    @given(
        st.integers(min_value=1, max_value=1000),
        st.integers(min_value=1, max_value=10000),
        st.integers(min_value=1, max_value=100),
    )
    @settings(max_examples=50)
    def test_property_init_parameters_stored_correctly(
        self,
        maxsize: int,
        max_entry_weight: int,
        max_errors_per_entry: int,
    ) -> None:
        """PROPERTY: Constructor parameters are stored correctly."""
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
    def test_property_primitives_hashable(self, text: str) -> None:
        """PROPERTY: All primitive types produce valid cache keys."""
        cache = IntegrityCache(strict=False)

        # String
        cache.put("msg", {"text": text}, None, "en", use_isolating=True, formatted="result", errors=())
        entry = cache.get("msg", {"text": text}, None, "en", use_isolating=True)
        assert entry is not None
        assert entry.as_result() == ("result", ())

        # Integer
        cache.put("msg", {"num": 42}, None, "en", use_isolating=True, formatted="result", errors=())
        entry = cache.get("msg", {"num": 42}, None, "en", use_isolating=True)
        assert entry is not None
        assert entry.as_result() == ("result", ())

        # Decimal
        cache.put("msg", {"decimal": Decimal("3.14")}, None, "en", use_isolating=True, formatted="result", errors=())
        entry = cache.get("msg", {"decimal": Decimal("3.14")}, None, "en", use_isolating=True)
        assert entry is not None
        assert entry.as_result() == ("result", ())

        # Bool
        cache.put("msg", {"bool": True}, None, "en", use_isolating=True, formatted="result", errors=())
        entry = cache.get("msg", {"bool": True}, None, "en", use_isolating=True)
        assert entry is not None
        assert entry.as_result() == ("result", ())

        # None
        cache.put("msg", {"val": None}, None, "en", use_isolating=True, formatted="result", errors=())
        entry = cache.get("msg", {"val": None}, None, "en", use_isolating=True)
        assert entry is not None
        assert entry.as_result() == ("result", ())
        event(f"text_len={len(text)}")
