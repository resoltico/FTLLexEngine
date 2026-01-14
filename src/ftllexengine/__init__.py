"""FTLLexEngine - Fluent (FTL) implementation with locale-aware parsing.

A logic engine for text and a parsing gateway. Implements the Fluent Template Language
specification with thread-safe formatting, input parsing (numbers, dates, currency),
and declarative grammar logic via .ftl resources.

Public API:
    FluentBundle - Single-locale message formatting (requires Babel)
    FluentLocalization - Multi-locale orchestration with fallback chains (requires Babel)
    parse_ftl - Parse FTL source to AST (no external dependencies)
    serialize_ftl - Serialize AST to FTL source (no external dependencies)
    validate_resource - Validate FTL resource for semantic errors (no external dependencies)
    FluentValue - Type alias for values accepted by formatting functions
    fluent_function - Decorator for custom functions (locale injection support)

Exceptions:
    FluentError - Base exception class
    FluentSyntaxError - Parse errors
    FluentReferenceError - Unknown message/term references
    FluentResolutionError - Runtime resolution errors

Submodules:
    ftllexengine.syntax - Parser and AST (no Babel dependency)
    ftllexengine.syntax.ast - AST node types (Resource, Message, Term, Pattern, etc.)
    ftllexengine.introspection - Message introspection and variable extraction
    ftllexengine.parsing - Bidirectional parsing (requires Babel)
    ftllexengine.diagnostics - Error types and validation results
    ftllexengine.localization - Resource loaders and type aliases (requires Babel)
    ftllexengine.runtime - Bundle and resolver (requires Babel)

Installation:
    # Parser-only (no external dependencies):
    pip install ftllexengine

    # Full runtime with locale formatting (requires Babel):
    pip install ftllexengine[babel]
    # or
    pip install ftllexengine[full]
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _get_version
from typing import TYPE_CHECKING

# Core API - Always available (no Babel dependency)
from .diagnostics import (
    FluentError,
    FluentReferenceError,
    FluentResolutionError,
    FluentSyntaxError,
)
from .syntax import parse as parse_ftl
from .syntax import serialize as serialize_ftl
from .validation import validate_resource

if TYPE_CHECKING:
    # Type hints only - not imported at runtime to avoid Babel dependency
    from .localization import FluentLocalization as FluentLocalizationType
    from .runtime import FluentBundle as FluentBundleType
    from .runtime.function_bridge import FluentValue as FluentValueType

# Lazy-loaded attributes (require Babel)
_BABEL_REQUIRED_ATTRS = frozenset({
    "FluentBundle",
    "FluentLocalization",
    "FluentValue",
    "fluent_function",
})

# Cache for lazy-loaded modules
_lazy_cache: dict[str, object] = {}


def __getattr__(name: str) -> object:
    """Lazy import for Babel-dependent components.

    Provides clear error message when Babel is not installed.
    """
    if name in _BABEL_REQUIRED_ATTRS:
        if name in _lazy_cache:
            return _lazy_cache[name]

        try:
            if name == "FluentBundle":
                from .runtime import FluentBundle
                _lazy_cache[name] = FluentBundle
                return FluentBundle
            if name == "FluentLocalization":
                from .localization import FluentLocalization
                _lazy_cache[name] = FluentLocalization
                return FluentLocalization
            if name == "FluentValue":
                from .runtime.function_bridge import FluentValue
                _lazy_cache[name] = FluentValue
                return FluentValue
            if name == "fluent_function":
                from .runtime.function_bridge import fluent_function
                _lazy_cache[name] = fluent_function
                return fluent_function
        except ImportError as e:
            if "babel" in str(e).lower() or "No module named 'babel'" in str(e):
                msg = (
                    f"{name} requires Babel for CLDR locale data. "
                    "Install with: pip install ftllexengine[babel]\n\n"
                    "For parser-only usage (no Babel required), use:\n"
                    "  from ftllexengine.syntax import parse, serialize\n"
                    "  from ftllexengine.syntax.ast import Message, Term, Pattern, ..."
                )
                raise ImportError(msg) from e
            raise

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)

# Version information - Auto-populated from package metadata
# SINGLE SOURCE OF TRUTH: pyproject.toml [project] version
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

# pylint: disable=undefined-all-variable
# Reason: FluentBundle, FluentLocalization, FluentValue, fluent_function are lazy-loaded
# via __getattr__ to defer Babel dependency. Pylint cannot see these at static analysis time.
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
    "validate_resource",
]
