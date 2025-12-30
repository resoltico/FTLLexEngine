"""Thread-safe LRU cache for message formatting results.

Provides transparent caching of format_pattern() calls with automatic
invalidation on resource/function changes.

Architecture:
    - Thread-safe using threading.RLock (reentrant lock)
    - LRU eviction via OrderedDict
    - Immutable cache keys (tuples of hashable types)
    - Automatic invalidation on bundle mutation
    - Zero overhead when disabled

Cache Key Structure:
    (message_id, args_tuple, attribute, locale_code)
    - message_id: str
    - args_tuple: tuple[tuple[str, Any], ...] (sorted, frozen)
    - attribute: str | None
    - locale_code: str (for multi-bundle scenarios)

Thread Safety:
    All operations protected by RLock. Safe for concurrent reads and writes.

Python 3.13+.
"""

from collections import OrderedDict
from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from threading import RLock
from typing import cast

from ftllexengine.diagnostics import FluentError
from ftllexengine.runtime.function_bridge import FluentValue

__all__ = ["FormatCache", "HashableValue"]

# Type alias for hashable values produced by _make_hashable().
# Recursive definition: primitives plus tuple/frozenset of self.
# Note: Decimal, datetime, date are hashable and preserved unchanged.
type HashableValue = (
    str
    | int
    | float
    | bool
    | Decimal
    | datetime
    | date
    | None
    | tuple["HashableValue", ...]
    | frozenset["HashableValue"]
)

# Internal type alias for cache keys (prefixed with _ per naming convention)
type _CacheKey = tuple[str, tuple[tuple[str, HashableValue], ...], str | None, str]

# Internal type alias for cache values (prefixed with _ per naming convention)
type _CacheValue = tuple[str, tuple[FluentError, ...]]


