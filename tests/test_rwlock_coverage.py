"""Edge case tests for RWLock implementation.

Tests verify:
- Error handling in all edge cases
- Thread safety edge cases
- State consistency in unusual scenarios
- Boundary conditions
"""

import threading
import time

import pytest

from ftllexengine.runtime.rwlock import RWLock


class TestRWLockErrorHandling:
    """Test error handling in edge cases."""

    def test_release_read_without_holding_lock(self) -> None:
        """Releasing read lock without holding it raises RuntimeError."""
        lock = RWLock()

        with pytest.raises(RuntimeError, match="does not hold read lock"):
            lock._release_read()

    def test_release_write_without_holding_lock(self) -> None:
        """Releasing write lock without holding it raises RuntimeError."""
        lock = RWLock()

        with pytest.raises(RuntimeError, match="does not hold write lock"):
            lock._release_write()

    def test_release_read_from_wrong_thread(self) -> None:
        """Releasing read lock from different thread raises RuntimeError."""
        lock = RWLock()
        acquired = threading.Event()

        def acquire_in_thread() -> None:
            lock._acquire_read()
            acquired.set()
            time.sleep(0.1)  # Hold lock
            lock._release_read()

        thread = threading.Thread(target=acquire_in_thread)
        thread.start()

        acquired.wait()

        # Try to release from main thread
        with pytest.raises(RuntimeError, match="does not hold read lock"):
            lock._release_read()

        thread.join()

    def test_release_write_from_wrong_thread(self) -> None:
        """Releasing write lock from different thread raises RuntimeError."""
        lock = RWLock()

        def acquire_in_thread() -> None:
            lock._acquire_write()

        thread = threading.Thread(target=acquire_in_thread)
        thread.start()
        thread.join()

        # Write lock held by other thread (now dead)
        with pytest.raises(RuntimeError, match="does not hold write lock"):
            lock._release_write()

    def test_double_release_read_lock(self) -> None:
        """Double releasing read lock raises RuntimeError."""
        lock = RWLock()

        lock._acquire_read()
        lock._release_read()

        with pytest.raises(RuntimeError, match="does not hold read lock"):
            lock._release_read()

    def test_double_release_write_lock(self) -> None:
        """Double releasing write lock raises RuntimeError."""
        lock = RWLock()

        lock._acquire_write()
        lock._release_write()

        with pytest.raises(RuntimeError, match="does not hold write lock"):
            lock._release_write()

    def test_read_to_write_upgrade_raises(self) -> None:
        """Attempting read-to-write upgrade raises RuntimeError."""
        lock = RWLock()

        # Intentionally nested to test upgrade rejection
        with lock.read():  # noqa: SIM117
            with pytest.raises(
                RuntimeError,
                match="Cannot upgrade read lock to write lock",
            ):
                lock._acquire_write()

    def test_read_to_write_upgrade_error_message(self) -> None:
        """Read-to-write upgrade error includes helpful message."""
        lock = RWLock()

        # Intentionally nested to test upgrade rejection error message
        with lock.read():  # noqa: SIM117
            with pytest.raises(
                RuntimeError,
                match="Release read lock before acquiring write lock",
            ):
                lock._acquire_write()

    def test_reentrant_read_over_release_raises(self) -> None:
        """Over-releasing reentrant read lock raises RuntimeError."""
        lock = RWLock()

        # Intentionally nested to test reentrant release tracking
        with lock.read():  # noqa: SIM117
            with lock.read():
                pass
            # Inner released

        # Outer released - now over-release
        with pytest.raises(RuntimeError, match="does not hold read lock"):
            lock._release_read()

    def test_reentrant_write_over_release_raises(self) -> None:
        """Over-releasing reentrant write lock raises RuntimeError."""
        lock = RWLock()

        # Intentionally nested to test reentrant release tracking
        with lock.write():  # noqa: SIM117
            with lock.write():
                pass
            # Inner released

        # Outer released - now over-release
        with pytest.raises(RuntimeError, match="does not hold write lock"):
            lock._release_write()



