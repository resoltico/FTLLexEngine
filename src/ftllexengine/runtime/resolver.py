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

from collections.abc import Mapping, Sequence
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from decimal import Decimal

from ftllexengine.constants import (
    FALLBACK_FUNCTION_ERROR,
    FALLBACK_INVALID,
    FALLBACK_MISSING_MESSAGE,
    FALLBACK_MISSING_TERM,
    FALLBACK_MISSING_VARIABLE,
    MAX_DEPTH,
)
from ftllexengine.core.babel_compat import BabelImportError
from ftllexengine.core.depth_guard import DepthGuard, depth_clamp
from ftllexengine.core.errors import FormattingError
from ftllexengine.diagnostics import (
    ErrorTemplate,
    FluentCyclicReferenceError,
    FluentError,
    FluentReferenceError,
    FluentResolutionError,
)
from ftllexengine.runtime.function_bridge import FluentNumber, FluentValue, FunctionRegistry
from ftllexengine.runtime.plural_rules import select_plural_category
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

# Re-export FluentValue for public API compatibility
# Canonical definition is in function_bridge.py to avoid circular imports
__all__ = ["FluentResolver", "FluentValue", "ResolutionContext"]

# Unicode bidirectional isolation characters per Unicode TR9.
# Used to prevent RTL/LTR text interference when interpolating values.
UNICODE_FSI: str = "\u2068"  # U+2068 FIRST STRONG ISOLATE
UNICODE_PDI: str = "\u2069"  # U+2069 POP DIRECTIONAL ISOLATE

# Global resolution depth tracking via contextvars.
# Prevents custom functions from bypassing depth limits by calling back into
# bundle.format_pattern(). Each async task/thread maintains independent state.
# This tracks the number of nested resolve_message() calls across all contexts.
_global_resolution_depth: ContextVar[int] = ContextVar(
    "fluent_resolution_depth", default=0
)


