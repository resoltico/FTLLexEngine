"""Depth-limit error adapters for higher layers.

Core depth tracking stays independent of diagnostics; higher layers that want
domain-specific ``FrozenFluentError`` instances opt into them through these
builders.
"""

from __future__ import annotations

from ftllexengine.diagnostics.errors import ErrorCategory, FrozenFluentError
from ftllexengine.diagnostics.templates import ErrorTemplate

__all__ = ["resolution_depth_error"]


def resolution_depth_error(max_depth: int) -> FrozenFluentError:
    """Build the canonical resolution-category depth error."""
    diagnostic = ErrorTemplate.depth_exceeded(max_depth)
    return FrozenFluentError(
        str(diagnostic),
        ErrorCategory.RESOLUTION,
        diagnostic=diagnostic,
    )
