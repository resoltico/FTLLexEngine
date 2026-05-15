"""Fluent message resolver - converts AST to formatted strings.

Resolves patterns by walking AST, interpolating variables, evaluating selectors.
Python 3.13+. Indirect dependency: Babel (via plural_rules).

Thread Safety:
    Resolution state is passed explicitly via ResolutionContext, making the
    resolver fully reentrant and compatible with async frameworks. Each
    resolution operation creates its own isolated context.

    Same-session depth tracking uses contextvars, while the bundle-owned
    ResolutionReentryGate rejects cross-thread re-entry during custom-function
    execution.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ftllexengine.constants import (
    DEFAULT_MAX_EXPANSION_SIZE,
    FALLBACK_MISSING_MESSAGE,
    FALLBACK_MISSING_TERM,
    MAX_DEPTH,
)
from ftllexengine.core import depth_clamp
from ftllexengine.diagnostics import (
    DiagnosticCode,
    ErrorCategory,
    ErrorTemplate,
    FrozenFluentError,
)
from ftllexengine.runtime.plural_rules import (
    select_plural_category as _select_plural_category,
)
from ftllexengine.runtime.resolution_context import (
    GlobalDepthGuard,
    ResolutionContext,
)
from ftllexengine.runtime.resolver_runtime import _ResolverRuntimeMixin
from ftllexengine.runtime.resolver_selection import _ResolverSelectionMixin
from ftllexengine.syntax import (
    FunctionReference,
    Message,
    MessageReference,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ftllexengine.core.value_types import FluentValue
    from ftllexengine.runtime._resolution_gate import ResolutionReentryGate
    from ftllexengine.runtime.function_bridge import FunctionRegistry

__all__ = ["FluentResolver", "GlobalDepthGuard", "ResolutionContext"]

select_plural_category = _select_plural_category

logger = logging.getLogger(__name__)

# Unicode bidirectional isolation characters per Unicode TR9.
# Used to prevent RTL/LTR text interference when interpolating values.
UNICODE_FSI: str = "\u2068"  # U+2068 FIRST STRONG ISOLATE
UNICODE_PDI: str = "\u2069"  # U+2069 POP DIRECTIONAL ISOLATE


def _is_output_budget_error(error: FrozenFluentError) -> bool:
    """Recognize the resolver's fail-closed output-budget breach.

    Premise:
        Expansion quota failures are structural guardrails, not recoverable
        formatting glitches.

    Reason:
        The pattern loop must stop at the first budget breach instead of
        rendering a fallback and continuing with later output.
    """
    diagnostic = error.diagnostic
    return diagnostic is not None and diagnostic.code == DiagnosticCode.EXPANSION_BUDGET_EXCEEDED


class FluentResolver(_ResolverRuntimeMixin, _ResolverSelectionMixin):
    """Resolves Fluent messages to strings.

    Aligned with Mozilla python-fluent error handling:
    - Collects errors instead of embedding them in output
    - Returns (result, errors) tuples
    - Provides readable fallbacks per Fluent specification

    Thread Safety:
        Uses explicit ResolutionContext instead of thread-local state for
        full reentrancy and async framework compatibility.
    """

    __slots__ = (
        "_function_registry",
        "_locale",
        "_max_expansion_size",
        "_max_nesting_depth",
        "_messages",
        "_resolution_gate",
        "_terms",
        "_use_isolating",
    )

    def __init__(
        self,
        locale: str,
        messages: dict[str, Message],
        terms: dict[str, Term],
        *,
        function_registry: FunctionRegistry,
        reentry_gate: ResolutionReentryGate | None = None,
        use_isolating: bool = True,
        max_nesting_depth: int = MAX_DEPTH,
        max_expansion_size: int | None = DEFAULT_MAX_EXPANSION_SIZE,
    ) -> None:
        """Initialize resolver.

        Args:
            locale: Locale code for plural selection
            messages: Message registry
            terms: Term registry
            function_registry: Function registry with camelCase conversion (keyword-only)
            reentry_gate: Bundle-owned admission control for custom-function
                re-entry. Direct ``FluentResolver`` callers may omit this to
                get a resolver-owned gate with the same protection.
            use_isolating: Wrap interpolated values in Unicode bidi marks (keyword-only)
            max_nesting_depth: Maximum resolution depth limit (keyword-only)
            max_expansion_size: Maximum total characters in resolved output (keyword-only)
        """
        self._locale = locale
        self._use_isolating = use_isolating
        self._messages = messages
        self._terms = terms
        self._function_registry = function_registry
        if reentry_gate is None:
            # Premise: direct resolver users do not always have a bundle owner.
            # Reason: a resolver-owned gate preserves the cross-thread
            # re-entry invariant without forcing callers to construct an
            # internal coordination object for one-off resolution work.
            from ftllexengine.runtime._resolution_gate import (  # noqa: PLC0415 - runtime-only default path
                ResolutionReentryGate,
            )

            reentry_gate = ResolutionReentryGate()
        self._resolution_gate = reentry_gate
        self._max_nesting_depth = depth_clamp(max_nesting_depth)
        self._max_expansion_size = max_expansion_size

    def resolve_message(
        self,
        message: Message,
        args: Mapping[str, FluentValue] | None = None,
        attribute: str | None = None,
        *,
        context: ResolutionContext | None = None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        """Resolve message to final string with error collection.

        Mozilla python-fluent aligned API:
        - Returns (result, errors) tuple
        - Collects all errors during resolution
        - Never raises exceptions (graceful degradation)

        Args:
            message: Message AST
            args: Variable arguments
            attribute: Attribute name (optional)
            context: Resolution context for cycle detection and depth tracking.
                    If None, creates a fresh context for this resolution.

                    Typical Usage: Leave as None (default). Each format_pattern()
                    call creates a fresh context automatically.

                    Advanced Usage: Provide a custom ResolutionContext when:
                    - Batching multiple resolutions with shared cycle detection
                    - Implementing custom depth limits via ResolutionContext(max_depth=N)
                    - Building resolution pipelines that need cross-call state

                    See ResolutionContext class for configuration options.

        Returns:
            Tuple of (formatted_string, errors)
            - formatted_string: Best-effort output (never empty)
            - errors: Tuple of FrozenFluentError instances encountered (immutable)

        Note:
            Per Fluent spec, resolution never fails catastrophically.
            Errors are collected and fallback values are used.

            Attribute resolution uses last-wins semantics for duplicate attribute
            names. If a message contains multiple attributes with the same name
            (which triggers a validation warning), the last definition is used
            during resolution. This matches the Fluent specification and Mozilla
            reference implementation behavior.
        """
        errors: list[FrozenFluentError] = []
        args = {} if args is None else args

        # Create fresh context if not provided (top-level call)
        if context is None:
            context = ResolutionContext(
                max_depth=self._max_nesting_depth,
                max_expression_depth=self._max_nesting_depth,
                max_expansion_size=self._max_expansion_size,
            )

        # Select pattern (value or attribute)
        if attribute:
            attr = next((a for a in reversed(message.attributes) if a.id.name == attribute), None)
            if not attr:
                diag = ErrorTemplate.attribute_not_found(attribute, message.id.name)
                error = FrozenFluentError(str(diag), ErrorCategory.REFERENCE, diagnostic=diag)
                errors.append(error)
                fallback = FALLBACK_MISSING_MESSAGE.format(id=f"{message.id.name}.{attribute}")
                return (fallback, tuple(errors))
            pattern = attr.value
        else:
            if message.value is None:
                diag = ErrorTemplate.message_no_value(message.id.name)
                error = FrozenFluentError(str(diag), ErrorCategory.REFERENCE, diagnostic=diag)
                errors.append(error)
                fallback = FALLBACK_MISSING_MESSAGE.format(id=message.id.name)
                return (fallback, tuple(errors))
            pattern = message.value

        # Check for circular references using explicit context
        msg_key = f"{message.id.name}.{attribute}" if attribute else message.id.name
        if context.contains(msg_key):
            cycle_path = context.get_cycle_path(msg_key)
            diag = ErrorTemplate.cyclic_reference(cycle_path)
            error = FrozenFluentError(str(diag), ErrorCategory.CYCLIC, diagnostic=diag)
            errors.append(error)
            fallback = FALLBACK_MISSING_MESSAGE.format(id=msg_key)
            return (fallback, tuple(errors))

        # Check for maximum depth (prevents stack overflow from long non-cyclic chains)
        if context.is_depth_exceeded():
            diag = ErrorTemplate.max_depth_exceeded(msg_key, context.max_depth)
            error = FrozenFluentError(str(diag), ErrorCategory.REFERENCE, diagnostic=diag)
            errors.append(error)
            fallback = FALLBACK_MISSING_MESSAGE.format(id=msg_key)
            return (fallback, tuple(errors))

        # Same-session nested format_pattern() calls share a depth budget here.
        # Cross-thread fresh entry is handled earlier by the bundle-owned
        # ResolutionReentryGate because ContextVar depth does not propagate to
        # spawned threads.
        try:
            with GlobalDepthGuard(max_depth=context.max_depth):
                context.push(msg_key)
                try:
                    result = self._resolve_pattern(pattern, args, errors, context)
                    return (result, tuple(errors))
                finally:
                    context.pop()
        except FrozenFluentError as e:
            # Resolution limits that escape the pattern loop, such as depth
            # guards, fail closed at the message boundary. Output-budget
            # breaches are handled inside _resolve_pattern so the caller keeps
            # the safe prefix accumulated before the quota was crossed.
            errors.append(e)
            fallback = FALLBACK_MISSING_MESSAGE.format(id=msg_key)
            return (fallback, tuple(errors))

    def _resolve_pattern(
        self,
        pattern: Pattern,
        args: Mapping[str, FluentValue],
        errors: list[FrozenFluentError],
        context: ResolutionContext,
    ) -> str:
        """Resolve pattern by walking elements.

        Uses list accumulation with join() for O(N) performance instead of
        repeated string concatenation which is O(N^2).
        """
        parts: list[str] = []

        for element in pattern.elements:
            if context.output_budget_exhausted:
                break
            match element:
                case TextElement():
                    try:
                        context.reserve_output(element.value)
                    except FrozenFluentError as error:
                        context.mark_output_budget_exhausted()
                        errors.append(error)
                        break
                    parts.append(element.value)
                case Placeable():
                    try:
                        error_count_before = len(errors)
                        # Track expression depth to prevent stack overflow from deeply
                        # nested SelectExpressions. The guard must be applied HERE at
                        # the Pattern->Placeable entry point, not just in _resolve_expression
                        # for nested Placeables. Without this, the recursion path:
                        # Pattern -> Placeable -> SelectExpression -> Variant Pattern -> ...
                        # bypasses depth limiting entirely.
                        with context.expression_guard:
                            value = self._resolve_expression(
                                element.expression, args, errors, context
                            )
                        # Premise: nested variant/message resolution may convert a
                        # budget breach into an appended error instead of a direct
                        # exception on this stack frame.
                        # Reason: the outer pattern must still stop before adding
                        # isolation marks or later suffix text.
                        if any(
                            _is_output_budget_error(error)
                            for error in errors[error_count_before:]
                        ):
                            context.mark_output_budget_exhausted()
                            break
                        formatted = self._format_value(value)
                        rendered = (
                            f"{UNICODE_FSI}{formatted}{UNICODE_PDI}"
                            if self._use_isolating
                            else formatted
                        )
                        context.reserve_output(rendered)
                        parts.append(rendered)

                    except FrozenFluentError as e:
                        # Mozilla-aligned error handling:
                        # Collect error, show readable fallback (not {ERROR: ...})
                        errors.append(e)
                        if _is_output_budget_error(e):
                            context.mark_output_budget_exhausted()
                            break
                        # Check category for type-safe fallback extraction
                        if e.category == ErrorCategory.FORMATTING and e.fallback_value:
                            # Formatting errors carry the original value as fallback
                            try:
                                context.reserve_output(e.fallback_value)
                            except FrozenFluentError as budget_error:
                                context.mark_output_budget_exhausted()
                                errors.append(budget_error)
                                break
                            parts.append(e.fallback_value)
                        else:
                            fallback = self._get_fallback_for_placeable(element.expression)
                            try:
                                context.reserve_output(fallback)
                            except FrozenFluentError as budget_error:
                                context.mark_output_budget_exhausted()
                                errors.append(budget_error)
                                break
                            parts.append(fallback)

        return "".join(parts)

    def _resolve_expression(
        self,
        expr: object,
        args: Mapping[str, FluentValue],
        errors: list[FrozenFluentError],
        context: ResolutionContext,
    ) -> FluentValue:
        """Resolve expression to value.

        Uses pattern matching (PEP 636) to reduce complexity.
        Each case delegates to a specialized resolver method.

        Note: PLR0911 (too many returns) is acceptable here - each case
        represents a distinct expression type in the Fluent AST.
        """
        match expr:
            case SelectExpression():
                return self._resolve_select_expression(expr, args, errors, context)
            case VariableReference():
                return self._resolve_variable_reference(expr, args, context)
            case MessageReference():
                return self._resolve_message_reference(expr, args, errors, context)
            case TermReference():
                return self._resolve_term_reference(expr, args, errors, context)
            case FunctionReference():
                return self._resolve_function_call(expr, args, errors, context)
            case StringLiteral():
                return expr.value
            case NumberLiteral():
                return expr.value
            case Placeable():
                # Track expression depth to prevent stack overflow from deep nesting
                with context.expression_guard:
                    return self._resolve_expression(expr.expression, args, errors, context)
            case _:
                # Defensive: catch unknown expression types from programmatic AST construction
                diag = ErrorTemplate.unknown_expression(type(expr).__name__)
                raise FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag)

    def _resolve_variable_reference(
        self,
        expr: VariableReference,
        args: Mapping[str, FluentValue],
        context: ResolutionContext,
    ) -> FluentValue:
        """Resolve variable reference from args."""
        var_name = expr.id.name
        if var_name not in args:
            # Include resolution path for debugging nested references.
            # resolution_path is an immutable snapshot of the current stack.
            path = context.resolution_path
            resolution_path = path or None
            diag = ErrorTemplate.variable_not_provided(
                var_name, resolution_path=resolution_path
            )
            raise FrozenFluentError(str(diag), ErrorCategory.REFERENCE, diagnostic=diag)
        return args[var_name]

    def _resolve_message_reference(
        self,
        expr: MessageReference,
        args: Mapping[str, FluentValue],
        errors: list[FrozenFluentError],
        context: ResolutionContext,
    ) -> str:
        """Resolve message reference."""
        msg_id = expr.id.name
        if msg_id not in self._messages:
            diag = ErrorTemplate.message_not_found(msg_id)
            raise FrozenFluentError(str(diag), ErrorCategory.REFERENCE, diagnostic=diag)
        message = self._messages[msg_id]
        # resolve_message returns (result, errors) tuple
        # Pass the same context for proper cycle detection across nested calls
        result, nested_errors = self.resolve_message(
            message,
            args,
            attribute=expr.attribute.name if expr.attribute else None,
            context=context,
        )
        # Add nested errors to our error list
        errors.extend(nested_errors)
        return result

    def _resolve_term_reference(
        self,
        expr: TermReference,
        args: Mapping[str, FluentValue],
        errors: list[FrozenFluentError],
        context: ResolutionContext,
    ) -> str:
        """Resolve term reference with cycle detection and argument handling.

        Per Fluent spec, terms can be parameterized with arguments:
            -brand(case: "nominative")

        Term arguments are evaluated and merged into the resolution context,
        allowing term patterns to reference them as variables.
        """
        term_id = expr.id.name
        if term_id not in self._terms:
            diag = ErrorTemplate.term_not_found(term_id)
            raise FrozenFluentError(str(diag), ErrorCategory.REFERENCE, diagnostic=diag)
        term = self._terms[term_id]

        # Select pattern (value or attribute)
        # Use reversed() for last-wins semantics, consistent with message attribute resolution
        if expr.attribute:
            attr = next(
                (a for a in reversed(term.attributes) if a.id.name == expr.attribute.name),
                None,
            )
            if not attr:
                diag = ErrorTemplate.term_attribute_not_found(expr.attribute.name, term_id)
                raise FrozenFluentError(str(diag), ErrorCategory.REFERENCE, diagnostic=diag)
            pattern = attr.value
        else:
            pattern = term.value

        # Build term key for cycle detection (use -prefix to match FTL syntax)
        term_key = f"-{term_id}.{expr.attribute.name}" if expr.attribute else f"-{term_id}"

        # Check for circular references
        if context.contains(term_key):
            cycle_path = context.get_cycle_path(term_key)
            diag = ErrorTemplate.cyclic_reference(cycle_path)
            cycle_error = FrozenFluentError(str(diag), ErrorCategory.CYCLIC, diagnostic=diag)
            errors.append(cycle_error)
            # term_key always starts with exactly one '-' prefix; removeprefix is precise.
            return FALLBACK_MISSING_TERM.format(name=term_key.removeprefix("-"))

        # Check for maximum depth
        if context.is_depth_exceeded():
            diag = ErrorTemplate.max_depth_exceeded(term_key, context.max_depth)
            depth_error = FrozenFluentError(str(diag), ErrorCategory.REFERENCE, diagnostic=diag)
            errors.append(depth_error)
            # term_key always starts with exactly one '-' prefix; removeprefix is precise.
            return FALLBACK_MISSING_TERM.format(name=term_key.removeprefix("-"))

        # Evaluate term arguments - terms are ISOLATED from calling context
        # Per Fluent spec: terms can ONLY access explicitly passed arguments
        # https://projectfluent.org/fluent/guide/terms.html
        # "Terms receive such data from messages in which they are used"
        # This means ONLY explicit parameterization like -term(arg: val), NOT
        # implicit access to the calling message's $variables.
        #
        # Security: Argument evaluation is wrapped in expression_guard to prevent
        # deeply nested term arguments from bypassing depth limits. Without this,
        # -term(arg: -term(arg: ...)) could cause stack overflow via unbounded recursion.
        term_args: dict[str, FluentValue] = {}
        if expr.arguments is not None:
            # Evaluate named arguments (the primary use case for term args)
            # Protected by expression_guard to enforce depth limits on argument expressions
            for named_arg in expr.arguments.named:
                arg_name = named_arg.name.name
                with context.expression_guard:
                    arg_value = self._resolve_expression(
                        named_arg.value, args, errors, context
                    )
                term_args[arg_name] = arg_value

            # Evaluate positional arguments (per Fluent spec, term arguments section)
            # Reference: https://projectfluent.org/fluent/guide/terms.html#parameterized-terms
            # The spec defines term arguments as named only (e.g., -term(case: "gen")).
            # Positional arguments in term references are technically parsed but have
            # no binding semantics - there's no parameter name to assign the value to.
            # We evaluate them to catch expression errors but discard the result.
            # Protected by expression_guard to enforce depth limits on argument expressions
            if expr.arguments.positional:
                for pos_arg in expr.arguments.positional:
                    with context.expression_guard:
                        self._resolve_expression(pos_arg, args, errors, context)

                # Emit warning that positional arguments are ignored
                diag = ErrorTemplate.term_positional_args_ignored(
                    term_name=term_id,
                    count=len(expr.arguments.positional),
                )
                errors.append(
                    FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag)
                )

        try:
            context.push(term_key)
            return self._resolve_pattern(pattern, term_args, errors, context)
        finally:
            context.pop()
