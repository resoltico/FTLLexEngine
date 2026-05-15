"""Cache configuration for ``FluentBundle``.

Provides one frozen dataclass that encapsulates all cache-related parameters.
The cache contract is intentionally separate from formatting strictness: cache
integrity failures are system failures regardless of whether callers choose
strict or fallback-oriented formatting behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ftllexengine.constants import (
    DEFAULT_CACHE_SIZE,
    DEFAULT_MAX_ENTRY_PAYLOAD_BYTES,
)
from ftllexengine.core.validators import require_bool, require_positive_int

if TYPE_CHECKING:
    from .cache_events import IntegrityEventSink

__all__ = ["CacheConfig"]


def _validate_optional_fingerprint_key(value: object) -> bytes | None:
    """Validate the optional keyed-fingerprint secret.

    Premise:
        Debug fingerprints are privacy controls, not cosmetic formatting.

    Reason:
        An empty string, text value, or short byte sequence weakens the contract
        silently. The configuration boundary therefore validates the shape up
        front instead of letting one cache instance limp along with weak input.
    """
    if value is None:
        return None
    if not isinstance(value, bytes):
        msg = f"debug_fingerprint_key must be bytes or None, got {type(value).__name__}"
        raise TypeError(msg)
    if len(value) < 16:
        msg = "debug_fingerprint_key must contain at least 16 bytes"
        raise ValueError(msg)
    return value


def _validate_optional_integrity_event_sink(value: object) -> None:
    """Validate the optional structured integrity-event sink."""
    if value is None:
        return
    record = getattr(value, "record", None)
    if not callable(record):
        msg = (
            "integrity_event_sink must implement a callable record(event) method, "
            f"got {type(value).__name__}"
        )
        raise TypeError(msg)


@dataclass(frozen=True, slots=True)
class CacheConfig:
    """Immutable configuration for ``FluentBundle`` format caching.

    All fields have sensible defaults; constructing ``CacheConfig()`` with no
    arguments produces a usable cache configuration. Pass an instance to
    ``FluentBundle(cache=CacheConfig(...))`` to enable caching.

    Attributes:
        size: Maximum cache entries (default: 1000).
        write_once: Reject updates to existing cache keys (default: False).
            Enables data-race detection in concurrent environments.
        enable_debug_log: Maintain a bounded recent-operation ring buffer
            (default: False). This is a debug surface, not a compliance ledger.
        max_debug_entries: Maximum debug-log entries before oldest eviction
            (default: 10000). Only relevant when ``enable_debug_log=True``.
        max_entry_payload_bytes: Maximum retained UTF-8 payload bytes for one
            cached result (default: 10000). Results exceeding this are computed
            but not cached.
        max_errors_per_entry: Maximum errors per cache entry (default: 50).
            Prevents payload blow-up from pathological failure sets.
        integrity_event_sink: Optional structured sink for critical integrity
            events such as corruption or write conflicts.
        debug_fingerprint_key: Optional keyed-fingerprint secret used for debug
            log key fingerprints. When omitted, each cache instance generates a
            private process-local secret automatically.
    """

    size: int = DEFAULT_CACHE_SIZE
    write_once: bool = False
    enable_debug_log: bool = False
    max_debug_entries: int = 10000
    max_entry_payload_bytes: int = DEFAULT_MAX_ENTRY_PAYLOAD_BYTES
    max_errors_per_entry: int = 50
    integrity_event_sink: IntegrityEventSink | None = None
    debug_fingerprint_key: bytes | None = None

    def __post_init__(self) -> None:
        """Validate configuration values at construction time.

        Raises:
            TypeError: If any field receives the wrong type.
            ValueError: If any positive integer field is zero or negative, or
                if ``debug_fingerprint_key`` is too short.
        """
        require_positive_int(self.size, "size")
        require_bool(self.write_once, "write_once")
        require_bool(self.enable_debug_log, "enable_debug_log")
        require_positive_int(self.max_debug_entries, "max_debug_entries")
        require_positive_int(self.max_entry_payload_bytes, "max_entry_payload_bytes")
        require_positive_int(self.max_errors_per_entry, "max_errors_per_entry")
        _validate_optional_integrity_event_sink(self.integrity_event_sink)
        _validate_optional_fingerprint_key(self.debug_fingerprint_key)
