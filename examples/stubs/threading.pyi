"""Type stubs for threading module to improve type checking in examples.

This stub file provides enhanced typing for threading.local() and other
threading primitives used in examples/thread_safety.py.

NOTE: This is a local stub for example code only. It augments the standard
typeshed threading stubs with better support for dynamic attributes on
threading.local().

For production code, consider using TypedDict or dataclass wrappers around
threading.local() instead of relying on dynamic attributes.
"""

# ruff: noqa: PIE790  # ... is required in stub files, not unnecessary
# pylint: disable=unnecessary-ellipsis  # ... is required in stub files per PEP 484

from collections.abc import Callable
from typing import Any

class local:  # noqa: N801  # pylint: disable=invalid-name
    """Enhanced type stub for threading.local() with dynamic attribute support.

    Type stub: Matches stdlib threading.local class naming convention.
    This stub allows mypy to understand that threading.local() instances can
    have arbitrary attributes set at runtime.

    Usage in examples/thread_safety.py:
        thread_local = threading.local()
        thread_local.bundle = FluentBundle(...)  # mypy understands this
        return thread_local.bundle  # type: ignore still needed for generic return
    """

    def __init__(self) -> None: ...
    def __getattribute__(self, name: str) -> Any: ...
    def __setattr__(self, name: str, value: Any) -> None: ...
    def __delattr__(self, name: str) -> None: ...

class Thread:  # pylint: disable=too-many-positional-arguments
    """Thread class stub."""

    def __init__(  # pylint: disable=unused-argument
        self,
        group: None = None,
        target: Callable[..., Any] | None = None,
        name: str | None = None,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        *,
        daemon: bool | None = None,
    ) -> None:
        """Initialize thread."""
        ...
    def start(self) -> None:
        """Start thread execution."""
        ...
    def join(self, timeout: float | None = None) -> None:  # pylint: disable=unused-argument
        """Wait for thread completion."""
        ...
    @property
    def ident(self) -> int | None:
        """Thread identifier."""
        ...

class Lock:
    """Lock class stub."""

    def __init__(self) -> None:
        """Initialize lock."""
        ...
    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:  # pylint: disable=unused-argument
        """Acquire lock."""
        ...
    def release(self) -> None:
        """Release lock."""
        ...
    def __enter__(self) -> bool:
        """Enter context manager."""
        ...
    def __exit__(self, *args: Any) -> None:  # pylint: disable=unused-argument
        """Exit context manager."""
        ...

def current_thread() -> Thread:
    """Return current thread."""
