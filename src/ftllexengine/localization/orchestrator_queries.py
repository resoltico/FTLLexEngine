"""Query and cache-reporting helpers for FluentLocalization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ftllexengine.localization.cache_stats import LocalizationCacheStats

if TYPE_CHECKING:
    from collections.abc import Iterator

    from ftllexengine.core.semantic_types import FTLSource, LocaleCode, MessageId
    from ftllexengine.diagnostics import ValidationResult
    from ftllexengine.introspection import MessageIntrospection
    from ftllexengine.localization.orchestrator_protocols import LocalizationStateProtocol
    from ftllexengine.runtime.bundle import FluentBundle
    from ftllexengine.runtime.cache import CacheDebugLogEntry, CacheStats
    from ftllexengine.syntax import Message, Term


@dataclass(slots=True)
class _LocalizationCacheAccumulator:
    """Aggregate cache stats across initialized locale bundles.

    Premise:
        Multi-locale cache reporting is one public contract even though each
        locale bundle owns its own cache.

    Reason:
        Keeping the accumulation state in one focused helper avoids a long
        monolithic query method and makes the aggregation rules explicit.
    """

    total_size: int = 0
    total_maxsize: int = 0
    total_hits: int = 0
    total_misses: int = 0
    total_unhashable: int = 0
    total_oversize: int = 0
    total_error_bloat: int = 0
    total_combined_payload: int = 0
    total_corruption: int = 0
    total_integrity_events: int = 0
    total_idempotent: int = 0
    total_write_once_conflicts: int = 0
    total_uncacheable_function_skips: int = 0
    total_sequence: int = 0
    total_debug_log_entries: int = 0
    max_cache_generation: int = 0
    first_write_once: bool = False
    first_debug_log_enabled: bool = False
    first_max_entry_payload_bytes: int = 0
    first_max_errors: int = 0
    saw_stats: bool = False

    def include(self, stats: CacheStats) -> None:
        """Merge one bundle cache snapshot into the aggregate."""
        self.total_size += stats.size
        self.total_maxsize += stats.maxsize
        self.total_hits += stats.hits
        self.total_misses += stats.misses
        self.total_unhashable += stats.unhashable_skips
        self.total_oversize += stats.oversize_skips
        self.total_error_bloat += stats.error_bloat_skips
        self.total_combined_payload += stats.combined_payload_skips
        self.total_corruption += stats.corruption_detected
        self.total_integrity_events += stats.integrity_events_emitted
        self.total_idempotent += stats.idempotent_writes
        self.total_write_once_conflicts += stats.write_once_conflicts
        self.total_uncacheable_function_skips += stats.uncacheable_function_skips
        self.total_sequence += stats.sequence
        self.total_debug_log_entries += stats.debug_log_entries
        self.max_cache_generation = max(self.max_cache_generation, stats.cache_generation)
        if not self.saw_stats:
            self.first_write_once = stats.write_once
            self.first_debug_log_enabled = stats.debug_log_enabled
            self.first_max_entry_payload_bytes = stats.max_entry_payload_bytes
            self.first_max_errors = stats.max_errors_per_entry
            self.saw_stats = True

    def build(self, *, bundle_count: int) -> LocalizationCacheStats:
        """Materialize the public aggregate cache snapshot."""
        total_requests = self.total_hits + self.total_misses
        hit_rate = (
            self.total_hits / total_requests * 100
            if total_requests > 0
            else 0.0
        )
        return LocalizationCacheStats(
            size=self.total_size,
            maxsize=self.total_maxsize,
            max_entry_payload_bytes=self.first_max_entry_payload_bytes,
            max_errors_per_entry=self.first_max_errors,
            hits=self.total_hits,
            misses=self.total_misses,
            hit_rate=round(hit_rate, 2),
            unhashable_skips=self.total_unhashable,
            oversize_skips=self.total_oversize,
            error_bloat_skips=self.total_error_bloat,
            combined_payload_skips=self.total_combined_payload,
            corruption_detected=self.total_corruption,
            integrity_events_emitted=self.total_integrity_events,
            idempotent_writes=self.total_idempotent,
            write_once_conflicts=self.total_write_once_conflicts,
            uncacheable_function_skips=self.total_uncacheable_function_skips,
            sequence=self.total_sequence,
            cache_generation=self.max_cache_generation,
            write_once=self.first_write_once,
            debug_log_enabled=self.first_debug_log_enabled,
            debug_log_entries=self.total_debug_log_entries,
            bundle_count=bundle_count,
        )


class _LocalizationQueryMixin:
    """Read-only query behavior for FluentLocalization."""

    def introspect_message(
        self: LocalizationStateProtocol,
        message_id: MessageId,
    ) -> MessageIntrospection | None:
        """Return introspection for the first locale containing ``message_id``."""
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            if bundle.has_message(message_id):
                return bundle.introspect_message(message_id)
        return None

    def has_attribute(
        self: LocalizationStateProtocol,
        message_id: MessageId,
        attribute: str,
    ) -> bool:
        """Return whether any locale exposes ``attribute`` for ``message_id``."""
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            if bundle.has_attribute(message_id, attribute):
                return True
        return False

    def get_message_ids(self: LocalizationStateProtocol) -> list[str]:
        """Return the union of message IDs across the fallback chain."""
        seen: set[str] = set()
        result: list[str] = []
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            for msg_id in bundle.get_message_ids():
                if msg_id not in seen:
                    seen.add(msg_id)
                    result.append(msg_id)
        return result

    def get_message_variables(
        self: LocalizationStateProtocol,
        message_id: MessageId,
    ) -> frozenset[str]:
        """Return variables from the first locale that contains ``message_id``."""
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            if bundle.has_message(message_id):
                return bundle.get_message_variables(message_id)
        msg = f"Message '{message_id}' not found in any locale"
        raise KeyError(msg)

    def get_all_message_variables(
        self: LocalizationStateProtocol,
    ) -> dict[str, frozenset[str]]:
        """Return variables for all messages across the fallback chain."""
        result: dict[str, frozenset[str]] = {}
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            for msg_id, variables in bundle.get_all_message_variables().items():
                if msg_id not in result:
                    result[msg_id] = variables
        return result

    def introspect_term(
        self: LocalizationStateProtocol,
        term_id: str,
    ) -> MessageIntrospection | None:
        """Return term introspection from the first locale that contains it."""
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            try:
                return bundle.introspect_term(term_id)
            except KeyError:
                continue
        return None

    def get_message(
        self: LocalizationStateProtocol, message_id: MessageId
    ) -> Message | None:
        """Return the first message AST node found across the fallback chain."""
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            message = bundle.get_message(message_id)
            if message is not None:
                return message
        return None

    def get_term(self: LocalizationStateProtocol, term_id: str) -> Term | None:
        """Return the first term AST node found across the fallback chain."""
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            term = bundle.get_term(term_id)
            if term is not None:
                return term
        return None

    def get_babel_locale(self: LocalizationStateProtocol) -> str:
        """Return the primary bundle's Babel locale identifier."""
        primary_locale = self._locales[0]
        bundle = self._get_or_create_bundle(primary_locale)
        return bundle.get_babel_locale()

    def validate_resource(
        self: LocalizationStateProtocol, ftl_source: FTLSource
    ) -> ValidationResult:
        """Validate FTL source using the primary locale bundle."""
        primary_locale = self._locales[0]
        bundle = self._get_or_create_bundle(primary_locale)
        return bundle.validate_resource(ftl_source)

    def clear_cache(self: LocalizationStateProtocol) -> None:
        """Clear caches on all initialized bundles."""
        with self._lock.write():
            for bundle in self._bundles.values():
                bundle.clear_cache()

    def get_cache_stats(
        self: LocalizationStateProtocol,
    ) -> LocalizationCacheStats | None:
        """Aggregate cache statistics across initialized bundles."""
        if self._cache_config is None:
            return None

        with self._lock.read():
            accumulator = _LocalizationCacheAccumulator()

            for bundle in self._bundles.values():
                stats = bundle.get_cache_stats()
                if stats is None:
                    continue
                accumulator.include(stats)

            return accumulator.build(bundle_count=len(self._bundles))

    def get_cache_debug_log(
        self: LocalizationStateProtocol,
    ) -> dict[LocaleCode, tuple[CacheDebugLogEntry, ...]] | None:
        """Return per-locale debug logs for initialized bundles."""
        if self._cache_config is None:
            return None

        with self._lock.read():
            debug_logs: dict[LocaleCode, tuple[CacheDebugLogEntry, ...]] = {}
            for locale in self._locales:
                bundle = self._bundles.get(locale)
                if bundle is None:
                    continue

                debug_log = bundle.get_cache_debug_log()
                if debug_log is not None:
                    debug_logs[locale] = debug_log

            return debug_logs

    def get_bundles(self: LocalizationStateProtocol) -> Iterator[FluentBundle]:
        """Yield bundles in fallback order, creating them lazily as needed."""
        yield from (self._get_or_create_bundle(locale) for locale in self._locales)
