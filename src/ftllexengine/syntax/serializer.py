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
    Junk,
    Message,
    Pattern,
    Resource,
    SelectExpression,
    Term,
)
from .serializer_engine import emit_classified_line as _emit_classified_line_impl
from .serializer_engine import (
    pattern_needs_separate_line as _pattern_needs_separate_line_impl,
)
from .serializer_engine import serialize_call_arguments as _serialize_call_arguments_impl
from .serializer_engine import serialize_expression as _serialize_expression_impl
from .serializer_engine import serialize_pattern as _serialize_pattern_impl
from .serializer_engine import (
    serialize_select_expression as _serialize_select_expression_impl,
)
from .serializer_lines import _ATTR_INDENT
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
                        isinstance(prev_entry, Comment) and isinstance(entry, (Message, Term))
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
                        trailing_n = len(prev_entry.content) - len(prev_entry.content.rstrip("\n"))
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

    def _serialize_message(self, node: Message, output: list[str], depth_guard: DepthGuard) -> None:
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

    def _serialize_term(self, node: Term, output: list[str], depth_guard: DepthGuard) -> None:
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
        """Return True when a pattern requires separate-line mode."""
        return _pattern_needs_separate_line_impl(pattern)

    def _serialize_pattern(  # Branches required by FTL pattern grammar
        self, pattern: Pattern, output: list[str], depth_guard: DepthGuard
    ) -> None:
        """Serialize Pattern elements."""
        _serialize_pattern_impl(
            pattern,
            output,
            depth_guard,
            pattern_needs_separate_line_fn=self._pattern_needs_separate_line,
            emit_classified_line_fn=self._emit_classified_line,
            serialize_expression_fn=self._serialize_expression,
        )

    @staticmethod
    def _emit_classified_line(line: str, output: list[str]) -> None:
        """Emit one continuation line after ambiguity classification."""
        _emit_classified_line_impl(line, output)

    def _serialize_expression(  # Branches required by Expression union type
        self, expr: Expression, output: list[str], depth_guard: DepthGuard
    ) -> None:
        """Serialize Expression nodes using structural pattern matching."""
        _serialize_expression_impl(
            expr,
            output,
            depth_guard,
            serialize_call_arguments_fn=self._serialize_call_arguments,
            serialize_expression_fn=self._serialize_expression,
            serialize_select_expression_fn=self._serialize_select_expression,
        )

    def _serialize_call_arguments(
        self, args: CallArguments, output: list[str], depth_guard: DepthGuard
    ) -> None:
        """Serialize CallArguments."""
        _serialize_call_arguments_impl(
            args,
            output,
            depth_guard,
            serialize_expression_fn=self._serialize_expression,
        )

    def _serialize_select_expression(
        self,
        expr: SelectExpression,
        output: list[str],
        depth_guard: DepthGuard,
    ) -> None:
        """Serialize SelectExpression."""
        _serialize_select_expression_impl(
            expr,
            output,
            depth_guard,
            serialize_expression_fn=self._serialize_expression,
            serialize_pattern_fn=self._serialize_pattern,
        )


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
