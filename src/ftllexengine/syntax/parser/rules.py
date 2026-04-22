"""Composable Fluent grammar surface assembled from focused parser modules."""

from __future__ import annotations

from ftllexengine.syntax.parser.context import ParseContext
from ftllexengine.syntax.parser.entries import (
    parse_attribute,
    parse_comment,
    parse_message,
    parse_message_attributes,
    parse_message_header,
    parse_term,
    validate_message_content,
)
from ftllexengine.syntax.parser.expressions import (
    _parse_inline_hyphen,
    _parse_inline_identifier,
    _parse_inline_number_literal,
    _parse_inline_string_literal,
    _parse_message_attribute,
    parse_argument_expression,
    parse_call_arguments,
    parse_function_reference,
    parse_inline_expression,
    parse_placeable,
    parse_select_expression,
    parse_term_reference,
    parse_variable_reference,
    parse_variant,
    parse_variant_key,
)
from ftllexengine.syntax.parser.patterns import (
    _MAX_LOOKAHEAD_CHARS,
    _is_valid_variant_key_char,
    _is_variant_marker,
    _trim_pattern_blank_lines,
    parse_pattern,
    parse_simple_pattern,
)
from ftllexengine.syntax.parser.primitives import parse_identifier, parse_number

__all__ = [
    "_MAX_LOOKAHEAD_CHARS",
    "ParseContext",
    "_is_valid_variant_key_char",
    "_is_variant_marker",
    "_parse_inline_hyphen",
    "_parse_inline_identifier",
    "_parse_inline_number_literal",
    "_parse_inline_string_literal",
    "_parse_message_attribute",
    "_trim_pattern_blank_lines",
    "parse_argument_expression",
    "parse_attribute",
    "parse_call_arguments",
    "parse_comment",
    "parse_function_reference",
    "parse_identifier",
    "parse_inline_expression",
    "parse_message",
    "parse_message_attributes",
    "parse_message_header",
    "parse_number",
    "parse_pattern",
    "parse_placeable",
    "parse_select_expression",
    "parse_simple_pattern",
    "parse_term",
    "parse_term_reference",
    "parse_variable_reference",
    "parse_variant",
    "parse_variant_key",
    "validate_message_content",
]
