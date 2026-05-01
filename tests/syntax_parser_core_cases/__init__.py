"""Core parser tests: blank line detection, comment merging, DoS protection, error recovery.

Tests for ``ftllexengine.syntax.parser.core``:

- ``_has_blank_line_between``: Region-based newline detection for comment merging
- ``_CommentAccumulator``: Span handling and content joining for adjacent comments
- ``FluentParserV1``: Comment merging, term/message/junk parsing, DoS limits,
  nesting depth clamping, source size validation, error recovery,
  parse_stream incremental entry parsing
"""

from __future__ import annotations

import logging
import sys

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.constants import MAX_SOURCE_SIZE
from ftllexengine.diagnostics import DiagnosticCode
from ftllexengine.enums import CommentType
from ftllexengine.syntax.ast import Comment, Junk, Message, Span, Term
from ftllexengine.syntax.parser.core import (
    FluentParserV1,
    _CommentAccumulator,
    _has_blank_line_between,
)

__all__ = [
    "MAX_SOURCE_SIZE",
    "Comment",
    "CommentType",
    "DiagnosticCode",
    "FluentParserV1",
    "Junk",
    "Message",
    "Span",
    "Term",
    "_CommentAccumulator",
    "_has_blank_line_between",
    "event",
    "given",
    "logging",
    "pytest",
    "st",
    "sys",
]
