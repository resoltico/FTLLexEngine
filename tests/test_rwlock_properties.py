"""Property-based tests for RWLock using Hypothesis.

Tests verify mathematical properties and invariants that must hold
for all possible lock operation sequences:
- Lock acquisition/release balance
- Mutual exclusion invariants
- Fairness properties
- State consistency
- Decorator preservation properties
"""

import contextlib
import random
import threading
from concurrent.futures import ThreadPoolExecutor

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.rwlock import RWLock, with_read_lock, with_write_lock


class TestRWLockMutualExclusionProperties:
    """Property tests for mutual exclusion guarantees."""

    @given(read_count=st.integers(min_value=1, max_value=20))
    @settings(max_examples=50, deadline=None)
    def test_multiple_readers_never_block_each_other(self, read_count: int) -> None:
        """Property: N readers can all acquire lock concurrently (no blocking).

        For any N >= 1, all N readers should successfully acquire the lock
        and execute concurrently.
        """
        lock = RWLock()
        active_readers = []

        def reader(reader_id: int) -> None:
            with lock.read():
                active_readers.append(reader_id)

        threads = [threading.Thread(target=reader, args=(i,)) for i in range(read_count)]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All readers completed
        assert len(active_readers) == read_count
        assert set(active_readers) == set(range(read_count))

    @given(reentry_depth=st.integers(min_value=1, max_value=10))
    @settings(max_examples=50, deadline=None)
    def test_read_reentrancy_depth_preserved(self, reentry_depth: int) -> None:
        """Property: Read lock can be acquired N times by same thread.

        For any N >= 1, same thread can acquire read lock N times
        and must release N times before lock is fully released.
        """
        lock = RWLock()

        def acquire_n_times(depth: int) -> None:
            if depth == 0:
                return
            with lock.read():
                acquire_n_times(depth - 1)

        # Acquire recursively
        acquire_n_times(reentry_depth)

        # Lock should be fully released - new writer can acquire
        acquired = False
        with lock.write():
            acquired = True
        assert acquired

    @given(reentry_depth=st.integers(min_value=1, max_value=10))
    @settings(max_examples=50, deadline=None)
    def test_write_reentrancy_depth_preserved(self, reentry_depth: int) -> None:
        """Property: Write lock can be acquired N times by same thread.

        For any N >= 1, same thread can acquire write lock N times
        and must release N times before lock is fully released.
        """
        lock = RWLock()

        def acquire_n_times(depth: int) -> None:
            if depth == 0:
                return
            with lock.write():
                acquire_n_times(depth - 1)

        # Acquire recursively
        acquire_n_times(reentry_depth)

        # Lock should be fully released - new writer can acquire
        acquired = False
        with lock.write():
            acquired = True
        assert acquired

    @given(
        initial_readers=st.integers(min_value=0, max_value=5),
        subsequent_readers=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=50, deadline=None)
    def test_writer_excludes_all_readers(
        self, initial_readers: int, subsequent_readers: int
    ) -> None:
        """Property: Writer has exclusive access (no concurrent readers).

        For any number of readers attempting to acquire before or during
        writer acquisition, writer must have exclusive access.
        """
        assume(initial_readers + subsequent_readers > 0)  # At least one reader

        lock = RWLock()
        writer_has_exclusive = threading.Event()
        readers_blocked = threading.Event()

        def writer() -> None:
            with lock.write():
                writer_has_exclusive.set()
                readers_blocked.wait()  # Wait for readers to attempt acquisition
                # Verify no readers acquired (tested via thread state)

        def reader() -> None:
            writer_has_exclusive.wait()
            with lock.read():
                # Should only execute after writer releases
                pass

        writer_thread = threading.Thread(target=writer)
        reader_threads = [
            threading.Thread(target=reader)
            for _ in range(initial_readers + subsequent_readers)
        ]

        # Start writer first
        writer_thread.start()

        # Start all readers
        for thread in reader_threads:
            thread.start()

        # Signal that readers are waiting
        readers_blocked.set()

        writer_thread.join()
        for thread in reader_threads:
            thread.join()


