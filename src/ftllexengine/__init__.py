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
    FluentNumber - Immutable formatted-number wrapper preserving numeric identity
    FluentValue - Type alias for values accepted by formatting functions
    make_fluent_number - Construct FluentNumber from int/Decimal with inferred precision
    fluent_function - Decorator for custom functions (locale injection support)
    clear_module_caches - Clear all module-level caches (memory management)

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

Parsing Return Type (no Babel dependency):
    ParseResult[T] - Return type alias for parse_* functions:
                     tuple[T | None, tuple[FrozenFluentError, ...]]

Introspection (no Babel dependency):
    MessageVariableValidationResult - Structured result of variable schema validation
    validate_message_variables - Compare FTL message variables against expected schema
    get_currency_decimal_digits - ISO 4217 decimal precision for a currency code (requires Babel)
    get_cldr_version - Babel CLDR data version string (requires Babel)

Exceptions:
    FrozenFluentError - Immutable, sealed error type
    ErrorCategory - Error classification enum (REFERENCE, RESOLUTION, CYCLIC, PARSE, FORMATTING)
    FrozenErrorContext - Immutable context for parse/formatting errors
    ParseTypeLiteral - Type alias for the parse_type field of FrozenErrorContext

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
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _get_version

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
    ParseResult,
    ParseTypeLiteral,
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
from .introspection.message import MessageVariableValidationResult, validate_message_variables
from .syntax import parse as parse_ftl
from .syntax import serialize as serialize_ftl
from .validation import validate_resource

# Babel-optional components: imported eagerly so all static analysis tools (mypy, IDEs,
# ruff) resolve the names from the import statement rather than from __getattr__ dispatch.
# On parser-only installations (no Babel) the ImportError is caught silently; __getattr__
# then provides a clear installation hint when the caller actually accesses the name.
try:
    from .core.babel_compat import (
        get_cldr_version as get_cldr_version,
    )
    from .introspection.iso import (
        get_currency_decimal_digits as get_currency_decimal_digits,
    )
    from .localization import (
        FluentLocalization as FluentLocalization,
    )
    from .runtime import (
        FluentBundle as FluentBundle,
    )
    from .runtime import (
        FluentNumber as FluentNumber,
    )
    from .runtime import (
        fluent_function as fluent_function,
    )
    from .runtime import (
        make_fluent_number as make_fluent_number,
    )
    from .runtime.cache_config import (
        CacheConfig as CacheConfig,
    )
    from .runtime.value_types import (
        FluentValue as FluentValue,
    )
except ImportError:
    pass  # Parser-only install; __getattr__ provides the installation hint on access


_BABEL_OPTIONAL_ATTRS: frozenset[str] = frozenset({
    "CacheConfig",
    "FluentBundle",
    "FluentNumber",
    "FluentLocalization",
    "FluentValue",
    "fluent_function",
    "make_fluent_number",
    "get_cldr_version",
    "get_currency_decimal_digits",
})


def __getattr__(name: str) -> object:
    """Provide a helpful ImportError for Babel-optional symbols when Babel is absent.

    Only called when Babel is NOT installed: the try/except block above did not bind
    these names into the module dict. When Babel IS installed, the names are already
    in globals() and Python resolves them without invoking this function.
    """
    if name in _BABEL_OPTIONAL_ATTRS:
        msg = (
            f"{name} requires Babel for CLDR locale data. "
            "Install with: pip install ftllexengine[babel]\n\n"
            "For parser-only usage (no Babel required), use:\n"
            "  from ftllexengine.syntax import parse, serialize\n"
            "  from ftllexengine.syntax.ast import Message, Term, Pattern, ..."
        )
        raise ImportError(msg)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


def clear_module_caches() -> None:
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
        >>> ftllexengine.clear_module_caches()  # Reclaim memory from all caches
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

# ruff: noqa: RUF022 - __all__ organized by category for readability, not alphabetically
__all__ = [
    # Bundle and Localization (Babel-optional; absent in parser-only installs)
    "CacheConfig",
    "FluentBundle",
    "FluentNumber",
    "FluentLocalization",
    "FluentValue",
    "fluent_function",
    "make_fluent_number",
    # Error types (immutable, sealed)
    "ErrorCategory",
    "FrozenErrorContext",
    "FrozenFluentError",
    "ParseTypeLiteral",
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
    # Parsing return type (no Babel dependency; lazy for init overhead)
    "ParseResult",
    # Introspection (no Babel dependency)
    "MessageVariableValidationResult",
    "validate_message_variables",
    # ISO data utilities (require Babel)
    "get_cldr_version",
    "get_currency_decimal_digits",
    # Parsing API
    "parse_ftl",
    "serialize_ftl",
    "validate_resource",
    # Utility
    "clear_module_caches",
    # Metadata
    "__fluent_spec_version__",
    "__recommended_encoding__",
    "__spec_url__",
    "__version__",
]
