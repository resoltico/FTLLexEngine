# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# Thread-safe caching behavior
# ---------------------------------------------------------------------------


class TestCurrencyCachingConcurrency:
    """Test thread-safe caching via functools.cache."""

    def test_concurrent_currency_maps_access(self) -> None:
        """Concurrent calls to _get_currency_maps_full return cached object.

        functools.cache provides thread-safe cache access, but does NOT
        prevent thundering herd on cold cache (multiple threads may compute
        simultaneously). This test verifies that AFTER cache is populated,
        concurrent access returns the same cached object.
        """
        import threading

        # Pre-warm cache to ensure it's populated
        _ = currency_module._get_currency_maps_full()

        barrier = threading.Barrier(4)
        results: list[object] = []

        def get_with_barrier() -> None:
            barrier.wait()
            data = currency_module._get_currency_maps_full()
            results.append(data)

        threads = [
            threading.Thread(target=get_with_barrier)
            for _ in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 4
        assert all(r is results[0] for r in results)

    def test_currency_maps_structure(self) -> None:
        """Cached currency maps have expected 4-tuple structure."""
        data = currency_module._get_currency_maps_full()

        assert len(data) == 4
        symbol_map, ambiguous, locale_to_currency, valid_codes = data

        assert isinstance(symbol_map, dict)
        assert isinstance(ambiguous, set)
        assert isinstance(locale_to_currency, dict)
        assert isinstance(valid_codes, frozenset)
