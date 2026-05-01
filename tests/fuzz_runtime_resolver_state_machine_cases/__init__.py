"""Stateful and advanced property-based tests for FluentResolver.

Consolidates:
- test_resolver_state_machine.py: FluentResolverStateMachine (fuzz), TestResolverErrorPaths
- test_resolver_advanced_hypothesis.py: all classes
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import assume, event, given
from hypothesis import strategies as st
from hypothesis.stateful import Bundle, RuleBasedStateMachine, initialize, invariant, rule

from ftllexengine.core.value_types import FluentValue
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.functions import create_default_registry
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.syntax import (
    Attribute,
    CallArguments,
    FunctionReference,
    Identifier,
    Message,
    MessageReference,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
    Term,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)
from tests.strategies import ftl_identifiers, ftl_simple_text

# ============================================================================
# STRATEGY HELPERS
# ============================================================================


def simple_pattern(text: str) -> Pattern:
    """Create simple text pattern."""
    return Pattern(elements=(TextElement(value=text),))


def variable_pattern(var_name: str) -> Pattern:
    """Create pattern with variable reference."""
    return Pattern(
        elements=(
            Placeable(expression=VariableReference(id=Identifier(name=var_name))),
        )
    )


def term_reference_pattern(term_name: str) -> Pattern:
    """Create pattern with term reference."""
    return Pattern(
        elements=(
            Placeable(
                expression=TermReference(id=Identifier(name=term_name), attribute=None)
            ),
        )
    )


def message_reference_pattern(msg_name: str) -> Pattern:
    """Create pattern with message reference."""
    return Pattern(
        elements=(
            Placeable(
                expression=MessageReference(id=Identifier(name=msg_name), attribute=None)
            ),
        )
    )

__all__ = [
    "Attribute",
    "Bundle",
    "CallArguments",
    "Decimal",
    "ErrorCategory",
    "FluentBundle",
    "FluentResolver",
    "FluentValue",
    "FrozenFluentError",
    "FunctionReference",
    "FunctionRegistry",
    "Identifier",
    "Message",
    "MessageReference",
    "NumberLiteral",
    "Pattern",
    "Placeable",
    "RuleBasedStateMachine",
    "SelectExpression",
    "Term",
    "TermReference",
    "TextElement",
    "VariableReference",
    "Variant",
    "assume",
    "create_default_registry",
    "event",
    "ftl_identifiers",
    "ftl_simple_text",
    "given",
    "initialize",
    "invariant",
    "message_reference_pattern",
    "pytest",
    "rule",
    "simple_pattern",
    "st",
    "term_reference_pattern",
    "variable_pattern",
]
