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
from dataclasses import dataclass, field

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.diagnostics import FluentResolutionError
from ftllexengine.diagnostics.templates import ErrorTemplate

__all__ = ["DepthGuard", "DepthLimitExceededError", "depth_clamp"]

logger = logging.getLogger(__name__)


class DepthLimitExceededError(FluentResolutionError):
    """Raised when maximum expression depth is exceeded.

    This error indicates either:
    - Adversarial input designed to cause stack overflow
    - Malformed programmatic AST construction
    - Unintended deep nesting in FTL content
    """


@dataclass(slots=True)
class DepthGuard:
    """Context manager for tracking and limiting recursion depth.

    Usage in resolution:
        guard = DepthGuard()
        with guard:
            # Recursive operation
            result = self._resolve_expression(nested_expr, ...)

    Usage in validation:
        guard = DepthGuard(max_depth=50)
        with guard:
            self._validate_expression(expr)

    Mutability Note:
        Intentionally mutable (not frozen=True) to enable stateful depth
        tracking via context manager protocol. The current_depth field is
        incremented/decremented on __enter__/__exit__.

    Thread Safety:
        Uses explicit instance state, fully reentrant.
        Each call stack maintains its own DepthGuard instance.

    Attributes:
        max_depth: Maximum allowed depth (default: MAX_DEPTH)
        current_depth: Current recursion depth
    """

    max_depth: int = MAX_DEPTH
    current_depth: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        """Clamp max_depth against Python recursion limit."""
        object.__setattr__(self, "max_depth", depth_clamp(self.max_depth))

    def __enter__(self) -> DepthGuard:
        """Enter guarded section, increment depth.

        Validates depth limit BEFORE incrementing to prevent state corruption
        if DepthLimitExceededError is raised. Since __exit__ is not called when
        __enter__ raises, incrementing first would leave current_depth permanently
        elevated, causing all subsequent operations to fail.
        """
        if self.current_depth >= self.max_depth:
            raise DepthLimitExceededError(
                ErrorTemplate.expression_depth_exceeded(self.max_depth)
            )
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

    @property
    def depth(self) -> int:
        """Current depth (alias for current_depth)."""
        return self.current_depth

    def is_exceeded(self) -> bool:
        """Check if depth limit has been exceeded."""
        return self.current_depth >= self.max_depth

    def check(self) -> None:
        """Explicitly check depth and raise if exceeded.

        Use when context manager pattern is not convenient.

        Raises:
            DepthLimitExceededError: If depth limit exceeded
        """
        if self.current_depth >= self.max_depth:
            raise DepthLimitExceededError(
                ErrorTemplate.expression_depth_exceeded(self.max_depth)
            )

    def increment(self) -> None:
        """Manually increment depth (use with decrement for non-context-manager use)."""
        self.current_depth += 1

    def decrement(self) -> None:
        """Manually decrement depth (use with increment for non-context-manager use)."""
        if self.current_depth > 0:
            self.current_depth -= 1

    def reset(self) -> None:
        """Reset depth to zero (useful for reuse across multiple operations)."""
        self.current_depth = 0


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
        >>> import sys
        >>> sys.setrecursionlimit(200)
        >>> depth_clamp(100)  # OK, within limit
        100
        >>> depth_clamp(500)  # Exceeds limit, clamped to 150
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
