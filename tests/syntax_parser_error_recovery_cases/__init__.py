"""Error recovery, defensive code paths, and edge-case coverage for parser rules.

Consolidated from 12 per-metric test files into a single semantic unit.
Covers: error paths, defensive/unreachable branches (via mocking), FluentParserV1
integration for malformed input, and property-based edge-case tests.
"""

from __future__ import annotations

import logging
import sys
from unittest.mock import patch

from ftllexengine.syntax.ast import (
    Attribute,
    Identifier,
    Junk,
    Message,
    MessageReference,
    NumberLiteral,
    Placeable,
    StringLiteral,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.cursor import Cursor, ParseError, ParseResult
from ftllexengine.syntax.parser.core import FluentParserV1
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    _parse_inline_hyphen,
    _parse_inline_identifier,
    parse_argument_expression,
    parse_attribute,
    parse_call_arguments,
    parse_function_reference,
    parse_inline_expression,
    parse_message,
    parse_pattern,
    parse_placeable,
    parse_select_expression,
    parse_simple_pattern,
    parse_term,
    parse_term_reference,
    parse_variant,
    parse_variant_key,
)

__all__ = [
    "Attribute",
    "Cursor",
    "FluentParserV1",
    "Identifier",
    "Junk",
    "Message",
    "MessageReference",
    "NumberLiteral",
    "ParseContext",
    "ParseError",
    "ParseResult",
    "Placeable",
    "StringLiteral",
    "TextElement",
    "VariableReference",
    "_parse_inline_hyphen",
    "_parse_inline_identifier",
    "logging",
    "parse_argument_expression",
    "parse_attribute",
    "parse_call_arguments",
    "parse_function_reference",
    "parse_inline_expression",
    "parse_message",
    "parse_pattern",
    "parse_placeable",
    "parse_select_expression",
    "parse_simple_pattern",
    "parse_term",
    "parse_term_reference",
    "parse_variant",
    "parse_variant_key",
    "patch",
    "sys",
]
