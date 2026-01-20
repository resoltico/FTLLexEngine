"""FluentBundle - Main API for Fluent message formatting.

Python 3.13+. External dependency: Babel (CLDR locale data).
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, NoReturn

from ftllexengine.constants import (
    DEFAULT_CACHE_SIZE,
    FALLBACK_INVALID,
    FALLBACK_MISSING_MESSAGE,
    MAX_DEPTH,
    MAX_LOCALE_LENGTH_HARD_LIMIT,
    MAX_SOURCE_SIZE,
)
from ftllexengine.core.depth_guard import depth_clamp
from ftllexengine.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    ErrorCategory,
    ErrorTemplate,
    FrozenFluentError,
    ValidationResult,
)
from ftllexengine.integrity import FormattingIntegrityError, IntegrityContext
from ftllexengine.introspection import extract_variables, introspect_message
from ftllexengine.locale_utils import get_system_locale
from ftllexengine.runtime.cache import IntegrityCache
from ftllexengine.runtime.function_bridge import FluentValue, FunctionRegistry
from ftllexengine.runtime.functions import get_shared_registry
from ftllexengine.runtime.locale_context import LocaleContext
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.runtime.rwlock import RWLock
from ftllexengine.syntax import Comment, Junk, Message, Resource, Term
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.validation import validate_resource as _validate_resource_impl

if TYPE_CHECKING:
    from ftllexengine.introspection import MessageIntrospection

__all__ = ["FluentBundle"]

logger = logging.getLogger(__name__)

# Logging truncation limits for error messages.
# Warnings show more context (100 chars) as they're surfaced to users.
# Debug messages are high-volume, shorter (50 chars) keeps logs manageable.
_LOG_TRUNCATE_WARNING: int = 100
_LOG_TRUNCATE_DEBUG: int = 50

# BCP 47 locale code pattern (ASCII-only alphanumerics with underscore/hyphen separators).
# Rejects non-ASCII characters like accented letters (e.g., "e_FR" with accented e).
# Uses \Z instead of $ to match only at end-of-string, not before trailing newline.
_LOCALE_PATTERN: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9]+([_-][a-zA-Z0-9]+)*\Z")


class FluentBundle:
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

    Parser Security:
        Configurable limits prevent DoS attacks:
        - max_source_size: Maximum FTL source length in characters (default: 10 MiB / 10,485,760 chars)
        - max_nesting_depth: Maximum placeable nesting depth (default: 100)

    Examples:
        >>> bundle = FluentBundle("lv_LV")
        >>> bundle.add_resource('''
        ... hello = Sveiki, pasaule!
        ... welcome = Laipni lūdzam, { $name }!
        ... ''')
        >>> result, errors = bundle.format_pattern("hello")
        >>> assert result == 'Sveiki, pasaule!'
        >>> assert errors == ()
        >>>
        >>> result, errors = bundle.format_pattern("welcome", {"name": "Jānis"})
        >>> assert result == 'Laipni lūdzam, Jānis!'
        >>> assert errors == ()
        >>>
        >>> # Custom security limits for stricter environments
        >>> strict_bundle = FluentBundle("en_US", max_source_size=1_000_000)
    """

    __slots__ = (
        "_cache",
        "_cache_size",
        "_function_registry",
        "_locale",
        "_max_nesting_depth",
        "_max_source_size",
        "_messages",
        "_modified_in_context",
        "_msg_deps",
        "_owns_registry",
        "_parser",
        "_rwlock",
        "_strict",
        "_term_deps",
        "_terms",
        "_use_isolating",
    )

    @staticmethod
    def _validate_locale_format(locale: str) -> None:
        """Validate locale code format.

        Checks that locale is non-empty and contains only ASCII alphanumeric
        characters with optional underscore or hyphen separators. Enforces
        BCP 47 compliance by rejecting non-ASCII characters.

        Rejects obviously malicious inputs (>1000 characters) to prevent DoS.
        Locale codes exceeding standard BCP 47 length (35 chars) trigger warnings
        in LocaleContext but are accepted here.

        Args:
            locale: Locale code to validate

        Raises:
            ValueError: If locale code is empty, excessively long (>1000),
                contains non-ASCII characters, or has invalid format
        """
        if not locale:
            msg = "Locale code cannot be empty"
            raise ValueError(msg)

        # Reject obviously malicious inputs (DoS prevention)
        if len(locale) > MAX_LOCALE_LENGTH_HARD_LIMIT:
            msg = (
                f"Locale code exceeds maximum length of {MAX_LOCALE_LENGTH_HARD_LIMIT} characters: "
                f"'{locale[:50]}...' ({len(locale)} characters)"
            )
            raise ValueError(msg)

        if not _LOCALE_PATTERN.match(locale):
            msg = f"Invalid locale code format: '{locale}' (must be ASCII alphanumeric)"
            raise ValueError(msg)

    def __init__(
        self,
        locale: str,
        /,
        *,
        use_isolating: bool = True,
        enable_cache: bool = False,
        cache_size: int = DEFAULT_CACHE_SIZE,
        functions: FunctionRegistry | None = None,
        max_source_size: int | None = None,
        max_nesting_depth: int | None = None,
        strict: bool = False,
    ) -> None:
        """Initialize bundle for locale.

        Args:
            locale: Locale code (lv_LV, en_US, de_DE, pl_PL) [positional-only]
            use_isolating: Wrap interpolated values in Unicode bidi isolation marks (default: True)
                          Set to False only if you're certain RTL languages won't be used.
                          See Unicode TR9: http://www.unicode.org/reports/tr9/
            enable_cache: Enable format caching for performance (default: False)
                         Cache provides 50x speedup on repeated format calls.
            cache_size: Maximum cache entries when caching enabled (default: 1000)
            functions: Custom FunctionRegistry to use (default: standard registry with
                      NUMBER, DATETIME, CURRENCY). Pass a custom registry to:
                      - Use pre-registered custom functions
                      - Share function registrations between bundles
                      - Override default function behavior
            max_source_size: Maximum FTL source length in characters (default: 10 MiB / 10,485,760 chars).
                            Set to 0 to disable limit (not recommended for untrusted input).
            max_nesting_depth: Maximum placeable nesting depth (default: 100).
                              Prevents DoS via deeply nested { { { ... } } } structures.
            strict: Enable strict mode for financial applications (default: False).
                   When True, format_pattern raises FormattingIntegrityError on ANY error
                   instead of returning fallback values. Use for monetary/critical data
                   where silent fallbacks are unacceptable.

        Raises:
            ValueError: If locale code is empty or has invalid format

        Thread Safety:
            FluentBundle is always thread-safe using a readers-writer lock (RWLock).
            Read operations (format calls) execute concurrently without blocking.
            Write operations (add_resource, add_function) acquire exclusive access.

        Example:
            >>> # Using default registry (standard functions)
            >>> bundle = FluentBundle("en")
            >>>
            >>> # Using custom registry with additional functions
            >>> from ftllexengine.runtime.functions import create_default_registry
            >>> registry = create_default_registry()
            >>> registry.register(my_custom_func, ftl_name="CUSTOM")
            >>> bundle = FluentBundle("en", functions=registry)
            >>>
            >>> # Stricter limits for untrusted input
            >>> bundle = FluentBundle("en", max_source_size=100_000, max_nesting_depth=20)
            >>>
            >>> # Financial-grade strict mode
            >>> bundle = FluentBundle("en", strict=True)
        """
        # Validate locale format
        FluentBundle._validate_locale_format(locale)

        self._locale = locale
        self._use_isolating = use_isolating
        self._strict = strict
        self._messages: dict[str, Message] = {}
        self._terms: dict[str, Term] = {}

        # Dependency tracking for cross-resource cycle detection.
        # Maps entry ID to set of (type-prefixed) dependencies.
        # E.g., {"greeting": {"msg:welcome", "term:brand"}}
        self._msg_deps: dict[str, set[str]] = {}
        self._term_deps: dict[str, set[str]] = {}

        # Parser security configuration
        self._max_source_size = max_source_size if max_source_size is not None else MAX_SOURCE_SIZE
        requested_depth = max_nesting_depth if max_nesting_depth is not None else MAX_DEPTH
        self._max_nesting_depth = depth_clamp(requested_depth)
        self._parser = FluentParserV1(
            max_source_size=self._max_source_size,
            max_nesting_depth=self._max_nesting_depth,
        )

        # Thread safety: always enabled via RWLock (readers-writer lock)
        # Allows concurrent read operations (format calls) while ensuring
        # exclusive write access (add_resource, add_function)
        self._rwlock = RWLock()

        # Function registry: copy-on-write optimization
        # Using the shared registry avoids re-registering built-in functions for each bundle.
        # Copy is deferred until add_function() is called (copy-on-write pattern).
        if functions is not None:
            # User provided a registry - copy it for isolation
            self._function_registry = functions.copy()
            self._owns_registry = True
        else:
            # Use shared registry directly (frozen, so safe to share)
            # Will be copied on first add_function() call
            self._function_registry = get_shared_registry()
            self._owns_registry = False

        # Format cache (opt-in) with integrity verification
        self._cache: IntegrityCache | None = None
        self._cache_size = cache_size
        if enable_cache:
            # Default: strict=True for data integrity, write_once=False for flexibility
            self._cache = IntegrityCache(maxsize=cache_size, strict=False)

        # Context manager state tracking (cache invalidation optimization)
        self._modified_in_context = False

        logger.info(
            "FluentBundle initialized for locale: %s (use_isolating=%s, cache=%s, strict=%s)",
            locale,
            use_isolating,
            "enabled" if enable_cache else "disabled",
            strict,
        )

    @property
    def locale(self) -> str:
        """Get the locale code for this bundle (read-only).

        Returns:
            str: Locale code (e.g., "en_US", "lv_LV")

        Example:
            >>> bundle = FluentBundle("lv_LV")
            >>> bundle.locale
            'lv_LV'
        """
        return self._locale

    @property
    def use_isolating(self) -> bool:
        """Get whether Unicode bidi isolation is enabled (read-only).

        Returns:
            bool: True if bidi isolation is enabled, False otherwise

        Example:
            >>> bundle = FluentBundle("ar_EG", use_isolating=True)
            >>> bundle.use_isolating
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
            >>> bundle = FluentBundle("en", strict=True)
            >>> bundle.strict
            True
            >>> bundle_normal = FluentBundle("en")
            >>> bundle_normal.strict
            False
        """
        return self._strict

    @property
    def cache_enabled(self) -> bool:
        """Get whether format caching is enabled (read-only).

        Returns:
            bool: True if caching is enabled, False otherwise

        Example:
            >>> bundle = FluentBundle("en", enable_cache=True)
            >>> bundle.cache_enabled
            True
            >>> bundle_no_cache = FluentBundle("en")
            >>> bundle_no_cache.cache_enabled
            False
        """
        return self._cache is not None

    @property
    def cache_size(self) -> int:
        """Get maximum cache size configuration (read-only).

        Returns:
            int: Configured maximum cache entries

        Example:
            >>> bundle = FluentBundle("en", enable_cache=True, cache_size=500)
            >>> bundle.cache_size
            500
            >>> # Cache size is returned even when caching is disabled
            >>> bundle_no_cache = FluentBundle("en", cache_size=200)
            >>> bundle_no_cache.cache_size
            200
            >>> bundle_no_cache.cache_enabled
            False

        Note:
            Returns configured size regardless of whether caching is enabled.
            Use cache_enabled to check if caching is active.
        """
        return self._cache_size

    @property
    def cache_usage(self) -> int:
        """Get current number of cached format results (read-only).

        Returns:
            int: Number of entries currently in cache (0 if caching disabled)

        Example:
            >>> bundle = FluentBundle("en", enable_cache=True, cache_size=500)
            >>> bundle.add_resource("msg = Hello")
            >>> bundle.format_pattern("msg", {})
            ('Hello', ())
            >>> bundle.cache_usage  # One entry cached
            1
            >>> bundle.cache_size   # Configured limit
            500

        Note:
            Use with cache_size to calculate utilization: cache_usage / cache_size
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
            >>> bundle = FluentBundle("en", max_source_size=1_000_000)
            >>> bundle.max_source_size
            1000000
        """
        return self._max_source_size

    @property
    def max_nesting_depth(self) -> int:
        """Maximum placeable nesting depth (read-only).

        Returns:
            int: Maximum nesting depth limit for parser

        Example:
            >>> bundle = FluentBundle("en", max_nesting_depth=50)
            >>> bundle.max_nesting_depth
            50
        """
        return self._max_nesting_depth

    @classmethod
    def for_system_locale(
        cls,
        *,
        use_isolating: bool = True,
        enable_cache: bool = False,
        cache_size: int = DEFAULT_CACHE_SIZE,
        functions: FunctionRegistry | None = None,
        max_source_size: int | None = None,
        max_nesting_depth: int | None = None,
    ) -> FluentBundle:
        """Factory method to create a FluentBundle using the system locale.

        Detects and uses the current system locale (from locale.getlocale(),
        LC_ALL, LC_MESSAGES, or LANG environment variables).

        Args:
            use_isolating: Wrap interpolated values in Unicode bidi isolation marks
            enable_cache: Enable format caching for performance
            cache_size: Maximum cache entries when caching enabled
            functions: Custom FunctionRegistry to use (default: standard registry)
            max_source_size: Maximum FTL source size in characters (default: 10 MiB / 10,485,760 chars)
            max_nesting_depth: Maximum placeable nesting depth (default: 100)

        Returns:
            Configured FluentBundle instance for system locale

        Raises:
            RuntimeError: If system locale cannot be determined

        Example:
            >>> bundle = FluentBundle.for_system_locale()
            >>> bundle.locale  # Returns detected system locale
            'en_US'
        """
        # Delegate to unified locale detection (raises RuntimeError on failure)
        system_locale = get_system_locale(raise_on_failure=True)

        return cls(
            system_locale,
            use_isolating=use_isolating,
            enable_cache=enable_cache,
            cache_size=cache_size,
            functions=functions,
            max_source_size=max_source_size,
            max_nesting_depth=max_nesting_depth,
        )

    def __repr__(self) -> str:
        """Return string representation for debugging.


        Returns:
            String representation showing locale and loaded messages count

        Example:
            >>> bundle = FluentBundle("lv_LV")
            >>> repr(bundle)
            "FluentBundle(locale='lv_LV', messages=0, terms=0)"
        """
        return (
            f"FluentBundle(locale={self._locale!r}, "
            f"messages={len(self._messages)}, "
            f"terms={len(self._terms)})"
        )

    def __enter__(self) -> FluentBundle:
        """Enter context manager.

        Enables use of FluentBundle with 'with' statement. The context manager
        clears the format cache on exit only if the bundle was modified during
        the context (add_resource, add_function, or clear_cache called). For
        read-only operations, the cache is preserved for better performance.

        Messages and terms are always preserved so the bundle remains usable
        after the with block.

        Returns:
            Self (the FluentBundle instance)

        Example:
            >>> with FluentBundle("en_US", enable_cache=True) as bundle:
            ...     bundle.add_resource("hello = Hello")  # Modifying operation
            ...     result = bundle.format_pattern("hello")
            ... # Cache cleared (bundle was modified)
            >>>
            >>> with bundle:  # Read-only context
            ...     result = bundle.format_pattern("hello")
            ... # Cache preserved (bundle NOT modified)
        """
        # Reset modification tracking for new context
        self._modified_in_context = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Exit context manager with conditional cache cleanup.

        Clears the format cache only if the bundle was modified during the
        context (add_resource, add_function, or clear_cache called). For
        read-only contexts, the cache is preserved to avoid invalidating
        cached results in shared bundle scenarios.

        Messages and terms are always preserved so the bundle remains usable
        after the with block. Does not suppress exceptions.

        Args:
            exc_type: Exception type (if any)
            exc_val: Exception value (if any)
            exc_tb: Exception traceback (if any)
        """
        # Clear cache only if bundle was modified during context
        # Read-only operations (format_pattern) preserve cache for performance
        if self._modified_in_context and self._cache is not None:
            self._cache.clear()
            logger.debug(
                "FluentBundle cache cleared on context exit (modified): %s",
                self._locale,
            )
        else:
            logger.debug(
                "FluentBundle cache preserved on context exit (read-only): %s",
                self._locale,
            )

        # Reset flag for next context (defensive)
        self._modified_in_context = False

    def get_babel_locale(self) -> str:
        """Get the Babel locale identifier for this bundle (introspection API).

        This is a debugging/introspection method that returns the actual Babel locale
        identifier being used for NUMBER(), DATETIME(), and CURRENCY() formatting.

        Useful for troubleshooting locale-related formatting issues, especially when
        verifying which CLDR data is being applied.

        Returns:
            str: Babel locale identifier (e.g., "en_US", "lv_LV", "ar_EG")

        Example:
            >>> bundle = FluentBundle("lv")
            >>> bundle.get_babel_locale()
            'lv'
            >>> bundle_us = FluentBundle("en-US")
            >>> bundle_us.get_babel_locale()
            'en_US'

        Note:
            This creates a LocaleContext temporarily to access Babel locale information.
            The return value shows what locale Babel is using for CLDR-based formatting.

        See Also:
            - bundle.locale: The original locale code passed to FluentBundle
            - LocaleContext.babel_locale: The underlying Babel Locale object
        """
        # create() always returns LocaleContext with en_US fallback for invalid locales
        ctx = LocaleContext.create(self._locale)
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

        Thread Safety:
            Parser is stateless and thread-safe. Parse operation can occur
            outside write lock without risk. Only registration step requires
            exclusive write access.
        """
        # Parse outside lock (expensive, but safe - parser is stateless, source is immutable)
        resource = self._parser.parse(source)

        # Only hold lock for registration (fast, O(N) where N is entry count)
        with self._rwlock.write():
            return self._register_resource(resource, source_path)

    def _register_resource(
        self, resource: Resource, source_path: str | None
    ) -> tuple[Junk, ...]:
        """Register parsed resource entries (messages, terms, junk).

        Assumes caller holds write lock. Internal method for add_resource.

        Args:
            resource: Parsed FTL resource
            source_path: Optional path for logging

        Returns:
            Tuple of Junk entries from resource
        """
        # Register messages and terms using structural pattern matching
        junk_entries: list[Junk] = []
        from ftllexengine.introspection import extract_references  # noqa: PLC0415

        for entry in resource.entries:
            match entry:
                case Message():
                    msg_id = entry.id.name
                    if msg_id in self._messages:
                        logger.warning(
                            "Overwriting existing message '%s' with new definition",
                            msg_id,
                        )
                    self._messages[msg_id] = entry
                    # Extract and store dependencies for cross-resource cycle detection
                    msg_refs, term_refs = extract_references(entry)
                    deps: set[str] = set()
                    for ref in msg_refs:
                        deps.add(f"msg:{ref}")
                    for ref in term_refs:
                        deps.add(f"term:{ref}")
                    self._msg_deps[msg_id] = deps
                    logger.debug("Registered message: %s", msg_id)
                case Term():
                    term_id = entry.id.name
                    if term_id in self._terms:
                        logger.warning(
                            "Overwriting existing term '-%s' with new definition",
                            term_id,
                        )
                    self._terms[term_id] = entry
                    # Extract and store dependencies for cross-resource cycle detection
                    msg_refs, term_refs = extract_references(entry)
                    deps_term: set[str] = set()
                    for ref in msg_refs:
                        deps_term.add(f"msg:{ref}")
                    for ref in term_refs:
                        deps_term.add(f"term:{ref}")
                    self._term_deps[term_id] = deps_term
                    logger.debug("Registered term: %s", term_id)
                case Junk():
                    # Collect junk entries, always log at WARNING level
                    # Syntax errors are functional failures regardless of source origin
                    junk_entries.append(entry)
                    # Use repr() to escape control characters while preserving Unicode readability.
                    # repr() escapes control chars (prevents ANSI injection) but keeps Unicode
                    # letters readable (e.g., 'Jānis' instead of 'J\xe2nis').
                    source_desc = source_path or "<string>"
                    logger.warning(
                        "Syntax error in %s: %s",
                        source_desc,
                        repr(entry.content[:_LOG_TRUNCATE_WARNING]),
                    )
                case Comment():
                    # Comments don't need registration - they're documentation only
                    logger.debug("Skipping comment entry")

        # Log summary with file context
        junk_count = len(junk_entries)
        if source_path:
            logger.info(
                "Added resource %s: %d messages, %d terms, %d junk entries",
                source_path,
                len(self._messages),
                len(self._terms),
                junk_count,
            )
        else:
            logger.info(
                "Added resource: %d messages, %d terms, %d junk entries",
                len(self._messages),
                len(self._terms),
                junk_count,
            )

        # Invalidate cache (messages changed)
        if self._cache is not None:
            self._cache.clear()
            logger.debug("Cache cleared after add_resource")

        # Mark bundle as modified for context manager tracking
        self._modified_in_context = True

        return tuple(junk_entries)

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

        Example:
            >>> bundle = FluentBundle("lv")
            >>> result = bundle.validate_resource(ftl_source)
            >>> if not result.is_valid:
            ...     for error in result.errors:
            ...         print(f"Error [{error.code}]: {error.message}")
            >>> if result.warning_count > 0:
            ...     for warning in result.warnings:
            ...         print(f"Warning [{warning.code}]: {warning.message}")

        See Also:
            ftllexengine.validation.validate_resource: Standalone validation function
        """
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
            In non-strict mode (default), this method handles expected formatting
            errors gracefully. All anticipated errors (missing messages, variables,
            references) are collected and returned in the errors list. The formatted
            string always contains a readable fallback value per Fluent specification.

            In strict mode (bundle.strict=True), FormattingIntegrityError is raised
            immediately when ANY error occurs. This is required for financial applications
            where silent fallbacks are unacceptable. The exception provides:
            - fluent_errors: The original FrozenFluentError instances
            - fallback_value: What would have been returned in non-strict mode
            - message_id: The message that failed to format

            If an attribute name is duplicated within a message (validation warning),
            the last definition is used during resolution (last-wins semantics).
            This matches the Fluent specification and Mozilla reference implementation.

        Examples:
            >>> # Successful formatting
            >>> result, errors = bundle.format_pattern("hello")
            >>> assert result == 'Sveiki, pasaule!'
            >>> assert errors == ()

            >>> # Missing variable - returns fallback and error (non-strict mode)
            >>> bundle.add_resource('msg = Hello { $name }!')
            >>> result, errors = bundle.format_pattern("msg", {})
            >>> assert result == 'Hello {$name}!'  # Readable fallback
            >>> assert len(errors) == 1
            >>> assert errors[0].category == ErrorCategory.REFERENCE

            >>> # Attribute access
            >>> result, errors = bundle.format_pattern("button-save", attribute="tooltip")
            >>> assert result == 'Saglabā pašreizējo ierakstu datubāzē'
            >>> assert errors == ()

            >>> # Strict mode - raises on errors
            >>> strict_bundle = FluentBundle("en", strict=True)
            >>> strict_bundle.add_resource('msg = Hello { $name }!')
            >>> strict_bundle.format_pattern("msg", {})  # Raises FormattingIntegrityError
        """
        with self._rwlock.read():
            return self._format_pattern_impl(message_id, args, attribute)

    def _raise_strict_error(
        self,
        message_id: str,
        fallback_value: str,
        errors: tuple[FrozenFluentError, ...],
    ) -> NoReturn:
        """Raise FormattingIntegrityError for strict mode (internal helper).

        Args:
            message_id: The message ID that failed to format
            fallback_value: The fallback value that would be returned in non-strict mode
            errors: Tuple of FrozenFluentError instances

        Raises:
            FormattingIntegrityError: Always raised with error details
        """
        error_summary = "; ".join(str(e) for e in errors[:3])
        if len(errors) > 3:
            error_summary += f" (and {len(errors) - 3} more)"

        context = IntegrityContext(
            component="bundle",
            operation="format_pattern",
            key=message_id,
            expected="<no errors>",
            actual=f"<{len(errors)} error(s)>",
            timestamp=time.monotonic(),
        )

        msg = (
            f"Strict mode: formatting '{message_id}' produced {len(errors)} error(s): "
            f"{error_summary}"
        )
        raise FormattingIntegrityError(
            msg,
            context=context,
            fluent_errors=errors,
            fallback_value=fallback_value,
            message_id=message_id,
        )

    def _format_pattern_impl(
        self,
        message_id: str,
        args: Mapping[str, FluentValue] | None,
        attribute: str | None,
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        """Internal implementation of format_pattern (no locking)."""
        # Check cache first (if enabled)
        if self._cache is not None:
            cached_entry = self._cache.get(
                message_id, args, attribute, self._locale, self._use_isolating
            )
            if cached_entry is not None:
                return cached_entry.to_tuple()

        # Validate message_id is non-empty string
        if not message_id or not isinstance(message_id, str):
            logger.warning("Invalid message ID: empty or non-string")
            diagnostic = Diagnostic(
                code=DiagnosticCode.MESSAGE_NOT_FOUND,
                message="Invalid message ID: empty or non-string",
            )
            error = FrozenFluentError(
                str(diagnostic), ErrorCategory.REFERENCE, diagnostic=diagnostic
            )
            # Strict mode: raise instead of returning fallback
            if self._strict:
                self._raise_strict_error("<empty>", FALLBACK_INVALID, (error,))
            # Don't cache errors
            return (FALLBACK_INVALID, (error,))

        # Validate args is None or a Mapping (defensive check for callers ignoring type hints)
        if args is not None and not isinstance(args, Mapping):
            logger.warning(  # type: ignore[unreachable]
                "Invalid args type: expected Mapping or None, got %s", type(args).__name__
            )
            diagnostic = Diagnostic(
                code=DiagnosticCode.INVALID_ARGUMENT,
                message=f"Invalid args type: expected Mapping or None, got {type(args).__name__}",
            )
            error = FrozenFluentError(
                str(diagnostic), ErrorCategory.RESOLUTION, diagnostic=diagnostic
            )
            # Strict mode: raise instead of returning fallback
            if self._strict:
                self._raise_strict_error(message_id, FALLBACK_INVALID, (error,))
            return (FALLBACK_INVALID, (error,))

        # Validate attribute is None or a string
        if attribute is not None and not isinstance(attribute, str):
            logger.warning(  # type: ignore[unreachable]
                "Invalid attribute type: expected str or None, got %s", type(attribute).__name__
            )
            diagnostic = Diagnostic(
                code=DiagnosticCode.INVALID_ARGUMENT,
                message=f"Invalid attribute type: expected str or None, got {type(attribute).__name__}",
            )
            error = FrozenFluentError(
                str(diagnostic), ErrorCategory.RESOLUTION, diagnostic=diagnostic
            )
            # Strict mode: raise instead of returning fallback
            if self._strict:
                self._raise_strict_error(message_id, FALLBACK_INVALID, (error,))
            return (FALLBACK_INVALID, (error,))

        # Check if message exists
        if message_id not in self._messages:
            logger.warning("Message '%s' not found", message_id)
            diag = ErrorTemplate.message_not_found(message_id)
            error = FrozenFluentError(str(diag), ErrorCategory.REFERENCE, diagnostic=diag)
            # Don't cache missing message errors
            fallback = FALLBACK_MISSING_MESSAGE.format(id=message_id)
            # Strict mode: raise instead of returning fallback
            if self._strict:
                self._raise_strict_error(message_id, fallback, (error,))
            return (fallback, (error,))

        message = self._messages[message_id]

        # Create resolver
        resolver = FluentResolver(
            locale=self._locale,
            messages=self._messages,
            terms=self._terms,
            function_registry=self._function_registry,
            use_isolating=self._use_isolating,
            max_nesting_depth=self._max_nesting_depth,
        )

        # Resolve message (resolver handles all errors internally including cycles)
        # Note: No try-except here. The resolver is designed to collect all expected
        # errors (missing references, type errors, etc.) and return them in the tuple.
        # If a raw KeyError/AttributeError/RuntimeError escapes the resolver, that
        # indicates a bug in the resolver implementation that should be exposed,
        # not swallowed. This follows the principle of failing fast on internal bugs.
        result, errors_tuple = resolver.resolve_message(message, args, attribute)

        if errors_tuple:
            logger.warning(
                "Message resolution errors for '%s': %d error(s)", message_id, len(errors_tuple)
            )
            for err in errors_tuple:
                logger.debug("  - %s: %s", type(err).__name__, err)
            # Strict mode: raise instead of returning fallback-containing result
            if self._strict:
                self._raise_strict_error(message_id, result, errors_tuple)
        else:
            logger.debug("Resolved message '%s': %s", message_id, result[:50])

        # Cache successful resolution (even if there are non-critical errors)
        # Note: In strict mode, we won't reach here if there are errors
        if self._cache is not None:
            self._cache.put(
                message_id, args, attribute, self._locale, self._use_isolating, result, errors_tuple
            )

        return (result, errors_tuple)

    def format_value(
        self, message_id: str, args: Mapping[str, FluentValue] | None = None
    ) -> tuple[str, tuple[FrozenFluentError, ...]]:
        """Format message to string (alias for format_pattern without attribute access).

        This method provides API consistency with FluentLocalization.format_value()
        for users who don't need attribute access. It's an alias for
        format_pattern(message_id, args, attribute=None).

        Args:
            message_id: Message identifier
            args: Variable arguments for interpolation

        Returns:
            Tuple of (formatted_string, errors)
            - formatted_string: Best-effort formatted output (never empty)
            - errors: Tuple of FrozenFluentError instances encountered during resolution (immutable)

        Raises:
            FormattingIntegrityError: In strict mode, if ANY error occurs during formatting

        Note:
            In non-strict mode, this method never raises exceptions. All errors
            are collected and returned in the errors list.

            In strict mode (bundle.strict=True), FormattingIntegrityError is raised
            instead of returning fallback values when errors occur.

        Example:
            >>> bundle.add_resource("welcome = Hello, { $name }!")
            >>> result, errors = bundle.format_value("welcome", {"name": "Alice"})
            >>> assert result == "Hello, Alice!"
            >>> assert errors == ()
        """
        return self.format_pattern(message_id, args, attribute=None)

    def has_message(self, message_id: str) -> bool:
        """Check if message exists.

        Args:
            message_id: Message identifier

        Returns:
            True if message exists in bundle
        """
        with self._rwlock.read():
            return message_id in self._messages

    def has_attribute(self, message_id: str, attribute: str) -> bool:
        """Check if message has specific attribute.

        Args:
            message_id: Message identifier
            attribute: Attribute name

        Returns:
            True if message exists AND has the specified attribute

        Note:
            This method checks if any attribute with the given name exists.
            If duplicate attribute names exist (validation warning), this returns
            True without indicating which definition will be used. See format_pattern
            for resolution semantics (last-wins for duplicates).

        Example:
            >>> bundle.add_resource('''
            ... button = Click
            ...     .tooltip = Click to save
            ... ''')
            >>> bundle.has_message("button")
            True
            >>> bundle.has_attribute("button", "tooltip")
            True
            >>> bundle.has_attribute("button", "missing")
            False
            >>> bundle.has_attribute("nonexistent", "tooltip")
            False
        """
        with self._rwlock.read():
            if message_id not in self._messages:
                return False
            message = self._messages[message_id]
            return any(attr.id.name == attribute for attr in message.attributes)

    def get_message_ids(self) -> list[str]:
        """Get all message IDs in bundle.

        Returns:
            List of message identifiers
        """
        with self._rwlock.read():
            return list(self._messages.keys())

    def get_message_variables(self, message_id: str) -> frozenset[str]:
        """Get all variables required by a message (introspection API).

        This is a value-add feature not present in Mozilla's python-fluent.
        Enables FTL file validation in CI/CD pipelines.

        Args:
            message_id: Message identifier

        Returns:
            Frozen set of variable names (without $ prefix)

        Raises:
            KeyError: If message doesn't exist

        Example:
            >>> bundle.add_resource("greeting = Hello, { $name }!")
            >>> vars = bundle.get_message_variables("greeting")
            >>> assert "name" in vars
        """
        with self._rwlock.read():
            if message_id not in self._messages:
                msg = f"Message '{message_id}' not found"
                raise KeyError(msg)

            return extract_variables(self._messages[message_id])

    def get_all_message_variables(self) -> dict[str, frozenset[str]]:
        """Get variables for all messages in bundle (batch introspection API).

        Convenience method for extracting variables from all messages at once.
        Useful for CI/CD validation pipelines that need to analyze entire
        FTL resources in a single operation.

        This is equivalent to calling get_message_variables() for each message
        ID, but provides a cleaner API for batch operations.

        Returns:
            Dictionary mapping message IDs to their required variable sets.
            Empty dict if bundle has no messages.

        Example:
            >>> bundle.add_resource('''
            ... greeting = Hello, { $name }!
            ... farewell = Goodbye, { $firstName } { $lastName }!
            ... simple = No variables here
            ... ''')
            >>> all_vars = bundle.get_all_message_variables()
            >>> assert all_vars["greeting"] == frozenset({"name"})
            >>> assert all_vars["farewell"] == frozenset({"firstName", "lastName"})
            >>> assert all_vars["simple"] == frozenset()

        See Also:
            - get_message_variables(): Get variables for single message
            - introspect_message(): Get complete metadata (variables + functions + references)

        Note:
            Acquires a single read lock for atomic snapshot of all message variables.
        """
        with self._rwlock.read():
            return {
                message_id: extract_variables(message)
                for message_id, message in self._messages.items()
            }

    def introspect_message(self, message_id: str) -> MessageIntrospection:
        """Get complete introspection data for a message.

        Returns comprehensive metadata about variables, functions, and references
        used in the message. Uses Python 3.13's TypeIs for type-safe results.

        Args:
            message_id: Message identifier

        Returns:
            MessageIntrospection with complete metadata

        Raises:
            KeyError: If message doesn't exist

        Example:
            >>> bundle.add_resource("price = { NUMBER($amount, minimumFractionDigits: 2) }")
            >>> info = bundle.introspect_message("price")
            >>> assert "amount" in info.get_variable_names()
            >>> assert "NUMBER" in info.get_function_names()
        """
        with self._rwlock.read():
            if message_id not in self._messages:
                msg = f"Message '{message_id}' not found"
                raise KeyError(msg)

            return introspect_message(self._messages[message_id])

    def introspect_term(self, term_id: str) -> MessageIntrospection:
        """Get complete introspection data for a term.

        Returns comprehensive metadata about variables, functions, and references
        used in the term. Mirrors introspect_message() for API symmetry.

        Args:
            term_id: Term identifier (without leading dash)

        Returns:
            MessageIntrospection with complete metadata

        Raises:
            KeyError: If term doesn't exist

        Example:
            >>> bundle.add_resource("-brand = { $case -> \\n    [nominative] Firefox\\n    *[other] Firefox\\n}")
            >>> info = bundle.introspect_term("brand")
            >>> assert "case" in info.get_variable_names()
        """
        with self._rwlock.read():
            if term_id not in self._terms:
                msg = f"Term '{term_id}' not found"
                raise KeyError(msg)

            return introspect_message(self._terms[term_id])

    def add_function(self, name: str, func: Callable[..., FluentValue]) -> None:
        """Add custom function to bundle.

        Args:
            name: Function name (UPPERCASE by convention)
            func: Callable function that returns a FluentValue

        Example:
            >>> def CUSTOM(value):
            ...     return value.upper()
            >>> bundle.add_function("CUSTOM", CUSTOM)
        """
        with self._rwlock.write():
            # Copy-on-write: copy the shared registry on first modification
            if not self._owns_registry:
                self._function_registry = self._function_registry.copy()
                self._owns_registry = True
                logger.debug("Registry copied on first add_function")

            self._function_registry.register(func, ftl_name=name)
            logger.debug("Added custom function: %s", name)

            # Invalidate cache (functions changed)
            if self._cache is not None:
                self._cache.clear()
                logger.debug("Cache cleared after add_function")

            # Mark bundle as modified for context manager tracking
            self._modified_in_context = True

    def clear_cache(self) -> None:
        """Clear format cache.

        Call this when you want to force cache invalidation.
        Automatically called by add_resource() and add_function().

        Example:
            >>> bundle = FluentBundle("en", enable_cache=True)
            >>> bundle.add_resource("msg = Hello")
            >>> bundle.format_pattern("msg")  # Caches result
            >>> bundle.clear_cache()  # Manual invalidation
        """
        with self._rwlock.write():
            if self._cache is not None:
                self._cache.clear()
                logger.debug("Cache manually cleared")

            # Mark bundle as modified for context manager tracking
            self._modified_in_context = True

    def get_cache_stats(self) -> dict[str, int | float] | None:
        """Get cache statistics.

        Returns:
            Dict with cache metrics or None if caching disabled.
            Keys: size (int), maxsize (int), hits (int), misses (int),
                  hit_rate (float 0.0-100.0), unhashable_skips (int)

        Example:
            >>> bundle = FluentBundle("en", enable_cache=True)
            >>> bundle.add_resource("msg = Hello")
            >>> bundle.format_pattern("msg", {})  # Cache miss
            >>> bundle.format_pattern("msg", {})  # Cache hit
            >>> stats = bundle.get_cache_stats()
            >>> stats["hits"]
            1
            >>> stats["misses"]
            1
            >>> isinstance(stats["hit_rate"], float)
            True
        """
        if self._cache is not None:
            return self._cache.get_stats()
        return None