class FormatCache:
    """Thread-safe LRU cache for format_pattern() results.

    Uses OrderedDict for LRU eviction and RLock for thread safety.
    Transparent to caller - returns None on cache miss.

    Attributes:
        maxsize: Maximum number of cache entries
        hits: Number of cache hits (for metrics)
        misses: Number of cache misses (for metrics)
    """

    __slots__ = ("_cache", "_hits", "_lock", "_maxsize", "_misses", "_unhashable_skips")

    def __init__(self, maxsize: int = 1000) -> None:
        """Initialize format cache.

        Args:
            maxsize: Maximum number of entries (default: 1000)
        """
        if maxsize <= 0:
            msg = "maxsize must be positive"
            raise ValueError(msg)

        self._cache: OrderedDict[_CacheKey, _CacheValue] = OrderedDict()
        self._maxsize = maxsize
        self._lock = RLock()  # Reentrant lock for safety
        self._hits = 0
        self._misses = 0
        self._unhashable_skips = 0

    def get(
        self,
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
        locale_code: str,
    ) -> _CacheValue | None:
        """Get cached result if exists.

        Thread-safe. Returns None on cache miss.

        Args:
            message_id: Message identifier
            args: Message arguments (may contain unhashable values like lists)
            attribute: Attribute name
            locale_code: Locale code

        Returns:
            Cached (result, errors) tuple or None
        """
        key = self._make_key(message_id, args, attribute, locale_code)

        if key is None:
            with self._lock:
                self._unhashable_skips += 1
                self._misses += 1
            return None

        with self._lock:
            if key in self._cache:
                # Move to end (mark as recently used)
                self._cache.move_to_end(key)
                self._hits += 1
                return self._cache[key]

            self._misses += 1
            return None

    def put(
        self,
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
        locale_code: str,
        result: _CacheValue,
    ) -> None:
        """Store result in cache.

        Thread-safe. Evicts LRU entry if cache is full.

        Args:
            message_id: Message identifier
            args: Message arguments (may contain unhashable values like lists)
            attribute: Attribute name
            locale_code: Locale code
            result: Format result to cache
        """
        key = self._make_key(message_id, args, attribute, locale_code)

        if key is None:
            with self._lock:
                self._unhashable_skips += 1
            return

        with self._lock:
            # Update existing or add new
            if key in self._cache:
                # Move to end (mark as recently used)
                self._cache.move_to_end(key)
            # Evict LRU if cache is full
            elif len(self._cache) >= self._maxsize:
                self._cache.popitem(last=False)  # Remove first (oldest)

            self._cache[key] = result

    def clear(self) -> None:
        """Clear all cached entries.

        Thread-safe. Call when bundle is mutated (add_resource, add_function).
        """
        with self._lock:
            self._cache.clear()
            # Reset metrics on clear
            self._hits = 0
            self._misses = 0
            self._unhashable_skips = 0

    def get_stats(self) -> dict[str, int | float]:
        """Get cache statistics.

        Thread-safe. Returns current metrics.

        Returns:
            Dict with keys:
            - size (int): Current number of cached entries
            - maxsize (int): Maximum cache capacity
            - hits (int): Number of cache hits
            - misses (int): Number of cache misses
            - hit_rate (float): Hit rate as percentage (0.0-100.0)
            - unhashable_skips (int): Operations skipped due to unhashable args
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0

            return {
                "size": len(self._cache),
                "maxsize": self._maxsize,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 2),
                "unhashable_skips": self._unhashable_skips,
            }

    @staticmethod
    def _make_hashable(value: object) -> HashableValue:
        """Convert potentially unhashable value to hashable equivalent.

        Converts:
            - list -> tuple (recursively)
            - dict -> tuple of sorted key-value tuples (recursively)
            - set -> frozenset (recursively)
            - Other values -> unchanged (assumed hashable FluentValue)

        Args:
            value: Value to convert (typically FluentValue or nested collection)

        Returns:
            Hashable equivalent of the value
        """
        match value:
            case list():
                return tuple(FormatCache._make_hashable(v) for v in value)
            case dict():
                return tuple(
                    sorted(
                        (k, FormatCache._make_hashable(v))
                        for k, v in value.items()
                    )
                )
            case set():
                return frozenset(FormatCache._make_hashable(v) for v in value)
            case _:
                # FluentValue types are already hashable (str, int, float, etc.)
                # Cast is safe: caller passes FluentValue or nested structures
                return cast(HashableValue, value)

    @staticmethod
    def _make_key(
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
        locale_code: str,
    ) -> _CacheKey | None:
        """Create immutable cache key from arguments.

        Converts unhashable types (lists, dicts, sets) to hashable equivalents.

        Performance Optimization:
            Fast path: If all args are already hashable primitives (the common case),
            skip the expensive _make_hashable() conversion entirely. This reduces
            overhead from O(N) conversions to O(N) type checks, which is faster
            since type checks don't allocate new objects.

            Slow path: Only invoked when args contain lists, dicts, or sets.
            Has O(N log N) complexity due to sorting for consistent key ordering.

            The sorting is REQUIRED for correctness: without it, format_pattern()
            called with args {"a": 1, "b": 2} and {"b": 2, "a": 1} would produce
            different cache keys despite being semantically equivalent.

        Robustness:
            Catches RecursionError for deeply nested structures and TypeError
            for unhashable values. Returns None in both cases to gracefully
            bypass caching without failing the format operation.

        Args:
            message_id: Message identifier
            args: Message arguments (may contain unhashable values)
            attribute: Attribute name
            locale_code: Locale code

        Returns:
            Immutable cache key tuple, or None if conversion fails
        """
        # Convert args dict to sorted tuple of tuples
        if args is None:
            args_tuple: tuple[tuple[str, HashableValue], ...] = ()
        else:
            try:
                # Fast path: check if all values are hashable primitives
                # This avoids creating intermediate conversion objects for the common case
                needs_conversion = any(
                    isinstance(v, (list, dict, set)) for v in args.values()
                )

                if needs_conversion:
                    # Slow path: convert unhashable types to hashable equivalents
                    converted_items: list[tuple[str, HashableValue]] = [
                        (k, FormatCache._make_hashable(v))
                        for k, v in args.items()
                    ]
                    args_tuple = tuple(sorted(converted_items))
                else:
                    # Fast path: values are already hashable, just sort keys
                    args_tuple = tuple(sorted(args.items()))

                # Verify the result is actually hashable
                hash(args_tuple)
            except (TypeError, RecursionError):
                # Args contain deeply nested or truly unhashable values
                return None

        return (message_id, args_tuple, attribute, locale_code)

    def __len__(self) -> int:
        """Get current cache size.

        Thread-safe.

        Returns:
            Number of entries in cache
        """
        with self._lock:
            return len(self._cache)

    @property
    def maxsize(self) -> int:
        """Maximum cache size."""
        return self._maxsize

    @property
    def hits(self) -> int:
        """Number of cache hits.

        Thread-safe.
        """
        with self._lock:
            return self._hits

    @property
    def misses(self) -> int:
        """Number of cache misses.

        Thread-safe.
        """
        with self._lock:
            return self._misses

    @property
    def unhashable_skips(self) -> int:
        """Number of operations skipped due to unhashable args.

        Thread-safe.
        """
        with self._lock:
            return self._unhashable_skips
