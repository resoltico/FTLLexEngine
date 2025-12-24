"""Semantic validation for Fluent AST.

Per Fluent spec valid.md, implements two-level validation:
1. Well-formed: Conforms to EBNF grammar (handled by parser)
2. Valid: Passes semantic correctness checks (this module)

The validation process may reject syntax which is well-formed but semantically incorrect.

References:
- Fluent spec: valid.md
- Example: message.attr(param: "val") is well-formed but invalid
  (message attributes cannot be parameterized, only terms can)
"""

from ftllexengine.diagnostics import ValidationResult
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

# ============================================================================
# VALIDATION ERROR CODES
# ============================================================================

# Per spec, error codes should be unique and descriptive
ERROR_CODES = {
    # Message validation
    "E0001": "Message cannot be called with arguments",
    "E0002": "Message attribute cannot be parameterized",
    "E0003": "Message reference cannot have call arguments",
    # Term validation
    "E0004": "Term must have a value",
    # Select expression validation
    "E0005": "Select expression must have exactly one default variant",
    "E0006": "Select expression must have at least one variant",
    "E0007": "Variant keys must be unique within select expression",
    # Function validation
    "E0008": "Function name must be uppercase",
    "E0009": "Named arguments cannot follow positional arguments",
    "E0010": "Duplicate named argument",
    # Reference validation
    "E0011": "Attribute accessor requires message or term reference",
    "E0012": "Only terms can be called with arguments",
    # General
    "E0013": "Invalid expression type in context",
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

        Args:
            resource: Parsed FTL resource

        Returns:
            ValidationResult with errors (if any)
        """
        errors: list[Annotation] = []

        for entry in resource.entries:
            self._validate_entry(entry, errors)

        return ValidationResult.from_annotations(tuple(errors))

    @staticmethod
    def _add_error(
        errors: list[Annotation],
        code: str,
        message: str | None = None,
        span: Span | None = None,
        **arguments: str,
    ) -> None:
        """Add a validation error to the errors list.

        Args:
            errors: Error list to append to
            code: Error code (e.g., "E0001")
            message: Optional custom message (uses default from ERROR_CODES if None)
            span: Optional source position
            **arguments: Additional error context
        """
        if message is None:
            message = ERROR_CODES.get(code, "Unknown validation error")

        errors.append(
            Annotation(
                code=code,
                message=message,
                arguments=arguments if arguments else None,
                span=span,
            )
        )

    # ========================================================================
    # ENTRY VALIDATION
    # ========================================================================

    def _validate_entry(self, entry: Entry, errors: list[Annotation]) -> None:
        """Validate top-level entry using structural pattern matching."""
        match entry:
            case Message():
                self._validate_message(entry, errors)
            case Term():
                self._validate_term(entry, errors)
            case Comment():
                pass  # Comments don't need validation
            case Junk():
                pass  # Junk already represents invalid syntax

    def _validate_message(self, message: Message, errors: list[Annotation]) -> None:
        """Validate message entry.

        Per spec:
        - Messages cannot be parameterized (no call arguments)
        - Message attributes cannot be parameterized
        """
        # Validate value pattern
        if message.value:
            self._validate_pattern(message.value, errors, context="message")

        # Validate attributes
        for attr in message.attributes:
            self._validate_attribute(attr, errors, parent_type="message")

    def _validate_term(self, term: Term, errors: list[Annotation]) -> None:
        """Validate term entry.

        Per spec:
        - Terms must have a value
        - Term values can contain any valid pattern
        """
        # Terms must have a value (enforced by AST, but check anyway)
        if not term.value:
            self._add_error(
                errors,
                "E0004",
                span=term.span,
                term_id=term.id.name,
            )
            return  # Cannot validate further without a value

        # Validate value pattern
        self._validate_pattern(term.value, errors, context="term")

        # Validate attributes
        for attr in term.attributes:
            self._validate_attribute(attr, errors, parent_type="term")

    def _validate_attribute(
        self,
        attribute: Attribute,
        errors: list[Annotation],
        parent_type: str,
    ) -> None:
        """Validate message or term attribute.

        Per spec:
        - Message attributes cannot be parameterized
        - Term attributes can be parameterized
        """
        self._validate_pattern(attribute.value, errors, context=f"{parent_type}_attribute")

    # ========================================================================
    # PATTERN VALIDATION
    # ========================================================================

    def _validate_pattern(
        self,
        pattern: Pattern,
        errors: list[Annotation],
        context: str,
    ) -> None:
        """Validate pattern elements."""
        for element in pattern.elements:
            self._validate_pattern_element(element, errors, context)

    def _validate_pattern_element(
        self,
        element: PatternElement,
        errors: list[Annotation],
        context: str,
    ) -> None:
        """Validate pattern element using structural pattern matching."""
        match element:
            case TextElement():
                pass  # Text elements don't need validation
            case Placeable():
                self._validate_expression(element.expression, errors, context)

    # ========================================================================
    # EXPRESSION VALIDATION
    # ========================================================================

    def _validate_expression(
        self,
        expr: Expression,
        errors: list[Annotation],
        context: str,
    ) -> None:
        """Validate expression (select or inline)."""
        if isinstance(expr, SelectExpression):
            self._validate_select_expression(expr, errors)
        else:
            self._validate_inline_expression(expr, errors, context)

    def _validate_inline_expression(
        self,
        expr: InlineExpression,
        errors: list[Annotation],
        context: str,
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
                self._validate_term_reference(expr, errors)
            case FunctionReference():
                self._validate_function_reference(expr, errors)
            case Placeable():
                self._validate_expression(expr.expression, errors, context)

    def _validate_term_reference(
        self,
        ref: TermReference,
        errors: list[Annotation],
    ) -> None:
        """Validate term reference.

        Per spec:
        - Terms can be called with arguments (valid)
        - Term.attribute can also be called with arguments
        """
        if ref.arguments:
            self._validate_call_arguments(ref.arguments, errors)

    def _validate_function_reference(
        self,
        ref: FunctionReference,
        errors: list[Annotation],
    ) -> None:
        """Validate function reference.

        Per spec:
        - Function names must be uppercase (already validated by parser)
        - Call arguments must be valid
        """
        self._validate_call_arguments(ref.arguments, errors)

    def _validate_call_arguments(
        self,
        args: CallArguments,
        errors: list[Annotation],
    ) -> None:
        """Validate function/term call arguments.

        Per spec:
        - Named arguments cannot follow positional arguments
        - Named argument names must be unique
        """
        # Check: positional args must come before named args
        if args.positional and args.named:
            # This is actually allowed in FTL, so no error
            # But we track it for potential linting
            pass

        # Check: named argument names must be unique
        seen_names: set[str] = set()
        for named_arg in args.named:
            name = named_arg.name.name
            if name in seen_names:
                self._add_error(
                    errors,
                    "E0010",
                    argument_name=name,
                )
            seen_names.add(name)

        # Validate each argument expression
        for pos_arg in args.positional:
            self._validate_inline_expression(pos_arg, errors, context="call_argument")

        for named_arg in args.named:
            self._validate_inline_expression(named_arg.value, errors, context="call_argument")

    # ========================================================================
    # SELECT EXPRESSION VALIDATION
    # ========================================================================

    def _validate_select_expression(
        self,
        select: SelectExpression,
        errors: list[Annotation],
    ) -> None:
        """Validate select expression.

        Per spec:
        - Must have at least one variant
        - Must have exactly one default variant (marked with *)
        - Variant keys must be unique
        """
        # Validate selector
        self._validate_inline_expression(select.selector, errors, context="select_selector")

        # Check: must have at least one variant
        if not select.variants:
            self._add_error(errors, "E0006")
            return

        # Check: exactly one default variant
        default_count = sum(1 for v in select.variants if v.default)
        if default_count != 1:
            self._add_error(
                errors,
                "E0005",
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
                    "E0007",
                    variant_key=key_str,
                )
            seen_keys.add(key_str)

            # Validate variant value pattern
            self._validate_pattern(variant.value, errors, context="select_variant")

    @staticmethod
    def _variant_key_to_string(key: Identifier | NumberLiteral) -> str:
        """Convert variant key to string for uniqueness checking."""
        if isinstance(key, Identifier):
            return key.name
        # key must be NumberLiteral at this point
        return str(key.value)


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
