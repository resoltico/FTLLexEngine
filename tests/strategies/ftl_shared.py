"""Shared imports and constants for split FTL strategies."""

from __future__ import annotations

import string
from decimal import Decimal

from hypothesis import event
from hypothesis import strategies as st
from hypothesis.strategies import composite

from ftllexengine.enums import CommentType
from ftllexengine.runtime.function_bridge import FluentNumber
from ftllexengine.syntax.ast import (
    Attribute,
    CallArguments,
    Comment,
    Expression,
    FunctionReference,
    Identifier,
    InlineExpression,
    Junk,
    Message,
    MessageReference,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)

FTL_IDENTIFIER_FIRST_CHARS: str = string.ascii_letters
FTL_IDENTIFIER_REST_CHARS: str = string.ascii_letters + string.digits + "-_"
IDENTIFIER_PARTS = ("foo", "bar", "baz", "value", "count", "name", "id", "key")
FTL_SAFE_CHARS = string.ascii_letters + string.digits + " .,!?'-"
UNICODE_CHARS = (
    "\u4e16\u754c"
    "\u0414\u043e\u0431\u0440\u043e"
    "\u3053\u3093\u306b\u3061\u306f"
    "\u00e9\u00e0\u00fc\u00f1"
    "\u2019\u2018\u201c\u201d"
)

__all__ = [
    "FTL_IDENTIFIER_FIRST_CHARS", "FTL_IDENTIFIER_REST_CHARS", "FTL_SAFE_CHARS",
    "IDENTIFIER_PARTS", "UNICODE_CHARS", "Attribute", "CallArguments", "Comment", "CommentType",
    "Decimal", "Expression", "FluentNumber", "FunctionReference", "Identifier",
    "InlineExpression", "Junk", "Message", "MessageReference", "NamedArgument", "NumberLiteral",
    "Pattern", "Placeable", "Resource", "SelectExpression", "StringLiteral", "Term",
    "TermReference", "TextElement", "VariableReference", "Variant", "composite", "event", "st",
    "string",
]
