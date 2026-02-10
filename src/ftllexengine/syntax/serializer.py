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

from enum import Enum, auto
from typing import assert_never

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.core.depth_guard import DepthGuard
from ftllexengine.core.identifier_validation import is_valid_identifier
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
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
    except FrozenFluentError as e:
        if e.category == ErrorCategory.RESOLUTION:
            # Depth limit exceeded - wrap in SerializationDepthError
            msg = f"Validation depth limit exceeded (max: {max_depth}): {e}"
            raise SerializationDepthError(msg) from e
        raise

# FTL indentation constants per Fluent spec.
# Standard continuation indent: 4 spaces.
_CONT_INDENT: str = "    "

# Attributes use 4 spaces for standard indentation.
_ATTR_INDENT: str = "\n    "

# Select expression variants use 3 spaces to align with the `*[` marker.
# This produces: "\n   *[key] value" where the `[` aligns with attribute `.`.
_VARIANT_INDENT: str = "\n   "

# Characters that are syntactically significant at the start of a continuation
# line in FTL: '[' (variant key), '*' (default variant), '.' (attribute).
# The FTL parser strips leading whitespace and checks the first non-whitespace
# character against these markers. Content containing these characters at
# structurally ambiguous positions must be wrapped in StringLiteral placeables.
_LINE_START_SYNTAX_CHARS: frozenset[str] = frozenset(".[*")

# Precomputed StringLiteral placeable forms for special characters.
# Used by both continuation line dispatch and brace escaping.
_CHAR_PLACEABLE: dict[str, str] = {
    "{": '{ "{" }',
    "}": '{ "}" }',
    "[": '{ "[" }',
    "*": '{ "*" }',
    ".": '{ "." }',
}


class _LineKind(Enum):
    """Classification of a continuation line's content for serialization.

    The FTL parser interprets continuation lines structurally: leading
    whitespace is syntactic indent, blank lines are stripped, and
    characters '.', '*', '[' as the first non-whitespace trigger
    attribute/variant parsing. Each kind maps to one unambiguous
    emission strategy.
    """

    EMPTY = auto()
    WHITESPACE_ONLY = auto()
    SYNTAX_LEADING = auto()
    NORMAL = auto()


def _classify_line(line: str) -> tuple[_LineKind, int]:
    """Classify a continuation line for serialization dispatch.

    Returns the line kind and, for SYNTAX_LEADING, the number of
    leading whitespace characters before the syntax character.
    For all other kinds the second element is 0.

    Pure function with no side effects.

    Args:
        line: Text content of a single continuation line (no newlines).

    Returns:
        (kind, ws_prefix_len) tuple.
    """
    if not line:
        return (_LineKind.EMPTY, 0)

    # Scan to first non-space character.
    ws_len = 0
    length = len(line)
    while ws_len < length and line[ws_len] == " ":
        ws_len += 1

    if ws_len == length:
        return (_LineKind.WHITESPACE_ONLY, 0)

    if line[ws_len] in _LINE_START_SYNTAX_CHARS:
        return (_LineKind.SYNTAX_LEADING, ws_len)

    return (_LineKind.NORMAL, 0)