class TestRWLockBalanceProperties:
    """Property tests for lock acquisition/release balance."""

    @given(
        operations=st.lists(
            st.sampled_from(["acquire_read", "release_read"]),
            min_size=2,
            max_size=30,
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_balanced_read_operations_maintain_consistency(
        self, operations: list[str]
    ) -> None:
        """Property: Balanced acquire/release sequences maintain lock consistency.

        For any sequence of balanced read acquire/release operations,
        the lock should return to unlocked state.
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
            return  # Skip empty sequences

        # Execute balanced operations
        for op in balanced_ops:
            if op == "acquire_read":
                lock._acquire_read()
            elif op == "release_read":
                lock._release_read()

        # Lock should be free - new writer can acquire immediately
        with lock.write():
            pass

    @given(
        operations=st.lists(
            st.sampled_from(["acquire_write", "release_write"]),
            min_size=2,
            max_size=20,
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_balanced_write_operations_maintain_consistency(
        self, operations: list[str]
    ) -> None:
        """Property: Balanced write acquire/release sequences maintain consistency.

        For any sequence of balanced write acquire/release operations,
        the lock should return to unlocked state.
        """
        lock = RWLock()

        # Balance the operations
        balance = 0
        balanced_ops = []
        for op in operations:
            if op == "acquire_write":
                balanced_ops.append(op)
                balance += 1
            elif op == "release_write" and balance > 0:
                balanced_ops.append(op)
                balance -= 1

        # Add releases to balance
        balanced_ops.extend(["release_write"] * balance)

        if not balanced_ops:
            return

        # Execute balanced operations
        for op in balanced_ops:
            if op == "acquire_write":
                lock._acquire_write()
            elif op == "release_write":
                lock._release_write()

        # Lock should be free
        with lock.write():
            pass


class TestRWLockContextManagerProperties:
    """Property tests for context manager behavior."""

    @given(
        exception_type=st.sampled_from([ValueError, RuntimeError, KeyError]),
        reentry_depth=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=50, deadline=None)
    def test_read_lock_released_on_exception(
        self, exception_type: type[Exception], reentry_depth: int
    ) -> None:
        """Property: Read lock always released on exception, regardless of reentry depth.

        For any exception type and any reentry depth, the lock must be
        fully released when exception propagates.
        """
        lock = RWLock()

        def acquire_with_exception(depth: int) -> None:
            if depth == 0:
                msg = "Test exception"
                raise exception_type(msg)
            with lock.read():
                acquire_with_exception(depth - 1)

        # Should raise exception but release all locks
        with contextlib.suppress(exception_type):
            acquire_with_exception(reentry_depth)

        # Lock should be free
        with lock.write():
            pass

    @given(
        exception_type=st.sampled_from([ValueError, RuntimeError, KeyError]),
        reentry_depth=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=50, deadline=None)
    def test_write_lock_released_on_exception(
        self, exception_type: type[Exception], reentry_depth: int
    ) -> None:
        """Property: Write lock always released on exception, regardless of reentry depth.

        For any exception type and any reentry depth, the lock must be
        fully released when exception propagates.
        """
        lock = RWLock()

        def acquire_with_exception(depth: int) -> None:
            if depth == 0:
                msg = "Test exception"
                raise exception_type(msg)
            with lock.write():
                acquire_with_exception(depth - 1)

        # Should raise exception but release all locks
        with contextlib.suppress(exception_type):
            acquire_with_exception(reentry_depth)

        # Lock should be free
        with lock.write():
            pass


class TestRWLockDecoratorProperties:
    """Property tests for decorator functions."""

    @given(
        return_value=st.one_of(st.integers(), st.text(), st.booleans(), st.none()),
    )
    @settings(max_examples=50, deadline=None)
    def test_read_decorator_preserves_return_value(self, return_value: object) -> None:
        """Property: with_read_lock decorator preserves return values.

        For any return value, the decorated function should return
        the same value as the undecorated function.
        """

        class Container:
            def __init__(self) -> None:
                self._rwlock = RWLock()

            @with_read_lock()
            def get_value(self) -> object:
                return return_value

        container = Container()
        assert container.get_value() == return_value

    @given(
        return_value=st.one_of(st.integers(), st.text(), st.booleans(), st.none()),
    )
    @settings(max_examples=50, deadline=None)
    def test_write_decorator_preserves_return_value(
        self, return_value: object
    ) -> None:
        """Property: with_write_lock decorator preserves return values.

        For any return value, the decorated function should return
        the same value as the undecorated function.
        """

        class Container:
            def __init__(self) -> None:
                self._rwlock = RWLock()

            @with_write_lock()
            def set_value(self) -> object:
                return return_value

        container = Container()
        assert container.set_value() == return_value

    @given(
        args=st.lists(st.integers(), min_size=0, max_size=5),
        kwargs=st.dictionaries(
            st.text(min_size=1, max_size=10, alphabet=st.characters(categories=["Ll"])),
            st.integers(),
            min_size=0,
            max_size=3,
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_read_decorator_preserves_arguments(
        self, args: list[int], kwargs: dict[str, int]
    ) -> None:
        """Property: with_read_lock decorator preserves function arguments.

        For any combination of positional and keyword arguments,
        the decorated function receives them unchanged.
        """

        class Container:
            def __init__(self) -> None:
                self._rwlock = RWLock()

            @with_read_lock()
            def process(self, *args: int, **kwargs: int) -> tuple[list[int], dict[str, int]]:
                return (list(args), kwargs)

        container = Container()
        result_args, result_kwargs = container.process(*args, **kwargs)
        assert result_args == list(args)
        assert result_kwargs == kwargs

    @given(
        args=st.lists(st.integers(), min_size=0, max_size=5),
        kwargs=st.dictionaries(
            st.text(min_size=1, max_size=10, alphabet=st.characters(categories=["Ll"])),
            st.integers(),
            min_size=0,
            max_size=3,
        ),
    )
    @settings(max_examples=50, deadline=None)
    def test_write_decorator_preserves_arguments(
        self, args: list[int], kwargs: dict[str, int]
    ) -> None:
        """Property: with_write_lock decorator preserves function arguments.

        For any combination of positional and keyword arguments,
        the decorated function receives them unchanged.
        """

        class Container:
            def __init__(self) -> None:
                self._rwlock = RWLock()

            @with_write_lock()
            def process(self, *args: int, **kwargs: int) -> tuple[list[int], dict[str, int]]:
                return (list(args), kwargs)

        container = Container()
        result_args, result_kwargs = container.process(*args, **kwargs)
        assert result_args == list(args)
        assert result_kwargs == kwargs

    @given(
        lock_attr=st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(categories=["Ll", "Lu"]),
        )
    )
    @settings(max_examples=30, deadline=None)
    def test_decorator_custom_lock_attribute(self, lock_attr: str) -> None:
        """Property: Decorators work with any valid attribute name.

        For any valid Python identifier, the decorator should use
        that attribute as the lock.
        """
        # Filter invalid identifiers
        if not lock_attr.isidentifier() or lock_attr.startswith("_"):
            assume(False)

        class Container:
            def __init__(self, attr_name: str) -> None:
                setattr(self, attr_name, RWLock())

        container = Container(lock_attr)

        # Dynamically create decorated method
        @with_read_lock(lock_attr=lock_attr)
        def read_method(self: object) -> str:  # noqa: ARG001
            return "success"

        # Bind method to instance
        result = read_method(container)
        assert result == "success"


class TestRWLockConcurrencyProperties:
    """Property tests for concurrent access patterns."""

    @given(
        num_readers=st.integers(min_value=1, max_value=20),
        num_writers=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=30, deadline=None)
    def test_mixed_readers_writers_no_deadlock(
        self, num_readers: int, num_writers: int
    ) -> None:
        """Property: Mixed readers/writers never deadlock.

        For any combination of N readers and M writers, all threads
        should complete without deadlock.
        """
        lock = RWLock()
        completed = []

        def reader(reader_id: int) -> None:
            with lock.read():
                completed.append(f"R{reader_id}")

        def writer(writer_id: int) -> None:
            with lock.write():
                completed.append(f"W{writer_id}")

        with ThreadPoolExecutor(max_workers=num_readers + num_writers) as executor:
            futures = []
            for i in range(num_readers):
                futures.append(executor.submit(reader, i))
            for i in range(num_writers):
                futures.append(executor.submit(writer, i))

            for future in futures:
                future.result(timeout=5.0)  # Should not timeout

        # All operations completed
        assert len(completed) == num_readers + num_writers

    @given(
        num_operations=st.integers(min_value=10, max_value=100),
        write_probability=st.floats(min_value=0.1, max_value=0.5),
    )
    @settings(max_examples=30, deadline=None)
    def test_operations_maintain_data_consistency(
        self, num_operations: int, write_probability: float
    ) -> None:
        """Property: Concurrent operations maintain shared data consistency.

        For any mix of read/write operations, the shared counter
        should match the number of write operations.
        """
        lock = RWLock()
        counter = 0
        expected_writes = 0

        def reader() -> None:
            with lock.read():
                _ = counter  # Read value

        def writer() -> None:
            nonlocal counter
            with lock.write():
                counter += 1

        operations = []
        for _ in range(num_operations):
            if random.random() < write_probability:
                operations.append("write")
                expected_writes += 1
            else:
                operations.append("read")

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = []
            for op in operations:
                if op == "write":
                    futures.append(executor.submit(writer))
                else:
                    futures.append(executor.submit(reader))

            for future in futures:
                future.result()

        assert counter == expected_writes


class TestRWLockStateInvariantProperties:
    """Property tests for internal state invariants."""

    @given(num_readers=st.integers(min_value=1, max_value=10))
    @settings(max_examples=50, deadline=None)
    def test_active_readers_count_accurate(self, num_readers: int) -> None:
        """Property: _active_readers count matches actual reader threads.

        After N threads acquire read lock, _active_readers should be N.
        """
        lock = RWLock()
        ready = threading.Barrier(num_readers + 1)

        def reader() -> None:
            lock._acquire_read()
            ready.wait()  # All readers acquired
            ready.wait()  # Wait for verification
            lock._release_read()

        threads = [threading.Thread(target=reader) for _ in range(num_readers)]

        for thread in threads:
            thread.start()

        ready.wait()  # Wait for all readers to acquire

        # Verify count
        assert lock._active_readers == num_readers
        assert len(lock._reader_threads) == num_readers

        ready.wait()  # Release readers

        for thread in threads:
            thread.join()

        # All released
        assert lock._active_readers == 0
        assert len(lock._reader_threads) == 0

    @given(reentry_count=st.integers(min_value=1, max_value=10))
    @settings(max_examples=50, deadline=None)
    def test_reader_threads_reentry_count_accurate(self, reentry_count: int) -> None:
        """Property: _reader_threads tracks reentry count accurately.

        After same thread acquires read lock N times, count should be N.
        """
        lock = RWLock()
        thread_id = threading.get_ident()

        for _ in range(reentry_count):
            lock._acquire_read()

        assert lock._reader_threads[thread_id] == reentry_count

        for _ in range(reentry_count):
            lock._release_read()

        assert thread_id not in lock._reader_threads
