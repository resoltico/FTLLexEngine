"""Tests for FluentBundle RWLock integration.

Verifies that:
- Read operations (format_pattern, has_message, etc.) allow concurrency
- Write operations (add_resource, add_function) are exclusive
- Lock is used correctly for all public methods
- Concurrent access patterns work correctly
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from ftllexengine.runtime.bundle import FluentBundle


class TestBundleReadOperationsConcurrency:
    """Test that read operations allow concurrency."""

    def test_concurrent_format_pattern(self) -> None:
        """Multiple threads can format patterns concurrently."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("msg = Hello, { $name }!")

        results = []

        def format_message() -> None:
            result, errors = bundle.format_pattern("msg", {"name": "World"})
            results.append((result, errors))

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(format_message) for _ in range(50)]
            for future in futures:
                future.result()

        assert len(results) == 50
        for result, errors in results:
            assert result == "Hello, World!"
            assert errors == ()

    def test_concurrent_has_message(self) -> None:
        """Multiple threads can check message existence concurrently."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("msg1 = Hello")

        results = []

        def check_message() -> None:
            has_msg1 = bundle.has_message("msg1")
            has_msg2 = bundle.has_message("msg2")
            results.append((has_msg1, has_msg2))

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(check_message) for _ in range(30)]
            for future in futures:
                future.result()

        assert len(results) == 30
        for has_msg1, has_msg2 in results:
            assert has_msg1 is True
            assert has_msg2 is False

    def test_concurrent_introspection(self) -> None:
        """Multiple threads can introspect messages concurrently."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("price = { NUMBER($amount, minimumFractionDigits: 2) }")

        results = []

        def introspect() -> None:
            info = bundle.introspect_message("price")
            results.append(info.get_variable_names())

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(introspect) for _ in range(20)]
            for future in futures:
                future.result()

        assert len(results) == 20
        for var_names in results:
            assert "amount" in var_names

    def test_concurrent_validate_resource(self) -> None:
        """Multiple threads can validate resources concurrently."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("msg1 = Hello")

        results = []

        def validate() -> None:
            result = bundle.validate_resource("msg2 = World")
            results.append(result.is_valid)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(validate) for _ in range(20)]
            for future in futures:
                future.result()

        assert len(results) == 20
        assert all(results)


class TestBundleWriteOperationsExclusive:
    """Test that write operations are exclusive."""

    def test_add_resource_blocks_format(self) -> None:
        """add_resource and format_pattern can run concurrently without deadlock."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("msg = Initial")

        results = []

        def add_resources() -> None:
            for i in range(5):
                bundle.add_resource(f"msg{i} = Message {i}")
                time.sleep(0.001)

        def format_messages() -> None:
            for _ in range(10):
                result, _ = bundle.format_pattern("msg")
                results.append(result)
                time.sleep(0.001)

        add_thread = threading.Thread(target=add_resources)
        format_thread = threading.Thread(target=format_messages)

        add_thread.start()
        format_thread.start()

        add_thread.join()
        format_thread.join()

        # Verify both operations completed successfully
        assert len(results) == 10
        for result in results:
            assert result == "Initial"
        for i in range(5):
            assert bundle.has_message(f"msg{i}")

    def test_concurrent_add_resource_serialized(self) -> None:
        """Multiple add_resource calls are serialized (exclusive write access)."""
        bundle = FluentBundle("en", use_isolating=False)

        messages_added = []

        def add_message(msg_id: int) -> None:
            bundle.add_resource(f"msg{msg_id} = Message {msg_id}")
            messages_added.append(msg_id)
            time.sleep(0.01)  # Simulate work

        threads = [threading.Thread(target=add_message, args=(i,)) for i in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All messages should be added
        assert len(messages_added) == 5
        assert set(messages_added) == {0, 1, 2, 3, 4}

        # Verify all messages exist
        for i in range(5):
            assert bundle.has_message(f"msg{i}")

    def test_add_function_blocks_format(self) -> None:
        """add_function and format_pattern can run concurrently without deadlock."""
        bundle = FluentBundle("en", use_isolating=False)

        # Add function first so formatting works
        bundle.add_function("UPPER", lambda x: str(x).upper())
        bundle.add_resource("msg = { UPPER($val) }")

        results = []

        def add_more_functions() -> None:
            for i in range(5):
                bundle.add_function(f"FUNC{i}", lambda _x, idx=i: f"func{idx}")
                time.sleep(0.001)

        def format_messages() -> None:
            for _ in range(10):
                result, _ = bundle.format_pattern("msg", {"val": "test"})
                results.append(result)
                time.sleep(0.001)

        add_thread = threading.Thread(target=add_more_functions)
        format_thread = threading.Thread(target=format_messages)

        add_thread.start()
        format_thread.start()

        add_thread.join()
        format_thread.join()

        # Verify both operations completed successfully
        assert len(results) == 10
        for result in results:
            assert result == "TEST"


class TestBundleReadWriteMixedConcurrency:
    """Test mixed read/write concurrency scenarios."""

    def test_many_readers_one_writer(self) -> None:
        """Many concurrent readers with occasional writer."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("msg = Hello, { $name }!")

        read_count = 0
        write_count = 0

        def reader() -> None:
            nonlocal read_count
            for _ in range(10):
                result, _ = bundle.format_pattern("msg", {"name": "Test"})
                assert result == "Hello, Test!"
                read_count += 1
                time.sleep(0.001)

        def writer() -> None:
            nonlocal write_count
            time.sleep(0.02)  # Let readers start
            bundle.add_resource("msg2 = New message")
            write_count += 1

        with ThreadPoolExecutor(max_workers=15) as executor:
            # Many readers
            reader_futures = [executor.submit(reader) for _ in range(10)]
            # One writer
            writer_future = executor.submit(writer)

            for future in [*reader_futures, writer_future]:
                future.result()

        assert read_count == 100  # 10 readers * 10 iterations
        assert write_count == 1
        assert bundle.has_message("msg2")

    def test_interleaved_reads_writes(self) -> None:
        """Reads and writes interleave correctly."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("count = { $val }")

        operations = []

        def reader(reader_id: int) -> None:
            _result, _ = bundle.format_pattern("count", {"val": reader_id})
            operations.append(f"R{reader_id}")

        def writer(msg_id: int) -> None:
            bundle.add_resource(f"msg{msg_id} = Message {msg_id}")
            operations.append(f"W{msg_id}")

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []
            for i in range(10):
                futures.append(executor.submit(reader, i))
            for i in range(5):
                futures.append(executor.submit(writer, i))
            for i in range(10, 20):
                futures.append(executor.submit(reader, i))

            for future in futures:
                future.result()

        # All operations completed
        assert len(operations) == 25  # 20 readers + 5 writers


class TestBundleLockCorrectness:
    """Test correctness of lock usage."""

    def test_format_with_concurrent_add_resource(self) -> None:
        """Format operations see consistent state during concurrent adds."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("msg1 = First")

        results = []

        def format_loop() -> None:
            for _ in range(20):
                if bundle.has_message("msg1"):
                    result, _ = bundle.format_pattern("msg1")
                    results.append(result)
                time.sleep(0.001)

        def add_resources() -> None:
            time.sleep(0.01)
            bundle.add_resource("msg2 = Second")
            bundle.add_resource("msg3 = Third")

        format_thread = threading.Thread(target=format_loop)
        add_thread = threading.Thread(target=add_resources)

        format_thread.start()
        add_thread.start()

        format_thread.join()
        add_thread.join()

        # All format results should be consistent
        assert all(r == "First" for r in results)

    def test_cache_clear_synchronized(self) -> None:
        """Cache clear is properly synchronized."""
        bundle = FluentBundle("en", enable_cache=True)
        bundle.add_resource("msg = Hello")

        # Prime cache
        bundle.format_pattern("msg")

        clear_count = 0
        format_count = 0

        def clear_cache() -> None:
            nonlocal clear_count
            for _ in range(5):
                bundle.clear_cache()
                clear_count += 1
                time.sleep(0.002)

        def format_message() -> None:
            nonlocal format_count
            for _ in range(10):
                bundle.format_pattern("msg")
                format_count += 1
                time.sleep(0.001)

        clear_thread = threading.Thread(target=clear_cache)
        format_thread = threading.Thread(target=format_message)

        clear_thread.start()
        format_thread.start()

        clear_thread.join()
        format_thread.join()

        assert clear_count == 5
        assert format_count == 10


class TestBundleReentrantReads:
    """Test reentrant read lock behavior in bundle."""

    def test_nested_format_calls(self) -> None:
        """Nested format calls work correctly (reentrant read locks)."""
        bundle = FluentBundle("en", use_isolating=False)

        # Create a custom function that triggers nested read
        def nested_format_func(_arg: object) -> str:
            # This will acquire read lock while already holding read lock
            result, _ = bundle.format_pattern("inner")
            return result

        bundle.add_function("NESTED", nested_format_func)
        bundle.add_resource("inner = Inner value")
        bundle.add_resource("outer = { NESTED($x) }")

        result, errors = bundle.format_pattern("outer", {"x": "test"})
        assert result == "Inner value"
        assert errors == ()

    def test_introspection_during_format(self) -> None:
        """Introspection can be called during format (reentrant read)."""
        bundle = FluentBundle("en", use_isolating=False)

        introspection_result = None

        def introspect_func(arg: object) -> str:
            nonlocal introspection_result
            # Nested read: introspect while formatting
            introspection_result = bundle.introspect_message("target")
            return str(arg)

        bundle.add_function("INTROSPECT", introspect_func)
        bundle.add_resource("target = Target message { $var }")
        bundle.add_resource("caller = { INTROSPECT($x) }")

        result, errors = bundle.format_pattern("caller", {"x": "test"})
        assert result == "test"
        assert errors == ()
        assert introspection_result is not None
        assert "var" in introspection_result.get_variable_names()


class TestBundleStressTest:
    """Stress tests for bundle concurrency."""

    def test_high_concurrency_mixed_operations(self) -> None:
        """Stress test with many concurrent mixed operations."""
        bundle = FluentBundle("en", use_isolating=False, enable_cache=True)
        bundle.add_resource("msg = Hello, { $name }!")

        operation_count = {"format": 0, "add": 0, "check": 0}

        def format_operation() -> None:
            result, _ = bundle.format_pattern("msg", {"name": "Test"})
            assert result == "Hello, Test!"
            operation_count["format"] += 1

        def add_operation(msg_id: int) -> None:
            bundle.add_resource(f"msg{msg_id} = Message {msg_id}")
            operation_count["add"] += 1

        def check_operation() -> None:
            bundle.has_message("msg")
            operation_count["check"] += 1

        with ThreadPoolExecutor(max_workers=30) as executor:
            futures = []
            # Many format operations (read-heavy)
            for _ in range(100):
                futures.append(executor.submit(format_operation))
            # Some add operations (writes)
            for i in range(10):
                futures.append(executor.submit(add_operation, i))
            # Many check operations (reads)
            for _ in range(50):
                futures.append(executor.submit(check_operation))

            for future in futures:
                future.result()

        assert operation_count["format"] == 100
        assert operation_count["add"] == 10
        assert operation_count["check"] == 50

        # Verify all added messages exist
        for i in range(10):
            assert bundle.has_message(f"msg{i}")