class TestRWLockBoundaryConditions:
    """Test boundary conditions and edge cases."""

    def test_zero_readers_state(self) -> None:
        """Lock state correct with zero readers."""
        lock = RWLock()

        assert lock._active_readers == 0
        assert len(lock._reader_threads) == 0
        assert lock._active_writer is None

    def test_zero_writers_state(self) -> None:
        """Lock state correct with zero writers."""
        lock = RWLock()

        assert lock._active_writer is None
        assert lock._waiting_writers == 0
        assert lock._writer_reentry_count == 0

    def test_single_thread_read_write_interleaving(self) -> None:
        """Single thread can interleave read and write acquisitions."""
        lock = RWLock()
        operations = []

        with lock.read():
            operations.append("read1")

        with lock.write():
            operations.append("write1")

        with lock.read():
            operations.append("read2")

        with lock.write():
            operations.append("write2")

        assert operations == ["read1", "write1", "read2", "write2"]

    def test_immediate_read_after_write_release(self) -> None:
        """Read lock can be acquired immediately after write release."""
        lock = RWLock()

        with lock.write():
            pass

        # Immediate read acquisition
        acquired = False
        with lock.read():
            acquired = True

        assert acquired

    def test_immediate_write_after_read_release(self) -> None:
        """Write lock can be acquired immediately after read release."""
        lock = RWLock()

        with lock.read():
            pass

        # Immediate write acquisition
        acquired = False
        with lock.write():
            acquired = True

        assert acquired

    def test_empty_context_manager(self) -> None:
        """Empty context manager blocks work correctly."""
        lock = RWLock()

        with lock.read():
            pass

        with lock.write():
            pass

    def test_nested_empty_context_managers(self) -> None:
        """Nested empty context managers work correctly."""
        lock = RWLock()

        # Intentionally nested to test reentrant empty contexts
        with lock.read():  # noqa: SIM117
            with lock.read():
                with lock.read():
                    pass

        # Intentionally nested to test reentrant empty contexts
        with lock.write():  # noqa: SIM117
            with lock.write():
                with lock.write():
                    pass


class TestRWLockThreadSafetyEdgeCases:
    """Test thread safety edge cases."""

    def test_concurrent_read_write_acquisition_race(self) -> None:
        """Concurrent read/write acquisitions don't cause race conditions."""
        lock = RWLock()
        results = []

        def reader() -> None:
            for _ in range(10):
                with lock.read():
                    results.append("R")

        def writer() -> None:
            for _ in range(10):
                with lock.write():
                    results.append("W")

        threads = [
            threading.Thread(target=reader),
            threading.Thread(target=writer),
            threading.Thread(target=reader),
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All operations completed
        assert results.count("R") == 20
        assert results.count("W") == 10

    def test_writer_waiting_count_consistency(self) -> None:
        """_waiting_writers count remains consistent under concurrency."""
        lock = RWLock()
        reader_active = threading.Event()
        writers_ready = threading.Barrier(5)

        def reader() -> None:
            with lock.read():
                reader_active.set()
                time.sleep(0.1)  # Hold lock

        def writer(_writer_id: int) -> None:
            reader_active.wait()
            writers_ready.wait()  # All writers ready simultaneously
            with lock.write():
                pass

        reader_thread = threading.Thread(target=reader)
        writer_threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]

        reader_thread.start()
        for thread in writer_threads:
            thread.start()

        reader_thread.join()
        for thread in writer_threads:
            thread.join()

        # All writers completed, count should be 0
        assert lock._waiting_writers == 0

    def test_active_readers_count_under_reentrant_releases(self) -> None:
        """_active_readers count correct with reentrant read releases."""
        lock = RWLock()

        def reader() -> None:
            # Intentionally nested to test reentrant reader count
            with lock.read():  # noqa: SIM117
                with lock.read():
                    with lock.read():
                        # 3 levels deep, but count should be 1
                        assert lock._active_readers == 1

        thread = threading.Thread(target=reader)
        thread.start()
        thread.join()

        # All released
        assert lock._active_readers == 0

    def test_writer_reentry_count_consistency(self) -> None:
        """_writer_reentry_count remains consistent with nested writes."""
        lock = RWLock()

        with lock.write():
            assert lock._writer_reentry_count == 0
            with lock.write():
                assert lock._writer_reentry_count == 1
                with lock.write():
                    assert lock._writer_reentry_count == 2
                assert lock._writer_reentry_count == 1
            assert lock._writer_reentry_count == 0

        assert lock._writer_reentry_count == 0


