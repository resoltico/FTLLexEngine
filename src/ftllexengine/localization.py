"""Multi-locale orchestration with fallback chains.

Implements FluentLocalization following Mozilla's python-fluent architecture.
Separates multi-locale orchestration (FluentLocalization) from single-locale
formatting (FluentBundle).

Key architectural decisions:
- Lazy bundle creation: FluentBundle objects created on first access
- Eager resource loading: FTL resources loaded at init (fail-fast behavior)
- Protocol-based ResourceLoader (dependency inversion)
- Immutable locale chain (established at construction)
- Python 3.13 features: pattern matching, TypeIs, frozen dataclasses

Initialization Behavior:
    FluentLocalization loads all resources eagerly at construction to
    provide fail-fast error detection. This means FileNotFoundError and
    parse errors are raised immediately rather than during format() calls.
    Bundle objects are still created lazily to reduce memory when fallback
    locales are rarely accessed.

Python 3.13+.
"""

from collections.abc import Callable, Generator, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from .diagnostics.codes import Diagnostic, DiagnosticCode
from .diagnostics.errors import FluentError
from .runtime.bundle import DEFAULT_CACHE_SIZE, FluentBundle
from .runtime.resolver import FluentValue

if TYPE_CHECKING:
    from .diagnostics import ValidationResult
    from .introspection import MessageIntrospection

