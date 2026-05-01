"""Tests for parser pattern and whitespace handling.

Tests whitespace utilities (skip_blank_inline, skip_blank,
is_indented_continuation, skip_multiline_pattern_start) and pattern
parsing (parse_pattern, parse_simple_pattern) including multiline
continuation, blank line handling, text accumulation, variant delimiter
lookahead, and CRLF normalization.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from hypothesis import event, example, given
from hypothesis import strategies as st

from ftllexengine import parse_ftl
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.ast import (
    Message,
    Pattern,
    Placeable,
    SelectExpression,
    Term,
    TextElement,
)
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    parse_message,
    parse_pattern,
    parse_simple_pattern,
    parse_variant,
)
from ftllexengine.syntax.parser.whitespace import (
    is_indented_continuation,
    skip_blank,
    skip_blank_inline,
    skip_multiline_pattern_start,
)

__all__ = [
    "Cursor",
    "FluentBundle",
    "Message",
    "ParseContext",
    "Pattern",
    "Placeable",
    "SelectExpression",
    "Term",
    "TextElement",
    "event",
    "example",
    "given",
    "is_indented_continuation",
    "parse_ftl",
    "parse_message",
    "parse_pattern",
    "parse_simple_pattern",
    "parse_variant",
    "patch",
    "pytest",
    "skip_blank",
    "skip_blank_inline",
    "skip_multiline_pattern_start",
    "st",
]
