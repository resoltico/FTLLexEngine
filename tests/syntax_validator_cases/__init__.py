"""Tests for syntax.validator: SemanticValidator, validate(), semantic correctness per spec."""

from __future__ import annotations

from decimal import Decimal

import pytest

from ftllexengine import FluentBundle
from ftllexengine.core.depth_guard import DepthGuard
from ftllexengine.diagnostics import ValidationResult
from ftllexengine.diagnostics.codes import DiagnosticCode
from ftllexengine.enums import CommentType
from ftllexengine.introspection import FunctionCallInfo, introspect_message
from ftllexengine.syntax.ast import (
    Annotation,
    Attribute,
    CallArguments,
    Comment,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    Span,
    Term,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.validator import (
    _VALIDATION_MESSAGES,
    SemanticValidator,
    validate,
)

__all__ = [
    "_VALIDATION_MESSAGES", "Annotation", "Attribute", "CallArguments", "Comment",
    "CommentType", "Decimal", "DepthGuard", "DiagnosticCode", "FluentBundle",
    "FluentParserV1", "FunctionCallInfo", "FunctionReference", "Identifier", "Junk",
    "Message", "NamedArgument", "NumberLiteral", "Pattern", "Placeable", "Resource",
    "SelectExpression", "SemanticValidator", "Span", "Term", "TermReference",
    "TextElement", "ValidationResult", "VariableReference", "Variant",
    "introspect_message", "pytest", "validate",
]
