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
    loading, types, CacheAuditLogEntry: Zero external dependencies; always importable.
    orchestrator and boot require Babel (via FluentBundle).
    On parser-only installs the Babel-dependent names are absent from normal
    feature probing; direct access raises a missing-symbol error with runtime
    install guidance.

Python 3.13+.
"""

# ruff: noqa: RUF022 - __all__ organized by category for readability

from typing import TYPE_CHECKING

from ftllexengine._optional_exports import (
    LOCALIZATION_BABEL_OPTIONAL_ATTRS as _BABEL_OPTIONAL_ATTRS,
)
from ftllexengine._optional_exports import (
    load_localization_babel_optional_exports,
    raise_missing_babel_symbol,
)
from ftllexengine.core.babel_compat import is_babel_available
from ftllexengine.core.semantic_types import FTLSource, LocaleCode, MessageId, ResourceId
from ftllexengine.enums import LoadStatus
from ftllexengine.localization.loading import (
    FallbackInfo,
    LoadSummary,
    PathResourceLoader,
    ResourceLoader,
    ResourceLoadResult,
)
from ftllexengine.runtime.cache import CacheAuditLogEntry

if TYPE_CHECKING:
    from ftllexengine.localization.boot import LocalizationBootConfig
    from ftllexengine.localization.orchestrator import (
        FluentLocalization,
        LocalizationCacheStats,
    )

_BABEL_AVAILABLE = is_babel_available()

if _BABEL_AVAILABLE:
    globals().update(load_localization_babel_optional_exports())


def __getattr__(name: str) -> object:
    """Raise a targeted missing-symbol error for Babel-backed localization symbols."""
    return raise_missing_babel_symbol(
        module_name=__name__,
        name=name,
        optional_attrs=_BABEL_OPTIONAL_ATTRS,
        parser_only_hint=(
            "Parser-only usage still supports ResourceLoader, PathResourceLoader, "
            "FallbackInfo, ResourceLoadResult, LoadSummary, and CacheAuditLogEntry."
        ),
    )


__all__ = [
    "CacheAuditLogEntry",
    "FallbackInfo",
    "FTLSource",
    "FluentLocalization",
    "LoadStatus",
    "LoadSummary",
    "LocaleCode",
    "LocalizationBootConfig",
    "LocalizationCacheStats",
    "MessageId",
    "PathResourceLoader",
    "ResourceId",
    "ResourceLoadResult",
    "ResourceLoader",
]

if not _BABEL_AVAILABLE:
    __all__ = [name for name in __all__ if name not in _BABEL_OPTIONAL_ATTRS]
