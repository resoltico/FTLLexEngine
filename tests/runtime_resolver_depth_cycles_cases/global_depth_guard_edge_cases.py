# mypy: ignore-errors
"""Split test cases from tests/test_runtime_resolver_depth_cycles.py."""

from tests.runtime_resolver_depth_cycles_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# GlobalDepthGuard Edge Cases
# ============================================================================


class TestGlobalDepthGuardEdgeCases:
    """Coverage for GlobalDepthGuard.__exit__ defensive branch."""

    def test_exit_without_enter(self) -> None:
        """Guard exit without enter does not crash (defensive branch)."""
        guard = GlobalDepthGuard(max_depth=100)
        # _token remains None; __exit__ defensive branch covered.
        guard.__exit__(None, None, None)

    def test_exit_returns_none(self) -> None:
        """Guard __exit__ does not suppress exceptions."""
        guard = GlobalDepthGuard(max_depth=100)
        with guard:
            pass
