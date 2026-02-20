"""Whitespace handling utilities for Fluent FTL parser.

This module provides whitespace skipping and continuation detection
per the Fluent specification.
"""

from ftllexengine.syntax.cursor import Cursor


def skip_blank_inline(cursor: Cursor) -> Cursor:
    """Skip inline whitespace (ONLY space U+0020, per FTL spec).

    Per Fluent EBNF specification:
        blank_inline ::= "\u0020"+

    This is stricter than skip_blank() - it ONLY accepts space (U+0020),
    NOT tabs or newlines.

    Used in contexts where spec requires blank_inline:
    - Between tokens on same line (identifier = value)
    - Before/after operators on same line (=, :)
    - Inside variant key brackets [key]

    Note: CallArguments uses skip_blank (not blank_inline) per FTL spec.
    The spec defines CallArguments ::= blank? "(" blank? argument_list blank? ")"
    where blank allows newlines for multiline argument formatting.

    Args:
        cursor: Current position in source

    Returns:
        New cursor at first non-space character (or EOF)

    Design:
        Immutable cursor ensures termination (same proof as skip_blank).
    """
    return cursor.skip_spaces()  # Always makes progress


def skip_blank(cursor: Cursor) -> Cursor:
    """Skip blank (spaces and line endings, per FTL spec).

    Per Fluent EBNF specification:
        blank ::= (blank_inline | line_end)+
        blank_inline ::= "\u0020"+
        line_end ::= "\u000d\u000a" | "\u000a" | EOF

    This accepts spaces and newlines, but NOT tabs.

    Used in contexts where spec requires blank:
    - Between entries in resource
    - Inside select expression variant lists
    - Before/after patterns with line breaks
    - Inside CallArguments (enables multiline argument formatting)

    Args:
        cursor: Current position in source

    Returns:
        New cursor at first non-blank character (or EOF)

    Design:
        Immutable cursor ensures termination.
    """
    return cursor.skip_whitespace()  # Always makes progress


def is_indented_continuation(cursor: Cursor) -> bool:
    """Check if the next line is an indented pattern continuation.

    According to FTL spec:
    - Continuation lines must start with at least one space (U+0020)
    - Lines starting with [, *, or . are NOT pattern continuations
      (they indicate variants, default variants, or attributes)

    Args:
        cursor: Current position (should be at newline character)

    Returns:
        True if next line is an indented continuation, False otherwise

    Note:
        Line endings are normalized to LF at parser entry point.
    """
    if cursor.is_eof or cursor.current != "\n":
        return False

    # Skip the newline and any subsequent blank lines
    # Pattern values can have blank lines before the indented content:
    #   msg =
    #
    #       value
    next_cursor = cursor.advance()
    while not next_cursor.is_eof and next_cursor.current == "\n":
        next_cursor = next_cursor.advance()

    # Check if next line starts with space (U+0020 only, NOT tab)
    if next_cursor.is_eof or next_cursor.current != " ":
        return False

    # Skip leading spaces to find first non-space character
    while not next_cursor.is_eof and next_cursor.current == " ":
        next_cursor = next_cursor.advance()

    # If line starts with special chars, it's not a pattern continuation.
    # '}' is excluded because bare '}' at line start is always a select/placeable
    # closing brace, never text content (literal '}' is serialized as {"}"}).
    return not (
        not next_cursor.is_eof and next_cursor.current in ("[", "*", ".", "}")
    )


def skip_multiline_pattern_start(cursor: Cursor) -> tuple[Cursor, int]:
    """Skip whitespace and handle multiline pattern start.

    Per spec: Pattern can start on same line or next line (if indented).
        Message ::= Identifier blank_inline? "=" blank_inline? Pattern
        Attribute ::= ... blank_inline? "=" blank_inline? Pattern
        blank_inline ::= "\u0020"+  (ONLY space, NOT tabs)

    This method handles:
    1. Inline patterns: "key = value" (skip spaces on same line)
    2. Multiline patterns: "key =\n    value" (skip newline + leading spaces)

    Returns:
        Tuple of (cursor at content start, common_indent for multiline patterns).
        For inline patterns, common_indent is 0.
        For multiline patterns, common_indent is the leading indentation count.
    """
    # Skip inline whitespace (ONLY spaces per spec, NOT tabs)
    cursor = skip_blank_inline(cursor)

    # Check for pattern starting on next line
    # Note: Line endings normalized to LF at parser entry point
    if not cursor.is_eof and cursor.current == "\n":  # noqa: SIM102 - two-phase
        if is_indented_continuation(cursor):
            # Multiline pattern - skip newlines (including blank lines)
            cursor = cursor.advance()
            while not cursor.is_eof and cursor.current == "\n":
                cursor = cursor.advance()
            # Count and skip leading indentation (ONLY spaces per spec)
            # Return the indent count so parse_pattern can use it as common_indent
            indent_count = 0
            while not cursor.is_eof and cursor.current == " ":
                indent_count += 1
                cursor = cursor.advance()
            return cursor, indent_count

    return cursor, 0
