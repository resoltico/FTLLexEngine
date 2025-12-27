"""FTLLexEngine - Fluent (FTL) implementation with locale-aware parsing.

A logic engine for text and a parsing gateway. Implements the Fluent Template Language
specification with thread-safe formatting, input parsing (numbers, dates, currency),
and declarative grammar logic via .ftl resources.

Public API:
    FluentBundle - Single-locale message formatting
    FluentLocalization - Multi-locale orchestration with fallback chains
    parse_ftl - Parse FTL source to AST
    serialize_ftl - Serialize AST to FTL source
    FluentValue - Type alias for values accepted by formatting functions
    fluent_function - Decorator for custom functions (locale injection support)

Exceptions:
    FluentError - Base exception class
    FluentSyntaxError - Parse errors
    FluentReferenceError - Unknown message/term references
    FluentResolutionError - Runtime resolution errors

Submodules:
    ftllexengine.syntax.ast - AST node types (Resource, Message, Term, Pattern, etc.)
    ftllexengine.introspection - Message introspection and variable extraction
    ftllexengine.parsing - Bidirectional parsing (parse_number, parse_date, parse_currency)
    ftllexengine.diagnostics - Error types and validation results
    ftllexengine.localization - Resource loaders and type aliases
    ftllexengine.runtime.locale_context - Thread-safe LocaleContext for formatting
"""

# Essential Public API - Minimal exports for clean namespace
from .diagnostics import (
    FluentError,
    FluentReferenceError,
    FluentResolutionError,
    FluentSyntaxError,
)
from .localization import FluentLocalization
from .runtime import FluentBundle
from .runtime.function_bridge import FluentValue, fluent_function
from .syntax import parse as parse_ftl
from .syntax import serialize as serialize_ftl

# Version information - Auto-populated from package metadata
# SINGLE SOURCE OF TRUTH: pyproject.toml [project] version
try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _get_version
except ImportError as e:
    # This should never happen on Python 3.13+ (importlib.metadata is stdlib since 3.8)
    raise RuntimeError("importlib.metadata unavailable - Python version too old? " + str(e)) from e

try:
    __version__ = _get_version("ftllexengine")
except PackageNotFoundError:
    # Development mode: package not installed yet
    # Run: uv sync
    __version__ = "0.0.0+dev"

# Fluent specification conformance
__fluent_spec_version__ = "1.0"  # FTL (Fluent Template Language) Specification v1.0
__spec_url__ = "https://github.com/projectfluent/fluent/blob/master/spec/fluent.ebnf"

# Encoding requirements per Fluent spec recommendations.md
__recommended_encoding__ = "UTF-8"  # Per spec: "The recommended encoding for Fluent files is UTF-8"

__all__ = [
    "FluentBundle",
    "FluentError",
    "FluentLocalization",
    "FluentReferenceError",
    "FluentResolutionError",
    "FluentSyntaxError",
    "FluentValue",
    "__fluent_spec_version__",
    "__recommended_encoding__",
    "__spec_url__",
    "__version__",
    "fluent_function",
    "parse_ftl",
    "serialize_ftl",
]
