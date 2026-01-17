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

from ftllexengine.constants import DEFAULT_MAX_ENTRY_SIZE, MAX_DEPTH
from ftllexengine.diagnostics import FluentError
from ftllexengine.runtime.function_bridge import FluentNumber, FluentValue

__all__ = ["FormatCache", "HashableValue"]

# Realistic estimate of memory weight per FluentError object.
# Each error carries Diagnostic objects with traceback information, message context,
# and error templates. 200 bytes is a realistic estimate that accounts for:
# - Error message strings (~50-100 bytes)
# - Diagnostic traceback data (~50-100 bytes)
# - Object overhead and references (~50 bytes)
# Previous value (1000) made max_errors_per_entry=50 unreachable due to weight
# calculation rejecting entries >10 errors. Reduced to 200 to align parameter
# interaction: 50 errors x 200 bytes = 10,000 bytes (matches DEFAULT_MAX_ENTRY_SIZE).
_ERROR_WEIGHT_BYTES: int = 200

# Maximum number of errors allowed per cache entry.
# Prevents memory exhaustion from pathological cases where resolution produces
# many errors (e.g., cyclic references, deeply nested validation failures).
# 50 errors at 200 bytes each = 10,000 bytes (DEFAULT_MAX_ENTRY_SIZE limit).
_DEFAULT_MAX_ERRORS_PER_ENTRY: int = 50

# Type alias for hashable values produced by _make_hashable().
# Recursive definition: primitives plus tuple/frozenset of self.
# Note: Decimal, datetime, date, FluentNumber are hashable and preserved unchanged.
type HashableValue = (
    str
    | int
    | float
    | bool
    | Decimal
    | datetime
    | date
    | FluentNumber
    | None
    | tuple["HashableValue", ...]
    | frozenset["HashableValue"]
)

# Internal type alias for cache keys (prefixed with _ per naming convention)
# 5-tuple: (message_id, args_tuple, attribute, locale_code, use_isolating)
type _CacheKey = tuple[str, tuple[tuple[str, HashableValue], ...], str | None, str, bool]

# Internal type alias for cache values (prefixed with _ per naming convention)
type _CacheValue = tuple[str, tuple[FluentError, ...]]


