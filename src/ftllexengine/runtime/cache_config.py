"""Cache configuration for FluentBundle.

Provides a single frozen dataclass that encapsulates all cache-related
parameters. Replaces seven individual constructor parameters with one
typed object, reducing API surface and eliminating parameter duplication
between FluentBundle and IntegrityCache.

Python 3.13+. Zero external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass

from ftllexengine.constants import DEFAULT_CACHE_SIZE, DEFAULT_MAX_ENTRY_SIZE

__all__ = ["CacheConfig"]


@dataclass(frozen=True, slots=True)
class CacheConfig:
    """Immutable configuration for FluentBundle format caching.

    All fields have sensible defaults; constructing ``CacheConfig()`` with
    no arguments produces a usable configuration. Pass an instance to
    ``FluentBundle(cache=CacheConfig(...))`` to enable caching.

    Attributes:
        size: Maximum cache entries (default: 1000).
        write_once: Reject updates to existing cache keys (default: False).
            Enables data-race detection in concurrent environments.
        enable_audit: Maintain audit log of all cache operations (default: False).
        max_audit_entries: Maximum audit log entries before oldest eviction
            (default: 10000). Only relevant when ``enable_audit=True``.
        max_entry_weight: Maximum memory weight for a single cached result
            (default: 10000). Results exceeding this are computed but not cached.
        max_errors_per_entry: Maximum errors per cache entry (default: 50).
            Prevents memory exhaustion from pathological cases.

    Example:
        >>> from ftllexengine import FluentBundle
        >>> from ftllexengine.runtime.cache_config import CacheConfig
        >>> config = CacheConfig(size=500, write_once=True)
        >>> bundle = FluentBundle("en", cache=config)
        >>> bundle.cache_enabled
        True
        >>> bundle.cache_size
        500

    Example - Financial application:
        >>> config = CacheConfig(
        ...     write_once=True,
        ...     enable_audit=True,
        ...     max_audit_entries=50000,
        ... )
        >>> bundle = FluentBundle("en", cache=config, strict=True)
    """

    size: int = DEFAULT_CACHE_SIZE
    write_once: bool = False
    enable_audit: bool = False
    max_audit_entries: int = 10000
    max_entry_weight: int = DEFAULT_MAX_ENTRY_SIZE
    max_errors_per_entry: int = 50
