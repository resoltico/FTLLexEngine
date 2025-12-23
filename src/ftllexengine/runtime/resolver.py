"""Fluent message resolver - converts AST to formatted strings.

Resolves patterns by walking AST, interpolating variables, evaluating selectors.
Python 3.13+. Indirect dependency: Babel (via plural_rules).

Thread Safety:
    Resolution state is passed explicitly via ResolutionContext, making the
    resolver fully reentrant and compatible with async frameworks. Each
    resolution operation creates its own isolated context.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from ftllexengine.diagnostics import (
    ErrorTemplate,
    FluentCyclicReferenceError,
    FluentError,
    FluentReferenceError,
    FluentResolutionError,
)
from ftllexengine.runtime.function_bridge import FluentValue, FunctionRegistry
from ftllexengine.runtime.function_metadata import (
    get_expected_positional_args,
    should_inject_locale,
)
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

# Maximum resolution depth to prevent stack overflow from long non-cyclic chains.
# A chain of 100+ message references is almost certainly a design error.
# This limit prevents RecursionError crashes while allowing reasonable nesting.
MAX_RESOLUTION_DEPTH: int = 100

# Unicode bidirectional isolation characters per Unicode TR9.
# Used to prevent RTL/LTR text interference when interpolating values.
UNICODE_FSI: str = "\u2068"  # U+2068 FIRST STRONG ISOLATE
UNICODE_PDI: str = "\u2069"  # U+2069 POP DIRECTIONAL ISOLATE


@dataclass(slots=True)
class ResolutionContext:
    """Explicit context for message resolution.

    Replaces thread-local state with explicit parameter passing for:
    - Thread safety without global state
    - Async framework compatibility (no thread-local conflicts)
    - Easier testing (no state reset needed)
    - Clear dependency flow

    Attributes:
        stack: Resolution stack for cycle detection (message keys being resolved)
        max_depth: Maximum resolution depth (prevents stack overflow)
    """

    stack: list[str] = field(default_factory=list)
    max_depth: int = MAX_RESOLUTION_DEPTH

    def push(self, key: str) -> None:
        """Push message key onto resolution stack."""
        self.stack.append(key)

    def pop(self) -> str:
        """Pop message key from resolution stack."""
        return self.stack.pop()

    def contains(self, key: str) -> bool:
        """Check if key is in resolution stack (cycle detection)."""
        return key in self.stack

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
    ) -> None:
        """Initialize resolver.

        Args:
            locale: Locale code for plural selection
            messages: Message registry
            terms: Term registry
            function_registry: Function registry with camelCase conversion (keyword-only)
            use_isolating: Wrap interpolated values in Unicode bidi marks (keyword-only)
        """
        self.locale = locale
        self.use_isolating = use_isolating
        self.messages = messages
        self.terms = terms
        self.function_registry = function_registry

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

        Returns:
            Tuple of (formatted_string, errors)
            - formatted_string: Best-effort output (never empty)
            - errors: Tuple of exceptions encountered (immutable)

        Note:
            Per Fluent spec, resolution never fails catastrophically.
            Errors are collected and fallback values are used.
        """
        errors: list[FluentError] = []
        args = args or {}

        # Create fresh context if not provided (top-level call)
        if context is None:
            context = ResolutionContext()

        # Select pattern (value or attribute)
        if attribute:
            attr = next((a for a in message.attributes if a.id.name == attribute), None)
            if not attr:
                error = FluentReferenceError(
                    ErrorTemplate.attribute_not_found(attribute, message.id.name)
                )
                errors.append(error)
                return (f"{{{message.id.name}.{attribute}}}", tuple(errors))
            pattern = attr.value
        else:
            if message.value is None:
                error = FluentReferenceError(ErrorTemplate.message_no_value(message.id.name))
                errors.append(error)
                return (f"{{{message.id.name}}}", tuple(errors))
            pattern = message.value

        # Check for circular references using explicit context
        msg_key = f"{message.id.name}.{attribute}" if attribute else message.id.name
        if context.contains(msg_key):
            cycle_path = context.get_cycle_path(msg_key)
            error = FluentCyclicReferenceError(ErrorTemplate.cyclic_reference(cycle_path))
            errors.append(error)
            return (f"{{{msg_key}}}", tuple(errors))

        # Check for maximum depth (prevents stack overflow from long non-cyclic chains)
        if context.is_depth_exceeded():
            error = FluentReferenceError(
                ErrorTemplate.max_depth_exceeded(msg_key, context.max_depth)
            )
            errors.append(error)
            return (f"{{{msg_key}}}", tuple(errors))

        try:
            context.push(msg_key)
            result = self._resolve_pattern(pattern, args, errors, context)
            return (result, tuple(errors))
        finally:
            context.pop()

    def _resolve_pattern(
        self,
        pattern: Pattern,
        args: Mapping[str, FluentValue],
        errors: list[FluentError],
        context: ResolutionContext,
    ) -> str:
        """Resolve pattern by walking elements."""
        result = ""

        for element in pattern.elements:
            match element:
                case TextElement():
                    result += element.value
                case Placeable():
                    try:
                        value = self._resolve_expression(element.expression, args, errors, context)
                        formatted = self._format_value(value)

                        # Wrap in Unicode bidi isolation marks (FSI/PDI)
                        # Per Unicode TR9, prevents RTL/LTR text interference
                        if self.use_isolating:
                            result += f"{UNICODE_FSI}{formatted}{UNICODE_PDI}"
                        else:
                            result += formatted

                    except (FluentReferenceError, FluentResolutionError) as e:
                        # Mozilla-aligned error handling:
                        # Collect error, show readable fallback (not {ERROR: ...})
                        errors.append(e)
                        fallback = self._get_fallback_for_placeable(element.expression)
                        result += fallback

        return result

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
                return self._resolve_variable_reference(expr, args)
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
                return self._resolve_expression(expr.expression, args, errors, context)
            case _:
                raise FluentResolutionError(ErrorTemplate.unknown_expression(type(expr).__name__))

    def _resolve_variable_reference(
        self, expr: VariableReference, args: Mapping[str, FluentValue]
    ) -> FluentValue:
        """Resolve variable reference from args."""
        var_name = expr.id.name
        if var_name not in args:
            raise FluentReferenceError(ErrorTemplate.variable_not_provided(var_name))
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
        """Resolve term reference with cycle detection."""
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
            return f"{{{term_key}}}"

        # Check for maximum depth
        if context.is_depth_exceeded():
            depth_error = FluentReferenceError(
                ErrorTemplate.max_depth_exceeded(term_key, context.max_depth)
            )
            errors.append(depth_error)
            return f"{{{term_key}}}"

        try:
            context.push(term_key)
            return self._resolve_pattern(pattern, args, errors, context)
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
                case NumberLiteral(value=key_value):
                    if isinstance(selector_value, (int, float)) and key_value == selector_value:
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
        """
        # Evaluate selector
        selector_value = self._resolve_expression(expr.selector, args, errors, context)

        # Handle None consistently with _format_value (which returns "" for None).
        # None represents a missing/undefined value and should NOT match any identifier.
        # Using "" ensures None falls through to the default variant, which is the
        # semantically correct behavior for missing data.
        selector_str = "" if selector_value is None else str(selector_value)

        # Pass 1: Exact match (takes priority)
        exact_match = self._find_exact_variant(expr.variants, selector_value, selector_str)
        if exact_match is not None:
            return self._resolve_pattern(exact_match.value, args, errors, context)

        # Pass 2: Plural category match (numeric selectors only)
        if isinstance(selector_value, (int, float)):
            plural_category = select_plural_category(selector_value, self.locale)
            plural_match = self._find_plural_variant(expr.variants, plural_category)
            if plural_match is not None:
                return self._resolve_pattern(plural_match.value, args, errors, context)

        # Fallback: default variant
        default_variant = self._find_default_variant(expr.variants)
        if default_variant is not None:
            return self._resolve_pattern(default_variant.value, args, errors, context)

        # Fallback: first variant
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

        Returns FluentValue which the resolver will convert to string for final output.
        """
        func_name = func_ref.id.name

        # Evaluate positional arguments
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
        if should_inject_locale(func_name, self.function_registry):
            # Validate arity before injection to provide clear error messages
            # instead of opaque TypeError from incorrect argument positioning
            expected_args = get_expected_positional_args(func_name)
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
                return f"{{${expr.id.name}}}"
            case MessageReference():
                attr_suffix = f".{expr.attribute.name}" if expr.attribute else ""
                return f"{{{expr.id.name}{attr_suffix}}}"
            case TermReference():
                attr_suffix = f".{expr.attribute.name}" if expr.attribute else ""
                return f"{{-{expr.id.name}{attr_suffix}}}"
            case FunctionReference():
                return f"{{{expr.id.name}(...)}}"
            case SelectExpression():
                # Provide context by showing the selector expression
                selector_fallback = self._get_fallback_for_placeable(expr.selector)
                return f"{{{selector_fallback} -> ...}}"
            case _:
                return "{???}"  # Unknown expression type
