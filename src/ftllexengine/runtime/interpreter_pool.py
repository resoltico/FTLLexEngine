"""Thread-safe pool of reusable concurrent.interpreters subinterpreters.

Implements a bounded pool that pre-warms a minimum number of subinterpreters
at construction time and manages acquisition/release under concurrent access.

Design rationale:
    Creating a subinterpreter is not free — it initializes a full Python
    interpreter state. For batch workloads (e.g., 50,000 legislative
    validation calls), O(n) interpreter lifecycle cost makes the per-call
    create-and-destroy pattern a bottleneck. A bounded pool amortizes creation
    cost across the lifetime of the pool while capping total interpreter count.

Mutable State (Architectural Decision):
    InterpreterPool maintains mutable state: the idle-interpreter deque
    (_pool), an active-count counter (_active_count), a closed flag (_closed),
    and a threading.Condition for coordinated blocking. Pool management is
    inherently stateful — immutability is impossible for a resource pool by
    definition. This is a permanent architectural exception to the library's
    default immutability protocol, documented here as the containing module's
    primary rationale.

Concurrency Model:
    All state transitions are protected by _condition (which owns the
    underlying Lock). acquire() uses Condition.wait_for() to block without
    spinning when the pool is exhausted and at max_size. release() notifies
    all waiting acquirers after returning or replacing an interpreter.

Python 3.14+. Zero external dependencies (concurrent.interpreters is PEP 734 stdlib).
"""

from __future__ import annotations

import concurrent.interpreters
import contextlib
import threading
import time
import weakref
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType
    from typing import Self

__all__ = ["InterpreterPool"]

# Module-level aliases for exception types used in health classification.
# Accessing these at module load validates that concurrent.interpreters
# is available, providing a clear ImportError rather than a late AttributeError.
_ExecutionFailed: type[Exception] = concurrent.interpreters.ExecutionFailed
_InterpreterError: type[Exception] = concurrent.interpreters.InterpreterError


class _PooledInterpreter:
    """A subinterpreter checked out from an InterpreterPool.

    Used as a context manager to guarantee return to the pool on exit:

        with pool.acquire() as interp:
            result = interp.call(my_function, arg1, arg2)

    The interpreter is returned to the pool when the ``with`` block exits
    cleanly. If an ``ExecutionFailed`` exception is raised (user code raised
    inside the subinterpreter), the interpreter is considered healthy and
    returned to the pool. Any other ``InterpreterError`` subclass marks the
    interpreter as unhealthy and triggers replacement.

    Attributes:
        interpreter: The underlying concurrent.interpreters.Interpreter.

    Note:
        Instances are created by InterpreterPool.acquire() and must not be
        constructed directly. The pool manages the lifecycle of all
        underlying interpreters.
    """

    __slots__ = ("_healthy", "_interpreter", "_pool_ref")

    def __init__(
        self,
        interpreter: concurrent.interpreters.Interpreter,
        pool: InterpreterPool,
    ) -> None:
        self._interpreter = interpreter
        self._pool_ref: weakref.ref[InterpreterPool] = weakref.ref(pool)
        self._healthy = True

    @property
    def interpreter(self) -> concurrent.interpreters.Interpreter:
        """The underlying subinterpreter."""
        return self._interpreter

    def call(
        self,
        callable_: Callable[..., object],
        /,
        *args: object,
        **kwargs: object,
    ) -> object:
        """Call a callable inside the subinterpreter and return its result.

        The callable must be importable by name in the subinterpreter's
        context (i.e., a module-level function, not a lambda or closure).
        Arguments and return values must be picklable or natively shareable
        across interpreter boundaries.

        If the callable raises an exception inside the subinterpreter, a
        ``concurrent.interpreters.ExecutionFailed`` exception is raised in
        the calling thread. The interpreter remains healthy after this event.

        Args:
            callable_: Module-level callable to invoke in the subinterpreter.
            *args: Positional arguments forwarded to the callable.
            **kwargs: Keyword arguments forwarded to the callable.

        Returns:
            The return value of the callable, transferred to the calling
            interpreter.

        Raises:
            concurrent.interpreters.ExecutionFailed: If callable raised
                inside the subinterpreter. The interpreter remains usable.
            concurrent.interpreters.InterpreterError: If the interpreter
                state is corrupted. The pool will replace this interpreter
                on release.
        """
        try:
            return self._interpreter.call(callable_, *args, **kwargs)
        except _ExecutionFailed:
            # User code raised inside the subinterpreter. The interpreter
            # itself is not corrupted — it remains usable. Re-raise without
            # marking unhealthy so the interpreter is returned to the pool.
            raise
        except _InterpreterError:
            # Interpreter-level error: state may be indeterminate.
            # Mark unhealthy so the pool replaces this interpreter on release.
            self._healthy = False
            raise

    def __enter__(self) -> Self:
        """Enter the context manager, yielding this interpreter wrapper."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Release the interpreter back to the pool on exit.

        Health classification on exception type:
        - No exception or ExecutionFailed: interpreter is healthy, returned.
        - Any other InterpreterError subclass: interpreter is unhealthy,
          replaced by the pool.
        - Any non-interpreter exception: interpreter is healthy (the exception
          originated in calling code, not inside the subinterpreter).
        """
        # If the exception passed through without being caught by call(), it
        # originated in calling code rather than inside the interpreter.
        # The interpreter itself is healthy in that case. Only flip to unhealthy
        # when call() explicitly set the flag due to an InterpreterError.
        pool = self._pool_ref()
        if pool is not None:
            pool.release(self, healthy=self._healthy)