# Type aliases using Python 3.13 type keyword
type MessageId = str
type LocaleCode = str
type ResourceId = str
type FTLSource = str


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

    def _get_root_dir(self) -> Path:
        """Get the fixed root directory for path validation.

        Returns:
            Resolved root directory Path.
            If root_dir was specified, returns that.
            Otherwise, extracts the static prefix from base_path (before {locale}).
        """
        if self.root_dir is not None:
            return Path(self.root_dir).resolve()

        # Extract static prefix from base_path template
        # e.g., "locales/{locale}" -> "locales"
        # e.g., "/app/locales/{locale}/messages" -> "/app/locales"
        template_parts = self.base_path.split("{locale}")
        if template_parts:
            static_prefix = template_parts[0].rstrip("/\\")
            if static_prefix:
                return Path(static_prefix).resolve()

        # Fallback to current directory if no static prefix
        return Path.cwd().resolve()

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

        # Get fixed root directory (cannot be influenced by locale)
        root_dir = self._get_root_dir()

        # Substitute {locale} in path template
        locale_path = self.base_path.format(locale=locale)
        base_dir = Path(locale_path).resolve()
        full_path = (base_dir / resource_id).resolve()

        # Security: Verify resolved path is within FIXED root directory
        # This prevents locale manipulation from escaping the intended directory
        if not self._is_safe_path(root_dir, full_path):
            msg = (
                f"Path traversal detected: resolved path escapes root directory. "
                f"locale='{locale}', resource_id='{resource_id}'"
            )
            raise ValueError(msg)

        return full_path.read_text(encoding="utf-8")

    @staticmethod
    def _validate_resource_id(resource_id: ResourceId) -> None:
        """Validate resource_id for path traversal attacks.

        Args:
            resource_id: Resource identifier to validate

        Raises:
            ValueError: If resource_id contains unsafe path components
        """
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

        Args:
            base_dir: Base directory (resolved)
            full_path: Full path to check (resolved)

        Returns:
            True if full_path is within base_dir, False otherwise
        """
        try:
            # Python 3.9+ method - check if full_path is relative to base_dir
            full_path.relative_to(base_dir)
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
        "_locales",
        "_resource_ids",
        "_resource_loader",
        "_resources_loaded",
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

        # Store immutable locale chain
        self._locales: tuple[LocaleCode, ...] = tuple(locale_list)
        self._resource_ids: tuple[ResourceId, ...] = tuple(resource_ids) if resource_ids else ()
        self._resource_loader: ResourceLoader | None = resource_loader
        self._use_isolating = use_isolating
        self._enable_cache = enable_cache
        self._cache_size = cache_size

        # Bundle storage: bundles are created lazily on first access
        # But resources are loaded eagerly at init time for fail-fast behavior
        self._bundles: dict[LocaleCode, FluentBundle | None] = dict.fromkeys(
            self._locales, None
        )

        # Track which locales have had resources loaded
        self._resources_loaded: set[LocaleCode] = set()

        # Resource loading is EAGER by design:
        # - Fail-fast: FileNotFoundError raised at construction, not at format() time
        # - Predictable: All resource parse errors discovered immediately
        # - Trade-off: Slower initialization, but no runtime surprises
        # Note: Bundle objects themselves are still lazily created via _get_or_create_bundle
        if resource_loader and resource_ids:
            for locale in self._locales:
                for resource_id in self._resource_ids:
                    try:
                        ftl_source = resource_loader.load(locale, resource_id)
                        bundle = self._get_or_create_bundle(locale)
                        # Construct source path for better error messages
                        # If loader is PathResourceLoader, use its base_path
                        if isinstance(resource_loader, PathResourceLoader):
                            locale_path = resource_loader.base_path.format(locale=locale)
                            source_path = f"{locale_path}/{resource_id}"
                        else:
                            source_path = f"{locale}/{resource_id}"
                        bundle.add_resource(ftl_source, source_path=source_path)
                        self._resources_loaded.add(locale)
                    except FileNotFoundError:
                        # Resource doesn't exist for this locale - skip it
                        # Fallback will try next locale in chain
                        continue

    def _get_or_create_bundle(self, locale: LocaleCode) -> FluentBundle:
        """Get existing bundle or create one lazily.

        This implements lazy bundle initialization to reduce memory usage
        when fallback locales are rarely accessed.

        Args:
            locale: Locale code (must be in _bundles dict)

        Returns:
            FluentBundle instance for the locale
        """
        bundle = self._bundles[locale]
        if bundle is None:
            bundle = FluentBundle(
                locale,
                use_isolating=self._use_isolating,
                enable_cache=self._enable_cache,
                cache_size=self._cache_size,
            )
            self._bundles[locale] = bundle
        return bundle

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
            int: Maximum cache entries per bundle (0 if caching disabled)

        Example:
            >>> l10n = FluentLocalization(['lv', 'en'], enable_cache=True, cache_size=500)
            >>> l10n.cache_size
            500
            >>> l10n_no_cache = FluentLocalization(['lv', 'en'])
            >>> l10n_no_cache.cache_size
            0

        Note:
            Returns configured size per bundle, not total across all bundles.
            Use cache_enabled to check if caching is active.
        """
        return self._cache_size if self._enable_cache else 0

    def __repr__(self) -> str:
        """Return string representation for debugging.


        Returns:
            String representation showing locales and resource count

        Example:
            >>> l10n = FluentLocalization(['lv', 'en'])
            >>> repr(l10n)
            "FluentLocalization(locales=('lv', 'en'), bundles=2)"
        """
        # Count only initialized bundles
        initialized = sum(1 for b in self._bundles.values() if b is not None)
        total = len(self._bundles)
        return f"FluentLocalization(locales={self._locales!r}, bundles={initialized}/{total})"

    def add_resource(self, locale: LocaleCode, ftl_source: FTLSource) -> None:
        """Add FTL resource to specific locale bundle.

        Allows dynamic resource loading without ResourceLoader.

        Args:
            locale: Locale code (must be in fallback chain)
            ftl_source: FTL source code

        Raises:
            ValueError: If locale not in fallback chain
        """
        if locale not in self._bundles:
            msg = f"Locale '{locale}' not in fallback chain {self._locales}"
            raise ValueError(msg)

        bundle = self._get_or_create_bundle(locale)
        bundle.add_resource(ftl_source)

    def format_value(
        self, message_id: MessageId, args: Mapping[str, FluentValue] | None = None
    ) -> tuple[str, tuple[FluentError, ...]]:
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
        errors: list[FluentError] = []

        # Try each locale in priority order (fallback chain)
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)

            # Check if this bundle has the message
            if bundle.has_message(message_id):
                # Message exists in this locale - format it
                value, bundle_errors = bundle.format_pattern(message_id, args)
                # FluentBundle.format_pattern returns tuple[FluentError, ...]
                errors.extend(bundle_errors)
                return (value, tuple(errors))

        # No locale had the message - return fallback
        # Use pattern matching for graceful degradation
        match message_id:
            case str() if message_id:
                # Return message ID wrapped in braces (Fluent convention)
                diagnostic = Diagnostic(
                    code=DiagnosticCode.MESSAGE_NOT_FOUND,
                    message=f"Message '{message_id}' not found in any locale",
                )
                errors.append(FluentError(diagnostic))
                return (f"{{{message_id}}}", tuple(errors))
            case _:
                # Invalid message ID - treat as simple string error
                errors.append(FluentError("Empty message ID"))
                return ("{???}", tuple(errors))

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
    ) -> tuple[str, tuple[FluentError, ...]]:
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
        errors: list[FluentError] = []

        # Try each locale in fallback order
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)

            if bundle.has_message(message_id):
                value, bundle_errors = bundle.format_pattern(message_id, args, attribute=attribute)
                errors.extend(bundle_errors)
                return (value, tuple(errors))

        # Not found - return fallback
        diagnostic = Diagnostic(
            code=DiagnosticCode.MESSAGE_NOT_FOUND,
            message=f"Message '{message_id}' not found in any locale",
        )
        errors.append(FluentError(diagnostic))
        return (f"{{{message_id}}}", tuple(errors))

    def add_function(self, name: str, func: Callable[..., str]) -> None:
        """Register custom function on all bundles.

        Convenience method to avoid manual bundle iteration.
        Creates bundles lazily if they don't exist yet.

        Args:
            name: Function name (UPPERCASE by convention)
            func: Python function implementation

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
        for locale in self._locales:
            bundle = self._get_or_create_bundle(locale)
            bundle.add_function(name, func)

    def introspect_message(self, message_id: MessageId) -> "MessageIntrospection | None":
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

    def validate_resource(self, ftl_source: FTLSource) -> "ValidationResult":
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
        """
        for bundle in self._bundles.values():
            if bundle is not None:
                bundle.clear_cache()

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
    "FluentLocalization",
    "PathResourceLoader",
    "ResourceLoader",
    # Type aliases for user code type annotations
    "MessageId",
    "LocaleCode",
    "ResourceId",
    "FTLSource",
]
