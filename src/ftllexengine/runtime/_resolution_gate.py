"""Internal gate for bundle formatting re-entry ownership.

This module closes the cross-thread seam left by ContextVar-only depth
tracking. The gate allows ordinary concurrent top-level formatting, but when a
bundle is executing opaque custom-function code it rejects fresh external
formatting entry into that same bundle unless the call already belongs to the
current resolution session.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING

from ftllexengine.diagnostics import ErrorCategory, ErrorTemplate, FrozenFluentError

__all__ = ["ResolutionReentryGate"]

if TYPE_CHECKING:
    from collections.abc import Iterator

_current_resolution_session: ContextVar[object | None] = ContextVar(
    "ftllexengine_resolution_session",
    default=None,
)


@dataclass(slots=True)
class ResolutionReentryGate:
    """Own re-entry admission for one bundle's formatting surface."""

    _lock: Lock = field(default_factory=Lock)
    _custom_function_depth: int = 0

    @contextmanager
    def format_call(self) -> Iterator[None]:
        """Enter one bundle.format_pattern() call under the current resolution session.

        Premise:
            New threads spawned inside custom functions do not inherit ContextVars.

        Reason:
            We admit same-session nested formatting, but block fresh entry while
            a custom function is active so a new thread cannot reset the depth
            budget simply by calling back into the bundle from outside the
            original session.
        """
        existing_session = _current_resolution_session.get()
        token: Token[object | None] | None = None

        if existing_session is None:
            with self._lock:
                if self._custom_function_depth > 0:
                    diag = ErrorTemplate.reentrant_formatting_blocked()
                    raise FrozenFluentError(
                        str(diag),
                        ErrorCategory.RESOLUTION,
                        diagnostic=diag,
                    )
            token = _current_resolution_session.set(object())

        try:
            yield
        finally:
            if token is not None:
                _current_resolution_session.reset(token)

    @contextmanager
    def custom_function_scope(self) -> Iterator[None]:
        """Mark the period where bundle-owned custom user code is executing."""
        with self._lock:
            self._custom_function_depth += 1
        try:
            yield
        finally:
            with self._lock:
                self._custom_function_depth -= 1
