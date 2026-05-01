"""Property-based tests for ftllexengine.syntax.serializer module.

Comprehensive test suite achieving 100% coverage using Hypothesis property-based
testing with HypoFuzz semantic coverage events.

Test Properties:
- Roundtrip: parse(serialize(ast)) preserves structure
- Idempotence: serialize(parse(serialize(ast))) == serialize(ast)
- Validation: Invalid ASTs raise SerializationValidationError
- Depth: Nested ASTs respect max_depth limits

Coverage Targets:
- Lines 117-118: SelectExpression with 0 defaults
- Lines 121-125: SelectExpression with >1 defaults
- Branch 238: FunctionReference without arguments
- Branch 429: Junk serialization
- Branch 616: Placeable in pattern
- Branch 749: SelectExpression serialization
- Branch 804: NumberLiteral variant keys

Python 3.13+.
"""

from __future__ import annotations

import typing
from typing import cast

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.enums import CommentType
from ftllexengine.syntax.ast import (
    CallArguments,
    Comment,
    FTLLiteral,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    NamedArgument,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import (
    FluentSerializer,
    SerializationDepthError,
    SerializationValidationError,
    serialize,
)
from ftllexengine.syntax.serializer_lines import (
    _classify_line,
    _escape_text,
    _LineKind,  # Private import for property tests
)
from tests.strategies.ftl import (
    build_invalid_select_multiple_defaults,
    build_invalid_select_no_defaults,
    ftl_comment_nodes,
    ftl_deep_placeables,
    ftl_function_references_no_args,
    ftl_junk_nodes,
    ftl_message_nodes,
    ftl_patterns,
    ftl_placeables,
    ftl_resources,
    ftl_select_expressions,
    ftl_select_expressions_with_number_keys,
    ftl_term_nodes,
)

__all__ = [
    "MAX_DEPTH",
    "CallArguments",
    "Comment",
    "CommentType",
    "FTLLiteral",
    "FluentParserV1",
    "FluentSerializer",
    "FunctionReference",
    "HealthCheck",
    "Identifier",
    "Junk",
    "Message",
    "NamedArgument",
    "Pattern",
    "Placeable",
    "Resource",
    "SelectExpression",
    "SerializationDepthError",
    "SerializationValidationError",
    "StringLiteral",
    "Term",
    "TermReference",
    "TextElement",
    "VariableReference",
    "_LineKind",
    "_classify_line",
    "_escape_text",
    "build_invalid_select_multiple_defaults",
    "build_invalid_select_no_defaults",
    "cast",
    "event",
    "ftl_comment_nodes",
    "ftl_deep_placeables",
    "ftl_function_references_no_args",
    "ftl_junk_nodes",
    "ftl_message_nodes",
    "ftl_patterns",
    "ftl_placeables",
    "ftl_resources",
    "ftl_select_expressions",
    "ftl_select_expressions_with_number_keys",
    "ftl_term_nodes",
    "given",
    "pytest",
    "serialize",
    "settings",
    "st",
    "typing",
]
