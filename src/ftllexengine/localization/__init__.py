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

from typing import TYPE_CHECKING

from ftllexengine._optional_exports import (
    babel_optional_attr_set,
    babel_optional_attr_tuple,
    load_babel_optional_export,
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
    from ftllexengine.localization.boot import (
        LocalizationBootConfig as LocalizationBootConfig,
    )
    from ftllexengine.localization.orchestrator import (
        FluentLocalization as FluentLocalization,
    )
    from ftllexengine.localization.orchestrator import (
        LocalizationCacheStats as LocalizationCacheStats,
    )

_BABEL_AVAILABLE = is_babel_available()
_BABEL_OPTIONAL_ATTRS = babel_optional_attr_set(__name__)
_BABEL_OPTIONAL_NAMES = babel_optional_attr_tuple(__name__)


def __getattr__(name: str) -> object:
    """Raise a targeted missing-symbol error for Babel-backed localization symbols."""
    if _BABEL_AVAILABLE and name in _BABEL_OPTIONAL_ATTRS:
        value = load_babel_optional_export(__name__, name)
        globals()[name] = value
        return value
    return raise_missing_babel_symbol(
        module_name=__name__,
        name=name,
        optional_attrs=_BABEL_OPTIONAL_ATTRS,
        parser_only_hint=(
            "Parser-only usage still supports ResourceLoader, PathResourceLoader, "
            "FallbackInfo, ResourceLoadResult, LoadSummary, and CacheAuditLogEntry."
        ),
    )


# ruff: noqa: RUF022 - grouped localization exports mirror the reader-facing facade
__all__: list[str] = [
    "CacheAuditLogEntry",
    "FallbackInfo",
    "FTLSource",
    "LoadStatus",
    "LoadSummary",
    "LocaleCode",
    "MessageId",
    "PathResourceLoader",
    "ResourceId",
    "ResourceLoadResult",
    "ResourceLoader",
]
__all__[6:6] = list(_BABEL_OPTIONAL_NAMES)

if not _BABEL_AVAILABLE:
    __all__ = [name for name in __all__ if name not in _BABEL_OPTIONAL_ATTRS]
