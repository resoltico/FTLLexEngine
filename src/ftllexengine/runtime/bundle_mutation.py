"""Mutation and cache-management helpers for FluentBundle."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ftllexengine.syntax import Resource
from ftllexengine.validation import validate_resource as _validate_resource_impl

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from ftllexengine.core.value_types import FluentValue
    from ftllexengine.diagnostics import ValidationResult
    from ftllexengine.syntax import Entry, Junk

    from .bundle_protocols import BundleStateProtocol
    from .cache import CacheAuditLogEntry, CacheStats

logger = logging.getLogger("ftllexengine.runtime.bundle")


class _BundleMutationMixin:
    """Resource mutation, validation, and cache helpers for FluentBundle."""

    def add_resource(
        self: BundleStateProtocol,
        source: str,
        /,
        *,
        source_path: str | None = None,
    ) -> tuple[Junk, ...]:
        """Add FTL resource to bundle."""
        raw_source: object = source
        if not isinstance(raw_source, str):
            msg = (
                f"source must be str, not {type(raw_source).__name__}. "
                "Decode bytes to str (e.g., source.decode('utf-8')) before calling add_resource()."
            )
            raise TypeError(msg)

        resource = self._parser.parse(raw_source)
        with self._rwlock.write():
            return self._register_resource(resource, source_path)

    def add_resource_stream(
        self: BundleStateProtocol,
        lines: Iterable[str],
        /,
        *,
        source_path: str | None = None,
    ) -> tuple[Junk, ...]:
        """Add FTL resource to bundle from a line-oriented source stream."""
        collected: list[Entry] = list(self._parser.parse_stream(lines))
        resource = Resource(entries=tuple(collected))

        with self._rwlock.write():
            return self._register_resource(resource, source_path)

    def validate_resource(self: BundleStateProtocol, source: str) -> ValidationResult:
        """Validate FTL resource without adding to bundle."""
        raw_source: object = source
        if not isinstance(raw_source, str):
            msg = (
                f"source must be str, not {type(raw_source).__name__}. "
                "Decode bytes to str (e.g., source.decode('utf-8')) "
                "before calling validate_resource()."
            )
            raise TypeError(msg)

        with self._rwlock.read():
            return _validate_resource_impl(
                raw_source,
                parser=self._parser,
                known_messages=frozenset(self._messages.keys()),
                known_terms=frozenset(self._terms.keys()),
                known_msg_deps=self._msg_deps,
                known_term_deps=self._term_deps,
            )

    def add_function(
        self: BundleStateProtocol,
        name: str,
        func: Callable[..., FluentValue],
    ) -> None:
        """Add custom function to bundle."""
        with self._rwlock.write():
            if not self._owns_registry:
                self._function_registry = self._function_registry.copy()
                self._owns_registry = True
                logger.debug("Registry copied on first add_function")

            self._function_registry.register(func, ftl_name=name)
            logger.debug("Added custom function: %s", name)
            self._resolver = self._create_resolver()

            if self._cache is not None:
                self._cache.clear()
                logger.debug("Cache cleared after add_function")

    def clear_cache(self: BundleStateProtocol) -> None:
        """Clear format cache."""
        with self._rwlock.write():
            if self._cache is not None:
                self._cache.clear()
                logger.debug("Cache manually cleared")

    def get_cache_stats(self: BundleStateProtocol) -> CacheStats | None:
        """Get cache statistics."""
        if self._cache is not None:
            return self._cache.get_stats()
        return None

    def get_cache_audit_log(
        self: BundleStateProtocol,
    ) -> tuple[CacheAuditLogEntry, ...] | None:
        """Get immutable cache audit log entries."""
        if self._cache is not None:
            return self._cache.get_audit_log()
        return None
