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
from ftllexengine.enums import CommentType
from ftllexengine.syntax.ast import (
    Annotation,
    Comment,
    Junk,
    Message,
    Resource,
    Span,
    Term,
)
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.primitives import clear_parse_error, is_identifier_start
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    parse_comment,
    parse_message,
    parse_term,
)
from ftllexengine.syntax.parser.whitespace import skip_blank


def _has_blank_line_between(source: str, start: int, end: int) -> bool:
    """Check if the region contains a blank line (empty line or whitespace-only line).

    Per Fluent spec, adjacent comments should only be joined if there are no
    blank lines between them. A blank line is defined as a line that contains
    only whitespace (spaces, per FTL spec).

    Note: Line endings are normalized to LF before parsing, so only checking
    for '\n' is sufficient.

    Args:
        source: The full source string (with normalized line endings)
        start: Start position (inclusive)
        end: End position (exclusive)

    Returns:
        True if there's a blank line in the region, False otherwise
    """
    region = source[start:end]
    # A blank line is when we see two consecutive newlines (possibly with spaces between)
    # Examples of blank lines: "\n\n", "\n  \n"
    newline_count = 0
    for ch in region:
        if ch == "\n":
            newline_count += 1
            if newline_count >= 2:
                return True
        elif ch == " ":
            # Spaces don't reset the newline counter (they can be part of blank line)
            pass
        else:
            # Non-blank character resets the counter
            newline_count = 0
    return False


def _is_at_column_one(cursor: Cursor) -> bool:
    """Check if cursor is at column 1 (start of a line).

    Per Fluent spec, top-level entries (messages, terms, comments) must start
    at column 1. This function checks if the current position is at the
    beginning of a line (after a newline or at start of file).

    Note: Line endings are normalized to LF before parsing, so only checking
    for '\n' is sufficient.

    Args:
        cursor: Current cursor position

    Returns:
        True if at column 1, False if indented
    """
    if cursor.pos == 0:
        return True
    # Check if previous character is a newline (normalized to LF)
    return cursor.source[cursor.pos - 1] == "\n"


def _merge_comments(first: Comment, second: Comment) -> Comment:
    """Merge two adjacent comments of the same type into one.

    Per Fluent spec, adjacent comment lines of the same type should be
    joined into a single Comment node with content separated by newlines.

    Args:
        first: The first comment
        second: The second comment (must be same type)

    Returns:
        New Comment with joined content and updated span
    """
    # Join content with newline
    merged_content = first.content + "\n" + second.content

    # Update span to cover both comments
    new_span: Span | None = None
    if first.span is not None and second.span is not None:
        new_span = Span(start=first.span.start, end=second.span.end)
    elif first.span is not None:
        new_span = first.span
    elif second.span is not None:
        new_span = second.span

    return Comment(content=merged_content, type=first.type, span=new_span)

__all__ = ["FluentParserV1"]


