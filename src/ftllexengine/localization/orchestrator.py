"""Multi-locale orchestration with fallback chains.

Implements FluentLocalization following Mozilla's python-fluent architecture.
Separates multi-locale orchestration (FluentLocalization) from single-locale
formatting (FluentBundle).

Key architectural decisions:
- Eager resource and bundle initialization: FTL resources AND bundles loaded at init
- Protocol-based ResourceLoader (dependency inversion)
- Immutable locale chain (established at construction)
- Python 3.13 features: pattern matching, TypeIs, frozen dataclasses

Initialization Behavior:
    FluentLocalization loads all resources eagerly at construction and collects
    load results in a LoadSummary. FileNotFoundError and other load errors are
    captured in ResourceLoadResult objects with appropriate status codes
    (NOT_FOUND, ERROR) rather than being raised as exceptions.

    To detect load failures, call get_load_summary() after construction:

        l10n = FluentLocalization(['en', 'de'], ...)
        summary = l10n.get_load_summary()
        if summary.errors > 0:
            raise RuntimeError(f"Failed to load {summary.errors} resources")

    Bundles are created eagerly for locales that have resources loaded during
    initialization. Fallback locale bundles (for locales not in the resource
    loading loop) are created lazily on first access. This hybrid approach
    balances comprehensive error collection with memory efficiency.

Python 3.13+.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ftllexengine.core.locale_utils import require_locale_code
from ftllexengine.localization.orchestrator_formatting import _LocalizationFormattingMixin
from ftllexengine.localization.orchestrator_loading import _LocalizationLoadingMixin
from ftllexengine.localization.orchestrator_queries import _LocalizationQueryMixin
from ftllexengine.runtime.cache import CacheStats
from ftllexengine.runtime.rwlock import RWLock

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from ftllexengine.core.semantic_types import LocaleCode, ResourceId
    from ftllexengine.core.value_types import FluentValue
    from ftllexengine.localization.loading import FallbackInfo, ResourceLoader, ResourceLoadResult
    from ftllexengine.runtime.bundle import FluentBundle
    from ftllexengine.runtime.cache_config import CacheConfig

__all__ = ["FluentLocalization", "LocalizationCacheStats"]


class LocalizationCacheStats(CacheStats, total=True):
    """Aggregate cache statistics across all bundles in a FluentLocalization.

    Extends CacheStats with an additional field tracking the number of
    bundles contributing to the aggregated metrics.
    """

    bundle_count: int
    """Number of initialized bundles contributing to these statistics."""


class FluentLocalization(
    _LocalizationQueryMixin,
    _LocalizationFormattingMixin,
    _LocalizationLoadingMixin,
):
    """Multi-locale message formatting with fallback chains.

    Orchestrates multiple FluentBundle instances (one per locale) and implements
    locale fallback logic. Follows Mozilla's python-fluent architecture.

    Architecture:
    - FluentBundle: Single-locale formatting (1 bundle = 1 locale)
    - FluentLocalization: Multi-locale orchestration (manages N bundles)

    This class does NOT subclass FluentBundle - it wraps multiple instances.

    Uses Python 3.13 features:
    - Pattern matching for fallback logic
    - Generator expressions for lazy bundle creation
    - Match statements for error handling

    Example - Disk-based resources:
        >>> loader = PathResourceLoader("locales/{locale}")  # doctest: +SKIP
        >>> l10n = FluentLocalization(['lv', 'en'], ['ui.ftl'], loader)  # doctest: +SKIP
        >>> result, errors = l10n.format_value('welcome', {'name': 'Anna'})  # doctest: +SKIP
        # Tries 'lv' first, falls back to 'en' if message not found

    Example - Direct resource provision:
        >>> l10n = FluentLocalization(['lv', 'en'])  # doctest: +SKIP
        >>> l10n.add_resource('lv', 'welcome = Sveiki, { $name }!')  # doctest: +SKIP
        >>> l10n.add_resource('en', 'welcome = Hello, { $name }!')  # doctest: +SKIP
        >>> result, errors = l10n.format_value('welcome', {'name': 'Anna'})  # doctest: +SKIP
        # Returns: ('Sveiki, Anna!', ())

    Attributes:
        locales: Immutable tuple of locale codes in fallback priority order
    """

    __slots__ = (
        "_bundles",
        "_cache_config",
        "_load_results",
        "_locales",
        "_lock",
        "_on_fallback",
        "_pending_functions",
        "_primary_locale",
        "_resource_ids",
        "_resource_loader",
        "_strict",
        "_use_isolating",
    )

    def __init__(
        self,
        locales: Iterable[LocaleCode],
        resource_ids: Iterable[ResourceId] | None = None,
        resource_loader: ResourceLoader | None = None,
        *,
        use_isolating: bool = True,
        cache: CacheConfig | None = None,
        on_fallback: Callable[[FallbackInfo], None] | None = None,
        strict: bool = True,
    ) -> None:
        """Initialize multi-locale localization.

        Args:
            locales: Locale codes in fallback order (e.g., ['lv', 'en', 'lt'])
            resource_ids: FTL file identifiers to load (e.g., ['ui.ftl', 'errors.ftl'])
            resource_loader: Loader for fetching FTL resources (optional)
            use_isolating: Wrap placeables in Unicode bidi isolation marks
            cache: Cache configuration. Pass ``CacheConfig()`` to enable caching
                with defaults, or ``CacheConfig(size=500, ...)`` for custom settings.
                ``None`` disables caching (default). Applied to each bundle created.
            on_fallback: Optional callback invoked when a message is resolved from
                        a fallback locale instead of the primary locale. Useful for
                        debugging and monitoring which messages are missing translations.
                        The callback receives a FallbackInfo with requested_locale,
                        resolved_locale, and message_id.
            strict: Fail-fast on formatting errors (default: True).
                   When True, syntax errors in resources raise SyntaxIntegrityError
                   and formatting errors raise FormattingIntegrityError.
                   Set to False only for development or when soft error recovery
                   is explicitly required.

        Raises:
            ValueError: If locales is empty
            ValueError: If resource_ids provided but no resource_loader
        """
        locale_list = list(locales)
        if not locale_list:
            msg = "At least one locale is required"
            raise ValueError(msg)

        if resource_ids and not resource_loader:
            msg = "resource_loader required when resource_ids provided"
            raise ValueError(msg)

        # Canonicalize all locales eagerly (fail-fast pattern). dict.fromkeys()
        # removes duplicates while maintaining insertion order.
        validated_locales = [require_locale_code(locale, "locale") for locale in locale_list]
        self._locales = tuple(dict.fromkeys(validated_locales))

        # Precompute primary locale once: _locales is guaranteed non-empty (checked above)
        # and is immutable (tuple), so this value never changes after construction.
        self._primary_locale: LocaleCode = self._locales[0]

        self._resource_ids: tuple[ResourceId, ...] = tuple(resource_ids) if resource_ids else ()
        self._resource_loader: ResourceLoader | None = resource_loader
        self._use_isolating = use_isolating
        self._cache_config: CacheConfig | None = cache
        self._on_fallback = on_fallback
        self._strict = strict

        # Bundle storage: only contains initialized bundles (no None markers)
        # Bundles are created lazily on first access via _get_or_create_bundle
        # But resources are loaded eagerly at init time for fail-fast behavior
        self._bundles: dict[LocaleCode, FluentBundle] = {}

        # Track all load results for diagnostics
        self._load_results: list[ResourceLoadResult] = []

        # Pending functions: stored until bundle is created (lazy loading support)
        # Functions are applied to bundles when they are first accessed
        self._pending_functions: dict[str, Callable[..., FluentValue]] = {}

        # Thread safety: RWLock allows concurrent format_value/format_pattern
        # calls (readers) while serializing add_resource/add_function (writers).
        self._lock = RWLock()

        # Resource loading is EAGER by design:
        # - Fail-fast: Critical errors (parse, permission) raised at construction
        # - Predictable: All resource parse errors discovered immediately
        # - Trade-off: Slower initialization, but no runtime surprises
        # - Tracking: All load attempts recorded in _load_results for diagnostics
        # Note: Bundles are created eagerly for locales loaded here. Fallback locale
        #       bundles (not in this loop) are created lazily via _get_or_create_bundle.
        if resource_loader and resource_ids:
            for locale in self._locales:
                for resource_id in self._resource_ids:
                    result = self._load_single_resource(locale, resource_id, resource_loader)
                    self._load_results.append(result)

    @property
    def locales(self) -> tuple[LocaleCode, ...]:
        """Get immutable locale fallback chain.

        Returns:
            Tuple of locale codes in priority order
        """
        return self._locales

    @property
    def cache_enabled(self) -> bool:
        """Get whether format caching is enabled for all bundles (read-only).

        Returns:
            bool: True if caching is enabled, False otherwise

        Example:
            >>> from ftllexengine.runtime.cache_config import CacheConfig  # doctest: +SKIP
            >>> l10n = FluentLocalization(['lv', 'en'], cache=CacheConfig())  # doctest: +SKIP
            >>> l10n.cache_enabled  # doctest: +SKIP
            True
            >>> l10n_no_cache = FluentLocalization(['lv', 'en'])  # doctest: +SKIP
            >>> l10n_no_cache.cache_enabled  # doctest: +SKIP
            False
        """
        return self._cache_config is not None

    @property
    def cache_config(self) -> CacheConfig | None:
        """Get cache configuration (read-only).

        Returns:
            CacheConfig or None if caching is disabled.

        Example:
            >>> from ftllexengine.runtime.cache_config import CacheConfig  # doctest: +SKIP
            >>> l10n = FluentLocalization(  # doctest: +SKIP
            ...     ['lv', 'en'], cache=CacheConfig(size=500)
            ... )
            >>> l10n.cache_config.size  # doctest: +SKIP
            500
        """
        return self._cache_config

    @property
    def strict(self) -> bool:
        """Get whether strict mode is enabled (read-only).

        When strict mode is enabled, formatting errors and missing messages
        raise FormattingIntegrityError instead of returning fallback values.

        Returns:
            bool: True if strict mode is enabled, False otherwise
        """
        return self._strict

    def __repr__(self) -> str:
        """Return string representation for debugging.

        Returns:
            String representation showing locales and bundle count

        Example:
            >>> l10n = FluentLocalization(['lv', 'en'])  # doctest: +SKIP
            >>> repr(l10n)  # doctest: +SKIP
            "FluentLocalization(locales=('lv', 'en'), bundles=0/2)"
        """
        with self._lock.read():
            initialized = len(self._bundles)
        total = len(self._locales)
        return f"FluentLocalization(locales={self._locales!r}, bundles={initialized}/{total})"
