"""Shared validation helpers for FTL syntax validation.

Provides reusable validation logic to avoid duplication between serializer
and validator modules.

Python 3.13+. Zero external dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ftllexengine.syntax.ast import SelectExpression

__all__ = ["count_default_variants"]


def count_default_variants(select: SelectExpression) -> int:
    """Count the number of default variants in a select expression.

    Per Fluent specification, select expressions must have exactly one
    default variant (marked with asterisk: *[key]).

    Args:
        select: Select expression to validate

    Returns:
        Number of default variants (should be exactly 1 for valid FTL)

    Example:
        >>> expr = SelectExpression(...)  # doctest: +SKIP
        >>> count = count_default_variants(expr)  # doctest: +SKIP
        >>> if count != 1:  # doctest: +SKIP
        ...     raise ValidationError(f"Expected 1 default, found {count}")
    """
    return sum(1 for v in select.variants if v.default)
