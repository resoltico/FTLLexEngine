"""Fluent syntax parsing package.

Provides parser, AST definitions, visitor pattern, and serialization.
Separate from runtime to enable tooling (linters, formatters, IDE plugins).

Python 3.14+.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

from .ast import (
    Annotation,
    Attribute,
    CallArguments,
    Comment,
    Entry,
    Expression,
    FTLLiteral,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    MessageReference,
    NamedArgument,
    NumberLiteral,
    Pattern,
    PatternElement,
    Placeable,
    Resource,
    SelectExpression,
    SelectorExpression,
    Span,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)
from .cursor import Cursor, ParseError, ParseResult
from .parser import FluentParserV1
from .serializer import SerializationDepthError, SerializationValidationError, serialize
from .visitor import ASTTransformer, ASTVisitor

# Note: FluentSerializer is intentionally NOT exported.
# Users should use the serialize() function instead of instantiating FluentSerializer directly.

__all__ = [
    "ASTTransformer",
    "ASTVisitor",
    "Annotation",
    "Attribute",
    "CallArguments",
    "Comment",
    "Cursor",
    "Entry",
    "Expression",
    "FTLLiteral",
    "FluentParserV1",
    "FunctionReference",
    "Identifier",
    "Junk",
    "Message",
    "MessageReference",
    "NamedArgument",
    "NumberLiteral",
    "ParseError",
    "ParseResult",
    "Pattern",
    "PatternElement",
    "Placeable",
    "Resource",
    "SelectExpression",
    "SelectorExpression",
    "SerializationDepthError",
    "SerializationValidationError",
    "Span",
    "StringLiteral",
    "Term",
    "TermReference",
    "TextElement",
    "VariableReference",
    "Variant",
    "parse",
    "parse_stream",
    "serialize",
]


def parse(source: str) -> Resource:
    """Parse FTL source into AST.

    Convenience function for FluentParserV1.parse().

    Args:
        source: FTL source code

    Returns:
        Resource containing parsed entries

    Example:
        >>> from ftllexengine.syntax import parse
        >>> resource = parse("hello = Hello, world!")
        >>> resource.entries[0].id.name
        'hello'
    """
    parser = FluentParserV1()
    return parser.parse(source)


def parse_stream(lines: Iterable[str]) -> Iterator[Entry]:
    """Parse FTL entries incrementally from a line-oriented source stream.

    Convenience function for FluentParserV1.parse_stream(). Yields entries as
    each blank-line-delimited chunk is parsed, without materializing the full
    source string. Memory usage is proportional to the largest single entry.

    Span positions in yielded entries are chunk-relative, not stream-relative.
    Use parse() when absolute span positions are required (e.g., IDE tooling).

    Args:
        lines: Iterable of FTL source lines. Trailing newlines are stripped per
               line; the stream need not be pre-normalized.

    Yields:
        Message, Term, Comment, or Junk AST nodes in document order.

    Example:
        >>> from ftllexengine.syntax import parse_stream
        >>> lines = ["greeting = Hello\\n", "\\n", "farewell = Bye\\n"]
        >>> entries = list(parse_stream(lines))
        >>> len(entries)
        2
        >>> entries[0].id.name
        'greeting'
    """
    parser = FluentParserV1()
    yield from parser.parse_stream(lines)
