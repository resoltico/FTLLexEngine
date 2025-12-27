"""Core Fluent FTL parser implementation.

This module provides the main FluentParserV1 class that orchestrates
parsing of FTL source files into AST structures defined in :mod:`ftllexengine.syntax.ast`.

Architecture:
    The parser uses an immutable cursor pattern (:class:`~ftllexengine.syntax.cursor.Cursor`)
    to traverse source text. Each sub-parser (in :mod:`~ftllexengine.syntax.parser.rules`,
    :mod:`~ftllexengine.syntax.parser.primitives`, etc.) returns either a
    :class:`~ftllexengine.syntax.cursor.ParseResult` containing the parsed AST node
    and updated cursor position, or None on parse failure.

AST Types:
    The parser produces a :class:`~ftllexengine.syntax.ast.Resource` containing entries:

    - :class:`~ftllexengine.syntax.ast.Message` - User-visible messages with optional attributes
    - :class:`~ftllexengine.syntax.ast.Term` - Reusable terms (referenced with ``-term`` syntax)
    - :class:`~ftllexengine.syntax.ast.Comment` - Single-line, group, or resource comments
    - :class:`~ftllexengine.syntax.ast.Junk` - Unparseable content (robustness principle)

Security:
    Includes configurable input size limit to prevent DoS attacks via
    unbounded memory allocation from extremely large FTL files.

See Also:
    - :mod:`ftllexengine.syntax.ast` - All AST node type definitions
    - :mod:`ftllexengine.syntax.cursor` - Cursor and ParseResult types
    - :mod:`ftllexengine.syntax.parser.rules` - Grammar rules (patterns, expressions, entries)
"""

from ftllexengine.constants import MAX_DEPTH, MAX_SOURCE_SIZE
from ftllexengine.diagnostics import DiagnosticCode
from ftllexengine.syntax.ast import Annotation, Comment, Junk, Message, Resource, Span, Term
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    parse_comment,
    parse_message,
    parse_term,
)
from ftllexengine.syntax.parser.whitespace import skip_blank

__all__ = ["FluentParserV1"]


