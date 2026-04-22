"""Parse-context state shared across Fluent grammar modules."""

from __future__ import annotations

from dataclasses import dataclass

from ftllexengine.constants import MAX_DEPTH

__all__ = ["ParseContext"]


@dataclass(slots=True)
class ParseContext:
    """Explicit context for parsing operations.

    Replaces thread-local state with explicit parameter passing for:
    - Thread safety without global state
    - Async framework compatibility
    - Easier testing (no state reset needed)
    - Clear dependency flow

    Security:
        Tracks nesting depth for BOTH placeables and function calls to prevent
        stack overflow DoS attacks. Deeply nested constructs like:
        - { { { ... } } } (nested placeables)
        - { A(B(C(D(...)))) } (nested function calls)
        Both consume stack frames and must be bounded.

    Attributes:
        max_nesting_depth: Maximum allowed nesting depth for placeables and calls
        current_depth: Current nesting depth (0 = top level)
        _depth_exceeded_flag: Mutable flag (list container) shared across all nested
            contexts to track if depth limit was exceeded during parse. Uses list[bool]
            as a mutable reference that persists when context objects are copied during
            enter_nesting(). Set to [True] when depth exceeded; checked at Junk creation
            to emit specific PARSE_NESTING_DEPTH_EXCEEDED diagnostic.
    """

    max_nesting_depth: int = MAX_DEPTH
    current_depth: int = 0
    _depth_exceeded_flag: list[bool] | None = None

    def __post_init__(self) -> None:
        """Initialize mutable depth exceeded flag if not provided."""
        if self._depth_exceeded_flag is None:
            self._depth_exceeded_flag = [False]

    def is_depth_exceeded(self) -> bool:
        """Check if maximum nesting depth has been exceeded."""
        return self.current_depth >= self.max_nesting_depth

    def mark_depth_exceeded(self) -> None:
        """Mark that depth limit was exceeded during parse."""
        if self._depth_exceeded_flag is not None:
            self._depth_exceeded_flag[0] = True

    def was_depth_exceeded(self) -> bool:
        """Check if depth limit was exceeded at any point during parse."""
        return bool(
            self._depth_exceeded_flag is not None and self._depth_exceeded_flag[0]
        )

    def enter_nesting(self) -> ParseContext:
        """Create new context with incremented depth for entering nested construct."""
        return ParseContext(
            max_nesting_depth=self.max_nesting_depth,
            current_depth=self.current_depth + 1,
            _depth_exceeded_flag=self._depth_exceeded_flag,
        )
