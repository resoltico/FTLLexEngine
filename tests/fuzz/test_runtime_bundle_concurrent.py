"""Concurrent access tests.

Tests for thread safety of FluentBundle:
- Concurrent format_pattern() calls
- No race conditions in resolution
- Consistent results across threads

Structure:
    - TestConcurrentFormatPatternBasic: Essential tests (run in every CI build)
    - TestConcurrentConsistency: Property-based concurrency tests (fuzz-marked)
    - TestConcurrentWithReferences: Property-based reference tests (fuzz-marked)
    - TestConcurrentErrorHandling: Property-based error tests (fuzz-marked)
    - TestConcurrentMutation: Property-based mutation tests (fuzz-marked)
    - TestMemoryStability: Soak tests for leak detection (essential, not fuzz)

Note: use_isolating=False is used throughout because these tests verify thread
safety behavior, not Unicode directional isolation. This makes assertions cleaner
and is independent of the isolation feature being tested elsewhere.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from hypothesis import event, given, settings
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

        event(f"thread_count={thread_count}")

        threads = [threading.Thread(target=format_msg) for _ in range(thread_count)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All results should be identical
        assert len(results) == thread_count
        assert all(r == results[0] for r in results)
        event("outcome=concurrent_deterministic")

    @given(
        worker_count=st.integers(min_value=5, max_value=30),
        iter_count=st.integers(min_value=10, max_value=50),
    )
    @settings(max_examples=20, deadline=None)
    def test_no_data_corruption(
        self, worker_count: int, iter_count: int
    ) -> None:
        """Property: No data corruption across variable concurrency."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource("user = User { $id } is { $status }")

        results: list[tuple[int, str, str]] = []
        lock = threading.Lock()

        def format_user(user_id: int, status: str) -> None:
            result, _ = bundle.format_pattern(
                "user", {"id": user_id, "status": status}
            )
            with lock:
                results.append((user_id, status, result))

        event(f"workers={worker_count}")

        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = []
            for i in range(iter_count):
                s = "online" if i % 2 == 0 else "offline"
                futures.append(pool.submit(format_user, i, s))

            for future in as_completed(futures):
                future.result()

        assert len(results) == iter_count

        for user_id, status, result in results:
            assert str(user_id) in result
            assert status in result
        event("outcome=no_corruption")


