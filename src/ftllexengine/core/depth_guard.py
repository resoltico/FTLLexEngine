"""Unified depth limiting for recursion protection.

Provides reusable depth tracking to prevent stack overflow from:
- Deep Placeable nesting in resolution
- Deep AST nesting in validation/serialization
- Programmatically constructed adversarial ASTs

Thread-safe: uses explicit state, no thread-local storage.
Python 3.13+.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Self

from ftllexengine.constants import MAX_DEPTH

__all__ = ["DepthGuard", "DepthLimitExceededError", "depth_clamp"]

logger = logging.getLogger(__name__)

type DepthErrorFactory = Callable[[int], BaseException]


class DepthLimitExceededError(ValueError):
    """Raised when DepthGuard detects recursion beyond the configured limit."""

    __slots__ = ("max_depth",)

    def __init__(self, max_depth: int) -> None:
        self.max_depth = max_depth
        super().__init__(f"Depth limit exceeded (max_depth={max_depth})")


def _default_depth_error(max_depth: int) -> DepthLimitExceededError:
    """Build the default core-layer depth exception."""
    return DepthLimitExceededError(max_depth)


@dataclass(slots=True)
class DepthGuard:
    """Context manager for tracking and limiting recursion depth.

    Usage in resolution:
        guard = DepthGuard()
        with guard:
            result = self._resolve_expression(nested_expr, ...)

    Usage in validation:
        guard = DepthGuard(max_depth=50)
        with guard:
            self._validate_expression(expr)

    Explicit check (non-context-manager call sites):
        guard = DepthGuard()
        guard.check()  # Raises DepthLimitExceededError if limit exceeded

    Mutability Note:
        Intentionally mutable (not frozen=True) to enable stateful depth
        tracking via context manager protocol. The current_depth field is
        incremented/decremented on __enter__/__exit__.

    Thread Safety:
        Uses explicit instance state, fully reentrant.
        Each call stack maintains its own DepthGuard instance.

    Attributes:
        max_depth: Maximum allowed depth (default: MAX_DEPTH)
        current_depth: Current recursion depth (read-only diagnostic)
    """

    max_depth: int = MAX_DEPTH
    current_depth: int = field(default=0, init=False)
    error_factory: DepthErrorFactory = field(
        default=_default_depth_error,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        """Clamp max_depth against Python recursion limit."""
        self.max_depth = depth_clamp(self.max_depth)

    def _raise_depth_error(self) -> None:
        """Raise the configured exception for a depth-limit breach."""
        raise self.error_factory(self.max_depth)

    def __enter__(self) -> Self:
        """Enter guarded section, increment depth.

        Validates depth limit BEFORE incrementing to prevent state corruption
        if the configured exception is raised. Since __exit__ is not called when
        __enter__ raises, incrementing first would leave current_depth
        permanently elevated, causing all subsequent operations to fail.
        """
        if self.current_depth >= self.max_depth:
            self._raise_depth_error()
        self.current_depth += 1
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit guarded section, decrement depth."""
        self.current_depth -= 1

    def check(self) -> None:
        """Explicitly check depth and raise if exceeded.

        Use when context manager pattern is not convenient.

        Raises:
            DepthLimitExceededError: If depth limit exceeded and the default
                core-layer error factory is in use.
            BaseException: Any caller-supplied exception produced by
                ``error_factory``.
        """
        if self.current_depth >= self.max_depth:
            self._raise_depth_error()


def depth_clamp(requested_depth: int, reserve_frames: int = 50) -> int:
    """Clamp requested depth against Python recursion limit.

    Validates requested depth against sys.getrecursionlimit() to prevent
    RecursionError on systems with constrained stack limits. Logs warning
    if clamping occurs.

    Args:
        requested_depth: Desired maximum depth
        reserve_frames: Stack frames to reserve for call overhead (default: 50)

    Returns:
        Safe depth value, clamped if necessary

    Example:
        >>> import sys  # doctest: +SKIP
        >>> sys.setrecursionlimit(200)  # doctest: +SKIP
        >>> depth_clamp(100)  # OK, within limit  # doctest: +SKIP
        100
        >>> depth_clamp(500)  # Exceeds limit, clamped to 150  # doctest: +SKIP
        150
    """
    max_safe_depth = sys.getrecursionlimit() - reserve_frames
    if requested_depth > max_safe_depth:
        logger.warning(
            "Requested depth %d exceeds Python recursion limit (%d). "
            "Clamping to %d to prevent RecursionError. "
            "Consider increasing sys.setrecursionlimit() if needed.",
            requested_depth,
            sys.getrecursionlimit(),
            max_safe_depth,
        )
        return max_safe_depth
    return requested_depth
