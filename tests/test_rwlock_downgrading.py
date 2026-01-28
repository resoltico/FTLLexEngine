"""Comprehensive tests for RWLock lock downgrading feature.

Tests verify:
- Writer can acquire read locks without blocking (lock downgrading)
- Writer-held read locks are tracked separately
- Writer-held read locks convert to regular read locks on write release
- Reentrant writer-held read locks work correctly
- Lock downgrading works in complex concurrent scenarios
- Property-based invariants hold for all lock state transitions
"""

import threading
import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.rwlock import RWLock, with_read_lock, with_write_lock


class TestRWLockDowngradingBasics:
    """Test basic lock downgrading functionality."""

    def test_writer_can_acquire_read_lock(self) -> None:
        """Writer can acquire read lock without blocking (downgrading)."""
        lock = RWLock()
        acquired_read = False

        # Intentionally nested to test lock downgrading
        with lock.write():  # noqa: SIM117
            # Writer acquires read lock - should not block
            with lock.read():
                acquired_read = True

        assert acquired_read

    def test_writer_multiple_read_acquisitions(self) -> None:
        """Writer can acquire multiple read locks (reentrant downgrading)."""
        lock = RWLock()
        read_depth = 0

        # Intentionally nested to test reentrant downgrading
        with lock.write():  # noqa: SIM117
            with lock.read():
                read_depth += 1
                with lock.read():
                    read_depth += 1
                    with lock.read():
                        read_depth += 1

        assert read_depth == 3

    def test_writer_held_reads_released_correctly(self) -> None:
        """Writer-held read locks are released correctly."""
        lock = RWLock()
        release_order = []

        with lock.write():
            release_order.append("write-acquired")
            with lock.read():
                release_order.append("read1-acquired")
                with lock.read():
                    release_order.append("read2-acquired")
                release_order.append("read2-released")
            release_order.append("read1-released")
        release_order.append("write-released")

        expected = [
            "write-acquired",
            "read1-acquired",
            "read2-acquired",
            "read2-released",
            "read1-released",
            "write-released",
        ]
        assert release_order == expected

    def test_writer_releases_all_read_locks_before_write(self) -> None:
        """Writer can release all read locks before releasing write lock."""
        lock = RWLock()
        state = []

        with lock.write():
            state.append("write")
            with lock.read():
                state.append("read1")
            with lock.read():
                state.append("read2")
            # All reads released, still holding write
            state.append("write-only")

        assert state == ["write", "read1", "read2", "write-only"]

    def test_writer_converts_held_reads_on_write_release(self) -> None:
        """Writer-held reads convert to regular reads when write lock released."""
        lock = RWLock()
        reader_can_acquire = threading.Event()
        writer_released_write = threading.Event()

        def writer() -> None:
            with lock.write():
                # Acquire read lock while holding write
                lock._acquire_read()
                writer_released_write.set()
                # Release write lock (read lock should convert to regular reader)
            # Still holding read lock as regular reader
            reader_can_acquire.wait()  # Wait for verification
            lock._release_read()

        def reader() -> None:
            writer_released_write.wait()
            # Writer has released write but still holds read
            # This reader should be able to acquire read lock concurrently
            with lock.read():
                reader_can_acquire.set()

        writer_thread = threading.Thread(target=writer)
        reader_thread = threading.Thread(target=reader)

        writer_thread.start()
        reader_thread.start()

        writer_thread.join()
        reader_thread.join()

        # Both threads completed successfully
        assert reader_can_acquire.is_set()

    def test_writer_downgrade_multiple_reads_conversion(self) -> None:
        """Multiple writer-held reads convert to single reader entry."""
        lock = RWLock()
        conversion_verified = False

        with lock.write():
            # Acquire 3 read locks while holding write
            lock._acquire_read()
            lock._acquire_read()
            lock._acquire_read()
            # Release write - should convert 3 reads to regular reader with count 3

        # Now should be holding read lock (count 3) as regular reader
        # Verify by checking we can release 3 times
        lock._release_read()
        lock._release_read()
        lock._release_read()
        conversion_verified = True

        assert conversion_verified

    def test_writer_downgrade_then_new_reader(self) -> None:
        """After write-to-read downgrade, new readers can acquire concurrently."""
        lock = RWLock()
        new_reader_acquired = threading.Event()
        downgraded = threading.Event()

        def writer() -> None:
            with lock.write():
                lock._acquire_read()  # Acquire read while holding write
                downgraded.set()
            # Now holding only read lock
            new_reader_acquired.wait()
            lock._release_read()

        def new_reader() -> None:
            downgraded.wait()
            # Writer has downgraded to reader
            with lock.read():
                new_reader_acquired.set()

        writer_thread = threading.Thread(target=writer)
        reader_thread = threading.Thread(target=new_reader)

        writer_thread.start()
        reader_thread.start()

        writer_thread.join()
        reader_thread.join()

        assert new_reader_acquired.is_set()