class GlobalDepthGuard:
    """Context manager for tracking global resolution depth across format_pattern calls.

    Uses contextvars for async-safe per-task state. This prevents custom functions
    from bypassing depth limits by creating new ResolutionContext instances.

    Usage:
        with GlobalDepthGuard(max_depth=100):
            # Nested format_pattern calls are tracked globally
            result = resolver.resolve_message(message, args)

    Security:
        Without global depth tracking, a malicious custom function could:
        1. Receive control during resolution
        2. Call bundle.format_pattern() which creates a fresh ResolutionContext
        3. Repeat step 2 recursively, bypassing per-context depth limits
        4. Eventually cause stack overflow

        GlobalDepthGuard prevents this by tracking depth across all contexts.
    """

    __slots__ = ("_max_depth", "_token")

    def __init__(self, max_depth: int = MAX_DEPTH) -> None:
        """Initialize guard with maximum depth limit."""
        self._max_depth = depth_clamp(max_depth)
        self._token: Token[int] | None = None

    def __enter__(self) -> GlobalDepthGuard:
        """Enter guarded section, increment global depth."""
        current = _global_resolution_depth.get()
        if current >= self._max_depth:
            raise FluentResolutionError(
                ErrorTemplate.expression_depth_exceeded(self._max_depth)
            )
        self._token = _global_resolution_depth.set(current + 1)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit guarded section, restore previous depth."""
        if self._token is not None:
            _global_resolution_depth.reset(self._token)


@dataclass(slots=True)
class ResolutionContext:
    """Explicit context for message resolution.

    Replaces thread-local state with explicit parameter passing for:
    - Thread safety without global state
    - Async framework compatibility (no thread-local conflicts)
    - Easier testing (no state reset needed)
    - Clear dependency flow

    Performance: Uses both list (for ordered path) and set (for O(1) lookup)
    to optimize cycle detection while preserving path information for errors.

    Instance Lifecycle:
        Each resolution operation creates a fresh ResolutionContext instance.
        This ensures complete isolation between concurrent resolutions.
        The per-resolution DepthGuard allocation is intentional for thread safety;
        object pooling is not used to avoid synchronization overhead.

    Attributes:
        stack: Resolution stack for cycle detection (message keys being resolved)
        _seen: Set for O(1) membership checking (internal)
        max_depth: Maximum resolution depth (prevents stack overflow)
        max_expression_depth: Maximum expression nesting depth
        _expression_guard: DepthGuard for expression depth tracking (internal)
    """

    stack: list[str] = field(default_factory=list)
    _seen: set[str] = field(default_factory=set)
    max_depth: int = MAX_DEPTH
    max_expression_depth: int = MAX_DEPTH
    _expression_guard: DepthGuard = field(init=False)

    def __post_init__(self) -> None:
        """Initialize the expression depth guard with configured max depth."""
        self._expression_guard = DepthGuard(max_depth=self.max_expression_depth)

    def push(self, key: str) -> None:
        """Push message key onto resolution stack."""
        self.stack.append(key)
        self._seen.add(key)

    def pop(self) -> str:
        """Pop message key from resolution stack."""
        key = self.stack.pop()
        self._seen.discard(key)
        return key

    def contains(self, key: str) -> bool:
        """Check if key is in resolution stack (cycle detection).

        Performance: O(1) set lookup instead of O(N) list scan.
        """
        return key in self._seen

    @property
    def depth(self) -> int:
        """Current resolution depth."""
        return len(self.stack)

    def is_depth_exceeded(self) -> bool:
        """Check if maximum depth has been exceeded."""
        return self.depth >= self.max_depth

    def get_cycle_path(self, key: str) -> list[str]:
        """Get the cycle path for error reporting."""
        return [*self.stack, key]

    @property
    def expression_guard(self) -> DepthGuard:
        """Get the expression depth guard for context manager use.

        Usage:
            with context.expression_guard:
                result = self._resolve_expression(nested_expr, ...)
        """
        return self._expression_guard

    @property
    def expression_depth(self) -> int:
        """Current expression nesting depth (read-only, delegates to guard)."""
        return self._expression_guard.current_depth


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
        "_max_nesting_depth",
        "function_registry",
        "locale",
        "messages",
        "terms",
        "use_isolating",
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
    ) -> None:
        """Initialize resolver.

        Args:
            locale: Locale code for plural selection
            messages: Message registry
            terms: Term registry
            function_registry: Function registry with camelCase conversion (keyword-only)
            use_isolating: Wrap interpolated values in Unicode bidi marks (keyword-only)
            max_nesting_depth: Maximum resolution depth limit (keyword-only)
        """
        self.locale = locale
        self.use_isolating = use_isolating
        self.messages = messages
        self.terms = terms
        self.function_registry = function_registry
        self._max_nesting_depth = depth_clamp(max_nesting_depth)

    def resolve_message(
        self,
        message: Message,
        args: Mapping[str, FluentValue] | None = None,
        attribute: str | None = None,
        *,
        context: ResolutionContext | None = None,
    ) -> tuple[str, tuple[FluentError, ...]]:
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
            - errors: Tuple of FluentError instances encountered (immutable)

        Note:
            Per Fluent spec, resolution never fails catastrophically.
            Errors are collected and fallback values are used.

            Attribute resolution uses last-wins semantics for duplicate attribute
            names. If a message contains multiple attributes with the same name
            (which triggers a validation warning), the last definition is used
            during resolution. This matches the Fluent specification and Mozilla
            reference implementation behavior.
        """
        errors: list[FluentError] = []
        args = args or {}

        # Create fresh context if not provided (top-level call)
        if context is None:
            context = ResolutionContext(
                max_depth=self._max_nesting_depth,
                max_expression_depth=self._max_nesting_depth,
            )

        # Select pattern (value or attribute)
        if attribute:
            attr = next((a for a in reversed(message.attributes) if a.id.name == attribute), None)
            if not attr:
                error = FluentReferenceError(
                    ErrorTemplate.attribute_not_found(attribute, message.id.name)
                )
                errors.append(error)
                fallback = FALLBACK_MISSING_MESSAGE.format(id=f"{message.id.name}.{attribute}")
                return (fallback, tuple(errors))
            pattern = attr.value
        else:
            if message.value is None:
                error = FluentReferenceError(ErrorTemplate.message_no_value(message.id.name))
                errors.append(error)
                fallback = FALLBACK_MISSING_MESSAGE.format(id=message.id.name)
                return (fallback, tuple(errors))
            pattern = message.value

        # Check for circular references using explicit context
        msg_key = f"{message.id.name}.{attribute}" if attribute else message.id.name
        if context.contains(msg_key):
            cycle_path = context.get_cycle_path(msg_key)
            error = FluentCyclicReferenceError(ErrorTemplate.cyclic_reference(cycle_path))
            errors.append(error)
            fallback = FALLBACK_MISSING_MESSAGE.format(id=msg_key)
            return (fallback, tuple(errors))

        # Check for maximum depth (prevents stack overflow from long non-cyclic chains)
        if context.is_depth_exceeded():
            error = FluentReferenceError(
                ErrorTemplate.max_depth_exceeded(msg_key, context.max_depth)
            )
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
        except FluentResolutionError as e:
            # Global depth exceeded - collect error and return fallback
            errors.append(e)
            fallback = FALLBACK_MISSING_MESSAGE.format(id=msg_key)
            return (fallback, tuple(errors))

    def _resolve_pattern(
        self,
        pattern: Pattern,
        args: Mapping[str, FluentValue],
        errors: list[FluentError],
        context: ResolutionContext,
    ) -> str:
        """Resolve pattern by walking elements.

        Uses list accumulation with join() for O(N) performance instead of
        repeated string concatenation which is O(N^2).
        """
        parts: list[str] = []

        for element in pattern.elements:
            match element:
                case TextElement():
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

                        # Wrap in Unicode bidi isolation marks (FSI/PDI)
                        # Per Unicode TR9, prevents RTL/LTR text interference
                        if self.use_isolating:
                            parts.append(f"{UNICODE_FSI}{formatted}{UNICODE_PDI}")
                        else:
                            parts.append(formatted)

                    except (FluentReferenceError, FluentResolutionError) as e:
                        # Mozilla-aligned error handling:
                        # Collect error, show readable fallback (not {ERROR: ...})
                        errors.append(e)
                        # Use pattern matching for type-safe fallback extraction
                        match e:
                            case FormattingError(fallback_value=fallback):
                                # FormattingError carries the original value as fallback
                                parts.append(fallback)
                            case _:
                                parts.append(self._get_fallback_for_placeable(element.expression))

        return "".join(parts)

    def _resolve_expression(  # noqa: PLR0911  # Complex dispatch logic expected
        self,
        expr: Expression,
        args: Mapping[str, FluentValue],
        errors: list[FluentError],
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
                raise FluentResolutionError(ErrorTemplate.unknown_expression(type(expr).__name__))

    def _resolve_variable_reference(
        self,
        expr: VariableReference,
        args: Mapping[str, FluentValue],
        context: ResolutionContext,
    ) -> FluentValue:
        """Resolve variable reference from args."""
        var_name = expr.id.name
        if var_name not in args:
            # Include resolution path for debugging nested references
            resolution_path = tuple(context.stack) if context.stack else None
            raise FluentReferenceError(
                ErrorTemplate.variable_not_provided(
                    var_name, resolution_path=resolution_path
                )
            )
        return args[var_name]

    def _resolve_message_reference(
        self,
        expr: MessageReference,
        args: Mapping[str, FluentValue],
        errors: list[FluentError],
        context: ResolutionContext,
    ) -> str:
        """Resolve message reference."""
        msg_id = expr.id.name
        if msg_id not in self.messages:
            raise FluentReferenceError(ErrorTemplate.message_not_found(msg_id))
        message = self.messages[msg_id]
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
        errors: list[FluentError],
        context: ResolutionContext,
    ) -> str:
        """Resolve term reference with cycle detection and argument handling.

        Per Fluent spec, terms can be parameterized with arguments:
            -brand(case: "nominative")

        Term arguments are evaluated and merged into the resolution context,
        allowing term patterns to reference them as variables.
        """
        term_id = expr.id.name
        if term_id not in self.terms:
            raise FluentReferenceError(ErrorTemplate.term_not_found(term_id))
        term = self.terms[term_id]

        # Select pattern (value or attribute)
        if expr.attribute:
            attr = next((a for a in term.attributes if a.id.name == expr.attribute.name), None)
            if not attr:
                raise FluentReferenceError(
                    ErrorTemplate.term_attribute_not_found(expr.attribute.name, term_id)
                )
            pattern = attr.value
        else:
            pattern = term.value

        # Build term key for cycle detection (use -prefix to match FTL syntax)
        term_key = f"-{term_id}.{expr.attribute.name}" if expr.attribute else f"-{term_id}"

        # Check for circular references
        if context.contains(term_key):
            cycle_path = context.get_cycle_path(term_key)
            cycle_error = FluentCyclicReferenceError(ErrorTemplate.cyclic_reference(cycle_path))
            errors.append(cycle_error)
            # term_key already has '-' prefix, strip it for the template
            return FALLBACK_MISSING_TERM.format(name=term_key.lstrip("-"))

        # Check for maximum depth
        if context.is_depth_exceeded():
            depth_error = FluentReferenceError(
                ErrorTemplate.max_depth_exceeded(term_key, context.max_depth)
            )
            errors.append(depth_error)
            # term_key already has '-' prefix, strip it for the template
            return FALLBACK_MISSING_TERM.format(name=term_key.lstrip("-"))

        # Evaluate term arguments - terms are ISOLATED from calling context
        # Per Fluent spec: terms can ONLY access explicitly passed arguments
        # https://projectfluent.org/fluent/guide/terms.html
        # "Terms receive such data from messages in which they are used"
        # This means ONLY explicit parameterization like -term(arg: val), NOT
        # implicit access to the calling message's $variables.
        term_args: dict[str, FluentValue] = {}
        if expr.arguments is not None:
            # Evaluate named arguments (the primary use case for term args)
            for named_arg in expr.arguments.named:
                arg_name = named_arg.name.name
                arg_value = self._resolve_expression(named_arg.value, args, errors, context)
                term_args[arg_name] = arg_value

            # Evaluate positional arguments (per Fluent spec, term arguments section)
            # Reference: https://projectfluent.org/fluent/guide/terms.html#parameterized-terms
            # The spec defines term arguments as named only (e.g., -term(case: "gen")).
            # Positional arguments in term references are technically parsed but have
            # no binding semantics - there's no parameter name to assign the value to.
            # We evaluate them to catch expression errors but discard the result.
            if expr.arguments.positional:
                for pos_arg in expr.arguments.positional:
                    self._resolve_expression(pos_arg, args, errors, context)

                # Emit warning that positional arguments are ignored
                errors.append(
                    FluentResolutionError(
                        ErrorTemplate.term_positional_args_ignored(
                            term_name=term_id,
                            count=len(expr.arguments.positional),
                        )
                    )
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
                    # Handle int, float, Decimal, and FluentNumber for exact numeric match.
                    # Use raw string representation for maximum precision.
                    # Problem: float(1.1) != Decimal("1.1") due to IEEE 754.
                    # Solution: Use NumberLiteral.raw (exact source string) for key,
                    # and convert selector to Decimal via str for comparison.
                    # Edge case: Float arithmetic results (e.g., 0.1 + 0.2) may produce
                    # values like 0.30000000000000004 that won't match literal "0.3".
                    # For exact matching with computed values, use Decimal arithmetic.
                    # Note: Exclude bool since isinstance(True, int) is True in Python,
                    # but str(True) == "True" which is not a valid Decimal.
                    #
                    # FluentNumber wraps formatted numbers (from NUMBER() function) while
                    # preserving the original numeric value for matching. Extract .value
                    # for numeric comparison so [1000] matches FluentNumber(1000, "1,000").
                    numeric_for_match: int | float | Decimal | None = None
                    if isinstance(selector_value, FluentNumber):
                        numeric_for_match = selector_value.value
                    elif (
                        isinstance(selector_value, (int, float, Decimal))
                        and not isinstance(selector_value, bool)
                    ):
                        numeric_for_match = selector_value

                    if numeric_for_match is not None:
                        # Use raw string for key to preserve exact source precision
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
        errors: list[FluentError],
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
        except (FluentReferenceError, FluentResolutionError) as e:
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
        # Note: Exclude bool since isinstance(True, int) is True in Python,
        # but booleans should match [true]/[false] variants, not plural categories.
        #
        # Extract numeric value from FluentNumber for plural matching.
        numeric_value: int | float | Decimal | None = None
        if isinstance(selector_value, FluentNumber):
            numeric_value = selector_value.value
        elif isinstance(selector_value, (int, float, Decimal)) and not isinstance(
            selector_value, bool
        ):
            numeric_value = selector_value

        if numeric_value is not None:
            # Try plural category matching (requires Babel for CLDR data).
            # If Babel is not installed (parser-only mode), skip plural matching
            # and fall through to default variant. This is graceful degradation.
            try:
                plural_category = select_plural_category(numeric_value, self.locale)
                plural_match = self._find_plural_variant(expr.variants, plural_category)
                if plural_match is not None:
                    return self._resolve_pattern(
                        plural_match.value, args, errors, context
                    )
            except BabelImportError:
                # Babel not installed - skip plural matching, fall through to default
                pass

        # Fallback: default variant
        default_variant = self._find_default_variant(expr.variants)
        if default_variant is not None:
            return self._resolve_pattern(default_variant.value, args, errors, context)

        # Fallback: first variant
        if expr.variants:
            return self._resolve_pattern(expr.variants[0].value, args, errors, context)

        raise FluentResolutionError(ErrorTemplate.no_variants())

    def _resolve_fallback_variant(
        self,
        expr: SelectExpression,
        args: Mapping[str, FluentValue],
        errors: list[FluentError],
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
            FluentResolutionError: If no variants exist
        """
        # Try default variant first
        default_variant = self._find_default_variant(expr.variants)
        if default_variant is not None:
            return self._resolve_pattern(default_variant.value, args, errors, context)

        # Fall back to first variant
        if expr.variants:
            return self._resolve_pattern(expr.variants[0].value, args, errors, context)

        raise FluentResolutionError(ErrorTemplate.no_variants())

    def _resolve_function_call(
        self,
        func_ref: FunctionReference,
        args: Mapping[str, FluentValue],
        errors: list[FluentError],
        context: ResolutionContext,
    ) -> FluentValue:
        """Resolve function call.

        Uses FunctionRegistry to handle camelCase → snake_case parameter conversion.
        Uses metadata system to determine if locale injection is needed.

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
        if self.function_registry.should_inject_locale(func_name):
            # Validate arity before injection to provide clear error messages
            # instead of opaque TypeError from incorrect argument positioning
            expected_args = self.function_registry.get_expected_positional_args(func_name)
            if expected_args is not None and len(positional_values) != expected_args:
                raise FluentResolutionError(
                    ErrorTemplate.function_arity_mismatch(
                        func_name, expected_args, len(positional_values)
                    )
                )

            # Built-in formatting functions expect signature: func(value, locale, *, ...)
            # Append locale after positional args (FTL passes exactly one value arg,
            # so this places locale as the second positional argument by contract)
            # FunctionRegistry.call() handles camelCase -> snake_case conversion
            return self.function_registry.call(
                func_name,
                [*positional_values, self.locale],
                named_values,
            )

        # Custom function or built-in that doesn't need locale: pass args as-is
        return self.function_registry.call(
            func_name,
            positional_values,
            named_values,
        )

    def _format_value(self, value: FluentValue) -> str:
        """Format FluentValue to string for final output.

        Handles all types in the FluentValue union:
        - str: returned as-is
        - bool: "true"/"false" (Fluent convention)
        - int/float: string representation
        - Decimal/datetime/date: string representation via __str__
        - None: empty string
        """
        if isinstance(value, str):
            return value
        # Check bool BEFORE int/float (bool is subclass of int in Python)
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if value is None:
            return ""
        # Handles Decimal, datetime, date, and any other types
        return str(value)

    def _get_fallback_for_placeable(self, expr: Expression) -> str:
        """Get readable fallback for failed placeable per Fluent spec.

        Per Fluent specification, when a placeable fails to resolve,
        we return a human-readable representation of what was attempted.
        This is superior to {ERROR: ...} as it:
        1. Doesn't expose internal diagnostics
        2. Shows what the translator expected
        3. Makes errors visible but not alarming

        Args:
            expr: The expression that failed to resolve

        Returns:
            Readable fallback string

        Examples:
            VariableReference($name) -> "{$name}"
            MessageReference(welcome) -> "{welcome}"
            TermReference(-brand) -> "{-brand}"
            FunctionReference(NUMBER) -> "{NUMBER(...)}"
            SelectExpression($count) -> "{{$count} -> ...}"
        """
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
                selector_fallback = self._get_fallback_for_placeable(expr.selector)
                return f"{{{selector_fallback} -> ...}}"
            case _:
                return FALLBACK_INVALID
