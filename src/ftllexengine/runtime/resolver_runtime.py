"""Function-call and fallback helpers for FluentResolver."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from ftllexengine.constants import (
    FALLBACK_FUNCTION_ERROR,
    FALLBACK_INVALID,
    FALLBACK_MISSING_MESSAGE,
    FALLBACK_MISSING_TERM,
    FALLBACK_MISSING_VARIABLE,
)
from ftllexengine.diagnostics import ErrorCategory, ErrorTemplate, FrozenFluentError
from ftllexengine.syntax import (
    Expression,
    FunctionReference,
    MessageReference,
    NumberLiteral,
    Placeable,
    SelectExpression,
    StringLiteral,
    TermReference,
    VariableReference,
)

if TYPE_CHECKING:
    from ftllexengine.core.value_types import FluentValue
    from ftllexengine.runtime.function_bridge import FunctionRegistry
    from ftllexengine.runtime.resolution_context import ResolutionContext

logger = logging.getLogger("ftllexengine.runtime.resolver")

_FALLBACK_MAX_DEPTH: int = 10


class _ResolverRuntimeMixin:
    """Function-call, formatting, and fallback behavior for FluentResolver."""

    _function_registry: FunctionRegistry
    _locale: str

    if TYPE_CHECKING:

        def _resolve_expression(
            self,
            expr: Expression,
            args: Mapping[str, FluentValue],
            errors: list[FrozenFluentError],
            context: ResolutionContext,
        ) -> FluentValue: ...

    def _resolve_function_call(
        self,
        func_ref: FunctionReference,
        args: Mapping[str, FluentValue],
        errors: list[FrozenFluentError],
        context: ResolutionContext,
    ) -> FluentValue:
        """Resolve a function call with guarded argument evaluation."""
        func_name = func_ref.id.name

        with context.expression_guard:
            positional_values = [
                self._resolve_expression(arg, args, errors, context)
                for arg in func_ref.arguments.positional
            ]
            named_values = {
                arg.name.name: self._resolve_expression(arg.value, args, errors, context)
                for arg in func_ref.arguments.named
            }

        if self._function_registry.should_inject_locale(func_name):
            expected_args = self._function_registry.get_expected_positional_args(func_name)
            if expected_args is not None and len(positional_values) != expected_args:
                diag = ErrorTemplate.function_arity_mismatch(
                    func_name, expected_args, len(positional_values)
                )
                raise FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag)

            return self._call_function_safe(
                func_name,
                [*positional_values, self._locale],
                named_values,
                errors,
            )

        return self._call_function_safe(
            func_name,
            positional_values,
            named_values,
            errors,
        )

    def _call_function_safe(
        self,
        func_name: str,
        positional: Sequence[FluentValue],
        named: Mapping[str, FluentValue],
        errors: list[FrozenFluentError],
    ) -> FluentValue:
        """Call a registered function and normalize unexpected exceptions."""
        try:
            return self._function_registry.call(func_name, positional, named)
        except FrozenFluentError:
            raise
        except Exception as error:  # noqa: BLE001 - function adapters may raise arbitrary user exceptions
            logger.warning(
                "Custom function %s raised %s: %s",
                func_name,
                type(error).__name__,
                str(error),
            )
            diag = ErrorTemplate.function_failed(
                func_name, f"Uncaught exception: {type(error).__name__}: {error}"
            )
            errors.append(
                FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag)
            )
            return FALLBACK_FUNCTION_ERROR.format(name=func_name)

    def _format_value(self, value: object) -> str:
        """Format a resolved FluentValue for final output."""
        match value:
            case str():
                return value
            case bool():
                return "true" if value else "false"
            case int():
                return str(value)
            case None:
                return ""
            case float():
                msg = (
                    f"float value {value!r} is not a valid FluentValue. "
                    "IEEE 754 float cannot represent most decimal fractions exactly. "
                    "Use int for whole amounts or decimal.Decimal for fractional amounts."
                )
                raise FrozenFluentError(msg, ErrorCategory.RESOLUTION)
            case Sequence() | Mapping():
                return f"[{type(value).__name__}]"
            case _:
                return str(value)

    def _get_reference_fallback(
        self, expr: Expression
    ) -> str | None:
        """Return direct fallback text for simple reference expressions."""
        match expr:
            case VariableReference():
                return FALLBACK_MISSING_VARIABLE.format(name=expr.id.name)
            case MessageReference():
                msg_id = expr.id.name
                if expr.attribute:
                    msg_id = f"{msg_id}.{expr.attribute.name}"
                return FALLBACK_MISSING_MESSAGE.format(id=msg_id)
            case TermReference():
                term_id = expr.id.name
                if expr.attribute:
                    term_id = f"{term_id}.{expr.attribute.name}"
                return FALLBACK_MISSING_TERM.format(name=term_id)
            case FunctionReference():
                return FALLBACK_FUNCTION_ERROR.format(name=expr.id.name)
            case _:
                return None

    def _get_nested_fallback(
        self, expr: Expression, depth: int
    ) -> str:
        """Return fallback text for nested or literal expressions."""
        match expr:
            case SelectExpression():
                selector_fallback = self._get_fallback_for_placeable(expr.selector, depth - 1)
                return f"{{{selector_fallback} -> ...}}"
            case Placeable():
                return self._get_fallback_for_placeable(expr.expression, depth - 1)
            case StringLiteral():
                return expr.value
            case NumberLiteral():
                return expr.raw
            case _:
                return FALLBACK_INVALID

    def _get_fallback_for_placeable(
        self, expr: Expression, depth: int = _FALLBACK_MAX_DEPTH
    ) -> str:
        """Render a readable fallback string for a failed placeable."""
        if depth <= 0:
            return FALLBACK_INVALID

        reference_fallback = self._get_reference_fallback(expr)
        if reference_fallback is not None:
            return reference_fallback
        return self._get_nested_fallback(expr, depth)
