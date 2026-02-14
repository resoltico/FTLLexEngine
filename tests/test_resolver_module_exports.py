"""Tests for resolver and resolution_context module export boundaries.

Verifies that:
- FluentValue is not exported from runtime.resolver (must use function_bridge)
- ResolutionContext and GlobalDepthGuard are canonically in resolution_context
- resolver re-exports ResolutionContext and GlobalDepthGuard for compatibility
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
            # Intentional ImportError test - FluentValue removed from resolver exports
            from ftllexengine.runtime.resolver import (
                FluentValue,  # noqa: F401
            )

    def test_fluent_resolver_still_exported_from_resolver(self) -> None:
        """FluentResolver should still be exported from resolver module."""
        from ftllexengine.runtime.resolver import FluentResolver

        assert FluentResolver is not None

    def test_resolution_context_still_exported_from_resolver(self) -> None:
        """ResolutionContext re-exported from resolver for compatibility."""
        from ftllexengine.runtime.resolver import ResolutionContext

        assert ResolutionContext is not None

    def test_global_depth_guard_still_exported_from_resolver(self) -> None:
        """GlobalDepthGuard re-exported from resolver for compatibility."""
        from ftllexengine.runtime.resolver import GlobalDepthGuard

        assert GlobalDepthGuard is not None


class TestResolutionContextModuleExports:
    """Test resolution_context canonical exports."""

    def test_resolution_context_canonical_import(self) -> None:
        """ResolutionContext canonical location is resolution_context module."""
        from ftllexengine.runtime.resolution_context import ResolutionContext

        assert ResolutionContext is not None

    def test_global_depth_guard_canonical_import(self) -> None:
        """GlobalDepthGuard canonical location is resolution_context module."""
        from ftllexengine.runtime.resolution_context import GlobalDepthGuard

        assert GlobalDepthGuard is not None

    def test_canonical_and_reexport_are_same_class(self) -> None:
        """Canonical and re-exported classes are identical objects."""
        from ftllexengine.runtime.resolution_context import (
            GlobalDepthGuard as CanonicalGuard,
        )
        from ftllexengine.runtime.resolution_context import (
            ResolutionContext as CanonicalCtx,
        )
        from ftllexengine.runtime.resolver import (
            GlobalDepthGuard as ReexportGuard,
        )
        from ftllexengine.runtime.resolver import (
            ResolutionContext as ReexportCtx,
        )

        assert CanonicalCtx is ReexportCtx
        assert CanonicalGuard is ReexportGuard
