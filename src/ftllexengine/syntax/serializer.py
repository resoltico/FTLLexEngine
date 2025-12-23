"""Serialize Fluent AST back to FTL syntax.

Converts AST nodes to FTL source code. Useful for:
- Formatters
- Code generators
- Property-based testing (roundtrip: parse → serialize → parse)

Python 3.13+.
"""

from ftllexengine.enums import CommentType

from .ast import (
    Attribute,
    CallArguments,
    Comment,
    Expression,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    MessageReference,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
)
from .visitor import ASTVisitor


class SerializationValidationError(ValueError):
    """Raised when AST validation fails during serialization.

    This error indicates the AST structure would produce invalid FTL syntax.
    Common causes:
    - SelectExpression without exactly one default variant
    - Malformed AST nodes from programmatic construction
    """


def _validate_select_expression(expr: SelectExpression, context: str) -> None:
    """Validate SelectExpression has exactly one default variant.

    Per FTL spec, every SelectExpression must have exactly one variant
    marked as default with the * prefix.

    Args:
        expr: SelectExpression to validate
        context: Description of location for error message

    Raises:
        SerializationValidationError: If validation fails
    """
    default_count = sum(1 for v in expr.variants if v.default)

    if default_count == 0:
        msg = f"SelectExpression in {context} has no default variant (requires exactly one *[key])"
        raise SerializationValidationError(msg)

    if default_count > 1:
        msg = (
            f"SelectExpression in {context} has {default_count} default variants "
            "(requires exactly one)"
        )
        raise SerializationValidationError(msg)


def _validate_pattern(pattern: Pattern, context: str) -> None:
    """Validate all expressions within a Pattern."""
    for element in pattern.elements:
        if isinstance(element, Placeable):
            _validate_expression(element.expression, context)


def _validate_expression(expr: Expression, context: str) -> None:
    """Validate an Expression recursively."""
    match expr:
        case SelectExpression():
            _validate_select_expression(expr, context)
            # Also validate patterns within variants
            for variant in expr.variants:
                _validate_pattern(variant.value, context)
        case Placeable():
            _validate_expression(expr.expression, context)
        case _:
            pass  # Other expressions don't need validation


def _validate_resource(resource: Resource) -> None:
    """Validate a Resource AST for serialization.

    Checks all SelectExpressions have exactly one default variant.

    Args:
        resource: Resource AST to validate

    Raises:
        SerializationValidationError: If validation fails
    """
    for entry in resource.entries:
        match entry:
            case Message():
                context = f"message '{entry.id.name}'"
                if entry.value:
                    _validate_pattern(entry.value, context)
                for attr in entry.attributes:
                    _validate_pattern(attr.value, f"{context}.{attr.id.name}")
            case Term():
                context = f"term '-{entry.id.name}'"
                _validate_pattern(entry.value, context)
                for attr in entry.attributes:
                    _validate_pattern(attr.value, f"{context}.{attr.id.name}")
            case _:
                pass  # Comments and Junk don't need validation

# FTL indentation constants per Fluent spec.
# Attributes use 4 spaces for standard indentation.
_ATTR_INDENT: str = "\n    "

# Select expression variants use 3 spaces to align with the `*[` marker.
# This produces: "\n   *[key] value" where the `[` aligns with attribute `.`.
_VARIANT_INDENT: str = "\n   "


