"""Property-based tests for FluentLocalization orchestration layer.

Covers multi-locale orchestration, data type invariants, fallback semantics,
and API surface completeness using Hypothesis strategies from
tests/strategies/localization.

Fuzz module: all @given tests emit hypothesis.event() for HypoFuzz guidance.

Python 3.13+.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from ftllexengine.core.locale_utils import normalize_locale
from ftllexengine.localization import (
    FluentLocalization,
    LoadStatus,
    LoadSummary,
    PathResourceLoader,
    ResourceLoadResult,
)
from ftllexengine.runtime.cache_config import CacheConfig
from ftllexengine.syntax.ast import Junk, Span
from tests.strategies.ftl import ftl_simple_messages
from tests.strategies.localization import (
    DictResourceLoader,
    FailingResourceLoader,
    ftl_messages_with_attributes,
    ftl_messages_with_terms,
    ftl_resource_sets,
    locale_chains,
    message_ids,
    resource_loaders,
)

pytestmark = pytest.mark.fuzz

__all__ = [
    "CacheConfig",
    "Decimal",
    "DictResourceLoader",
    "FailingResourceLoader",
    "FluentLocalization",
    "HealthCheck",
    "Junk",
    "LoadStatus",
    "LoadSummary",
    "Path",
    "PathResourceLoader",
    "ResourceLoadResult",
    "Span",
    "event",
    "ftl_messages_with_attributes",
    "ftl_messages_with_terms",
    "ftl_resource_sets",
    "ftl_simple_messages",
    "given",
    "locale_chains",
    "message_ids",
    "normalize_locale",
    "pytest",
    "resource_loaders",
    "settings",
    "st",
]
