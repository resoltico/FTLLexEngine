"""Tests for ftllexengine.core package re-exports."""

from __future__ import annotations

import pytest

import ftllexengine.core as core_module


class TestCoreModuleExports:
    """Tests for core/__init__.py stable re-exports."""

    def test_unknown_attribute_raises_attribute_error(self) -> None:
        """Accessing a non-existent attribute on ftllexengine.core raises AttributeError.

        Unknown names should still raise the standard module-attribute error.
        """
        missing_name = "nonexistent_attribute"
        with pytest.raises(AttributeError, match="has no attribute"):
            _ = getattr(core_module, missing_name)

    def test_depth_guard_is_reexported(self) -> None:
        """DepthGuard is re-exported from ftllexengine.core."""
        assert core_module.DepthGuard is not None

    def test_depth_clamp_is_reexported(self) -> None:
        """depth_clamp is re-exported from ftllexengine.core."""
        assert callable(core_module.depth_clamp)
