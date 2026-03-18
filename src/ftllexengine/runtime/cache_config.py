"""Cache configuration for FluentBundle.

Provides a single frozen dataclass that encapsulates all cache-related
parameters. Replaces seven individual constructor parameters with one
typed object, reducing API surface and eliminating parameter duplication
between FluentBundle and IntegrityCache.

Python 3.14+. Zero external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass

from ftllexengine.constants import DEFAULT_CACHE_SIZE, DEFAULT_MAX_ENTRY_WEIGHT
from ftllexengine.core.validators import require_positive_int

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
        integrity_strict: If True, raise CacheCorruptionError on checksum
            mismatch and WriteConflictError on write-once violations
            (default: True). If False, silently evict corrupted entries
            and ignore write conflicts. Acts as an upper bound: when
            FluentBundle ``strict=False``, the cache is always lenient
            regardless of this setting (AND-gate with bundle strict mode).
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
        >>> assert bundle.cache_config is not None
        >>> bundle.cache_config.size
        500

    Example - Financial application:
        >>> config = CacheConfig(
        ...     write_once=True,
        ...     integrity_strict=True,
        ...     enable_audit=True,
        ...     max_audit_entries=50000,
        ... )
        >>> bundle = FluentBundle("en", cache=config, strict=True)
    """

    size: int = DEFAULT_CACHE_SIZE
    write_once: bool = False
    integrity_strict: bool = True
    enable_audit: bool = False
    max_audit_entries: int = 10000
    max_entry_weight: int = DEFAULT_MAX_ENTRY_WEIGHT
    max_errors_per_entry: int = 50

    def __post_init__(self) -> None:
        """Validate configuration values at construction time.

        Raises:
            TypeError: If any integer field receives a non-int value.
            ValueError: If size, max_entry_weight, max_errors_per_entry,
                or max_audit_entries is zero or negative.
        """
        require_positive_int(self.size, "size")
        require_positive_int(self.max_entry_weight, "max_entry_weight")
        require_positive_int(self.max_errors_per_entry, "max_errors_per_entry")
        require_positive_int(self.max_audit_entries, "max_audit_entries")
