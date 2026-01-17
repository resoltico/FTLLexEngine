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

import re

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.core.depth_guard import DepthGuard, DepthLimitExceededError
from ftllexengine.core.identifier_validation import is_valid_identifier
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
from .validation_helpers import count_default_variants
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


def _validate_identifier(identifier: Identifier, context: str) -> None:
    """Validate identifier follows FTL grammar rules.

    Uses unified validation module to ensure consistency between parser
    and serializer. Validates both syntax and length constraints.

    Args:
        identifier: Identifier to validate
        context: Context string for error messages

    Raises:
        SerializationValidationError: If identifier name is invalid
    """
    if not is_valid_identifier(identifier.name):
        msg = (
            f"Invalid identifier '{identifier.name}' in {context}. "
            f"Identifiers must match [a-zA-Z][a-zA-Z0-9_-]* and be ≤256 characters"
        )
        raise SerializationValidationError(msg)


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
    default_count = count_default_variants(expr)

    if default_count == 0:
        msg = f"SelectExpression in {context} has no default variant (requires exactly one *[key])"
        raise SerializationValidationError(msg)

    if default_count > 1:
        msg = (
            f"SelectExpression in {context} has {default_count} default variants "
            "(requires exactly one)"
        )
        raise SerializationValidationError(msg)


def _validate_pattern(pattern: Pattern, context: str, depth_guard: DepthGuard) -> None:
    """Validate all expressions within a Pattern.

    Args:
        pattern: Pattern AST to validate
        context: Context string for error messages
        depth_guard: Depth guard for recursion protection
    """
    for element in pattern.elements:
        if isinstance(element, Placeable):
            with depth_guard:
                _validate_expression(element.expression, context, depth_guard)


def _validate_call_arguments(
    args: CallArguments, context: str, depth_guard: DepthGuard
) -> None:
    """Validate CallArguments per FTL specification.

    Per FTL EBNF:
        NamedArgument ::= Identifier blank? ":" blank? (StringLiteral | NumberLiteral)

    Enforces:
    1. Named argument names must be unique (no duplicates)
    2. Named argument values must be StringLiteral or NumberLiteral

    The parser enforces these constraints during parsing, but programmatically
    constructed ASTs may violate them. This validation catches such errors
    before serialization produces invalid FTL.

    Args:
        args: CallArguments to validate
        context: Context string for error messages
        depth_guard: Depth guard for recursion protection

    Raises:
        SerializationValidationError: If constraints are violated
    """
    # Validate positional arguments
    for pos_arg in args.positional:
        with depth_guard:
            _validate_expression(pos_arg, context, depth_guard)

    # Validate named arguments with duplicate detection and type enforcement
    seen_names: set[str] = set()
    for named_arg in args.named:
        arg_name = named_arg.name.name

        # Check for duplicate named argument names
        if arg_name in seen_names:
            msg = (
                f"Duplicate named argument '{arg_name}' in {context}. "
                "Named argument names must be unique per FTL specification."
            )
            raise SerializationValidationError(msg)
        seen_names.add(arg_name)

        # Validate the identifier
        _validate_identifier(named_arg.name, f"{context}, named argument")

        # Per FTL spec, named argument values must be StringLiteral or NumberLiteral
        if not isinstance(named_arg.value, (StringLiteral, NumberLiteral)):
            value_type = type(named_arg.value).__name__
            msg = (
                f"Named argument '{arg_name}' in {context} has invalid value type "
                f"'{value_type}'. Per FTL specification, named argument values must be "
                "StringLiteral or NumberLiteral, not arbitrary expressions."
            )
            raise SerializationValidationError(msg)

        # No need to recursively validate StringLiteral/NumberLiteral (they have no sub-expressions)


