"""Entry-oriented Fluent grammar rules."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ftllexengine.enums import CommentType
from ftllexengine.syntax.ast import Attribute, Comment, Identifier, Message, Pattern, Span, Term
from ftllexengine.syntax.cursor import Cursor, ParseError, ParseResult
from ftllexengine.syntax.parser.patterns import parse_pattern
from ftllexengine.syntax.parser.primitives import parse_identifier
from ftllexengine.syntax.parser.whitespace import skip_blank_inline, skip_multiline_pattern_start

if TYPE_CHECKING:
    from ftllexengine.syntax.parser.context import ParseContext

__all__ = [
    "parse_comment",
    "parse_message",
    "parse_message_attributes",
    "parse_message_header",
    "parse_term",
    "validate_message_content",
]

_COMMENT_TYPE_BY_HASH_COUNT: tuple[CommentType, CommentType, CommentType] = (
    CommentType.COMMENT,
    CommentType.GROUP,
    CommentType.RESOURCE,
)


def parse_message_header(cursor: Cursor) -> ParseResult[tuple[str, int]] | None:
    """Parse message header: Identifier "="."""
    id_result = parse_identifier(cursor)
    if isinstance(id_result, ParseError):
        return None

    id_end_pos = id_result.cursor.pos
    cursor = skip_blank_inline(id_result.cursor)
    if cursor.is_eof or cursor.current != "=":
        return None

    cursor = cursor.advance()
    return ParseResult((id_result.value, id_end_pos), cursor)


def parse_message_attributes(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[list[Attribute]] | None:
    """Parse zero or more message attributes."""
    attributes: list[Attribute] = []

    while not cursor.is_eof:
        if cursor.current != "\n":
            break

        cursor = cursor.advance()
        while not cursor.is_eof and cursor.current == "\n":
            cursor = cursor.advance()

        saved_cursor = cursor
        cursor = cursor.skip_spaces()
        if cursor.is_eof or cursor.current != ".":
            cursor = saved_cursor
            break

        attr_result = parse_attribute(saved_cursor, context)
        if attr_result is None:
            cursor = saved_cursor
            break

        attributes.append(attr_result.value)
        cursor = attr_result.cursor

    return ParseResult(attributes, cursor)


def validate_message_content(pattern: Pattern | None, attributes: list[Attribute]) -> bool:
    """Validate message has either pattern or attributes."""
    has_pattern = pattern is not None and len(pattern.elements) > 0
    has_attributes = len(attributes) > 0
    return has_pattern or has_attributes


def parse_message(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[Message] | None:
    """Parse message with full support for select expressions."""
    start_pos = cursor.pos
    id_result = parse_message_header(cursor)
    if id_result is None:
        return id_result

    id_name, id_end_pos = id_result.value
    cursor = id_result.cursor
    cursor, initial_indent = skip_multiline_pattern_start(cursor)
    pattern_result = parse_pattern(cursor, context, initial_common_indent=initial_indent)
    if pattern_result is None:
        return pattern_result

    cursor = pattern_result.cursor
    attributes_result = parse_message_attributes(cursor, context)
    if attributes_result is None:
        return attributes_result

    cursor = attributes_result.cursor
    if not validate_message_content(pattern_result.value, attributes_result.value):
        return None

    message = Message(
        id=Identifier(id_name, span=Span(start=start_pos, end=id_end_pos)),
        value=pattern_result.value,
        attributes=tuple(attributes_result.value),
        span=Span(start=start_pos, end=cursor.pos),
    )
    return ParseResult(message, cursor)


def parse_attribute(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[Attribute] | None:
    """Parse message attribute (.attribute = pattern)."""
    cursor = skip_blank_inline(cursor)
    if cursor.is_eof or cursor.current != ".":
        return None

    attr_start_pos = cursor.pos
    cursor = cursor.advance()
    id_start_pos = cursor.pos

    id_result = parse_identifier(cursor)
    if isinstance(id_result, ParseError):
        return None

    id_end_pos = id_result.cursor.pos
    cursor = skip_blank_inline(id_result.cursor)
    if cursor.is_eof or cursor.current != "=":
        return None

    cursor = cursor.advance()
    cursor, initial_indent = skip_multiline_pattern_start(cursor)
    pattern_result = parse_pattern(cursor, context, initial_common_indent=initial_indent)
    if pattern_result is None:
        return pattern_result

    attribute = Attribute(
        id=Identifier(id_result.value, span=Span(start=id_start_pos, end=id_end_pos)),
        value=pattern_result.value,
        span=Span(start=attr_start_pos, end=pattern_result.cursor.pos),
    )
    return ParseResult(attribute, pattern_result.cursor)


def parse_term(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[Term] | None:
    """Parse term definition (-term-id = pattern)."""
    start_pos = cursor.pos
    if cursor.is_eof or cursor.current != "-":
        return None

    cursor = cursor.advance()
    id_start_pos = cursor.pos
    id_result = parse_identifier(cursor)
    if isinstance(id_result, ParseError):
        return None

    id_end_pos = id_result.cursor.pos
    cursor = skip_blank_inline(id_result.cursor)
    if cursor.is_eof or cursor.current != "=":
        return None

    cursor = cursor.advance()
    cursor, initial_indent = skip_multiline_pattern_start(cursor)
    pattern_result = parse_pattern(cursor, context, initial_common_indent=initial_indent)
    if pattern_result is None:
        return pattern_result

    cursor = pattern_result.cursor
    if not pattern_result.value.elements:
        return None

    attributes_result = parse_message_attributes(cursor, context)
    if attributes_result is None:
        return None

    cursor = attributes_result.cursor
    term = Term(
        id=Identifier(id_result.value, span=Span(start=id_start_pos, end=id_end_pos)),
        value=pattern_result.value,
        attributes=tuple(attributes_result.value),
        span=Span(start=start_pos, end=cursor.pos),
    )
    return ParseResult(term, cursor)


def parse_comment(cursor: Cursor) -> ParseResult[Comment] | None:
    """Parse comment line per Fluent spec."""
    start_pos = cursor.pos
    hash_count = 0
    temp_cursor = cursor
    while not temp_cursor.is_eof and temp_cursor.current == "#":
        hash_count += 1
        temp_cursor = temp_cursor.advance()

    if hash_count > 3:
        return None

    comment_type = _COMMENT_TYPE_BY_HASH_COUNT[hash_count - 1]
    cursor = temp_cursor
    if not cursor.is_eof and cursor.current == " ":
        cursor = cursor.advance()

    content_start = cursor.pos
    cursor = cursor.skip_to_line_end()
    content = cursor.source[content_start : cursor.pos]
    cursor = cursor.skip_line_end()

    comment_node = Comment(
        content=content,
        type=comment_type,
        span=Span(start=start_pos, end=cursor.pos),
    )
    return ParseResult(comment_node, cursor)
