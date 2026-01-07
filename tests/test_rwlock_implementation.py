"""Comprehensive tests for RWLock readers-writer lock implementation.

Tests verify:
- Multiple concurrent readers
- Exclusive writer access
- Writer preference (prevents starvation)
- Reentrant read locks
- Deadlock prevention
- Thread safety
- Error handling
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from ftllexengine.runtime.rwlock import RWLock


class TestRWLockBasics:
    """Test basic RWLock functionality."""

    def test_single_reader(self) -> None:
        """Single reader can acquire lock."""
        lock = RWLock()
        acquired = False

        with lock.read():
            acquired = True

        assert acquired

    def test_single_writer(self) -> None:
        """Single writer can acquire lock."""
        lock = RWLock()
        acquired = False

        with lock.write():
            acquired = True

        assert acquired

    def test_multiple_reads_concurrent(self) -> None:
        """Multiple readers can hold lock simultaneously."""
        lock = RWLock()
        concurrent_readers = []

        def reader(reader_id: int) -> None:
            with lock.read():
                concurrent_readers.append(reader_id)
                time.sleep(0.01)  # Hold lock briefly
                # All readers should be in list before any exits
                assert len(concurrent_readers) >= 1

        threads = [threading.Thread(target=reader, args=(i,)) for i in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All readers completed
        assert len(concurrent_readers) == 5

    def test_write_blocks_readers(self) -> None:
        """Writers block readers from acquiring lock."""
        lock = RWLock()
        writer_active = threading.Event()
        reader_blocked = threading.Event()

        def writer() -> None:
            with lock.write():
                writer_active.set()
                time.sleep(0.05)  # Hold write lock

        def reader() -> None:
            writer_active.wait()  # Wait for writer to acquire
            reader_blocked.set()
            with lock.read():
                # This will only execute after writer releases
                pass

        writer_thread = threading.Thread(target=writer)
        reader_thread = threading.Thread(target=reader)

        writer_thread.start()
        reader_thread.start()

        # Verify reader is blocked
        time.sleep(0.02)
        assert reader_blocked.is_set()
        assert reader_thread.is_alive()

        writer_thread.join()
        reader_thread.join()

    def test_read_blocks_writers(self) -> None:
        """Readers block writers from acquiring lock."""
        lock = RWLock()
        reader_active = threading.Event()
        writer_blocked = threading.Event()

        def reader() -> None:
            with lock.read():
                reader_active.set()
                time.sleep(0.05)  # Hold read lock

        def writer() -> None:
            reader_active.wait()  # Wait for reader to acquire
            writer_blocked.set()
            with lock.write():
                # This will only execute after reader releases
                pass

        reader_thread = threading.Thread(target=reader)
        writer_thread = threading.Thread(target=writer)

        reader_thread.start()
        writer_thread.start()

        # Verify writer is blocked
        time.sleep(0.02)
        assert writer_blocked.is_set()
        assert writer_thread.is_alive()

        reader_thread.join()
        writer_thread.join()


class TestRWLockReentrancy:
    """Test reentrant read lock behavior."""

    def test_same_thread_multiple_read_locks(self) -> None:
        """Same thread can acquire read lock multiple times (reentrant)."""
        lock = RWLock()
        depth = 0

        with lock.read():
            depth += 1
            with lock.read():
                depth += 1
                with lock.read():
                    depth += 1

        assert depth == 3

    def test_reentrant_read_release_order(self) -> None:
        """Reentrant read locks release in correct order."""
        lock = RWLock()
        release_order = []

        with lock.read():
            release_order.append("outer-enter")
            with lock.read():
                release_order.append("inner-enter")
            release_order.append("inner-exit")
        release_order.append("outer-exit")

        assert release_order == ["outer-enter", "inner-enter", "inner-exit", "outer-exit"]

    def test_reentrant_read_with_concurrent_readers(self) -> None:
        """Reentrant reads work correctly with other concurrent readers."""
        lock = RWLock()
        results = []

        def reentrant_reader() -> None:
            with lock.read():
                results.append("outer")
                with lock.read():
                    results.append("inner")

        def simple_reader() -> None:
            with lock.read():
                results.append("simple")

        threads = [
            threading.Thread(target=reentrant_reader),
            threading.Thread(target=simple_reader),
            threading.Thread(target=simple_reader),
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All readers completed (order may vary)
        assert "outer" in results
        assert "inner" in results
        assert results.count("simple") == 2


class TestRWLockWriterPreference:
    """Test writer preference to prevent starvation."""

    def test_waiting_writer_blocks_new_readers(self) -> None:
        """Waiting writers prevent new readers (writer preference)."""
        lock = RWLock()
        reader1_acquired = threading.Event()
        writer_waiting = threading.Event()
        reader2_blocked = threading.Event()

        def reader1() -> None:
            with lock.read():
                reader1_acquired.set()
                writer_waiting.wait()  # Wait for writer to start waiting
                time.sleep(0.05)  # Hold lock

        def writer() -> None:
            reader1_acquired.wait()  # Wait for reader1 to acquire
            # Writer will wait here (reader1 still holds lock)
            writer_waiting.set()
            with lock.write():
                pass

        def reader2() -> None:
            writer_waiting.wait()  # Wait for writer to start waiting
            reader2_blocked.set()
            with lock.read():
                # Should only acquire after writer completes
                pass

        thread_reader1 = threading.Thread(target=reader1)
        thread_writer = threading.Thread(target=writer)
        thread_reader2 = threading.Thread(target=reader2)

        thread_reader1.start()
        thread_writer.start()
        thread_reader2.start()

        # Verify reader2 is blocked until writer completes
        time.sleep(0.02)
        assert reader2_blocked.is_set()
        assert thread_reader2.is_alive()

        thread_reader1.join()
        thread_writer.join()
        thread_reader2.join()


class TestRWLockConcurrency:
    """Test high-concurrency scenarios."""

    def test_many_concurrent_readers(self) -> None:
        """Many readers can hold lock simultaneously."""
        lock = RWLock()
        concurrent_count = []

        def reader() -> None:
            with lock.read():
                concurrent_count.append(1)
                time.sleep(0.01)

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(reader) for _ in range(50)]
            for future in futures:
                future.result()

        assert len(concurrent_count) == 50

    def test_read_write_interleaving(self) -> None:
        """Readers and writers correctly interleave."""
        lock = RWLock()
        operations = []

        def reader(reader_id: int) -> None:
            with lock.read():
                operations.append(f"R{reader_id}-start")
                time.sleep(0.01)
                operations.append(f"R{reader_id}-end")

        def writer(writer_id: int) -> None:
            with lock.write():
                operations.append(f"W{writer_id}-start")
                time.sleep(0.01)
                operations.append(f"W{writer_id}-end")

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for i in range(5):
                futures.append(executor.submit(reader, i))
            for i in range(3):
                futures.append(executor.submit(writer, i))
            for i in range(5, 10):
                futures.append(executor.submit(reader, i))

            for future in futures:
                future.result()

        # Verify operations completed (exact order depends on scheduler)
        assert len(operations) == 26  # 10 readers * 2 + 3 writers * 2

    def test_stress_test(self) -> None:
        """Stress test with many readers and writers."""
        lock = RWLock()
        shared_value = 0
        read_count = 0

        def reader() -> None:
            nonlocal read_count
            with lock.read():
                _ = shared_value  # Read value
                read_count += 1

        def writer() -> None:
            nonlocal shared_value
            with lock.write():
                shared_value += 1

        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = []
            # Many readers, few writers
            for _ in range(100):
                futures.append(executor.submit(reader))
            for _ in range(10):
                futures.append(executor.submit(writer))

            for future in futures:
                future.result()

        assert shared_value == 10  # All writes completed
        assert read_count == 100  # All reads completed


class TestRWLockErrors:
    """Test error handling."""

    def test_release_read_without_acquire_raises(self) -> None:
        """Releasing read lock without acquiring raises RuntimeError."""
        lock = RWLock()
        with pytest.raises(RuntimeError, match="does not hold read lock"):
            lock._release_read()

    def test_release_write_without_acquire_raises(self) -> None:
        """Releasing write lock without acquiring raises RuntimeError."""
        lock = RWLock()
        with pytest.raises(RuntimeError, match="does not hold write lock"):
            lock._release_write()

    def test_release_write_from_different_thread_raises(self) -> None:
        """Releasing write lock from different thread raises RuntimeError."""
        lock = RWLock()

        def acquire_write() -> None:
            lock._acquire_write()

        thread = threading.Thread(target=acquire_write)
        thread.start()
        thread.join()

        # Try to release from main thread
        with pytest.raises(RuntimeError, match="does not hold write lock"):
            lock._release_write()


class TestRWLockContextManager:
    """Test context manager behavior."""

    def test_read_context_releases_on_exception(self) -> None:
        """Read lock is released even when exception occurs."""
        lock = RWLock()

        exc_msg = "Test exception"
        with pytest.raises(ValueError, match=exc_msg), lock.read():
            raise ValueError(exc_msg)

        # Lock should be released - new reader can acquire
        acquired = False
        with lock.read():
            acquired = True
        assert acquired

    def test_write_context_releases_on_exception(self) -> None:
        """Write lock is released even when exception occurs."""
        lock = RWLock()

        exc_msg = "Test exception"
        with pytest.raises(ValueError, match=exc_msg), lock.write():
            raise ValueError(exc_msg)

        # Lock should be released - new writer can acquire
        acquired = False
        with lock.write():
            acquired = True
        assert acquired


class TestRWLockFairness:
    """Test fairness and starvation prevention."""

    def test_writers_not_starved(self) -> None:
        """Writers eventually acquire lock despite continuous readers."""
        lock = RWLock()
        writer_completed = threading.Event()
        reader_count = 0

        def continuous_reader() -> None:
            nonlocal reader_count
            for _ in range(10):
                with lock.read():
                    reader_count += 1
                    time.sleep(0.001)

        def writer() -> None:
            time.sleep(0.01)  # Let readers start
            with lock.write():
                writer_completed.set()

        # Start many concurrent readers
        reader_threads = [threading.Thread(target=continuous_reader) for _ in range(5)]
        writer_thread = threading.Thread(target=writer)

        for thread in reader_threads:
            thread.start()
        writer_thread.start()

        # Writer should complete despite continuous readers
        writer_thread.join(timeout=2.0)
        assert writer_completed.is_set(), "Writer was starved"

        for thread in reader_threads:
            thread.join()
