"""Fluent FTL parser module.

This module provides the main FluentParserV1 parser class and related
parsing utilities organized into focused submodules.

Module Organization:
- core.py: Main FluentParserV1 class and parse() entry point
- primitives.py: Basic parsers (identifiers, numbers, strings)
- whitespace.py: Whitespace handling and continuation detection
- rules.py: All grammar rules (patterns, expressions, entries)
  - v0.27.0: Merged entries.py to eliminate circular imports
  - v0.26.0: Merged patterns.py + expressions.py to eliminate circular imports

Public API:
    FluentParserV1: Main parser class
    ParseContext: Parse context for depth tracking (advanced usage)
"""

from ftllexengine.syntax.parser.core import FluentParserV1
from ftllexengine.syntax.parser.rules import ParseContext

__all__ = ["FluentParserV1", "ParseContext"]
