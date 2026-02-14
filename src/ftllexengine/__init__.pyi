"""Type stubs for ftllexengine package.

This stub file declares types for lazy-loaded attributes and re-exported symbols.
Mypy cannot infer types from __getattr__, so explicit declarations are required.
"""

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
    SyntaxIntegrityError as SyntaxIntegrityError,
)
from .integrity import (
    WriteConflictError as WriteConflictError,
)

# Localization and runtime (requires Babel)
from .localization import FluentLocalization as FluentLocalization
from .runtime import FluentBundle as FluentBundle
from .runtime.function_bridge import fluent_function as fluent_function
from .runtime.value_types import FluentValue as FluentValue

# Syntax API (no Babel required)
from .syntax import parse as parse_ftl
from .syntax import serialize as serialize_ftl

# Validation API
from .validation import validate_resource as validate_resource

# Cache management
def clear_all_caches() -> None: ...

# Version and specification information
__version__: str
__fluent_spec_version__: str
__spec_url__: str
__recommended_encoding__: str

# Explicit __all__ for mypy to recognize re-exports
# ruff: noqa: RUF022 - __all__ organized by category for readability, not alphabetically
__all__: list[str] = [
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
