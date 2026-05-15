"""Async-native FluentBundle wrapper for asyncio applications.

AsyncFluentBundle wraps FluentBundle and owns its executor, admission control,
and shutdown semantics explicitly. The underlying FluentBundle still owns the
actual formatting and mutation logic; this module owns how that blocking work
is scheduled from asyncio.

Python 3.13+.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from threading import Thread
from typing import TYPE_CHECKING, Self, TypeVar

from ftllexengine.core.locale_utils import get_system_locale
from ftllexengine.core.validators import require_positive_int

from .bundle import FluentBundle

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from types import TracebackType

    from ftllexengine.core._limits import LimitArg
    from ftllexengine.core.semantic_types import LocaleCode
    from ftllexengine.core.value_types import FluentValue
    from ftllexengine.diagnostics import FrozenFluentError
    from ftllexengine.introspection import MessageIntrospection
    from ftllexengine.runtime.cache import CacheDebugLogEntry, CacheStats
    from ftllexengine.syntax.ast import Junk, Message, Term

    from .cache_config import CacheConfig
    from .function_bridge import FunctionRegistry

T = TypeVar("T")


class AsyncFluentBundle:
    """Async-native wrapper around FluentBundle for asyncio applications.

    All methods that may touch bundle locks or perform CPU-bound work route
    through one owned executor plus a bounded async admission gate. This keeps
    event-loop blocking behavior explicit and gives the bundle a shutdown owner.

    Supports the async context manager protocol:

    Examples:
        >>> import asyncio  # doctest: +SKIP
        >>> async def example() -> None:  # doctest: +SKIP
        ...     async with AsyncFluentBundle("en_US") as bundle:
        ...         await bundle.add_resource("greeting = Hello, { $name }!")
        ...         result, errors = await bundle.format_pattern(
        ...             "greeting", {"name": "Alice"}
        ...         )
        ...         assert errors == ()
        >>> asyncio.run(example())  # doctest: +SKIP
    """

    __slots__ = ("_bundle", "_executor", "_max_pending_operations", "_pending_gate")

    def __init__(
        self,
        locale: str,
        /,
        *,
        use_isolating: bool = True,
        cache: CacheConfig | None = None,
        functions: FunctionRegistry | None = None,
        max_source_size: LimitArg = None,
        max_nesting_depth: int | None = None,
        max_parse_errors: LimitArg = None,
        max_stream_line_length: LimitArg = None,
        max_expansion_size: LimitArg = None,
        max_workers: int = 4,
        max_pending_operations: int = 16,
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
            max_parse_errors: Maximum Junk entries accepted before parse abort.
            max_stream_line_length: Maximum line length accepted by stream parsing.
            max_expansion_size: Maximum formatted output length in characters.
            max_workers: Worker threads owned by this async wrapper.
            max_pending_operations: Maximum in-flight or queued async bundle calls.
            strict: Raise on formatting or syntax errors (default: True).
        """
        require_positive_int(max_workers, "max_workers")
        require_positive_int(max_pending_operations, "max_pending_operations")
        self._bundle = FluentBundle(
            locale,
            use_isolating=use_isolating,
            cache=cache,
            functions=functions,
            max_source_size=max_source_size,
            max_nesting_depth=max_nesting_depth,
            max_parse_errors=max_parse_errors,
            max_stream_line_length=max_stream_line_length,
            max_expansion_size=max_expansion_size,
            strict=strict,
        )
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=f"ftllexengine-{self._bundle.locale}",
        )
        self._max_pending_operations = max_pending_operations
        self._pending_gate = asyncio.Semaphore(max_pending_operations)

    @classmethod
    def for_system_locale(
        cls,
        *,
        use_isolating: bool = True,
        cache: CacheConfig | None = None,
        functions: FunctionRegistry | None = None,
        max_source_size: LimitArg = None,
        max_nesting_depth: int | None = None,
        max_parse_errors: LimitArg = None,
        max_stream_line_length: LimitArg = None,
        max_expansion_size: LimitArg = None,
        max_workers: int = 4,
        max_pending_operations: int = 16,
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
            max_parse_errors: Maximum Junk entries accepted before parse abort.
            max_stream_line_length: Maximum line length accepted by stream parsing.
            max_expansion_size: Maximum formatted output length in characters.
            max_workers: Worker threads owned by this async wrapper.
            max_pending_operations: Maximum in-flight or queued async bundle calls.
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
            max_parse_errors=max_parse_errors,
            max_stream_line_length=max_stream_line_length,
            max_expansion_size=max_expansion_size,
            max_workers=max_workers,
            max_pending_operations=max_pending_operations,
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
        """Exit async context manager and shut down the owned executor."""
        loop = asyncio.get_running_loop()
        done = loop.create_future()

        def shutdown_executor() -> None:
            try:
                self._executor.shutdown(wait=True, cancel_futures=False)
            except Exception as error:  # noqa: BLE001  # pragma: no cover
                # Premise: shutdown must resolve the awaiting coroutine exactly once.
                # Reason: a narrow list here would risk hanging __aexit__ if the
                # executor raises an unexpected failure during interpreter teardown.
                loop.call_soon_threadsafe(done.set_exception, error)
            else:
                loop.call_soon_threadsafe(done.set_result, None)

        Thread(target=shutdown_executor, name="ftllexengine-async-shutdown", daemon=True).start()
        await done

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return (
            f"AsyncFluentBundle(locale={self._bundle.locale!r}, "
            f"strict={self._bundle.strict!r}, "
            f"max_pending_operations={self._max_pending_operations!r})"
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

    async def _run_blocking(
        self,
        func: Callable[..., T],
        /,
        *args: object,
        **kwargs: object,
    ) -> T:
        """Run bundle work through the owned executor with bounded admission.

        Cancellation is explicit: once work is submitted to the thread pool it
        keeps running to completion, but the semaphore permit is released only
        when the underlying thread actually finishes.
        """
        await self._pending_gate.acquire()
        released = False

        def release_permit(_completed: object | None = None) -> None:
            nonlocal released
            if not released:
                released = True
                self._pending_gate.release()

        loop = asyncio.get_running_loop()
        future = loop.run_in_executor(
            self._executor,
            partial(func, *args, **kwargs),
        )
        try:
            result = await asyncio.wrap_future(future)
        except asyncio.CancelledError:
            future.add_done_callback(release_permit)
            raise
        except Exception:
            release_permit()
            raise
        else:
            release_permit()
            return result

    # ------------------------------------------------------------------
    # Async mutation and formatting operations (offloaded to thread pool)
    # ------------------------------------------------------------------

    async def add_resource(
        self,
        source: str,
        /,
        *,
        source_path: str | None = None,
        allow_overwrite: bool = False,
    ) -> tuple[Junk, ...]:
        """Add FTL resource from a string.

        Semantically identical to FluentBundle.add_resource() in all respects:
        strict-mode behavior, two-phase commit atomicity, thread safety, and
        overwrite admission.

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
        return await self._run_blocking(
            self._bundle.add_resource,
            source,
            source_path=source_path,
            allow_overwrite=allow_overwrite,
        )

    async def add_resource_stream(
        self,
        lines: Iterable[str],
        /,
        *,
        source_path: str | None = None,
        allow_overwrite: bool = False,
    ) -> tuple[Junk, ...]:
        """Add FTL resource from a line iterator.

        Args:
            lines: Iterable of FTL source lines [positional-only].
            source_path: Optional source path for error messages.

        Returns:
            Tuple of Junk entries. Empty if parsing succeeded without errors.

        Raises:
            SyntaxIntegrityError: In strict mode, if any Junk entries are parsed.

        Example:
            >>> async with AsyncFluentBundle("en_US") as bundle:  # doctest: +SKIP
            ...     with open("locales/en/ui.ftl") as f:
            ...         await bundle.add_resource_stream(f, source_path="locales/en/ui.ftl")
        """
        return await self._run_blocking(
            self._bundle.add_resource_stream,
            lines,
            source_path=source_path,
            allow_overwrite=allow_overwrite,
        )

    async def format_pattern(
        self,
        message_id: str,
        /,
        args: Mapping[str, FluentValue] | None = None,
        *,
        attribute: str | None = None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        """Format message to string.

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
        return await self._run_blocking(
            self._bundle.format_pattern,
            message_id,
            args,
            attribute=attribute,
        )

    async def add_function(
        self,
        name: str,
        func: Callable[..., FluentValue],
        *,
        cacheable: bool = False,
    ) -> None:
        """Register a custom Fluent function. Offloads registration to a thread pool.

        Args:
            name: Function name as used in FTL (e.g., "CUSTOM_FORMAT").
                  Uppercase by convention.
            func: Callable implementing the function. See fluent_function decorator
                  for locale-injection support.
            cacheable: Whether formatted outputs depending on this function may
                enter the cache. Defaults to ``False`` for safety.
        """
        await self._run_blocking(
            self._bundle.add_function,
            name,
            func,
            cacheable=cacheable,
        )

    # ------------------------------------------------------------------
    # Async read operations (all lock-taking bundle access stays off the loop)
    # ------------------------------------------------------------------

    async def has_message(self, message_id: str) -> bool:
        """Return True if the bundle contains a message with the given ID."""
        return await self._run_blocking(self._bundle.has_message, message_id)

    async def has_attribute(self, message_id: str, attribute: str) -> bool:
        """Return True if the message exists and has the named attribute."""
        return await self._run_blocking(self._bundle.has_attribute, message_id, attribute)

    async def get_message_ids(self) -> list[str]:
        """Return a snapshot list of all message IDs registered in this bundle."""
        return await self._run_blocking(self._bundle.get_message_ids)

    async def get_message(self, message_id: str) -> Message | None:
        """Return the parsed AST node for a message, or None if not found."""
        return await self._run_blocking(self._bundle.get_message, message_id)

    async def get_term(self, term_id: str) -> Term | None:
        """Return the parsed AST node for a term, or None if not found."""
        return await self._run_blocking(self._bundle.get_term, term_id)

    async def introspect_message(self, message_id: str) -> MessageIntrospection:
        """Return complete introspection data for a message."""
        return await self._run_blocking(self._bundle.introspect_message, message_id)

    async def clear_cache(self) -> None:
        """Clear the format result cache, if caching is enabled."""
        await self._run_blocking(self._bundle.clear_cache)

    async def get_cache_stats(self) -> CacheStats | None:
        """Return cache statistics, or None if caching is disabled."""
        return await self._run_blocking(self._bundle.get_cache_stats)

    async def get_cache_debug_log(self) -> tuple[CacheDebugLogEntry, ...] | None:
        """Return the immutable cache debug log, or None if caching is disabled."""
        return await self._run_blocking(self._bundle.get_cache_debug_log)