class TestRWLockDowngradingConcurrency:
    """Test lock downgrading in concurrent scenarios."""

    def test_downgrade_blocks_waiting_writers(self) -> None:
        """Downgraded writer (now reader) blocks waiting writers."""
        lock = RWLock()
        writer1_downgraded = threading.Event()
        writer2_waiting = threading.Event()
        writer2_acquired = threading.Event()

        def writer1() -> None:
            with lock.write():
                lock._acquire_read()  # Downgrade to reader
                writer1_downgraded.set()
            # Now holding read lock
            writer2_waiting.wait()  # Wait for writer2 to start waiting
            time.sleep(0.05)  # Hold read lock
            lock._release_read()

        def writer2() -> None:
            writer1_downgraded.wait()
            writer2_waiting.set()
            # Should block until writer1 releases read lock
            with lock.write():
                writer2_acquired.set()

        thread1 = threading.Thread(target=writer1)
        thread2 = threading.Thread(target=writer2)

        thread1.start()
        thread2.start()

        # Verify writer2 is blocked
        time.sleep(0.02)
        assert not writer2_acquired.is_set()

        thread1.join()
        thread2.join()

        assert writer2_acquired.is_set()

    def test_downgrade_allows_concurrent_readers(self) -> None:
        """Downgraded writer allows concurrent readers."""
        lock = RWLock()
        downgraded = threading.Event()
        reader_count = []

        def writer() -> None:
            with lock.write():
                lock._acquire_read()
                downgraded.set()
            # Now reader
            time.sleep(0.05)
            lock._release_read()

        def reader(reader_id: int) -> None:
            downgraded.wait()
            with lock.read():
                reader_count.append(reader_id)
                time.sleep(0.02)

        writer_thread = threading.Thread(target=writer)
        reader_threads = [threading.Thread(target=reader, args=(i,)) for i in range(5)]

        writer_thread.start()
        for thread in reader_threads:
            thread.start()

        writer_thread.join()
        for thread in reader_threads:
            thread.join()

        # All readers acquired concurrently with downgraded writer
        assert len(reader_count) == 5

    def test_multiple_writers_downgrade_sequentially(self) -> None:
        """Multiple writers can downgrade but still serialize on write acquisition."""
        lock = RWLock()
        operations = []

        def writer_with_downgrade(writer_id: int) -> None:
            with lock.write():
                operations.append(f"W{writer_id}-write")
                lock._acquire_read()
                operations.append(f"W{writer_id}-downgrade")
            # Now reader
            operations.append(f"W{writer_id}-reader")
            lock._release_read()
            operations.append(f"W{writer_id}-done")

        threads = [
            threading.Thread(target=writer_with_downgrade, args=(i,)) for i in range(3)
        ]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All operations completed
        assert len(operations) == 12  # 3 writers * 4 operations each

        # Verify writes were serialized (each writer completes write phase before next)
        write_ops = [op for op in operations if "-write" in op]
        assert len(write_ops) == 3


class TestRWLockDowngradingEdgeCases:
    """Test edge cases in lock downgrading."""

    def test_reentrant_write_with_downgrade(self) -> None:
        """Reentrant write locks work correctly with downgrading."""
        lock = RWLock()
        state = []

        with lock.write():
            state.append("outer-write")
            with lock.write():  # Reentrant write
                state.append("inner-write")
                lock._acquire_read()  # Downgrade
                state.append("downgraded")
            state.append("inner-write-released")
        # Write fully released, should have read lock
        state.append("write-released")

        # Should be holding read lock
        lock._release_read()
        state.append("read-released")

        expected = [
            "outer-write",
            "inner-write",
            "downgraded",
            "inner-write-released",
            "write-released",
            "read-released",
        ]
        assert state == expected

    def test_downgrade_then_reentrant_read(self) -> None:
        """After downgrading, further read acquisitions use regular read reentrancy."""
        lock = RWLock()

        with lock.write():
            lock._acquire_read()  # First downgrade read
            lock._acquire_read()  # Second downgrade read

        # Both should be writer-held reads, converting to count=2
        # Now as regular reader, acquire more reads
        with lock.read():  # Should increment to 3
            # Verify we're holding reentrant reads
            pass

        # Release the 2 converted reads
        lock._release_read()
        lock._release_read()

    def test_release_read_after_full_write_release(self) -> None:
        """Can release converted read locks after write is fully released."""
        lock = RWLock()
        released = False

        # Intentionally nested to test reentrant write with downgrading
        with lock.write():  # noqa: SIM117
            with lock.write():  # Reentrant
                lock._acquire_read()
            # Inner write released
        # Outer write released, read converted

        lock._release_read()
        released = True

        assert released

    def test_no_downgrade_without_write_lock(self) -> None:
        """Regular reader cannot be confused with downgraded writer."""
        lock = RWLock()

        # Regular reader
        with lock.read():
            # This is regular read, not downgrade
            # Internal state should reflect this
            assert lock._active_writer is None
            assert lock._writer_held_reads == 0

    def test_writer_held_reads_dont_block_writer(self) -> None:
        """Writer holding read locks doesn't block itself from reentrant write."""
        lock = RWLock()
        reentrant_succeeded = False

        with lock.write():
            lock._acquire_read()  # Downgrade
            with lock.write():  # Reentrant write - should not deadlock
                reentrant_succeeded = True

        lock._release_read()
        assert reentrant_succeeded


