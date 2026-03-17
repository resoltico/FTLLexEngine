"""Tests for runtime/interpreter_pool.py (InterpreterPool).

Covers:
- Construction: min_size/max_size validation, pre-warming
- acquire(): returns _PooledInterpreter context manager
- Context manager protocol: acquire/release via 'with' statement
- call(): delegates to subinterpreter, returns result
- ExecutionFailed propagates without marking interpreter unhealthy
- InterpreterError marks interpreter unhealthy; release() replaces it
- release(healthy=False): closes unhealthy interpreter, replaces if below min_size
- _PooledInterpreter.__exit__: no-op when pool weakref is cleared (GC scenario)
- release(): returns healthy interpreters to pool
- close(): destroys idle interpreters, marks pool closed
- acquire() after close() raises RuntimeError
- acquire_timeout=None: blocks indefinitely, wakes on release
- acquire_timeout=None: raises RuntimeError if pool closed while blocked
- InterpreterPool as context manager (__enter__/__exit__)
- acquire_timeout: TimeoutError when pool exhausted
- Thread safety: concurrent acquire/release

Python 3.14+.
"""

from __future__ import annotations

import concurrent.futures
import gc
import threading
import time
import unittest.mock

import pytest

from ftllexengine.runtime.interpreter_pool import InterpreterPool

# ---------------------------------------------------------------------------
# Module-level helpers (must be top-level for subinterpreter call())
# ---------------------------------------------------------------------------


def _fn_return_42() -> int:
    """Return a fixed integer for basic call verification."""
    return 42


def _fn_return_arg(x: int) -> int:
    """Return the argument unchanged."""
    return x


def _fn_raise_value_error() -> None:
    """Raise ValueError inside the subinterpreter."""
    msg = "error inside subinterpreter"
    raise ValueError(msg)


def _fn_slow(delay: float) -> str:
    """Sleep for delay seconds and return 'done'."""
    time.sleep(delay)
    return "done"


# ===========================================================================
# Construction validation
# ===========================================================================


class TestInterpreterPoolConstruction:
    """InterpreterPool validates configuration at construction time."""

    def test_default_construction(self) -> None:
        """Default construction creates a pool with min_size=2, max_size=8."""
        pool = InterpreterPool()
        assert pool.min_size == 2
        assert pool.max_size == 8
        pool.close()

    def test_custom_sizes(self) -> None:
        """Custom min/max sizes are stored correctly."""
        pool = InterpreterPool(min_size=1, max_size=4)
        assert pool.min_size == 1
        assert pool.max_size == 4
        pool.close()

    def test_min_size_zero_raises(self) -> None:
        """min_size < 1 raises ValueError."""
        with pytest.raises(ValueError, match="min_size"):
            InterpreterPool(min_size=0)

    def test_max_size_less_than_min_raises(self) -> None:
        """max_size < min_size raises ValueError."""
        with pytest.raises(ValueError, match="max_size"):
            InterpreterPool(min_size=3, max_size=2)

    def test_equal_min_max_allowed(self) -> None:
        """min_size == max_size is valid (fixed-size pool)."""
        pool = InterpreterPool(min_size=2, max_size=2)
        assert pool.min_size == 2
        assert pool.max_size == 2
        pool.close()


# ===========================================================================
# Basic acquire/release/call
# ===========================================================================


