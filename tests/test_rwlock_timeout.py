"""Tests for RWLock timeout support.

Tests verify:
- Read lock acquisition respects timeout
- Write lock acquisition respects timeout
- Timeout of zero is non-blocking attempt
- Negative timeout raises ValueError
- None timeout preserves indefinite blocking
- Reentrant read acquisition ignores timeout (no waiting)
- TimeoutError does not corrupt internal state (_waiting_writers counter)
- Property-based timeout invariants
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.rwlock import RWLock


class TestReadTimeout:
    """Test read lock timeout behavior."""

    def test_read_timeout_when_writer_active(self) -> None:
        """Read lock times out when writer holds lock."""
        lock = RWLock()
        writer_ready = threading.Event()
        writer_release = threading.Event()

        def hold_write() -> None:
            with lock.write():
                writer_ready.set()
                writer_release.wait()

        t = threading.Thread(target=hold_write)
        t.start()
        writer_ready.wait()

        with pytest.raises(TimeoutError, match="read lock"), lock.read(timeout=0.05):
            pass  # pragma: no cover

        writer_release.set()
        t.join()

    def test_read_timeout_zero_nonblocking(self) -> None:
        """Timeout of 0.0 is a non-blocking attempt."""
        lock = RWLock()
        writer_ready = threading.Event()
        writer_release = threading.Event()

        def hold_write() -> None:
            with lock.write():
                writer_ready.set()
                writer_release.wait()

        t = threading.Thread(target=hold_write)
        t.start()
        writer_ready.wait()

        with pytest.raises(TimeoutError), lock.read(timeout=0.0):
            pass  # pragma: no cover

        writer_release.set()
        t.join()

    def test_read_timeout_none_waits_indefinitely(self) -> None:
        """None timeout (default) waits indefinitely."""
        lock = RWLock()
        writer_ready = threading.Event()
        acquired = threading.Event()

        def hold_write_briefly() -> None:
            with lock.write():
                writer_ready.set()
                time.sleep(0.05)

        t = threading.Thread(target=hold_write_briefly)
        t.start()
        writer_ready.wait()

        with lock.read(timeout=None):
            acquired.set()

        t.join()
        assert acquired.is_set()

    def test_read_negative_timeout_raises_valueerror(self) -> None:
        """Negative timeout raises ValueError before any blocking."""
        lock = RWLock()

        with pytest.raises(ValueError, match="non-negative"), lock.read(timeout=-1.0):
            pass  # pragma: no cover

    def test_read_timeout_reentrant_ignores_timeout(self) -> None:
        """Reentrant read acquisition does not wait, timeout irrelevant."""
        lock = RWLock()

        with lock.read(), lock.read(timeout=0.0):
            pass  # Should not raise

    def test_read_timeout_writer_waiting_blocks_reader(self) -> None:
        """Read times out when writers are waiting (writer preference)."""
        lock = RWLock()
        read_held = threading.Event()
        writer_waiting = threading.Event()
        read_release = threading.Event()

        def hold_read() -> None:
            with lock.read():
                read_held.set()
                read_release.wait()

        def wait_write() -> None:
            read_held.wait()
            writer_waiting.set()
            with lock.write():
                pass

        t_reader = threading.Thread(target=hold_read)
        t_writer = threading.Thread(target=wait_write)
        t_reader.start()
        t_writer.start()

        read_held.wait()
        writer_waiting.wait()
        time.sleep(0.02)  # Let writer register as waiting

        with pytest.raises(TimeoutError), lock.read(timeout=0.05):
            pass  # pragma: no cover

        read_release.set()
        t_reader.join()
        t_writer.join()


class TestWriteTimeout:
    """Test write lock timeout behavior."""

    def test_write_timeout_when_readers_active(self) -> None:
        """Write lock times out when readers hold lock."""
        lock = RWLock()
        reader_ready = threading.Event()
        reader_release = threading.Event()

        def hold_read() -> None:
            with lock.read():
                reader_ready.set()
                reader_release.wait()

        t = threading.Thread(target=hold_read)
        t.start()
        reader_ready.wait()

        with pytest.raises(TimeoutError, match="write lock"), lock.write(timeout=0.05):
            pass  # pragma: no cover

        reader_release.set()
        t.join()

    def test_write_timeout_when_writer_active(self) -> None:
        """Write lock times out when another writer holds lock."""
        lock = RWLock()
        writer_ready = threading.Event()
        writer_release = threading.Event()

        def hold_write() -> None:
            with lock.write():
                writer_ready.set()
                writer_release.wait()

        t = threading.Thread(target=hold_write)
        t.start()
        writer_ready.wait()

        with pytest.raises(TimeoutError, match="write lock"), lock.write(timeout=0.05):
            pass  # pragma: no cover

        writer_release.set()
        t.join()

    def test_write_timeout_zero_nonblocking(self) -> None:
        """Timeout of 0.0 is a non-blocking attempt."""
        lock = RWLock()
        reader_ready = threading.Event()
        reader_release = threading.Event()

        def hold_read() -> None:
            with lock.read():
                reader_ready.set()
                reader_release.wait()

        t = threading.Thread(target=hold_read)
        t.start()
        reader_ready.wait()

        with pytest.raises(TimeoutError), lock.write(timeout=0.0):
            pass  # pragma: no cover

        reader_release.set()
        t.join()

    def test_write_negative_timeout_raises_valueerror(self) -> None:
        """Negative timeout raises ValueError before any blocking."""
        lock = RWLock()

        with pytest.raises(ValueError, match="non-negative"), lock.write(timeout=-1.0):
            pass  # pragma: no cover

    def test_write_timeout_none_waits_indefinitely(self) -> None:
        """None timeout (default) waits indefinitely."""
        lock = RWLock()
        reader_ready = threading.Event()
        acquired = threading.Event()

        def hold_read_briefly() -> None:
            with lock.read():
                reader_ready.set()
                time.sleep(0.05)

        t = threading.Thread(target=hold_read_briefly)
        t.start()
        reader_ready.wait()

        with lock.write(timeout=None):
            acquired.set()

        t.join()
        assert acquired.is_set()


class TestTimeoutStateConsistency:
    """Test that timeout does not corrupt internal lock state."""

    def test_write_timeout_decrements_waiting_writers(self) -> None:
        """Write timeout correctly decrements _waiting_writers counter.

        If _waiting_writers is not decremented on timeout, all future readers
        deadlock because they wait for waiting_writers == 0.
        """
        lock = RWLock()
        reader_ready = threading.Event()
        reader_release = threading.Event()

        def hold_read() -> None:
            with lock.read():
                reader_ready.set()
                reader_release.wait()

        t = threading.Thread(target=hold_read)
        t.start()
        reader_ready.wait()

        # Write timeout should not permanently inflate _waiting_writers
        with pytest.raises(TimeoutError), lock.write(timeout=0.05):
            pass  # pragma: no cover

        reader_release.set()
        t.join()

        # Verify a reader can still acquire after write timeout
        with lock.read():
            pass  # Should not deadlock

    def test_multiple_write_timeouts_preserve_state(self) -> None:
        """Multiple write timeouts do not accumulate _waiting_writers."""
        lock = RWLock()
        writer_ready = threading.Event()
        writer_release = threading.Event()

        def hold_write() -> None:
            with lock.write():
                writer_ready.set()
                writer_release.wait()

        t = threading.Thread(target=hold_write)
        t.start()
        writer_ready.wait()

        for _ in range(5):
            with pytest.raises(TimeoutError), lock.write(timeout=0.01):
                pass  # pragma: no cover

        writer_release.set()
        t.join()

        # Lock should be fully operational
        with lock.read():
            pass
        with lock.write():
            pass

    def test_read_timeout_does_not_affect_reader_tracking(self) -> None:
        """Read timeout does not leave ghost entries in _reader_threads."""
        lock = RWLock()
        writer_ready = threading.Event()
        writer_release = threading.Event()

        def hold_write() -> None:
            with lock.write():
                writer_ready.set()
                writer_release.wait()

        t = threading.Thread(target=hold_write)
        t.start()
        writer_ready.wait()

        with pytest.raises(TimeoutError), lock.read(timeout=0.05):
            pass  # pragma: no cover

        writer_release.set()
        t.join()

        # Verify lock state is clean
        with lock.write():
            pass

    def test_timeout_then_successful_acquire(self) -> None:
        """Lock can be acquired normally after a timeout."""
        lock = RWLock()
        blocker_ready = threading.Event()
        blocker_release = threading.Event()

        def hold_write() -> None:
            with lock.write():
                blocker_ready.set()
                blocker_release.wait()

        t = threading.Thread(target=hold_write)
        t.start()
        blocker_ready.wait()

        with pytest.raises(TimeoutError), lock.write(timeout=0.05):
            pass  # pragma: no cover

        blocker_release.set()
        t.join()

        # Both read and write should work normally
        acquired = False
        with lock.write():
            acquired = True
        assert acquired


class TestTimeoutProperties:
    """Property-based tests for timeout behavior."""

    @given(timeout_val=st.floats(min_value=0.0, max_value=0.001))
    @settings(max_examples=20, deadline=None)
    def test_write_timeout_never_corrupts_state(self, timeout_val: float) -> None:
        """Property: write timeout always leaves lock in consistent state.

        For any non-negative timeout, a timed-out write must leave the lock
        fully operational for subsequent acquisitions.
        """
        event(f"timeout={timeout_val}")
        lock = RWLock()
        blocker_ready = threading.Event()
        blocker_release = threading.Event()

        def hold_write() -> None:
            with lock.write():
                blocker_ready.set()
                blocker_release.wait()

        t = threading.Thread(target=hold_write)
        t.start()
        blocker_ready.wait()

        with pytest.raises(TimeoutError), lock.write(timeout=timeout_val):
            pass  # pragma: no cover

        blocker_release.set()
        t.join()

        # Lock must be usable
        with lock.read():
            pass
        with lock.write():
            pass

    @given(timeout_val=st.floats(min_value=-100.0, max_value=-0.001))
    @settings(max_examples=20, deadline=None)
    def test_negative_timeout_always_raises_valueerror(self, timeout_val: float) -> None:
        """Property: any negative timeout raises ValueError immediately."""
        event(f"timeout={timeout_val}")
        lock = RWLock()

        with pytest.raises(ValueError, match="non-negative"), lock.read(timeout=timeout_val):
            pass  # pragma: no cover

        with pytest.raises(ValueError, match="non-negative"), lock.write(timeout=timeout_val):
            pass  # pragma: no cover

    @given(n_timeouts=st.integers(min_value=1, max_value=10))
    @settings(max_examples=10, deadline=None)
    def test_n_write_timeouts_leave_waiting_writers_zero(self, n_timeouts: int) -> None:
        """Property: N write timeouts leave _waiting_writers at zero.

        Regardless of how many concurrent write timeouts occur, the counter
        must return to zero so readers are not permanently blocked.
        """
        event(f"n_timeouts={n_timeouts}")
        lock = RWLock()
        blocker_ready = threading.Event()
        blocker_release = threading.Event()

        def hold_write() -> None:
            with lock.write():
                blocker_ready.set()
                blocker_release.wait()

        t = threading.Thread(target=hold_write)
        t.start()
        blocker_ready.wait()

        # Fire N timeouts from separate threads
        results: list[bool] = []

        def attempt_write() -> None:
            try:
                with lock.write(timeout=0.01):
                    pass  # pragma: no cover
            except TimeoutError:
                results.append(True)

        with ThreadPoolExecutor(max_workers=n_timeouts) as pool:
            futures = [pool.submit(attempt_write) for _ in range(n_timeouts)]
            for f in futures:
                f.result()

        assert len(results) == n_timeouts

        blocker_release.set()
        t.join()

        # All timeouts resolved; readers must work
        with lock.read():
            pass
