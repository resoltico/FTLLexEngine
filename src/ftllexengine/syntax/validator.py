"""Semantic validation for Fluent AST.

Per Fluent spec valid.md, implements two-level validation:
1. Well-formed: Conforms to EBNF grammar (handled by parser)
2. Valid: Passes semantic correctness checks (this module)

The validation process may reject syntax which is well-formed but semantically incorrect.

Includes depth limiting to prevent stack overflow on adversarial or malformed ASTs.

References:
- Fluent spec: valid.md
- Example: message.attr(param: "val") is well-formed but invalid
  (message attributes cannot be parameterized, only terms can)
"""

from decimal import Decimal, InvalidOperation

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.core.depth_guard import DepthGuard
from ftllexengine.diagnostics import ValidationResult
from ftllexengine.diagnostics.codes import DiagnosticCode
from ftllexengine.syntax.ast import (
    Annotation,
    Attribute,
    CallArguments,
    Comment,
    Entry,
    Expression,
    FunctionReference,
    Identifier,
    InlineExpression,
    Junk,
    Message,
    MessageReference,
    NumberLiteral,
    Pattern,
    PatternElement,
    Placeable,
    Resource,
    SelectExpression,
    Span,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.validation_helpers import count_default_variants

__all__ = ["SemanticValidator", "validate"]

# Validation error messages keyed by DiagnosticCode
_VALIDATION_MESSAGES: dict[DiagnosticCode, str] = {
    DiagnosticCode.VALIDATION_TERM_NO_VALUE: "Term must have a value",
    DiagnosticCode.VALIDATION_SELECT_NO_DEFAULT: (
        "Select expression must have exactly one default variant"
    ),
    DiagnosticCode.VALIDATION_SELECT_NO_VARIANTS: (
        "Select expression must have at least one variant"
    ),
    DiagnosticCode.VALIDATION_VARIANT_DUPLICATE: (
        "Variant keys must be unique within select expression"
    ),
    DiagnosticCode.VALIDATION_NAMED_ARG_DUPLICATE: "Duplicate named argument",
}


# ============================================================================
# SEMANTIC VALIDATOR
# ============================================================================


class SemanticValidator:
    """Semantic validator for Fluent AST.

    Per Fluent spec valid.md, validates that well-formed AST is semantically correct.

    Thread-safe validator with no mutable instance state.
    All validation state is local to the validate() call.

    Usage:
        validator = SemanticValidator()
        result = validator.validate(resource)
        if not result.is_valid:
            for annotation in result.annotations:
                print(f"{annotation.code}: {annotation.message}")
    """

    def validate(self, resource: Resource) -> ValidationResult:
        """Validate a parsed resource.

        Pure function - builds error list locally without mutating instance state.
        Thread-safe and reusable.

        Includes depth limiting to prevent stack overflow on deeply nested ASTs.

        Args:
            resource: Parsed FTL resource

        Returns:
            ValidationResult with errors (if any)
        """
        errors: list[Annotation] = []
        depth_guard = DepthGuard(max_depth=MAX_DEPTH)

        for entry in resource.entries:
            self._validate_entry(entry, errors, depth_guard)

        return ValidationResult.from_annotations(tuple(errors))

    @staticmethod
    def _add_error(
        errors: list[Annotation],
        code: DiagnosticCode,
        message: str | None = None,
        span: Span | None = None,
        **arguments: str,
    ) -> None:
        """Add a validation error to the errors list.

        Args:
            errors: Error list to append to
            code: DiagnosticCode enum value
            message: Optional custom message (uses default from _VALIDATION_MESSAGES)
            span: Optional source position
            **arguments: Additional error context
        """
        if message is None:
            message = _VALIDATION_MESSAGES.get(code, "Unknown validation error")

        # Convert kwargs dict to immutable tuple of (key, value) pairs
        args_tuple = tuple(arguments.items()) if arguments else None
        errors.append(
            Annotation(
                code=code.name,
                message=message,
                arguments=args_tuple,
                span=span,
            )
        )

    # ========================================================================
    # ENTRY VALIDATION
    # ========================================================================

    def _validate_entry(
        self, entry: Entry, errors: list[Annotation], depth_guard: DepthGuard
    ) -> None:
        """Validate top-level entry using structural pattern matching."""
        match entry:
            case Message():
                self._validate_message(entry, errors, depth_guard)
            case Term():
                self._validate_term(entry, errors, depth_guard)
            case Comment():
                pass  # Comments don't need validation
            case Junk():
                pass  # Junk already represents invalid syntax
            case _:
                # Inline f-string required: splitting into a variable assignment
                # causes MyPy to flag raise as unreachable in exhausted
                # match/case union branches (a MyPy analysis limitation).
                raise TypeError(f"Unexpected entry type: {type(entry)}")  # noqa: EM102

    def _validate_message(
        self, message: Message, errors: list[Annotation], depth_guard: DepthGuard
    ) -> None:
        """Validate message entry.

        Per spec:
        - Messages cannot be parameterized (no call arguments)
        - Message attributes cannot be parameterized
        """
        # Validate value pattern
        if message.value:
            self._validate_pattern(message.value, errors, "message", depth_guard)

        # Validate attributes
        for attr in message.attributes:
            self._validate_attribute(attr, errors, "message", depth_guard)

    def _validate_term(
        self, term: Term, errors: list[Annotation], depth_guard: DepthGuard
    ) -> None:
        """Validate term entry.

        Per spec:
        - Terms must have a value
        - Term values can contain any valid pattern
        """
        # Terms must have a value (enforced by AST, but check anyway)
        if not term.value:
            self._add_error(
                errors,
                DiagnosticCode.VALIDATION_TERM_NO_VALUE,
                span=term.span,
                term_id=term.id.name,
            )
            return  # Cannot validate further without a value

        # Validate value pattern
        self._validate_pattern(term.value, errors, "term", depth_guard)

        # Validate attributes
        for attr in term.attributes:
            self._validate_attribute(attr, errors, "term", depth_guard)

    def _validate_attribute(
        self,
        attribute: Attribute,
        errors: list[Annotation],
        parent_type: str,
        depth_guard: DepthGuard,
    ) -> None:
        """Validate message or term attribute.

        Per spec:
        - Message attributes cannot be parameterized
        - Term attributes can be parameterized
        """
        self._validate_pattern(
            attribute.value, errors, f"{parent_type}_attribute", depth_guard
        )

    # ========================================================================
    # PATTERN VALIDATION
    # ========================================================================

    def _validate_pattern(
        self,
        pattern: Pattern,
        errors: list[Annotation],
        context: str,
        depth_guard: DepthGuard,
    ) -> None:
        """Validate pattern elements."""
        for element in pattern.elements:
            self._validate_pattern_element(element, errors, context, depth_guard)

    def _validate_pattern_element(
        self,
        element: PatternElement,
        errors: list[Annotation],
        context: str,
        depth_guard: DepthGuard,
    ) -> None:
        """Validate pattern element using structural pattern matching."""
        match element:
            case TextElement():
                pass  # Text elements don't need validation
            case Placeable():
                # Track depth to prevent stack overflow on deep nesting
                with depth_guard:
                    self._validate_expression(element.expression, errors, context, depth_guard)
            case _:
                raise TypeError(
                    f"Unexpected pattern element type: {type(element)}"  # noqa: EM102
                )

    # ========================================================================
    # EXPRESSION VALIDATION
    # ========================================================================

    def _validate_expression(
        self,
        expr: Expression,
        errors: list[Annotation],
        context: str,
        depth_guard: DepthGuard,
    ) -> None:
        """Validate expression (select or inline)."""
        if isinstance(expr, SelectExpression):
            self._validate_select_expression(expr, errors, depth_guard)
        else:
            self._validate_inline_expression(expr, errors, context, depth_guard)

    def _validate_inline_expression(
        self,
        expr: InlineExpression,
        errors: list[Annotation],
        context: str,
        depth_guard: DepthGuard,
    ) -> None:
        """Validate inline expression using structural pattern matching."""
        match expr:
            case StringLiteral():
                pass  # String literals always valid
            case NumberLiteral():
                pass  # Number literals always valid
            case VariableReference():
                pass  # Variable references always valid
            case MessageReference():
                # Message references cannot have arguments (grammar-enforced)
                # MessageReference AST has no arguments field, unlike TermReference
                pass
            case TermReference():
                self._validate_term_reference(expr, errors, depth_guard)
            case FunctionReference():
                self._validate_function_reference(expr, errors, depth_guard)
            case Placeable():
                # Track depth for nested Placeables
                with depth_guard:
                    self._validate_expression(expr.expression, errors, context, depth_guard)
            case _:
                raise TypeError(
                    f"Unexpected inline expression type: {type(expr)}"  # noqa: EM102
                )

    def _validate_term_reference(
        self,
        ref: TermReference,
        errors: list[Annotation],
        depth_guard: DepthGuard,
    ) -> None:
        """Validate term reference.

        Per spec:
        - Terms can be called with named arguments (valid)
        - Positional arguments are ignored at runtime (emit warning)
        - Term.attribute can also be called with arguments
        """
        if ref.arguments:
            # Per Fluent spec, terms only accept named arguments.
            # Positional arguments are silently ignored at runtime.
            # Emit warning to catch likely user errors at validation time.
            if ref.arguments.positional:
                self._add_error(
                    errors,
                    DiagnosticCode.VALIDATION_TERM_POSITIONAL_ARGS,
                    message=(
                        f"Term '-{ref.id.name}' called with positional arguments; "
                        f"positional arguments are ignored for term references"
                    ),
                    span=ref.span,
                )
            self._validate_call_arguments(ref.arguments, errors, depth_guard)

    def _validate_function_reference(
        self,
        ref: FunctionReference,
        errors: list[Annotation],
        depth_guard: DepthGuard,
    ) -> None:
        """Validate function reference.

        Per spec:
        - Function names must be uppercase (already validated by parser)
        - Call arguments must be valid
        """
        self._validate_call_arguments(ref.arguments, errors, depth_guard)

    def _validate_call_arguments(
        self,
        args: CallArguments,
        errors: list[Annotation],
        depth_guard: DepthGuard,
    ) -> None:
        """Validate function/term call arguments.

        Per spec, named argument names must be unique.
        """
        # Check: named argument names must be unique
        seen_names: set[str] = set()
        for named_arg in args.named:
            name = named_arg.name.name
            if name in seen_names:
                self._add_error(
                    errors,
                    DiagnosticCode.VALIDATION_NAMED_ARG_DUPLICATE,
                    argument_name=name,
                )
            seen_names.add(name)

        # Validate each argument expression
        # Track depth for each argument to prevent stack overflow on deeply nested arguments
        for pos_arg in args.positional:
            with depth_guard:
                self._validate_inline_expression(
                    pos_arg, errors, "call_argument", depth_guard
                )

        for named_arg in args.named:
            with depth_guard:
                self._validate_inline_expression(
                    named_arg.value, errors, "call_argument", depth_guard
                )

    # ========================================================================
    # SELECT EXPRESSION VALIDATION
    # ========================================================================

    def _validate_select_expression(
        self,
        select: SelectExpression,
        errors: list[Annotation],
        depth_guard: DepthGuard,
    ) -> None:
        """Validate select expression.

        Per spec:
        - Must have at least one variant
        - Must have exactly one default variant (marked with *)
        - Variant keys must be unique
        """
        # Validate selector using the general dispatcher so that nested SelectExpressions
        # (e.g., from direct AST construction) are handled gracefully rather than
        # falling through to the exhaustiveness-guard raise in _validate_inline_expression.
        self._validate_expression(select.selector, errors, "select_selector", depth_guard)

        # Check: must have at least one variant
        if not select.variants:
            self._add_error(errors, DiagnosticCode.VALIDATION_SELECT_NO_VARIANTS)
            return

        # Check: exactly one default variant
        default_count = count_default_variants(select)
        if default_count != 1:
            self._add_error(
                errors,
                DiagnosticCode.VALIDATION_SELECT_NO_DEFAULT,
                message=(
                    f"Select expression must have exactly one default variant, "
                    f"found {default_count}"
                ),
            )

        # Check: variant keys must be unique
        seen_keys: set[str] = set()
        for variant in select.variants:
            key_str = self._variant_key_to_string(variant.key)
            if key_str in seen_keys:
                self._add_error(
                    errors,
                    DiagnosticCode.VALIDATION_VARIANT_DUPLICATE,
                    variant_key=key_str,
                )
            seen_keys.add(key_str)

            # Validate variant value pattern
            self._validate_pattern(variant.value, errors, "select_variant", depth_guard)

    @staticmethod
    def _variant_key_to_string(key: Identifier | NumberLiteral) -> str:
        """Convert variant key to normalized string for uniqueness checking.

        For numeric keys, uses Decimal normalization to ensure 1 == 1.0.
        This prevents false negatives where [1] and [1.0] are incorrectly
        treated as unique when they should be duplicates.
        """
        if isinstance(key, Identifier):
            return key.name
        # key must be NumberLiteral at this point.
        # Normalize numeric value using Decimal for proper equality.
        # Use raw string (original source) instead of value (float) to preserve precision.
        # This matches resolver behavior and prevents false positives for high-precision variants.
        try:
            # Convert raw string to Decimal and normalize to canonical form
            normalized = Decimal(key.raw).normalize()
            # Use fixed-point format ('f') instead of str() to avoid scientific notation
            # str(Decimal("100").normalize()) returns "1E2", but format(..., 'f') returns "100"
            return format(normalized, "f")
        except (ValueError, InvalidOperation):
            # Fallback to raw string if Decimal conversion fails
            return key.raw


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================


def validate(resource: Resource) -> ValidationResult:
    """Validate a Fluent resource for semantic correctness.

    Convenience function for one-off validation.

    Args:
        resource: Parsed FTL resource

    Returns:
        ValidationResult with any errors found

    Example:
        >>> from ftllexengine.syntax.parser import FluentParserV1
        >>> from ftllexengine.syntax.validator import validate
        >>>
        >>> parser = FluentParserV1()
        >>> resource = parser.parse("msg = value")
        >>> result = validate(resource)
        >>> assert result.is_valid
    """
    validator = SemanticValidator()
    return validator.validate(resource)