class TestInterpreterPoolAcquireRelease:
    """acquire() returns a usable _PooledInterpreter and release() returns it."""

    def test_acquire_returns_context_manager(self) -> None:
        """acquire() returns an object usable as a context manager."""
        pool = InterpreterPool(min_size=1, max_size=2)
        try:
            pooled = pool.acquire()
            assert hasattr(pooled, "__enter__")
            assert hasattr(pooled, "__exit__")
            pool.release(pooled)
        finally:
            pool.close()

    def test_call_returns_value(self) -> None:
        """call() executes the function in a subinterpreter and returns the result."""
        pool = InterpreterPool(min_size=1, max_size=2)
        try:
            with pool.acquire() as interp:
                result = interp.call(_fn_return_42)
            assert result == 42
        finally:
            pool.close()

    def test_call_with_argument(self) -> None:
        """call() passes arguments to the function correctly."""
        pool = InterpreterPool(min_size=1, max_size=2)
        try:
            with pool.acquire() as interp:
                result = interp.call(_fn_return_arg, 99)
            assert result == 99
        finally:
            pool.close()

    def test_context_manager_auto_releases(self) -> None:
        """'with pool.acquire()' releases the interpreter on exit."""
        pool = InterpreterPool(min_size=1, max_size=1)
        try:
            with pool.acquire():
                pass  # Interpreter checked out
            # After the with block, interpreter must be returned to pool
            # so a second acquire does not block
            with pool.acquire() as interp:
                result = interp.call(_fn_return_42)
            assert result == 42
        finally:
            pool.close()

    def test_multiple_sequential_acquires(self) -> None:
        """Multiple sequential acquire/release cycles work correctly."""
        pool = InterpreterPool(min_size=1, max_size=2)
        try:
            results = []
            for i in range(5):
                with pool.acquire() as interp:
                    results.append(interp.call(_fn_return_arg, i))
            assert results == list(range(5))
        finally:
            pool.close()


# ===========================================================================
# ExecutionFailed handling
# ===========================================================================


class TestInterpreterPoolExecutionFailed:
    """ExecutionFailed from user code does not corrupt the interpreter."""

    def test_execution_failed_propagates(self) -> None:
        """ExecutionFailed raised inside call() propagates to the caller."""
        pool = InterpreterPool(min_size=1, max_size=2)
        try:
            with pytest.raises(concurrent.interpreters.ExecutionFailed), pool.acquire() as interp:
                interp.call(_fn_raise_value_error)
        finally:
            pool.close()

    def test_interpreter_reusable_after_execution_failed(self) -> None:
        """After ExecutionFailed, the interpreter is returned to the pool and reusable."""
        pool = InterpreterPool(min_size=1, max_size=1)
        try:
            # First call: raise inside interpreter
            with pytest.raises(concurrent.interpreters.ExecutionFailed), pool.acquire() as interp:
                interp.call(_fn_raise_value_error)

            # Second call: pool should still have one interpreter (reused)
            with pool.acquire() as interp:
                result = interp.call(_fn_return_42)
            assert result == 42
        finally:
            pool.close()


# ===========================================================================
# Pool shutdown
# ===========================================================================


class TestInterpreterPoolClose:
    """close() marks the pool closed; acquire() raises RuntimeError after close."""

    def test_acquire_after_close_raises(self) -> None:
        """acquire() raises RuntimeError after close()."""
        pool = InterpreterPool(min_size=1, max_size=2)
        pool.close()
        with pytest.raises(RuntimeError, match="closed"):
            pool.acquire()

    def test_close_is_idempotent(self) -> None:
        """Calling close() multiple times does not raise."""
        pool = InterpreterPool(min_size=1, max_size=2)
        pool.close()
        pool.close()  # Should not raise

    def test_context_manager_closes_on_exit(self) -> None:
        """Using InterpreterPool as context manager closes it on __exit__."""
        with InterpreterPool(min_size=1, max_size=2) as pool:
            with pool.acquire() as interp:
                result = interp.call(_fn_return_42)
            assert result == 42

        # Pool is now closed
        with pytest.raises(RuntimeError, match="closed"):
            pool.acquire()


# ===========================================================================
# acquire_timeout
# ===========================================================================


class TestInterpreterPoolTimeout:
    """acquire_timeout causes TimeoutError when pool is exhausted."""

    def test_timeout_when_pool_exhausted(self) -> None:
        """acquire() raises TimeoutError when max_size interpreters are checked out."""
        pool = InterpreterPool(min_size=1, max_size=1, acquire_timeout=0.1)
        try:
            # Acquire the only interpreter and hold it
            outer = pool.acquire()
            try:
                start = time.monotonic()
                with pytest.raises(TimeoutError, match="timed out"):
                    pool.acquire()
                elapsed = time.monotonic() - start
                # Should have waited approximately the timeout duration
                assert elapsed >= 0.05  # at least half the timeout
            finally:
                pool.release(outer)
        finally:
            pool.close()

    def test_no_timeout_when_pool_available(self) -> None:
        """acquire() succeeds immediately when a slot is available."""
        pool = InterpreterPool(min_size=2, max_size=4, acquire_timeout=1.0)
        try:
            with pool.acquire() as interp:
                result = interp.call(_fn_return_42)
            assert result == 42
        finally:
            pool.close()

    def test_none_timeout_blocks_indefinitely(self) -> None:
        """acquire_timeout=None means acquire() blocks without a timeout (no TimeoutError)."""
        pool = InterpreterPool(min_size=1, max_size=2, acquire_timeout=None)
        try:
            with pool.acquire() as interp:
                assert interp.call(_fn_return_42) == 42
        finally:
            pool.close()


