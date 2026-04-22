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

from typing import assert_never

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.core.depth_guard import DepthGuard, DepthLimitExceededError
from ftllexengine.diagnostics import FrozenFluentError
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
from .serializer_lines import (
    _ATTR_INDENT,
    _CHAR_PLACEABLE,
    _CONT_INDENT,
    _VARIANT_INDENT,
    _classify_line,
    _escape_text,
    _LineKind,
)
from .serializer_validation import (
    SerializationDepthError,
    SerializationValidationError,
    _validate_pattern,
)
from .serializer_validation import (
    validate_resource as _validate_resource_impl,
)
from .visitor import ASTVisitor

__all__ = [
    "SerializationDepthError",
    "SerializationValidationError",
    "serialize",
]


def _validate_resource(resource: Resource, max_depth: int = MAX_DEPTH) -> None:
    """Validate a resource using the serializer module's patchable helpers."""
    _validate_resource_impl(
        resource,
        max_depth=max_depth,
        validate_pattern=_validate_pattern,
    )


class FluentSerializer(ASTVisitor):
    """Converts AST back to FTL source string.

    Thread-safe serializer with no mutable instance state.
    All serialization state is local to the serialize() call.

    Usage:
        >>> from ftllexengine.syntax import parse, serialize  # doctest: +SKIP
        >>> ast = parse("hello = Hello, world!")  # doctest: +SKIP
        >>> ftl = serialize(ast)  # doctest: +SKIP
        >>> print(ftl)  # doctest: +SKIP
        hello = Hello, world!

    Advanced usage (direct class instantiation):
        >>> from ftllexengine.syntax import parse  # doctest: +SKIP
        >>> from ftllexengine.syntax.serializer import FluentSerializer  # doctest: +SKIP
        >>> ast = parse("hello = Hello, world!")  # doctest: +SKIP
        >>> serializer = FluentSerializer()  # doctest: +SKIP
        >>> ftl = serializer.serialize(ast)  # doctest: +SKIP
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
        except DepthLimitExceededError as exc:
            msg = f"AST nesting exceeds maximum depth ({max_depth})"
            raise SerializationDepthError(msg) from exc
        except FrozenFluentError:
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
        - Junk separator is capped so that parse/serialize cycles are idempotent:
          _consume_junk_lines absorbs trailing blank lines into Junk.content;
          without compensation, each cycle appends one extra blank line.
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
                    elif isinstance(prev_entry, Junk):
                        # _consume_junk_lines absorbs trailing blank lines into
                        # Junk.content, so prev_entry.content may already supply
                        # the blank-line separator. Only emit enough additional
                        # newlines to reach exactly 2 trailing newlines total
                        # (Junk's own line-end "\n" + one blank-line "\n").
                        # Adding an unconditional "\n" would grow the blank count
                        # by one on every parse/serialize cycle.
                        trailing_n = len(prev_entry.content) - len(
                            prev_entry.content.rstrip("\n")
                        )
                        if trailing_n < 2:
                            output.append("\n" * (2 - trailing_n))
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
           an element ending with newline, AND its first line classifies as
           NORMAL. WHITESPACE_ONLY and SYNTAX_LEADING lines are handled by
           per-line wrapping in _emit_classified_line and do not need
           separate-line mode.

        2. Intra-element: A single TextElement contains an embedded newline
           followed by whitespace on a NORMAL line (not WHITESPACE_ONLY or
           SYNTAX_LEADING, which are handled by per-line wrapping).

        Both triggers use _classify_line to determine if separate-line mode is
        actually needed.  Per-line wrapping converts TextElements into Placeables,
        changing the AST structure on re-parse; triggering separate-line mode for
        content that wrapping already handles makes the mode decision unstable
        across roundtrips.
        """
        prev_ends_newline = False
        for elem in pattern.elements:
            if isinstance(elem, TextElement):
                if prev_ends_newline and elem.value and elem.value[0] == " ":
                    first_nl = elem.value.find("\n")
                    first_line = (
                        elem.value[:first_nl] if first_nl != -1
                        else elem.value
                    )
                    kind, _ = _classify_line(first_line)
                    if kind is _LineKind.NORMAL:
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

            else:
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
                case _ as unreachable:  # pragma: no cover
                    assert_never(unreachable)

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
        >>> from ftllexengine.syntax import parse, serialize  # doctest: +SKIP
        >>> ast = parse("hello = Hello, world!")  # doctest: +SKIP
        >>> ftl = serialize(ast)  # doctest: +SKIP
        >>> assert ftl == "hello = Hello, world!\\n"  # doctest: +SKIP
    """
    serializer = FluentSerializer()
    return serializer.serialize(resource, validate=validate, max_depth=max_depth)
