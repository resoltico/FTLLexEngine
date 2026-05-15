"""Immutable cache statistics contracts for multi-locale localization."""

from __future__ import annotations

from dataclasses import dataclass

from ftllexengine.runtime.cache import CacheStats

__all__ = ["LocalizationCacheStats"]


@dataclass(frozen=True, slots=True)
class LocalizationCacheStats(CacheStats):
    """Aggregate cache statistics across all bundles in a ``FluentLocalization``.

    Premise:
        Multi-locale cache reporting is a separate public contract from the
        orchestrator implementation that happens to produce it.

    Reason:
        Giving this snapshot its own module keeps cache-reporting imports
        acyclic and makes the type the clear owner of its own semantics.
    """

    bundle_count: int
