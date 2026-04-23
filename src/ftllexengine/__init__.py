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
    CacheConfig - Immutable runtime cache configuration (no external dependencies)
    clear_module_caches - Clear all module-level caches (memory management)

Localization Loading (no Babel dependency):
    LoadSummary - Aggregate of all resource load results from initialization
    ResourceLoadResult - Immutable result of a single resource load attempt
    FallbackInfo - Immutable record of a locale fallback event
    ResourceLoader - Protocol for loading FTL resources (structural typing)
    PathResourceLoader - Disk-based loader with path-traversal prevention

Localization Boot (requires Babel):
    LocalizationBootConfig - One-shot boot orchestrator for strict-mode assembly
    LocalizationCacheStats - Cache statistics for all locales in a FluentLocalization

Locale Utilities (no Babel dependency):
    LoadStatus - Enum of resource load statuses (SUCCESS, NOT_FOUND, ERROR)
    LocaleCode - Type alias for BCP-47 / POSIX locale codes (e.g. "en_US", "de")
    MessageId - Type alias for Fluent message identifiers
    ResourceId - Type alias for loader resource identifiers
    FTLSource - Type alias for raw Fluent source text
    normalize_locale - Convert BCP-47 to canonical lowercase POSIX form
    get_system_locale - Detect locale from OS environment variables

Boundary Validators:
    require_date - Validate that a boundary value is a date (not datetime)
    require_datetime - Validate that a boundary value is a datetime
    require_fluent_number - Validate that a boundary value is a FluentNumber
    require_locale_code - Validate and canonicalize a locale code at a
                          system boundary
    require_currency_code - Validate and normalize an ISO 4217 currency code
                            (Babel-backed)
    require_territory_code - Validate and normalize an ISO 3166-1 alpha-2
                             territory code (Babel-backed)

Parsing Return Type (no Babel dependency):
    ParseResult[T] - Return type alias for parse_* functions:
                     tuple[T | None, tuple[FrozenFluentError, ...]]

Introspection (no Babel dependency):
    MessageVariableValidationResult - Structured result of variable schema validation
    validate_message_variables - Compare FTL message variables against expected schema

ISO Standards (full-runtime CLDR data required at call time; importable in parser-only installs):
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
    ftllexengine.localization - Resource loaders always available; FluentLocalization requires Babel
    ftllexengine.runtime - Helper types always available; bundle classes require Babel
    ftllexengine.integrity - Data integrity exceptions (fail-fast validation)

Installation:
    # Parser-only install:
    pip install ftllexengine

    # Full runtime install:
    pip install ftllexengine[babel]
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _get_version
from typing import TYPE_CHECKING

from ._optional_exports import (
    ROOT_BABEL_OPTIONAL_ATTRS as _BABEL_OPTIONAL_ATTRS,
)
from ._optional_exports import (
    load_root_babel_optional_exports,
    raise_missing_babel_symbol,
)
from .analysis import detect_cycles
from .cache_management import clear_module_caches
from .core.babel_compat import get_cldr_version, is_babel_available
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
from .localization.loading import (
    FallbackInfo,
    LoadSummary,
    PathResourceLoader,
    ResourceLoader,
    ResourceLoadResult,
)
from .runtime.cache_config import CacheConfig
from .runtime.function_bridge import FluentNumber, fluent_function
from .runtime.value_types import FluentValue, make_fluent_number
from .syntax import parse as parse_ftl
from .syntax import parse_stream as parse_stream_ftl
from .syntax import serialize as serialize_ftl
from .validation import validate_resource

if TYPE_CHECKING:
    from .localization import FluentLocalization, LocalizationBootConfig, LocalizationCacheStats
    from .runtime import AsyncFluentBundle, FluentBundle

_BABEL_AVAILABLE = is_babel_available()

if _BABEL_AVAILABLE:
    globals().update(load_root_babel_optional_exports())


def __getattr__(name: str) -> object:
    """Provide a helpful missing-symbol error for Babel-backed facade symbols."""
    return raise_missing_babel_symbol(
        module_name=__name__,
        name=name,
        optional_attrs=_BABEL_OPTIONAL_ATTRS,
        parser_only_hint=(
            "For parser-only installs, use:\n"
            "  from ftllexengine.syntax import parse, serialize\n"
            "  from ftllexengine.syntax.ast import Message, Term, Pattern, ..."
        ),
    )


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
    # Babel-backed facades
    "AsyncFluentBundle",
    # Runtime helpers and localization loading (parser-only safe)
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
    # ISO standards (importable in parser-only installs; most validate via Babel at call time)
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

if not _BABEL_AVAILABLE:
    __all__ = [name for name in __all__ if name not in _BABEL_OPTIONAL_ATTRS]
