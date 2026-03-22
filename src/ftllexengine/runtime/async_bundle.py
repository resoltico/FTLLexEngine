"""Async-native FluentBundle wrapper for asyncio applications.

AsyncFluentBundle wraps FluentBundle and offloads all CPU-bound operations
to a thread pool via asyncio.to_thread(), keeping the event loop unblocked.
The underlying FluentBundle handles all concurrency via its internal RWLock;
this module is purely an asyncio adapter layer.

Python 3.13+.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Self

from ftllexengine.core.locale_utils import get_system_locale

from .bundle import FluentBundle

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from types import TracebackType

    from ftllexengine.core.value_types import FluentValue
    from ftllexengine.diagnostics import FrozenFluentError
    from ftllexengine.introspection import MessageIntrospection
    from ftllexengine.localization.types import LocaleCode
    from ftllexengine.runtime.cache import CacheAuditLogEntry, CacheStats
    from ftllexengine.syntax.ast import Junk, Message, Term

    from .cache_config import CacheConfig
    from .function_bridge import FunctionRegistry


class AsyncFluentBundle:
    """Async-native wrapper around FluentBundle for asyncio applications.

    All mutation and formatting operations are offloaded to a thread pool via
    asyncio.to_thread(), preventing event-loop blocking. The underlying
    FluentBundle handles all thread safety via its internal RWLock. This class
    is purely an asyncio adapter — no additional locking is introduced.

    Fast read lookups (has_message, get_message, etc.) are exposed as
    synchronous methods because the underlying dict operations are O(1) and
    hold the read lock for nanoseconds, not long enough to meaningfully block
    an event loop iteration.

    Supports the async context manager protocol:

    Examples:
        >>> import asyncio
        >>> async def example() -> None:
        ...     async with AsyncFluentBundle("en_US") as bundle:
        ...         await bundle.add_resource("greeting = Hello, { $name }!")
        ...         result, errors = await bundle.format_pattern(
        ...             "greeting", {"name": "Alice"}
        ...         )
        ...         assert errors == ()
        >>> asyncio.run(example())
    """

    __slots__ = ("_bundle",)

    def __init__(
        self,
        locale: str,
        /,
        *,
        use_isolating: bool = True,
        cache: CacheConfig | None = None,
        functions: FunctionRegistry | None = None,
        max_source_size: int | None = None,
        max_nesting_depth: int | None = None,
        max_expansion_size: int | None = None,
        strict: bool = True,
    ) -> None:
        """Initialize async bundle for locale.

        Args:
            locale: Locale code (en_US, de_DE, etc.) [positional-only]
            use_isolating: Wrap interpolated values in Unicode bidi isolation
                marks (default: True). Set False only when RTL languages are
                not used.
            cache: Cache configuration. Pass CacheConfig() for defaults.
            functions: Custom FunctionRegistry. Copied on construction;
                later mutations to the original have no effect.
            max_source_size: Maximum FTL source length in characters.
            max_nesting_depth: Maximum placeable nesting depth.
            max_expansion_size: Maximum formatted output length in characters.
            strict: Raise on formatting or syntax errors (default: True).
        """
        self._bundle = FluentBundle(
            locale,
            use_isolating=use_isolating,
            cache=cache,
            functions=functions,
            max_source_size=max_source_size,
            max_nesting_depth=max_nesting_depth,
            max_expansion_size=max_expansion_size,
            strict=strict,
        )

    @classmethod
    def for_system_locale(
        cls,
        *,
        use_isolating: bool = True,
        cache: CacheConfig | None = None,
        functions: FunctionRegistry | None = None,
        max_source_size: int | None = None,
        max_nesting_depth: int | None = None,
        max_expansion_size: int | None = None,
        strict: bool = True,
    ) -> AsyncFluentBundle:
        """Create AsyncFluentBundle for the current system locale.

        Detects the locale from OS environment variables (LANG, LC_ALL, etc.).

        Args:
            use_isolating: Wrap interpolated values in Unicode bidi isolation marks.
            cache: Cache configuration. Pass CacheConfig() to enable caching.
            functions: Custom FunctionRegistry (default: standard registry).
            max_source_size: Maximum FTL source size in characters.
            max_nesting_depth: Maximum placeable nesting depth.
            max_expansion_size: Maximum formatted output length in characters.
            strict: Fail-fast mode (default True).

        Returns:
            AsyncFluentBundle configured for the detected system locale.

        Raises:
            RuntimeError: If the system locale cannot be determined.
        """
        system_locale = get_system_locale(raise_on_failure=True)
        return cls(
            system_locale,
            use_isolating=use_isolating,
            cache=cache,
            functions=functions,
            max_source_size=max_source_size,
            max_nesting_depth=max_nesting_depth,
            max_expansion_size=max_expansion_size,
            strict=strict,
        )

    async def __aenter__(self) -> Self:
        """Enter async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit async context manager. No cleanup required."""

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return (
            f"AsyncFluentBundle(locale={self._bundle.locale!r}, "
            f"strict={self._bundle.strict!r})"
        )

    # ------------------------------------------------------------------
    # Properties (synchronous — no lock acquisition; pure attribute reads)
    # ------------------------------------------------------------------

    @property
    def locale(self) -> LocaleCode:
        """Locale code this bundle was created for."""
        return self._bundle.locale

    @property
    def strict(self) -> bool:
        """Whether strict mode is enabled."""
        return self._bundle.strict

    @property
    def use_isolating(self) -> bool:
        """Whether Unicode bidi isolation marks are inserted around interpolations."""
        return self._bundle.use_isolating

    @property
    def cache_enabled(self) -> bool:
        """Whether result caching is enabled."""
        return self._bundle.cache_enabled

    @property
    def cache_config(self) -> CacheConfig | None:
        """Active cache configuration, or None if caching is disabled."""
        return self._bundle.cache_config

    # ------------------------------------------------------------------
    # Async mutation and formatting operations (offloaded to thread pool)
    # ------------------------------------------------------------------

    async def add_resource(
        self, source: str, /, *, source_path: str | None = None
    ) -> tuple[Junk, ...]:
        """Add FTL resource from a string. Offloads parsing to a thread pool.

        Semantically identical to FluentBundle.add_resource() in all respects:
        strict-mode behavior, two-phase commit atomicity, thread safety, and
        overwrite warnings.

        Args:
            source: FTL file content [positional-only]
            source_path: Optional source path for error messages
                (e.g., "locales/en/ui.ftl"). Defaults to "<string>".

        Returns:
            Tuple of Junk entries. Empty if parsing succeeded without errors.

        Raises:
            TypeError: If source is not a string.
            SyntaxIntegrityError: In strict mode, if any Junk entries are parsed.
        """
        return await asyncio.to_thread(
            self._bundle.add_resource, source, source_path=source_path
        )

    async def add_resource_stream(
        self, lines: Iterable[str], /, *, source_path: str | None = None
    ) -> tuple[Junk, ...]:
        """Add FTL resource from a line iterator. Offloads parsing to a thread pool.

        Memory usage is proportional to the largest single FTL entry, not the
        total resource size. Semantically identical to add_resource() in all
        other respects.

        Args:
            lines: Iterable of FTL source lines [positional-only].
            source_path: Optional source path for error messages.

        Returns:
            Tuple of Junk entries. Empty if parsing succeeded without errors.

        Raises:
            SyntaxIntegrityError: In strict mode, if any Junk entries are parsed.

        Example:
            >>> async with AsyncFluentBundle("en_US") as bundle:
            ...     with open("locales/en/ui.ftl") as f:
            ...         await bundle.add_resource_stream(f, source_path="locales/en/ui.ftl")
        """
        return await asyncio.to_thread(
            self._bundle.add_resource_stream, lines, source_path=source_path
        )

    async def format_pattern(
        self,
        message_id: str,
        /,
        args: Mapping[str, FluentValue] | None = None,
        *,
        attribute: str | None = None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        """Format message to string. Offloads resolution to a thread pool.

        Semantically identical to FluentBundle.format_pattern() in all respects:
        strict/soft-error behavior, fallback semantics, and error reporting.

        Args:
            message_id: Message identifier [positional-only]
            args: Variable arguments for interpolation.
            attribute: Attribute name (keyword-only).

        Returns:
            Tuple of (formatted_string, errors). The string is never empty;
            errors is an empty tuple on success.

        Raises:
            FormattingIntegrityError: In strict mode, if any error occurs during
                formatting.
        """
        return await asyncio.to_thread(
            self._bundle.format_pattern, message_id, args, attribute=attribute
        )

    async def add_function(
        self, name: str, func: Callable[..., FluentValue]
    ) -> None:
        """Register a custom Fluent function. Offloads registration to a thread pool.

        Args:
            name: Function name as used in FTL (e.g., "CUSTOM_FORMAT").
                  Uppercase by convention.
            func: Callable implementing the function. See fluent_function decorator
                  for locale-injection support.
        """
        await asyncio.to_thread(self._bundle.add_function, name, func)

    # ------------------------------------------------------------------
    # Synchronous read operations (fast dict lookups — O(1), non-blocking)
    # ------------------------------------------------------------------

    def has_message(self, message_id: str) -> bool:
        """Return True if the bundle contains a message with the given ID.

        Synchronous. The underlying lookup is O(1) and holds the read lock
        for nanoseconds — not long enough to block an event loop iteration.

        Args:
            message_id: Message identifier to check.
        """
        return self._bundle.has_message(message_id)

    def has_attribute(self, message_id: str, attribute: str) -> bool:
        """Return True if the message exists and has the named attribute.

        Synchronous. The underlying lookup is O(1) and holds the read lock
        for nanoseconds — not long enough to block an event loop iteration.

        Args:
            message_id: Message identifier.
            attribute: Attribute name.
        """
        return self._bundle.has_attribute(message_id, attribute)

    def get_message_ids(self) -> list[str]:
        """Return a list of all message IDs registered in this bundle.

        Synchronous. Returns a snapshot; concurrent mutations are not visible
        in the returned list.
        """
        return self._bundle.get_message_ids()

    def get_message(self, message_id: str) -> Message | None:
        """Return the parsed AST node for a message, or None if not found.

        Synchronous. The underlying lookup is O(1).

        Args:
            message_id: Message identifier.
        """
        return self._bundle.get_message(message_id)

    def get_term(self, term_id: str) -> Term | None:
        """Return the parsed AST node for a term, or None if not found.

        The term_id should be supplied without the leading dash (e.g., ``"brand"``
        for ``-brand``). Synchronous. The underlying lookup is O(1).

        Args:
            term_id: Term identifier without leading dash.
        """
        return self._bundle.get_term(term_id)

    def introspect_message(self, message_id: str) -> MessageIntrospection:
        """Return complete introspection data for a message.

        Provides variable names, function names, reference graph, and selector
        presence. Synchronous; introspection is CPU-bound but fast.

        Args:
            message_id: Message identifier.

        Returns:
            MessageIntrospection with complete metadata.

        Raises:
            KeyError: If the message does not exist.
        """
        return self._bundle.introspect_message(message_id)

    def clear_cache(self) -> None:
        """Clear the format result cache, if caching is enabled.

        Synchronous. Safe to call from async code; the cache clear is O(1).
        """
        self._bundle.clear_cache()

    def get_cache_stats(self) -> CacheStats | None:
        """Return cache statistics, or None if caching is disabled.

        Synchronous. Returns a snapshot of current hit/miss counts.
        """
        return self._bundle.get_cache_stats()

    def get_cache_audit_log(self) -> tuple[CacheAuditLogEntry, ...] | None:
        """Return the immutable cache audit log, or None if caching is disabled.

        Synchronous. Each entry records a cache write event with dual timestamps
        (monotonic + wall-clock) for compliance audit trails.
        """
        return self._bundle.get_cache_audit_log()
