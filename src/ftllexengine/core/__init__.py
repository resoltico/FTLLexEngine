"""Core utilities shared across syntax, parsing, and runtime layers.

This package provides foundational utilities that all higher layers depend on.
By isolating these utilities here, we maintain a clean dependency graph:

    core <- syntax <- parsing <- runtime

Exports:
    DepthGuard: Context manager for recursion depth limiting
    FluentNumber: Formatted number preserving numeric identity and precision
    FluentValue: Union of all Fluent-compatible value types
    depth_clamp: Clamp depth values against Python recursion limits
    make_fluent_number: Public helper for manual FluentNumber construction
    require_date: Validate that a boundary value is a date (not datetime)
    require_datetime: Validate that a boundary value is a datetime
    require_fluent_number: Validate that a boundary value is a FluentNumber
    require_positive_int: Validate that a boundary value is a positive integer (internal)

Python 3.13+. No external dependencies.
"""

from .depth_guard import DepthGuard, depth_clamp
from .validators import (
    require_date,
    require_datetime,
    require_fluent_number,
    require_positive_int,
)
from .value_types import FluentNumber, FluentValue, make_fluent_number

__all__ = [
    "DepthGuard",
    "FluentNumber",
    "FluentValue",
    "depth_clamp",
    "make_fluent_number",
    "require_date",
    "require_datetime",
    "require_fluent_number",
    "require_positive_int",
]
