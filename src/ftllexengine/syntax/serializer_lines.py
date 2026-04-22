"""Low-level line and text emission helpers for the serializer."""

from __future__ import annotations

from enum import Enum, auto

__all__ = [
    "_ATTR_INDENT",
    "_CHAR_PLACEABLE",
    "_CONT_INDENT",
    "_VARIANT_INDENT",
    "_LineKind",
    "_classify_line",
    "_escape_text",
]

_CONT_INDENT: str = "    "
_ATTR_INDENT: str = "\n    "
_VARIANT_INDENT: str = "\n   "
_LINE_START_SYNTAX_CHARS: frozenset[str] = frozenset(".[*")
_CHAR_PLACEABLE: dict[str, str] = {
    "{": '{ "{" }',
    "}": '{ "}" }',
    "[": '{ "[" }',
    "*": '{ "*" }',
    ".": '{ "." }',
}


class _LineKind(Enum):
    """Classification of continuation-line content for serialization."""

    EMPTY = auto()
    WHITESPACE_ONLY = auto()
    SYNTAX_LEADING = auto()
    NORMAL = auto()


def _classify_line(line: str) -> tuple[_LineKind, int]:
    """Classify a continuation line for serializer dispatch."""
    if not line:
        return (_LineKind.EMPTY, 0)

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
    """Escape brace characters in text content."""
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
