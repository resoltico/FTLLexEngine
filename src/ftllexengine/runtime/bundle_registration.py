"""Registration helpers for FluentBundle resource ingestion."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, assert_never

from ftllexengine.core.reference_graph import entry_dependency_set
from ftllexengine.integrity import IntegrityContext, SyntaxIntegrityError
from ftllexengine.introspection import extract_references
from ftllexengine.syntax import Comment, Junk, Message, Resource, Term

if TYPE_CHECKING:
    from ftllexengine.runtime.bundle_protocols import BundleStateProtocol

logger = logging.getLogger("ftllexengine.runtime.bundle")

_LOG_TRUNCATE_WARNING: int = 100


@dataclass(slots=True)
class _PendingRegistration:
    """Collected resource entries prior to mutating bundle state."""

    messages: dict[str, Message] = field(default_factory=dict)
    terms: dict[str, Term] = field(default_factory=dict)
    msg_deps: dict[str, frozenset[str]] = field(default_factory=dict)
    term_deps: dict[str, frozenset[str]] = field(default_factory=dict)
    junk: list[Junk] = field(default_factory=list)
    overwrite_warnings: list[tuple[Literal["message", "term"], str]] = field(default_factory=list)


class _BundleRegistrationMixin:
    """Resource registration behavior for FluentBundle."""

    def _collect_pending_entries(
        self: BundleStateProtocol, resource: Resource
    ) -> _PendingRegistration:
        """Collect parsed entries without mutating bundle state."""
        pending = _PendingRegistration()

        for entry in resource.entries:
            match entry:
                case Message():
                    msg_id = entry.id.name
                    if msg_id in self._messages or msg_id in pending.messages:
                        pending.overwrite_warnings.append(("message", msg_id))
                    pending.messages[msg_id] = entry
                    pending.msg_deps[msg_id] = entry_dependency_set(*extract_references(entry))
                case Term():
                    term_id = entry.id.name
                    if term_id in self._terms or term_id in pending.terms:
                        pending.overwrite_warnings.append(("term", term_id))
                    pending.terms[term_id] = entry
                    pending.term_deps[term_id] = entry_dependency_set(*extract_references(entry))
                case Junk():
                    pending.junk.append(entry)
                case Comment():
                    pass
                case _ as unreachable:  # pragma: no cover
                    assert_never(unreachable)

        return pending

    def _register_resource(
        self: BundleStateProtocol, resource: Resource, source_path: str | None
    ) -> tuple[Junk, ...]:
        """Register parsed resource entries via a two-phase commit."""
        pending = self._collect_pending_entries(resource)
        junk_tuple = tuple(pending.junk)

        if self._strict and junk_tuple:
            source_desc = source_path or "<string>"
            error_summary = "; ".join(repr(junk.content[:50]) for junk in junk_tuple[:3])
            if len(junk_tuple) > 3:
                error_summary += f" (and {len(junk_tuple) - 3} more)"

            context = IntegrityContext(
                component="bundle",
                operation="add_resource",
                key=source_desc,
                expected="<no syntax errors>",
                actual=f"<{len(junk_tuple)} syntax error(s)>",
                timestamp=time.monotonic(),
                wall_time_unix=time.time(),
            )
            msg = (
                f"Strict mode: {len(junk_tuple)} syntax error(s) in "
                f"{source_desc}: {error_summary}"
            )
            raise SyntaxIntegrityError(
                msg,
                context=context,
                junk_entries=junk_tuple,
                source_path=source_path,
            )

        for entry_type, entry_id in pending.overwrite_warnings:
            if entry_type == "message":
                logger.warning(
                    "Overwriting existing message '%s' with new definition",
                    entry_id,
                )
            else:
                logger.warning(
                    "Overwriting existing term '-%s' with new definition",
                    entry_id,
                )

        self._messages.update(pending.messages)
        self._terms.update(pending.terms)
        self._msg_deps.update(pending.msg_deps)
        self._term_deps.update(pending.term_deps)

        for msg_id in pending.messages:
            logger.debug("Registered message: %s", msg_id)
        for term_id in pending.terms:
            logger.debug("Registered term: %s", term_id)

        source_desc = source_path or "<string>"
        for junk in pending.junk:
            logger.warning(
                "Syntax error in %s: %s",
                source_desc,
                repr(junk.content[:_LOG_TRUNCATE_WARNING]),
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
