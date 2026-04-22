"""Variant-selection helpers for FluentResolver."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from ftllexengine.core.babel_compat import BabelImportError
from ftllexengine.core.value_types import FluentNumber
from ftllexengine.diagnostics import ErrorCategory, ErrorTemplate, FrozenFluentError
from ftllexengine.runtime import resolver as _resolver_module
from ftllexengine.syntax import Expression, Identifier, NumberLiteral, SelectExpression, Variant

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ftllexengine.core.value_types import FluentValue
    from ftllexengine.runtime.resolution_context import ResolutionContext
    from ftllexengine.syntax import Pattern


class _ResolverSelectionMixin:
    """Select-expression behavior for FluentResolver."""

    _locale: str

    if TYPE_CHECKING:

        def _format_value(self, value: object) -> str: ...

        def _resolve_expression(
            self,
            expr: Expression,
            args: Mapping[str, FluentValue],
            errors: list[FrozenFluentError],
            context: ResolutionContext,
        ) -> FluentValue: ...

        def _resolve_pattern(
            self,
            pattern: Pattern,
            args: Mapping[str, FluentValue],
            errors: list[FrozenFluentError],
            context: ResolutionContext,
        ) -> str: ...

    def _find_exact_variant(
        self,
        variants: Sequence[Variant],
        selector_value: object,
        selector_str: str,
    ) -> Variant | None:
        """Pass 1: find an exact string or numeric variant match."""
        numeric_for_match: int | Decimal | None = None
        if isinstance(selector_value, FluentNumber):
            numeric_for_match = selector_value.value
        elif isinstance(selector_value, (int, Decimal)) and not isinstance(selector_value, bool):
            numeric_for_match = selector_value

        sel_decimal: Decimal | None = None
        if numeric_for_match is not None:
            sel_decimal = Decimal(str(numeric_for_match))

        for variant in variants:
            match variant.key:
                case Identifier(name=key_name):
                    if key_name == selector_str:
                        return variant
                case NumberLiteral(raw=raw_str):
                    if sel_decimal is not None and Decimal(raw_str) == sel_decimal:
                        return variant
        return None

    def _find_plural_variant(
        self, variants: Sequence[Variant], plural_category: str
    ) -> Variant | None:
        """Pass 2: find a plural-category variant match."""
        for variant in variants:
            match variant.key:
                case Identifier(name=key_name):
                    if key_name == plural_category:
                        return variant
        return None

    def _find_default_variant(
        self, variants: Sequence[Variant]
    ) -> Variant | None:
        """Return the default variant, if one exists."""
        for variant in variants:
            if variant.default:
                return variant
        return None

    def _resolve_select_expression(
        self,
        expr: SelectExpression,
        args: Mapping[str, FluentValue],
        errors: list[FrozenFluentError],
        context: ResolutionContext,
    ) -> str:
        """Resolve a select expression using Fluent's matching order."""
        try:
            with context.expression_guard:
                selector_value = self._resolve_expression(expr.selector, args, errors, context)
        except FrozenFluentError as error:
            errors.append(error)
            return self._resolve_fallback_variant(expr, args, errors, context)

        selector_str = self._format_value(selector_value)

        exact_match = self._find_exact_variant(expr.variants, selector_value, selector_str)
        if exact_match is not None:
            return self._resolve_pattern(exact_match.value, args, errors, context)

        numeric_value: int | Decimal | None = None
        precision: int | None = None
        if isinstance(selector_value, FluentNumber):
            numeric_value = selector_value.value
            precision = selector_value.precision
        elif isinstance(selector_value, (int, Decimal)) and not isinstance(
            selector_value, bool
        ):
            numeric_value = selector_value

        if numeric_value is not None:
            try:
                plural_category = _resolver_module.select_plural_category(
                    numeric_value,
                    self._locale,
                    precision,
                )
                plural_match = self._find_plural_variant(expr.variants, plural_category)
                if plural_match is not None:
                    return self._resolve_pattern(plural_match.value, args, errors, context)
            except BabelImportError:
                diag = ErrorTemplate.plural_support_unavailable()
                errors.append(
                    FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag)
                )

        return self._resolve_fallback_variant(expr, args, errors, context)

    def _resolve_fallback_variant(
        self,
        expr: SelectExpression,
        args: Mapping[str, FluentValue],
        errors: list[FrozenFluentError],
        context: ResolutionContext,
    ) -> str:
        """Resolve the default or first variant after selector failure."""
        default_variant = self._find_default_variant(expr.variants)
        if default_variant is not None:
            return self._resolve_pattern(default_variant.value, args, errors, context)

        if expr.variants:
            return self._resolve_pattern(expr.variants[0].value, args, errors, context)

        diag = ErrorTemplate.no_variants()
        raise FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag)
