"""Core utilities shared across syntax and runtime layers.

This package provides foundational utilities that both the syntax layer
(parsing, serialization) and runtime layer (resolution, formatting) depend on.
By isolating these utilities here, we maintain a clean dependency graph:

    core <- syntax <- runtime

Exports:
    DepthGuard: Context manager for recursion depth limiting
    depth_clamp: Utility function for clamping depth values against recursion limit

Python 3.13+.
"""

from .depth_guard import DepthGuard, depth_clamp

__all__ = [
    "DepthGuard",
    "depth_clamp",
]
