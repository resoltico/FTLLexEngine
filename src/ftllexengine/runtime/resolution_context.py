"""Resolution context and global depth guard for Fluent message resolution.

Provides the stateful context passed through the resolver during message
resolution, and a global depth guard that prevents stack overflow attacks
via custom function re-entry.

Architecture:
    - GlobalDepthGuard: Uses contextvars for async-safe same-session depth tracking
    - ResolutionContext: Explicit per-resolution state (stack, depth, expansion)

Thread Safety:
    ResolutionContext is created per-resolution for full isolation.
    GlobalDepthGuard uses contextvars for thread/async-safe same-session state.

Python 3.13+.
"""

from __future__ import annotations

import time
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Self

from ftllexengine.constants import DEFAULT_MAX_EXPANSION_SIZE, MAX_DEPTH
from ftllexengine.core.depth_guard import DepthGuard, depth_clamp
from ftllexengine.diagnostics import (
    ErrorCategory,
    ErrorTemplate,
    FrozenFluentError,
)
from ftllexengine.diagnostics.depth import resolution_depth_error
from ftllexengine.integrity import DataIntegrityError, IntegrityContext

__all__ = ["GlobalDepthGuard", "ResolutionContext"]

# ContextVar State (Architectural Decision):
# Global resolution depth tracking is still the right owner for same-session
# nested formatting. Cross-thread entry is owned separately by
# ResolutionReentryGate at the bundle boundary because spawned threads do not
# inherit ContextVars.
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

    Thread Spawning:
        Cross-thread entry is rejected by the bundle-owned ResolutionReentryGate
        while custom-function code is executing. This guard therefore remains
        responsible only for same-session depth tracking, which is exactly what
        ContextVar propagation can represent reliably.
    """

    __slots__ = ("_max_depth", "_token")

    def __init__(self, max_depth: int = MAX_DEPTH) -> None:
        """Initialize guard with maximum depth limit."""
        self._max_depth = depth_clamp(max_depth)
        self._token: Token[int] | None = None

    def __enter__(self) -> Self:
        """Enter guarded section, increment global depth."""
        current = _global_resolution_depth.get()
        if current >= self._max_depth:
            diag = ErrorTemplate.depth_exceeded(self._max_depth)
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
        max_depth: Maximum resolution depth (prevents stack overflow)
        max_expression_depth: Maximum expression nesting depth
        max_expansion_size: Maximum total characters in resolved output (DoS prevention)
        _stack: Mutable resolution stack for cycle detection — always starts empty;
            not an init parameter to prevent bypass of cycle-detection invariants.
        _seen: O(1) membership set for cycle detection (private, always starts empty)
        _total_chars: Running count of resolved characters (private, always starts at zero)
        _expression_guard: DepthGuard for expression depth tracking (private)
    """

    _stack: list[str] = field(init=False, default_factory=list)
    _seen: set[str] = field(init=False, default_factory=set)
    max_depth: int = MAX_DEPTH
    max_expression_depth: int = MAX_DEPTH
    max_expansion_size: int | None = DEFAULT_MAX_EXPANSION_SIZE
    _total_chars: int = field(init=False, default=0)
    _expression_guard: DepthGuard = field(init=False)
    _output_budget_exhausted: bool = field(init=False, default=False)
    _cacheable_output: bool = field(init=False, default=True)
    _noncacheable_functions: set[str] = field(init=False, default_factory=set)

    def __post_init__(self) -> None:
        """Initialize the expression depth guard with configured max depth."""
        self._expression_guard = DepthGuard(
            max_depth=self.max_expression_depth,
            error_factory=resolution_depth_error,
        )

    def push(self, key: str) -> None:
        """Push message key onto resolution stack."""
        self._stack.append(key)
        self._seen.add(key)

    def pop(self) -> str:
        """Pop message key from resolution stack.

        Raises:
            DataIntegrityError: If the stack and lookup set are out of sync,
                indicating internal state corruption. The stack is not mutated
                when corruption is detected, leaving both structures consistent
                for diagnostic inspection.
        """
        if not self._stack:
            ctx = IntegrityContext(
                component="resolution_context",
                operation="pop",
                timestamp=time.monotonic(),
                wall_time_unix=time.time(),
            )
            msg = "Resolution stack underflow: pop() called on empty stack"
            raise DataIntegrityError(msg, ctx)

        # Peek before mutating: if the key is absent from the lookup set,
        # the two structures are already out of sync. Raising here (before
        # any mutation) preserves the pre-pop state for post-mortem inspection.
        key = self._stack[-1]
        if key not in self._seen:
            ctx = IntegrityContext(
                component="resolution_context",
                operation="pop",
                key=key,
                timestamp=time.monotonic(),
                wall_time_unix=time.time(),
            )
            msg = (
                f"Resolution stack corrupted: key '{key}' present in stack "
                f"but absent from lookup set. Stack: {list(self._stack)}"
            )
            raise DataIntegrityError(msg, ctx)

        self._stack.pop()
        self._seen.remove(key)
        return key

    def contains(self, key: str) -> bool:
        """Check if key is in resolution stack (cycle detection).

        Performance: O(1) set lookup instead of O(N) list scan.
        """
        return key in self._seen

    @property
    def depth(self) -> int:
        """Current resolution depth."""
        return len(self._stack)

    def is_depth_exceeded(self) -> bool:
        """Check if maximum depth has been exceeded."""
        return self.depth >= self.max_depth

    def get_cycle_path(self, key: str) -> list[str]:
        """Get the cycle path for error reporting."""
        return [*self._stack, key]

    @property
    def resolution_path(self) -> tuple[str, ...]:
        """Current resolution stack as an immutable snapshot (read-only).

        Returns an immutable copy of the current resolution path for external
        use (e.g., error context, diagnostics). Callers must not modify the
        stack directly; use push() and pop() for all mutations.
        """
        return tuple(self._stack)

    def reserve_output(self, text: str) -> None:
        """Reserve budget for the exact string about to be appended.

        Premise:
            Budgeting after partial formatting creates undercount gaps.

        Reason:
            The owner of the output budget must see the final string fragment
            including isolation marks and fallbacks before it becomes visible.
        """
        next_total = self._total_chars + len(text)
        if self.max_expansion_size is not None and next_total > self.max_expansion_size:
            diag = ErrorTemplate.expansion_budget_exceeded(
                next_total,
                self.max_expansion_size,
            )
            raise FrozenFluentError(
                str(diag),
                ErrorCategory.RESOLUTION,
                diagnostic=diag,
            )
        self._total_chars = next_total

    def mark_output_budget_exhausted(self) -> None:
        """Remember that a later append crossed the output budget.

        Premise:
            Nested pattern resolution may convert an append failure into an
            error tuple instead of re-raising immediately.

        Reason:
            The enclosing pattern loop must still stop at the first quota
            breach so no later literal or fallback output leaks past the
            configured maximum.
        """
        self._output_budget_exhausted = True

    def mark_noncacheable_function(self, function_name: str) -> None:
        """Mark the current resolution as unsafe to cache.

        Premise:
            Custom functions may depend on time, I/O, process state, or other
            external inputs outside the cache key.

        Reason:
            Resolution must carry cacheability evidence forward explicitly so
            the bundle can skip caching results that depended on non-pure
            callables.
        """
        self._cacheable_output = False
        self._noncacheable_functions.add(function_name)

    @property
    def output_budget_exhausted(self) -> bool:
        """Report whether output generation must stop after a budget breach."""
        return self._output_budget_exhausted

    @property
    def cacheable_output(self) -> bool:
        """Report whether the resolved output may safely enter the cache."""
        return self._cacheable_output

    @property
    def noncacheable_functions(self) -> frozenset[str]:
        """Return the non-cacheable functions observed during this resolution."""
        return frozenset(self._noncacheable_functions)

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
