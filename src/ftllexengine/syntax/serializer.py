"""Serialize Fluent AST back to FTL syntax.

Converts AST nodes to FTL source code. Useful for:
- Formatters
- Code generators
- Property-based testing (roundtrip: parse → serialize → parse)

Security:
- DepthGuard protects against stack overflow from deeply nested ASTs.
- Maximum nesting depth defaults to 100 (matching parser limit).
- Raises SerializationDepthError on overflow (not RecursionError).

Python 3.13+.
"""

from __future__ import annotations

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.core.depth_guard import DepthGuard, DepthLimitExceededError
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

__all__ = [
    "SerializationDepthError",
    "SerializationValidationError",
    "serialize",
]


class SerializationValidationError(ValueError):
    """Raised when AST validation fails during serialization.

    This error indicates the AST structure would produce invalid FTL syntax.
    Common causes:
    - SelectExpression without exactly one default variant
    - Malformed AST nodes from programmatic construction
    """


class SerializationDepthError(ValueError):
    """Raised when AST nesting exceeds maximum serialization depth.

    This error indicates the AST is too deeply nested for safe serialization.
    Prevents stack overflow from:
    - Adversarially constructed ASTs with excessive Placeable nesting
    - Malformed programmatic AST construction

    The default limit is 100, matching the parser's maximum nesting depth.
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

    def serialize(
        self,
        resource: Resource,
        *,
        validate: bool = True,
        max_depth: int = MAX_DEPTH,
    ) -> str:
        """Serialize Resource to FTL string.

        Pure function - builds output locally without mutating instance state.
        Thread-safe and reusable.

        Args:
            resource: Resource AST node
            validate: If True, validate AST before serialization (default: True).
                     Checks that SelectExpressions have exactly one default variant.
                     Set to False only for trusted ASTs from the parser.
            max_depth: Maximum nesting depth (default: 100). Prevents stack
                      overflow from adversarial or malformed ASTs.

        Returns:
            FTL source code

        Raises:
            SerializationValidationError: If validate=True and AST is invalid
            SerializationDepthError: If AST nesting exceeds max_depth
        """
        if validate:
            _validate_resource(resource)

        output: list[str] = []
        depth_guard = DepthGuard(max_depth=max_depth)

        try:
            self._serialize_resource(resource, output, depth_guard)
        except DepthLimitExceededError as e:
            msg = f"AST nesting exceeds maximum depth ({max_depth})"
            raise SerializationDepthError(msg) from e

        return "".join(output)

    def _serialize_resource(
        self, node: Resource, output: list[str], depth_guard: DepthGuard
    ) -> None:
        """Serialize Resource to output list."""
        for i, entry in enumerate(node.entries):
            if i > 0:
                output.append("\n")
            self._serialize_entry(entry, output, depth_guard)

    def _serialize_entry(
        self,
        entry: Message | Term | Comment | Junk,
        output: list[str],
        depth_guard: DepthGuard,
    ) -> None:
        """Serialize a top-level entry."""
        match entry:
            case Message():
                self._serialize_message(entry, output, depth_guard)
            case Term():
                self._serialize_term(entry, output, depth_guard)
            case Comment():
                self._serialize_comment(entry, output)
            case Junk():
                self._serialize_junk(entry, output)

    def _serialize_message(
        self, node: Message, output: list[str], depth_guard: DepthGuard
    ) -> None:
        """Serialize Message."""
        # Comment if present (attached comment, no blank line before message)
        # Per Fluent spec, attached comments (#) should immediately precede their entry
        if node.comment:
            self._serialize_comment(node.comment, output)

        # Message ID
        output.append(node.id.name)

        # Value
        if node.value:
            output.append(" = ")
            self._serialize_pattern(node.value, output, depth_guard)

        # Attributes
        for attr in node.attributes:
            output.append(_ATTR_INDENT)
            self._serialize_attribute(attr, output, depth_guard)

        output.append("\n")

    def _serialize_term(
        self, node: Term, output: list[str], depth_guard: DepthGuard
    ) -> None:
        """Serialize Term."""
        # Comment if present (attached comment, no blank line before term)
        # Per Fluent spec, attached comments (#) should immediately precede their entry
        if node.comment:
            self._serialize_comment(node.comment, output)

        # Term ID (with leading -)
        output.append(f"-{node.id.name} = ")

        # Value
        self._serialize_pattern(node.value, output, depth_guard)

        # Attributes
        for attr in node.attributes:
            output.append(_ATTR_INDENT)
            self._serialize_attribute(attr, output, depth_guard)

        output.append("\n")

    def _serialize_attribute(
        self, node: Attribute, output: list[str], depth_guard: DepthGuard
    ) -> None:
        """Serialize Attribute."""
        output.append(f".{node.id.name} = ")
        self._serialize_pattern(node.value, output, depth_guard)

    def _serialize_comment(self, node: Comment, output: list[str]) -> None:
        """Serialize Comment.

        Note: Content should NOT have trailing newlines. The parser produces
        content without trailing newlines (e.g., "Line1\\nLine2", not "Line1\\nLine2\\n").
        If manually constructed AST nodes include trailing newlines, they will
        produce extra empty comment lines, which is arguably the correct behavior
        for the content provided.
        """
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
        """Serialize Junk (keep as-is).

        Only appends newline if content doesn't already end with one,
        preventing redundant blank lines in parse/serialize cycles.
        """
        output.append(node.content)
        if not node.content.endswith("\n"):
            output.append("\n")

    def _serialize_pattern(
        self, pattern: Pattern, output: list[str], depth_guard: DepthGuard
    ) -> None:
        """Serialize Pattern elements.

        Per Fluent Spec 1.0: Backslash has no escaping power in TextElements.
        Literal braces MUST be expressed as StringLiterals within Placeables:
        - { must be serialized as {"{"} (Placeable containing StringLiteral)
        - } must be serialized as {"}"} (Placeable containing StringLiteral)

        Multi-line patterns: Newlines in text elements are followed by
        4-space indentation to create valid continuation lines for roundtrip.

        This ensures output is valid FTL that compliant parsers accept.
        """
        for element in pattern.elements:
            if isinstance(element, TextElement):
                # Per Fluent spec: no escape sequences in TextElements
                # Literal braces must become Placeable(StringLiteral("{"/"}")
                text = element.value

                # Handle newlines: add indentation after each newline for continuation
                if "\n" in text:
                    text = text.replace("\n", "\n    ")

                if "{" in text or "}" in text:
                    # Split and emit braces as StringLiteral Placeables
                    self._serialize_text_with_braces(text, output)
                else:
                    # No special characters - emit directly
                    output.append(text)
            elif isinstance(element, Placeable):
                output.append("{ ")
                with depth_guard:
                    self._serialize_expression(element.expression, output, depth_guard)
                output.append(" }")

    def _serialize_text_with_braces(self, text: str, output: list[str]) -> None:
        """Serialize text containing literal braces per Fluent spec.

        Converts literal { and } characters to Placeable(StringLiteral) form.
        Example: "a{b}c" becomes: a{"{"}b{"}"}c
        """
        # Collect runs of non-brace characters for efficiency
        buffer: list[str] = []

        for char in text:
            if char == "{":
                # Flush buffer, emit brace as StringLiteral Placeable
                if buffer:
                    output.append("".join(buffer))
                    buffer.clear()
                output.append('{ "{" }')
            elif char == "}":
                # Flush buffer, emit brace as StringLiteral Placeable
                if buffer:
                    output.append("".join(buffer))
                    buffer.clear()
                output.append('{ "}" }')
            else:
                buffer.append(char)

        # Flush remaining buffer
        if buffer:
            output.append("".join(buffer))

    def _serialize_expression(  # noqa: PLR0912  # Branches required by Expression union type
        self, expr: Expression, output: list[str], depth_guard: DepthGuard
    ) -> None:
        """Serialize Expression nodes using structural pattern matching.

        Handles all Expression types including nested Placeables (valid per FTL spec).
        """
        match expr:
            case StringLiteral():
                # Escape special characters per FTL spec
                # Uses \uHHHH for ALL control characters (< 0x20 and 0x7F)
                # to produce robust output that works in all editors and parsers
                result: list[str] = []
                for char in expr.value:
                    code = ord(char)
                    if char == "\\":
                        result.append("\\\\")
                    elif char == '"':
                        result.append('\\"')
                    elif code < 0x20 or code == 0x7F:
                        # All control characters: NUL, BEL, BS, TAB, LF, VT, FF, CR, ESC, DEL, etc.
                        result.append(f"\\u{code:04X}")
                    else:
                        result.append(char)
                output.append(f'"{"".join(result)}"')

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
                    self._serialize_call_arguments(expr.arguments, output, depth_guard)

            case FunctionReference():
                output.append(expr.id.name)
                self._serialize_call_arguments(expr.arguments, output, depth_guard)

            case Placeable():
                # Nested Placeable - serialize inner expression with braces
                # Valid per FTL spec: { { $var } } is a nested placeable
                output.append("{ ")
                with depth_guard:
                    self._serialize_expression(expr.expression, output, depth_guard)
                output.append(" }")

            case SelectExpression():
                self._serialize_select_expression(expr, output, depth_guard)

    def _serialize_call_arguments(
        self, args: CallArguments, output: list[str], depth_guard: DepthGuard
    ) -> None:
        """Serialize CallArguments."""
        output.append("(")

        # Positional arguments
        for i, arg in enumerate(args.positional):
            if i > 0:
                output.append(", ")
            self._serialize_expression(arg, output, depth_guard)

        # Named arguments
        named_arg: NamedArgument
        for i, named_arg in enumerate(args.named):
            if i > 0 or args.positional:
                output.append(", ")
            output.append(f"{named_arg.name.name}: ")
            self._serialize_expression(named_arg.value, output, depth_guard)

        output.append(")")

    def _serialize_select_expression(
        self,
        expr: SelectExpression,
        output: list[str],
        depth_guard: DepthGuard,
    ) -> None:
        """Serialize SelectExpression."""
        self._serialize_expression(expr.selector, output, depth_guard)
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
            self._serialize_pattern(variant.value, output, depth_guard)

        output.append("\n")


def serialize(
    resource: Resource,
    *,
    validate: bool = True,
    max_depth: int = MAX_DEPTH,
) -> str:
    """Serialize Resource to FTL string.

    Convenience function for FluentSerializer.serialize().

    Args:
        resource: Resource AST node
        validate: If True, validate AST before serialization (default: True).
                 Checks that SelectExpressions have exactly one default variant.
                 Set to False only for trusted ASTs from the parser.
        max_depth: Maximum nesting depth (default: 100). Prevents stack
                  overflow from adversarial or malformed ASTs.

    Returns:
        FTL source code

    Raises:
        SerializationValidationError: If validate=True and AST is invalid
        SerializationDepthError: If AST nesting exceeds max_depth

    Example:
        >>> from ftllexengine.syntax import parse, serialize
        >>> ast = parse("hello = Hello, world!")
        >>> ftl = serialize(ast)
        >>> assert ftl == "hello = Hello, world!\\n"
    """
    serializer = FluentSerializer()
    return serializer.serialize(resource, validate=validate, max_depth=max_depth)