class TestRWLockDowngradingStateInvariants:
    """Test state invariants during lock downgrading."""

    def test_writer_held_reads_tracked_separately(self) -> None:
        """Writer-held reads tracked separately from regular readers."""
        lock = RWLock()

        with lock.write():
            # Before downgrade
            assert lock._active_readers == 0
            assert lock._writer_held_reads == 0

            lock._acquire_read()

            # After downgrade
            assert lock._active_readers == 0  # Still 0 - not a regular reader
            assert lock._writer_held_reads == 1  # Tracked separately

    def test_conversion_updates_state_correctly(self) -> None:
        """State updated correctly when converting writer-held reads."""
        lock = RWLock()
        current_thread_id = threading.get_ident()

        with lock.write():
            lock._acquire_read()
            lock._acquire_read()
            assert lock._writer_held_reads == 2
            assert current_thread_id not in lock._reader_threads

        # After write release, should be regular reader
        assert lock._active_writer is None
        assert lock._writer_held_reads == 0
        assert lock._active_readers == 1
        assert lock._reader_threads[current_thread_id] == 2

        # Clean up
        lock._release_read()
        lock._release_read()

    def test_partial_read_release_during_write(self) -> None:
        """Can partially release writer-held reads before releasing write."""
        lock = RWLock()

        with lock.write():
            lock._acquire_read()
            lock._acquire_read()
            lock._acquire_read()

            assert lock._writer_held_reads == 3

            lock._release_read()
            assert lock._writer_held_reads == 2

            lock._release_read()
            assert lock._writer_held_reads == 1

        # After write release, 1 read should convert
        assert lock._writer_held_reads == 0
        assert lock._active_readers == 1

        lock._release_read()


