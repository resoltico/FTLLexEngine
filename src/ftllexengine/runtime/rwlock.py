"""Readers-writer lock for high-concurrency FluentBundle access.

This module provides a readers-writer lock that allows:
- Multiple concurrent readers (format operations)
- Exclusive writer access (add_resource, add_function)
- Writer preference to prevent starvation
- Reentrant reader locks (same thread can acquire read lock multiple times)
- Optional timeout for lock acquisition (raises TimeoutError)
- Proper deadlock avoidance

Architecture:
    RWLock uses a condition variable to coordinate reader and writer threads.
    Writers are prioritized when waiting to prevent indefinite write starvation
    in read-heavy workloads.

Upgrade and Downgrade Limitations:
    Read-to-write lock upgrades are not supported. A thread holding a read lock
    cannot acquire the write lock (raises RuntimeError). This prevents deadlock
    scenarios where the thread would wait for itself to release the read lock.
    Release the read lock before acquiring the write lock, or restructure code
    to acquire write lock first.

    Write-to-read lock downgrading is not supported. A thread holding the write
    lock cannot acquire the read lock (raises RuntimeError). FluentBundle write
    paths (add_resource, add_function) are single-level operations that do not
    need to read-validate while holding the write lock.

    Write lock reentrancy is not supported. A thread holding the write lock
    cannot acquire the write lock again (raises RuntimeError). FluentBundle write
    paths are single-level operations; nested write acquisition is a design error.

Python 3.13+.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator

__all__ = ["RWLock"]


class RWLock:
    """Readers-writer lock with writer preference.

    Allows multiple concurrent readers OR a single exclusive writer.
    Writers have priority to prevent starvation in read-heavy workloads.

    Thread Safety:
        All methods are thread-safe. The read lock is reentrant: the same
        thread can acquire it multiple times and must release it the same
        number of times.

    Limitations:
        Read-to-write upgrades are prohibited: raises RuntimeError.
        Write-to-read downgrades are prohibited: raises RuntimeError.
        Write lock reentrancy is prohibited: raises RuntimeError.

    Example:
        >>> lock = RWLock()
        >>>
        >>> # Multiple readers can proceed concurrently
        >>> with lock.read():
        ...     # Read data
        ...     pass
        >>>
        >>> # Writers get exclusive access
        >>> with lock.write():
        ...     # Modify data
        ...     pass
        >>>
        >>> # Reentrant read locks work
        >>> with lock.read():
        ...     with lock.read():  # Same thread can reacquire
        ...         # Still shared
        ...         pass
    """

    __slots__ = (
        "_active_readers",
        "_active_writer",
        "_condition",
        "_reader_threads",
        "_waiting_writers",
    )

    def __init__(self) -> None:
        """Initialize readers-writer lock."""
        # Condition variable coordinates access between threads
        self._condition = threading.Condition(threading.Lock())

        # Track active readers count
        self._active_readers: int = 0

        # Track which thread ID (if any) holds write lock
        self._active_writer: int | None = None

        # Track waiting writers count (for priority scheduling)
        self._waiting_writers: int = 0

        # Track reader thread IDs and their recursive acquisition count
        # This enables reentrant read locks (same thread acquiring multiple times)
        self._reader_threads: dict[int, int] = {}

    @contextmanager
    def read(self, timeout: float | None = None) -> Generator[None]:
        """Acquire read lock (shared access).

        Multiple threads can hold read locks concurrently.
        Reentrant: same thread can acquire read lock multiple times.

        Args:
            timeout: Maximum seconds to wait for lock acquisition.
                None (default) waits indefinitely. Non-negative float
                specifies deadline; 0.0 is a non-blocking attempt.

        Raises:
            RuntimeError: If thread holds write lock (downgrade prohibited).
            TimeoutError: If lock cannot be acquired within timeout.
            ValueError: If timeout is negative.

        Yields:
            None

        Example:
            >>> with lock.read():
            ...     # Safe to read data
            ...     pass
            >>> with lock.read(timeout=1.0):
            ...     # Acquired within 1 second or TimeoutError raised
            ...     pass
        """
        self._acquire_read(timeout)
        try:
            yield
        finally:
            self._release_read()

    @contextmanager
    def write(self, timeout: float | None = None) -> Generator[None]:
        """Acquire write lock (exclusive access).

        Only one thread can hold write lock at a time.
        Blocks until all readers release their locks.
        Non-reentrant: raises RuntimeError if called while already holding write lock.

        Args:
            timeout: Maximum seconds to wait for lock acquisition.
                None (default) waits indefinitely. Non-negative float
                specifies deadline; 0.0 is a non-blocking attempt.

        Raises:
            RuntimeError: If thread attempts read-to-write lock upgrade.
            RuntimeError: If thread already holds the write lock.
            TimeoutError: If lock cannot be acquired within timeout.
            ValueError: If timeout is negative.

        Yields:
            None

        Example:
            >>> with lock.write():
            ...     # Exclusive access to modify data
            ...     pass
            >>> with lock.write(timeout=2.0):
            ...     # Acquired within 2 seconds or TimeoutError raised
            ...     pass
        """
        self._acquire_write(timeout)
        try:
            yield
        finally:
            self._release_write()

    def _acquire_read(self, timeout: float | None = None) -> None:
        """Acquire read lock (internal implementation).

        Blocks if:
        - A writer is active
        - Writers are waiting (writer preference to prevent starvation)

        Allows reentrant acquisition by same thread.

        Args:
            timeout: Maximum seconds to wait. None waits indefinitely.

        Raises:
            RuntimeError: If thread holds write lock (downgrade prohibited).
            TimeoutError: If lock cannot be acquired within timeout.
            ValueError: If timeout is negative.
        """
        if timeout is not None and timeout < 0:
            msg = f"Timeout must be non-negative, got {timeout}"
            raise ValueError(msg)

        current_thread_id = threading.get_ident()

        with self._condition:
            # Check if this thread already holds a read lock (reentrant case)
            if current_thread_id in self._reader_threads:
                self._reader_threads[current_thread_id] += 1
                return

            # Prohibit write-to-read downgrade. FluentBundle writers are single-level
            # operations; they do not need to read-validate while holding the write lock.
            if self._active_writer == current_thread_id:
                msg = (
                    "Cannot acquire read lock while holding write lock. "
                    "Release the write lock before acquiring a read lock."
                )
                raise RuntimeError(msg)

            # Compute deadline for timeout-aware waiting
            deadline = (
                time.monotonic() + timeout if timeout is not None else None
            )

            # Wait while writer is active OR writers are waiting (writer preference)
            while self._active_writer is not None or self._waiting_writers > 0:
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        msg = "Timed out waiting for read lock"
                        raise TimeoutError(msg)
                    self._condition.wait(timeout=remaining)
                else:
                    self._condition.wait()

            # Acquire read lock
            self._active_readers += 1
            self._reader_threads[current_thread_id] = 1

    def _release_read(self) -> None:
        """Release read lock (internal implementation).

        Handles reentrant lock releases correctly.
        Notifies waiting writers when last reader exits.
        """
        current_thread_id = threading.get_ident()

        with self._condition:
            if current_thread_id not in self._reader_threads:
                msg = "Thread does not hold read lock"
                raise RuntimeError(msg)

            # Decrement reentrant count
            self._reader_threads[current_thread_id] -= 1

            # If this thread has no more read locks, remove from tracking
            if self._reader_threads[current_thread_id] == 0:
                del self._reader_threads[current_thread_id]
                self._active_readers -= 1

                # If no more active readers, notify waiting writers
                if self._active_readers == 0:
                    self._condition.notify_all()

    def _acquire_write(self, timeout: float | None = None) -> None:
        """Acquire write lock (internal implementation).

        Blocks until all readers release their locks.
        Only one writer can be active at a time.
        Non-reentrant: raises RuntimeError if called while already holding write lock.

        Args:
            timeout: Maximum seconds to wait. None waits indefinitely.

        Raises:
            RuntimeError: If thread attempts read-to-write lock upgrade.
            RuntimeError: If thread already holds the write lock.
            TimeoutError: If lock cannot be acquired within timeout.
            ValueError: If timeout is negative.
        """
        if timeout is not None and timeout < 0:
            msg = f"Timeout must be non-negative, got {timeout}"
            raise ValueError(msg)

        current_thread_id = threading.get_ident()

        with self._condition:
            # Check for read-to-write upgrade attempt (prohibited to prevent deadlock)
            if current_thread_id in self._reader_threads:
                msg = (
                    "Cannot upgrade read lock to write lock. "
                    "Release read lock before acquiring write lock."
                )
                raise RuntimeError(msg)

            # Prohibit write lock reentrancy. FluentBundle write paths are single-level
            # operations; nested write acquisition is a design error, not a feature.
            if self._active_writer == current_thread_id:
                msg = (
                    "Cannot acquire write lock: already holding write lock. "
                    "Release the write lock before acquiring it again."
                )
                raise RuntimeError(msg)

            # Compute deadline for timeout-aware waiting
            deadline = (
                time.monotonic() + timeout if timeout is not None else None
            )

            # Increment waiting writers count (for reader blocking)
            self._waiting_writers += 1

            try:
                # Wait until no readers and no active writer
                while self._active_readers > 0 or self._active_writer is not None:
                    if deadline is not None:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            msg = "Timed out waiting for write lock"
                            raise TimeoutError(msg)
                        self._condition.wait(timeout=remaining)
                    else:
                        self._condition.wait()

                # Acquire write lock
                self._active_writer = current_thread_id

            finally:
                # Decrement waiting writers count and notify waiting readers.
                # Runs on both success and TimeoutError, keeping counter consistent.
                # notify_all() is required here: readers blocked in _acquire_read spin
                # on `while ... or self._waiting_writers > 0`. When a writer times out
                # and decrements _waiting_writers, no other thread issues a notification,
                # so those readers remain stuck indefinitely without this call.
                self._waiting_writers -= 1
                self._condition.notify_all()

    def _release_write(self) -> None:
        """Release write lock (internal implementation).

        Notifies all waiting readers and writers when released.
        """
        current_thread_id = threading.get_ident()

        with self._condition:
            if self._active_writer != current_thread_id:
                msg = "Thread does not hold write lock"
                raise RuntimeError(msg)

            # Release write lock
            self._active_writer = None

            # Notify all waiting threads (readers and writers)
            # Writer preference handled in _acquire_read logic
            self._condition.notify_all()

    @property
    def reader_count(self) -> int:
        """Number of distinct threads currently holding read locks.

        Thread-safe point-in-time snapshot. A thread holding a reentrant
        read lock (acquired multiple times) counts as one reader.

        Returns:
            Non-negative integer; 0 when no readers are active.
        """
        with self._condition:
            return self._active_readers

    @property
    def writer_active(self) -> bool:
        """True if any thread currently holds the write lock.

        Thread-safe point-in-time snapshot. Useful for production monitoring
        to detect write lock contention or stalled writers.

        Returns:
            True if write lock is held, False otherwise.
        """
        with self._condition:
            return self._active_writer is not None

    @property
    def writers_waiting(self) -> int:
        """Number of threads currently blocked waiting to acquire the write lock.

        Thread-safe point-in-time snapshot. A non-zero value means new readers
        are also being blocked (writer preference). Useful for diagnosing write
        starvation or identifying write-heavy contention patterns.

        Returns:
            Non-negative integer; 0 when no writers are waiting.
        """
        with self._condition:
            return self._waiting_writers
