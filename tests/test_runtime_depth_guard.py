"""Comprehensive tests for core/depth_guard.py.

Tests DepthGuard context manager, explicit check(), and depth_clamp()
with Hypothesis for property-based testing.

Python 3.13+.
"""

from __future__ import annotations

import logging
import sys

import pytest
from hypothesis import event, example, given, settings
from hypothesis import strategies as st

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.core.depth_guard import DepthGuard, depth_clamp
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.diagnostics.templates import ErrorTemplate

# ============================================================================
# Construction
# ============================================================================


class TestDepthGuardConstruction:
    """Test DepthGuard construction and defaults."""

    def test_default_construction(self) -> None:
        """DepthGuard uses MAX_DEPTH by default."""
        guard = DepthGuard()

        assert guard.max_depth == MAX_DEPTH
        assert guard.current_depth == 0

    def test_custom_max_depth(self) -> None:
        """DepthGuard accepts custom max_depth."""
        guard = DepthGuard(max_depth=50)

        assert guard.max_depth == 50
        assert guard.current_depth == 0

    def test_max_depth_constant(self) -> None:
        """MAX_DEPTH is set to 100."""
        assert MAX_DEPTH == 100

    def test_post_init_clamps_max_depth(self) -> None:
        """__post_init__ clamps max_depth against recursion limit."""
        limit = sys.getrecursionlimit()
        guard = DepthGuard(max_depth=limit + 1000)

        assert guard.max_depth == limit - 50
        assert guard.max_depth < limit


# ============================================================================
# Context Manager
# ============================================================================


class TestDepthGuardContextManager:
    """Test DepthGuard as context manager."""

    def test_context_manager_increments_depth(self) -> None:
        """Entering context increments depth."""
        guard = DepthGuard()

        assert guard.current_depth == 0

        with guard:
            assert guard.current_depth == 1

    def test_context_manager_decrements_depth(self) -> None:
        """Exiting context decrements depth."""
        guard = DepthGuard()

        with guard:
            pass

        assert guard.current_depth == 0

    def test_context_manager_nested(self) -> None:
        """Nested context managers increment depth correctly."""
        guard = DepthGuard(max_depth=10)

        with guard:
            assert guard.current_depth == 1
            with guard:
                assert guard.current_depth == 2
                with guard:
                    assert guard.current_depth == 3

        assert guard.current_depth == 0

    def test_context_manager_raises_on_exceeded(self) -> None:
        """Context manager raises FrozenFluentError when depth exceeded."""
        guard = DepthGuard(max_depth=3)

        with guard, guard, guard:  # noqa: SIM117
            with pytest.raises(FrozenFluentError) as exc_info:
                with guard:
                    pass

        assert exc_info.value.category == ErrorCategory.RESOLUTION
        assert "3" in str(exc_info.value)

    def test_context_manager_depth_restoration_on_error(self) -> None:
        """Depth is restored even if exception occurs in context."""
        guard = DepthGuard(max_depth=10)
        test_error_msg = "Test error"

        with guard:
            assert guard.current_depth == 1
            try:
                with guard:
                    assert guard.current_depth == 2
                    raise ValueError(test_error_msg)
            except ValueError:
                pass
            assert guard.current_depth == 1

        assert guard.current_depth == 0

    def test_context_manager_returns_self(self) -> None:
        """__enter__ returns self for 'as' binding."""
        guard = DepthGuard()

        with guard as g:
            assert g is guard

    def test_state_not_corrupted_on_enter_failure(self) -> None:
        """current_depth unchanged when __enter__ raises.

        Validates check-before-increment ordering: if __enter__ raises,
        current_depth must not be elevated, since __exit__ is never called.
        """
        guard = DepthGuard(max_depth=2)

        with guard, guard:
            assert guard.current_depth == 2
            with pytest.raises(FrozenFluentError), guard:
                pass
            # current_depth must still be 2, not 3
            assert guard.current_depth == 2

        assert guard.current_depth == 0


# ============================================================================
# Explicit check()
# ============================================================================


class TestCheckMethod:
    """Test check() explicit depth checking method."""

    def test_check_passes_below_limit(self) -> None:
        """check() does not raise when depth < max_depth."""
        guard = DepthGuard(max_depth=10)

        with guard, guard:
            guard.check()  # Should not raise

    def test_check_raises_at_limit(self) -> None:
        """check() raises FrozenFluentError when depth >= max_depth."""
        guard = DepthGuard(max_depth=2)

        with guard, guard, pytest.raises(FrozenFluentError) as exc_info:
            guard.check()

        assert exc_info.value.category == ErrorCategory.RESOLUTION
        assert "2" in str(exc_info.value)

    def test_check_raises_above_limit(self) -> None:
        """check() raises when depth > max_depth via direct attribute set."""
        guard = DepthGuard(max_depth=2)
        guard.current_depth = 5

        with pytest.raises(FrozenFluentError) as exc_info:
            guard.check()
        assert exc_info.value.category == ErrorCategory.RESOLUTION


# ============================================================================
# FrozenFluentError from DepthGuard
# ============================================================================


class TestDepthGuardError:
    """Test FrozenFluentError raised by DepthGuard."""

    def test_error_is_frozen_fluent_error(self) -> None:
        """DepthGuard raises FrozenFluentError with RESOLUTION category."""
        guard = DepthGuard(max_depth=1)

        with guard, pytest.raises(FrozenFluentError) as exc_info, guard:
            pass

        assert exc_info.value.category == ErrorCategory.RESOLUTION
        assert isinstance(exc_info.value, Exception)

    def test_error_carries_diagnostic(self) -> None:
        """DepthGuard error carries diagnostic template data."""
        diagnostic = ErrorTemplate.expression_depth_exceeded(50)
        error = FrozenFluentError(
            str(diagnostic),
            ErrorCategory.RESOLUTION,
            diagnostic=diagnostic,
        )

        assert "50" in str(error)

    def test_error_includes_max_depth_value(self) -> None:
        """Error message includes the configured max_depth."""
        guard = DepthGuard(max_depth=2)

        with guard, guard, pytest.raises(FrozenFluentError, match="2"), guard:
            pass


