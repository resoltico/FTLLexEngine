"""Pattern-oriented Fluent grammar rules."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from ftllexengine.syntax.ast import Pattern, Placeable, TextElement
from ftllexengine.syntax.cursor import Cursor, ParseResult
from ftllexengine.syntax.parser.primitives import (
    _ASCII_DIGITS,
    is_identifier_char,
    is_identifier_start,
)
from ftllexengine.syntax.parser.whitespace import is_indented_continuation

if TYPE_CHECKING:
    from ftllexengine.syntax.parser.context import ParseContext

__all__ = [
    "_MAX_LOOKAHEAD_CHARS",
    "parse_pattern",
    "parse_simple_pattern",
]

# Maximum lookahead distance for variant marker detection.
# Must accommodate: '[' + optional_spaces + identifier (up to MAX_IDENTIFIER_LENGTH chars)
# + optional_spaces + ']'. Value of 300 ensures variant keys with maximum-length
# identifiers parse correctly while bounding lookahead on adversarial inputs.
_MAX_LOOKAHEAD_CHARS: int = 300


def _parse_placeable(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[Placeable] | None:
    """Load the placeable parser lazily to keep grammar modules acyclic."""
    expressions = importlib.import_module("ftllexengine.syntax.parser.expressions")
    return cast("ParseResult[Placeable] | None", expressions.parse_placeable(cursor, context))


def _is_valid_variant_key_char(ch: str, *, is_first: bool) -> bool:
    """Check if character is valid in a variant key (identifier or number)."""
    if is_first:
        return is_identifier_start(ch) or ch == "_" or ch in _ASCII_DIGITS
    return is_identifier_char(ch) or ch == "."


def _is_variant_marker(cursor: Cursor) -> bool:
    """Check if cursor is at a variant marker using bounded lookahead."""
    max_lookahead = _MAX_LOOKAHEAD_CHARS

    if cursor.is_eof:
        return False

    ch = cursor.current

    if ch == "*":
        next_cursor = cursor.advance()
        return not next_cursor.is_eof and next_cursor.current == "["

    if ch == "[":
        scan = cursor.advance()
        is_first = True
        has_content = False
        lookahead_count = 0

        while not scan.is_eof and scan.current == " " and lookahead_count < max_lookahead:
            scan = scan.advance()
            lookahead_count += 1

        while not scan.is_eof and lookahead_count < max_lookahead:
            current = scan.current
            lookahead_count += 1

            if current == "]":
                if not has_content:
                    return False

                after_bracket = scan.advance()
                while (
                    not after_bracket.is_eof
                    and after_bracket.current == " "
                    and lookahead_count < max_lookahead
                ):
                    after_bracket = after_bracket.advance()
                    lookahead_count += 1

                if after_bracket.is_eof:
                    return True

                return after_bracket.current in ("\n", "}", "[", "*")

            if current in ("\n", "{", "}", " ", "\t", ",", ":", ";", "=", "+", "*", "/"):
                return False
            if not _is_valid_variant_key_char(current, is_first=is_first):
                return False
            has_content = True
            is_first = False
            scan = scan.advance()

    return False


def _trim_pattern_blank_lines(
    elements: list[TextElement | Placeable],
) -> tuple[TextElement | Placeable, ...]:
    """Trim leading and trailing blank lines from pattern elements."""
    if not elements:
        return ()

    result = list(elements)

    while result and isinstance(result[0], TextElement):
        first = result[0]
        stripped = first.value.lstrip(" \n")
        if stripped:
            result[0] = TextElement(value=stripped)
            break
        result.pop(0)

    while result and isinstance(result[-1], TextElement):
        last = result[-1]
        text = last.value
        last_newline = text.rfind("\n")

        if last_newline == -1:
            break

        after_newline = text[last_newline + 1 :]
        if after_newline.strip(" "):
            break

        trimmed = text[:last_newline]
        if trimmed:
            result[-1] = TextElement(value=trimmed)
        else:
            result.pop()

    return tuple(result)


class _TextAccumulator:
    """Accumulator for building TextElement with efficient string concatenation."""

    __slots__ = ("fragments",)

    def __init__(self) -> None:
        self.fragments: list[str] = []

    def add(self, text: str) -> None:
        """Add text fragment to accumulator."""
        self.fragments.append(text)

    def has_content(self) -> bool:
        """Check if accumulator has any content."""
        return len(self.fragments) > 0

    def finalize(self) -> TextElement:
        """Create TextElement from accumulated fragments."""
        return TextElement(value="".join(self.fragments))

    def clear(self) -> None:
        """Clear accumulated fragments."""
        self.fragments.clear()


@dataclass(slots=True)
class _ContinuationResult:
    """Result of processing a continuation line."""

    cursor: Cursor
    common_indent: int
    extra_spaces: str


def _count_leading_spaces(cursor: Cursor) -> int:
    """Count leading spaces at current position."""
    pos = cursor.pos
    source = cursor.source
    length = len(source)
    start = pos
    while pos < length and source[pos] == " ":
        pos += 1
    return pos - start


def _skip_common_indent(cursor: Cursor, common_indent: int) -> tuple[Cursor, str]:
    """Skip common indentation and return any extra spaces."""
    skipped = 0
    while skipped < common_indent and not cursor.is_eof and cursor.current == " ":
        cursor = cursor.advance()
        skipped += 1

    extra_spaces: list[str] = []
    while not cursor.is_eof and cursor.current == " ":
        extra_spaces.append(" ")
        cursor = cursor.advance()

    return cursor, "".join(extra_spaces)


def _process_continuation_line(
    cursor: Cursor,
    common_indent: int | None,
) -> _ContinuationResult:
    """Process a continuation line after newline."""
    while not cursor.is_eof and cursor.current == "\n":
        cursor = cursor.advance()

    if common_indent is None:
        common_indent = _count_leading_spaces(cursor)
        cursor = cursor.skip_spaces()
        extra_spaces = ""
    else:
        cursor, extra_spaces = _skip_common_indent(cursor, common_indent)

    return _ContinuationResult(
        cursor=cursor,
        common_indent=common_indent,
        extra_spaces=extra_spaces,
    )


def _append_newline_to_elements(
    elements: list[TextElement | Placeable],
) -> None:
    """Append newline to last element or create new TextElement."""
    if elements and not isinstance(elements[-1], Placeable):
        last_elem = elements[-1]
        elements[-1] = TextElement(value=last_elem.value + "\n")
    else:
        elements.append(TextElement(value="\n"))


def parse_simple_pattern(
    cursor: Cursor,
    context: ParseContext | None = None,
) -> ParseResult[Pattern] | None:
    """Parse simple pattern (text with optional placeables)."""
    elements: list[TextElement | Placeable] = []
    common_indent: int | None = None
    text_acc = _TextAccumulator()

    while not cursor.is_eof:
        ch = cursor.current

        if ch == "}":
            break

        if ch in ("[", "*") and _is_variant_marker(cursor):
            break

        if ch == "\n":
            if is_indented_continuation(cursor):
                cursor = cursor.advance()
                result = _process_continuation_line(cursor, common_indent)
                cursor = result.cursor
                common_indent = result.common_indent
                _append_newline_to_elements(elements)
                if result.extra_spaces:
                    text_acc.add(result.extra_spaces)
                continue
            break

        if ch == "{":
            if text_acc.has_content():
                elements.append(text_acc.finalize())
                text_acc.clear()

            cursor = cursor.advance()
            placeable_result = _parse_placeable(cursor, context)
            if placeable_result is None:
                return placeable_result

            cursor = placeable_result.cursor
            elements.append(placeable_result.value)
        else:
            text_start = cursor.pos
            while not cursor.is_eof:  # pragma: no branch
                ch = cursor.current
                if ch in ("{", "\n", "}"):
                    break
                if ch in ("[", "*") and _is_variant_marker(cursor):
                    break
                cursor = cursor.advance()

            if cursor.pos > text_start:  # pragma: no branch
                text = Cursor(cursor.source, text_start).slice_to(cursor.pos)
                if text_acc.has_content():
                    text = text_acc.finalize().value + text
                    text_acc.clear()
                elements.append(TextElement(value=text))

    if text_acc.has_content():
        elements.append(text_acc.finalize())

    return ParseResult(Pattern(elements=_trim_pattern_blank_lines(elements)), cursor)


def parse_pattern(
    cursor: Cursor,
    context: ParseContext | None = None,
    *,
    initial_common_indent: int | None = None,
) -> ParseResult[Pattern] | None:
    """Parse full pattern with multi-line continuation support."""
    elements: list[TextElement | Placeable] = []
    common_indent: int | None = initial_common_indent or None
    text_acc = _TextAccumulator()

    while not cursor.is_eof:
        ch = cursor.current

        if ch == "\n":
            if is_indented_continuation(cursor):
                cursor = cursor.advance()
                result = _process_continuation_line(cursor, common_indent)
                cursor = result.cursor
                common_indent = result.common_indent
                _append_newline_to_elements(elements)
                if result.extra_spaces:
                    text_acc.add(result.extra_spaces)
                continue
            break

        if ch == "{":
            if text_acc.has_content():
                elements.append(text_acc.finalize())
                text_acc.clear()

            cursor = cursor.advance()
            placeable_result = _parse_placeable(cursor, context)
            if placeable_result is None:
                return placeable_result

            elements.append(placeable_result.value)
            cursor = placeable_result.cursor
        else:
            text_start = cursor.pos
            while not cursor.is_eof:
                ch = cursor.current
                if ch in ("{", "\n"):
                    break
                cursor = cursor.advance()

            if cursor.pos > text_start:  # pragma: no branch
                text = Cursor(cursor.source, text_start).slice_to(cursor.pos)
                if text_acc.has_content():
                    text = text_acc.finalize().value + text
                    text_acc.clear()
                elements.append(TextElement(value=text))

    if text_acc.has_content():
        elements.append(text_acc.finalize())

    return ParseResult(Pattern(elements=_trim_pattern_blank_lines(elements)), cursor)
