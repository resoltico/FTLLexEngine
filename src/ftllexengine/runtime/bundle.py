"""FluentBundle - Main API for Fluent message formatting.

Python 3.13+. External dependency: Babel (CLDR locale data).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from ftllexengine.constants import (
    DEFAULT_MAX_EXPANSION_SIZE,
    MAX_DEPTH,
    MAX_SOURCE_SIZE,
)
from ftllexengine.core.depth_guard import depth_clamp
from ftllexengine.core.locale_utils import get_system_locale, require_locale_code
from ftllexengine.runtime.bundle_formatting import _BundleFormattingMixin
from ftllexengine.runtime.bundle_queries import _BundleQueryMixin
from ftllexengine.runtime.bundle_registration import _BundleRegistrationMixin
from ftllexengine.runtime.cache import CacheAuditLogEntry, CacheStats, IntegrityCache
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.functions import get_shared_registry
from ftllexengine.runtime.locale_context import LocaleContext
from ftllexengine.runtime.rwlock import RWLock
from ftllexengine.syntax import Entry, Junk, Message, Resource, Term
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.validation import validate_resource as _validate_resource_impl

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from ftllexengine.core.semantic_types import LocaleCode
    from ftllexengine.core.value_types import FluentValue
    from ftllexengine.diagnostics import FrozenFluentError, ValidationResult
    from ftllexengine.runtime.cache_config import CacheConfig
    from ftllexengine.runtime.resolver import FluentResolver

__all__ = ["FluentBundle"]

logger = logging.getLogger(__name__)


class FluentBundle(_BundleQueryMixin, _BundleFormattingMixin, _BundleRegistrationMixin):
    """Fluent message bundle for specific locale.

    Main public API for Fluent localization. Aligned with Mozilla python-fluent
    error handling that returns (result, errors) tuples.

    Thread Safety:
        FluentBundle is always thread-safe using a readers-writer lock (RWLock).
        This enables high-concurrency access patterns:

        - Read operations (format_pattern, format_message, has_message, etc.)
          can execute concurrently without blocking each other.
        - Write operations (add_resource, add_function) acquire exclusive access.
        - Writers have priority to prevent starvation in read-heavy workloads.

        This design provides superior throughput for multi-threaded applications
        while maintaining full thread safety. Typical web servers with 100+
        concurrent format requests will see significant performance improvements
        compared to coarse-grained locking.

    Reentrancy Limitation:
        Modifying the bundle from within format operations is PROHIBITED and
        raises RuntimeError. This includes calling add_resource() or add_function()
        from custom functions invoked during formatting. The RWLock does not
        support read-to-write lock upgrading (deadlock prevention).

        If you need lazy-loading patterns, load resources before formatting
        or use a separate bundle instance for dynamic content.

    Parser Security:
        Configurable limits prevent DoS attacks:
        - max_source_size: Maximum FTL source length in characters (default: 10,000,000)
        - max_nesting_depth: Maximum placeable nesting depth (default: 100)

    Examples:
        >>> bundle = FluentBundle("lv_LV")  # doctest: +SKIP
        >>> bundle.add_resource('''  # doctest: +SKIP
        ... hello = Sveiki, pasaule!
        ... welcome = Laipni lūdzam, { $name }!
        ... ''')
        >>> result, errors = bundle.format_pattern("hello")  # doctest: +SKIP
        >>> assert result == 'Sveiki, pasaule!'  # doctest: +SKIP
        >>> assert errors == ()  # doctest: +SKIP

        >>> result, errors = bundle.format_pattern("welcome", {"name": "Jānis"})  # doctest: +SKIP
        >>> assert result == 'Laipni lūdzam, Jānis!'  # doctest: +SKIP
        >>> assert errors == ()  # doctest: +SKIP

        Custom security limits for stricter environments:
        >>> strict_bundle = FluentBundle("en_US", max_source_size=1_000_000)  # doctest: +SKIP
    """

    __slots__ = (
        "_cache",
        "_cache_config",
        "_function_registry",
        "_locale",
        "_max_expansion_size",
        "_max_nesting_depth",
        "_max_source_size",
        "_messages",
        "_msg_deps",
        "_owns_registry",
        "_parser",
        "_resolver",
        "_rwlock",
        "_strict",
        "_term_deps",
        "_terms",
        "_use_isolating",
    )

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
        """Initialize bundle for locale.

        Args:
            locale: Locale code (lv_LV, en_US, de_DE, pl_PL) [positional-only]
            use_isolating: Wrap interpolated values in Unicode bidi isolation marks (default: True).
                          Set to False only if you're certain RTL languages won't be used.
                          See Unicode TR9: http://www.unicode.org/reports/tr9/
            cache: Cache configuration (default: None = caching disabled).
                  Pass ``CacheConfig()`` for default settings or customize fields.
                  Cache provides 50x speedup on repeated format calls.
            functions: Custom FunctionRegistry to use (default: standard registry with
                      NUMBER, DATETIME, CURRENCY). Pass a custom registry to use
                      pre-registered custom functions or override default behavior.
                      The registry is copied on construction; later mutations to the
                      original have no effect on this bundle.
            max_source_size: Maximum FTL source length in characters (default: 10,000,000).
                            Set to 0 to disable limit (not recommended for untrusted input).
            max_nesting_depth: Maximum placeable nesting depth (default: 100).
                              Prevents DoS via deeply nested { { { ... } } } structures.
            max_expansion_size: Maximum total characters produced during resolution (default: 1,000,000).
                               Prevents Billion Laughs attacks via exponentially expanding message references.
            strict: Fail-fast on formatting errors (default: True).
                   When True, format_pattern raises FormattingIntegrityError on ANY error
                   instead of returning fallback values. Set to False only for development
                   or when soft error recovery is explicitly required. Also affects cache
                   corruption handling: raises CacheCorruptionError instead of silent eviction.

        Raises:
            ValueError: If locale code is empty, structurally invalid, or not
                recognized by Babel/CLDR

        Thread Safety:
            FluentBundle is always thread-safe using a readers-writer lock (RWLock).
            Read operations (format calls) execute concurrently without blocking.
            Write operations (add_resource, add_function) acquire exclusive access.

        Example:
            >>> from ftllexengine.runtime.cache_config import CacheConfig  # doctest: +SKIP

            Using the default registry (standard functions):
            >>> bundle = FluentBundle("en")  # doctest: +SKIP

            Using a custom registry with additional functions:
            >>> from ftllexengine.runtime.functions import create_default_registry  # doctest: +SKIP
            >>> registry = create_default_registry()  # doctest: +SKIP
            >>> registry.register(my_custom_func, ftl_name="CUSTOM")  # doctest: +SKIP
            >>> bundle = FluentBundle("en", functions=registry)  # doctest: +SKIP

            Stricter limits for untrusted input:
            >>> bundle = FluentBundle("en", max_source_size=100_000, max_nesting_depth=20)  # doctest: +SKIP

            Financial-grade default: `strict=True` with a write-once cache:
            >>> bundle = FluentBundle("en", cache=CacheConfig(write_once=True))  # doctest: +SKIP

            Audit-enabled cache for compliance:
            >>> bundle = FluentBundle("en", cache=CacheConfig(enable_audit=True))  # doctest: +SKIP
        """
        # Validate against Babel/CLDR at the public boundary so the bundle never
        # advertises one locale while formatting with a different fallback locale.
        canonical_locale = require_locale_code(locale, "locale")
        locale_context = LocaleContext.create_or_raise(canonical_locale)
        self._locale = locale_context.locale_code
        self._use_isolating = use_isolating
        self._strict = strict
        self._messages: dict[str, Message] = {}
        self._terms: dict[str, Term] = {}

        # Dependency tracking for cross-resource cycle detection.
        # Maps entry ID to set of (type-prefixed) dependencies.
        # E.g., {"greeting": {"msg:welcome", "term:brand"}}
        self._msg_deps: dict[str, frozenset[str]] = {}
        self._term_deps: dict[str, frozenset[str]] = {}

        # Parser security configuration
        self._max_source_size = max_source_size if max_source_size is not None else MAX_SOURCE_SIZE
        requested_depth = max_nesting_depth if max_nesting_depth is not None else MAX_DEPTH
        self._max_nesting_depth = depth_clamp(requested_depth)
        self._max_expansion_size = (
            max_expansion_size if max_expansion_size is not None else DEFAULT_MAX_EXPANSION_SIZE
        )
        self._parser = FluentParserV1(
            max_source_size=self._max_source_size,
            max_nesting_depth=self._max_nesting_depth,
        )

        # Thread safety: always enabled via RWLock (readers-writer lock)
        self._rwlock = RWLock()

        # Function registry: copy-on-write optimization
        if functions is not None:
            if not isinstance(functions, FunctionRegistry):
                msg = (  # type: ignore[unreachable]
                    f"functions must be FunctionRegistry, not {type(functions).__name__}. "
                    "Use create_default_registry() or FunctionRegistry() to create one."
                )
                raise TypeError(msg)
            self._function_registry = functions.copy()
            self._owns_registry = True
        else:
            self._function_registry = get_shared_registry()
            self._owns_registry = False

        # Cache configuration and instance
        self._cache_config: CacheConfig | None = cache
        self._cache: IntegrityCache | None = None

        if cache is not None:
            # The bundle's strict flag gates cache exception propagation: a
            # non-strict bundle must never raise CacheCorruptionError from
            # format_pattern. When strict=False, corruption is always handled
            # by silent eviction regardless of CacheConfig.integrity_strict.
            # When strict=True, CacheConfig.integrity_strict is the user's
            # explicit fine-grained control (AND-gate: both must be True for
            # CacheCorruptionError to propagate).
            self._cache = IntegrityCache(
                maxsize=cache.size,
                max_entry_weight=cache.max_entry_weight,
                max_errors_per_entry=cache.max_errors_per_entry,
                write_once=cache.write_once,
                strict=cache.integrity_strict and strict,
                enable_audit=cache.enable_audit,
                max_audit_entries=cache.max_audit_entries,
            )

        # Resolver: eagerly created, re-created only when function_registry changes.
        # Holds dict references (not copies) so add_resource() mutations are immediately
        # visible without re-creation. Initialized here to eliminate the read-lock
        # write race that existed in the previous lazy-initialization pattern.
        self._resolver: FluentResolver = self._create_resolver()

        logger.info(
            "FluentBundle initialized for locale: %s (use_isolating=%s, cache=%s, strict=%s)",
            self._locale,
            use_isolating,
            "enabled" if cache is not None else "disabled",
            strict,
        )

    @property
    def locale(self) -> LocaleCode:
        """Get the canonical locale code for this bundle (read-only).

        Returns:
            LocaleCode: Canonical lowercase POSIX locale code (e.g., "en_us", "lv_lv")

        Example:
            >>> bundle = FluentBundle("lv_LV")  # doctest: +SKIP
            >>> bundle.locale  # doctest: +SKIP
            'lv_lv'
        """
        return self._locale

    @property
    def use_isolating(self) -> bool:
        """Get whether Unicode bidi isolation is enabled (read-only).

        Returns:
            bool: True if bidi isolation is enabled, False otherwise

        Example:
            >>> bundle = FluentBundle("ar_EG", use_isolating=True)  # doctest: +SKIP
            >>> bundle.use_isolating  # doctest: +SKIP
            True
        """
        return self._use_isolating

    @property
    def strict(self) -> bool:
        """Get whether strict mode is enabled (read-only).

        Strict mode raises FormattingIntegrityError on ANY formatting error
        instead of returning fallback values. Essential for financial applications
        where silent fallbacks are unacceptable.

        Returns:
            bool: True if strict mode is enabled, False otherwise

        Example:
            >>> bundle = FluentBundle("en", strict=True)  # doctest: +SKIP
            >>> bundle.strict  # doctest: +SKIP
            True
            >>> bundle_normal = FluentBundle("en")  # doctest: +SKIP
            >>> bundle_normal.strict  # doctest: +SKIP
            True
        """
        return self._strict

    @property
    def cache_enabled(self) -> bool:
        """Get whether format caching is enabled (read-only).

        Returns:
            bool: True if caching is enabled, False otherwise

        Example:
            >>> from ftllexengine.runtime.cache_config import CacheConfig  # doctest: +SKIP
            >>> bundle = FluentBundle("en", cache=CacheConfig())  # doctest: +SKIP
            >>> bundle.cache_enabled  # doctest: +SKIP
            True
            >>> bundle_no_cache = FluentBundle("en")  # doctest: +SKIP
            >>> bundle_no_cache.cache_enabled  # doctest: +SKIP
            False
        """
        return self._cache is not None

    @property
    def cache_config(self) -> CacheConfig | None:
        """Get cache configuration (read-only).

        Returns:
            CacheConfig if caching is enabled, None if caching is disabled.

        Example:
            >>> from ftllexengine.runtime.cache_config import CacheConfig  # doctest: +SKIP
            >>> bundle = FluentBundle("en", cache=CacheConfig(size=500))  # doctest: +SKIP
            >>> bundle.cache_config.size  # doctest: +SKIP
            500
            >>> bundle_no_cache = FluentBundle("en")  # doctest: +SKIP
            >>> bundle_no_cache.cache_config is None  # doctest: +SKIP
            True
        """
        return self._cache_config

    @property
    def cache_usage(self) -> int:
        """Get current number of cached format results (read-only).

        Returns:
            int: Number of entries currently in cache (0 if caching disabled)
        """
        if self._cache is None:
            return 0
        return self._cache.size

    @property
    def max_source_size(self) -> int:
        """Maximum FTL source size in characters (read-only).

        Python measures string length in characters (code points), not bytes.
        UTF-8 encoding means 1 character = 1-4 bytes, but this limit counts
        characters as returned by len(source).

        Returns:
            int: Maximum source size limit for add_resource()

        Example:
            >>> bundle = FluentBundle("en", max_source_size=1_000_000)  # doctest: +SKIP
            >>> bundle.max_source_size  # doctest: +SKIP
            1000000
        """
        return self._max_source_size

    @property
    def max_nesting_depth(self) -> int:
        """Maximum placeable nesting depth (read-only).

        Returns:
            int: Maximum nesting depth limit for parser

        Example:
            >>> bundle = FluentBundle("en", max_nesting_depth=50)  # doctest: +SKIP
            >>> bundle.max_nesting_depth  # doctest: +SKIP
            50
        """
        return self._max_nesting_depth

    @property
    def max_expansion_size(self) -> int:
        """Maximum total characters produced during resolution (read-only).

        Returns:
            int: Maximum expansion budget for DoS prevention
        """
        return self._max_expansion_size

    @property
    def function_registry(self) -> FunctionRegistry:
        """Get the function registry for this bundle (read-only).

        Provides read access to the registered formatting functions without
        requiring access to private attributes.

        Returns:
            FunctionRegistry: The function registry for this bundle

        Example:
            >>> bundle = FluentBundle("en")  # doctest: +SKIP
            >>> registry = bundle.function_registry  # doctest: +SKIP
            >>> "NUMBER" in registry  # doctest: +SKIP
            True
        """
        return self._function_registry

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
    ) -> FluentBundle:
        """Factory method to create a FluentBundle using the system locale.

        Detects and uses the current system locale (from locale.getlocale(),
        LC_ALL, LC_MESSAGES, or LANG environment variables).

        Args:
            use_isolating: Wrap interpolated values in Unicode bidi isolation marks
            cache: Cache configuration. Pass ``CacheConfig()`` to enable caching
                with defaults, or ``CacheConfig(size=500, ...)`` for custom settings.
                ``None`` disables caching (default).
            functions: Custom FunctionRegistry to use (default: standard registry).
                      Copied on construction; later mutations to the original have no effect.
            max_source_size: Maximum FTL source size in characters (default: 10,000,000)
            max_nesting_depth: Maximum placeable nesting depth (default: 100)
            strict: Fail-fast mode (default True): raises on formatting errors. Pass False for soft error recovery.

        Returns:
            Configured FluentBundle instance for system locale

        Raises:
            RuntimeError: If system locale cannot be determined

        Example:
            >>> bundle = FluentBundle.for_system_locale()  # doctest: +SKIP
            >>> bundle.locale  # Returns canonical detected system locale  # doctest: +SKIP
            'en_us'
        """
        # Delegate to unified locale detection (raises RuntimeError on failure)
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

    def __repr__(self) -> str:
        """Return string representation for debugging.

        Returns:
            String representation showing locale and loaded messages count

        Example:
            >>> bundle = FluentBundle("lv_LV")  # doctest: +SKIP
            >>> repr(bundle)  # doctest: +SKIP
            "FluentBundle(locale='lv_lv', messages=0, terms=0)"
        """
        with self._rwlock.read():
            return (
                f"FluentBundle(locale={self._locale!r}, "
                f"messages={len(self._messages)}, "
                f"terms={len(self._terms)})"
            )

    def get_babel_locale(self) -> str:
        """Get the Babel locale identifier for this bundle (introspection API).

        This is a debugging/introspection method that returns the actual Babel locale
        identifier being used for NUMBER(), DATETIME(), and CURRENCY() formatting.

        Useful for troubleshooting locale-related formatting issues, especially when
        verifying which CLDR data is being applied.

        Returns:
            str: Babel locale identifier (e.g., "en_US", "lv_LV", "ar_EG")

        Example:
            >>> bundle = FluentBundle("lv")  # doctest: +SKIP
            >>> bundle.get_babel_locale()  # doctest: +SKIP
            'lv'
            >>> bundle_us = FluentBundle("en-US")  # doctest: +SKIP
            >>> bundle_us.get_babel_locale()  # doctest: +SKIP
            'en_US'

        Note:
            This creates a LocaleContext temporarily to access Babel locale
            information. The return value shows the Babel/CLDR locale, which
            may differ in casing from bundle.locale.

        See Also:
            - bundle.locale: The canonical LocaleCode stored by FluentBundle
            - LocaleContext.babel_locale: The underlying Babel Locale object
        """
        ctx = LocaleContext.create_or_raise(self._locale)
        return str(ctx.babel_locale)

    def add_resource(
        self, source: str, /, *, source_path: str | None = None
    ) -> tuple[Junk, ...]:
        """Add FTL resource to bundle.

        Parses FTL source and adds messages/terms to registry.
        Thread-safe (uses internal RWLock).

        Parse operation occurs outside the write lock to minimize reader
        contention. Only registration (dict updates) requires exclusive access.

        Args:
            source: FTL file content [positional-only]
            source_path: Optional path to source file for better error messages
                        (e.g., "locales/lv/ui.ftl"). Used as source identifier
                        in warning messages. Defaults to "<string>" if not provided.

        Returns:
            Tuple of Junk entries encountered during parsing. Empty tuple if
            parsing succeeded without errors. Each Junk entry contains the
            unparseable content and associated annotations.

        Logging:
            Syntax errors (Junk entries) are logged at WARNING level regardless
            of whether source_path is provided. This ensures syntax errors are
            visible whether loading from files, databases, or in-memory strings.

        Note:
            Parser continues after errors (robustness principle). Junk entries
            are returned for programmatic error handling.

        Raises:
            TypeError: If source is not a string (e.g., bytes were passed).
            SyntaxIntegrityError: In strict mode only, if parsing produces any
                Junk entries. Financial applications using strict=True get
                fail-fast behavior on syntax errors.

        Thread Safety:
            Parser is stateless and thread-safe. Parse operation can occur
            outside write lock without risk. Only registration step requires
            exclusive write access.
        """
        # Type validation at API boundary - type hints are not enforced at runtime.
        # Defensive check: users may pass bytes despite str annotation.
        if not isinstance(source, str):
            msg = (  # type: ignore[unreachable]
                f"source must be str, not {type(source).__name__}. "
                "Decode bytes to str (e.g., source.decode('utf-8')) before calling add_resource()."
            )
            raise TypeError(msg)

        # Parse outside lock (expensive, but safe - parser is stateless, source is immutable)
        resource = self._parser.parse(source)

        # Only hold lock for registration (fast, O(N) where N is entry count)
        with self._rwlock.write():
            return self._register_resource(resource, source_path)

    def add_resource_stream(
        self, lines: Iterable[str], /, *, source_path: str | None = None
    ) -> tuple[Junk, ...]:
        """Add FTL resource to bundle from a line-oriented source stream.

        Semantically identical to add_resource() but accepts any iterable of
        lines rather than a pre-assembled source string. Memory usage is
        proportional to the largest single FTL entry in the stream, not the
        total resource size.

        The stream is split at blank-line boundaries (which delimit top-level
        FTL entries). Each chunk is parsed independently, then all entries are
        committed together via the same two-phase protocol used by add_resource().
        Strict mode, overwrite warnings, cache invalidation, and thread safety
        are identical.

        Args:
            lines: Iterable of FTL source lines [positional-only]. Trailing
                   newlines are stripped per line.
            source_path: Optional path to source file for better error messages
                         (e.g., "locales/lv/ui.ftl"). Defaults to "<string>".

        Returns:
            Tuple of Junk entries encountered during parsing. Empty tuple if
            parsing succeeded without errors.

        Raises:
            SyntaxIntegrityError: In strict mode, if any Junk entries are parsed.

        Example:
            >>> bundle = FluentBundle("en")  # doctest: +SKIP
            >>> with open("locales/en/ui.ftl") as f:  # doctest: +SKIP
            ...     bundle.add_resource_stream(f, source_path="locales/en/ui.ftl")
        """
        # Collect parsed entries outside lock (stateless parse, immutable input)
        collected: list[Entry] = list(self._parser.parse_stream(lines))
        resource = Resource(entries=tuple(collected))

        with self._rwlock.write():
            return self._register_resource(resource, source_path)

    def validate_resource(self, source: str) -> ValidationResult:
        """Validate FTL resource without adding to bundle.

        Use this to check FTL files in CI/tooling before adding them.
        Unlike add_resource(), this does not modify the bundle.

        Performs both syntax validation (errors) and semantic validation (warnings):
        - Errors: Parse failures (Junk entries)
        - Warnings: Duplicate IDs, messages without values, undefined references,
          circular dependencies

        Args:
            source: FTL file content

        Returns:
            ValidationResult with parse errors and semantic warnings

        Raises:
            TypeError: If source is not a string (e.g., bytes were passed).

        Example:
            >>> bundle = FluentBundle("lv")  # doctest: +SKIP
            >>> result = bundle.validate_resource(ftl_source)  # doctest: +SKIP
            >>> if not result.is_valid:  # doctest: +SKIP
            ...     for error in result.errors:
            ...         print(f"Error [{error.code}]: {error.message}")
            >>> if result.warning_count > 0:  # doctest: +SKIP
            ...     for warning in result.warnings:
            ...         print(f"Warning [{warning.code}]: {warning.message}")

        See Also:
            ftllexengine.validation.validate_resource: Standalone validation function
        """
        # Type validation at API boundary - type hints are not enforced at runtime.
        # Defensive check: users may pass bytes despite str annotation.
        if not isinstance(source, str):
            msg = (  # type: ignore[unreachable]
                f"source must be str, not {type(source).__name__}. "
                "Decode bytes to str (e.g., source.decode('utf-8')) before calling validate_resource()."
            )
            raise TypeError(msg)

        # Delegate to validation module, reusing bundle's parser for consistency
        # Pass existing bundle entries and their dependencies for cross-resource validation
        with self._rwlock.read():
            return _validate_resource_impl(
                source,
                parser=self._parser,
                known_messages=frozenset(self._messages.keys()),
                known_terms=frozenset(self._terms.keys()),
                known_msg_deps=self._msg_deps,
                known_term_deps=self._term_deps,
            )

    def format_pattern(
        self,
        message_id: str,
        /,
        args: Mapping[str, FluentValue] | None = None,
        *,
        attribute: str | None = None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        """Format message to string with error reporting.

        Mozilla python-fluent aligned API that returns both the formatted
        string and any errors encountered during resolution. Thread-safe.

        Args:
            message_id: Message identifier [positional-only]
            args: Variable arguments for interpolation
            attribute: Attribute name (optional, keyword-only)

        Returns:
            Tuple of (formatted_string, errors)
            - formatted_string: Best-effort formatted output (never empty)
            - errors: Tuple of FrozenFluentError instances encountered during resolution (immutable)

        Raises:
            FormattingIntegrityError: In strict mode, if ANY error occurs during formatting.
                The exception carries the original errors, fallback value, and message ID.

        Note:
            In strict mode (default: strict=True), FormattingIntegrityError is raised
            immediately when ANY error occurs. This is the default for financial applications
            where silent fallbacks are unacceptable. The exception provides:
            - fluent_errors: The original FrozenFluentError instances
            - fallback_value: What would have been returned in soft mode
            - message_id: The message that failed to format

            In soft error mode (strict=False), formatting errors are collected and
            returned in the errors tuple. The formatted string always contains a
            readable fallback value per Fluent specification.

            If an attribute name is duplicated within a message (validation warning),
            the last definition is used during resolution (last-wins semantics).
            This matches the Fluent specification and Mozilla reference implementation.

        Examples:
            Successful formatting:
            >>> result, errors = bundle.format_pattern("hello")  # doctest: +SKIP
            >>> assert result == 'Sveiki, pasaule!'  # doctest: +SKIP
            >>> assert errors == ()  # doctest: +SKIP

            Missing variable returns a fallback plus an error in non-strict mode:
            >>> bundle.add_resource('msg = Hello { $name }!')  # doctest: +SKIP
            >>> result, errors = bundle.format_pattern("msg", {})  # doctest: +SKIP
            >>> assert result == 'Hello {$name}!'  # Readable fallback  # doctest: +SKIP
            >>> assert len(errors) == 1  # doctest: +SKIP
            >>> assert errors[0].category == ErrorCategory.REFERENCE  # doctest: +SKIP

            Attribute access:
            >>> result, errors = bundle.format_pattern("button-save", attribute="tooltip")  # doctest: +SKIP
            >>> assert result == 'Saglabā pašreizējo ierakstu datubāzē'  # doctest: +SKIP
            >>> assert errors == ()  # doctest: +SKIP

            Default `strict=True` raises on errors, including missing `$name`:
            >>> bundle_strict = FluentBundle("en")  # doctest: +SKIP
            >>> bundle_strict.add_resource('msg = Hello { $name }!')  # doctest: +SKIP
            >>> bundle_strict.format_pattern("msg", {})  # Raises FormattingIntegrityError  # doctest: +SKIP
        """
        with self._rwlock.read():
            return self._format_pattern_impl(message_id, args, attribute)

    def add_function(self, name: str, func: Callable[..., FluentValue]) -> None:
        """Add custom function to bundle.

        Args:
            name: Function name (UPPERCASE by convention)
            func: Callable function that returns a FluentValue

        Example:
            >>> def CUSTOM(value):  # doctest: +SKIP
            ...     return value.upper()
            >>> bundle.add_function("CUSTOM", CUSTOM)  # doctest: +SKIP
        """
        with self._rwlock.write():
            # Copy-on-write: copy the shared registry on first modification
            if not self._owns_registry:
                self._function_registry = self._function_registry.copy()
                self._owns_registry = True
                logger.debug("Registry copied on first add_function")

            self._function_registry.register(func, ftl_name=name)
            logger.debug("Added custom function: %s", name)

            # Re-create resolver so it captures the updated function registry
            self._resolver = self._create_resolver()

            # Invalidate cache (functions changed)
            if self._cache is not None:
                self._cache.clear()
                logger.debug("Cache cleared after add_function")

    def clear_cache(self) -> None:
        """Clear format cache.

        Call this when you want to force cache invalidation.
        Automatically called by add_resource() and add_function().

        Example:
            >>> bundle = FluentBundle("en", cache=CacheConfig())  # doctest: +SKIP
            >>> bundle.add_resource("msg = Hello")  # doctest: +SKIP
            >>> bundle.format_pattern("msg")  # Caches result  # doctest: +SKIP
            >>> bundle.clear_cache()  # Manual invalidation  # doctest: +SKIP
        """
        with self._rwlock.write():
            if self._cache is not None:
                self._cache.clear()
                logger.debug("Cache manually cleared")

    def get_cache_stats(self) -> CacheStats | None:
        """Get cache statistics.

        Returns:
            CacheStats snapshot, or None if caching is disabled.
            All fields are read atomically under the cache lock.
            See CacheStats for the complete field specification.

        Example:
            >>> bundle = FluentBundle("en", cache=CacheConfig())  # doctest: +SKIP
            >>> bundle.add_resource("msg = Hello")  # doctest: +SKIP
            >>> bundle.format_pattern("msg", {})  # Cache miss  # doctest: +SKIP
            >>> bundle.format_pattern("msg", {})  # Cache hit  # doctest: +SKIP
            >>> stats = bundle.get_cache_stats()  # doctest: +SKIP
            >>> stats["hits"]  # doctest: +SKIP
            1
            >>> stats["misses"]  # doctest: +SKIP
            1
            >>> isinstance(stats["hit_rate"], float)  # doctest: +SKIP
            True
        """
        if self._cache is not None:
            return self._cache.get_stats()
        return None

    def get_cache_audit_log(self) -> tuple[CacheAuditLogEntry, ...] | None:
        """Get immutable cache audit log entries.

        Returns:
            Tuple of cache audit-log entry snapshots, or None if caching is disabled.
            Returns an empty tuple when caching is enabled but audit logging is
            disabled or no cache operations have been recorded.
        """
        if self._cache is not None:
            return self._cache.get_audit_log()
        return None
