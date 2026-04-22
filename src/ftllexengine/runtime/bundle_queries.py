"""Query and introspection helpers for FluentBundle."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ftllexengine.introspection import extract_variables, introspect_message

if TYPE_CHECKING:
    from ftllexengine.introspection import MessageIntrospection
    from ftllexengine.runtime.bundle_protocols import BundleStateProtocol
    from ftllexengine.syntax import Message, Term


class _BundleQueryMixin:
    """Read-only query behavior for FluentBundle."""

    def has_message(self: BundleStateProtocol, message_id: str) -> bool:
        """Return whether the bundle contains ``message_id``."""
        with self._rwlock.read():
            return message_id in self._messages

    def has_attribute(
        self: BundleStateProtocol, message_id: str, attribute: str
    ) -> bool:
        """Return whether ``message_id`` exposes ``attribute``."""
        with self._rwlock.read():
            message = self._messages.get(message_id)
            if message is None:
                return False
            return any(attr.id.name == attribute for attr in message.attributes)

    def get_message_ids(self: BundleStateProtocol) -> list[str]:
        """Return message IDs in insertion order."""
        with self._rwlock.read():
            return list(self._messages.keys())

    def get_message_variables(
        self: BundleStateProtocol, message_id: str
    ) -> frozenset[str]:
        """Return the variables referenced by one message."""
        with self._rwlock.read():
            if message_id not in self._messages:
                msg = f"Message '{message_id}' not found"
                raise KeyError(msg)
            return frozenset(extract_variables(self._messages[message_id]))

    def get_all_message_variables(
        self: BundleStateProtocol,
    ) -> dict[str, frozenset[str]]:
        """Return variables for every registered message."""
        with self._rwlock.read():
            return {
                message_id: frozenset(extract_variables(message))
                for message_id, message in self._messages.items()
            }

    def introspect_message(
        self: BundleStateProtocol, message_id: str
    ) -> MessageIntrospection:
        """Return structured introspection for ``message_id``."""
        with self._rwlock.read():
            if message_id not in self._messages:
                msg = f"Message '{message_id}' not found"
                raise KeyError(msg)
            return introspect_message(self._messages[message_id])

    def introspect_term(
        self: BundleStateProtocol, term_id: str
    ) -> MessageIntrospection:
        """Return structured introspection for ``term_id``."""
        with self._rwlock.read():
            if term_id not in self._terms:
                msg = f"Term '{term_id}' not found"
                raise KeyError(msg)
            return introspect_message(self._terms[term_id])

    def get_message(
        self: BundleStateProtocol, message_id: str
    ) -> Message | None:
        """Return the raw message AST node when present."""
        with self._rwlock.read():
            return self._messages.get(message_id)

    def get_term(self: BundleStateProtocol, term_id: str) -> Term | None:
        """Return the raw term AST node when present."""
        with self._rwlock.read():
            return self._terms.get(term_id)
