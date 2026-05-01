"""Tests for parser expression and placeable handling.

Tests expression parsing functions: parse_variable_reference,
parse_variant_key, parse_variant, parse_select_expression,
parse_argument_expression, parse_call_arguments, parse_function_reference,
parse_term_reference, parse_inline_expression, parse_placeable, and
associated helpers (_parse_inline_hyphen, _parse_inline_identifier,
_parse_inline_number_literal, _parse_inline_string_literal,
_parse_message_attribute, _is_variant_marker, _is_valid_variant_key_char,
_trim_pattern_blank_lines, validate_message_content).
"""

from __future__ import annotations

from typing import cast

from hypothesis import event, example, given
from hypothesis import strategies as st

from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.ast import (
    Attribute,
    Identifier,
    Message,
    MessageReference,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
    StringLiteral,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.parser.rules import _MAX_LOOKAHEAD_CHARS as MAX_LOOKAHEAD_CHARS
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    _is_valid_variant_key_char,
    _is_variant_marker,
    _parse_inline_hyphen,
    _parse_inline_identifier,
    _parse_inline_number_literal,
    _parse_inline_string_literal,
    _parse_message_attribute,
    _trim_pattern_blank_lines,
    parse_argument_expression,
    parse_call_arguments,
    parse_function_reference,
    parse_inline_expression,
    parse_message,
    parse_pattern,
    parse_placeable,
    parse_select_expression,
    parse_simple_pattern,
    parse_term_reference,
    parse_variable_reference,
    parse_variant,
    parse_variant_key,
    validate_message_content,
)

__all__ = [
    "MAX_LOOKAHEAD_CHARS",
    "Attribute",
    "Cursor",
    "FluentBundle",
    "FluentParserV1",
    "Identifier",
    "Message",
    "MessageReference",
    "NumberLiteral",
    "ParseContext",
    "Pattern",
    "Placeable",
    "SelectExpression",
    "StringLiteral",
    "TermReference",
    "TextElement",
    "VariableReference",
    "Variant",
    "_is_valid_variant_key_char",
    "_is_variant_marker",
    "_parse_inline_hyphen",
    "_parse_inline_identifier",
    "_parse_inline_number_literal",
    "_parse_inline_string_literal",
    "_parse_message_attribute",
    "_trim_pattern_blank_lines",
    "cast",
    "event",
    "example",
    "given",
    "parse_argument_expression",
    "parse_call_arguments",
    "parse_function_reference",
    "parse_inline_expression",
    "parse_message",
    "parse_pattern",
    "parse_placeable",
    "parse_select_expression",
    "parse_simple_pattern",
    "parse_term_reference",
    "parse_variable_reference",
    "parse_variant",
    "parse_variant_key",
    "st",
    "validate_message_content",
]
