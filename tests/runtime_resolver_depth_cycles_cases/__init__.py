"""Resolver depth limiting and cycle detection tests.

Consolidates:
- test_resolver_cycles.py (direct/indirect/deep cycles, cycle detection properties)
- test_resolver_depth_limit.py (MAX_DEPTH enforcement, attribute chains)
- test_resolver_depth_guard_and_variants.py (guard edge cases, multi-placeables,
  malformed NumberLiteral, fallback depth protection)
- test_resolver_expression_depth.py (SelectExpression depth, Placeable depth, mixed)
- test_resolver_expression_depth_and_select.py (ResolutionContext expression depth)
- test_resolver_expansion_budget.py (expansion budget DoS protection)
"""

from __future__ import annotations

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.constants import FALLBACK_INVALID, MAX_DEPTH
from ftllexengine.diagnostics import DiagnosticCode, ErrorCategory, FrozenFluentError
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.resolution_context import GlobalDepthGuard, ResolutionContext
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.syntax import (
    CallArguments,
    FunctionReference,
    Identifier,
    Message,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
    StringLiteral,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.ast import InlineExpression

__all__ = [
    "FALLBACK_INVALID",
    "MAX_DEPTH",
    "CallArguments",
    "DiagnosticCode",
    "ErrorCategory",
    "FluentBundle",
    "FluentResolver",
    "FrozenFluentError",
    "FunctionReference",
    "FunctionRegistry",
    "GlobalDepthGuard",
    "Identifier",
    "InlineExpression",
    "Message",
    "NumberLiteral",
    "Pattern",
    "Placeable",
    "ResolutionContext",
    "SelectExpression",
    "StringLiteral",
    "TextElement",
    "VariableReference",
    "Variant",
    "event",
    "given",
    "pytest",
    "settings",
    "st",
]
