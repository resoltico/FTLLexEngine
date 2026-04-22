"""Multi-locale localization package for FluentLocalization.

Provides the full localization stack: type aliases, resource loading
infrastructure, the multi-locale orchestrator, and the boot configuration
API for strict, audited localization initialization.

Submodules:
    types        - PEP 695 type aliases (MessageId, LocaleCode, ResourceId, FTLSource)
    loading      - ResourceLoader protocol, PathResourceLoader, FallbackInfo,
                   ResourceLoadResult, LoadSummary
    orchestrator - FluentLocalization (multi-locale orchestration)
    boot         - LocalizationBootConfig (one-call boot-validated assembly)

Babel Optionality:
    loading, types: Zero external dependencies; always importable.
    orchestrator, boot, CacheAuditLogEntry: Require Babel (via FluentBundle).
    On parser-only installs the Babel-dependent names are absent; accessing
    them raises ImportError via the root ftllexengine.__getattr__ guard.

Python 3.13+.
"""

# ruff: noqa: RUF022 - __all__ organized by category for readability

from ftllexengine.core.semantic_types import FTLSource, LocaleCode, MessageId, ResourceId
from ftllexengine.enums import LoadStatus
from ftllexengine.localization.loading import (
    FallbackInfo,
    LoadSummary,
    PathResourceLoader,
    ResourceLoader,
    ResourceLoadResult,
)

# Babel-optional: orchestrator and boot depend on FluentBundle (runtime → Babel).
# On parser-only installs these imports fail; the names are absent from this
# package's namespace. The root ftllexengine.__getattr__ provides the hint.
try:
    from ftllexengine.localization.boot import (
        LocalizationBootConfig as LocalizationBootConfig,
    )
    from ftllexengine.localization.orchestrator import (
        FluentLocalization as FluentLocalization,
    )
    from ftllexengine.localization.orchestrator import (
        LocalizationCacheStats as LocalizationCacheStats,
    )
    from ftllexengine.runtime.cache import (
        CacheAuditLogEntry as CacheAuditLogEntry,
    )
except ImportError:  # pragma: no cover - parser-only install; Babel-dependent names unavailable
    pass  # pragma: no cover - parser-only install; Babel-dependent names unavailable

__all__ = [
    # Main orchestrator (Babel-optional; absent in parser-only installs)
    "FluentLocalization",
    "LocalizationCacheStats",
    # Boot configuration (Babel-optional; absent in parser-only installs)
    "LocalizationBootConfig",
    # Loader protocol and implementations (no Babel dependency)
    "ResourceLoader",
    "PathResourceLoader",
    # Load tracking (no Babel dependency)
    "LoadStatus",
    "LoadSummary",
    "ResourceLoadResult",
    # Fallback observability (no Babel dependency)
    "FallbackInfo",
    # Type aliases for user code type annotations (no Babel dependency)
    "FTLSource",
    "LocaleCode",
    "MessageId",
    "ResourceId",
    # Public cache audit-log entry type (Babel-optional; absent in parser-only installs)
    "CacheAuditLogEntry",
]
