"""Tests for resolver module export boundaries.

Verifies that FluentValue is not exported from runtime.resolver module
and must be imported from runtime.function_bridge instead.
"""

import pytest


class TestResolverModuleExports:
    """Test resolver module export boundaries."""

    def test_fluent_value_available_from_function_bridge(self) -> None:
        """FluentValue should be available from function_bridge module."""
        from ftllexengine.runtime.function_bridge import FluentValue

        # If import succeeds, test passes
        assert FluentValue is not None

    def test_importing_fluent_value_from_resolver_fails(self) -> None:
        """FluentValue should not be importable from resolver module."""
        # This tests the BREAKING CHANGE: FluentValue removed from resolver exports
        with pytest.raises(ImportError, match="cannot import name 'FluentValue'"):
            # pylint: disable=unused-import
            from ftllexengine.runtime.resolver import (  # type: ignore[attr-defined]
                FluentValue,  # noqa: F401
            )

    def test_fluent_resolver_still_exported_from_resolver(self) -> None:
        """FluentResolver should still be exported from resolver module."""
        from ftllexengine.runtime.resolver import FluentResolver

        assert FluentResolver is not None

    def test_resolution_context_still_exported_from_resolver(self) -> None:
        """ResolutionContext should still be exported from resolver module."""
        from ftllexengine.runtime.resolver import ResolutionContext

        assert ResolutionContext is not None
