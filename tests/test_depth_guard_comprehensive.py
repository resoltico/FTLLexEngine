"""Comprehensive tests for runtime/depth_guard.py achieving 100% coverage.

Tests DepthGuard context manager and all depth tracking methods
with Hypothesis for property-based testing.

Python 3.13+.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.core.depth_guard import DepthGuard
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.diagnostics.templates import ErrorTemplate


class TestDepthGuardConstruction:
    """Test DepthGuard construction and defaults."""

    def test_default_construction(self):
        """DepthGuard uses MAX_DEPTH by default."""
        guard = DepthGuard()

        assert guard.max_depth == MAX_DEPTH
        assert guard.current_depth == 0

    def test_custom_max_depth(self):
        """DepthGuard accepts custom max_depth."""
        guard = DepthGuard(max_depth=50)

        assert guard.max_depth == 50
        assert guard.current_depth == 0

    def test_max_expression_depth_constant(self):
        """MAX_DEPTH is set to 100."""
        assert MAX_DEPTH == 100


class TestDepthGuardContextManager:
    """Test DepthGuard as context manager."""

    def test_context_manager_increments_depth(self):
        """Entering context increments depth."""
        guard = DepthGuard()

        assert guard.current_depth == 0

        with guard:
            assert guard.current_depth == 1

    def test_context_manager_decrements_depth(self):
        """Exiting context decrements depth."""
        guard = DepthGuard()

        with guard:
            pass

        assert guard.current_depth == 0

    def test_context_manager_nested(self):
        """Nested context managers increment depth correctly."""
        guard = DepthGuard(max_depth=10)

        with guard:
            assert guard.current_depth == 1
            with guard:
                assert guard.current_depth == 2
                with guard:
                    assert guard.current_depth == 3

        assert guard.current_depth == 0

    def test_context_manager_raises_on_exceeded(self):
        """Context manager raises FrozenFluentError when depth exceeded."""
        guard = DepthGuard(max_depth=3)

        with guard, guard, guard:  # noqa: SIM117
            # Depth is now 3, next entry should raise
            with pytest.raises(FrozenFluentError) as exc_info:
                with guard:
                    pass

        # Verify error details
        assert exc_info.value.category == ErrorCategory.RESOLUTION
        assert "Maximum expression nesting depth (3) exceeded" in str(exc_info.value)

    def test_context_manager_depth_restoration_on_error(self):
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
            # Depth should be restored to 1
            assert guard.current_depth == 1

        assert guard.current_depth == 0

    def test_context_manager_returns_self(self):
        """__enter__ returns self for 'as' binding."""
        guard = DepthGuard()

        with guard as g:
            assert g is guard


class TestDepthProperty:
    """Test depth property (alias for current_depth)."""

    def test_depth_property_initial(self):
        """depth property returns 0 initially."""
        guard = DepthGuard()

        assert guard.depth == 0

    def test_depth_property_after_increment(self):
        """depth property reflects current_depth."""
        guard = DepthGuard()

        with guard:
            assert guard.depth == 1
            assert guard.depth == guard.current_depth

    def test_depth_property_is_readonly(self):
        """depth is a read-only property (no setter)."""
        guard = DepthGuard()

        # Attempting to set should fail
        with pytest.raises(AttributeError):
            guard.depth = 5  # type: ignore[misc]


class TestIsExceeded:
    """Test is_exceeded() method."""

    def test_is_exceeded_false_initially(self):
        """is_exceeded returns False when depth < max_depth."""
        guard = DepthGuard(max_depth=10)

        assert not guard.is_exceeded()

    def test_is_exceeded_false_below_limit(self):
        """is_exceeded returns False when depth < max_depth."""
        guard = DepthGuard(max_depth=10)

        with guard, guard:
            assert guard.current_depth == 2
            assert not guard.is_exceeded()

    def test_is_exceeded_true_at_limit(self):
        """is_exceeded returns True when depth == max_depth."""
        guard = DepthGuard(max_depth=3)

        with guard, guard, guard:
            assert guard.current_depth == 3
            assert guard.is_exceeded()

    def test_is_exceeded_true_above_limit_manual(self):
        """is_exceeded returns True when manually incremented past limit."""
        guard = DepthGuard(max_depth=2)

        guard.increment()
        guard.increment()
        assert guard.current_depth == 2
        assert guard.is_exceeded()


class TestCheckMethod:
    """Test check() explicit depth checking method."""

    def test_check_passes_below_limit(self):
        """check() does not raise when depth < max_depth."""
        guard = DepthGuard(max_depth=10)

        guard.increment()
        guard.increment()
        guard.check()  # Should not raise
        assert guard.current_depth == 2  # Verify depth tracked correctly

    def test_check_raises_at_limit(self):
        """check() raises FrozenFluentError when depth >= max_depth."""
        guard = DepthGuard(max_depth=2)

        guard.increment()
        guard.increment()

        with pytest.raises(FrozenFluentError) as exc_info:
            guard.check()

        assert exc_info.value.category == ErrorCategory.RESOLUTION
        assert "Maximum expression nesting depth (2) exceeded" in str(exc_info.value)

    def test_check_raises_above_limit(self):
        """check() raises when depth > max_depth."""
        guard = DepthGuard(max_depth=2)

        guard.current_depth = 5  # Bypass normal increment

        with pytest.raises(FrozenFluentError) as exc_info:
            guard.check()
        assert exc_info.value.category == ErrorCategory.RESOLUTION


class TestManualIncrementDecrement:
    """Test manual increment() and decrement() methods."""

    def test_increment_increases_depth(self):
        """increment() increases current_depth by 1."""
        guard = DepthGuard()

        guard.increment()
        assert guard.current_depth == 1

        guard.increment()
        assert guard.current_depth == 2

    def test_increment_multiple_times(self):
        """increment() can be called multiple times."""
        guard = DepthGuard()

        for i in range(1, 6):
            guard.increment()
            assert guard.current_depth == i

    def test_decrement_decreases_depth(self):
        """decrement() decreases current_depth by 1."""
        guard = DepthGuard()

        guard.increment()
        guard.increment()
        guard.increment()
        assert guard.current_depth == 3

        guard.decrement()
        assert guard.current_depth == 2

    def test_decrement_guards_against_negative(self):
        """decrement() does not go below 0."""
        guard = DepthGuard()

        guard.decrement()
        assert guard.current_depth == 0

        guard.decrement()
        assert guard.current_depth == 0

    def test_increment_decrement_symmetry(self):
        """Paired increment/decrement operations cancel out."""
        guard = DepthGuard()

        for _ in range(10):
            guard.increment()

        for _ in range(10):
            guard.decrement()

        assert guard.current_depth == 0


class TestResetMethod:
    """Test reset() method."""

    def test_reset_sets_depth_to_zero(self):
        """reset() sets current_depth to 0."""
        guard = DepthGuard()

        guard.increment()
        guard.increment()
        guard.increment()
        assert guard.current_depth == 3

        guard.reset()
        assert guard.current_depth == 0

    def test_reset_from_zero(self):
        """reset() on zero depth has no effect."""
        guard = DepthGuard()

        guard.reset()
        assert guard.current_depth == 0

    def test_reset_after_context_manager(self):
        """reset() can be used after context manager exits."""
        guard = DepthGuard()

        with guard, guard:
            pass

        # Depth should be 0 after context exits
        assert guard.current_depth == 0

        # Manual increment then reset
        guard.increment()
        guard.increment()
        guard.reset()
        assert guard.current_depth == 0


class TestFrozenFluentErrorFromDepthGuard:
    """Test FrozenFluentError raised by DepthGuard."""

    def test_depth_guard_error_is_frozen_fluent_error(self):
        """DepthGuard raises FrozenFluentError with RESOLUTION category."""
        guard = DepthGuard(max_depth=1)

        with guard, pytest.raises(FrozenFluentError) as exc_info, guard:
            pass

        assert exc_info.value.category == ErrorCategory.RESOLUTION
        assert isinstance(exc_info.value, Exception)

    def test_depth_guard_error_message(self):
        """DepthGuard error carries diagnostic message."""
        diagnostic = ErrorTemplate.expression_depth_exceeded(50)
        error = FrozenFluentError(str(diagnostic), ErrorCategory.RESOLUTION, diagnostic=diagnostic)

        assert "50" in str(error)


# Hypothesis property-based tests


@given(max_depth=st.integers(min_value=1, max_value=100))
def test_property_context_manager_respects_max_depth(max_depth: int) -> None:
    """Property: Context manager enforces max_depth limit."""
    guard = DepthGuard(max_depth=max_depth)

    # Should be able to nest max_depth times
    def nest(remaining: int) -> None:
        if remaining == 0:
            return
        with guard:
            nest(remaining - 1)

    # Nesting max_depth times should succeed
    nest(max_depth)
    assert guard.current_depth == 0  # All contexts exited

    # Nesting max_depth + 1 times should raise
    with pytest.raises(FrozenFluentError) as exc_info:
        nest(max_depth + 1)
    assert exc_info.value.category == ErrorCategory.RESOLUTION


@given(
    increments=st.integers(min_value=0, max_value=100),
    decrements=st.integers(min_value=0, max_value=100),
)
def test_property_manual_depth_tracking(increments: int, decrements: int) -> None:
    """Property: Manual increment/decrement tracking is accurate."""
    guard = DepthGuard(max_depth=200)

    for _ in range(increments):
        guard.increment()

    for _ in range(decrements):
        guard.decrement()

    # Depth should be max(0, increments - decrements)
    expected_depth = max(0, increments - decrements)
    assert guard.current_depth == expected_depth


@given(max_depth=st.integers(min_value=1, max_value=100))
def test_property_reset_always_returns_to_zero(max_depth: int) -> None:
    """Property: reset() always returns depth to 0 regardless of current depth."""
    guard = DepthGuard(max_depth=max_depth)

    # Increment to arbitrary depth (not exceeding max)
    for _ in range(min(max_depth - 1, 50)):
        guard.increment()

    guard.reset()
    assert guard.current_depth == 0


@given(depth=st.integers(min_value=0, max_value=100))
def test_property_depth_property_mirrors_current_depth(depth: int) -> None:
    """Property: depth property always equals current_depth."""
    guard = DepthGuard(max_depth=200)

    guard.current_depth = depth

    assert guard.depth == guard.current_depth
    assert guard.depth == depth
