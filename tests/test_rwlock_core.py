"""Tests for RWLock readers-writer lock implementation.

Tests verify:
- Multiple concurrent readers
- Exclusive writer access
- Writer preference (prevents starvation)
- Reentrant read locks
- Read-to-write upgrade rejection
- Write-to-write reentry rejection
- Write-to-read downgrade rejection
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
    """Test reentrant read lock behavior and lock acquisition prohibitions."""

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

    def test_read_to_write_upgrade_rejected(self) -> None:
        """Read-to-write lock upgrade raises RuntimeError."""
        lock = RWLock()

        with lock.read(), pytest.raises(
            RuntimeError,
            match="Cannot upgrade read lock to write lock",
        ), lock.write():
            pass  # Should never reach here

    def test_read_to_write_upgrade_rejected_with_message(self) -> None:
        """Read-to-write upgrade error message includes guidance."""
        lock = RWLock()

        with lock.read(), pytest.raises(
            RuntimeError,
            match="Release read lock before acquiring write lock",
        ), lock.write():
            pass

    def test_write_to_write_reentry_rejected(self) -> None:
        """Write-to-write reentry raises RuntimeError."""
        lock = RWLock()

        with lock.write(), pytest.raises(
            RuntimeError,
            match="Cannot acquire write lock: already holding write lock",
        ), lock.write():
            pass  # Should never reach here

    def test_write_to_write_reentry_rejected_with_message(self) -> None:
        """Write-to-write reentry error message includes guidance."""
        lock = RWLock()

        with lock.write(), pytest.raises(
            RuntimeError,
            match="Release the write lock before acquiring it again",
        ), lock.write():
            pass

    def test_write_to_read_downgrade_rejected(self) -> None:
        """Write-to-read downgrade raises RuntimeError."""
        lock = RWLock()

        with lock.write(), pytest.raises(
            RuntimeError,
            match="Cannot acquire read lock while holding write lock",
        ), lock.read():
            pass  # Should never reach here

    def test_write_to_read_downgrade_rejected_with_message(self) -> None:
        """Write-to-read downgrade error message includes guidance."""
        lock = RWLock()

        with lock.write(), pytest.raises(
            RuntimeError,
            match="Release the write lock before acquiring a read lock",
        ), lock.read():
            pass


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


class TestRWLockInspection:
    """Tests for RWLock state inspection properties.

    Covers reader_count, writer_active, and writers_waiting.
    """

    def test_reader_count_zero_when_idle(self) -> None:
        """reader_count is 0 when no thread holds a read lock."""
        lock = RWLock()
        assert lock.reader_count == 0

    def test_reader_count_one_inside_read(self) -> None:
        """reader_count is 1 while one thread holds a read lock."""
        lock = RWLock()
        with lock.read():
            assert lock.reader_count == 1
        assert lock.reader_count == 0

    def test_reader_count_reentrant_read_still_one(self) -> None:
        """Reentrant read by the same thread counts as one reader, not two."""
        lock = RWLock()
        with lock.read():
            with lock.read():
                assert lock.reader_count == 1
            assert lock.reader_count == 1
        assert lock.reader_count == 0

    def test_reader_count_concurrent_readers(self) -> None:
        """reader_count reflects all concurrent readers."""
        lock = RWLock()
        # Two-phase barrier: phase 1 ensures all are inside the lock before
        # any appends; phase 2 holds all inside until every thread has appended,
        # preventing any thread from releasing its read lock prematurely.
        barrier = threading.Barrier(3)
        observed_counts: list[int] = []

        def reader() -> None:
            with lock.read():
                barrier.wait()  # Phase 1: all three inside simultaneously
                observed_counts.append(lock.reader_count)
                barrier.wait()  # Phase 2: hold lock until all have appended

        threads = [threading.Thread(target=reader) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(c == 3 for c in observed_counts), (
            f"Expected 3 readers, got {observed_counts}"
        )

    def test_writer_active_false_when_idle(self) -> None:
        """writer_active is False when no thread holds the write lock."""
        lock = RWLock()
        assert lock.writer_active is False

    def test_writer_active_true_inside_write(self) -> None:
        """writer_active is True while a thread holds the write lock."""
        lock = RWLock()
        with lock.write():
            assert lock.writer_active is True
        assert lock.writer_active is False

    def test_writer_active_false_inside_read(self) -> None:
        """writer_active is False when only a read lock is held."""
        lock = RWLock()
        with lock.read():
            assert lock.writer_active is False

    def test_writers_waiting_zero_when_idle(self) -> None:
        """writers_waiting is 0 when no thread is blocked on write lock."""
        lock = RWLock()
        assert lock.writers_waiting == 0

    def test_writers_waiting_increments_under_read_contention(self) -> None:
        """writers_waiting is >= 1 while a writer is blocked by an active reader.

        Synchronization protocol:
          1. Reader acquires lock, signals main thread.
          2. Main thread starts writer thread (will block on write lock).
          3. Main thread sleeps 50ms — enough time for writer to enter
             _acquire_write and block on the condition variable.
          4. Main thread samples writers_waiting (must be 1).
          5. Main thread signals reader to release, unblocking the writer.
        """
        lock = RWLock()
        reader_holding = threading.Event()
        reader_can_release = threading.Event()

        def blocking_reader() -> None:
            with lock.read():
                reader_holding.set()
                reader_can_release.wait()  # Hold until main thread says release

        def waiting_writer() -> None:
            with lock.write():
                pass  # Acquire and immediately release

        r = threading.Thread(target=blocking_reader)
        r.start()

        reader_holding.wait()  # Reader is holding the read lock

        w = threading.Thread(target=waiting_writer)
        w.start()

        # 50ms is ample time for waiting_writer to enter _acquire_write and block
        # on the condition variable (which increments _waiting_writers).
        time.sleep(0.05)
        observed_waiting = lock.writers_waiting

        reader_can_release.set()  # Release reader; writer can now acquire lock

        r.join()
        w.join()

        assert observed_waiting >= 1, (
            f"writers_waiting never >= 1: observed={observed_waiting}"
        )
        assert lock.writers_waiting == 0  # Back to 0 after writer completes