@pytest.mark.fuzz
class TestConcurrentWithReferences:
    """Intensive tests for concurrent resolution with message references.

    Tests reference chain resolution under heavy concurrent load.
    Designed for dedicated fuzzing runs.
    """

    @given(worker_count=st.integers(min_value=3, max_value=20))
    @settings(max_examples=20, deadline=None)
    def test_concurrent_reference_chains(
        self, worker_count: int
    ) -> None:
        """Property: Reference chains resolve consistently."""
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

        event(f"workers={worker_count}")
        iters = worker_count * 3

        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = [
                pool.submit(resolve_welcome)
                for _ in range(iters)
            ]
            for future in as_completed(futures):
                future.result()

        assert len(results) == iters
        expected = "Hello, World! Welcome!"
        assert all(r == expected for r in results)
        event("outcome=reference_chains_consistent")

    @given(thread_count=st.integers(min_value=5, max_value=30))
    @settings(max_examples=20, deadline=None)
    def test_concurrent_term_resolution(
        self, thread_count: int
    ) -> None:
        """Property: Term resolution is consistent across threads."""
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

        event(f"thread_count={thread_count}")

        threads = [
            threading.Thread(target=resolve_messages)
            for _ in range(thread_count)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(download_results) == thread_count
        assert len(about_results) == thread_count

        assert all("Firefox" in r for r in download_results)
        assert all("Firefox" in r for r in about_results)
        event("outcome=term_resolution_consistent")


@pytest.mark.fuzz
class TestConcurrentErrorHandling:
    """Intensive tests for concurrent error handling.

    Tests error path behavior under heavy concurrent load.
    Designed for dedicated fuzzing runs.
    """

    @given(worker_count=st.integers(min_value=3, max_value=15))
    @settings(max_examples=20, deadline=None)
    def test_concurrent_missing_messages(
        self, worker_count: int
    ) -> None:
        """Property: Missing message errors are consistent."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource("exists = This exists")

        results: list[tuple[str, int]] = []
        lock = threading.Lock()

        def format_message(msg_id: str) -> None:
            result, errors = bundle.format_pattern(msg_id)
            with lock:
                results.append((result, len(errors)))

        event(f"workers={worker_count}")
        repeats = worker_count * 2

        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = []
            for _ in range(repeats):
                futures.append(pool.submit(format_message, "exists"))
                futures.append(pool.submit(format_message, "missing"))

            for future in as_completed(futures):
                future.result()

        assert len(results) == repeats * 2

        exists_results = [
            r for r in results if "This exists" in r[0]
        ]
        missing_results = [r for r in results if r[1] > 0]

        assert len(exists_results) == repeats
        assert len(missing_results) == repeats
        event("outcome=error_handling_consistent")

    @given(worker_count=st.integers(min_value=3, max_value=15))
    @settings(max_examples=20, deadline=None)
    def test_concurrent_missing_variables(
        self, worker_count: int
    ) -> None:
        """Property: Missing variable errors are thread-safe."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource("msg = Hello, { $name }!")

        results: list[tuple[str, int]] = []
        lock = threading.Lock()

        def format_with_args(args: dict[str, str]) -> None:
            result, errors = bundle.format_pattern("msg", args)
            with lock:
                results.append((result, len(errors)))

        event(f"workers={worker_count}")
        iters = worker_count * 3

        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = []
            for i in range(iters):
                if i % 2 == 0:
                    futures.append(
                        pool.submit(
                            format_with_args, {"name": f"User{i}"}
                        )
                    )
                else:
                    futures.append(
                        pool.submit(format_with_args, {})
                    )

            for future in as_completed(futures):
                future.result()

        assert len(results) == iters
        event("outcome=missing_vars_consistent")


@pytest.mark.fuzz
class TestConcurrentMutation:
    """Tests for concurrent read/write operations on FluentBundle.

    These tests verify thread safety when add_resource() is called
    concurrently with format_pattern() calls. This simulates hot-reload
    scenarios where resources may be updated during active formatting.
    """

    @given(
        reader_count=st.integers(min_value=2, max_value=8),
        writer_count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=20, deadline=None)
    def test_concurrent_add_resource_while_formatting(
        self, reader_count: int, writer_count: int
    ) -> None:
        """Property: Concurrent read/write never crashes.

        Reader threads call format_pattern() while writer threads
        call add_resource() to add new messages.
        """
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource("initial = Initial message")

        results: list[tuple[str, str]] = []
        errors_encountered: list[Exception] = []
        lock = threading.Lock()

        def format_messages() -> None:
            for _ in range(10):
                try:
                    result, _ = bundle.format_pattern("initial")
                    with lock:
                        results.append(("initial", result))
                    for msg_id in ["dyn1", "dyn2", "dyn3"]:
                        result, errs = bundle.format_pattern(
                            msg_id
                        )
                        if not errs:
                            with lock:
                                results.append((msg_id, result))
                except Exception as e:
                    with lock:
                        errors_encountered.append(e)

        def add_resources() -> None:
            try:
                bundle.add_resource("dyn1 = Dynamic 1")
                bundle.add_resource("dyn2 = Dynamic 2")
                bundle.add_resource("dyn3 = Dynamic 3")
            except Exception as e:
                with lock:
                    errors_encountered.append(e)

        event(f"readers={reader_count}")
        event(f"writers={writer_count}")

        fmt_threads = [
            threading.Thread(target=format_messages)
            for _ in range(reader_count)
        ]
        add_threads = [
            threading.Thread(target=add_resources)
            for _ in range(writer_count)
        ]

        for t in fmt_threads:
            t.start()
        for t in add_threads:
            t.start()
        for t in fmt_threads + add_threads:
            t.join()

        assert not errors_encountered, (
            f"Exceptions: {errors_encountered}"
        )
        initial = [r for r in results if r[0] == "initial"]
        assert len(initial) >= reader_count
        event("outcome=concurrent_mutation_safe")

    @given(thread_count=st.integers(min_value=2, max_value=8))
    @settings(max_examples=20, deadline=None)
    def test_overwrite_message_while_formatting(
        self, thread_count: int
    ) -> None:
        """Property: Message overwrites are atomic.

        Formatters see either old or new value, never corrupted.
        """
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource("changing = Version A")

        results: list[str] = []
        lock = threading.Lock()
        stop_event = threading.Event()

        def format_continuously() -> None:
            while not stop_event.is_set():
                result, _ = bundle.format_pattern("changing")
                with lock:
                    results.append(result)

        def overwrite_message() -> None:
            for version in ["B", "C", "D", "E"]:
                bundle.add_resource(
                    f"changing = Version {version}"
                )

        event(f"thread_count={thread_count}")

        fmt_threads = [
            threading.Thread(target=format_continuously)
            for _ in range(thread_count)
        ]
        for t in fmt_threads:
            t.start()

        overwrite_thread = threading.Thread(
            target=overwrite_message
        )
        overwrite_thread.start()
        overwrite_thread.join()

        time.sleep(0.01)
        stop_event.set()

        for t in fmt_threads:
            t.join()

        valid = {
            "Version A", "Version B", "Version C",
            "Version D", "Version E",
        }
        for result in results:
            assert result in valid, (
                f"Got corrupted result: {result!r}"
            )

        assert len(results) >= thread_count
        event("outcome=atomic_overwrite")

    def test_concurrent_add_resource_idempotent(self) -> None:
        """Multiple threads adding the same resource should be idempotent.

        When multiple threads add identical resources, the end state
        should be consistent with a single add.
        """
        bundle = FluentBundle("en-US", use_isolating=False)

        errors_encountered: list[Exception] = []
        lock = threading.Lock()

        def add_same_resource() -> None:
            """Add the same resource from multiple threads."""
            try:
                bundle.add_resource("shared = This is shared content")
            except Exception as e:
                with lock:
                    errors_encountered.append(e)

        threads = [threading.Thread(target=add_same_resource) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # No exceptions should have occurred
        assert not errors_encountered

        # Message should be formatted correctly
        result, errors = bundle.format_pattern("shared")
        assert not errors
        assert result == "This is shared content"


class TestMemoryStability:
    """Soak tests for memory stability under sustained load.

    These tests verify that repeated operations don't cause memory leaks
    or unbounded growth. They run many iterations to expose issues that
    only manifest over time.

    Not fuzz-marked: soak tests need fixed iteration counts for reliable
    leak detection. Variable counts would make growth measurements noisy.
    """

    def test_repeated_bundle_creation_no_memory_growth(self) -> None:
        """Creating and discarding bundles should not leak memory.

        This tests that bundle cleanup is complete - no dangling references
        to parsed resources, caches, or internal state.
        """
        import gc  # noqa: PLC0415 - local import to avoid measuring import overhead

        # Warm up to avoid measuring one-time allocations
        for _ in range(10):
            bundle = FluentBundle("en-US", use_isolating=False)
            bundle.add_resource("msg = Hello")
            bundle.format_pattern("msg")
            del bundle

        gc.collect()

        # Get baseline memory (approximate via object count)
        gc.collect()
        baseline_objects = len(gc.get_objects())

        # Create and discard many bundles
        for i in range(100):
            bundle = FluentBundle("en-US", use_isolating=False)
            bundle.add_resource(f"msg{i % 10} = Message {i}")
            bundle.add_resource(
                """
complex = This is { $var ->
    [a] option A
    [b] option B
   *[other] default
}
"""
            )
            bundle.format_pattern(f"msg{i % 10}", {"var": f"value{i}"})
            bundle.format_pattern("complex", {"var": "a"})
            del bundle

            # Periodic GC to simulate real-world conditions
            if i % 25 == 0:
                gc.collect()

        gc.collect()
        final_objects = len(gc.get_objects())

        # Allow some growth for caching/interning, but flag major leaks
        # A leak would show O(N) growth; normal should be O(1) with some constant overhead
        growth = final_objects - baseline_objects
        # Allow up to 500 objects of growth (accounts for caching, interning, etc.)
        assert growth < 500, f"Potential memory leak: object count grew by {growth}"

    def test_repeated_format_no_memory_growth(self) -> None:
        """Repeated formatting of the same message should not leak.

        This tests that format_pattern() cleans up all intermediate state
        including resolution contexts, scope chains, and partial results.
        """
        import gc  # noqa: PLC0415 - local import to avoid measuring import overhead

        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            """
greeting = Hello, { $name }!
items = { $count ->
    [one] One item
   *[other] { $count } items
}
nested = { greeting } You have { items }.
"""
        )

        # Warm up
        for _ in range(100):
            bundle.format_pattern("nested", {"name": "User", "count": 5})

        gc.collect()
        baseline_objects = len(gc.get_objects())

        # Many format calls
        for i in range(1000):
            bundle.format_pattern("greeting", {"name": f"User{i % 50}"})
            bundle.format_pattern("items", {"count": i % 100})
            bundle.format_pattern("nested", {"name": f"User{i}", "count": i})

            if i % 200 == 0:
                gc.collect()

        gc.collect()
        final_objects = len(gc.get_objects())

        growth = final_objects - baseline_objects
        # Formatting should have zero net growth (no persistent allocations)
        assert growth < 200, f"Potential memory leak in format: object count grew by {growth}"

    def test_repeated_parse_serialize_cycle(self) -> None:
        """Repeated parse-serialize cycles should not leak memory.

        Tests that parser and serializer properly clean up after each operation.
        """
        import gc  # noqa: PLC0415 - local import to avoid measuring import overhead

        from ftllexengine.syntax.parser import FluentParserV1  # noqa: PLC0415
        from ftllexengine.syntax.serializer import serialize  # noqa: PLC0415

        parser = FluentParserV1()

        ftl_source = """
# Comment
msg1 = Simple message
msg2 = Message with { $var }
msg3 = { $count ->
    [one] One
   *[other] Many
}
-term = Term value
ref = { -term }
"""

        # Warm up
        for _ in range(10):
            ast = parser.parse(ftl_source)
            _ = serialize(ast)

        gc.collect()
        baseline_objects = len(gc.get_objects())

        # Many parse-serialize cycles
        for _ in range(200):
            ast = parser.parse(ftl_source)
            serialized = serialize(ast)
            # Verify round-trip works (sanity check)
            ast2 = parser.parse(serialized)
            assert len(ast.entries) == len(ast2.entries)

        gc.collect()
        final_objects = len(gc.get_objects())

        growth = final_objects - baseline_objects
        assert growth < 300, (
            f"Potential memory leak in parse/serialize: object count grew by {growth}"
        )
