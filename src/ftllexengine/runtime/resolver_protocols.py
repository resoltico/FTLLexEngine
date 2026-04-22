"""Type-checking protocols for FluentResolver mixins."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ftllexengine.core.value_types import FluentValue
    from ftllexengine.diagnostics import FrozenFluentError
    from ftllexengine.runtime.function_bridge import FunctionRegistry
    from ftllexengine.runtime.resolution_context import ResolutionContext
    from ftllexengine.syntax import Expression, Pattern, SelectExpression, Variant


class ResolverStateProtocol(Protocol):
    """Structural contract implemented by FluentResolver for its mixins."""

    _function_registry: FunctionRegistry
    _locale: str

    def _format_value(self, value: object) -> str:
        ...  # pragma: no cover - typing-only protocol declaration

    def _resolve_expression(
        self,
        expr: Expression,
        args: Mapping[str, object],
        errors: list[FrozenFluentError],
        context: ResolutionContext,
    ) -> FluentValue:
        ...  # pragma: no cover - typing-only protocol declaration

    def _resolve_pattern(
        self,
        pattern: Pattern,
        args: Mapping[str, object],
        errors: list[FrozenFluentError],
        context: ResolutionContext,
    ) -> str:
        ...  # pragma: no cover - typing-only protocol declaration

    def _call_function_safe(
        self,
        func_name: str,
        positional: Sequence[FluentValue],
        named: Mapping[str, FluentValue],
        errors: list[FrozenFluentError],
    ) -> FluentValue:
        ...  # pragma: no cover - typing-only protocol declaration

    def _get_fallback_for_placeable(
        self, expr: Expression, depth: int = 10
    ) -> str:
        ...  # pragma: no cover - typing-only protocol declaration

    def _resolve_fallback_variant(
        self,
        expr: SelectExpression,
        args: Mapping[str, object],
        errors: list[FrozenFluentError],
        context: ResolutionContext,
    ) -> str:
        ...  # pragma: no cover - typing-only protocol declaration

    def _find_exact_variant(
        self,
        variants: Sequence[Variant],
        selector_value: object,
        selector_str: str,
    ) -> Variant | None:
        ...  # pragma: no cover - typing-only protocol declaration

    def _find_plural_variant(
        self, variants: Sequence[Variant], plural_category: str
    ) -> Variant | None:
        ...  # pragma: no cover - typing-only protocol declaration

    def _find_default_variant(self, variants: Sequence[Variant]) -> Variant | None:
        ...  # pragma: no cover - typing-only protocol declaration

    def _get_reference_fallback(self, expr: Expression) -> str | None:
        ...  # pragma: no cover - typing-only protocol declaration

    def _get_nested_fallback(self, expr: Expression, depth: int) -> str:
        ...  # pragma: no cover - typing-only protocol declaration
