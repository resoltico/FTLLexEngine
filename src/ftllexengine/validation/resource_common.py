"""Shared helpers for resource validation passes."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ftllexengine.syntax import Junk, Message, Term
    from ftllexengine.syntax.cursor import LineOffsetCache

__all__ = ["get_entry_position"]


def get_entry_position(
    entry: Message | Term | Junk,
    line_cache: LineOffsetCache,
) -> tuple[int | None, int | None]:
    """Return the line and column for a spanned resource entry when available."""
    if entry.span:
        return line_cache.get_line_col(entry.span.start)
    return None, None