# ===========================================================================
# Thread safety
# ===========================================================================


class TestInterpreterPoolThreadSafety:
    """Pool acquire/release are safe under concurrent access."""

    def test_concurrent_acquires_within_max_size(self) -> None:
        """Multiple threads can each acquire a separate interpreter concurrently."""
        max_size = 4
        pool = InterpreterPool(min_size=2, max_size=max_size, acquire_timeout=5.0)
        results: list[int] = []
        errors: list[Exception] = []
        lock = threading.Lock()

        def worker(n: int) -> None:
            try:
                with pool.acquire() as interp:
                    val = interp.call(_fn_return_arg, n)
                    with lock:
                        results.append(val)  # type: ignore[arg-type]
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(max_size)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert not errors, f"Thread errors: {errors}"
        assert sorted(results) == list(range(max_size))
        pool.close()

    def test_acquire_blocks_until_release_from_other_thread(self) -> None:
        """acquire() in one thread unblocks when another thread releases."""
        pool = InterpreterPool(min_size=1, max_size=1, acquire_timeout=5.0)
        unblock_event = threading.Event()
        second_result: list[object] = []

        def holder() -> None:
            with pool.acquire() as interp:
                interp.call(_fn_return_42)
                # Signal that we're about to release
                unblock_event.set()
                time.sleep(0.05)  # Hold briefly so waiter has time to block

        def waiter() -> None:
            unblock_event.wait(timeout=5.0)
            with pool.acquire() as interp:
                second_result.append(interp.call(_fn_return_42))

        t1 = threading.Thread(target=holder)
        t2 = threading.Thread(target=waiter)
        t1.start()
        t2.start()
        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        assert second_result == [42]
        pool.close()

    def test_concurrent_futures_integration(self) -> None:
        """InterpreterPool integrates with concurrent.futures.ThreadPoolExecutor."""
        pool = InterpreterPool(min_size=2, max_size=4, acquire_timeout=5.0)
        try:
            def task(n: int) -> int:
                with pool.acquire() as interp:
                    return interp.call(_fn_return_arg, n)  # type: ignore[return-value]

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(task, i) for i in range(8)]
                results = sorted(f.result() for f in concurrent.futures.as_completed(futures))

            assert results == list(range(8))
        finally:
            pool.close()


# ===========================================================================
# InterpreterError handling (interpreter marked unhealthy)
# ===========================================================================


class TestInterpreterPoolInterpreterError:
    """InterpreterError from the subinterpreter marks the interpreter unhealthy."""

    def test_interpreter_error_marks_unhealthy(self) -> None:
        """InterpreterError inside call() sets _healthy=False on the pooled interpreter."""
        pool = InterpreterPool(min_size=1, max_size=2)
        try:
            pooled = pool.acquire()
            # Replace the underlying interpreter with a mock that raises InterpreterError.
            fake = unittest.mock.MagicMock()
            fake.call.side_effect = concurrent.interpreters.InterpreterError("corrupted")
            pooled._interpreter = fake

            with pytest.raises(concurrent.interpreters.InterpreterError):
                pooled.call(_fn_return_42)

            # _healthy must be False — pool will replace this interpreter on release.
            assert pooled._healthy is False
        finally:
            pool.close()

    def test_interpreter_error_triggers_replacement_on_release(self) -> None:
        """After InterpreterError, release() closes and replaces the unhealthy interpreter."""
        pool = InterpreterPool(min_size=1, max_size=1)
        try:
            pooled = pool.acquire()
            fake = unittest.mock.MagicMock()
            fake.call.side_effect = concurrent.interpreters.InterpreterError("corrupted")
            pooled._interpreter = fake

            with pytest.raises(concurrent.interpreters.InterpreterError):
                pooled.call(_fn_return_42)
            # _healthy=False propagated from call() into __exit__ path
            pool.release(pooled, healthy=False)

            # Pool replaced the interpreter; a subsequent acquire must succeed.
            with pool.acquire() as fresh:
                result = fresh.call(_fn_return_42)
            assert result == 42
        finally:
            pool.close()


