"""Tests for FTL-MODERN-001: Breaking changes in v0.71.0 - FluentValue re-export removal.

Verifies that FluentValue is no longer exported from runtime.resolver module
and must be imported from runtime.function_bridge instead.
"""

import pytest


class TestResolverBreakingChangesV071:
    """Test breaking changes for resolver module in v0.71.0."""

    def test_fluent_value_available_from_function_bridge(self) -> None:
        """FluentValue should be available from function_bridge module."""
        from ftllexengine.runtime.function_bridge import FluentValue  # noqa: PLC0415

        # If import succeeds, test passes
        assert FluentValue is not None

    def test_importing_fluent_value_from_resolver_fails(self) -> None:
        """FluentValue should not be importable from resolver module."""
        # This tests the BREAKING CHANGE: FluentValue removed from resolver exports
        with pytest.raises(ImportError, match="cannot import name 'FluentValue'"):
            # pylint: disable=unused-import
            from ftllexengine.runtime.resolver import (  # noqa: PLC0415
                FluentValue,  # noqa: F401
            )

    def test_fluent_resolver_still_exported_from_resolver(self) -> None:
        """FluentResolver should still be exported from resolver module."""
        from ftllexengine.runtime.resolver import FluentResolver  # noqa: PLC0415

        assert FluentResolver is not None

    def test_resolution_context_still_exported_from_resolver(self) -> None:
        """ResolutionContext should still be exported from resolver module."""
        from ftllexengine.runtime.resolver import ResolutionContext  # noqa: PLC0415

        assert ResolutionContext is not None
