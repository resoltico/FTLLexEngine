"""Readers-writer lock for high-concurrency FluentBundle access.

This module provides a readers-writer lock that allows:
- Multiple concurrent readers (format operations)
- Exclusive writer access (add_resource, add_function)
- Writer preference to prevent starvation
- Reentrant reader locks (same thread can acquire read lock multiple times)
- Reentrant writer locks (same thread can acquire write lock multiple times)
- Write-to-read lock downgrading (writer can acquire read locks)
- Optional timeout for lock acquisition (raises TimeoutError)
- Proper deadlock avoidance

Architecture:
    RWLock uses a condition variable to coordinate reader and writer threads.
    Writers are prioritized when waiting to prevent indefinite write starvation
    in read-heavy workloads.

Lock Downgrading:
    A thread holding the write lock can acquire read locks without blocking.
    This enables write-then-read patterns where a thread modifies data, then
    reads it back for validation. When the write lock is released, any held
    read locks automatically convert to regular reader locks.

Upgrade Limitation:
    Read-to-write lock upgrades are not supported. A thread holding a read lock
    cannot acquire the write lock (raises RuntimeError). This prevents deadlock
    scenarios where the thread would wait for itself to release the read lock.
    Release the read lock before acquiring the write lock, or restructure code
    to acquire write lock first.

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
        All methods are thread-safe. The lock is reentrant for readers
        and writers (same thread can acquire read or write lock multiple times).

    Lock Downgrading:
        A thread holding the write lock can acquire read locks without blocking.
        When the write lock is released, held read locks remain valid as regular
        reader locks. This enables write-then-read validation patterns.

    Upgrade Limitation:
        Read-to-write lock upgrades are not supported. A thread holding a read
        lock cannot acquire the write lock (raises RuntimeError).

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
        >>> # Reentrant write locks work
        >>> with lock.write():
        ...     with lock.write():  # Same thread can reacquire
        ...         # Still exclusive
        ...         pass
        >>>
        >>> # Write-to-read downgrading works
        >>> with lock.write():
        ...     # Modify data
        ...     with lock.read():  # Can acquire read while holding write
        ...         # Validate changes
        ...         pass
    """

    __slots__ = (
        "_active_readers",
        "_active_writer",
        "_condition",
        "_reader_threads",
        "_waiting_writers",
        "_writer_held_reads",
        "_writer_reentry_count",
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

        # Track write lock reentry count for write reentrancy
        self._writer_reentry_count: int = 0

        # Track read locks acquired while holding write lock (lock downgrading)
        # When writer releases, these convert to regular reader locks
        self._writer_held_reads: int = 0

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
        Reentrant: same thread can acquire write lock multiple times.

        Args:
            timeout: Maximum seconds to wait for lock acquisition.
                None (default) waits indefinitely. Non-negative float
                specifies deadline; 0.0 is a non-blocking attempt.

        Raises:
            RuntimeError: If thread attempts read-to-write lock upgrade.
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
        - A writer is active (unless current thread IS the active writer)
        - Writers are waiting (writer preference to prevent starvation)

        Allows reentrant acquisition by same thread.
        Allows lock downgrading (write lock holder can acquire read locks).

        Args:
            timeout: Maximum seconds to wait. None waits indefinitely.

        Raises:
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

            # Lock downgrading: writer can acquire read locks without blocking
            # These reads are tracked separately and convert to regular reads
            # when the write lock is released
            if self._active_writer == current_thread_id:
                self._writer_held_reads += 1
                return

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
        Handles writer-held reads (lock downgrading) correctly.
        Notifies waiting writers when last reader exits.
        """
        current_thread_id = threading.get_ident()

        with self._condition:
            # Check if this is a writer-held read (lock downgrading case)
            if self._active_writer == current_thread_id and self._writer_held_reads > 0:
                self._writer_held_reads -= 1
                return

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
        Reentrant: same thread can acquire write lock multiple times.

        Args:
            timeout: Maximum seconds to wait. None waits indefinitely.

        Raises:
            RuntimeError: If thread attempts read-to-write lock upgrade.
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

            # Check if this thread already holds the write lock (reentrant case)
            if self._active_writer == current_thread_id:
                self._writer_reentry_count += 1
                return

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

        Handles reentrant lock releases correctly.
        Converts writer-held reads to regular reader locks when fully released.
        Notifies all waiting readers and writers when fully released.
        """
        current_thread_id = threading.get_ident()

        with self._condition:
            if self._active_writer != current_thread_id:
                msg = "Thread does not hold write lock"
                raise RuntimeError(msg)

            # Handle reentrant release
            if self._writer_reentry_count > 0:
                self._writer_reentry_count -= 1
                return

            # Convert writer-held reads to regular reader locks
            # This enables lock downgrading: writer can acquire reads, release write,
            # and continue as a reader without blocking
            if self._writer_held_reads > 0:
                self._active_readers += 1
                self._reader_threads[current_thread_id] = self._writer_held_reads
                self._writer_held_reads = 0

            # Release write lock
            self._active_writer = None

            # Notify all waiting threads (readers and writers)
            # Writer preference handled in _acquire_read logic
            self._condition.notify_all()