def _validate_expression(expr: Expression, context: str, depth_guard: DepthGuard) -> None:  # noqa: PLR0912
    """Validate an Expression recursively.

    Args:
        expr: Expression AST to validate
        context: Context string for error messages
        depth_guard: Depth guard for recursion protection
    """
    match expr:
        case SelectExpression():
            _validate_select_expression(expr, context)
            # Validate selector expression and variant keys
            with depth_guard:
                _validate_expression(expr.selector, context, depth_guard)
            # Validate variant keys (if Identifier) and patterns
            for variant in expr.variants:
                if isinstance(variant.key, Identifier):
                    _validate_identifier(variant.key, f"{context}, variant key")
                with depth_guard:
                    _validate_pattern(variant.value, context, depth_guard)
        case Placeable():
            with depth_guard:
                _validate_expression(expr.expression, context, depth_guard)
        case VariableReference():
            _validate_identifier(expr.id, f"{context}, variable reference")
        case MessageReference():
            _validate_identifier(expr.id, f"{context}, message reference")
            if expr.attribute:
                _validate_identifier(expr.attribute, f"{context}, message attribute")
        case TermReference():
            _validate_identifier(expr.id, f"{context}, term reference")
            if expr.attribute:
                _validate_identifier(expr.attribute, f"{context}, term attribute")
            if expr.arguments:
                _validate_call_arguments(expr.arguments, context, depth_guard)
        case FunctionReference():
            _validate_identifier(expr.id, f"{context}, function reference")
            if expr.arguments:
                _validate_call_arguments(expr.arguments, context, depth_guard)
        case _:
            pass  # Other expressions (NumberLiteral, StringLiteral) don't need validation


def _validate_resource(resource: Resource, max_depth: int = MAX_DEPTH) -> None:
    """Validate a Resource AST for serialization.

    Checks all SelectExpressions have exactly one default variant.
    Enforces depth limits to prevent stack overflow.

    Args:
        resource: Resource AST to validate
        max_depth: Maximum AST nesting depth (default: MAX_DEPTH)

    Raises:
        SerializationValidationError: If validation fails
        SerializationDepthError: If AST nesting exceeds max_depth
    """
    depth_guard = DepthGuard(max_depth=max_depth)

    try:
        for entry in resource.entries:
            match entry:
                case Message():
                    _validate_identifier(entry.id, "message ID")
                    context = f"message '{entry.id.name}'"
                    if entry.value:
                        _validate_pattern(entry.value, context, depth_guard)
                    for attr in entry.attributes:
                        _validate_identifier(attr.id, f"{context}, attribute ID")
                        _validate_pattern(attr.value, f"{context}.{attr.id.name}", depth_guard)
                case Term():
                    _validate_identifier(entry.id, "term ID")
                    context = f"term '-{entry.id.name}'"
                    _validate_pattern(entry.value, context, depth_guard)
                    for attr in entry.attributes:
                        _validate_identifier(attr.id, f"{context}, attribute ID")
                        _validate_pattern(attr.value, f"{context}.{attr.id.name}", depth_guard)
                case _:
                    pass  # Comments and Junk don't need validation
    except DepthLimitExceededError as e:
        msg = f"Validation depth limit exceeded (max: {max_depth}): {e}"
        raise SerializationDepthError(msg) from e