# ===========================================================================
# Unhealthy release path (release(healthy=False))
# ===========================================================================


class TestInterpreterPoolUnhealthyRelease:
    """release(healthy=False) closes the interpreter and maintains min_size."""

    def test_release_healthy_false_replaces_interpreter(self) -> None:
        """release(healthy=False) closes the interpreter and adds a replacement."""
        pool = InterpreterPool(min_size=1, max_size=2)
        try:
            pooled = pool.acquire()
            # Direct release with healthy=False.
            pool.release(pooled, healthy=False)
            # Pool should still be functional — replacement was created.
            with pool.acquire() as interp:
                result = interp.call(_fn_return_42)
            assert result == 42
        finally:
            pool.close()

    def test_release_healthy_false_after_pool_close_no_replacement(self) -> None:
        """After close(), release(healthy=False) closes but does not replace."""
        pool = InterpreterPool(min_size=1, max_size=1)
        pooled = pool.acquire()
        pool.close()  # Close the pool while interpreter is checked out.
        # release() must not raise even though pool is closed.
        pool.release(pooled, healthy=False)


# ===========================================================================
# Weakref GC scenario (_PooledInterpreter.__exit__ when pool is collected)
# ===========================================================================


class TestPooledInterpreterWeakref:
    """_PooledInterpreter.__exit__ is a no-op when the pool has been garbage collected."""

    def test_exit_noop_when_pool_collected(self) -> None:
        """Exiting a _PooledInterpreter after the pool is GC'd does not raise."""
        pool = InterpreterPool(min_size=1, max_size=1)
        pooled = pool.acquire()
        # Drop the last strong reference to the pool; force GC so the weakref expires.
        del pool
        gc.collect()
        # __exit__ must silently do nothing (pool ref is None).
        pooled.__exit__(None, None, None)


# ===========================================================================
# acquire_timeout=None paths
# ===========================================================================


class TestInterpreterPoolNoTimeout:
    """acquire_timeout=None blocks until a slot is available or pool is closed."""

    def test_no_timeout_blocks_until_released(self) -> None:
        """acquire_timeout=None blocks when pool is exhausted; unblocks on release."""
        pool = InterpreterPool(min_size=1, max_size=1, acquire_timeout=None)
        release_event = threading.Event()
        second_acquired: list[bool] = []

        def holder() -> None:
            with pool.acquire():
                release_event.wait(timeout=5.0)

        def waiter() -> None:
            # Trigger the holder to release, then immediately try to acquire.
            release_event.set()
            with pool.acquire() as interp:
                second_acquired.append(interp.call(_fn_return_42) == 42)

        t1 = threading.Thread(target=holder)
        t1.start()
        # Let the holder get the interpreter first.
        time.sleep(0.02)
        t2 = threading.Thread(target=waiter)
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        assert second_acquired == [True]
        pool.close()

    def test_no_timeout_raises_runtime_error_if_pool_closed_while_waiting(self) -> None:
        """acquire_timeout=None raises RuntimeError if pool is closed while blocked."""
        pool = InterpreterPool(min_size=1, max_size=1, acquire_timeout=None)
        outer = pool.acquire()
        error_seen: list[type[Exception]] = []

        def blocked_acquirer() -> None:
            try:
                pool.acquire()
            except RuntimeError:
                error_seen.append(RuntimeError)

        t = threading.Thread(target=blocked_acquirer)
        t.start()
        time.sleep(0.05)  # Give the thread time to block in acquire().
        pool.close()  # Closes the pool; wakes all waiters.
        t.join(timeout=5.0)
        pool.release(outer, healthy=False)  # Clean up the checked-out interpreter.

        assert error_seen == [RuntimeError]
