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
        if summary.error_count > 0:
            raise RuntimeError(f"Failed to load {summary.error_count} resources")

    Bundles are created eagerly for locales that have resources loaded during
    initialization. Fallback locale bundles (for locales not in the resource
    loading loop) are created lazily on first access. This hybrid approach
    balances comprehensive error collection with memory efficiency.

Python 3.13+.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Generator, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from .constants import DEFAULT_CACHE_SIZE, FALLBACK_INVALID, FALLBACK_MISSING_MESSAGE
from .diagnostics.codes import Diagnostic, DiagnosticCode
from .diagnostics.errors import ErrorCategory, FrozenFluentError
from .runtime.bundle import FluentBundle
from .runtime.function_bridge import FluentValue
from .syntax import Junk

if TYPE_CHECKING:
    from .diagnostics import ValidationResult
    from .introspection import MessageIntrospection

# Type aliases using Python 3.13 type keyword
type MessageId = str
type LocaleCode = str
type ResourceId = str
type FTLSource = str


class LoadStatus(StrEnum):
    """Status of a resource load attempt."""

    SUCCESS = "success"  # Resource loaded successfully
    NOT_FOUND = "not_found"  # Resource file not found (expected for optional locales)
    ERROR = "error"  # Resource load failed with error


@dataclass(frozen=True, slots=True)
class FallbackInfo:
    """Information about a locale fallback event.

    Provided to the on_fallback callback when FluentLocalization resolves
    a message using a fallback locale instead of the primary locale.

    Attributes:
        requested_locale: The primary (first) locale in the chain
        resolved_locale: The locale that actually contained the message
        message_id: The message identifier that was resolved

    Example:
        >>> def log_fallback(info: FallbackInfo) -> None:
        ...     print(f"Fallback: {info.message_id} resolved from "
        ...           f"{info.resolved_locale} (requested {info.requested_locale})")
        >>> l10n = FluentLocalization(['lv', 'en'], on_fallback=log_fallback)
    """

    requested_locale: LocaleCode
    resolved_locale: LocaleCode
    message_id: MessageId


@dataclass(frozen=True, slots=True)
class ResourceLoadResult:
    """Result of loading a single FTL resource.

    Tracks the outcome of loading a resource for a specific locale,
    including any errors encountered and any Junk entries from parsing.

    Attributes:
        locale: Locale code for this resource
        resource_id: Resource identifier (e.g., 'main.ftl')
        status: Load status (success, not_found, error)
        error: Exception if status is ERROR, None otherwise
        source_path: Full path to resource (if available)
        junk_entries: Junk entries from parsing (unparseable content)
    """

    locale: LocaleCode
    resource_id: ResourceId
    status: LoadStatus
    error: Exception | None = None
    source_path: str | None = None
    junk_entries: tuple[Junk, ...] = ()

    @property
    def is_success(self) -> bool:
        """Check if resource loaded successfully."""
        return self.status == LoadStatus.SUCCESS

    @property
    def is_not_found(self) -> bool:
        """Check if resource was not found (expected for optional locales)."""
        return self.status == LoadStatus.NOT_FOUND

    @property
    def is_error(self) -> bool:
        """Check if resource load failed with an error."""
        return self.status == LoadStatus.ERROR

    @property
    def has_junk(self) -> bool:
        """Check if resource had unparseable content (Junk entries)."""
        return len(self.junk_entries) > 0