# ---------------------------------------------------------------------------
# depth_clamp
# ---------------------------------------------------------------------------


class TestDepthClamp:
    """Test depth_clamp() utility function."""

    def test_returns_value_within_limit(self) -> None:
        """depth_clamp returns requested depth when within limit."""
        result = depth_clamp(50)
        assert result == 50

    def test_clamps_excessive_depth(self) -> None:
        """depth_clamp clamps depth exceeding recursion limit."""
        limit = sys.getrecursionlimit()
        result = depth_clamp(limit + 1000)
        assert result == limit - 50

    def test_custom_reserve_frames(self) -> None:
        """depth_clamp respects custom reserve_frames parameter."""
        limit = sys.getrecursionlimit()
        result = depth_clamp(limit, reserve_frames=100)
        assert result == limit - 100

    def test_logs_warning_on_clamp(self, caplog: pytest.LogCaptureFixture) -> None:
        """depth_clamp logs warning when clamping occurs."""
        limit = sys.getrecursionlimit()
        with caplog.at_level(logging.WARNING):
            depth_clamp(limit + 500)

        assert any("Clamping" in record.message for record in caplog.records)

    def test_no_warning_within_limit(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """depth_clamp does not log when within limit."""
        with caplog.at_level(logging.WARNING):
            depth_clamp(50)

        assert not any(
            "Clamping" in record.message for record in caplog.records
        )


# ============================================================================
# Hypothesis Property-Based Tests
# ============================================================================


@given(max_depth=st.integers(min_value=1, max_value=100))
def test_property_context_manager_enforces_limit(max_depth: int) -> None:
    """Property: context manager enforces max_depth limit exactly.

    For any max_depth in [1, 100]:
    - Nesting max_depth times succeeds
    - Nesting max_depth + 1 times raises FrozenFluentError
    """
    event(f"max_depth={max_depth}")
    guard = DepthGuard(max_depth=max_depth)

    def nest(remaining: int) -> None:
        if remaining == 0:
            return
        with guard:
            nest(remaining - 1)

    nest(max_depth)
    assert guard.current_depth == 0

    with pytest.raises(FrozenFluentError) as exc_info:
        nest(max_depth + 1)
    assert exc_info.value.category == ErrorCategory.RESOLUTION


@given(max_depth=st.integers(min_value=1, max_value=100))
def test_property_depth_zero_after_balanced_contexts(max_depth: int) -> None:
    """Property: current_depth is 0 after all contexts exit.

    For any nesting depth, balanced with-blocks return depth to 0.
    """
    event(f"max_depth={max_depth}")
    guard = DepthGuard(max_depth=max_depth)

    depth = min(max_depth, 50)

    def nest(remaining: int) -> None:
        if remaining == 0:
            return
        with guard:
            nest(remaining - 1)

    nest(depth)
    assert guard.current_depth == 0


@given(
    max_depth=st.integers(min_value=1, max_value=100),
    target_depth=st.integers(min_value=0, max_value=99),
)
def test_property_check_consistent_with_context_manager(
    max_depth: int, target_depth: int,
) -> None:
    """Property: check() and context manager agree on limit enforcement.

    At any depth, check() raises iff entering a with-block would raise.
    """
    target_depth = min(target_depth, max_depth)
    event(f"max_depth={max_depth}")
    at_limit = "at_limit" if target_depth == max_depth else "below"
    event(f"boundary={at_limit}")

    guard = DepthGuard(max_depth=max_depth)
    guard.current_depth = target_depth

    if target_depth >= max_depth:
        with pytest.raises(FrozenFluentError):
            guard.check()
        with pytest.raises(FrozenFluentError), guard:
            pass
    else:
        guard.check()  # Should not raise
        with guard:
            pass  # Should not raise


@given(
    requested=st.integers(min_value=1, max_value=100000),
    reserve=st.integers(min_value=10, max_value=200),
)
@example(requested=50, reserve=50)
@example(requested=99999, reserve=50)
def test_property_depth_clamp_never_exceeds_limit(
    requested: int, reserve: int,
) -> None:
    """Property: depth_clamp never returns a value that would exceed limit.

    For any (requested, reserve), result + reserve <= recursion_limit.
    """
    event(f"requested={'within' if requested < 1000 else 'excessive'}")
    event(f"reserve={reserve}")

    result = depth_clamp(requested, reserve_frames=reserve)
    limit = sys.getrecursionlimit()

    assert result + reserve <= limit
    assert result <= requested


@given(max_depth=st.integers(min_value=2, max_value=50))
@settings(max_examples=200)
def test_property_exception_preserves_depth_invariant(
    max_depth: int,
) -> None:
    """Property: exceptions inside guarded sections preserve depth.

    After an exception within a `with guard:` block, current_depth
    is correctly decremented by __exit__. Requires max_depth >= 2
    for two-level nesting.
    """
    event(f"max_depth={max_depth}")
    guard = DepthGuard(max_depth=max_depth)

    msg = "test"
    with guard:
        try:
            with guard:
                raise RuntimeError(msg)
        except RuntimeError:
            pass
        assert guard.current_depth == 1

    assert guard.current_depth == 0
