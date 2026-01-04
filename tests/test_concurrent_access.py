"""Concurrent access tests.

Tests for thread safety of FluentBundle:
- Concurrent format_pattern() calls
- No race conditions in resolution
- Consistent results across threads

Structure:
    - TestConcurrentFormatPatternBasic: Essential tests (run in every CI build)
    - TestConcurrentFormatPatternIntensive: Property-based tests (fuzz-marked)
    - TestConcurrentConsistency: Fuzz-marked intensive tests
    - TestConcurrentWithReferences: Fuzz-marked intensive tests
    - TestConcurrentErrorHandling: Fuzz-marked intensive tests

Note: use_isolating=False is used throughout because these tests verify thread
safety behavior, not Unicode directional isolation. This makes assertions cleaner
and is independent of the isolation feature being tested elsewhere.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.bundle import FluentBundle

# =============================================================================
# Essential Concurrency Tests (Run in every CI build)
# =============================================================================


class TestConcurrentFormatPatternBasic:
    """Essential thread safety tests that run in every CI build.

    These verify the core thread safety guarantees of FluentBundle without
    intensive property-based testing. They complete quickly and catch
    regressions in concurrent access patterns.
    """

    def test_concurrent_same_message(self) -> None:
        """Multiple threads formatting the same message."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource("greeting = Hello, { $name }!")

        results: list[str] = []
        errors_list: list[tuple[object, ...]] = []
        lock = threading.Lock()

        def format_message(name: str) -> None:
            result, errors = bundle.format_pattern("greeting", {"name": name})
            with lock:
                results.append(result)
                errors_list.append(errors)

        threads = []
        names = [f"User{i}" for i in range(20)]

        for name in names:
            t = threading.Thread(target=format_message, args=(name,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(results) == 20
        for result in results:
            assert "Hello, User" in result

    def test_concurrent_different_messages(self) -> None:
        """Multiple threads formatting different messages."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            """
msg1 = First message
msg2 = Second message
msg3 = Third message
"""
        )

        results: dict[str, str] = {}
        lock = threading.Lock()

        def format_message(msg_id: str) -> None:
            result, _ = bundle.format_pattern(msg_id)
            with lock:
                results[msg_id] = result

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for msg_id in ["msg1", "msg2", "msg3"] * 10:
                futures.append(executor.submit(format_message, msg_id))

            for future in as_completed(futures):
                future.result()  # Raise any exceptions

        assert "msg1" in results
        assert "msg2" in results
        assert "msg3" in results

    def test_concurrent_with_variables(self) -> None:
        """Concurrent formatting with different variable values."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource("count = You have { $n } items.")

        results: list[tuple[int, str]] = []
        lock = threading.Lock()

        def format_with_count(n: int) -> None:
            result, _ = bundle.format_pattern("count", {"n": n})
            with lock:
                results.append((n, result))

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(format_with_count, i) for i in range(50)]
            for future in as_completed(futures):
                future.result()

        assert len(results) == 50

        # Verify each result matches its input
        for n, result in results:
            assert str(n) in result

    def test_concurrent_select_expressions(self) -> None:
        """Concurrent formatting with select expressions."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            """
items = { $count ->
    [one] One item
   *[other] { $count } items
}
"""
        )

        results: list[tuple[int, str]] = []
        lock = threading.Lock()

        def format_items(count: int) -> None:
            result, _ = bundle.format_pattern("items", {"count": count})
            with lock:
                results.append((count, result))

        counts = [0, 1, 2, 5, 10, 21, 100] * 5

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(format_items, c) for c in counts]
            for future in as_completed(futures):
                future.result()

        assert len(results) == len(counts)

        # Verify results
        for count, result in results:
            if count == 1:
                assert "One item" in result
            else:
                assert "items" in result


# =============================================================================
# Intensive Concurrency Tests (Fuzz-marked, run with pytest -m fuzz)
# =============================================================================


@pytest.mark.fuzz
class TestConcurrentConsistency:
    """Intensive tests for result consistency across threads.

    These are property-based tests with many threads - designed for dedicated
    fuzzing runs, not every CI build.
    """

    @given(st.integers(min_value=10, max_value=50))
    @settings(max_examples=20, deadline=None)
    def test_deterministic_results(self, thread_count: int) -> None:
        """Property: Same input produces same output across threads."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource("msg = Fixed message with { $var }")

        results: list[str] = []
        lock = threading.Lock()

        def format_msg() -> None:
            result, _ = bundle.format_pattern("msg", {"var": "value"})
            with lock:
                results.append(result)

        threads = [threading.Thread(target=format_msg) for _ in range(thread_count)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All results should be identical
        assert len(results) == thread_count
        assert all(r == results[0] for r in results)

    def test_no_data_corruption(self) -> None:
        """Verify no data corruption with many concurrent operations."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            """
user = User { $id } is { $status }
"""
        )

        results: list[tuple[int, str, str]] = []
        lock = threading.Lock()

        def format_user(user_id: int, status: str) -> None:
            result, _ = bundle.format_pattern("user", {"id": user_id, "status": status})
            with lock:
                results.append((user_id, status, result))

        # Many concurrent calls with different data
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []
            for i in range(100):
                status = "online" if i % 2 == 0 else "offline"
                futures.append(executor.submit(format_user, i, status))

            for future in as_completed(futures):
                future.result()

        assert len(results) == 100

        # Verify each result contains its specific data
        for user_id, status, result in results:
            assert str(user_id) in result
            assert status in result


@pytest.mark.fuzz
class TestConcurrentWithReferences:
    """Intensive tests for concurrent resolution with message references.

    Tests reference chain resolution under heavy concurrent load.
    Designed for dedicated fuzzing runs.
    """

    def test_concurrent_reference_chains(self) -> None:
        """Concurrent resolution of reference chains."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            """
base = World
greeting = Hello, { base }!
welcome = { greeting } Welcome!
"""
        )

        results: list[str] = []
        lock = threading.Lock()

        def resolve_welcome() -> None:
            result, _ = bundle.format_pattern("welcome")
            with lock:
                results.append(result)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(resolve_welcome) for _ in range(50)]
            for future in as_completed(futures):
                future.result()

        assert len(results) == 50
        expected = "Hello, World! Welcome!"
        assert all(r == expected for r in results)

    def test_concurrent_term_resolution(self) -> None:
        """Concurrent resolution of terms."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            """
-brand = Firefox
download = Download { -brand } today!
about = About { -brand }
"""
        )

        download_results: list[str] = []
        about_results: list[str] = []
        lock = threading.Lock()

        def resolve_messages() -> None:
            d_result, _ = bundle.format_pattern("download")
            a_result, _ = bundle.format_pattern("about")
            with lock:
                download_results.append(d_result)
                about_results.append(a_result)

        threads = [threading.Thread(target=resolve_messages) for _ in range(20)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(download_results) == 20
        assert len(about_results) == 20

        assert all("Firefox" in r for r in download_results)
        assert all("Firefox" in r for r in about_results)


@pytest.mark.fuzz
class TestConcurrentErrorHandling:
    """Intensive tests for concurrent error handling.

    Tests error path behavior under heavy concurrent load.
    Designed for dedicated fuzzing runs.
    """

    def test_concurrent_missing_messages(self) -> None:
        """Concurrent access to missing messages."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource("exists = This exists")

        results: list[tuple[str, int]] = []
        lock = threading.Lock()

        def format_message(msg_id: str) -> None:
            result, errors = bundle.format_pattern(msg_id)
            with lock:
                results.append((result, len(errors)))

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for _ in range(20):
                futures.append(executor.submit(format_message, "exists"))
                futures.append(executor.submit(format_message, "missing"))

            for future in as_completed(futures):
                future.result()

        assert len(results) == 40

        # Verify error handling is consistent
        exists_results = [r for r in results if "This exists" in r[0]]
        missing_results = [r for r in results if r[1] > 0]

        assert len(exists_results) == 20
        assert len(missing_results) == 20

    def test_concurrent_missing_variables(self) -> None:
        """Concurrent formatting with missing variables."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource("msg = Hello, { $name }!")

        results: list[tuple[str, int]] = []
        lock = threading.Lock()

        def format_with_args(args: dict) -> None:
            result, errors = bundle.format_pattern("msg", args)
            with lock:
                results.append((result, len(errors)))

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for i in range(40):
                if i % 2 == 0:
                    futures.append(executor.submit(format_with_args, {"name": f"User{i}"}))
                else:
                    futures.append(executor.submit(format_with_args, {}))  # Missing variable

            for future in as_completed(futures):
                future.result()

        assert len(results) == 40