@dataclass(frozen=True, slots=True)
class LoadSummary:
    """Summary of all resource load attempts during initialization.

    Provides aggregated information about resource loading success/failure
    across all locales. Use this to diagnose missing resources or loading errors.

    Attributes:
        results: All individual load results
        total_attempted: Total number of load attempts
        successful: Number of successful loads
        not_found: Number of resources not found
        errors: Number of load errors
        junk_count: Total number of Junk entries across all resources

    Example:
        >>> l10n = FluentLocalization(['en', 'de'], ['ui.ftl'], loader)
        >>> summary = l10n.get_load_summary()
        >>> if summary.errors > 0:
        ...     for result in summary.get_errors():
        ...         print(f"Failed: {result.locale}/{result.resource_id}: {result.error}")
        >>> if summary.has_junk:
        ...     for result in summary.get_with_junk():
        ...         print(f"Junk in {result.source_path}: {len(result.junk_entries)} entries")
    """

    results: tuple[ResourceLoadResult, ...]
    total_attempted: int = field(init=False)
    successful: int = field(init=False)
    not_found: int = field(init=False)
    errors: int = field(init=False)
    junk_count: int = field(init=False)

    def __post_init__(self) -> None:
        """Calculate summary statistics."""
        # Use object.__setattr__ because this is a frozen dataclass
        object.__setattr__(self, "total_attempted", len(self.results))
        object.__setattr__(
            self, "successful", sum(1 for r in self.results if r.is_success)
        )
        object.__setattr__(
            self, "not_found", sum(1 for r in self.results if r.is_not_found)
        )
        object.__setattr__(self, "errors", sum(1 for r in self.results if r.is_error))
        object.__setattr__(
            self, "junk_count", sum(len(r.junk_entries) for r in self.results)
        )

    def get_errors(self) -> tuple[ResourceLoadResult, ...]:
        """Get all results with errors."""
        return tuple(r for r in self.results if r.is_error)

    def get_not_found(self) -> tuple[ResourceLoadResult, ...]:
        """Get all results where resource was not found."""
        return tuple(r for r in self.results if r.is_not_found)

    def get_successful(self) -> tuple[ResourceLoadResult, ...]:
        """Get all successful load results."""
        return tuple(r for r in self.results if r.is_success)

    def get_by_locale(self, locale: LocaleCode) -> tuple[ResourceLoadResult, ...]:
        """Get all results for a specific locale."""
        return tuple(r for r in self.results if r.locale == locale)

    def get_with_junk(self) -> tuple[ResourceLoadResult, ...]:
        """Get all results with Junk entries (unparseable content)."""
        return tuple(r for r in self.results if r.has_junk)

    def get_all_junk(self) -> tuple[Junk, ...]:
        """Get all Junk entries across all resources.

        Returns:
            Flattened tuple of all Junk entries from all resources.
        """
        junk_list: list[Junk] = []
        for result in self.results:
            junk_list.extend(result.junk_entries)
        return tuple(junk_list)

    @property
    def has_errors(self) -> bool:
        """Check if any resources failed to load with errors."""
        return self.errors > 0

    @property
    def has_junk(self) -> bool:
        """Check if any resources had Junk entries (unparseable content)."""
        return self.junk_count > 0

    @property
    def all_successful(self) -> bool:
        """Check if all attempted resources loaded successfully.

        Success means no I/O errors and all files were found. Resources with
        Junk entries (unparseable content) are still considered "successful"
        because the parse operation completed.

        For stricter validation that also checks for Junk, use all_clean.

        Returns:
            True if errors == 0 and not_found == 0, regardless of junk_count
        """
        return self.errors == 0 and self.not_found == 0

    @property
    def all_clean(self) -> bool:
        """Check if all resources loaded successfully without any Junk entries.

        Stricter than all_successful: requires no errors, all files found,
        AND zero Junk entries. Use this for validation workflows where
        unparseable content should be treated as a failure.

        Returns:
            True if errors == 0 and not_found == 0 and junk_count == 0
        """
        return self.errors == 0 and self.not_found == 0 and self.junk_count == 0


class ResourceLoader(Protocol):
    """Protocol for loading FTL resources for specific locales.

    Implementations must provide a load() method that retrieves FTL source
    for a given locale and resource identifier.

    This is a Protocol (structural typing) rather than ABC to allow
    maximum flexibility for users implementing custom loaders.

    Example:
        >>> class DiskLoader:
        ...     def load(self, locale: str, resource_id: str) -> str:
        ...         path = Path(f"locales/{locale}/{resource_id}")
        ...         return path.read_text(encoding="utf-8")
        ...
        >>> loader = DiskLoader()
        >>> l10n = FluentLocalization(['en', 'fr'], ['main.ftl'], loader)
    """

    def load(self, locale: LocaleCode, resource_id: ResourceId) -> FTLSource:
        """Load FTL resource for given locale.

        Args:
            locale: Locale code (e.g., 'en', 'fr', 'lv')
            resource_id: Resource identifier (e.g., 'main.ftl', 'errors.ftl')

        Returns:
            FTL source code as string

        Raises:
            FileNotFoundError: If resource doesn't exist for this locale
            OSError: If file cannot be read
        """