class TestRWLockDowngradingEdgeCases:
    """Test edge cases specific to lock downgrading."""

    def test_writer_held_reads_zero_after_full_release(self) -> None:
        """_writer_held_reads is 0 after all locks released."""
        lock = RWLock()

        with lock.write():
            lock._acquire_read()
            lock._acquire_read()
            lock._release_read()
            lock._release_read()
            assert lock._writer_held_reads == 0

    def test_partial_downgrade_release_before_write_release(self) -> None:
        """Can partially release downgraded reads before releasing write."""
        lock = RWLock()

        with lock.write():
            lock._acquire_read()
            lock._acquire_read()
            lock._acquire_read()

            lock._release_read()
            assert lock._writer_held_reads == 2

            lock._release_read()
            assert lock._writer_held_reads == 1

        # Last read converts on write release
        lock._release_read()

    def test_full_downgrade_release_before_write_release(self) -> None:
        """Can fully release all downgraded reads before releasing write."""
        lock = RWLock()

        with lock.write():
            lock._acquire_read()
            lock._acquire_read()

            lock._release_read()
            lock._release_read()

            assert lock._writer_held_reads == 0

        # No conversion needed - no writer_held_reads

    def test_downgrade_with_exception_cleans_state(self) -> None:
        """Exception during downgrade converts writer-held reads correctly."""
        lock = RWLock()
        thread_id = threading.get_ident()

        try:
            with lock.write():
                lock._acquire_read()
                lock._acquire_read()
                msg = "Test error"
                raise ValueError(msg)
        except ValueError:
            pass

        # Write lock released, but writer-held reads converted to regular reads
        assert lock._active_writer is None
        assert lock._writer_held_reads == 0
        assert lock._active_readers == 1  # Converted from writer-held reads
        assert lock._reader_threads[thread_id] == 2  # Count of converted reads

        # Clean up converted read locks
        lock._release_read()
        lock._release_read()

        # Now all locks fully released
        assert lock._active_readers == 0

    def test_reentrant_write_with_downgrade_state(self) -> None:
        """Reentrant write with downgrade maintains correct state."""
        lock = RWLock()

        with lock.write():
            lock._acquire_read()
            assert lock._writer_held_reads == 1

            with lock.write():  # Reentrant
                lock._acquire_read()
                assert lock._writer_held_reads == 2
            # Inner write released

            assert lock._writer_held_reads == 2
            lock._release_read()
            lock._release_read()

    def test_conversion_with_zero_writer_held_reads(self) -> None:
        """Write release with zero writer_held_reads doesn't create reader."""
        lock = RWLock()
        thread_id = threading.get_ident()

        with lock.write():
            pass  # No downgrade reads

        # No conversion should have occurred
        assert thread_id not in lock._reader_threads
        assert lock._active_readers == 0


class TestRWLockStateConsistency:
    """Test internal state consistency."""

    def test_reader_threads_dict_consistency(self) -> None:
        """_reader_threads dict maintains consistency across operations."""
        lock = RWLock()
        thread_id = threading.get_ident()

        # Initially empty
        assert thread_id not in lock._reader_threads

        lock._acquire_read()
        assert thread_id in lock._reader_threads
        assert lock._reader_threads[thread_id] == 1

        lock._acquire_read()
        assert lock._reader_threads[thread_id] == 2

        lock._release_read()
        assert lock._reader_threads[thread_id] == 1

        lock._release_read()
        assert thread_id not in lock._reader_threads

    def test_active_writer_consistency(self) -> None:
        """_active_writer maintains consistency across operations."""
        lock = RWLock()
        current_thread_id = threading.get_ident()

        assert lock._active_writer is None

        lock._acquire_write()
        assert lock._active_writer == current_thread_id

        lock._acquire_write()  # Reentrant
        assert lock._active_writer == current_thread_id

        lock._release_write()  # Release reentrant
        assert lock._active_writer == current_thread_id

        lock._release_write()  # Release outer
        assert lock._active_writer is None

    def test_condition_variable_notifications(self) -> None:
        """Condition variable notifications work correctly."""
        lock = RWLock()
        reader_notified = threading.Event()
        writer_notified = threading.Event()

        def reader() -> None:
            with lock.read():
                reader_notified.set()

        def writer() -> None:
            with lock.write():
                writer_notified.set()

        # Reader acquires
        reader_thread1 = threading.Thread(target=reader)
        reader_thread1.start()
        reader_notified.wait()

        # Writer waits
        writer_thread = threading.Thread(target=writer)
        writer_thread.start()

        # Release reader - should notify writer
        reader_thread1.join()
        writer_notified.wait(timeout=1.0)

        assert writer_notified.is_set()
        writer_thread.join()
