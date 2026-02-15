"""Thread safety tests for caching.

Validates concurrent access to FormatCache.
"""

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from ftllexengine import FluentBundle
from ftllexengine.runtime.cache_config import CacheConfig


class TestCacheConcurrency:
    """Test cache thread safety."""

    def test_concurrent_reads(self) -> None:
        """Concurrent reads are thread-safe."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello, { $name }!")

        def format_message(name: str) -> str:
            result, _ = bundle.format_pattern("msg", {"name": name})
            return result

        # Concurrent reads from multiple threads
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(format_message, "Alice") for _ in range(100)]
            results = [future.result() for future in as_completed(futures)]

        # All results should be identical
        assert all(r == "Hello, Alice!" for r in results)

        # Check cache was populated
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["hits"] > 0  # At least some cache hits

    def test_concurrent_different_args(self) -> None:
        """Concurrent reads with different args are thread-safe."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello, { $name }!")

        names = ["Alice", "Bob", "Charlie", "David"]

        def format_message(name: str) -> str:
            result, _ = bundle.format_pattern("msg", {"name": name})
            return result

        # Concurrent reads with different args
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [
                executor.submit(format_message, names[i % len(names)]) for i in range(100)
            ]
            results = [future.result() for future in as_completed(futures)]

        # Check results are correct
        for result in results:
            assert result.startswith("Hello, ")

    def test_concurrent_cache_clear(self) -> None:
        """Concurrent cache clear is thread-safe."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello")

        errors = []

        def format_and_clear() -> None:
            try:
                for _ in range(10):
                    bundle.format_pattern("msg")
                    bundle.clear_cache()
            except Exception as e:  # pylint: disable=broad-exception-caught
                errors.append(e)

        # Multiple threads formatting and clearing
        threads = [threading.Thread(target=format_and_clear) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # No exceptions should occur
        assert len(errors) == 0

    def test_concurrent_add_resource(self) -> None:
        """Concurrent add_resource with formatting is thread-safe."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello")

        errors = []

        def format_message() -> None:
            try:
                for _ in range(10):
                    bundle.format_pattern("msg")
            except Exception as e:  # pylint: disable=broad-exception-caught
                errors.append(e)

        def add_resource() -> None:
            try:
                for i in range(5):
                    bundle.add_resource(f"msg{i} = World {i}")
            except Exception as e:  # pylint: disable=broad-exception-caught
                errors.append(e)

        # Mix of formatting and resource addition
        format_threads = [threading.Thread(target=format_message) for _ in range(3)]
        add_threads = [threading.Thread(target=add_resource) for _ in range(2)]

        all_threads = format_threads + add_threads
        for thread in all_threads:
            thread.start()
        for thread in all_threads:
            thread.join()

        # No exceptions should occur
        assert len(errors) == 0


class TestCacheRaceConditions:
    """Test for potential race conditions."""

    def test_no_race_on_lru_eviction(self) -> None:
        """No race condition during LRU eviction."""
        bundle = FluentBundle("en", cache=CacheConfig(size=10))
        bundle.add_resource(
            "\n".join([f"msg{i} = Message {i}" for i in range(20)])
        )

        def format_messages() -> None:
            for i in range(20):
                bundle.format_pattern(f"msg{i}")

        # Multiple threads causing evictions
        threads = [threading.Thread(target=format_messages) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Cache should be at or below size limit
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["size"] <= 10

    def test_cache_stats_consistency(self) -> None:
        """Cache stats remain consistent under concurrent access."""
        bundle = FluentBundle("en", cache=CacheConfig(), use_isolating=False)
        bundle.add_resource("msg = Hello")

        def format_many() -> None:
            for _ in range(100):
                bundle.format_pattern("msg")

        # Multiple threads accessing cache
        threads = [threading.Thread(target=format_many) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # Stats should be consistent
        stats = bundle.get_cache_stats()
        assert stats is not None
        assert stats["hits"] + stats["misses"] == 500  # 100 * 5 threads
        assert stats["hits"] >= 495  # At least 495 hits (first 5 are misses)
