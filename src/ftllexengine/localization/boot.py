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

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ftllexengine.localization.loading import (
    FallbackInfo,
    LoadSummary,
    PathResourceLoader,
    ResourceLoader,
)
from ftllexengine.localization.orchestrator import FluentLocalization

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from ftllexengine.introspection import MessageVariableValidationResult
    from ftllexengine.localization.types import MessageId
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
        strict: Fail-fast on formatting errors (default: True).
        use_isolating: Wrap placeables in Unicode bidi isolation marks
            (default: True).
        cache: Cache configuration, or None to disable (default: None).
        on_fallback: Callback invoked when a message is resolved from a
            fallback locale (optional). Receives a FallbackInfo instance.

    Example:
        >>> config = LocalizationBootConfig(
        ...     locales=('lv', 'en'),
        ...     resource_ids=('ui.ftl',),
        ...     base_path='locales/{locale}',
        ...     message_schemas={'welcome': frozenset({'name'})},
        ... )
        >>> l10n = config.boot()  # raises on any load error or schema mismatch
    """

    locales: tuple[str, ...]
    resource_ids: tuple[str, ...]
    loader: ResourceLoader | None = None
    base_path: str | None = None
    message_schemas: Mapping[MessageId, frozenset[str] | set[str]] | None = None
    strict: bool = True
    use_isolating: bool = True
    cache: CacheConfig | None = None
    on_fallback: Callable[[FallbackInfo], None] | None = None

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
        if path is None:
            # Unreachable: __post_init__ rejects the case where both are None.
            msg = "internal invariant violated: both loader and base_path are None"
            raise AssertionError(msg)  # pragma: no cover
        return PathResourceLoader(path)

    def boot(self) -> FluentLocalization:
        """Build and boot-validate a FluentLocalization instance.

        Executes the full boot sequence in strict order:

        1. Creates FluentLocalization with the configured loader and locales,
           loading all resources eagerly.
        2. Calls require_clean() — raises IntegrityCheckFailedError if any
           resource failed to load, produced FTL junk entries, or was missing.
        3. If message_schemas is provided, calls validate_message_schemas() —
           raises IntegrityCheckFailedError if any declared message is absent
           or its variable set does not match exactly.

        All three steps must succeed for boot() to return. This guarantees
        that the returned FluentLocalization instance has a clean load summary
        and, when schemas are declared, all schema contracts are satisfied.

        Returns:
            Fully-initialized and boot-validated FluentLocalization.

        Raises:
            IntegrityCheckFailedError: If any resources failed to load,
                produced junk entries, or if message schemas do not match.
            ValueError: Propagated from PathResourceLoader when base_path
                lacks the required {locale} placeholder.
        """
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

        l10n.require_clean()

        if self.message_schemas is not None:
            l10n.validate_message_schemas(self.message_schemas)

        return l10n

    def boot_with_summary(
        self,
    ) -> tuple[FluentLocalization, LoadSummary, tuple[MessageVariableValidationResult, ...]]:
        """Build and boot-validate, returning the full boot evidence record.

        Identical to boot() but returns structured evidence alongside the
        localization instance. Useful for audit trails, boot-time logging,
        and applications that need to inspect load and schema results after
        a successful boot.

        Returns:
            Three-tuple of:
            - FluentLocalization: Validated instance (same guarantee as boot()).
            - LoadSummary: Immutable record of all resource load attempts.
            - tuple[MessageVariableValidationResult, ...]: Schema validation
              results for each key in message_schemas. Empty tuple when
              message_schemas is None.

        Raises:
            IntegrityCheckFailedError: Same conditions as boot().
            ValueError: Same conditions as boot().
        """
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

        schema_results: tuple[MessageVariableValidationResult, ...]
        if self.message_schemas is not None:
            schema_results = l10n.validate_message_schemas(self.message_schemas)
        else:
            schema_results = ()

        return l10n, summary, schema_results

    @staticmethod
    def from_path(
        locales: tuple[str, ...],
        resource_ids: tuple[str, ...],
        base_path: str | Path,
        *,
        message_schemas: (
            Mapping[MessageId, frozenset[str] | set[str]] | None
        ) = None,
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
            strict=strict,
            use_isolating=use_isolating,
            cache=cache,
            on_fallback=on_fallback,
        )
