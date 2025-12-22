"""Validation utilities for FTL resources.

This module provides standalone validation functions for FTL resources,
separated from FluentBundle for better modularity and testability.

Python 3.13+.
"""

from ftllexengine.validation.resource import (
    validate_resource,
)

__all__ = [
    "validate_resource",
]