class FluentParserV1:
    """Fluent FTL parser using immutable cursor pattern.

    Design:
    - Immutable cursor prevents infinite loops (no manual guards needed)
    - Type-safe by design (no custom Result monad)
    - Error messages include line:column with source context

    Security:
    - Configurable max_source_size prevents DoS via large inputs
    - Default limit: 10M characters (sufficient for any reasonable FTL file)
    - Configurable max_nesting_depth prevents DoS via deeply nested placeables

    Architecture:
    - Every parser method takes Cursor (immutable) as input
    - Every parser returns ParseResult[T] | None (None indicates parse failure)
    - No mutation - compiler enforces progress

    Attributes:
        max_source_size: Maximum allowed source length in characters (default: 10M)
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
            max_source_size: Maximum source length in characters (default: 10M).
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
        """Maximum allowed source length in characters."""
        return self._max_source_size

    @property
    def max_nesting_depth(self) -> int:
        """Maximum allowed placeable nesting depth."""
        return self._max_nesting_depth

    def parse(self, source: str) -> Resource:  # noqa: PLR0915
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
        # Clear any stale parse error context from previous operations.
        # This is critical for async frameworks that reuse threads, ensuring
        # clean error state for each parse operation.
        clear_parse_error()

        # Validate input size (DoS prevention)
        if self._max_source_size > 0 and len(source) > self._max_source_size:
            msg = (
                f"Source length ({len(source):,} characters) exceeds maximum "
                f"({self._max_source_size:,} characters). "
                "Configure max_source_size in FluentParserV1 constructor to increase limit."
            )
            raise ValueError(msg)

        # Normalize line endings to LF per Fluent spec.
        # This ensures consistent behavior across platforms and simplifies
        # line/column tracking throughout the parser.
        # Order matters: CRLF first (otherwise CR becomes LF and remaining LF stays)
        source = source.replace("\r\n", "\n").replace("\r", "\n")

        cursor = Cursor(source, 0)
        entries: list[Message | Term | Junk | Comment] = []

        # Create parse context with configured nesting depth limit
        context = ParseContext(max_nesting_depth=self._max_nesting_depth)

        # Track last comment for joining adjacent comments of same type
        pending_comment: Comment | None = None
        pending_comment_end_pos: int = 0  # Position after the pending comment

        # Parse entries until EOF
        while not cursor.is_eof:
            # Per spec: blank_block ::= (blank_inline? line_end)+
            # Between resource entries, skip blank (spaces and newlines, NOT tabs)
            # Track position before blank skipping for Junk content preservation.
            # If entry is not at column 1, we include the leading whitespace in Junk.
            pos_before_blank = cursor.pos
            cursor = skip_blank(cursor)
            # Track position after blank skipping for accurate blank line detection.
            # This is where the next entry actually starts (after any blank lines).
            pos_after_blank = cursor.pos

            if cursor.is_eof:
                # Finalize pending comment before breaking
                if pending_comment is not None:
                    entries.append(pending_comment)
                    pending_comment = None
                break

            # Per Fluent spec, top-level entries must start at column 1.
            # Indented content is treated as Junk.
            if not _is_at_column_one(cursor):
                # Finalize pending comment if any
                if pending_comment is not None:
                    entries.append(pending_comment)
                    pending_comment = None
                    pending_comment_end_pos = 0

                # Consume the indented content as Junk.
                # Use pos_before_blank to include leading whitespace in Junk content.
                # This ensures serialization roundtrip preserves the original structure.
                junk_start = pos_before_blank
                cursor = self._consume_junk_lines(cursor)

                # Create Junk entry for indented content
                junk_content = cursor.source[junk_start : cursor.pos]
                junk_span = Span(start=junk_start, end=cursor.pos)

                annotation = Annotation(
                    code=DiagnosticCode.PARSE_JUNK.name,
                    message="Entry must start at column 1",
                    span=Span(start=junk_start, end=junk_start),
                )

                entries.append(
                    Junk(content=junk_content, annotations=(annotation,), span=junk_span)
                )
                continue

            # Parse comments (per Fluent spec: #, ##, ###)
            if cursor.current == "#":
                comment_result = parse_comment(cursor)
                if comment_result is not None:
                    new_comment = comment_result.value
                    cursor = comment_result.cursor

                    # Check if we should merge with pending comment
                    if pending_comment is not None:
                        # Merge if same type AND no blank lines between.
                        # Use pos_after_blank (where new comment starts) to correctly
                        # detect blank lines between previous comment and this one.
                        if (
                            pending_comment.type == new_comment.type
                            and not _has_blank_line_between(
                                cursor.source,
                                pending_comment_end_pos,
                                pos_after_blank,
                            )
                        ):
                            # Merge comments
                            pending_comment = _merge_comments(
                                pending_comment, new_comment
                            )
                            pending_comment_end_pos = cursor.pos
                            continue
                        # Different type or blank line - finalize pending
                        entries.append(pending_comment)

                    # Start new pending comment
                    pending_comment = new_comment
                    pending_comment_end_pos = cursor.pos
                    continue
                # If comment parsing fails, create Junk entry (not silent skip)
                # This maintains parser transparency and enables roundtrip fidelity
                junk_start = cursor.pos
                # Note: Line endings normalized to LF at parse entry (line 255)
                while not cursor.is_eof and cursor.current != "\n":
                    cursor = cursor.advance()
                junk_end = cursor.pos
                junk_content = cursor.source[junk_start:junk_end]
                # Create annotation for the malformed comment
                annotation = Annotation(
                    code=DiagnosticCode.PARSE_JUNK.name,
                    message="Invalid comment syntax (too many # characters or malformed)",
                    span=Span(start=junk_start, end=junk_end),
                )
                entries.append(
                    Junk(
                        content=junk_content,
                        annotations=(annotation,),
                        span=Span(start=junk_start, end=junk_end),
                    )
                )
                if not cursor.is_eof:
                    cursor = cursor.advance()
                continue

            # Non-comment entry - check if pending comment should be attached
            # Per Fluent spec: Single-hash comments (#) immediately preceding
            # a message/term (no blank lines) should be attached to that entry
            attach_comment: Comment | None = None
            if pending_comment is not None:
                # Check if it's a single-hash comment with no blank line before entry.
                # Use pos_after_blank (where message/term starts) to correctly detect
                # blank lines between comment and the entry.
                if (
                    pending_comment.type == CommentType.COMMENT
                    and not _has_blank_line_between(
                        cursor.source, pending_comment_end_pos, pos_after_blank
                    )
                ):
                    # Attach to following message/term
                    attach_comment = pending_comment
                else:
                    # Group/resource comments or comments with blank line: add to entries
                    entries.append(pending_comment)
                pending_comment = None
                pending_comment_end_pos = 0

            # Try to parse term (starts with '-')
            if cursor.current == "-":
                term_result = parse_term(cursor, context)

                if term_result is not None:
                    term_parse = term_result
                    term = term_parse.value
                    # Attach comment if available
                    if attach_comment is not None:
                        term = Term(
                            id=term.id,
                            value=term.value,
                            attributes=term.attributes,
                            comment=attach_comment,
                            span=term.span,
                        )
                    entries.append(term)
                    cursor = term_parse.cursor
                    continue

            # Try to parse message
            message_result = parse_message(cursor, context)

            if message_result is not None:
                message_parse = message_result
                message = message_parse.value
                # Attach comment if available
                if attach_comment is not None:
                    message = Message(
                        id=message.id,
                        value=message.value,
                        attributes=message.attributes,
                        comment=attach_comment,
                        span=message.span,
                    )
                entries.append(message)
                cursor = message_parse.cursor
            else:
                # Parse error - if we had a pending comment to attach, add it as entry
                if attach_comment is not None:
                    entries.append(attach_comment)

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

        # Finalize any remaining pending comment at EOF
        if pending_comment is not None:
            entries.append(pending_comment)

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
            # Per spec: Junk stops at #, -, or ASCII letter [a-zA-Z]
            # Note: Uses is_identifier_start for ASCII-only check per Fluent spec
            if cursor.current in ("#", "-") or is_identifier_start(cursor.current):
                # Found valid entry start - restore to line start and stop
                cursor = saved_cursor
                break

            # This line doesn't start a valid entry - consume it as junk
            # Skip to end of line and consume line ending
            cursor = cursor.skip_to_line_end().skip_line_end()

        return cursor
