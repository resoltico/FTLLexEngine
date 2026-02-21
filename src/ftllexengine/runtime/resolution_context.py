"""Resolution context and global depth guard for Fluent message resolution.

Provides the stateful context passed through the resolver during message
resolution, and a global depth guard that prevents stack overflow attacks
via custom function re-entry.

Architecture:
    - GlobalDepthGuard: Uses contextvars for async-safe global depth tracking
    - ResolutionContext: Explicit per-resolution state (stack, depth, expansion)

Thread Safety:
    ResolutionContext is created per-resolution for full isolation.
    GlobalDepthGuard uses contextvars for thread/async-safe state.

Python 3.13+.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field

from ftllexengine.constants import DEFAULT_MAX_EXPANSION_SIZE, MAX_DEPTH
from ftllexengine.core.depth_guard import DepthGuard, depth_clamp
from ftllexengine.diagnostics import (
    ErrorCategory,
    ErrorTemplate,
    FrozenFluentError,
)

__all__ = ["GlobalDepthGuard", "ResolutionContext"]

# ContextVar State (Architectural Decision):
# Global resolution depth tracking via contextvars prevents custom functions from
# bypassing depth limits by calling back into bundle.format_pattern().
#
# Trade-off:
# - Explicit parameter threading would require signature changes across resolver,
#   function bridge, and all custom function implementations (~10+ signatures).
# - ContextVar provides thread/async-safe implicit state with minimal API impact.
# - Security requirement (DoS prevention via stack overflow) takes precedence over
#   the explicit control flow principle.
#
# This is a permanent architectural pattern; the security mechanism cannot be
# implemented without cross-context state tracking. Each async task/thread
# maintains independent state via contextvars semantics.
_global_resolution_depth: ContextVar[int] = ContextVar(
    "fluent_resolution_depth", default=0
)


class GlobalDepthGuard:
    """Context manager for tracking global resolution depth across format_pattern calls.

    Uses contextvars for async-safe per-task state. This prevents custom functions
    from bypassing depth limits by creating new ResolutionContext instances.

    Usage:
        with GlobalDepthGuard(max_depth=100):
            # Nested format_pattern calls are tracked globally
            result = resolver.resolve_message(message, args)

    Security:
        Without global depth tracking, a malicious custom function could:
        1. Receive control during resolution
        2. Call bundle.format_pattern() which creates a fresh ResolutionContext
        3. Repeat step 2 recursively, bypassing per-context depth limits
        4. Eventually cause stack overflow

        GlobalDepthGuard prevents this by tracking depth across all contexts.
    """

    __slots__ = ("_max_depth", "_token")

    def __init__(self, max_depth: int = MAX_DEPTH) -> None:
        """Initialize guard with maximum depth limit."""
        self._max_depth = depth_clamp(max_depth)
        self._token: Token[int] | None = None

    def __enter__(self) -> GlobalDepthGuard:
        """Enter guarded section, increment global depth."""
        current = _global_resolution_depth.get()
        if current >= self._max_depth:
            diag = ErrorTemplate.expression_depth_exceeded(self._max_depth)
            raise FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag)
        self._token = _global_resolution_depth.set(current + 1)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit guarded section, restore previous depth."""
        if self._token is not None:
            _global_resolution_depth.reset(self._token)


@dataclass(slots=True)
class ResolutionContext:
    """Explicit context for message resolution.

    Replaces thread-local state with explicit parameter passing for:
    - Thread safety without global state
    - Async framework compatibility (no thread-local conflicts)
    - Easier testing (no state reset needed)
    - Clear dependency flow

    Performance: Uses both list (for ordered path) and set (for O(1) lookup)
    to optimize cycle detection while preserving path information for errors.

    Instance Lifecycle:
        Each resolution operation creates a fresh ResolutionContext instance.
        This ensures complete isolation between concurrent resolutions.
        The per-resolution DepthGuard allocation is intentional for thread safety;
        object pooling is not used to avoid synchronization overhead.

    Attributes:
        stack: Resolution stack for cycle detection (message keys being resolved)
        _seen: Set for O(1) membership checking (internal)
        max_depth: Maximum resolution depth (prevents stack overflow)
        max_expression_depth: Maximum expression nesting depth
        max_expansion_size: Maximum total characters in resolved output (DoS prevention)
        _total_chars: Running count of resolved characters (internal)
        _expression_guard: DepthGuard for expression depth tracking (internal)
    """

    stack: list[str] = field(default_factory=list)
    _seen: set[str] = field(default_factory=set)
    max_depth: int = MAX_DEPTH
    max_expression_depth: int = MAX_DEPTH
    max_expansion_size: int = DEFAULT_MAX_EXPANSION_SIZE
    _total_chars: int = 0
    _expression_guard: DepthGuard = field(init=False)

    def __post_init__(self) -> None:
        """Initialize the expression depth guard with configured max depth."""
        self._expression_guard = DepthGuard(
            max_depth=self.max_expression_depth
        )

    def push(self, key: str) -> None:
        """Push message key onto resolution stack."""
        self.stack.append(key)
        self._seen.add(key)

    def pop(self) -> str:
        """Pop message key from resolution stack."""
        key = self.stack.pop()
        self._seen.discard(key)
        return key

    def contains(self, key: str) -> bool:
        """Check if key is in resolution stack (cycle detection).

        Performance: O(1) set lookup instead of O(N) list scan.
        """
        return key in self._seen

    @property
    def depth(self) -> int:
        """Current resolution depth."""
        return len(self.stack)

    def is_depth_exceeded(self) -> bool:
        """Check if maximum depth has been exceeded."""
        return self.depth >= self.max_depth

    def get_cycle_path(self, key: str) -> list[str]:
        """Get the cycle path for error reporting."""
        return [*self.stack, key]

    def track_expansion(self, char_count: int) -> None:
        """Add to running expansion total and check budget.

        Raises FrozenFluentError if expansion budget is exceeded. This prevents
        Billion Laughs attacks where small FTL input expands to gigabytes via
        nested message references (e.g., m0={m1}{m1}, m1={m2}{m2}, ...).
        """
        self._total_chars += char_count
        if self._total_chars > self.max_expansion_size:
            diag = ErrorTemplate.expansion_budget_exceeded(
                self._total_chars, self.max_expansion_size
            )
            raise FrozenFluentError(
                str(diag), ErrorCategory.RESOLUTION, diagnostic=diag
            )

    @property
    def expression_guard(self) -> DepthGuard:
        """Get the expression depth guard for context manager use.

        Usage:
            with context.expression_guard:
                result = self._resolve_expression(nested_expr, ...)
        """
        return self._expression_guard

    @property
    def total_chars(self) -> int:
        """Running count of resolved characters (read-only).

        Used by the resolver to check expansion budget before each element.
        """
        return self._total_chars

    @property
    def expression_depth(self) -> int:
        """Current expression nesting depth (read-only, delegates to guard)."""
        return self._expression_guard.current_depth
