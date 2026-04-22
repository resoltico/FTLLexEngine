"""Query and cache-reporting helpers for FluentLocalization."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Iterator

    from ftllexengine.core.semantic_types import FTLSource, LocaleCode, MessageId
    from ftllexengine.diagnostics import ValidationResult
    from ftllexengine.introspection import MessageIntrospection
    from ftllexengine.localization.orchestrator import LocalizationCacheStats
    from ftllexengine.localization.orchestrator_protocols import LocalizationStateProtocol
    from ftllexengine.runtime.bundle import FluentBundle
    from ftllexengine.runtime.cache import CacheAuditLogEntry
    from ftllexengine.syntax import Message, Term


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
            total_size = 0
            total_maxsize = 0
            total_hits = 0
            total_misses = 0
            total_unhashable = 0
            total_oversize = 0
            total_error_bloat = 0
            total_combined_weight = 0
            total_corruption = 0
            total_idempotent = 0
            total_write_once_conflicts = 0
            total_sequence = 0
            total_audit_entries = 0
            first_write_once = False
            first_strict = False
            first_audit_enabled = False
            first_max_entry_weight = 0
            first_max_errors = 0
            is_first = True

            for bundle in self._bundles.values():
                stats = bundle.get_cache_stats()
                if stats is None:
                    continue

                total_size += stats["size"]
                total_maxsize += stats["maxsize"]
                total_hits += stats["hits"]
                total_misses += stats["misses"]
                total_unhashable += stats["unhashable_skips"]
                total_oversize += stats["oversize_skips"]
                total_error_bloat += stats["error_bloat_skips"]
                total_combined_weight += stats["combined_weight_skips"]
                total_corruption += stats["corruption_detected"]
                total_idempotent += stats["idempotent_writes"]
                total_write_once_conflicts += stats["write_once_conflicts"]
                total_sequence += stats["sequence"]
                total_audit_entries += stats["audit_entries"]
                if is_first:
                    first_write_once = stats["write_once"]
                    first_strict = stats["strict"]
                    first_audit_enabled = stats["audit_enabled"]
                    first_max_entry_weight = stats["max_entry_weight"]
                    first_max_errors = stats["max_errors_per_entry"]
                    is_first = False

            total_requests = total_hits + total_misses
            hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0.0

            return cast(
                "LocalizationCacheStats",
                {
                "size": total_size,
                "maxsize": total_maxsize,
                "max_entry_weight": first_max_entry_weight,
                "max_errors_per_entry": first_max_errors,
                "hits": total_hits,
                "misses": total_misses,
                "hit_rate": round(hit_rate, 2),
                "unhashable_skips": total_unhashable,
                "oversize_skips": total_oversize,
                "error_bloat_skips": total_error_bloat,
                "combined_weight_skips": total_combined_weight,
                "corruption_detected": total_corruption,
                "idempotent_writes": total_idempotent,
                "write_once_conflicts": total_write_once_conflicts,
                "sequence": total_sequence,
                "write_once": first_write_once,
                "strict": first_strict,
                "audit_enabled": first_audit_enabled,
                "audit_entries": total_audit_entries,
                "bundle_count": len(self._bundles),
                },
            )

    def get_cache_audit_log(
        self: LocalizationStateProtocol,
    ) -> dict[LocaleCode, tuple[CacheAuditLogEntry, ...]] | None:
        """Return per-locale audit logs for initialized bundles."""
        if self._cache_config is None:
            return None

        with self._lock.read():
            audit_logs: dict[LocaleCode, tuple[CacheAuditLogEntry, ...]] = {}
            for locale in self._locales:
                bundle = self._bundles.get(locale)
                if bundle is None:
                    continue

                audit_log = bundle.get_cache_audit_log()
                if audit_log is not None:
                    audit_logs[locale] = audit_log

            return audit_logs

    def get_bundles(self: LocalizationStateProtocol) -> Iterator[FluentBundle]:
        """Yield bundles in fallback order, creating them lazily as needed."""
        yield from (self._get_or_create_bundle(locale) for locale in self._locales)
