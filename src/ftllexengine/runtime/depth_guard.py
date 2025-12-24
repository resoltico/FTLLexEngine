"""Unified depth limiting for recursion protection.

Provides reusable depth tracking to prevent stack overflow from:
- Deep Placeable nesting in resolution
- Deep AST nesting in validation
- Programmatically constructed adversarial ASTs

Thread-safe: uses explicit state, no thread-local storage.
Python 3.13+.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ftllexengine.diagnostics import FluentResolutionError
from ftllexengine.diagnostics.templates import ErrorTemplate

__all__ = ["MAX_EXPRESSION_DEPTH", "DepthGuard", "DepthLimitExceededError"]

# Maximum expression/AST depth to prevent stack overflow.
# 100 nested Placeables is almost certainly adversarial or malformed input.
# This limit prevents RecursionError while allowing reasonable nesting.
MAX_EXPRESSION_DEPTH: int = 100


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

    Thread Safety:
        Uses explicit instance state, fully reentrant.
        Each call stack maintains its own DepthGuard instance.

    Attributes:
        max_depth: Maximum allowed depth (default: MAX_EXPRESSION_DEPTH)
        current_depth: Current recursion depth
    """

    max_depth: int = MAX_EXPRESSION_DEPTH
    current_depth: int = field(default=0, init=False)

    def __enter__(self) -> DepthGuard:
        """Enter guarded section, increment depth."""
        self.current_depth += 1
        if self.current_depth > self.max_depth:
            raise DepthLimitExceededError(
                ErrorTemplate.expression_depth_exceeded(self.max_depth)
            )
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