def _escape_text(text: str, output: list[str]) -> None:
    """Escape brace characters in text content.

    Wraps { and } as StringLiteral placeables per Fluent spec.
    Character-level escaping only; line-level concerns (whitespace
    ambiguity, syntax chars) are handled by _emit_classified_line.
    """
    pos = 0
    length = len(text)
    while pos < length:
        ch = text[pos]
        if ch in ("{", "}"):
            output.append(_CHAR_PLACEABLE[ch])
            pos += 1
            continue
        run_start = pos
        pos += 1
        while pos < length and text[pos] not in ("{", "}"):
            pos += 1
        output.append(text[run_start:pos])


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
        except FrozenFluentError as e:
            if e.category == ErrorCategory.RESOLUTION:
                # Depth limit exceeded - wrap in SerializationDepthError
                msg = f"AST nesting exceeds maximum depth ({max_depth})"
                raise SerializationDepthError(msg) from e
            raise

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
            case _ as unreachable:  # pragma: no cover
                assert_never(unreachable)

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

        Returns True when a continuation line with NORMAL content has leading
        whitespace that would be consumed as structural indent during re-parse.
        Two triggers:

        1. Cross-element: A TextElement starting with whitespace is preceded by
           an element ending with newline.

        2. Intra-element: A single TextElement contains an embedded newline
           followed by whitespace on a NORMAL line (not WHITESPACE_ONLY or
           SYNTAX_LEADING, which are handled by per-line wrapping).

        Separate-line mode establishes initial_common_indent before any content
        with embedded leading whitespace, so extra whitespace is preserved as
        extra_spaces on subsequent continuation lines.
        """
        prev_ends_newline = False
        for elem in pattern.elements:
            if isinstance(elem, TextElement):
                if prev_ends_newline and elem.value and elem.value[0] == " ":
                    return True
                # Check for embedded newlines followed by whitespace within
                # a single TextElement. Only NORMAL lines trigger separate-line
                # mode; WHITESPACE_ONLY and SYNTAX_LEADING are handled by
                # per-line wrapping in _serialize_pattern.
                value = elem.value
                idx = value.find("\n")
                while idx != -1 and idx + 1 < len(value):
                    if value[idx + 1] == " ":
                        next_nl = value.find("\n", idx + 1)
                        line = value[idx + 1 : next_nl] if next_nl != -1 else value[idx + 1 :]
                        kind, _ = _classify_line(line)
                        if kind is _LineKind.NORMAL:
                            return True
                    idx = value.find("\n", idx + 1)
                prev_ends_newline = value.endswith("\n")
            else:
                prev_ends_newline = False
        return False

    def _serialize_pattern(  # noqa: PLR0912  # Branches required by FTL pattern grammar
        self, pattern: Pattern, output: list[str], depth_guard: DepthGuard
    ) -> None:
        """Serialize Pattern elements.

        Handles three concerns in strict order:
        1. Pattern-level: separate-line mode, leading whitespace preservation
        2. Line-level: classify each continuation line via _classify_line,
           dispatch to the appropriate wrapping strategy via match/case
        3. Character-level: escape braces via _escape_text

        Per Fluent Spec 1.0: Backslash has no escaping power in TextElements.
        Literal braces MUST be expressed as StringLiterals within Placeables.
        """
        # Pattern-level: determine separate-line serialization.
        needs_separate_line = self._pattern_needs_separate_line(pattern)
        if needs_separate_line:
            output.append("\n" + _CONT_INDENT)

        # Pattern-level: handle leading whitespace in the first TextElement.
        # In FTL, whitespace after '=' is syntactic. A TextElement starting
        # with spaces at pattern start loses its whitespace during re-parse.
        leading_ws_len = 0
        if (
            pattern.elements
            and isinstance(pattern.elements[0], TextElement)
            and pattern.elements[0].value
            and pattern.elements[0].value[0] == " "
        ):
            first_value = pattern.elements[0].value
            stripped = first_value.lstrip(" ")
            leading_ws_len = len(first_value) - len(stripped)
            output.append('{ "')
            output.append(" " * leading_ws_len)
            output.append('" }')

        # Track continuation line state for text elements.
        at_line_start = needs_separate_line

        for element in pattern.elements:
            if isinstance(element, TextElement):
                text = element.value

                # Skip already-emitted leading whitespace on first element.
                if leading_ws_len > 0:
                    text = text[leading_ws_len:]
                    leading_ws_len = 0
                    if not text:
                        at_line_start = False
                        continue

                if "\n" in text:
                    lines = text.split("\n")
                    # First line segment: classify if at line start,
                    # otherwise just escape braces.
                    if at_line_start:
                        self._emit_classified_line(lines[0], output)
                    else:
                        _escape_text(lines[0], output)
                    # Continuation lines: classify-then-dispatch.
                    for line in lines[1:]:
                        output.append("\n    ")
                        self._emit_classified_line(line, output)
                    # Track state: empty last line means text ended with \n.
                    at_line_start = not lines[-1]
                else:
                    if at_line_start:
                        self._emit_classified_line(text, output)
                    else:
                        _escape_text(text, output)
                    at_line_start = False

            elif isinstance(element, Placeable):
                output.append("{ ")
                with depth_guard:
                    self._serialize_expression(element.expression, output, depth_guard)
                output.append(" }")
                at_line_start = False

    @staticmethod
    def _emit_classified_line(line: str, output: list[str]) -> None:
        """Classify a line and emit with appropriate wrapping.

        Single dispatch point for all continuation line ambiguity classes.
        Each _LineKind maps to exactly one emission strategy.
        """
        kind, ws_len = _classify_line(line)
        match kind:
            case _LineKind.EMPTY:
                pass
            case _LineKind.WHITESPACE_ONLY:
                output.append('{ "')
                output.append(line)
                output.append('" }')
            case _LineKind.SYNTAX_LEADING:
                # Invariant: ALL content whitespace preceding the first
                # non-whitespace character on a continuation line must be
                # placeable-wrapped. Raw spaces here become indistinguishable
                # from structural indent during common-indent stripping.
                if ws_len:
                    output.append('{ "')
                    output.append(line[:ws_len])
                    output.append('" }')
                output.append(_CHAR_PLACEABLE[line[ws_len]])
                remaining = line[ws_len + 1 :]
                if remaining:
                    _escape_text(remaining, output)
            case _LineKind.NORMAL:
                _escape_text(line, output)
            case _ as unreachable:  # pragma: no cover
                assert_never(unreachable)

    def _serialize_expression(  # noqa: PLR0912  # Branches required by Expression union type
        self, expr: Expression, output: list[str], depth_guard: DepthGuard
    ) -> None:
        """Serialize Expression nodes using structural pattern matching.

        Handles all Expression types including nested Placeables (valid per FTL spec).
        """
        match expr:
            case StringLiteral(value=value):
                # Escape special characters per FTL spec.
                # Uses \uHHHH for ALL control characters (< 0x20 and 0x7F)
                # to produce robust output that works in all editors and parsers.
                result: list[str] = []
                for char in value:
                    code = ord(char)
                    if char == "\\":
                        result.append("\\\\")
                    elif char == '"':
                        result.append('\\"')
                    elif code < 0x20 or code == 0x7F:
                        result.append(f"\\u{code:04X}")
                    else:
                        result.append(char)
                output.append(f'"{"".join(result)}"')

            case NumberLiteral(raw=raw):
                output.append(raw)

            case VariableReference(id=Identifier(name=name)):
                output.append(f"${name}")

            case MessageReference(id=Identifier(name=name), attribute=attr):
                output.append(name)
                if attr:
                    output.append(f".{attr.name}")

            case TermReference(
                id=Identifier(name=name), attribute=attr, arguments=args
            ):
                output.append(f"-{name}")
                if attr:
                    output.append(f".{attr.name}")
                if args:
                    self._serialize_call_arguments(args, output, depth_guard)

            case FunctionReference(id=Identifier(name=name), arguments=args):
                output.append(name)
                self._serialize_call_arguments(args, output, depth_guard)

            case Placeable(expression=inner):
                # Nested Placeable: { { $var } } is valid per FTL spec
                output.append("{ ")
                with depth_guard:
                    self._serialize_expression(inner, output, depth_guard)
                output.append(" }")

            case SelectExpression():
                self._serialize_select_expression(expr, output, depth_guard)

            case _ as unreachable:  # pragma: no cover
                assert_never(unreachable)

    def _serialize_call_arguments(
        self, args: CallArguments, output: list[str], depth_guard: DepthGuard
    ) -> None:
        """Serialize CallArguments.

        Security: Argument expressions are wrapped in depth_guard to prevent
        deeply nested term/function arguments from bypassing depth limits.
        Without this, -term(arg: -term(arg: ...)) could cause stack overflow.
        """
        output.append("(")

        # Positional arguments - protected by depth_guard to enforce depth limits
        for i, arg in enumerate(args.positional):
            if i > 0:
                output.append(", ")
            with depth_guard:
                self._serialize_expression(arg, output, depth_guard)

        # Named arguments - protected by depth_guard to enforce depth limits
        named_arg: NamedArgument
        for i, named_arg in enumerate(args.named):
            if i > 0 or args.positional:
                output.append(", ")
            output.append(f"{named_arg.name.name}: ")
            with depth_guard:
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

            # Variant key: explicit destructuring for exhaustiveness
            match variant.key:
                case Identifier(name=name):
                    output.append(name)
                case NumberLiteral(raw=raw):
                    output.append(raw)

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