# FTL indentation constants per Fluent spec.
# Standard continuation indent: 4 spaces.
_CONT_INDENT: str = "    "

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
        >>> from ftllexengine.syntax import parse, serialize
        >>> ast = parse("hello = Hello, world!")
        >>> ftl = serialize(ast)
        >>> print(ftl)
        hello = Hello, world!

    Advanced usage (direct class instantiation):
        >>> from ftllexengine.syntax import parse
        >>> from ftllexengine.syntax.serializer import FluentSerializer
        >>> ast = parse("hello = Hello, world!")
        >>> serializer = FluentSerializer()
        >>> ftl = serializer.serialize(ast)
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
            _validate_resource(resource, max_depth=max_depth)

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
        """Serialize Resource to output list.

        Handles blank line insertion between entries per Fluent spec:
        - Consecutive standalone comments of the same type require a blank
          line between them to prevent merging during re-parse.
        - Messages and terms get standard single newline separation.
        """
        prev_entry: Message | Term | Comment | Junk | None = None

        for entry in node.entries:
            if prev_entry is not None:
                # Skip separator if Junk already contains leading whitespace.
                # Parser includes preceding whitespace in Junk.content for containment,
                # so adding another separator would duplicate newlines on roundtrip.
                if isinstance(entry, Junk) and entry.content and entry.content[0] in "\n ":
                    pass  # Junk content already has leading whitespace
                else:
                    # Determine if we need extra blank line to preserve roundtrip.
                    # Per Fluent spec:
                    # 1. Adjacent comments of the same type without a blank line
                    #    between them are merged. Insert extra newline to preserve.
                    # 2. A comment followed by 0-1 blank lines then a message/term
                    #    becomes an attached comment. If the Comment is a standalone
                    #    entry (in entries[], not as entry.comment), we need 2 blank
                    #    lines to prevent attachment during re-parse.
                    needs_extra_blank = (
                        isinstance(prev_entry, Comment)
                        and isinstance(entry, Comment)
                        and prev_entry.type == entry.type
                    ) or (
                        isinstance(prev_entry, Comment)
                        and isinstance(entry, (Message, Term))
                        # Standalone Comment followed by Message/Term needs extra blank
                        # to prevent the comment from becoming attached on re-parse
                    )
                    if needs_extra_blank:
                        output.append("\n\n")
                    elif isinstance(prev_entry, (Message, Term)) and isinstance(
                        entry, (Message, Term)
                    ):
                        # Message/Term already end with \n; no extra separator for compact output
                        pass
                    else:
                        output.append("\n")

            self._serialize_entry(entry, output, depth_guard)
            prev_entry = entry

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

    def _pattern_needs_separate_line(self, pattern: Pattern) -> bool:
        """Check if pattern needs separate-line serialization for roundtrip correctness.

        Returns True if any TextElement starting with whitespace is preceded by
        an element ending with newline. This structure would lose the leading
        whitespace during roundtrip if serialized on the same line, because:

        1. Parser sets common_indent from first continuation line's FULL indentation
        2. Serializer adds 4-space continuation indent after newlines
        3. Content's leading whitespace becomes part of combined indentation
        4. On re-parse, common_indent strips ALL indentation including content whitespace

        By outputting on a separate line, we establish initial_common_indent before
        any content with embedded leading whitespace, so extra whitespace is preserved
        as extra_spaces on subsequent continuation lines.
        """
        prev_ends_newline = False
        for elem in pattern.elements:
            if isinstance(elem, TextElement):
                # Check if this element starts with whitespace and follows a newline
                if prev_ends_newline and elem.value and elem.value[0] == " ":
                    return True
                prev_ends_newline = elem.value.endswith("\n")
            else:
                # Placeable doesn't end with newline
                prev_ends_newline = False
        return False

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

        Roundtrip Whitespace Preservation:
        If the pattern has TextElements where leading whitespace follows a newline
        in a preceding element, the pattern is output on a separate line. This
        ensures the parser establishes initial_common_indent from a line without
        semantic whitespace, preserving extra whitespace on continuation lines.

        This ensures output is valid FTL that compliant parsers accept.
        """
        # Check if pattern needs separate-line serialization for roundtrip correctness.
        # This handles patterns where leading whitespace follows a newline in separate
        # TextElements (e.g., "Line 1\n" followed by "  Line 2").
        if self._pattern_needs_separate_line(pattern):
            output.append("\n" + _CONT_INDENT)

        for element in pattern.elements:
            if isinstance(element, TextElement):
                # Per Fluent spec: no escape sequences in TextElements
                # Literal braces must become Placeable(StringLiteral("{"/"}")
                text = element.value

                # Handle newlines: add indentation after each newline for continuation
                # Only add indentation if not already present (prevents double-indentation
                # in roundtrip scenarios where the parsed AST already contains indented text)
                if "\n" in text:
                    # Use regex to replace "\n" not followed by 4+ spaces
                    text = re.sub(r"\n(?!    )", "\n    ", text)

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
        # C-level str.find() outperforms Python-level character iteration.
        # Scans for next brace, emits text run, then emits brace placeholder.
        pos = 0
        length = len(text)

        while pos < length:
            # Find next brace (whichever comes first)
            open_pos = text.find("{", pos)
            close_pos = text.find("}", pos)

            # Determine which brace is next (or neither)
            if open_pos == -1 and close_pos == -1:
                # No more braces - emit remaining text
                output.append(text[pos:])
                break
            if open_pos == -1:
                next_brace_pos = close_pos
                brace_placeholder = '{ "}" }'
            elif close_pos == -1 or open_pos < close_pos:
                next_brace_pos = open_pos
                brace_placeholder = '{ "{" }'
            else:
                next_brace_pos = close_pos
                brace_placeholder = '{ "}" }'

            # Emit text before brace (if any)
            if next_brace_pos > pos:
                output.append(text[pos:next_brace_pos])

            # Emit brace as StringLiteral Placeable
            output.append(brace_placeholder)
            pos = next_brace_pos + 1

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
        # Wrap selector serialization in depth_guard to track depth for DoS protection.
        # Without this, a deeply nested selector could bypass depth limits.
        with depth_guard:
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
                 Checks that:
                 - SelectExpressions have exactly one default variant
                 - Identifiers follow FTL grammar ([a-zA-Z][a-zA-Z0-9_-]*)
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