class FluentSerializer(ASTVisitor):
    """Converts AST back to FTL source string.

    Thread-safe serializer with no mutable instance state.
    All serialization state is local to the serialize() call.

    Usage:
        >>> from ftllexengine.syntax import parse, FluentSerializer
        >>> ast = parse("hello = Hello, world!")
        >>> serializer = FluentSerializer()
        >>> ftl = serializer.serialize(ast)
        >>> print(ftl)
        hello = Hello, world!
    """

    def serialize(self, resource: Resource, *, validate: bool = False) -> str:
        """Serialize Resource to FTL string.

        Pure function - builds output locally without mutating instance state.
        Thread-safe and reusable.

        Args:
            resource: Resource AST node
            validate: If True, validate AST before serialization (default: False).
                     Checks that SelectExpressions have exactly one default variant.

        Returns:
            FTL source code

        Raises:
            SerializationValidationError: If validate=True and AST is invalid
        """
        if validate:
            _validate_resource(resource)

        output: list[str] = []
        self._serialize_resource(resource, output)
        return "".join(output)

    def _serialize_resource(self, node: Resource, output: list[str]) -> None:
        """Serialize Resource to output list."""
        for i, entry in enumerate(node.entries):
            if i > 0:
                output.append("\n")
            self._serialize_entry(entry, output)

    def _serialize_entry(
        self,
        entry: Message | Term | Comment | Junk,
        output: list[str],
    ) -> None:
        """Serialize a top-level entry."""
        match entry:
            case Message():
                self._serialize_message(entry, output)
            case Term():
                self._serialize_term(entry, output)
            case Comment():
                self._serialize_comment(entry, output)
            case Junk():
                self._serialize_junk(entry, output)

    def _serialize_message(self, node: Message, output: list[str]) -> None:
        """Serialize Message."""
        # Comment if present
        if node.comment:
            self._serialize_comment(node.comment, output)
            output.append("\n")

        # Message ID
        output.append(node.id.name)

        # Value
        if node.value:
            output.append(" = ")
            self._serialize_pattern(node.value, output)

        # Attributes
        for attr in node.attributes:
            output.append(_ATTR_INDENT)
            self._serialize_attribute(attr, output)

        output.append("\n")

    def _serialize_term(self, node: Term, output: list[str]) -> None:
        """Serialize Term."""
        # Comment if present
        if node.comment:
            self._serialize_comment(node.comment, output)
            output.append("\n")

        # Term ID (with leading -)
        output.append(f"-{node.id.name} = ")

        # Value
        self._serialize_pattern(node.value, output)

        # Attributes
        for attr in node.attributes:
            output.append(_ATTR_INDENT)
            self._serialize_attribute(attr, output)

        output.append("\n")

    def _serialize_attribute(self, node: Attribute, output: list[str]) -> None:
        """Serialize Attribute."""
        output.append(f".{node.id.name} = ")
        self._serialize_pattern(node.value, output)

    def _serialize_comment(self, node: Comment, output: list[str]) -> None:
        """Serialize Comment."""
        if node.type is CommentType.COMMENT:
            prefix = "#"
        elif node.type is CommentType.GROUP:
            prefix = "##"
        else:  # CommentType.RESOURCE
            prefix = "###"

        lines = node.content.split("\n")
        for line in lines:
            if line:
                output.append(f"{prefix} {line}\n")
            else:
                output.append(f"{prefix}\n")

    def _serialize_junk(self, node: Junk, output: list[str]) -> None:
        """Serialize Junk (keep as-is)."""
        output.append(node.content)
        output.append("\n")

    def _serialize_pattern(self, pattern: Pattern, output: list[str]) -> None:
        """Serialize Pattern elements.

        TextElement values must have special characters escaped per FTL spec:
        - { and } must be escaped as \\{ and \\} to avoid placeable interpretation
        - Backslashes must be escaped first to prevent double-escaping
        """
        for element in pattern.elements:
            if isinstance(element, TextElement):
                # Escape special characters in text elements per FTL spec
                # Order matters: backslash first to avoid double-escaping
                escaped = element.value.replace("\\", "\\\\")
                escaped = escaped.replace("{", "\\{")
                escaped = escaped.replace("}", "\\}")
                output.append(escaped)
            elif isinstance(element, Placeable):
                output.append("{ ")
                self._serialize_expression(element.expression, output)
                output.append(" }")

    def _serialize_expression(self, expr: Expression, output: list[str]) -> None:
        """Serialize Expression nodes using structural pattern matching.

        Handles all Expression types including nested Placeables (valid per FTL spec).
        """
        match expr:
            case StringLiteral():
                # Escape special characters per FTL spec
                # Order matters: backslash first to avoid double-escaping
                escaped = expr.value.replace("\\", "\\\\")
                escaped = escaped.replace('"', '\\"')
                # Control characters prohibited in FTL string literals
                escaped = escaped.replace("\n", "\\u000A")
                escaped = escaped.replace("\r", "\\u000D")
                escaped = escaped.replace("\t", "\\t")
                output.append(f'"{escaped}"')

            case NumberLiteral():
                output.append(expr.raw)

            case VariableReference():
                output.append(f"${expr.id.name}")

            case MessageReference():
                output.append(expr.id.name)
                if expr.attribute:
                    output.append(f".{expr.attribute.name}")

            case TermReference():
                output.append(f"-{expr.id.name}")
                if expr.attribute:
                    output.append(f".{expr.attribute.name}")
                if expr.arguments:
                    self._serialize_call_arguments(expr.arguments, output)

            case FunctionReference():
                output.append(expr.id.name)
                self._serialize_call_arguments(expr.arguments, output)

            case Placeable():
                # Nested Placeable - serialize inner expression with braces
                # Valid per FTL spec: { { $var } } is a nested placeable
                output.append("{ ")
                self._serialize_expression(expr.expression, output)
                output.append(" }")

            case SelectExpression():
                self._serialize_select_expression(expr, output)

    def _serialize_call_arguments(self, args: CallArguments, output: list[str]) -> None:
        """Serialize CallArguments."""
        output.append("(")

        # Positional arguments
        for i, arg in enumerate(args.positional):
            if i > 0:
                output.append(", ")
            self._serialize_expression(arg, output)

        # Named arguments
        named_arg: NamedArgument
        for i, named_arg in enumerate(args.named):
            if i > 0 or args.positional:
                output.append(", ")
            output.append(f"{named_arg.name.name}: ")
            self._serialize_expression(named_arg.value, output)

        output.append(")")

    def _serialize_select_expression(
        self,
        expr: SelectExpression,
        output: list[str],
    ) -> None:
        """Serialize SelectExpression."""
        self._serialize_expression(expr.selector, output)
        output.append(" ->")

        for variant in expr.variants:
            output.append(_VARIANT_INDENT)
            if variant.default:
                output.append("*")
            output.append("[")

            # Variant key (Identifier or NumberLiteral) - explicit match for exhaustiveness
            match variant.key:
                case Identifier():
                    output.append(variant.key.name)
                case NumberLiteral():
                    output.append(variant.key.raw)

            output.append("] ")
            self._serialize_pattern(variant.value, output)

        output.append("\n")


def serialize(resource: Resource, *, validate: bool = False) -> str:
    """Serialize Resource to FTL string.

    Convenience function for FluentSerializer.serialize().

    Args:
        resource: Resource AST node
        validate: If True, validate AST before serialization (default: False).
                 Checks that SelectExpressions have exactly one default variant.

    Returns:
        FTL source code

    Raises:
        SerializationValidationError: If validate=True and AST is invalid

    Example:
        >>> from ftllexengine.syntax import parse, serialize
        >>> ast = parse("hello = Hello, world!")
        >>> ftl = serialize(ast)
        >>> assert ftl == "hello = Hello, world!\\n"
    """
    serializer = FluentSerializer()
    return serializer.serialize(resource, validate=validate)
