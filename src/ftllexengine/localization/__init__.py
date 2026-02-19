"""Multi-locale localization package for FluentLocalization.

Provides the full localization stack: type aliases, resource loading
infrastructure, and the multi-locale orchestrator.

Submodules:
    types      - PEP 695 type aliases (MessageId, LocaleCode, ResourceId, FTLSource)
    loading    - ResourceLoader protocol, PathResourceLoader, FallbackInfo,
                 ResourceLoadResult, LoadSummary
    orchestrator - FluentLocalization (multi-locale orchestration)

Python 3.13+. Zero external dependencies.
"""

# ruff: noqa: RUF022 - __all__ organized by category for readability

from ftllexengine.enums import LoadStatus
from ftllexengine.localization.loading import (
    FallbackInfo,
    LoadSummary,
    PathResourceLoader,
    ResourceLoader,
    ResourceLoadResult,
)
from ftllexengine.localization.orchestrator import FluentLocalization
from ftllexengine.localization.types import FTLSource, LocaleCode, MessageId, ResourceId

__all__ = [
    # Main orchestrator
    "FluentLocalization",
    # Loader protocol and implementations
    "ResourceLoader",
    "PathResourceLoader",
    # Load tracking (eager loading diagnostics)
    "LoadStatus",
    "LoadSummary",
    "ResourceLoadResult",
    # Fallback observability
    "FallbackInfo",
    # Type aliases for user code type annotations
    "FTLSource",
    "LocaleCode",
    "MessageId",
    "ResourceId",
]