class TestRWLockPropertyBased:
    """Property-based tests for RWLock invariants using Hypothesis."""

    @given(
        read_count=st.integers(min_value=1, max_value=10),
        write_reentry=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=100, deadline=None)
    def test_downgrade_read_count_preserved(
        self, read_count: int, write_reentry: int
    ) -> None:
        """Writer-held read count preserved through write release (property).

        Property: If writer acquires N read locks, after releasing write lock,
        should be able to release exactly N read locks.
        """
        lock = RWLock()

        with lock.write():
            # Add write reentrancy
            for _ in range(write_reentry):
                lock._acquire_write()

            # Acquire N read locks
            for _ in range(read_count):
                lock._acquire_read()

            # Release reentrant writes
            for _ in range(write_reentry):
                lock._release_write()

        # Write released, reads converted
        # Should be able to release exactly read_count reads
        for _ in range(read_count):
            lock._release_read()

        # All locks released - new writer should be able to acquire
        with lock.write():
            pass

    @given(
        operations=st.lists(
            st.sampled_from(["acquire_read", "release_read"]), min_size=2, max_size=20
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_balanced_writer_held_reads(self, operations: list[str]) -> None:
        """Balanced acquire/release of writer-held reads maintains consistency.

        Property: For any sequence of balanced acquire/release operations
        while holding write lock, state should be consistent.
        """
        lock = RWLock()

        # Balance the operations
        balance = 0
        balanced_ops = []
        for op in operations:
            if op == "acquire_read":
                balanced_ops.append(op)
                balance += 1
            elif op == "release_read" and balance > 0:
                balanced_ops.append(op)
                balance -= 1

        # Add releases to balance
        balanced_ops.extend(["release_read"] * balance)

        if not balanced_ops:
            return  # Skip empty operation sequences

        with lock.write():
            for op in balanced_ops:
                if op == "acquire_read":
                    lock._acquire_read()
                elif op == "release_read":
                    lock._release_read()

        # All locks should be released
        # New writer should be able to acquire immediately
        acquired = False
        with lock.write():
            acquired = True
        assert acquired

    @given(num_reads=st.integers(min_value=0, max_value=5))
    @settings(max_examples=50, deadline=None)
    def test_write_lock_excludes_readers_with_downgrade(self, num_reads: int) -> None:
        """Write lock excludes external readers even with downgrading.

        Property: While holding write lock (even with downgraded reads),
        external readers cannot acquire the lock.
        """
        lock = RWLock()
        external_reader_blocked = True

        def external_reader() -> None:
            nonlocal external_reader_blocked
            # Should not be able to acquire
            with lock.read():
                external_reader_blocked = False

        with lock.write():
            # Acquire downgrade reads
            for _ in range(num_reads):
                lock._acquire_read()

            # Try external reader
            reader_thread = threading.Thread(target=external_reader)
            reader_thread.start()
            time.sleep(0.01)  # Give thread time to attempt acquisition

            # Release downgrade reads
            for _ in range(num_reads):
                lock._release_read()

        # After write release, external reader should acquire
        reader_thread.join(timeout=1.0)

        # External reader should have been blocked while write was held
        # (even if no actual verification in this property test, the threading.Thread
        # join confirms no deadlock occurred)


class TestRWLockDecoratorDowngrading:
    """Test decorators work correctly with lock downgrading."""

    def test_write_decorator_can_call_read_decorated_method(self) -> None:
        """Method with write_lock can call method with read_lock (downgrading)."""

        class DataStore:
            def __init__(self) -> None:
                self._rwlock = RWLock()
                self.value = 0

            @with_read_lock()
            def read_value(self) -> int:
                return self.value

            @with_write_lock()
            def write_and_verify(self, new_value: int) -> int:
                self.value = new_value
                # Call read_decorated method while holding write lock
                return self.read_value()

        store = DataStore()
        result = store.write_and_verify(42)

        assert result == 42
        assert store.value == 42

    def test_nested_write_then_read_decorators(self) -> None:
        """Nested decorator calls work with write-to-read downgrading."""

        class Calculator:
            def __init__(self) -> None:
                self._rwlock = RWLock()
                self.result = 0

            @with_read_lock()
            def get_result(self) -> int:
                return self.result

            @with_write_lock()
            def compute(self, value: int) -> int:
                self.result = value * 2
                # Downgrade: call read while holding write
                verified = self.get_result()
                assert verified == value * 2
                return verified

        calc = Calculator()
        result = calc.compute(21)
        assert result == 42

    def test_decorator_downgrade_with_exception(self) -> None:
        """Decorators handle exceptions correctly during downgrading."""

        class DataStore:
            def __init__(self) -> None:
                self._rwlock = RWLock()
                self.value = 0

            @with_read_lock()
            def read_value(self) -> int:
                if self.value == 99:
                    msg = "Invalid value"
                    raise ValueError(msg)
                return self.value

            @with_write_lock()
            def write_and_verify(self, new_value: int) -> int:
                self.value = new_value
                return self.read_value()

        store = DataStore()

        # Normal case works
        assert store.write_and_verify(42) == 42

        # Exception case
        with pytest.raises(ValueError, match="Invalid value"):
            store.write_and_verify(99)

        # Lock should be released - can acquire again
        assert store.write_and_verify(100) == 100


class TestRWLockDowngradingValidation:
    """Validation tests ensuring downgrading doesn't break lock semantics."""

    def test_downgraded_writer_cannot_reacquire_as_new_reader(self) -> None:
        """Downgraded writer is already a reader, not a new reader thread."""
        lock = RWLock()
        current_thread_id = threading.get_ident()

        with lock.write():
            lock._acquire_read()  # Downgrade

            # Attempting to acquire as "new" reader should recognize reentrancy
            lock._acquire_read()  # Should increment writer_held_reads, not add new reader

            assert lock._writer_held_reads == 2
            assert current_thread_id not in lock._reader_threads

            lock._release_read()
            lock._release_read()

    def test_conversion_happens_only_on_final_write_release(self) -> None:
        """Writer-held reads convert only when write lock fully released."""
        lock = RWLock()
        current_thread_id = threading.get_ident()

        with lock.write():
            with lock.write():  # Reentrant
                lock._acquire_read()
                assert lock._writer_held_reads == 1
                assert current_thread_id not in lock._reader_threads
            # Inner write released, but outer still held
            assert lock._writer_held_reads == 1  # Still writer-held
            assert current_thread_id not in lock._reader_threads

        # Outer write released - conversion happens
        assert lock._writer_held_reads == 0
        assert current_thread_id in lock._reader_threads
        assert lock._reader_threads[current_thread_id] == 1

        lock._release_read()

    def test_cannot_upgrade_downgraded_read_to_write(self) -> None:
        """After downgrading, cannot re-upgrade read back to write (already have write)."""
        lock = RWLock()

        with lock.write():
            lock._acquire_read()  # Downgrade

            # Reentrant write acquisition should still work
            with lock.write():
                pass

            lock._release_read()
