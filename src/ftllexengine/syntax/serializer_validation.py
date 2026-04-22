"""Validation helpers for serializer-facing AST checks."""

from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.core.depth_guard import DepthGuard, DepthLimitExceededError
from ftllexengine.core.identifier_validation import is_valid_identifier
from ftllexengine.diagnostics import FrozenFluentError

from .ast import (
    CallArguments,
    Expression,
    FunctionReference,
    Identifier,
    Message,
    MessageReference,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    StringLiteral,
    Term,
    TermReference,
    VariableReference,
)

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["SerializationDepthError", "SerializationValidationError", "validate_resource"]


class SerializationValidationError(ValueError):
    """Raised when AST validation fails during serialization."""


class SerializationDepthError(ValueError):
    """Raised when AST nesting exceeds maximum serialization depth."""


def _validate_pattern(pattern: Pattern, context: str, depth_guard: DepthGuard) -> None:
    for element in pattern.elements:
        if isinstance(element, Placeable):
            with depth_guard:
                _validate_expression(element.expression, context, depth_guard)


def _validate_identifier(identifier: Identifier, context: str) -> None:
    if not is_valid_identifier(identifier.name):
        msg = (
            f"Invalid identifier '{identifier.name}' in {context}. "
            f"Identifiers must match [a-zA-Z][a-zA-Z0-9_-]* and be ≤256 characters"
        )
        raise SerializationValidationError(msg)


def _require_single_default_variant(
    expr: SelectExpression, context: str
) -> None:
    n_defaults = sum(1 for variant in expr.variants if variant.default)
    if n_defaults == 1:
        return
    if n_defaults == 0:
        msg = (
            f"SelectExpression in {context} has no default variant. "
            "Exactly one variant must be marked as default."
        )
    else:
        msg = (
            f"SelectExpression in {context} has {n_defaults} default variants. "
            "Exactly one variant must be marked as default."
        )
    raise SerializationValidationError(msg)


def _validate_select_expression(
    expr: SelectExpression, context: str, depth_guard: DepthGuard
) -> None:
    _require_single_default_variant(expr, context)
    with depth_guard:
        _validate_expression(expr.selector, context, depth_guard)
    for variant in expr.variants:
        if isinstance(variant.key, Identifier):
            _validate_identifier(variant.key, f"{context}, variant key")
        with depth_guard:
            _validate_pattern(variant.value, context, depth_guard)


def _validate_term_reference(
    expr: TermReference, context: str, depth_guard: DepthGuard
) -> None:
    _validate_identifier(expr.id, f"{context}, term reference")
    if expr.attribute:
        _validate_identifier(expr.attribute, f"{context}, term attribute")
    if expr.arguments:
        _validate_call_arguments(expr.arguments, context, depth_guard)


def _validate_message_reference(expr: MessageReference, context: str) -> None:
    _validate_identifier(expr.id, f"{context}, message reference")
    if expr.attribute:
        _validate_identifier(expr.attribute, f"{context}, message attribute")


def _assert_named_arg_value_is_literal(
    value: object, arg_name: str, context: str
) -> None:
    if not isinstance(value, (StringLiteral, NumberLiteral)):
        value_type = type(value).__name__
        msg = (
            f"Named argument '{arg_name}' in {context} has invalid value type "
            f"'{value_type}'. Named argument values must be StringLiteral or "
            f"NumberLiteral per FTL specification "
            f'(NamedArgument ::= Identifier ":" (StringLiteral | NumberLiteral)).'
        )
        raise SerializationValidationError(msg)


def _validate_call_arguments(
    args: CallArguments, context: str, depth_guard: DepthGuard
) -> None:
    for pos_arg in args.positional:
        with depth_guard:
            _validate_expression(pos_arg, context, depth_guard)

    seen_names: set[str] = set()
    for named_arg in args.named:
        arg_name = named_arg.name.name
        if arg_name in seen_names:
            msg = (
                f"Duplicate named argument '{arg_name}' in {context}. "
                "Named argument names must be unique per FTL specification."
            )
            raise SerializationValidationError(msg)
        seen_names.add(arg_name)

        _validate_identifier(named_arg.name, f"{context}, named argument")
        _assert_named_arg_value_is_literal(named_arg.value, arg_name, context)


def _validate_expression(
    expr: Expression, context: str, depth_guard: DepthGuard
) -> None:
    match expr:
        case SelectExpression():
            _validate_select_expression(expr, context, depth_guard)
        case Placeable():
            with depth_guard:
                _validate_expression(expr.expression, context, depth_guard)
        case VariableReference():
            _validate_identifier(expr.id, f"{context}, variable reference")
        case MessageReference():
            _validate_message_reference(expr, context)
        case TermReference():
            _validate_term_reference(expr, context, depth_guard)
        case FunctionReference():
            _validate_identifier(expr.id, f"{context}, function reference")
            _validate_call_arguments(expr.arguments, context, depth_guard)
        case StringLiteral() | NumberLiteral():
            return
        case _ as unreachable:  # pragma: no cover
            assert_never(unreachable)


def validate_resource(
    resource: Resource,
    max_depth: int = MAX_DEPTH,
    *,
    validate_pattern: Callable[[Pattern, str, DepthGuard], None] | None = None,
) -> None:
    """Validate a Resource AST for safe serialization."""
    depth_guard = DepthGuard(max_depth=max_depth)
    pattern_validator = _validate_pattern if validate_pattern is None else validate_pattern

    try:
        for entry in resource.entries:
            match entry:
                case Message():
                    _validate_identifier(entry.id, "message ID")
                    context = f"message '{entry.id.name}'"
                    if entry.value:
                        pattern_validator(entry.value, context, depth_guard)
                    for attr in entry.attributes:
                        _validate_identifier(attr.id, f"{context}, attribute ID")
                        pattern_validator(
                            attr.value,
                            f"{context}.{attr.id.name}",
                            depth_guard,
                        )
                case Term():
                    _validate_identifier(entry.id, "term ID")
                    context = f"term '-{entry.id.name}'"
                    pattern_validator(entry.value, context, depth_guard)
                    for attr in entry.attributes:
                        _validate_identifier(attr.id, f"{context}, attribute ID")
                        pattern_validator(
                            attr.value,
                            f"{context}.{attr.id.name}",
                            depth_guard,
                        )
                case _:
                    pass
    except DepthLimitExceededError as exc:
        msg = f"Validation depth limit exceeded (max: {max_depth}): {exc}"
        raise SerializationDepthError(msg) from exc
    except FrozenFluentError:
        raise
