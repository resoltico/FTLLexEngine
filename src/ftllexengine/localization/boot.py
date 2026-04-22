"""Boot configuration for strict-mode FluentLocalization assembly.

Provides LocalizationBootConfig, a frozen dataclass that composes
PathResourceLoader, FluentLocalization, require_clean(), and
validate_message_schemas() into a single canonical boot API.

Designed for applications that require audited, validated localization boot
(e.g., financial services, regulated systems) where every resource must load
cleanly and declared message schemas must match exactly before the application
accepts production traffic.

Python 3.13+. Zero external dependencies.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ftllexengine.integrity import IntegrityCheckFailedError, IntegrityContext
from ftllexengine.localization.loading import (
    FallbackInfo,
    LoadSummary,
    PathResourceLoader,
    ResourceLoader,
)
from ftllexengine.localization.orchestrator import FluentLocalization

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from ftllexengine.core.semantic_types import MessageId
    from ftllexengine.introspection import MessageVariableValidationResult
    from ftllexengine.runtime.cache_config import CacheConfig

__all__ = ["LocalizationBootConfig"]


@dataclass(frozen=True, slots=True)
class LocalizationBootConfig:
    """Boot configuration for strict-mode FluentLocalization assembly.

    Composes PathResourceLoader (or a custom ResourceLoader),
    FluentLocalization, require_clean(), and validate_message_schemas()
    in a single canonical API for applications that require audited
    localization boot.

    Exactly one of ``loader`` or ``base_path`` must be provided.
    ``base_path`` is a shorthand that creates a PathResourceLoader with
    the given path template (must contain a ``{locale}`` placeholder, e.g.,
    ``"locales/{locale}"``).

    Attributes:
        locales: Locale codes in fallback priority order (e.g., ('lv', 'en')).
        resource_ids: FTL file identifiers to load (e.g., ('ui.ftl',)).
        loader: Custom resource loader implementing the ResourceLoader protocol.
            Mutually exclusive with ``base_path``.
        base_path: Path template with ``{locale}`` placeholder for creating a
            PathResourceLoader. Mutually exclusive with ``loader``.
        message_schemas: Optional mapping of message ID to expected variable
            set. When provided, boot() enforces exact variable contracts via
            validate_message_schemas() and raises IntegrityCheckFailedError
            if any message is missing or its variable set differs.
        required_messages: Optional set of message IDs that must be resolvable
            by at least one locale in the fallback chain. When provided,
            boot() raises IntegrityCheckFailedError for any message absent
            from all locales, regardless of message_schemas. This enforces
            message existence contracts at pack definition time rather than
            relying on the caller to remember to pass message_schemas.
        strict: Fail-fast on formatting errors (default: True).
        use_isolating: Wrap placeables in Unicode bidi isolation marks
            (default: True).
        cache: Cache configuration, or None to disable (default: None).
        on_fallback: Callback invoked when a message is resolved from a
            fallback locale (optional). Receives a FallbackInfo instance.

    Example:
        >>> config = LocalizationBootConfig(  # doctest: +SKIP
        ...     locales=('lv', 'en'),
        ...     resource_ids=('ui.ftl',),
        ...     base_path='locales/{locale}',
        ...     message_schemas={'welcome': frozenset({'name'})},
        ...     required_messages=frozenset({'welcome', 'farewell'}),
        ... )
        >>> l10n, summary, schema_results = config.boot()  # doctest: +SKIP
    """

    locales: tuple[str, ...]
    resource_ids: tuple[str, ...]
    loader: ResourceLoader | None = None
    base_path: str | None = None
    message_schemas: Mapping[MessageId, frozenset[str] | set[str]] | None = None
    required_messages: frozenset[str] | None = None
    strict: bool = True
    use_isolating: bool = True
    cache: CacheConfig | None = None
    on_fallback: Callable[[FallbackInfo], None] | None = None
    # One-shot guard: False until boot() is called, then permanently True.
    # object.__setattr__ is used in boot() to bypass the frozen constraint for
    # this single transition. Config fields (locales, resource_ids, etc.) remain
    # effectively immutable; only this guard transitions (False -> True, once).
    # This is a permanent architectural pattern — see Known Waiver Registry.
    _booted: bool = field(default=False, init=False, repr=False, compare=False, hash=False)

    def __post_init__(self) -> None:
        """Validate boot configuration invariants.

        Raises:
            ValueError: If locales is empty.
            ValueError: If resource_ids is empty.
            ValueError: If neither loader nor base_path is provided.
            ValueError: If both loader and base_path are provided.
        """
        if not self.locales:
            msg = "LocalizationBootConfig.locales must not be empty"
            raise ValueError(msg)
        if not self.resource_ids:
            msg = "LocalizationBootConfig.resource_ids must not be empty"
            raise ValueError(msg)
        if self.loader is None and self.base_path is None:
            msg = (
                "LocalizationBootConfig requires either 'loader' or 'base_path'. "
                "Provide a ResourceLoader instance or a path template "
                "containing '{locale}' (e.g., 'locales/{locale}')."
            )
            raise ValueError(msg)
        if self.loader is not None and self.base_path is not None:
            msg = (
                "LocalizationBootConfig accepts either 'loader' or 'base_path', "
                "not both. Remove one of them."
            )
            raise ValueError(msg)

    def _resolve_loader(self) -> ResourceLoader:
        """Return the effective resource loader.

        Returns PathResourceLoader constructed from base_path when loader is
        absent; returns loader directly otherwise.
        """
        if self.loader is not None:
            return self.loader
        path = self.base_path
        if path is None:  # pragma: no cover
            # Unreachable: __post_init__ rejects the case where both are None.
            msg = "internal invariant violated: both loader and base_path are None"
            raise AssertionError(msg)
        return PathResourceLoader(path)

    def _check_required_messages(self, l10n: FluentLocalization) -> None:
        """Raise IntegrityCheckFailedError if any required message is absent.

        Checks each message ID in required_messages against the full fallback
        chain. A message is present if at least one locale in the chain can
        resolve it. The first absent message triggers the error; collection
        of all absent IDs is included in the error message for diagnostics.

        Args:
            l10n: Fully initialized FluentLocalization after require_clean().

        Raises:
            IntegrityCheckFailedError: If any required message is absent from
                all locales in the fallback chain. IntegrityContext carries
                component="localization.boot", operation="required_messages",
                and key=<first absent message ID>.
        """
        if self.required_messages is None:
            return

        absent: list[str] = [
            msg_id for msg_id in sorted(self.required_messages)
            if not l10n.has_message(msg_id)
        ]

        if not absent:
            return

        first_absent = absent[0]
        absent_list = ", ".join(repr(m) for m in absent)
        msg = (
            f"Required message(s) absent from all locales in the fallback chain: "
            f"{absent_list}"
        )
        context = IntegrityContext(
            component="localization.boot",
            operation="required_messages",
            key=first_absent,
            expected="message present in at least one locale",
            actual=f"absent_messages={len(absent)}",
            timestamp=time.monotonic(),
            wall_time_unix=time.time(),
        )
        raise IntegrityCheckFailedError(msg, context=context)

    def boot(
        self,
    ) -> tuple[FluentLocalization, LoadSummary, tuple[MessageVariableValidationResult, ...]]:
        """Build and boot-validate, returning the full boot evidence record.

        Primary boot API. Executes the full boot sequence in strict order:

        1. Creates FluentLocalization with the configured loader and locales,
           loading all resources eagerly.
        2. Calls require_clean() — raises IntegrityCheckFailedError if any
           resource failed to load, produced FTL junk entries, or was missing.
        3. If required_messages is provided, verifies each required message is
           resolvable by at least one locale in the fallback chain — raises
           IntegrityCheckFailedError with component="localization.boot",
           operation="required_messages" if any are absent.
        4. If message_schemas is provided, calls validate_message_schemas() —
           raises IntegrityCheckFailedError if any declared message is absent
           or its variable set does not match exactly.

        All steps must succeed for boot() to return. This guarantees that the
        returned FluentLocalization instance has a clean load summary, all
        required messages are present, and all schema contracts are satisfied.

        Returning structured evidence is the primary API because financial
        applications require boot evidence in their startup audit trail. Use
        boot_simple() when only the FluentLocalization instance is needed.

        Returns:
            Three-tuple of:
            - FluentLocalization: Validated instance.
            - LoadSummary: Immutable record of all resource load attempts.
            - tuple[MessageVariableValidationResult, ...]: Schema validation
              results for each key in message_schemas. Empty tuple when
              message_schemas is None.

        Raises:
            IntegrityCheckFailedError: If any resources failed to load,
                produced junk entries, any required message is absent, or if
                message schemas do not match.
            ValueError: Propagated from PathResourceLoader when base_path
                lacks the required {locale} placeholder.
        """
        if self._booted:
            msg = (
                "LocalizationBootConfig.boot() has already been called on this instance. "
                "LocalizationBootConfig is a one-shot boot coordinator — create a new "
                "instance to run boot again."
            )
            raise RuntimeError(msg)
        object.__setattr__(self, "_booted", True)

        loader = self._resolve_loader()

        l10n = FluentLocalization(
            self.locales,
            self.resource_ids,
            loader,
            use_isolating=self.use_isolating,
            cache=self.cache,
            on_fallback=self.on_fallback,
            strict=self.strict,
        )

        summary = l10n.require_clean()
        self._check_required_messages(l10n)

        schema_results: tuple[MessageVariableValidationResult, ...]
        if self.message_schemas is not None:
            schema_results = l10n.validate_message_schemas(self.message_schemas)
        else:
            schema_results = ()

        return l10n, summary, schema_results

    def boot_simple(self) -> FluentLocalization:
        """Build and boot-validate a FluentLocalization instance.

        Convenience wrapper around boot() for callers that only need the
        FluentLocalization and do not require the boot evidence record.
        Executes the identical boot sequence (require_clean, required_messages
        check, validate_message_schemas) and raises on any failure.

        Use boot() when structured evidence (LoadSummary, schema validation
        results) must be captured for audit trails. Use boot_simple() when
        the FluentLocalization instance alone is sufficient.

        Returns:
            Fully-initialized and boot-validated FluentLocalization.

        Raises:
            IntegrityCheckFailedError: If any resources failed to load,
                produced junk entries, any required message is absent, or if
                message schemas do not match.
            ValueError: Propagated from PathResourceLoader when base_path
                lacks the required {locale} placeholder.
        """
        l10n, _, _ = self.boot()
        return l10n

    @staticmethod
    def from_path(
        locales: tuple[str, ...],
        resource_ids: tuple[str, ...],
        base_path: str | Path,
        *,
        message_schemas: (
            Mapping[MessageId, frozenset[str] | set[str]] | None
        ) = None,
        required_messages: frozenset[str] | None = None,
        strict: bool = True,
        use_isolating: bool = True,
        cache: CacheConfig | None = None,
        on_fallback: Callable[[FallbackInfo], None] | None = None,
    ) -> LocalizationBootConfig:
        """Construct a LocalizationBootConfig from a path template.

        Convenience factory for the common case where resources live on
        disk under a directory tree keyed by locale code. The path template
        must contain a ``{locale}`` placeholder (e.g., ``"locales/{locale}"``).

        Args:
            locales: Locale codes in fallback priority order.
            resource_ids: FTL file identifiers to load.
            base_path: Path template with ``{locale}`` placeholder, as a
                string or Path. Path objects are converted to POSIX string
                form automatically.
            message_schemas: Optional variable-schema contracts per message.
            required_messages: Optional set of message IDs that must exist
                in at least one locale in the fallback chain.
            strict: Fail-fast on formatting errors (default: True).
            use_isolating: Unicode bidi isolation marks (default: True).
            cache: Cache configuration, or None to disable.
            on_fallback: Fallback event callback.

        Returns:
            LocalizationBootConfig ready for boot().

        Raises:
            ValueError: If locales or resource_ids is empty.
            ValueError: If base_path does not contain ``{locale}``.
        """
        path_str = base_path.as_posix() if isinstance(base_path, Path) else base_path
        return LocalizationBootConfig(
            locales=locales,
            resource_ids=resource_ids,
            base_path=path_str,
            message_schemas=message_schemas,
            required_messages=required_messages,
            strict=strict,
            use_isolating=use_isolating,
            cache=cache,
            on_fallback=on_fallback,
        )
