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

Fiscal Calendar (no Babel dependency):
    FiscalCalendar - Configuration for fiscal year boundaries
    FiscalDelta - Immutable fiscal period delta for date arithmetic
    FiscalPeriod - Immutable fiscal period identifier (year, quarter, month)
    MonthEndPolicy - Enum for month-end date handling in arithmetic
    fiscal_quarter - Fiscal quarter for a date
    fiscal_year - Fiscal year for a date
    fiscal_month - Fiscal month for a date
    fiscal_year_start - First day of a fiscal year
    fiscal_year_end - Last day of a fiscal year

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
    ftllexengine.core.fiscal - Fiscal calendar arithmetic (no Babel dependency)
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

# Fiscal calendar - no Babel dependency; imported after diagnostics to avoid circular import
from .core.fiscal import (
    FiscalCalendar,
    FiscalDelta,
    FiscalPeriod,
    MonthEndPolicy,
    fiscal_month,
    fiscal_quarter,
    fiscal_year,
    fiscal_year_end,
    fiscal_year_start,
)

# Error types must load before core to avoid circular import:
# diagnostics -> validation -> syntax.ast -> syntax.__init__ -> serializer -> core.depth_guard
# depth_guard imports from diagnostics; diagnostics must be in sys.modules first.
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
    from .runtime.cache_config import CacheConfig as CacheConfigType
    from .runtime.value_types import FluentValue as FluentValueType

# Lazy-loaded attributes that require Babel for CLDR locale data
_BABEL_REQUIRED_ATTRS = frozenset({
    "FluentBundle",
    "FluentLocalization",
})

# Lazy-loaded attributes that do NOT require Babel (pure Python utilities)
# These are lazy-loaded to avoid runtime package initialization overhead,
# not because of Babel dependency.
_BABEL_INDEPENDENT_ATTRS = frozenset({
    "CacheConfig",
    "FluentValue",
    "fluent_function",
})

def __getattr__(name: str) -> object:
    """Lazy import for components.

    Handles two categories:
    - Babel-dependent (FluentBundle, FluentLocalization): Clear error if Babel missing
    - Babel-independent (CacheConfig, FluentValue, fluent_function): No Babel required

    Uses the standard ``globals()[name] = obj`` caching pattern so the attribute is
    stored in the module dict after the first access. Subsequent lookups hit
    ``module.__dict__`` directly without going through ``__getattr__`` again.
    """
    # Babel-independent utilities (no Babel dependency, lazy for package init overhead)
    if name in _BABEL_INDEPENDENT_ATTRS:
        match name:
            case "CacheConfig":
                from .runtime.cache_config import CacheConfig
                globals()[name] = CacheConfig
                return CacheConfig
            case "FluentValue":
                from .runtime.value_types import FluentValue
                globals()[name] = FluentValue
                return FluentValue
            case "fluent_function":
                from .runtime.function_bridge import fluent_function
                globals()[name] = fluent_function
                return fluent_function
            case _:
                msg = f"__getattr__: unhandled Babel-independent attribute {name!r}"
                raise AssertionError(msg)

    # Babel-dependent components
    if name in _BABEL_REQUIRED_ATTRS:
        try:
            match name:
                case "FluentBundle":
                    from .runtime import FluentBundle
                    globals()[name] = FluentBundle
                    return FluentBundle
                case "FluentLocalization":
                    from .localization import FluentLocalization
                    globals()[name] = FluentLocalization
                    return FluentLocalization
                case _:
                    msg = f"__getattr__: unhandled Babel-required attribute {name!r}"
                    raise AssertionError(msg)
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

        FluentBundle instances maintain their own IntegrityCache which is NOT
        cleared by this function. To clear a bundle's format cache, call
        ``bundle.clear_cache()``.

    Example:
        >>> import ftllexengine
        >>> ftllexengine.clear_all_caches()  # Reclaim memory from all caches
    """
    # Import and clear each cache module.
    # Order: parsing caches first (depend on locale cache), then locale, then introspection.
    # Parsing and runtime caches are conditionally cleared: they are Babel-dependent and
    # may not have been imported in parser-only installations. Skipping an unimported module
    # is semantically correct — an unimported module has no populated cache to clear.

    # 1. Parsing caches (Babel-dependent: only present in full-runtime installations)
    try:
        from .parsing.currency import clear_currency_caches
        clear_currency_caches()
    except ImportError:  # pragma: no cover
        pass  # Parser-only installation; parsing.currency never imported

    try:
        from .parsing.dates import clear_date_caches
        clear_date_caches()
    except ImportError:  # pragma: no cover
        pass  # Parser-only installation; parsing.dates never imported

    # 2. Locale caches (always present: core.locale_utils has no Babel dep at module level)
    from .core.locale_utils import clear_locale_cache

    clear_locale_cache()

    # 3. Runtime locale context (Babel-dependent)
    try:
        from .runtime.locale_context import LocaleContext
        LocaleContext.clear_cache()
    except ImportError:  # pragma: no cover
        pass  # Parser-only installation; runtime.locale_context never imported

    # 4. Introspection caches (message introspection + ISO standards data)
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
    "CacheConfig",
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
    # Fiscal calendar (no Babel dependency)
    "FiscalCalendar",
    "FiscalDelta",
    "FiscalPeriod",
    "MonthEndPolicy",
    "fiscal_month",
    "fiscal_quarter",
    "fiscal_year",
    "fiscal_year_end",
    "fiscal_year_start",
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