@dataclass(slots=True, weakref_slot=True)
class InterpreterPool:
    """Thread-safe pool of reusable concurrent.interpreters subinterpreters.

    Pre-warms ``min_size`` interpreters at construction time. Additional
    interpreters are created on demand up to ``max_size``. When all
    interpreters are checked out and the pool is at ``max_size``,
    ``acquire()`` blocks until one is returned or the optional
    ``acquire_timeout`` expires.

    Usage::

        pool = InterpreterPool(min_size=2, max_size=8)
        with pool.acquire() as interp:
            result = interp.call(my_function, arg1, arg2)
        pool.close()

    Or as a context manager::

        with InterpreterPool(min_size=4) as pool:
            with pool.acquire() as interp:
                result = interp.call(my_function)

    Crash isolation guarantee:
        An exception raised inside ``interp.call()`` (surfaced as
        ``ExecutionFailed``) does NOT corrupt the subinterpreter. The
        interpreter is returned to the pool after such an event. Only
        a lower-level ``InterpreterError`` (interpreter state corrupted)
        triggers replacement.

    Thread safety:
        All methods are safe for concurrent use from multiple threads,
        including free-threaded Python 3.14 workers. The pool uses a single
        ``threading.Condition`` to coordinate acquire/release without spinning.

    Attributes:
        min_size: Number of interpreters to create at construction time.
        max_size: Maximum total interpreters (idle + checked out).
        acquire_timeout: Seconds to wait when the pool is exhausted before
            raising ``TimeoutError``. ``None`` blocks indefinitely.
    """

    min_size: int = 2
    max_size: int = 8
    acquire_timeout: float | None = 10.0

    # Private mutable pool state. Mutable state is a permanent architectural
    # requirement for any bounded resource pool; see module docstring.
    _pool: deque[concurrent.interpreters.Interpreter] = field(
        default_factory=deque, repr=False, init=False
    )
    _condition: threading.Condition = field(
        default_factory=threading.Condition, repr=False, init=False
    )
    _active_count: int = field(default=0, repr=False, init=False)
    _closed: bool = field(default=False, repr=False, init=False)

    def __post_init__(self) -> None:
        """Validate configuration and pre-warm the interpreter pool.

        Raises:
            ValueError: If min_size < 1 or max_size < min_size.
        """
        if self.min_size < 1:
            msg = f"InterpreterPool.min_size must be >= 1, got {self.min_size}"
            raise ValueError(msg)
        if self.max_size < self.min_size:
            msg = (
                f"InterpreterPool.max_size ({self.max_size}) must be >= "
                f"min_size ({self.min_size})"
            )
            raise ValueError(msg)
        for _ in range(self.min_size):
            self._pool.append(concurrent.interpreters.create())

    def acquire(self) -> _PooledInterpreter:
        """Acquire an interpreter from the pool, blocking if necessary.

        Returns immediately when an idle interpreter is available or when a
        new interpreter can be created (total active < max_size). Blocks
        until an interpreter is released when the pool is exhausted.

        Returns:
            A ``_PooledInterpreter`` context manager wrapping an idle
            subinterpreter. Use as a ``with`` statement to guarantee release.

        Raises:
            TimeoutError: If ``acquire_timeout`` is set and no interpreter
                becomes available within that many seconds.
            RuntimeError: If the pool has been closed.
        """
        with self._condition:
            if self._closed:
                msg = "InterpreterPool is closed"
                raise RuntimeError(msg)

            deadline: float | None = None
            if self.acquire_timeout is not None:
                deadline = time.monotonic() + self.acquire_timeout

            def _can_acquire() -> bool:
                return bool(self._pool) or self._active_count < self.max_size

            while not _can_acquire():
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        msg = (
                            f"InterpreterPool.acquire() timed out after "
                            f"{self.acquire_timeout}s: all {self.max_size} "
                            f"interpreters are checked out"
                        )
                        raise TimeoutError(msg)
                    self._condition.wait(timeout=remaining)
                else:
                    self._condition.wait()

                if self._closed:
                    # _condition.wait() releases the lock; another thread may close the pool.
                    # mypy narrows _closed as False after the initial guard check, but wait()
                    # releases the underlying lock — making concurrent close() possible at
                    # runtime. This guard is a permanent correctness requirement, not dead code.
                    msg = "InterpreterPool was closed while waiting for an interpreter"  # type: ignore[unreachable]
                    raise RuntimeError(msg)

            # Either we have an idle interpreter or we can create a new one.
            interp = self._pool.popleft() if self._pool else concurrent.interpreters.create()

            self._active_count += 1

        return _PooledInterpreter(interp, self)

    def release(
        self,
        pooled: _PooledInterpreter,
        *,
        healthy: bool = True,
    ) -> None:
        """Return a checked-out interpreter to the pool.

        Called automatically by ``_PooledInterpreter.__exit__``. May also be
        called directly when not using the context manager protocol, but the
        context manager is strongly preferred to avoid leaking interpreters.

        If ``healthy`` is ``False``, the interpreter is closed and replaced
        with a fresh one (provided total interpreter count stays within bounds).

        Args:
            pooled: The ``_PooledInterpreter`` being returned.
            healthy: Whether the interpreter is in a trustworthy state.
                Defaults to ``True``. Pass ``False`` when an
                ``InterpreterError`` (not ``ExecutionFailed``) was raised
                to trigger replacement with a fresh interpreter.
        """
        with self._condition:
            self._active_count -= 1
            if healthy and not self._closed:
                self._pool.append(pooled.interpreter)
            else:
                # Close the unhealthy or post-shutdown interpreter.
                with contextlib.suppress(Exception):
                    pooled.interpreter.close()
                # Replace with a fresh interpreter if the pool is still running
                # and below min_size, maintaining the pre-warmed floor.
                if not self._closed and len(self._pool) < self.min_size:
                    with contextlib.suppress(Exception):
                        self._pool.append(concurrent.interpreters.create())
            self._condition.notify_all()

    def close(self) -> None:
        """Close all idle interpreters and mark the pool as closed.

        After ``close()`` returns, ``acquire()`` raises ``RuntimeError``.
        Interpreters that are currently checked out are NOT forcibly closed;
        they will be closed (not returned to the pool) when their context
        manager exits.

        This method is idempotent: calling it multiple times is safe.
        """
        with self._condition:
            if self._closed:
                return
            self._closed = True
            idle = list(self._pool)
            self._pool.clear()
            self._condition.notify_all()

        for interp in idle:
            with contextlib.suppress(Exception):
                interp.close()

    def __enter__(self) -> Self:
        """Enter pool context manager, returning the pool itself."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the pool on context manager exit."""
        self.close()
