"""Fluent syntax parsing package.

Provides parser, AST definitions, visitor pattern, and serialization.
Separate from runtime to enable tooling (linters, formatters, IDE plugins).

Python 3.13+.
"""

from .ast import (
    Annotation,
    Attribute,
    CallArguments,
    Comment,
    Entry,
    Expression,
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
