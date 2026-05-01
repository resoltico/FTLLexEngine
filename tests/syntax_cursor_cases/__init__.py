"""Tests for syntax.cursor: Cursor, ParseError, ParseResult, LineOffsetCache.

Validates the immutable cursor pattern for type-safe parsing, line/column
computation, and the LineOffsetCache binary-search infrastructure.
"""

from __future__ import annotations

import pytest

from ftllexengine.syntax.cursor import Cursor, LineOffsetCache, ParseError, ParseResult

__all__ = [
    "Cursor",
    "LineOffsetCache",
    "ParseError",
    "ParseResult",
    "pytest",
]
