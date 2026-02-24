"""Fluent message resolver - converts AST to formatted strings.

Resolves patterns by walking AST, interpolating variables, evaluating selectors.
Python 3.13+. Indirect dependency: Babel (via plural_rules).

Thread Safety:
    Resolution state is passed explicitly via ResolutionContext, making the
    resolver fully reentrant and compatible with async frameworks. Each
    resolution operation creates its own isolated context.

    Global depth tracking uses contextvars for async-safe per-task state,
    preventing custom functions from bypassing depth limits by calling
    back into bundle.format_pattern().
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import TYPE_CHECKING

from ftllexengine.constants import (
    DEFAULT_MAX_EXPANSION_SIZE,
    FALLBACK_FUNCTION_ERROR,
    FALLBACK_INVALID,
    FALLBACK_MISSING_MESSAGE,
    FALLBACK_MISSING_TERM,
    FALLBACK_MISSING_VARIABLE,
    MAX_DEPTH,
)
from ftllexengine.core import depth_clamp
from ftllexengine.core.babel_compat import BabelImportError
from ftllexengine.diagnostics import (
    ErrorCategory,
    ErrorTemplate,
    FrozenFluentError,
)
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.plural_rules import select_plural_category
from ftllexengine.runtime.resolution_context import (
    GlobalDepthGuard,
    ResolutionContext,
)
from ftllexengine.runtime.value_types import FluentNumber
from ftllexengine.syntax import (
    Expression,
    FunctionReference,
    Identifier,
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
    Variant,
)

if TYPE_CHECKING:
    from ftllexengine.runtime.value_types import FluentValue

__all__ = ["FluentResolver", "GlobalDepthGuard", "ResolutionContext"]

logger = logging.getLogger(__name__)

# Unicode bidirectional isolation characters per Unicode TR9.
# Used to prevent RTL/LTR text interference when interpolating values.
UNICODE_FSI: str = "\u2068"  # U+2068 FIRST STRONG ISOLATE
UNICODE_PDI: str = "\u2069"  # U+2069 POP DIRECTIONAL ISOLATE

# Maximum recursion depth for fallback string generation in _get_fallback_for_placeable.
# Fallback rendering is purely diagnostic (shown when resolution fails), so a shallow
# depth limit prevents runaway recursion while still capturing meaningful context.
_FALLBACK_MAX_DEPTH: int = 10


class FluentResolver:
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
        use_isolating: bool = True,
        max_nesting_depth: int = MAX_DEPTH,
        max_expansion_size: int = DEFAULT_MAX_EXPANSION_SIZE,
    ) -> None:
        """Initialize resolver.

        Args:
            locale: Locale code for plural selection
            messages: Message registry
            terms: Term registry
            function_registry: Function registry with camelCase conversion (keyword-only)
            use_isolating: Wrap interpolated values in Unicode bidi marks (keyword-only)
            max_nesting_depth: Maximum resolution depth limit (keyword-only)
            max_expansion_size: Maximum total characters in resolved output (keyword-only)
        """
        self._locale = locale
        self._use_isolating = use_isolating
        self._messages = messages
        self._terms = terms
        self._function_registry = function_registry
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

        # Use GlobalDepthGuard to track depth across separate format_pattern() calls.
        # This prevents custom functions from bypassing depth limits by calling
        # back into bundle.format_pattern() which creates a fresh ResolutionContext.
        try:
            with GlobalDepthGuard(max_depth=context.max_depth):
                context.push(msg_key)
                try:
                    result = self._resolve_pattern(pattern, args, errors, context)
                    return (result, tuple(errors))
                finally:
                    context.pop()
        except FrozenFluentError as e:
            # Resolution limit exceeded (global depth, expression depth, or
            # expansion budget). Collect error and return fallback — prevents
            # partial output from reaching the caller.
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

        # Fast-path: budget already exceeded before any element is processed.
        # Covers externally-provided ResolutionContext instances (e.g., test fixtures,
        # callers that pass a pre-populated context) where no element in this pattern
        # has yet contributed to the error list.
        if context.total_chars > context.max_expansion_size:
            diag = ErrorTemplate.expansion_budget_exceeded(
                context.total_chars, context.max_expansion_size
            )
            errors.append(
                FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag)
            )
            return "".join(parts)

        for element in pattern.elements:
            match element:
                case TextElement():
                    context.track_expansion(len(element.value))
                    if context.total_chars > context.max_expansion_size:
                        diag = ErrorTemplate.expansion_budget_exceeded(
                            context.total_chars, context.max_expansion_size
                        )
                        errors.append(
                            FrozenFluentError(
                                str(diag), ErrorCategory.RESOLUTION, diagnostic=diag
                            )
                        )
                        break
                    parts.append(element.value)
                case Placeable():
                    try:
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
                        formatted = self._format_value(value)
                        pre_track = context.total_chars
                        context.track_expansion(len(formatted))
                        if context.total_chars > context.max_expansion_size:
                            if pre_track <= context.max_expansion_size:
                                # This placeable's formatted output caused the overflow.
                                # When pre_track was already over the limit, the overflow
                                # was reported inside the nested resolution (term, message,
                                # or select variant), and we must not duplicate that error.
                                diag = ErrorTemplate.expansion_budget_exceeded(
                                    context.total_chars, context.max_expansion_size
                                )
                                errors.append(
                                    FrozenFluentError(
                                        str(diag), ErrorCategory.RESOLUTION, diagnostic=diag
                                    )
                                )
                            break

                        # Wrap in Unicode bidi isolation marks (FSI/PDI)
                        # Per Unicode TR9, prevents RTL/LTR text interference
                        if self._use_isolating:
                            parts.append(f"{UNICODE_FSI}{formatted}{UNICODE_PDI}")
                        else:
                            parts.append(formatted)

                    except FrozenFluentError as e:
                        # Mozilla-aligned error handling:
                        # Collect error, show readable fallback (not {ERROR: ...})
                        errors.append(e)
                        # Check category for type-safe fallback extraction
                        if e.category == ErrorCategory.FORMATTING and e.fallback_value:
                            # Formatting errors carry the original value as fallback
                            parts.append(e.fallback_value)
                        else:
                            parts.append(self._get_fallback_for_placeable(element.expression))

        return "".join(parts)

    def _resolve_expression(  # noqa: PLR0911  # Complex dispatch logic expected
        self,
        expr: Expression,
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
                diag = ErrorTemplate.unknown_expression(type(expr).__name__)  # type: ignore[unreachable]
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
            resolution_path = path if path else None
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
            # term_key already has '-' prefix, strip it for the template
            return FALLBACK_MISSING_TERM.format(name=term_key.lstrip("-"))

        # Check for maximum depth
        if context.is_depth_exceeded():
            diag = ErrorTemplate.max_depth_exceeded(term_key, context.max_depth)
            depth_error = FrozenFluentError(str(diag), ErrorCategory.REFERENCE, diagnostic=diag)
            errors.append(depth_error)
            # term_key already has '-' prefix, strip it for the template
            return FALLBACK_MISSING_TERM.format(name=term_key.lstrip("-"))

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

    def _find_exact_variant(
        self,
        variants: Sequence[Variant],
        selector_value: FluentValue,
        selector_str: str,
    ) -> Variant | None:
        """Pass 1: Find variant with exact string or number match.

        Args:
            variants: Sequence of variants to search
            selector_value: Resolved selector value (for numeric comparison)
            selector_str: String representation of selector (for string comparison)

        Returns:
            Matching variant or None if no exact match found.
        """
        for variant in variants:
            match variant.key:
                case Identifier(name=key_name):
                    if key_name == selector_str:
                        return variant
                case NumberLiteral(raw=raw_str):
                    # Handle int, Decimal, and FluentNumber for exact numeric match.
                    # float is not in FluentValue: only int and Decimal are valid numeric types.
                    # Use NumberLiteral.raw (exact source string) for key comparison.
                    # Note: Exclude bool since isinstance(True, int) is True in Python,
                    # but str(True) == "True" which is not a valid Decimal.
                    #
                    # FluentNumber wraps formatted numbers (from NUMBER() function) while
                    # preserving the original numeric value for matching. Extract .value
                    # for numeric comparison so [1000] matches FluentNumber(1000, "1,000").
                    numeric_for_match: int | Decimal | None = None
                    if isinstance(selector_value, FluentNumber):
                        numeric_for_match = selector_value.value
                    elif (
                        isinstance(selector_value, (int, Decimal))
                        and not isinstance(selector_value, bool)
                    ):
                        numeric_for_match = selector_value

                    if numeric_for_match is not None:
                        # Use raw string for key to preserve exact source precision.
                        # NumberLiteral.__post_init__ guarantees raw is a parseable
                        # finite number, so Decimal(raw_str) always succeeds here.
                        key_decimal = Decimal(raw_str)
                        sel_decimal = Decimal(str(numeric_for_match))
                        if key_decimal == sel_decimal:
                            return variant
        return None

    def _find_plural_variant(
        self,
        variants: Sequence[Variant],
        plural_category: str,
    ) -> Variant | None:
        """Pass 2: Find variant matching plural category.

        Args:
            variants: Sequence of variants to search
            plural_category: CLDR plural category (zero, one, two, few, many, other)

        Returns:
            Matching variant or None if no plural category match found.
        """
        for variant in variants:
            match variant.key:
                case Identifier(name=key_name):
                    if key_name == plural_category:
                        return variant
        return None

    def _find_default_variant(self, variants: Sequence[Variant]) -> Variant | None:
        """Find the default variant (marked with *).

        Args:
            variants: Sequence of variants to search

        Returns:
            Default variant or None if no default marked.
        """
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
        """Resolve select expression by matching variant.

        Matching priority (two-pass linear scan):
            1. Exact string/number match (pass 1)
            2. Plural category match for numeric selectors (pass 2)
            3. Default variant
            4. First variant (fallback)

        For typical FTL files with <5 variants, linear scan is more efficient
        than building dictionary indices. Exact matches always take precedence
        over plural category matches, regardless of variant order in FTL source.

        Error handling:
            If the selector expression fails (e.g., missing variable), the error
            is collected and resolution falls back to the default variant. This
            ensures robustness and matches the Fluent spec behavior.
        """
        # Evaluate selector with error resilience.
        # If selector evaluation fails (e.g., missing variable), collect the error
        # and fall back to the default variant per Fluent spec.
        # Wrap in expression_guard to track depth for DoS protection.
        try:
            with context.expression_guard:
                selector_value = self._resolve_expression(
                    expr.selector, args, errors, context
                )
        except FrozenFluentError as e:
            # Collect the error but don't propagate - fall back to default variant
            errors.append(e)
            return self._resolve_fallback_variant(expr, args, errors, context)

        # Use _format_value for consistent string representation.
        # This ensures:
        # - None -> "" (falls through to default variant)
        # - bool -> "true"/"false" (matches FTL variant keys, not Python "True"/"False")
        # - FluentNumber -> formatted string (display representation)
        # - Other types -> str() representation
        selector_str = self._format_value(selector_value)

        # Pass 1: Exact match (takes priority)
        exact_match = self._find_exact_variant(expr.variants, selector_value, selector_str)
        if exact_match is not None:
            return self._resolve_pattern(exact_match.value, args, errors, context)

        # Pass 2: Plural category match (numeric selectors only)
        # FluentValue includes Decimal for currency/financial values.
        # FluentNumber wraps formatted numbers while preserving numeric identity.
        # float is not in FluentValue: only int and Decimal are valid numeric types.
        # Note: Exclude bool since isinstance(True, int) is True in Python,
        # but booleans should match [true]/[false] variants, not plural categories.
        #
        # Extract numeric value and precision from FluentNumber for plural matching.
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
            # Try plural category matching (requires Babel for CLDR data).
            # If Babel is not installed (parser-only mode), collect error and
            # fall through to default variant.
            try:
                # Pass precision to ensure CLDR v operand (fraction digit count) is correct.
                # Example: NUMBER(1, minimumFractionDigits: 2) creates FluentNumber with
                # precision=2, which makes select_plural_category treat it as "1.00" (v=2),
                # selecting "other" instead of "one" in English plural rules.
                plural_category = select_plural_category(numeric_value, self._locale, precision)
                plural_match = self._find_plural_variant(expr.variants, plural_category)
                if plural_match is not None:
                    return self._resolve_pattern(
                        plural_match.value, args, errors, context
                    )
            except BabelImportError:
                # Babel not installed - collect error, fall through to default
                diag = ErrorTemplate.plural_support_unavailable()
                errors.append(
                    FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag)
                )

        # Fallback: default variant
        default_variant = self._find_default_variant(expr.variants)
        if default_variant is not None:
            return self._resolve_pattern(default_variant.value, args, errors, context)

        # Fallback: first variant
        if expr.variants:
            return self._resolve_pattern(expr.variants[0].value, args, errors, context)

        diag = ErrorTemplate.no_variants()
        raise FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag)

    def _resolve_fallback_variant(
        self,
        expr: SelectExpression,
        args: Mapping[str, FluentValue],
        errors: list[FrozenFluentError],
        context: ResolutionContext,
    ) -> str:
        """Resolve fallback variant when selector evaluation fails.

        Attempts to resolve in order:
            1. Default variant (marked with *)
            2. First variant

        Args:
            expr: The SelectExpression to resolve
            args: Arguments for pattern resolution
            errors: Error list for error collection
            context: Resolution context

        Returns:
            Resolved variant pattern string

        Raises:
            FrozenFluentError: If no variants exist (category=RESOLUTION)
        """
        # Try default variant first
        default_variant = self._find_default_variant(expr.variants)
        if default_variant is not None:
            return self._resolve_pattern(default_variant.value, args, errors, context)

        # Fall back to first variant
        if expr.variants:
            return self._resolve_pattern(expr.variants[0].value, args, errors, context)

        diag = ErrorTemplate.no_variants()
        raise FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag)

    def _resolve_function_call(
        self,
        func_ref: FunctionReference,
        args: Mapping[str, FluentValue],
        errors: list[FrozenFluentError],
        context: ResolutionContext,
    ) -> FluentValue:
        """Resolve function call.

        Uses FunctionRegistry to handle camelCase → snake_case parameter conversion.
        Uses metadata system to determine if locale injection is needed.

        Exception Handling:
            FrozenFluentError from registry (TypeError/ValueError) propagates to
            pattern-level handler. Other exceptions (bugs in custom functions)
            are caught here to provide graceful degradation per Fluent spec.
            This ensures resolution "never fails catastrophically."

        Security:
            Wraps argument resolution in expression_guard to prevent DoS via deeply
            nested function calls like NUMBER(A(B(C(...)))). Each nested call
            consumes stack frames during resolution.

        Returns FluentValue which the resolver will convert to string for final output.
        """
        func_name = func_ref.id.name

        # Evaluate arguments within depth guard (DoS prevention)
        # Function arguments can contain nested function calls: NUMBER(ABS(FLOOR($x)))
        # Without depth tracking, deeply nested calls can exhaust the Python stack.
        with context.expression_guard:
            positional_values: list[FluentValue] = [
                self._resolve_expression(arg, args, errors, context)
                for arg in func_ref.arguments.positional
            ]

            # Evaluate named arguments (camelCase from FTL)
            named_values: dict[str, FluentValue] = {
                arg.name.name: self._resolve_expression(arg.value, args, errors, context)
                for arg in func_ref.arguments.named
            }

        # Check if locale injection is needed (metadata-driven, not magic tuple)
        # This correctly handles custom functions with same name as built-ins
        if self._function_registry.should_inject_locale(func_name):
            # Validate arity before injection to provide clear error messages
            # instead of opaque TypeError from incorrect argument positioning
            expected_args = self._function_registry.get_expected_positional_args(func_name)
            if expected_args is not None and len(positional_values) != expected_args:
                diag = ErrorTemplate.function_arity_mismatch(
                    func_name, expected_args, len(positional_values)
                )
                raise FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag)

            # Built-in formatting functions expect signature: func(value, locale, *, ...)
            # Append locale after positional args (FTL passes exactly one value arg,
            # so this places locale as the second positional argument by contract)
            # FunctionRegistry.call() handles camelCase -> snake_case conversion
            return self._call_function_safe(
                func_name,
                [*positional_values, self._locale],
                named_values,
                errors,
            )

        # Custom function or built-in that doesn't need locale: pass args as-is
        return self._call_function_safe(
            func_name,
            positional_values,
            named_values,
            errors,
        )

    def _call_function_safe(
        self,
        func_name: str,
        positional: list[FluentValue],
        named: dict[str, FluentValue],
        errors: list[FrozenFluentError],
    ) -> FluentValue:
        """Call a registered function with graceful error handling.

        FrozenFluentError from the registry propagates directly (already
        structured). Any other exception is caught and converted to a
        diagnostic error per Fluent spec requirement that resolution must
        "never fail catastrophically."

        Args:
            func_name: Function name as it appears in FTL.
            positional: Positional argument values (locale may be appended).
            named: Named argument values (camelCase keys from FTL).
            errors: Mutable error accumulator for the current resolution.

        Returns:
            Function result on success, or fallback error string on failure.
        """
        try:
            return self._function_registry.call(func_name, positional, named)
        except FrozenFluentError:
            # Already structured error from registry (TypeError/ValueError),
            # let it propagate to pattern-level handler
            raise
        except Exception as e:  # pylint: disable=broad-exception-caught
            # Intentionally broad: Fluent spec requires graceful degradation
            # for ANY exception from custom functions.
            logger.warning(
                "Custom function %s raised %s: %s",
                func_name,
                type(e).__name__,
                str(e),
            )
            diag = ErrorTemplate.function_failed(
                func_name, f"Uncaught exception: {type(e).__name__}: {e}"
            )
            errors.append(
                FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag)
            )
            return FALLBACK_FUNCTION_ERROR.format(name=func_name)

    def _format_value(self, value: FluentValue) -> str:
        """Format FluentValue to string for final output.

        Handles all types in the FluentValue union:
        - str: returned as-is
        - bool: "true"/"false" (Fluent convention)
        - int: string representation
        - Decimal/datetime/date/FluentNumber: string representation via __str__
        - Sequence/Mapping: type name (collections are for function args, not display)
        - None: empty string

        float is not in FluentValue and is not handled here. Callers passing float
        will see a type error at the call site, not here.
        """
        if isinstance(value, str):
            return value
        # Check bool BEFORE int (bool is a subclass of int in Python)
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        if value is None:
            return ""
        # Guard against str() on collections (Sequence/Mapping). These are valid
        # FluentValue types for passing structured data to custom functions, but
        # str() on deeply nested/shared structures causes exponential expansion
        # (e.g., DAG with depth 30 → 2^30 nodes in str() output).
        if isinstance(value, (Sequence, Mapping)):
            return f"[{type(value).__name__}]"
        # Handles Decimal, datetime, date, FluentNumber, and any other types
        return str(value)

    def _get_fallback_for_placeable(  # noqa: PLR0911 - fallback dispatch
        self, expr: Expression, depth: int = _FALLBACK_MAX_DEPTH
    ) -> str:
        """Get readable fallback for failed placeable per Fluent spec.

        Per Fluent specification, when a placeable fails to resolve,
        we return a human-readable representation of what was attempted.
        This is superior to {ERROR: ...} as it:
        1. Doesn't expose internal diagnostics
        2. Shows what the translator expected
        3. Makes errors visible but not alarming

        Args:
            expr: The expression that failed to resolve
            depth: Remaining recursion depth (prevents stack overflow)

        Returns:
            Readable fallback string

        Examples:
            VariableReference($name) -> "{$name}"
            MessageReference(welcome) -> "{welcome}"
            TermReference(-brand) -> "{-brand}"
            FunctionReference(NUMBER) -> "{NUMBER(...)}"
            SelectExpression($count) -> "{{$count} -> ...}"
        """
        # Depth protection: prevent recursion overflow on adversarial ASTs
        if depth <= 0:
            return FALLBACK_INVALID

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
            case SelectExpression():
                # Provide context by showing the selector expression
                selector_fallback = self._get_fallback_for_placeable(expr.selector, depth - 1)
                return f"{{{selector_fallback} -> ...}}"
            case _:
                return FALLBACK_INVALID