class FormatCache:
    """Thread-safe LRU cache for format_pattern() results.

    Uses OrderedDict for LRU eviction and RLock for thread safety.
    Transparent to caller - returns None on cache miss.

    Memory Protection:
        The max_entry_weight parameter prevents unbounded memory usage by
        skipping cache storage for results exceeding the weight limit.
        Weight is calculated as: len(formatted_str) + (len(errors) * 200).
        This protects against scenarios where large variable values produce
        very large formatted strings or large error collections (e.g., 10MB
        results cached 1000 times would consume 10GB of memory).

    Attributes:
        maxsize: Maximum number of cache entries
        max_entry_weight: Maximum memory weight for cached results
        hits: Number of cache hits (for metrics)
        misses: Number of cache misses (for metrics)
    """

    __slots__ = (
        "_cache",
        "_error_bloat_skips",
        "_hits",
        "_lock",
        "_max_entry_weight",
        "_max_errors_per_entry",
        "_maxsize",
        "_misses",
        "_oversize_skips",
        "_unhashable_skips",
    )

    def __init__(
        self,
        maxsize: int = 1000,
        max_entry_weight: int = DEFAULT_MAX_ENTRY_SIZE,
        max_errors_per_entry: int = _DEFAULT_MAX_ERRORS_PER_ENTRY,
    ) -> None:
        """Initialize format cache.

        Args:
            maxsize: Maximum number of entries (default: 1000)
            max_entry_weight: Maximum memory weight for cached results (default: 10_000).
                Weight is calculated as: len(formatted_str) + (len(errors) * 200).
                Results exceeding this weight are not cached to prevent memory
                exhaustion from large formatted strings or large error collections.
            max_errors_per_entry: Maximum number of errors per cache entry
                (default: 50). Results with more errors are not cached to
                prevent memory exhaustion from error collections.
        """
        if maxsize <= 0:
            msg = "maxsize must be positive"
            raise ValueError(msg)
        if max_entry_weight <= 0:
            msg = "max_entry_weight must be positive"
            raise ValueError(msg)
        if max_errors_per_entry <= 0:
            msg = "max_errors_per_entry must be positive"
            raise ValueError(msg)

        self._cache: OrderedDict[_CacheKey, _CacheValue] = OrderedDict()
        self._maxsize = maxsize
        self._max_entry_weight = max_entry_weight
        self._max_errors_per_entry = max_errors_per_entry
        self._lock = RLock()  # Reentrant lock for safety
        self._hits = 0
        self._misses = 0
        self._unhashable_skips = 0
        self._oversize_skips = 0
        self._error_bloat_skips = 0

    def get(
        self,
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
        locale_code: str,
        use_isolating: bool,
    ) -> _CacheValue | None:
        """Get cached result if exists.

        Thread-safe. Returns None on cache miss.

        Args:
            message_id: Message identifier
            args: Message arguments (may contain unhashable values like lists)
            attribute: Attribute name
            locale_code: Locale code
            use_isolating: Whether Unicode isolation marks are used

        Returns:
            Cached (result, errors) tuple or None
        """
        key = self._make_key(message_id, args, attribute, locale_code, use_isolating)

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
        use_isolating: bool,
        result: _CacheValue,
    ) -> None:
        """Store result in cache.

        Thread-safe. Evicts LRU entry if cache is full.
        Skips caching for results exceeding max_entry_weight or max_errors_per_entry.

        Args:
            message_id: Message identifier
            args: Message arguments (may contain unhashable values like lists)
            attribute: Attribute name
            locale_code: Locale code
            use_isolating: Whether Unicode isolation marks are used
            result: Format result to cache
        """
        # Check entry weight before caching (result is (formatted_str, errors))
        formatted_str = result[0]
        errors = result[1]

        # Check formatted string size
        if len(formatted_str) > self._max_entry_weight:
            with self._lock:
                self._oversize_skips += 1
            return

        # Check error collection size (memory weight = count * estimated bytes per error)
        if len(errors) > self._max_errors_per_entry:
            with self._lock:
                self._error_bloat_skips += 1
            return

        # Calculate total memory weight (string + error collection)
        # String: measured in characters (Python len())
        # Errors: estimated weight in bytes (conservative: 1KB per error)
        total_weight = len(formatted_str) + (len(errors) * _ERROR_WEIGHT_BYTES)
        if total_weight > self._max_entry_weight:
            with self._lock:
                self._error_bloat_skips += 1
            return

        key = self._make_key(message_id, args, attribute, locale_code, use_isolating)

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
            self._oversize_skips = 0
            self._error_bloat_skips = 0

    def get_stats(self) -> dict[str, int | float]:
        """Get cache statistics.

        Thread-safe. Returns current metrics.

        Returns:
            Dict with keys:
            - size (int): Current number of cached entries
            - maxsize (int): Maximum cache capacity
            - max_entry_weight (int): Maximum memory weight for cached results
            - max_errors_per_entry (int): Maximum errors per cache entry
            - hits (int): Number of cache hits
            - misses (int): Number of cache misses
            - hit_rate (float): Hit rate as percentage (0.0-100.0)
            - unhashable_skips (int): Operations skipped due to unhashable args
            - oversize_skips (int): Operations skipped due to result weight
            - error_bloat_skips (int): Operations skipped due to error collection size
        """
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0

            return {
                "size": len(self._cache),
                "maxsize": self._maxsize,
                "max_entry_weight": self._max_entry_weight,
                "max_errors_per_entry": self._max_errors_per_entry,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 2),
                "unhashable_skips": self._unhashable_skips,
                "oversize_skips": self._oversize_skips,
                "error_bloat_skips": self._error_bloat_skips,
            }

    @staticmethod
    def _make_hashable(  # noqa: PLR0911 - type dispatch requires multiple returns
        value: object, depth: int = MAX_DEPTH
    ) -> HashableValue:
        """Convert potentially unhashable value to hashable equivalent.

        Converts:
            - list -> tuple (recursively)
            - tuple -> tuple with converted elements (recursively)
            - dict -> tuple of sorted key-value tuples (recursively)
            - set -> frozenset (recursively)
            - Known FluentValue types -> unchanged (already hashable)

        Depth Protection:
            Uses explicit depth tracking consistent with codebase pattern
            (parser, resolver, serializer all use MAX_DEPTH=100). Raises
            TypeError when depth is exhausted, which is caught by _make_key
            and results in graceful cache bypass.

        Args:
            value: Value to convert (typically FluentValue or nested collection)
            depth: Remaining recursion depth (default: MAX_DEPTH)

        Returns:
            Hashable equivalent of the value

        Raises:
            TypeError: If depth limit exceeded or value is not a known hashable type
        """
        if depth <= 0:
            msg = "Maximum nesting depth exceeded in cache key conversion"
            raise TypeError(msg)

        match value:
            case list():
                return tuple(FormatCache._make_hashable(v, depth - 1) for v in value)
            case tuple():
                # Tuples may contain unhashable elements (e.g., nested lists)
                # Recursively process to ensure all elements are hashable
                return tuple(FormatCache._make_hashable(v, depth - 1) for v in value)
            case dict():
                return tuple(
                    sorted(
                        (k, FormatCache._make_hashable(v, depth - 1))
                        for k, v in value.items()
                    )
                )
            case set():
                return frozenset(FormatCache._make_hashable(v, depth - 1) for v in value)
            case str() | int() | float() | bool() | None:
                # Primitives are hashable
                return value
            case Decimal() | datetime() | date():
                # These types are hashable and part of FluentValue
                return value
            case FluentNumber():
                # FluentNumber is hashable (wraps numeric value with formatting)
                return value
            case _:
                # Unknown type - let hash() verification in _make_key catch failures
                # This provides runtime safety while avoiding overly restrictive checks
                msg = f"Unknown type in cache key: {type(value).__name__}"
                raise TypeError(msg)

    @staticmethod
    def _make_key(
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
        locale_code: str,
        use_isolating: bool,
    ) -> _CacheKey | None:
        """Create immutable cache key from arguments.

        Converts unhashable types (lists, dicts, sets) to hashable equivalents.

        Performance Optimization:
            Single-pass conversion: iterates args once, converting unhashable values
            (list, dict, set) inline as encountered. This avoids the double iteration
            penalty of checking for unhashables first, then converting.

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
            use_isolating: Whether Unicode isolation marks are used

        Returns:
            Immutable cache key tuple, or None if conversion fails
        """
        # Convert args dict to sorted tuple of tuples
        if args is None:
            args_tuple: tuple[tuple[str, HashableValue], ...] = ()
        else:
            try:
                # Convert all values through _make_hashable for consistent type validation.
                # _make_hashable handles primitives directly and converts collections.
                items: list[tuple[str, HashableValue]] = []
                for k, v in args.items():
                    items.append((k, FormatCache._make_hashable(v)))
                args_tuple = tuple(sorted(items))

                # Verify the result is actually hashable
                hash(args_tuple)
            except (TypeError, RecursionError):
                # Args contain deeply nested or truly unhashable values
                return None

        return (message_id, args_tuple, attribute, locale_code, use_isolating)

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

    @property
    def oversize_skips(self) -> int:
        """Number of operations skipped due to result weight exceeding max_entry_weight.

        Thread-safe.
        """
        with self._lock:
            return self._oversize_skips

    @property
    def max_entry_weight(self) -> int:
        """Maximum memory weight for cached results.

        Weight is calculated as: len(formatted_str) + (len(errors) * 200).
        """
        return self._max_entry_weight

    @property
    def size(self) -> int:
        """Current number of cached entries.

        Thread-safe.
        """
        with self._lock:
            return len(self._cache)
