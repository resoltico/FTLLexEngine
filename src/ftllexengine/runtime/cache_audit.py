"""Audit helpers for IntegrityCache."""

from __future__ import annotations

import hashlib
import time
from typing import TYPE_CHECKING

from .cache_types import IntegrityCacheEntry, WriteLogEntry, _CacheKey

if TYPE_CHECKING:
    from .cache_protocols import CacheStateProtocol


class _CacheAuditMixin:
    """Audit-log behavior for IntegrityCache."""

    def get_audit_log(self: CacheStateProtocol) -> tuple[WriteLogEntry, ...]:
        """Get audit log entries."""
        with self._lock:
            if self._audit_log is None:
                return ()
            return tuple(self._audit_log)

    def _audit(
        self: CacheStateProtocol,
        operation: str,
        key: _CacheKey,
        entry: IntegrityCacheEntry | None,
    ) -> None:
        """Record audit log entry (internal, assumes lock held)."""
        if self._audit_log is None:
            return

        key_hash = hashlib.blake2b(
            str(key).encode("utf-8", errors="surrogatepass"),
            digest_size=8,
        ).hexdigest()

        log_entry = WriteLogEntry(
            operation=operation,
            key_hash=key_hash,
            timestamp=time.monotonic(),
            sequence=entry.sequence if entry is not None else 0,
            checksum_hex=entry.checksum.hex() if entry is not None else "",
            wall_time_unix=time.time(),
        )
        self._audit_log.append(log_entry)