class FluentParserV1:
    """Fluent FTL parser using immutable cursor pattern.

    Design:
    - Immutable cursor prevents infinite loops (no manual guards needed)
    - Type-safe by design (no custom Result monad)
    - Error messages include line:column with source context

    Security:
    - Configurable max_source_size prevents DoS via large inputs
    - Default limit: 10 MB (sufficient for any reasonable FTL file)
    - Configurable max_nesting_depth prevents DoS via deeply nested placeables

    Architecture:
    - Every parser method takes Cursor (immutable) as input
    - Every parser returns ParseResult[T] | None (None indicates parse failure)
    - No mutation - compiler enforces progress

    Attributes:
        max_source_size: Maximum allowed source size in bytes (default: 10 MB)
        max_nesting_depth: Maximum allowed placeable nesting depth (default: 100)
    """

    __slots__ = ("_max_nesting_depth", "_max_source_size")

    def __init__(
        self,
        *,
        max_source_size: int | None = None,
        max_nesting_depth: int | None = None,
    ) -> None:
        """Initialize parser with optional size and nesting depth limits.

        Args:
            max_source_size: Maximum source size in bytes (default: 10 MB).
                            Set to None or 0 to disable size limit (not recommended).
            max_nesting_depth: Maximum placeable nesting depth (default: 100).
                              Prevents DoS via deeply nested { { { ... } } }.
        """
        self._max_source_size = (
            max_source_size if max_source_size is not None else MAX_SOURCE_SIZE
        )
        self._max_nesting_depth = (
            max_nesting_depth if max_nesting_depth is not None else MAX_DEPTH
        )

    @property
    def max_source_size(self) -> int:
        """Maximum allowed source size in bytes."""
        return self._max_source_size

    @property
    def max_nesting_depth(self) -> int:
        """Maximum allowed placeable nesting depth."""
        return self._max_nesting_depth

    def parse(self, source: str) -> Resource:
        """Parse FTL source into AST Resource.

        Parses complete FTL file into messages, terms, and comments.
        Continues parsing after errors (robustness principle).

        Args:
            source: FTL file content (UTF-8 string)

        Returns:
            :class:`~ftllexengine.syntax.ast.Resource` with tuple of entries, where
            each entry is one of:

            - :class:`~ftllexengine.syntax.ast.Message` - Parsed message with id, value, attributes
            - :class:`~ftllexengine.syntax.ast.Term` - Parsed term (id starts with ``-``)
            - :class:`~ftllexengine.syntax.ast.Comment` - Standalone comment
            - :class:`~ftllexengine.syntax.ast.Junk` - Unparseable content with annotations

        Raises:
            ValueError: If source exceeds max_source_size (DoS prevention)
            FluentSyntaxError: Only on critical parse failures

        Security:
            Validates source size before parsing to prevent DoS via
            unbounded memory allocation. Configure via max_source_size
            parameter in constructor.

        Example:
            >>> parser = FluentParserV1()
            >>> resource = parser.parse("hello = World")
            >>> message = resource.entries[0]
            >>> message.id.name
            'hello'

        See Also:
            - :func:`~ftllexengine.syntax.parser.rules.parse_message` - Message parsing
            - :func:`~ftllexengine.syntax.parser.rules.parse_term` - Term parsing
            - :func:`~ftllexengine.syntax.parser.rules.parse_comment` - Comment parsing
        """
        # Validate input size (DoS prevention)
        if self._max_source_size > 0 and len(source) > self._max_source_size:
            msg = (
                f"Source size ({len(source):,} bytes) exceeds maximum "
                f"({self._max_source_size:,} bytes). "
                "Configure max_source_size in FluentParserV1 constructor to increase limit."
            )
            raise ValueError(msg)

        cursor = Cursor(source, 0)
        entries: list[Message | Term | Junk | Comment] = []

        # Create parse context with configured nesting depth limit
        context = ParseContext(max_nesting_depth=self._max_nesting_depth)

        # Parse entries until EOF
        while not cursor.is_eof:
            # Per spec: blank_block ::= (blank_inline? line_end)+
            # Between resource entries, skip blank (spaces and newlines, NOT tabs)
            cursor = skip_blank(cursor)

            if cursor.is_eof:
                break

            # Parse comments (per Fluent spec: #, ##, ###)
            if cursor.current == "#":
                comment_result = parse_comment(cursor)
                if comment_result is not None:
                    comment_parse = comment_result
                    entries.append(comment_parse.value)
                    cursor = comment_parse.cursor
                    continue
                # If comment parsing fails, skip the line
                while not cursor.is_eof and cursor.current not in ("\n", "\r"):
                    cursor = cursor.advance()
                if not cursor.is_eof:
                    cursor = cursor.advance()
                continue

            # Try to parse term (starts with '-')
            if cursor.current == "-":
                term_result = parse_term(cursor, context)

                if term_result is not None:
                    term_parse = term_result
                    entries.append(term_parse.value)
                    cursor = term_parse.cursor
                    continue

            # Try to parse message
            message_result = parse_message(cursor, context)

            if message_result is not None:
                message_parse = message_result
                entries.append(message_parse.value)
                cursor = message_parse.cursor
            else:
                # Parse error - create Junk entry and continue (robustness principle)
                # Junk creation still preserves robustness
                junk_start = cursor.pos

                # Per FTL spec: Junk ::= junk_line (junk_line - "#" - "-" - [a-zA-Z])*
                # Consume multiple lines until we hit a valid entry start
                cursor = self._consume_junk_lines(cursor)

                # Create Junk entry with all consumed problematic content
                junk_content = cursor.source[junk_start : cursor.pos]
                junk_span = Span(start=junk_start, end=cursor.pos)

                annotation = Annotation(
                    code=DiagnosticCode.PARSE_JUNK.name,
                    message="Parse error",
                    span=Span(start=junk_start, end=junk_start),
                )

                entries.append(
                    Junk(content=junk_content, annotations=(annotation,), span=junk_span)
                )

        return Resource(entries=tuple(entries))

    def _consume_junk_lines(self, cursor: Cursor) -> Cursor:
        """Consume junk lines per FTL spec until valid entry start.

        Per Fluent EBNF:
            Junk ::= junk_line (junk_line - "#" - "-" - [a-zA-Z])*
            junk_line ::= /[^\n]*/ ("\u000a" | EOF)

        This means:
        1. First junk line: consume to end of line
        2. Subsequent lines: continue UNTIL hitting a line that starts with:
           - "#" (comment)
           - "-" (term)
           - [a-zA-Z] (message identifier)

        Args:
            cursor: Current position in source (at start of junk content)

        Returns:
            New cursor position after all junk lines consumed
        """
        # Skip first line to end and consume line ending
        cursor = cursor.skip_to_line_end().skip_line_end()

        # Continue consuming lines UNTIL we hit a valid entry start
        while not cursor.is_eof:
            # Save position at start of line
            saved_cursor = cursor

            # Skip leading spaces on THIS line only (not newlines)
            cursor = cursor.skip_spaces()

            if cursor.is_eof:
                break

            # Check for valid entry start characters
            # Per spec: Junk stops at #, -, or [a-zA-Z]
            if cursor.current in ("#", "-") or cursor.current.isalpha():
                # Found valid entry start - restore to line start and stop
                cursor = saved_cursor
                break

            # This line doesn't start a valid entry - consume it as junk
            # Skip to end of line and consume line ending
            cursor = cursor.skip_to_line_end().skip_line_end()

        return cursor
