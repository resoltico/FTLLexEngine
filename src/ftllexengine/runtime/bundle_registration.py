"""Registration helpers for FluentBundle resource ingestion."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, assert_never

from ftllexengine.core.reference_graph import entry_dependency_set
from ftllexengine.diagnostics._redaction import redacted_loader_snippet
from ftllexengine.integrity import (
    IntegrityContext,
    ResourceConflictIntegrityError,
    SyntaxIntegrityError,
)
from ftllexengine.introspection import extract_references
from ftllexengine.syntax import Comment, Junk, Message, Resource, Term

if TYPE_CHECKING:
    from ftllexengine.runtime.bundle_protocols import BundleStateProtocol

logger = logging.getLogger("ftllexengine.runtime.bundle")


@dataclass(slots=True)
class _PendingRegistration:
    """Collected resource entries prior to mutating bundle state."""

    messages: dict[str, Message] = field(default_factory=dict)
    terms: dict[str, Term] = field(default_factory=dict)
    msg_deps: dict[str, frozenset[str]] = field(default_factory=dict)
    term_deps: dict[str, frozenset[str]] = field(default_factory=dict)
    junk: list[Junk] = field(default_factory=list)
    duplicate_ids: list[str] = field(default_factory=list)
    shadowed_ids: list[str] = field(default_factory=list)


class _BundleRegistrationMixin:
    """Resource registration behavior for FluentBundle."""

    @staticmethod
    def _conflict_label(entry_type: Literal["message", "term"], entry_id: str) -> str:
        """Render the public-facing identifier used in conflict diagnostics."""
        return entry_id if entry_type == "message" else f"-{entry_id}"

    @staticmethod
    def _append_unique(target: list[str], value: str) -> None:
        """Keep conflict lists stable without duplicating identical IDs."""
        if value not in target:
            target.append(value)

    def _collect_pending_entry(
        self: BundleStateProtocol,
        pending: _PendingRegistration,
        entry: Message | Term | Junk | Comment,
    ) -> None:
        """Merge one parsed entry into the pending registration accumulator."""
        match entry:
            case Message():
                msg_id = entry.id.name
                if msg_id in pending.messages:
                    _BundleRegistrationMixin._append_unique(
                        pending.duplicate_ids,
                        _BundleRegistrationMixin._conflict_label("message", msg_id),
                    )
                elif msg_id in self._messages:
                    _BundleRegistrationMixin._append_unique(
                        pending.shadowed_ids,
                        _BundleRegistrationMixin._conflict_label("message", msg_id),
                    )
                pending.messages[msg_id] = entry
                pending.msg_deps[msg_id] = entry_dependency_set(*extract_references(entry))
            case Term():
                term_id = entry.id.name
                if term_id in pending.terms:
                    _BundleRegistrationMixin._append_unique(
                        pending.duplicate_ids,
                        _BundleRegistrationMixin._conflict_label("term", term_id),
                    )
                elif term_id in self._terms:
                    _BundleRegistrationMixin._append_unique(
                        pending.shadowed_ids,
                        _BundleRegistrationMixin._conflict_label("term", term_id),
                    )
                pending.terms[term_id] = entry
                pending.term_deps[term_id] = entry_dependency_set(*extract_references(entry))
            case Junk():
                pending.junk.append(entry)
            case Comment():
                pass
            case _ as unreachable:  # pragma: no cover
                assert_never(unreachable)

    def _collect_pending_entries(
        self: BundleStateProtocol, resource: Resource
    ) -> _PendingRegistration:
        """Collect parsed entries without mutating bundle state."""
        pending = _PendingRegistration()

        for entry in resource.entries:
            self._collect_pending_entry(pending, entry)

        return pending

    def _register_resource(
        self: BundleStateProtocol,
        resource: Resource,
        source_path: str | None,
        *,
        allow_overwrite: bool = False,
    ) -> tuple[Junk, ...]:
        """Register parsed resource entries via a two-phase commit."""
        pending = self._collect_pending_entries(resource)
        return self._register_pending_entries(
            pending,
            source_path,
            allow_overwrite=allow_overwrite,
        )

    def _register_pending_entries(
        self: BundleStateProtocol,
        pending: _PendingRegistration,
        source_path: str | None,
        *,
        allow_overwrite: bool = False,
    ) -> tuple[Junk, ...]:
        """Commit a pre-collected pending registration into the bundle state."""
        junk_tuple = tuple(pending.junk)
        duplicate_ids = tuple(pending.duplicate_ids)
        shadowed_ids = tuple(pending.shadowed_ids)
        source_desc = source_path or "<string>"

        if self._strict and junk_tuple:
            _BundleRegistrationMixin._raise_strict_junk_error(
                junk_tuple, source_desc, source_path
            )
        if duplicate_ids:
            _BundleRegistrationMixin._raise_duplicate_error(
                duplicate_ids, source_desc, source_path
            )

        if shadowed_ids and not allow_overwrite:
            _BundleRegistrationMixin._raise_shadow_error(
                shadowed_ids, source_desc, source_path
            )

        for entry_id in shadowed_ids:
            logger.warning("Replacing existing bundle entry %s from %s", entry_id, source_desc)

        self._messages.update(pending.messages)
        self._terms.update(pending.terms)
        self._msg_deps.update(pending.msg_deps)
        self._term_deps.update(pending.term_deps)

        for msg_id in pending.messages:
            logger.debug("Registered message: %s", msg_id)
        for term_id in pending.terms:
            logger.debug("Registered term: %s", term_id)

        for junk in pending.junk:
            logger.warning(
                "Syntax error in %s: %s",
                source_desc,
                redacted_loader_snippet(junk.content[:100]),
            )

        if source_path:
            logger.info(
                "Added resource %s: %d messages, %d terms, %d junk entries",
                source_path,
                len(self._messages),
                len(self._terms),
                len(pending.junk),
            )
        else:
            logger.info(
                "Added resource: %d messages, %d terms, %d junk entries",
                len(self._messages),
                len(self._terms),
                len(pending.junk),
            )

        if self._cache is not None:
            self._cache.clear()
            logger.debug("Cache cleared after add_resource")

        return junk_tuple

    @staticmethod
    def _conflict_summary(conflict_ids: tuple[str, ...]) -> str:
        """Summarize conflict identifiers without overlong diagnostics."""
        summary = ", ".join(conflict_ids[:5])
        if len(conflict_ids) > 5:
            summary += f" (and {len(conflict_ids) - 5} more)"
        return summary

    @staticmethod
    def _raise_strict_junk_error(
        junk_entries: tuple[Junk, ...],
        source_desc: str,
        source_path: str | None,
    ) -> None:
        """Fail closed when strict ingestion encounters parser junk."""
        error_summary = "; ".join(
            redacted_loader_snippet(junk.content[:50]) for junk in junk_entries[:3]
        )
        if len(junk_entries) > 3:
            error_summary += f" (and {len(junk_entries) - 3} more)"

        context = IntegrityContext(
            component="bundle",
            operation="add_resource",
            key=source_desc,
            expected="<no syntax errors>",
            actual=f"<{len(junk_entries)} syntax error(s)>",
            timestamp=time.monotonic(),
            wall_time_unix=time.time(),
        )
        msg = f"Strict mode: {len(junk_entries)} syntax error(s) in {source_desc}: {error_summary}"
        raise SyntaxIntegrityError(
            msg,
            context=context,
            junk_entries=junk_entries,
            source_path=source_path,
        )

    @staticmethod
    def _raise_duplicate_error(
        duplicate_ids: tuple[str, ...],
        source_desc: str,
        source_path: str | None,
    ) -> None:
        """Reject duplicate IDs inside one resource before mutating bundle state."""
        context = IntegrityContext(
            component="bundle",
            operation="add_resource",
            key=source_desc,
            expected="unique resource IDs",
            actual=", ".join(duplicate_ids),
            timestamp=time.monotonic(),
            wall_time_unix=time.time(),
        )
        duplicate_summary = _BundleRegistrationMixin._conflict_summary(duplicate_ids)
        msg = f"Resource defines duplicate message/term IDs in {source_desc}: {duplicate_summary}"
        raise ResourceConflictIntegrityError(
            msg,
            context=context,
            duplicate_ids=duplicate_ids,
            source_path=source_path,
        )

    @staticmethod
    def _raise_shadow_error(
        shadowed_ids: tuple[str, ...],
        source_desc: str,
        source_path: str | None,
    ) -> None:
        """Reject implicit replacement of existing canonical bundle entries."""
        context = IntegrityContext(
            component="bundle",
            operation="add_resource",
            key=source_desc,
            expected="no replacement of existing IDs",
            actual=", ".join(shadowed_ids),
            timestamp=time.monotonic(),
            wall_time_unix=time.time(),
        )
        shadow_summary = _BundleRegistrationMixin._conflict_summary(shadowed_ids)
        msg = (
            f"Resource attempts to replace existing IDs in {source_desc}: "
            f"{shadow_summary}. Pass allow_overwrite=True only when replacement "
            "is intentional and audited."
        )
        raise ResourceConflictIntegrityError(
            msg,
            context=context,
            shadowed_ids=shadowed_ids,
            source_path=source_path,
        )
