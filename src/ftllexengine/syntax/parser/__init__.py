"""Fluent FTL parser module.

This module provides the main FluentParserV1 parser class and related
parsing utilities organized into focused submodules.

Module Organization:
- core.py: Main FluentParserV1 class and parse() entry point
- context.py: ParseContext depth-tracking state
- entries.py: Message, term, and comment parsing
- expressions.py: Inline expressions, calls, and select expressions
- patterns.py: Pattern parsing and multiline continuation handling
- primitives.py: Basic parsers (identifiers, numbers, strings)
- whitespace.py: Whitespace handling and continuation detection
- rules.py: Aggregated grammar surface for advanced internal/test usage

Public API:
    FluentParserV1: Main parser class
    ParseContext: Parse context for depth tracking (advanced usage)
"""

from ftllexengine.syntax.parser.context import ParseContext
from ftllexengine.syntax.parser.core import FluentParserV1

__all__ = ["FluentParserV1", "ParseContext"]
