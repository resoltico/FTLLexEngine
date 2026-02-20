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

import time
from collections.abc import Callable, Generator, Iterable, Mapping
from typing import TYPE_CHECKING, NoReturn

from ftllexengine.constants import FALLBACK_INVALID, FALLBACK_MISSING_MESSAGE
from ftllexengine.diagnostics.codes import Diagnostic, DiagnosticCode
from ftllexengine.diagnostics.errors import ErrorCategory, FrozenFluentError
from ftllexengine.enums import LoadStatus
from ftllexengine.integrity import FormattingIntegrityError, IntegrityContext
from ftllexengine.localization.loading import (
    FallbackInfo,
    LoadSummary,
    ResourceLoader,
    ResourceLoadResult,
)
from ftllexengine.localization.types import FTLSource, LocaleCode, MessageId, ResourceId
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.cache_config import CacheConfig
from ftllexengine.runtime.rwlock import RWLock
from ftllexengine.runtime.value_types import FluentValue
from ftllexengine.syntax import Junk

if TYPE_CHECKING:
    from ftllexengine.diagnostics import ValidationResult
    from ftllexengine.introspection import MessageIntrospection

__all__ = ["FluentLocalization"]


class FluentLocalization:
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
        >>> loader = PathResourceLoader("locales/{locale}")
        >>> l10n = FluentLocalization(['lv', 'en'], ['ui.ftl'], loader)
        >>> result, errors = l10n.format_value('welcome', {'name': 'Anna'})
        # Tries 'lv' first, falls back to 'en' if message not found

    Example - Direct resource provision:
        >>> l10n = FluentLocalization(['lv', 'en'])
        >>> l10n.add_resource('lv', 'welcome = Sveiki, { $name }!')
        >>> l10n.add_resource('en', 'welcome = Hello, { $name }!')
        >>> result, errors = l10n.format_value('welcome', {'name': 'Anna'})
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
        "_modified_in_context",
        "_on_fallback",
        "_pending_functions",
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
        strict: bool = False,
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
            strict: Enable strict mode for fail-fast integrity (default: False).
                   When True, syntax errors in resources raise SyntaxIntegrityError
                   and formatting errors raise FormattingIntegrityError.
                   Financial applications should enable this for data integrity.

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

        # dict.fromkeys() removes duplicates while maintaining insertion order
        self._locales: tuple[LocaleCode, ...] = tuple(dict.fromkeys(locale_list))

        # Validate all locales eagerly (fail-fast pattern)
        # Prevents ValueError from leaking out of format_value during lazy bundle creation
        for locale in self._locales:
            FluentBundle._validate_locale_format(locale)

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

        # Context manager state tracking (cache invalidation optimization).
        # Mirrors FluentBundle's context manager semantics: cache is cleared
        # on __exit__ only if the localization was modified during the context.
        self._modified_in_context = False

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

    def _get_or_create_bundle(self, locale: LocaleCode) -> FluentBundle:
        """Get existing bundle or create one lazily.

        This implements lazy bundle initialization to reduce memory usage
        when fallback locales are rarely accessed.

        When a new bundle is created, any pending functions (registered via
        add_function before the bundle was accessed) are automatically applied.

        Thread-safe via double-checked locking: read lock for the common
        already-initialized case (allows concurrent format operations), write
        lock only when a new bundle must be created. Callers already holding
        the write lock (add_resource, add_function) use RWLock downgrading
        semantics: _acquire_read short-circuits via _writer_held_reads.

        Args:
            locale: Locale code (must be in _locales tuple)

        Returns:
            FluentBundle instance for the locale
        """
        # Fast path: read lock allows concurrent format operations once all
        # bundles are initialized. The write-lock-holder path (add_resource,
        # add_function) uses RWLock downgrading and is also safe here.
        with self._lock.read():
            if locale in self._bundles:
                return self._bundles[locale]

        # Slow path: bundle does not exist; acquire write lock and create it.
        # Double-check after acquiring write lock: another thread may have
        # created the bundle between our read-lock release and write-lock acquire.
        with self._lock.write():
            if locale in self._bundles:
                return self._bundles[locale]

            bundle = FluentBundle(
                locale,
                use_isolating=self._use_isolating,
                cache=self._cache_config,
                strict=self._strict,
            )
            # Apply any pending functions that were registered before bundle creation
            for name, func in self._pending_functions.items():
                bundle.add_function(name, func)
            self._bundles[locale] = bundle
            return bundle

    def _load_single_resource(
        self,
        locale: LocaleCode,
        resource_id: ResourceId,
        resource_loader: ResourceLoader,
    ) -> ResourceLoadResult:
        """Load a single FTL resource and record the result.

        Encapsulates the logic for loading one resource for one locale,
        including path construction, error handling, and result recording.

        Args:
            locale: Locale code to load resource for
            resource_id: Resource identifier (e.g., 'main.ftl')
            resource_loader: Loader implementation to use

        Returns:
            ResourceLoadResult indicating success, not_found, or error
        """
        # Delegate path description to loader via protocol method.
        # ResourceLoader.describe_path() returns a human-readable path string.
        # PathResourceLoader overrides this with the actual locale-substituted path.
        # Custom loaders use the default "{locale}/{resource_id}" implementation.
        source_path = resource_loader.describe_path(locale, resource_id)

        try:
            ftl_source = resource_loader.load(locale, resource_id)
            bundle = self._get_or_create_bundle(locale)
            junk_entries = bundle.add_resource(ftl_source, source_path=source_path)
            return ResourceLoadResult(
                locale=locale,
                resource_id=resource_id,
                status=LoadStatus.SUCCESS,
                source_path=source_path,
                junk_entries=junk_entries,
            )
        except FileNotFoundError:
            # Resource doesn't exist for this locale - expected for optional locales
            return ResourceLoadResult(
                locale=locale,
                resource_id=resource_id,
                status=LoadStatus.NOT_FOUND,
                source_path=source_path,
            )
        except (OSError, ValueError) as e:
            # Permission errors, path traversal errors, etc.
            return ResourceLoadResult(
                locale=locale,
                resource_id=resource_id,
                status=LoadStatus.ERROR,
                error=e,
                source_path=source_path,
            )

    @staticmethod
    def _check_mapping_arg(
        args: Mapping[str, FluentValue] | None,
        errors: list[FrozenFluentError],
    ) -> bool:
        """Validate that args is None or a Mapping (defensive runtime check).

        Callers annotate args as Mapping | None, but external callers may
        violate the contract at runtime. This static method provides the
        shared guard used by both format_value() and format_pattern().

        Args:
            args: The args argument from format_value or format_pattern
            errors: Mutable error list; an error is appended if args is invalid

        Returns:
            True if args is valid (None or Mapping), False otherwise
        """
        if args is not None and not isinstance(args, Mapping):
            diagnostic = Diagnostic(  # type: ignore[unreachable]
                code=DiagnosticCode.INVALID_ARGUMENT,
                message=f"Invalid args type: expected Mapping or None, got {type(args).__name__}",
            )
            errors.append(
                FrozenFluentError(
                    str(diagnostic), ErrorCategory.RESOLUTION, diagnostic=diagnostic
                )
            )
            return False
        return True

    @property
    def locales(self) -> tuple[LocaleCode, ...]:
        """Get immutable locale fallback chain.

        Returns:
            Tuple of locale codes in priority order
        """
        return self._locales

    def get_load_summary(self) -> LoadSummary:
        """Get summary of resource load attempts during initialization.

        Returns a LoadSummary with information about which resources loaded
        successfully, which were not found, and which failed with errors
        during the __init__() resource loading phase.

        IMPORTANT: This only reflects resources loaded via the ResourceLoader
        during construction. Resources added dynamically via add_resource()
        are NOT included in this summary. This maintains a clear semantic
        distinction between initialization-time (fail-fast) loading and
        runtime (dynamic) resource additions.

        Use this to diagnose loading issues, especially in multi-locale setups
        where some locales may have missing or broken resources.

        Returns:
            LoadSummary with aggregated load results from initialization

        Example:
            >>> loader = PathResourceLoader("locales/{locale}")
            >>> l10n = FluentLocalization(['en', 'de', 'fr'], ['ui.ftl'], loader)
            >>> summary = l10n.get_load_summary()
            >>> print(f"Loaded: {summary.successful}/{summary.total_attempted}")
            Loaded: 2/3
            >>> if summary.has_errors:
            ...     for result in summary.get_errors():
            ...         print(f"Error loading {result.source_path}: {result.error}")
            >>> for result in summary.get_not_found():
            ...     print(f"Missing: {result.locale}/{result.resource_id}")
        """
        return LoadSummary(results=tuple(self._load_results))

    @property
    def cache_enabled(self) -> bool:
        """Get whether format caching is enabled for all bundles (read-only).

        Returns:
            bool: True if caching is enabled, False otherwise

        Example:
            >>> from ftllexengine.runtime.cache_config import CacheConfig
            >>> l10n = FluentLocalization(['lv', 'en'], cache=CacheConfig())
            >>> l10n.cache_enabled
            True
            >>> l10n_no_cache = FluentLocalization(['lv', 'en'])
            >>> l10n_no_cache.cache_enabled
            False
        """
        return self._cache_config is not None

    @property
    def cache_config(self) -> CacheConfig | None:
        """Get cache configuration (read-only).

        Returns:
            CacheConfig or None if caching is disabled.

        Example:
            >>> from ftllexengine.runtime.cache_config import CacheConfig
            >>> l10n = FluentLocalization(['lv', 'en'], cache=CacheConfig(size=500))
            >>> l10n.cache_config.size
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
            >>> l10n = FluentLocalization(['lv', 'en'])
            >>> repr(l10n)
            "FluentLocalization(locales=('lv', 'en'), bundles=0/2)"
        """
        initialized = len(self._bundles)
        total = len(self._locales)
        return f"FluentLocalization(locales={self._locales!r}, bundles={initialized}/{total})"

    def add_resource(
        self, locale: LocaleCode, ftl_source: FTLSource
    ) -> tuple[Junk, ...]:
        """Add FTL resource to specific locale bundle.

        Allows dynamic resource loading without ResourceLoader.

        Thread-safe via internal RWLock.

        Args:
            locale: Locale code (must be in fallback chain, no leading/trailing whitespace)
            ftl_source: FTL source code

        Returns:
            Tuple of Junk entries encountered during parsing. Empty tuple if
            parsing succeeded without errors.

        Raises:
            ValueError: If locale not in fallback chain or contains whitespace.
        """
        stripped = locale.strip()
        if stripped != locale:
            msg = (
                f"Locale code contains leading/trailing whitespace: {locale!r}. "
                f"Stripped would be: {stripped!r}"
            )
            raise ValueError(msg)

        with self._lock.write():
            if locale not in self._locales:
                msg = f"Locale '{locale}' not in fallback chain {self._locales}"
                raise ValueError(msg)

            # _get_or_create_bundle uses double-checked locking: it first
            # acquires a read lock (downgrading from this write lock via
            # RWLock._writer_held_reads), then a write lock if needed (reentrant).
            bundle = self._get_or_create_bundle(locale)
            self._modified_in_context = True
            return bundle.add_resource(ftl_source)

    def _handle_message_not_found(
        self,
        message_id: MessageId,
        errors: list[FrozenFluentError],
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        """Handle message-not-found with consistent validation.

        Uses pattern matching to distinguish between empty/invalid message IDs
        and valid IDs that simply weren't found in any locale.

        In strict mode, raises FormattingIntegrityError instead of returning
        a fallback value. Financial applications must never silently display
        placeholder text like ``{message_id}`` to end users.

        Args:
            message_id: The message ID that was not found
            errors: Mutable error list to append to

        Returns:
            Tuple of (fallback_value, errors_tuple)

        Raises:
            FormattingIntegrityError: In strict mode, always raised
        """
        match message_id:
            case str() if message_id:
                # Valid but not found
                diagnostic = Diagnostic(
                    code=DiagnosticCode.MESSAGE_NOT_FOUND,
                    message=f"Message '{message_id}' not found in any locale",
                )
                error = FrozenFluentError(
                    str(diagnostic), ErrorCategory.REFERENCE, diagnostic=diagnostic
                )
                errors.append(error)
                fallback = FALLBACK_MISSING_MESSAGE.format(id=message_id)
            case _:
                # Empty or invalid message ID
                diagnostic = Diagnostic(
                    code=DiagnosticCode.MESSAGE_NOT_FOUND,
                    message="Empty or invalid message ID",
                )
                error = FrozenFluentError(
                    str(diagnostic), ErrorCategory.REFERENCE, diagnostic=diagnostic
                )
                errors.append(error)
                fallback = FALLBACK_INVALID

        errors_tuple = tuple(errors)

        if self._strict:
            self._raise_strict_error(message_id, fallback, error)

        return (fallback, errors_tuple)

    def _raise_strict_error(
        self,
        message_id: MessageId,
        fallback_value: str,
        error: FrozenFluentError,
    ) -> NoReturn:
        """Raise FormattingIntegrityError for strict mode.

        Called from _handle_message_not_found which produces exactly one
        error (message not found or invalid message ID).

        Args:
            message_id: The message ID that failed
            fallback_value: Value that would be returned in non-strict mode
            error: The FrozenFluentError describing the failure

        Raises:
            FormattingIntegrityError: Always raised with error details
        """
        context = IntegrityContext(
            component="localization",
            operation="format_pattern",
            key=str(message_id),
            expected="<no errors>",
            actual="<1 error>",
            timestamp=time.monotonic(),
        )

        msg = f"Strict mode: '{message_id}' failed: {error}"
        raise FormattingIntegrityError(
            msg,
            context=context,
            fluent_errors=(error,),
            fallback_value=fallback_value,
            message_id=str(message_id),
        )

    def format_value(
        self, message_id: MessageId, args: Mapping[str, FluentValue] | None = None
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        """Format message with fallback chain.

        Tries each locale in priority order until message is found.

        Args:
            message_id: Message identifier (e.g., 'welcome', 'error-404')
            args: Message arguments for variable interpolation

        Returns:
            Tuple of (formatted_value, errors)
            - If message found: Returns formatted result from first bundle with message
            - If not found: Returns ({message_id}, (error,))

        Raises:
            FormattingIntegrityError: In strict mode, raised when formatting
                produces errors or when the message is not found in any locale.

        Example:
            >>> l10n = FluentLocalization(['lv', 'en'])
            >>> l10n.add_resource('lv', 'welcome = Sveiki!')
            >>> l10n.add_resource('en', 'welcome = Hello!')
            >>> result, errors = l10n.format_value('welcome')
            >>> result
            'Sveiki!'
        """
        errors: list[FrozenFluentError] = []

        if not self._check_mapping_arg(args, errors):
            return (FALLBACK_INVALID, tuple(errors))

        primary_locale = self._locales[0] if self._locales else None

        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)

            if bundle.has_message(message_id):
                value, bundle_errors = bundle.format_pattern(message_id, args)
                errors.extend(bundle_errors)

                if (
                    self._on_fallback is not None
                    and primary_locale is not None
                    and locale != primary_locale
                ):
                    fallback_info = FallbackInfo(
                        requested_locale=primary_locale,
                        resolved_locale=locale,
                        message_id=message_id,
                    )
                    self._on_fallback(fallback_info)

                return (value, tuple(errors))

        return self._handle_message_not_found(message_id, errors)

    def has_message(self, message_id: MessageId) -> bool:
        """Check if message exists in any locale.

        Args:
            message_id: Message identifier

        Returns:
            True if message exists in at least one locale
        """
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            if bundle.has_message(message_id):
                return True
        return False

    def format_pattern(
        self,
        message_id: MessageId,
        args: Mapping[str, FluentValue] | None = None,
        *,
        attribute: str | None = None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        """Format message with attribute support (fallback chain).

        Extends format_value() with attribute access.

        Args:
            message_id: Message identifier
            args: Variable arguments
            attribute: Attribute name (e.g., "tooltip", "aria-label")

        Returns:
            Tuple of (formatted_value, errors)

        Raises:
            FormattingIntegrityError: In strict mode, raised when formatting
                produces errors or when the message is not found in any locale.

        Example:
            >>> l10n = FluentLocalization(['lv', 'en'])
            >>> l10n.add_resource('lv', '''
            ... button = Klikšķināt
            ...     .tooltip = Klikšķiniet, lai iesniegtu
            ... ''')
            >>> result, errors = l10n.format_pattern("button", attribute="tooltip")
            >>> result
            'Klikšķiniet, lai iesniegtu'
        """
        errors: list[FrozenFluentError] = []

        if not self._check_mapping_arg(args, errors):
            return (FALLBACK_INVALID, tuple(errors))

        # Validate attribute is None or a string
        if attribute is not None and not isinstance(attribute, str):
            attr_type = type(attribute).__name__  # type: ignore[unreachable]
            diagnostic = Diagnostic(
                code=DiagnosticCode.INVALID_ARGUMENT,
                message=f"Invalid attribute type: expected str or None, got {attr_type}",
            )
            errors.append(
                FrozenFluentError(
                    str(diagnostic), ErrorCategory.RESOLUTION, diagnostic=diagnostic
                )
            )
            return (FALLBACK_INVALID, tuple(errors))

        primary_locale = self._locales[0] if self._locales else None

        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)

            if bundle.has_message(message_id):
                value, bundle_errors = bundle.format_pattern(message_id, args, attribute=attribute)
                errors.extend(bundle_errors)

                if (
                    self._on_fallback is not None
                    and primary_locale is not None
                    and locale != primary_locale
                ):
                    fallback_info = FallbackInfo(
                        requested_locale=primary_locale,
                        resolved_locale=locale,
                        message_id=message_id,
                    )
                    self._on_fallback(fallback_info)

                return (value, tuple(errors))

        return self._handle_message_not_found(message_id, errors)

    def add_function(self, name: str, func: Callable[..., FluentValue]) -> None:
        """Register custom function on all bundles.

        Functions are applied immediately to any already-created bundles,
        and stored for deferred application to bundles created later.
        This preserves lazy bundle initialization.

        Thread-safe via internal RWLock.

        Args:
            name: Function name (UPPERCASE by convention)
            func: Python function implementation returning FluentValue

        Example:
            >>> l10n = FluentLocalization(['lv', 'en'])
            >>> def CUSTOM(value: str) -> str:
            ...     return value.upper()
            >>> l10n.add_function("CUSTOM", CUSTOM)
            >>> l10n.add_resource('en', 'msg = { CUSTOM($text) }')
            >>> result, _ = l10n.format_value('msg', {'text': 'hello'})
            >>> result
            'HELLO'
        """
        with self._lock.write():
            # Store for future bundle creation (lazy loading support)
            self._pending_functions[name] = func
            self._modified_in_context = True

            # Apply to any already-created bundles
            for bundle in self._bundles.values():
                bundle.add_function(name, func)

    def introspect_message(
        self,
        message_id: MessageId,
    ) -> MessageIntrospection | None:
        """Get message introspection from first bundle with message.

        Args:
            message_id: Message identifier

        Returns:
            MessageIntrospection or None if not found
        """
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            if bundle.has_message(message_id):
                return bundle.introspect_message(message_id)
        return None

    def has_attribute(
        self,
        message_id: MessageId,
        attribute: str,
    ) -> bool:
        """Check if message has specific attribute in any locale.

        Tries bundles in fallback order. Returns True if any bundle
        has the message AND the specified attribute.

        Args:
            message_id: Message identifier
            attribute: Attribute name

        Returns:
            True if attribute exists in at least one locale
        """
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            if bundle.has_attribute(message_id, attribute):
                return True
        return False

    def get_message_ids(self) -> list[str]:
        """Get all message IDs across all locales.

        Returns the union of message IDs from all bundles, ordered by
        first appearance in locale priority order. Primary locale IDs
        appear first.

        Returns:
            List of unique message identifiers
        """
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
        self,
        message_id: MessageId,
    ) -> frozenset[str]:
        """Get variables required by a message.

        Delegates to the first bundle in fallback order that has the
        message.

        Args:
            message_id: Message identifier

        Returns:
            Frozen set of variable names (without $ prefix)

        Raises:
            KeyError: If message not found in any locale
        """
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            if bundle.has_message(message_id):
                return bundle.get_message_variables(message_id)
        msg = f"Message '{message_id}' not found in any locale"
        raise KeyError(msg)

    def get_all_message_variables(self) -> dict[str, frozenset[str]]:
        """Get variables for all messages across all locales.

        Merges variables from all bundles. For messages present in
        multiple locales, the primary locale's variables take
        precedence (first-wins).

        Returns:
            Dictionary mapping message IDs to variable sets
        """
        result: dict[str, frozenset[str]] = {}
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            for msg_id, variables in bundle.get_all_message_variables().items():
                if msg_id not in result:
                    result[msg_id] = variables
        return result

    def introspect_term(
        self,
        term_id: str,
    ) -> MessageIntrospection | None:
        """Get term introspection from first bundle with term.

        Tries bundles in fallback order.

        Args:
            term_id: Term identifier (without leading dash)

        Returns:
            MessageIntrospection or None if not found
        """
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            try:
                return bundle.introspect_term(term_id)
            except KeyError:
                continue
        return None

    def __enter__(self) -> FluentLocalization:
        """Enter context manager for cache invalidation tracking.

        Clears all bundle caches on exit only if the localization was
        modified during the context (add_resource, add_function, or
        clear_cache called). For read-only operations, caches are
        preserved for better performance.

        Semantics match FluentBundle's context manager: both track
        modifications and conditionally clear caches on exit.

        Returns:
            Self (the FluentLocalization instance)

        Example:
            >>> with FluentLocalization(['en'], cache=CacheConfig()) as l10n:
            ...     l10n.add_resource('en', 'hello = Hello')
            ... # Caches cleared (localization was modified)
        """
        self._modified_in_context = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Exit context manager with conditional cache cleanup.

        Clears all bundle caches only if the localization was modified
        during the context. Does not suppress exceptions.

        Args:
            exc_type: Exception type (if any)
            exc_val: Exception value (if any)
            exc_tb: Exception traceback (if any)
        """
        if self._modified_in_context:
            with self._lock.write():
                for bundle in self._bundles.values():
                    bundle.clear_cache()
        self._modified_in_context = False

    def get_babel_locale(self) -> str:
        """Get Babel locale identifier from primary bundle.

        Returns Babel Locale for the first locale in fallback chain.
        Useful for integrating with Babel's formatting functions.

        Returns:
            Babel locale identifier

        Example:
            >>> l10n = FluentLocalization(['lv', 'en'])
            >>> locale = l10n.get_babel_locale()
            >>> locale
            'lv'
        """
        primary_locale = self._locales[0]
        bundle = self._get_or_create_bundle(primary_locale)
        return bundle.get_babel_locale()

    def validate_resource(self, ftl_source: FTLSource) -> ValidationResult:
        """Validate FTL resource without adding to bundles.

        Uses primary locale's bundle for validation.

        Args:
            ftl_source: FTL source code

        Returns:
            ValidationResult with errors and warnings

        Example:
            >>> l10n = FluentLocalization(['lv', 'en'])
            >>> result = l10n.validate_resource("msg = Hello")
            >>> result.is_valid
            True
        """
        primary_locale = self._locales[0]
        bundle = self._get_or_create_bundle(primary_locale)
        return bundle.validate_resource(ftl_source)

    def clear_cache(self) -> None:
        """Clear format cache on all initialized bundles.

        Calls clear_cache() on each bundle that has been created.
        Does not create new bundles.

        Thread-safe via internal RWLock.
        """
        with self._lock.write():
            self._modified_in_context = True
            for bundle in self._bundles.values():
                bundle.clear_cache()

    def get_cache_stats(self) -> dict[str, int | float | bool] | None:
        """Get aggregate cache statistics across all initialized bundles.

        Aggregates cache metrics from all bundles that have been created.
        Useful for production monitoring of multi-locale deployments.

        Returns:
            Dict with aggregated cache metrics, or None if caching disabled.
            Keys:
            - size (int): Total cached entries across all bundles
            - maxsize (int): Sum of maximum cache sizes
            - hits (int): Total cache hits
            - misses (int): Total cache misses
            - hit_rate (float): Weighted hit rate (0.0-100.0)
            - unhashable_skips (int): Total uncacheable argument skips
            - bundle_count (int): Number of initialized bundles

        Thread-safe via internal RWLock (read lock).

        Example:
            >>> l10n = FluentLocalization(['en', 'de'], cache=CacheConfig())
            >>> l10n.add_resource('en', 'msg = Hello')
            >>> l10n.add_resource('de', 'msg = Hallo')
            >>> l10n.format_value('msg')  # Uses 'en' bundle
            >>> stats = l10n.get_cache_stats()
            >>> stats["bundle_count"]
            2
            >>> stats["size"]  # Total entries across all bundles
            1
        """
        if self._cache_config is None:
            return None

        with self._lock.read():
            total_size = 0
            total_maxsize = 0
            total_hits = 0
            total_misses = 0
            total_unhashable = 0

            for bundle in self._bundles.values():
                stats = bundle.get_cache_stats()
                if stats is not None:
                    # Cast to int: these values are always int from FormatCache.get_stats()
                    total_size += int(stats["size"])
                    total_maxsize += int(stats["maxsize"])
                    total_hits += int(stats["hits"])
                    total_misses += int(stats["misses"])
                    total_unhashable += int(stats["unhashable_skips"])

            total_requests = total_hits + total_misses
            hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0.0

            return {
                "size": total_size,
                "maxsize": total_maxsize,
                "hits": total_hits,
                "misses": total_misses,
                "hit_rate": round(hit_rate, 2),
                "unhashable_skips": total_unhashable,
                "bundle_count": len(self._bundles),
            }

    def get_bundles(self) -> Generator[FluentBundle]:
        """Lazy generator yielding bundles in fallback order.

        Enables advanced use cases where direct bundle access is needed.
        Creates bundles lazily if they don't exist yet.

        Yields:
            FluentBundle instances in locale priority order
        """
        yield from (self._get_or_create_bundle(locale) for locale in self._locales)
