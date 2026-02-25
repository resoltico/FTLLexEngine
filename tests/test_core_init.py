"""Tests for ftllexengine.core package __getattr__ lazy-loading.

Covers lines 85-86: AttributeError raised when a non-lazy attribute is
accessed on the core module (i.e., name not in _LAZY_DEPTH_GUARD).
"""

from __future__ import annotations

import pytest

import ftllexengine.core as core_module


class TestCoreModuleGetattr:
    """Tests for core/__init__.py lazy-loading via __getattr__."""

    def test_unknown_attribute_raises_attribute_error(self) -> None:
        """Accessing a non-existent attribute on ftllexengine.core raises AttributeError.

        Covers lines 85-86: the branch where name is not in _LAZY_DEPTH_GUARD.
        The module __getattr__ falls through to raise AttributeError with
        the standard module-attribute error message.
        """
        with pytest.raises(AttributeError, match="has no attribute"):
            _ = core_module.nonexistent_attribute

    def test_depth_guard_lazy_loads_successfully(self) -> None:
        """DepthGuard is lazily loaded from ftllexengine.core without error.

        Covers lines 77-84: the lazy-load branch for DepthGuard.
        """
        assert core_module.DepthGuard is not None

    def test_depth_clamp_lazy_loads_successfully(self) -> None:
        """depth_clamp is lazily loaded from ftllexengine.core without error.

        Covers lines 77-84: the lazy-load branch for depth_clamp.
        """
        assert callable(core_module.depth_clamp)
