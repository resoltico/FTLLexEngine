"""Tests for runtime/resolution_context.py: ResolutionContext.pop() error paths.

Covers lines 167-172 (stack underflow) and 179-188 (corrupted state):
- pop() on empty stack raises DataIntegrityError with component='resolution_context'
- pop() when the top key is absent from _seen raises DataIntegrityError

These paths are defensive integrity guards that cannot be triggered by the
resolver under normal operation; they detect internal corruption bugs.

Python 3.13+.
"""

from __future__ import annotations

import pytest

from ftllexengine.integrity import DataIntegrityError
from ftllexengine.runtime.resolution_context import ResolutionContext


class TestResolutionContextPopErrors:
    """ResolutionContext.pop() integrity guards raise DataIntegrityError."""

    def test_pop_empty_stack_raises_data_integrity_error(self) -> None:
        """pop() on empty stack raises DataIntegrityError (lines 167-172).

        The stack underflow guard prevents silent state corruption when
        pop() is called without a preceding push().
        """
        ctx = ResolutionContext()

        with pytest.raises(DataIntegrityError, match="stack underflow"):
            ctx.pop()

    def test_pop_empty_stack_error_has_correct_component(self) -> None:
        """DataIntegrityError from empty pop has component='resolution_context'."""
        ctx = ResolutionContext()

        with pytest.raises(DataIntegrityError) as exc_info:
            ctx.pop()

        exc = exc_info.value
        assert exc.context is not None
        assert exc.context.component == "resolution_context"
        assert exc.context.operation == "pop"

    def test_pop_corrupted_seen_raises_data_integrity_error(self) -> None:
        """pop() with key in stack but absent from _seen raises DataIntegrityError (lines 179-188).

        The corruption guard fires when _stack and _seen are out of sync.
        This is a permanent defensive invariant: push() always adds to both;
        corruption indicates a bug in the caller, not a user error.
        """
        ctx = ResolutionContext()
        ctx.push("message-id")

        # Directly corrupt the state: remove from _seen without removing from _stack.
        # This simulates internal corruption that the guard detects before mutating.
        ctx._seen.discard("message-id")

        with pytest.raises(DataIntegrityError, match="stack corrupted"):
            ctx.pop()

    def test_pop_corrupted_error_preserves_state_for_inspection(self) -> None:
        """Corruption guard raises before mutating: pre-pop state is preserved."""
        ctx = ResolutionContext()
        ctx.push("msg-a")
        ctx.push("msg-b")

        # Corrupt _seen by removing only the top key
        ctx._seen.discard("msg-b")

        with pytest.raises(DataIntegrityError) as exc_info:
            ctx.pop()

        exc = exc_info.value
        assert exc.context is not None
        assert exc.context.component == "resolution_context"
        assert exc.context.operation == "pop"
        assert exc.context.key == "msg-b"

        # Stack must not have been mutated (guard raised before pop())
        assert ctx.depth == 2

    def test_pop_normal_operation_succeeds(self) -> None:
        """pop() after push() returns the pushed key without error."""
        ctx = ResolutionContext()
        ctx.push("hello")

        result = ctx.pop()

        assert result == "hello"
        assert ctx.depth == 0

    def test_push_pop_roundtrip_restores_empty_state(self) -> None:
        """push/pop roundtrip leaves context in empty state."""
        ctx = ResolutionContext()
        ctx.push("a")
        ctx.push("b")
        ctx.push("c")

        assert ctx.pop() == "c"
        assert ctx.pop() == "b"
        assert ctx.pop() == "a"
        assert ctx.depth == 0
        assert not ctx.contains("a")
        assert not ctx.contains("b")
        assert not ctx.contains("c")
