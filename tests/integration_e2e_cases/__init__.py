"""End-to-end tests for parse->format workflow integration.

Tests the complete pipeline from FTL source to formatted output:
- Parse FTL source with parse_ftl()
- Add to FluentBundle via add_resource()
- Format with format_pattern()
- Verify round-trip produces expected results

These tests validate that parsing and formatting work together correctly
as an integrated system, not just as isolated components.

Note: "Bidirectional" refers to the two-way workflow (parse->format), not
bidirectional text handling or currency/number parsing from strings.

Structure:
    - TestParseFormatBasic: Essential round-trip tests (run in every CI build)
    - TestParseFormatWithVariables: Variable interpolation round-trips
    - TestParseFormatSelectExpressions: Select expression round-trips
    - TestParseFormatReferences: Message/term reference round-trips
    - TestParseFormatEdgeCases: Edge cases and unicode handling
    - TestParseFormatWithFunctions: Built-in function integration
    - TestParseFormatErrorHandling: Error paths in integration
    - TestParseFormatIntrospection: Introspection API integration
    - TestParseFormatValidation: Validation API integration
    - TestParseFormatWithCache: Caching behavior integration
    - TestParseFormatIsolation: Unicode isolation mark behavior
    - TestSerializeParseRoundtrip: AST serialization round-trips
    - TestMultiModuleIntegration: parse->validate->serialize->introspect pipeline
    - TestValidationRuntimeConsistency: validation warnings predict runtime failures
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from ftllexengine import (
    FluentBundle,
    parse_ftl,
    serialize_ftl,
)
from ftllexengine.constants import MAX_DEPTH
from ftllexengine.diagnostics import DiagnosticCode, ErrorCategory, FrozenFluentError
from ftllexengine.introspection import introspect_message
from ftllexengine.runtime.cache_config import CacheConfig
from ftllexengine.syntax.ast import Junk, Message, NumberLiteral, Term
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import serialize
from ftllexengine.validation.resource import validate_resource

__all__ = [
    "MAX_DEPTH",
    "UTC",
    "CacheConfig",
    "Decimal",
    "DiagnosticCode",
    "ErrorCategory",
    "FluentBundle",
    "FluentParserV1",
    "FrozenFluentError",
    "Junk",
    "Message",
    "NumberLiteral",
    "Term",
    "datetime",
    "introspect_message",
    "parse_ftl",
    "pytest",
    "serialize",
    "serialize_ftl",
    "validate_resource",
]