@dataclass(frozen=True, slots=True)
class PathResourceLoader:
    """File system resource loader using path templates.

    Implements ResourceLoader protocol for loading FTL files from disk.
    Uses {locale} placeholder in path template for locale substitution.

    Uses Python 3.13 frozen dataclass with slots for low memory overhead.

    Security:
        Validates both locale and resource_id to prevent directory traversal attacks.
        Locale codes containing path separators or ".." are rejected.
        Resource IDs containing ".." or absolute paths are rejected.
        All resolved paths are validated against a fixed root directory.

    Example:
        >>> loader = PathResourceLoader("locales/{locale}")
        >>> ftl = loader.load("en", "main.ftl")
        # Loads from: locales/en/main.ftl

    Attributes:
        base_path: Path template with {locale} placeholder
        root_dir: Fixed root directory for path traversal validation.
                  Defaults to parent of base_path if not specified.
    """

    base_path: str
    root_dir: str | None = None
    _resolved_root: Path = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """Cache resolved root directory and validate template at initialization.

        Raises:
            ValueError: If base_path does not contain {locale} placeholder
        """
        # Fail-fast validation: Require {locale} placeholder in path template
        # Without this placeholder, all locales would load from the same path,
        # causing silent data corruption where wrong locale files are loaded.
        if "{locale}" not in self.base_path:
            msg = (
                f"base_path must contain '{{locale}}' placeholder for locale substitution, "
                f"got: '{self.base_path}'"
            )
            raise ValueError(msg)

        if self.root_dir is not None:
            resolved = Path(self.root_dir).resolve()
        else:
            # Extract static prefix from base_path template
            # e.g., "locales/{locale}" -> "locales"
            # Note: split() always returns non-empty list, so template_parts[0] always exists
            template_parts = self.base_path.split("{locale}")
            static_prefix = template_parts[0].rstrip("/\\")
            resolved = Path(static_prefix).resolve() if static_prefix else Path.cwd().resolve()
        object.__setattr__(self, "_resolved_root", resolved)

    @staticmethod
    def _validate_locale(locale: LocaleCode) -> None:
        """Validate locale code for path traversal attacks.

        Args:
            locale: Locale code to validate

        Raises:
            ValueError: If locale contains unsafe path components
        """
        # Reject path traversal sequences
        if ".." in locale:
            msg = f"Path traversal sequences not allowed in locale: '{locale}'"
            raise ValueError(msg)

        # Reject path separators
        if "/" in locale or "\\" in locale:
            msg = f"Path separators not allowed in locale: '{locale}'"
            raise ValueError(msg)

        # Reject empty locale
        if not locale:
            msg = "Locale code cannot be empty"
            raise ValueError(msg)

    def load(self, locale: LocaleCode, resource_id: ResourceId) -> FTLSource:
        """Load FTL file from disk.

        Args:
            locale: Locale code to substitute in path template
            resource_id: FTL filename (e.g., 'main.ftl')

        Returns:
            FTL source code

        Raises:
            ValueError: If locale or resource_id contains path traversal sequences
            FileNotFoundError: If file doesn't exist
            OSError: If file cannot be read

        Security:
            Validates both locale and resource_id to prevent directory traversal.
            All resolved paths are verified against a fixed root directory.
        """
        # Security: Validate locale against path traversal attacks
        self._validate_locale(locale)

        # Security: Validate resource_id against path traversal attacks
        self._validate_resource_id(resource_id)

        # Use cached root directory (cannot be influenced by locale)

        # Substitute {locale} in path template
        # Use replace() instead of format() to avoid KeyError if template
        # contains other braces like "{version}" for future extensibility
        locale_path = self.base_path.replace("{locale}", locale)
        base_dir = Path(locale_path).resolve()
        full_path = (base_dir / resource_id).resolve()

        # Security: Verify resolved path is within FIXED root directory
        # This prevents locale manipulation from escaping the intended directory
        if not self._is_safe_path(self._resolved_root, full_path):
            msg = (
                f"Path traversal detected: resolved path escapes root directory. "
                f"locale='{locale}', resource_id='{resource_id}'"
            )
            raise ValueError(msg)

        return full_path.read_text(encoding="utf-8")

    @staticmethod
    def _validate_resource_id(resource_id: ResourceId) -> None:
        """Validate resource_id for path traversal attacks and whitespace.

        Args:
            resource_id: Resource identifier to validate

        Raises:
            ValueError: If resource_id contains unsafe path components or
                       leading/trailing whitespace
        """
        # Reject leading/trailing whitespace (common source of path bugs)
        # Explicit rejection ensures fail-fast behavior for copy-paste errors
        stripped = resource_id.strip()
        if stripped != resource_id:
            msg = (
                f"Resource ID contains leading/trailing whitespace: {resource_id!r}. "
                f"Stripped would be: {stripped!r}"
            )
            raise ValueError(msg)

        # Reject absolute paths
        if Path(resource_id).is_absolute():
            msg = f"Absolute paths not allowed in resource_id: '{resource_id}'"
            raise ValueError(msg)

        # Reject parent directory references
        if ".." in resource_id:
            msg = f"Path traversal sequences not allowed in resource_id: '{resource_id}'"
            raise ValueError(msg)

        # Reject paths starting with / or \
        if resource_id.startswith(("/", "\\")):
            msg = f"Resource ID must not start with path separator: '{resource_id}'"
            raise ValueError(msg)

    @staticmethod
    def _is_safe_path(base_dir: Path, full_path: Path) -> bool:
        """Check if full_path is safely within base_dir.

        Security Note:
            Explicitly resolves both paths before comparison to prevent
            path manipulation attacks. This follows defense-in-depth:
            even if caller provides un-resolved paths, this method
            canonicalizes them before the security check.

        Args:
            base_dir: Base directory (will be resolved)
            full_path: Full path to check (will be resolved)

        Returns:
            True if resolved full_path is within resolved base_dir
        """
        try:
            # Defense-in-depth: resolve() both paths to canonicalize
            # This follows symlinks and normalizes path components
            resolved_base = base_dir.resolve()
            resolved_path = full_path.resolve()

            # Python 3.9+ method - check if full_path is relative to base_dir
            resolved_path.relative_to(resolved_base)
            return True
        except ValueError:
            # full_path is not within base_dir
            return False


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
        >>> result = l10n.format_value('welcome', {'name': 'Anna'})
        # Tries 'lv' first, falls back to 'en' if message not found

    Example - Direct resource provision:
        >>> l10n = FluentLocalization(['lv', 'en'])
        >>> l10n.add_resource('lv', 'welcome = Sveiki, { $name }!')
        >>> l10n.add_resource('en', 'welcome = Hello, { $name }!')
        >>> result = l10n.format_value('welcome', {'name': 'Anna'})
        # Returns: ('Sveiki, Anna!', ())

    Attributes:
        locales: Immutable tuple of locale codes in fallback priority order
    """

    __slots__ = (
        "_bundles",
        "_cache_size",
        "_enable_cache",
        "_load_results",
        "_locales",
        "_lock",
        "_on_fallback",
        "_pending_functions",
        "_resource_ids",
        "_resource_loader",
        "_resources_loaded",
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
        enable_cache: bool = False,
        cache_size: int = DEFAULT_CACHE_SIZE,
        on_fallback: Callable[[FallbackInfo], None] | None = None,
        strict: bool = False,
    ) -> None:
        """Initialize multi-locale localization.

        Args:
            locales: Locale codes in fallback order (e.g., ['lv', 'en', 'lt'])
            resource_ids: FTL file identifiers to load (e.g., ['ui.ftl', 'errors.ftl'])
            resource_loader: Loader for fetching FTL resources (optional)
            use_isolating: Wrap placeables in Unicode bidi isolation marks
            enable_cache: Enable format caching for performance (default: False)
                         Cache provides 50x speedup on repeated format calls.
            cache_size: Maximum cache entries when caching enabled (default: DEFAULT_CACHE_SIZE)
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
        # Validate inputs
        locale_list = list(locales)
        if not locale_list:
            msg = "At least one locale is required"
            raise ValueError(msg)

        if resource_ids and not resource_loader:
            msg = "resource_loader required when resource_ids provided"
            raise ValueError(msg)

        # Store immutable locale chain with deduplication (preserves order)
        # dict.fromkeys() removes duplicates while maintaining insertion order
        self._locales: tuple[LocaleCode, ...] = tuple(dict.fromkeys(locale_list))

        # Validate all locales eagerly (fail-fast pattern)
        # Prevents ValueError from leaking out of format_value during lazy bundle creation
        for locale in self._locales:
            FluentBundle._validate_locale_format(locale)

        self._resource_ids: tuple[ResourceId, ...] = tuple(resource_ids) if resource_ids else ()
        self._resource_loader: ResourceLoader | None = resource_loader
        self._use_isolating = use_isolating
        self._enable_cache = enable_cache
        self._cache_size = cache_size
        self._on_fallback = on_fallback
        self._strict = strict

        # Bundle storage: only contains initialized bundles (no None markers)
        # Bundles are created lazily on first access via _get_or_create_bundle
        # But resources are loaded eagerly at init time for fail-fast behavior
        self._bundles: dict[LocaleCode, FluentBundle] = {}

        # Track which locales have had resources loaded
        self._resources_loaded: set[LocaleCode] = set()

        # Track all load results for diagnostics
        self._load_results: list[ResourceLoadResult] = []

        # Pending functions: stored until bundle is created (lazy loading support)
        # Functions are applied to bundles when they are first accessed
        self._pending_functions: dict[str, Callable[..., FluentValue]] = {}

        # Thread safety: always enabled via RLock
        self._lock = threading.RLock()

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

        Thread-safe via internal RLock.

        Args:
            locale: Locale code (must be in _locales tuple)

        Returns:
            FluentBundle instance for the locale
        """
        with self._lock:
            if locale in self._bundles:
                return self._bundles[locale]

            # Create new bundle
            bundle = FluentBundle(
                locale,
                use_isolating=self._use_isolating,
                enable_cache=self._enable_cache,
                cache_size=self._cache_size,
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
        # Construct source path for diagnostics
        if isinstance(resource_loader, PathResourceLoader):
            locale_path = resource_loader.base_path.replace("{locale}", locale)
            source_path = f"{locale_path}/{resource_id}"
        else:
            source_path = f"{locale}/{resource_id}"

        try:
            ftl_source = resource_loader.load(locale, resource_id)
            bundle = self._get_or_create_bundle(locale)
            junk_entries = bundle.add_resource(ftl_source, source_path=source_path)
            self._resources_loaded.add(locale)
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
            >>> l10n = FluentLocalization(['lv', 'en'], enable_cache=True)
            >>> l10n.cache_enabled
            True
            >>> l10n_no_cache = FluentLocalization(['lv', 'en'])
            >>> l10n_no_cache.cache_enabled
            False
        """
        return self._enable_cache

    @property
    def cache_size(self) -> int:
        """Get maximum cache size per bundle (read-only).

        Returns:
            int: Configured maximum cache entries per bundle

        Example:
            >>> l10n = FluentLocalization(['lv', 'en'], enable_cache=True, cache_size=500)
            >>> l10n.cache_size
            500
            >>> # Cache size is returned even when caching is disabled
            >>> l10n_no_cache = FluentLocalization(['lv', 'en'], cache_size=200)
            >>> l10n_no_cache.cache_size
            200
            >>> l10n_no_cache.cache_enabled
            False

        Note:
            Returns configured size per bundle, not total across all bundles.
            Use cache_enabled to check if caching is active.
        """
        return self._cache_size

    def __repr__(self) -> str:
        """Return string representation for debugging.


        Returns:
            String representation showing locales and resource count

        Example:
            >>> l10n = FluentLocalization(['lv', 'en'])
            >>> repr(l10n)
            "FluentLocalization(locales=('lv', 'en'), bundles=2)"
        """
        # Count initialized bundles vs total locales
        initialized = len(self._bundles)
        total = len(self._locales)
        return f"FluentLocalization(locales={self._locales!r}, bundles={initialized}/{total})"

    def add_resource(
        self, locale: LocaleCode, ftl_source: FTLSource
    ) -> tuple[Junk, ...]:
        """Add FTL resource to specific locale bundle.

        Allows dynamic resource loading without ResourceLoader.

        Thread-safe via internal RLock.

        Args:
            locale: Locale code (must be in fallback chain, no leading/trailing whitespace)
            ftl_source: FTL source code

        Returns:
            Tuple of Junk entries encountered during parsing. Empty tuple if
            parsing succeeded without errors.

        Raises:
            ValueError: If locale not in fallback chain or contains whitespace.
        """
        # Validate locale for leading/trailing whitespace (fail-fast)
        stripped = locale.strip()
        if stripped != locale:
            msg = (
                f"Locale code contains leading/trailing whitespace: {locale!r}. "
                f"Stripped would be: {stripped!r}"
            )
            raise ValueError(msg)

        with self._lock:
            if locale not in self._locales:
                msg = f"Locale '{locale}' not in fallback chain {self._locales}"
                raise ValueError(msg)

            bundle = self._get_or_create_bundle(locale)
            return bundle.add_resource(ftl_source)

    def _handle_message_not_found(
        self,
        message_id: MessageId,
        errors: list[FrozenFluentError],
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        """Handle message-not-found with consistent validation.

        Uses pattern matching to distinguish between empty/invalid message IDs
        and valid IDs that simply weren't found in any locale.

        Args:
            message_id: The message ID that was not found
            errors: Mutable error list to append to

        Returns:
            Tuple of (fallback_value, errors_tuple)
        """
        match message_id:
            case str() if message_id:
                # Valid but not found - return ID wrapped in braces (Fluent convention)
                diagnostic = Diagnostic(
                    code=DiagnosticCode.MESSAGE_NOT_FOUND,
                    message=f"Message '{message_id}' not found in any locale",
                )
                error = FrozenFluentError(
                    str(diagnostic), ErrorCategory.REFERENCE, diagnostic=diagnostic
                )
                errors.append(error)
                return (FALLBACK_MISSING_MESSAGE.format(id=message_id), tuple(errors))
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
                return (FALLBACK_INVALID, tuple(errors))

    def format_value(
        self, message_id: MessageId, args: Mapping[str, FluentValue] | None = None
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        """Format message with fallback chain.

        Tries each locale in priority order until message is found.
        Uses Python 3.13 pattern matching for elegant fallback logic.

        Args:
            message_id: Message identifier (e.g., 'welcome', 'error-404')
            args: Message arguments for variable interpolation

        Returns:
            Tuple of (formatted_value, errors)
            - If message found: Returns formatted result from first bundle with message
            - If not found: Returns ({message_id}, (error,))

        Example:
            >>> l10n = FluentLocalization(['lv', 'en'])
            >>> l10n.add_resource('lv', 'welcome = Sveiki!')
            >>> l10n.add_resource('en', 'welcome = Hello!')
            >>> result, errors = l10n.format_value('welcome')
            >>> result
            'Sveiki!'
        """
        errors: list[FrozenFluentError] = []

        # Validate args is None or a Mapping (defensive check)
        if args is not None and not isinstance(args, Mapping):
            diagnostic = Diagnostic(  # type: ignore[unreachable]
                code=DiagnosticCode.INVALID_ARGUMENT,
                message=f"Invalid args type: expected Mapping or None, got {type(args).__name__}",
            )
            errors.append(
                FrozenFluentError(str(diagnostic), ErrorCategory.RESOLUTION, diagnostic=diagnostic)
            )
            return (FALLBACK_INVALID, tuple(errors))

        primary_locale = self._locales[0] if self._locales else None

        # Try each locale in priority order (fallback chain)
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)

            # Check if this bundle has the message
            if bundle.has_message(message_id):
                # Message exists in this locale - format it
                value, bundle_errors = bundle.format_pattern(message_id, args)
                # FluentBundle.format_pattern returns tuple[FluentError, ...]
                errors.extend(bundle_errors)

                # Invoke fallback callback if message resolved from non-primary locale
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

        # No locale had the message - delegate to helper for consistent handling
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

        # Validate args is None or a Mapping (defensive check)
        if args is not None and not isinstance(args, Mapping):
            diagnostic = Diagnostic(  # type: ignore[unreachable]
                code=DiagnosticCode.INVALID_ARGUMENT,
                message=f"Invalid args type: expected Mapping or None, got {type(args).__name__}",
            )
            errors.append(
                FrozenFluentError(str(diagnostic), ErrorCategory.RESOLUTION, diagnostic=diagnostic)
            )
            return (FALLBACK_INVALID, tuple(errors))

        # Validate attribute is None or a string
        if attribute is not None and not isinstance(attribute, str):
            attr_type = type(attribute).__name__  # type: ignore[unreachable]
            diagnostic = Diagnostic(
                code=DiagnosticCode.INVALID_ARGUMENT,
                message=f"Invalid attribute type: expected str or None, got {attr_type}",
            )
            errors.append(
                FrozenFluentError(str(diagnostic), ErrorCategory.RESOLUTION, diagnostic=diagnostic)
            )
            return (FALLBACK_INVALID, tuple(errors))

        primary_locale = self._locales[0] if self._locales else None

        # Try each locale in fallback order
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)

            if bundle.has_message(message_id):
                value, bundle_errors = bundle.format_pattern(message_id, args, attribute=attribute)
                errors.extend(bundle_errors)

                # Invoke fallback callback if message resolved from non-primary locale
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

        # Not found - delegate to helper for consistent handling
        return self._handle_message_not_found(message_id, errors)

    def add_function(self, name: str, func: Callable[..., FluentValue]) -> None:
        """Register custom function on all bundles.

        Functions are applied immediately to any already-created bundles,
        and stored for deferred application to bundles created later.
        This preserves lazy bundle initialization.

        Thread-safe via internal RLock.

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
        with self._lock:
            # Store for future bundle creation (lazy loading support)
            self._pending_functions[name] = func

            # Apply to any already-created bundles
            for bundle in self._bundles.values():
                bundle.add_function(name, func)

    def introspect_message(self, message_id: MessageId) -> MessageIntrospection | None:
        """Get message introspection from first bundle with message.

        Args:
            message_id: Message identifier

        Returns:
            MessageIntrospection or None if not found

        Example:
            >>> l10n = FluentLocalization(['lv', 'en'])
            >>> l10n.add_resource('en', 'msg = { $name } has { $count } items')
            >>> info = l10n.introspect_message('msg')
            >>> info.get_variable_names() if info else set()
            frozenset({'name', 'count'})
        """
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            if bundle.has_message(message_id):
                return bundle.introspect_message(message_id)
        return None

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

        Thread-safe via internal RLock.
        """
        with self._lock:
            for bundle in self._bundles.values():
                bundle.clear_cache()

    def get_cache_stats(self) -> dict[str, int | float] | None:
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

        Thread-safe via internal RLock.

        Example:
            >>> l10n = FluentLocalization(['en', 'de'], enable_cache=True)
            >>> l10n.add_resource('en', 'msg = Hello')
            >>> l10n.add_resource('de', 'msg = Hallo')
            >>> l10n.format_value('msg')  # Uses 'en' bundle
            >>> stats = l10n.get_cache_stats()
            >>> stats["bundle_count"]
            2
            >>> stats["size"]  # Total entries across all bundles
            1
        """
        if not self._enable_cache:
            return None

        with self._lock:
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


# ruff: noqa: RUF022 - __all__ organized by category for readability, not alphabetically
__all__ = [
    # Main classes
    "FluentLocalization",
    "PathResourceLoader",
    "ResourceLoader",
    # Load tracking (eager loading diagnostics)
    "LoadStatus",
    "LoadSummary",
    "ResourceLoadResult",
    # Fallback observability
    "FallbackInfo",
    # Type aliases for user code type annotations
    "MessageId",
    "LocaleCode",
    "ResourceId",
    "FTLSource",
]
