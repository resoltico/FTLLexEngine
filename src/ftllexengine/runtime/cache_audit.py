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

        self._audit_sequence += 1
        key_hash = hashlib.blake2b(
            str(key).encode("utf-8", errors="surrogatepass"),
            digest_size=8,
        ).hexdigest()

        log_entry = WriteLogEntry(
            operation=operation,
            key_hash=key_hash,
            timestamp=time.monotonic(),
            sequence=self._audit_sequence,
            cache_sequence=entry.sequence if entry is not None else self._sequence,
            checksum_hex=entry.checksum.hex() if entry is not None else "",
            wall_time_unix=time.time(),
        )
        self._audit_log.append(log_entry)
