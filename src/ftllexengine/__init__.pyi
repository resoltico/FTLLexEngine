# ISO data utilities (require Babel)
from .core.babel_compat import get_cldr_version as get_cldr_version

# Fiscal calendar (no Babel dependency)
from .core.fiscal import FiscalCalendar as FiscalCalendar
from .core.fiscal import FiscalDelta as FiscalDelta
from .core.fiscal import FiscalPeriod as FiscalPeriod
from .core.fiscal import MonthEndPolicy as MonthEndPolicy
from .core.fiscal import fiscal_month as fiscal_month
from .core.fiscal import fiscal_quarter as fiscal_quarter
from .core.fiscal import fiscal_year as fiscal_year
from .core.fiscal import fiscal_year_end as fiscal_year_end
from .core.fiscal import fiscal_year_start as fiscal_year_start

# Locale utilities (no Babel dependency)
from .core.locale_utils import get_system_locale as get_system_locale
from .core.locale_utils import normalize_locale as normalize_locale
from .core.locale_utils import require_locale_code as require_locale_code

# Boundary validators (no Babel dependency)
from .core.validators import coerce_tuple as coerce_tuple
from .core.validators import require_int as require_int
from .core.validators import require_non_empty_str as require_non_empty_str
from .core.validators import require_non_negative_int as require_non_negative_int
from .core.validators import require_positive_int as require_positive_int

# Core API - Error types (immutable, sealed)
from .diagnostics import (
    ErrorCategory as ErrorCategory,
)
from .diagnostics import (
    FrozenErrorContext as FrozenErrorContext,
)
from .diagnostics import (
    FrozenFluentError as FrozenFluentError,
)
from .diagnostics import (
    ParseResult as ParseResult,
)
from .diagnostics import (
    ParseTypeLiteral as ParseTypeLiteral,
)

# Localization status enum (no Babel dependency)
from .enums import LoadStatus as LoadStatus

# Data integrity exceptions
from .integrity import (
    CacheCorruptionError as CacheCorruptionError,
)
from .integrity import (
    DataIntegrityError as DataIntegrityError,
)
from .integrity import (
    FormattingIntegrityError as FormattingIntegrityError,
)
from .integrity import (
    ImmutabilityViolationError as ImmutabilityViolationError,
)
from .integrity import (
    IntegrityCheckFailedError as IntegrityCheckFailedError,
)
from .integrity import (
    IntegrityContext as IntegrityContext,
)
from .integrity import (
    LedgerInvariantError as LedgerInvariantError,
)
from .integrity import (
    PersistenceIntegrityError as PersistenceIntegrityError,
)
from .integrity import (
    SyntaxIntegrityError as SyntaxIntegrityError,
)
from .integrity import (
    WriteConflictError as WriteConflictError,
)
from .introspection.iso import get_currency_decimal_digits as get_currency_decimal_digits

# Message introspection (no Babel dependency)
from .introspection.message import (
    MessageVariableValidationResult as MessageVariableValidationResult,
)
from .introspection.message import validate_message_variables as validate_message_variables

# Localization and runtime (requires Babel)
from .localization import FallbackInfo as FallbackInfo
from .localization import FluentLocalization as FluentLocalization
from .localization import LoadSummary as LoadSummary
from .localization import LocalizationBootConfig as LocalizationBootConfig
from .localization import LocalizationCacheStats as LocalizationCacheStats
from .localization import PathResourceLoader as PathResourceLoader
from .localization import ResourceLoader as ResourceLoader
from .localization import ResourceLoadResult as ResourceLoadResult
from .localization.types import LocaleCode as LocaleCode
from .runtime import AsyncFluentBundle as AsyncFluentBundle
from .runtime import FluentBundle as FluentBundle
from .runtime import FluentNumber as FluentNumber
from .runtime import fluent_function as fluent_function
from .runtime import make_fluent_number as make_fluent_number
from .runtime.cache_config import CacheConfig as CacheConfig
from .runtime.interpreter_pool import InterpreterPool as InterpreterPool
from .runtime.value_types import FluentValue as FluentValue

# Syntax API (no Babel required)
from .syntax import parse as parse_ftl
from .syntax import parse_stream as parse_stream_ftl
from .syntax import serialize as serialize_ftl

# Validation API
from .validation import validate_resource as validate_resource

# Cache management
def clear_module_caches(components: frozenset[str] | None = ...) -> None: ...

# Version and specification information
__version__: str
__fluent_spec_version__: str
__spec_url__: str
__recommended_encoding__: str

# Explicit __all__ for mypy to recognize re-exports
# ruff: noqa: RUF022 - __all__ organized by category for readability, not alphabetically
__all__: list[str] = [
    # Bundle and Localization (Babel-optional; absent in parser-only installs)
    "AsyncFluentBundle",
    "CacheConfig",
    "FallbackInfo",
    "FluentBundle",
    "FluentNumber",
    "FluentLocalization",
    "FluentValue",
    "InterpreterPool",
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
    "LedgerInvariantError",
    "PersistenceIntegrityError",
    "SyntaxIntegrityError",
    "WriteConflictError",
    # Locale utilities (no Babel dependency)
    "LocaleCode",
    "get_system_locale",
    "normalize_locale",
    # Boundary validators (no Babel dependency)
    "coerce_tuple",
    "require_int",
    "require_locale_code",
    "require_non_empty_str",
    "require_non_negative_int",
    "require_positive_int",
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
    # Parsing return type (no Babel dependency)
    "ParseResult",
    # Message introspection (no Babel dependency)
    "MessageVariableValidationResult",
    "validate_message_variables",
    # ISO data utilities (require Babel)
    "get_cldr_version",
    "get_currency_decimal_digits",
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
