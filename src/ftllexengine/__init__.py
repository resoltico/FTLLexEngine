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
    clear_all_caches - Clear all module-level caches (memory management)

Exceptions:
    FrozenFluentError - Immutable, sealed error type
    ErrorCategory - Error classification enum (REFERENCE, RESOLUTION, CYCLIC, PARSE, FORMATTING)
    FrozenErrorContext - Immutable context for parse/formatting errors

Data Integrity:
    DataIntegrityError - Base for system integrity failures
    CacheCorruptionError - Checksum mismatch in cache
    FormattingIntegrityError - Strict mode formatting failure
    ImmutabilityViolationError - Mutation attempt on frozen object
    IntegrityCheckFailedError - Generic verification failure
    SyntaxIntegrityError - Strict mode syntax error during resource loading
    WriteConflictError - Write-once violation in cache

Submodules:
    ftllexengine.syntax - Parser and AST (no Babel dependency)
    ftllexengine.syntax.ast - AST node types (Resource, Message, Term, Pattern, etc.)
    ftllexengine.introspection - Message introspection and variable extraction
    ftllexengine.parsing - Bidirectional parsing (requires Babel)
    ftllexengine.diagnostics - Error types and validation results
    ftllexengine.localization - Resource loaders and type aliases (requires Babel)
    ftllexengine.runtime - Bundle and resolver (requires Babel)
    ftllexengine.integrity - Data integrity exceptions (financial-grade safety)

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
    ErrorCategory,
    FrozenErrorContext,
    FrozenFluentError,
)
from .integrity import (
    CacheCorruptionError,
    DataIntegrityError,
    FormattingIntegrityError,
    ImmutabilityViolationError,
    IntegrityCheckFailedError,
    IntegrityContext,
    SyntaxIntegrityError,
    WriteConflictError,
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


def clear_all_caches() -> None:
    """Clear all module-level caches in the library.

    Provides unified cache management for long-running applications. Clears:
    - Babel locale object cache (locale_utils)
    - CLDR date/datetime pattern caches (parsing.dates)
    - CLDR currency data caches (parsing.currency)
    - LocaleContext instance cache (runtime.locale_context)
    - Message introspection result cache (introspection.message)
    - ISO territory/currency introspection cache (introspection.iso)

    Useful for:
    - Memory reclamation in long-running server applications
    - Testing scenarios requiring fresh cache state
    - After Babel/CLDR data updates

    Thread-safe. Each underlying cache uses its own locking mechanism.

    Note:
        This function does NOT require Babel. It clears caches regardless
        of whether Babel-dependent modules have been imported. Caches that
        haven't been populated yet are simply no-ops.

        FluentBundle instances maintain their own FormatCache which is NOT
        cleared by this function. To clear bundle-specific caches, use
        bundle._cache.clear() on each bundle instance.

    Example:
        >>> import ftllexengine
        >>> ftllexengine.clear_all_caches()  # Reclaim memory from all caches
    """
    # Import and clear each cache module
    # Order: parsing caches first (depend on locale cache), then locale, then introspection

    # 1. Parsing caches (use locale_utils internally)
    from .parsing.currency import clear_currency_caches
    from .parsing.dates import clear_date_caches

    clear_currency_caches()
    clear_date_caches()

    # 2. Locale caches
    from .locale_utils import clear_locale_cache
    from .runtime.locale_context import LocaleContext

    clear_locale_cache()
    LocaleContext.clear_cache()

    # 3. Introspection caches (message introspection + ISO standards data)
    from .introspection import clear_introspection_cache, clear_iso_cache

    clear_introspection_cache()
    clear_iso_cache()


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
# ruff: noqa: RUF022 - __all__ organized by category for readability, not alphabetically
__all__ = [
    # Bundle and Localization (lazy-loaded, require Babel)
    "FluentBundle",
    "FluentLocalization",
    "FluentValue",
    "fluent_function",
    # Error types (immutable, sealed)
    "ErrorCategory",
    "FrozenErrorContext",
    "FrozenFluentError",
    # Data integrity exceptions
    "CacheCorruptionError",
    "DataIntegrityError",
    "FormattingIntegrityError",
    "ImmutabilityViolationError",
    "IntegrityCheckFailedError",
    "IntegrityContext",
    "SyntaxIntegrityError",
    "WriteConflictError",
    # Parsing API
    "parse_ftl",
    "serialize_ftl",
    "validate_resource",
    # Utility
    "clear_all_caches",
    # Metadata
    "__fluent_spec_version__",
    "__recommended_encoding__",
    "__spec_url__",
    "__version__",
]
