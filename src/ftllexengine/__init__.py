"""FTLLexEngine - Fluent (FTL) implementation with locale-aware parsing.

A logic engine for text and a parsing gateway. Implements the Fluent Template Language
specification with thread-safe formatting, input parsing (numbers, dates, currency),
and declarative grammar logic via .ftl resources.

Public API:
    FluentBundle - Single-locale message formatting (requires Babel)
    AsyncFluentBundle - Async-native wrapper around FluentBundle (requires Babel)
    FluentLocalization - Multi-locale orchestration with fallback chains (requires Babel)
    parse_ftl - Parse FTL source to AST (no external dependencies)
    parse_stream_ftl - Parse FTL source from a line iterator, yields entries incrementally
    serialize_ftl - Serialize AST to FTL source (no external dependencies)
    validate_resource - Validate FTL resource for semantic errors (no external dependencies)
    FluentNumber - Immutable formatted-number wrapper preserving numeric identity
    FluentValue - Type alias for values accepted by formatting functions
    make_fluent_number - Construct FluentNumber from int/Decimal with inferred precision
    fluent_function - Decorator for custom functions (locale injection support)
    clear_module_caches - Clear all module-level caches (memory management)

Localization Boot (requires Babel):
    LocalizationBootConfig - One-shot boot orchestrator for strict-mode assembly
    LoadSummary - Aggregate of all resource load results from initialization
    ResourceLoadResult - Immutable result of a single resource load attempt
    FallbackInfo - Immutable record of a locale fallback event
    ResourceLoader - Protocol for loading FTL resources (structural typing)
    PathResourceLoader - Disk-based loader with path-traversal prevention
    LocalizationCacheStats - Cache statistics for all locales in a FluentLocalization

Locale Utilities (no Babel dependency):
    LoadStatus - Enum of resource load statuses (SUCCESS, NOT_FOUND, ERROR)
    LocaleCode - Type alias for BCP-47 / POSIX locale codes (e.g. "en_US", "de")
    MessageId - Type alias for Fluent message identifiers
    ResourceId - Type alias for loader resource identifiers
    FTLSource - Type alias for raw Fluent source text
    normalize_locale - Convert BCP-47 to canonical lowercase POSIX form
    get_system_locale - Detect locale from OS environment variables

Domain Validators (no Babel dependency):
    require_currency_code - Validate and normalize an ISO 4217 currency code (requires Babel)
    require_date - Validate that a boundary value is a date (not datetime)
    require_datetime - Validate that a boundary value is a datetime
    require_fluent_number - Validate that a boundary value is a FluentNumber
    require_locale_code - Validate and canonicalize a locale code at a system boundary
    require_territory_code - Validate and normalize an ISO 3166-1 alpha-2 territory code

Parsing Return Type (no Babel dependency):
    ParseResult[T] - Return type alias for parse_* functions:
                     tuple[T | None, tuple[FrozenFluentError, ...]]

Introspection (no Babel dependency):
    MessageVariableValidationResult - Structured result of variable schema validation
    validate_message_variables - Compare FTL message variables against expected schema

ISO Standards (Babel required at call time; importable without Babel):
    CurrencyCode - ISO 4217 currency code NewType (e.g., CurrencyCode("USD"))
    TerritoryCode - ISO 3166-1 alpha-2 territory code NewType (e.g., TerritoryCode("US"))
    is_valid_currency_code - TypeIs guard: True if str is a valid ISO 4217 code (requires Babel)
    is_valid_territory_code - TypeIs guard: True if str is a valid ISO 3166-1 alpha-2 code
    get_currency_decimal_digits - ISO 4217 decimal precision for a currency code (no Babel required)
    get_cldr_version - Babel CLDR data version string (requires Babel)

Diagnostics:
    WarningSeverity - Severity levels for validation warnings (CRITICAL, WARNING, INFO)

Graph Analysis:
    detect_cycles - Detect circular dependencies in a message/term reference graph

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
    ftllexengine.introspection - Message introspection and variable extraction
    ftllexengine.parsing - Bidirectional parsing (requires Babel)
    ftllexengine.diagnostics - Error types and validation results
    ftllexengine.localization - Resource loaders and type aliases (requires Babel)
    ftllexengine.runtime - Bundle and resolver (requires Babel)
    ftllexengine.integrity - Data integrity exceptions (fail-fast validation)

Installation:
    # Parser-only (no external dependencies):
    pip install ftllexengine

    # Full runtime with locale formatting (requires Babel):
    pip install ftllexengine[babel]
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _get_version

from .analysis import detect_cycles
from .core.locale_utils import get_system_locale, normalize_locale, require_locale_code
from .core.semantic_types import FTLSource, LocaleCode, MessageId, ResourceId

# Domain validators - no Babel dependency; no circular import risk
from .core.validators import (
    require_date,
    require_datetime,
    require_fluent_number,
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
    WarningSeverity,
)
from .enums import LoadStatus
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
from .introspection.iso import (
    CurrencyCode,
    TerritoryCode,
    get_currency_decimal_digits,
    is_valid_currency_code,
    is_valid_territory_code,
    require_currency_code,
    require_territory_code,
)
from .introspection.message import MessageVariableValidationResult, validate_message_variables
from .syntax import parse as parse_ftl
from .syntax import parse_stream as parse_stream_ftl
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
    from .localization import (
        FallbackInfo as FallbackInfo,
    )
    from .localization import (
        FluentLocalization as FluentLocalization,
    )
    from .localization import (
        LoadSummary as LoadSummary,
    )
    from .localization import (
        LocalizationBootConfig as LocalizationBootConfig,
    )
    from .localization import (
        LocalizationCacheStats as LocalizationCacheStats,
    )
    from .localization import (
        PathResourceLoader as PathResourceLoader,
    )
    from .localization import (
        ResourceLoader as ResourceLoader,
    )
    from .localization import (
        ResourceLoadResult as ResourceLoadResult,
    )
    from .runtime import (
        AsyncFluentBundle as AsyncFluentBundle,
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
    "AsyncFluentBundle",
    "CacheConfig",
    "FallbackInfo",
    "FluentBundle",
    "FluentNumber",
    "FluentLocalization",
    "FluentValue",
    "LoadSummary",
    "LocalizationBootConfig",
    "LocalizationCacheStats",
    "PathResourceLoader",
    "ResourceLoadResult",
    "ResourceLoader",
    "fluent_function",
    "make_fluent_number",
    "get_cldr_version",
})


def __getattr__(name: str) -> object:
    """Provide a helpful ImportError for Babel-optional symbols when Babel is absent.

    Only called when Babel is NOT installed: the try/except block above did not bind
    these names into the module dict. When Babel IS installed, the names are already
    in globals() and Python resolves them without invoking this function.
    """
    if name in _BABEL_OPTIONAL_ATTRS:
        msg = (
            f"{name} requires the full runtime install (Babel + CLDR locale data). "
            "Install with: pip install ftllexengine[babel]\n\n"
            "For parser-only usage (no Babel required), use:\n"
            "  from ftllexengine.syntax import parse, serialize\n"
            "  from ftllexengine.syntax.ast import Message, Term, Pattern, ..."
        )
        raise ImportError(msg)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


def clear_module_caches(
    components: frozenset[str] | None = None,
) -> None:
    """Clear module-level caches in the library.

    Provides unified cache management for long-running applications. With
    ``components=None`` (the default), clears all caches:

    - ``'parsing.currency'``: CLDR currency data caches
    - ``'parsing.dates'``: CLDR date/datetime pattern caches
    - ``'locale'``: Babel locale object cache (locale_utils)
    - ``'runtime.locale_context'``: LocaleContext instance cache
    - ``'introspection.message'``: Message introspection result cache
    - ``'introspection.iso'``: ISO territory/currency introspection cache

    Pass a ``frozenset`` of component names to clear only specific caches.
    This is useful when certain caches (e.g., Babel locale data) are expensive
    to repopulate and should not be cleared during routine periodic trimming.

    Args:
        components: Set of component names to clear. When ``None``, clears all
            caches. Known component names: ``'parsing.currency'``,
            ``'parsing.dates'``, ``'locale'``, ``'runtime.locale_context'``,
            ``'introspection.message'``, ``'introspection.iso'``.
            Unknown component names are silently ignored.

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
        >>> import ftllexengine  # doctest: +SKIP
        >>> ftllexengine.clear_module_caches()  # Clear all caches  # doctest: +SKIP
        >>> ftllexengine.clear_module_caches(  # Clear only ISO + message caches  # doctest: +SKIP
        ...     components=frozenset({'introspection.iso', 'introspection.message'})
        ... )
    """
    # Import and clear each cache module.
    # Order: parsing caches first (depend on locale cache), then locale, then introspection.
    # Parsing and runtime caches are conditionally cleared: they are Babel-dependent and
    # may not have been imported in parser-only installations. Skipping an unimported module
    # is semantically correct — an unimported module has no populated cache to clear.

    # When components is None (clear all), use an empty sentinel so that every
    # `_want()` call short-circuits via clear_all without inspecting the set.
    clear_all = components is None
    _comps: frozenset[str] = frozenset() if components is None else components

    def _want(name: str) -> bool:
        return clear_all or name in _comps

    # 1. Parsing caches (Babel-dependent: only present in full-runtime installations)
    if _want("parsing.currency"):
        try:
            from .parsing.currency import clear_currency_caches
            clear_currency_caches()
        except ImportError:  # pragma: no cover
            pass  # Parser-only installation; parsing.currency never imported

    if _want("parsing.dates"):
        try:
            from .parsing.dates import clear_date_caches
            clear_date_caches()
        except ImportError:  # pragma: no cover
            pass  # Parser-only installation; parsing.dates never imported

    # 2. Locale caches (always present: core.locale_utils has no Babel dep at module level)
    if _want("locale"):
        from .core.locale_utils import clear_locale_cache

        clear_locale_cache()

    # 3. Runtime locale context (Babel-dependent)
    if _want("runtime.locale_context"):
        try:
            from .runtime.locale_context import LocaleContext
            LocaleContext.clear_cache()
        except ImportError:  # pragma: no cover
            pass  # Parser-only installation; runtime.locale_context never imported

    # 4. Introspection caches (message introspection + ISO standards data)
    if _want("introspection.message"):
        from .introspection import clear_introspection_cache

        clear_introspection_cache()

    if _want("introspection.iso"):
        from .introspection import clear_iso_cache

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
    "AsyncFluentBundle",
    "CacheConfig",
    "FallbackInfo",
    "FluentBundle",
    "FluentNumber",
    "FluentLocalization",
    "FluentValue",
    "LoadSummary",
    "LocalizationBootConfig",
    "LocalizationCacheStats",
    "PathResourceLoader",
    "ResourceLoadResult",
    "ResourceLoader",
    "fluent_function",
    "make_fluent_number",
    # Localization status enum (no Babel dependency)
    "LoadStatus",
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
    # Locale utilities (no Babel dependency)
    "FTLSource",
    "LocaleCode",
    "MessageId",
    "ResourceId",
    "get_system_locale",
    "normalize_locale",
    # Domain validators (no Babel dependency)
    "require_currency_code",
    "require_date",
    "require_datetime",
    "require_fluent_number",
    "require_locale_code",
    "require_territory_code",
    # Parsing return type (no Babel dependency; lazy for init overhead)
    "ParseResult",
    # Introspection (no Babel dependency)
    "MessageVariableValidationResult",
    "validate_message_variables",
    # ISO standards (importable without Babel; most raise BabelImportError when called)
    "CurrencyCode",
    "TerritoryCode",
    "get_cldr_version",
    "get_currency_decimal_digits",
    "is_valid_currency_code",
    "is_valid_territory_code",
    # Diagnostics
    "WarningSeverity",
    # Graph analysis
    "detect_cycles",
    # Parsing API
    "parse_ftl",
    "parse_stream_ftl",
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
