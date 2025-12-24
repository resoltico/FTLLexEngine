"""FluentBundle - Main API for Fluent message formatting.

Python 3.13+. External dependency: Babel (CLDR locale data).
"""

import logging
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING

from ftllexengine.diagnostics import (
    Diagnostic,
    DiagnosticCode,
    ErrorTemplate,
    FluentError,
    FluentReferenceError,
    FluentSyntaxError,
    ValidationResult,
)
from ftllexengine.introspection import extract_variables, introspect_message
from ftllexengine.runtime.cache import FormatCache
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.functions import get_shared_registry
from ftllexengine.runtime.locale_context import LocaleContext
from ftllexengine.runtime.resolver import FluentResolver, FluentValue
from ftllexengine.syntax import Junk, Message, Term
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.validation import validate_resource as _validate_resource_impl

if TYPE_CHECKING:
    from ftllexengine.introspection import MessageIntrospection

logger = logging.getLogger(__name__)

# Default maximum cache entries for format results.
# 1000 entries is sufficient for most applications (typical UI has <500 messages).
DEFAULT_CACHE_SIZE: int = 1000

# Logging truncation limits for error messages.
# Warnings show more context (100 chars) as they're surfaced to users.
# Debug messages are high-volume, shorter (50 chars) keeps logs manageable.
_LOG_TRUNCATE_WARNING: int = 100
_LOG_TRUNCATE_DEBUG: int = 50


class FluentBundle:
    """Fluent message bundle for specific locale.

    Main public API for Fluent localization. Aligned with Mozilla python-fluent
    error handling that returns (result, errors) tuples.

    Thread Safety:
        - format_pattern() and format_value() are thread-safe for concurrent reads.
        - add_resource() and add_function() are NOT thread-safe. These methods
          mutate internal state without locking.
        - Recommended pattern: Complete all add_resource() and add_function() calls
          during initialization before sharing the bundle across threads.
        - If dynamic resource loading is required during concurrent operation,
          use external synchronization (e.g., threading.Lock).

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
    """

    __slots__ = (
        "_cache",
        "_cache_size",
        "_function_registry",
        "_locale",
        "_messages",
        "_parser",
        "_terms",
        "_use_isolating",
    )

    @staticmethod
    def _validate_locale_format(locale: str) -> None:
        """Validate locale code format.

        Checks that locale is non-empty and contains only alphanumeric
        characters with optional underscore or hyphen separators.

        Args:
            locale: Locale code to validate

        Raises:
            ValueError: If locale code is empty or has invalid format
        """
        if not locale:
            msg = "Locale code cannot be empty"
            raise ValueError(msg)

        if not locale.replace("_", "").replace("-", "").isalnum():
            msg = f"Invalid locale code format: '{locale}'"
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

        Raises:
            ValueError: If locale code is empty or has invalid format

        Example:
            >>> # Using default registry (standard functions)
            >>> bundle = FluentBundle("en")
            >>>
            >>> # Using custom registry with additional functions
            >>> from ftllexengine.runtime.functions import create_default_registry
            >>> registry = create_default_registry()
            >>> registry.register(my_custom_func, ftl_name="CUSTOM")
            >>> bundle = FluentBundle("en", functions=registry)
        """
        # Validate locale format
        FluentBundle._validate_locale_format(locale)

        self._locale = locale
        self._use_isolating = use_isolating
        self._messages: dict[str, Message] = {}
        self._terms: dict[str, Term] = {}
        self._parser = FluentParserV1()

        # Function registry: use provided registry (copy it for isolation) or use shared default
        # Using the shared registry avoids re-registering built-in functions for each bundle.
        # The copy() ensures bundles are isolated even when sharing the same source registry.
        if functions is not None:
            self._function_registry = functions.copy()
        else:
            self._function_registry = get_shared_registry().copy()

        # Format cache (opt-in)
        self._cache: FormatCache | None = None
        self._cache_size = cache_size
        if enable_cache:
            self._cache = FormatCache(maxsize=cache_size)

        logger.info(
            "FluentBundle initialized for locale: %s (use_isolating=%s, cache=%s)",
            locale,
            use_isolating,
            "enabled" if enable_cache else "disabled",
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
            int: Maximum cache entries (0 if caching disabled)

        Example:
            >>> bundle = FluentBundle("en", enable_cache=True, cache_size=500)
            >>> bundle.cache_size
            500
            >>> bundle_no_cache = FluentBundle("en")
            >>> bundle_no_cache.cache_size
            0

        Note:
            Returns configured size even if cache is disabled.
            Use cache_enabled to check if caching is active.
        """
        return self._cache_size if self.cache_enabled else 0

    @classmethod
    def for_system_locale(
        cls,
        *,
        use_isolating: bool = True,
        enable_cache: bool = False,
        cache_size: int = DEFAULT_CACHE_SIZE,
        functions: FunctionRegistry | None = None,
    ) -> "FluentBundle":
        """Factory method to create a FluentBundle using the system locale.

        Detects and uses the current system locale (from LC_ALL, LC_MESSAGES,
        LANG environment variables, or OS settings).

        Args:
            use_isolating: Wrap interpolated values in Unicode bidi isolation marks
            enable_cache: Enable format caching for performance
            cache_size: Maximum cache entries when caching enabled
            functions: Custom FunctionRegistry to use (default: standard registry)

        Returns:
            Configured FluentBundle instance for system locale

        Raises:
            RuntimeError: If system locale cannot be determined

        Example:
            >>> bundle = FluentBundle.for_system_locale()
            >>> bundle.locale  # Returns detected system locale
            'en_US'
        """
        import locale as locale_module  # noqa: PLC0415

        # Get system locale
        system_locale, _ = locale_module.getlocale()

        if not system_locale:
            # Try alternative detection methods via environment variables
            import os  # noqa: PLC0415

            system_locale = os.environ.get("LC_ALL") or os.environ.get(
                "LC_MESSAGES"
            ) or os.environ.get("LANG")

        if not system_locale:
            msg = (
                "Could not determine system locale. "
                "Set LC_ALL, LC_MESSAGES, or LANG environment variable."
            )
            raise RuntimeError(msg)

        # Normalize locale code (convert POSIX format to Fluent-compatible)
        # e.g., "en_US.UTF-8" -> "en_US"
        if "." in system_locale:
            system_locale = system_locale.split(".")[0]

        return cls(
            system_locale,
            use_isolating=use_isolating,
            enable_cache=enable_cache,
            cache_size=cache_size,
            functions=functions,
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

    def __enter__(self) -> "FluentBundle":
        """Enter context manager.

        Enables use of FluentBundle with 'with' statement for automatic
        resource cleanup on exit.

        Returns:
            Self (the FluentBundle instance)

        Example:
            >>> with FluentBundle("en_US", enable_cache=True) as bundle:
            ...     bundle.add_resource("hello = Hello")
            ...     result = bundle.format_pattern("hello")
            ... # Cache automatically cleared on exit
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Exit context manager with cleanup.

        Clears cache and resets internal state for clean exit.
        Does not suppress exceptions.

        Args:
            exc_type: Exception type (if any)
            exc_val: Exception value (if any)
            exc_tb: Exception traceback (if any)
        """
        # Clear cache if enabled
        if self._cache is not None:
            self._cache.clear()

        # Clear registries for clean exit
        self._messages.clear()
        self._terms.clear()

        logger.debug("FluentBundle context exited for locale: %s", self._locale)

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
    ) -> None:
        """Add FTL resource to bundle.

        Parses FTL source and adds messages/terms to registry.

        Args:
            source: FTL file content [positional-only]
            source_path: Optional path to source file for better error messages
                        (e.g., "locales/lv/ui.ftl")

        Raises:
            FluentSyntaxError: On critical parse error

        Note:
            Non-critical syntax errors become Junk entries and are logged.
            Parser continues after errors (robustness principle).
        """
        try:
            resource = self._parser.parse(source)

            # Register messages and terms using structural pattern matching
            junk_count = 0
            for entry in resource.entries:
                match entry:
                    case Message():
                        self._messages[entry.id.name] = entry
                        logger.debug("Registered message: %s", entry.id.name)
                    case Term():
                        self._terms[entry.id.name] = entry
                        logger.debug("Registered term: %s", entry.id.name)
                    case Junk():
                        # Count junk entries, log at debug level (non-critical parse artifacts)
                        junk_count += 1
                        # Security: Use ascii() to escape control characters in untrusted content
                        # Prevents log injection via ANSI escape codes or other control chars
                        # Include source path in error message if available
                        if source_path:
                            logger.warning(
                                "Syntax error in %s: %s",
                                source_path,
                                ascii(entry.content[:_LOG_TRUNCATE_WARNING]),
                            )
                        else:
                            logger.debug(
                                "Junk entry (non-critical): %s",
                                ascii(entry.content[:_LOG_TRUNCATE_DEBUG]),
                            )
                    case _:
                        # Comments or other entry types don't need registration
                        pass

            # Log summary with file context
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

        except FluentSyntaxError as e:
            if source_path:
                logger.error("Failed to parse resource %s: %s", source_path, e)
            else:
                logger.error("Failed to parse resource: %s", e)
            raise

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
        return _validate_resource_impl(source, parser=self._parser)

    def format_pattern(
        self,
        message_id: str,
        /,
        args: Mapping[str, FluentValue] | None = None,
        *,
        attribute: str | None = None,
    ) -> tuple[str, tuple[FluentError, ...]]:
        """Format message to string with error reporting.

        Mozilla python-fluent aligned API that returns both the formatted
        string and any errors encountered during resolution.

        Args:
            message_id: Message identifier [positional-only]
            args: Variable arguments for interpolation
            attribute: Attribute name (optional, keyword-only)

        Returns:
            Tuple of (formatted_string, errors)
            - formatted_string: Best-effort formatted output (never empty)
            - errors: Tuple of exceptions encountered during resolution (immutable)

        Note:
            This method handles expected formatting errors gracefully. All
            anticipated errors (missing messages, variables, references) are
            collected and returned in the errors list. The formatted string
            always contains a readable fallback value per Fluent specification.

        Examples:
            >>> # Successful formatting
            >>> result, errors = bundle.format_pattern("hello")
            >>> assert result == 'Sveiki, pasaule!'
            >>> assert errors == ()

            >>> # Missing variable - returns fallback and error
            >>> bundle.add_resource('msg = Hello { $name }!')
            >>> result, errors = bundle.format_pattern("msg", {})
            >>> assert result == 'Hello {$name}!'  # Readable fallback
            >>> assert len(errors) == 1
            >>> assert isinstance(errors[0], FluentReferenceError)

            >>> # Attribute access
            >>> result, errors = bundle.format_pattern("button-save", attribute="tooltip")
            >>> assert result == 'Saglabā pašreizējo ierakstu datubāzē'
            >>> assert errors == ()
        """
        # Check cache first (if enabled)
        if self._cache is not None:
            cached = self._cache.get(message_id, args, attribute, self._locale)
            if cached is not None:
                return cached

        # Validate message_id is non-empty string
        if not message_id or not isinstance(message_id, str):
            logger.warning("Invalid message ID: empty or non-string")
            diagnostic = Diagnostic(
                code=DiagnosticCode.MESSAGE_NOT_FOUND,
                message="Invalid message ID: empty or non-string",
            )
            error = FluentReferenceError(diagnostic)
            # Don't cache errors
            return ("{???}", (error,))

        # Check if message exists
        if message_id not in self._messages:
            logger.warning("Message '%s' not found", message_id)
            error = FluentReferenceError(ErrorTemplate.message_not_found(message_id))
            # Don't cache missing message errors
            return (f"{{{message_id}}}", (error,))

        message = self._messages[message_id]

        # Create resolver
        resolver = FluentResolver(
            locale=self._locale,
            messages=self._messages,
            terms=self._terms,
            function_registry=self._function_registry,
            use_isolating=self._use_isolating,
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
        else:
            logger.debug("Resolved message '%s': %s", message_id, result[:50])

        # Cache successful resolution (even if there are non-critical errors)
        if self._cache is not None:
            self._cache.put(message_id, args, attribute, self._locale, (result, errors_tuple))

        return (result, errors_tuple)

    def format_value(
        self, message_id: str, args: Mapping[str, FluentValue] | None = None
    ) -> tuple[str, tuple[FluentError, ...]]:
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
            - errors: Tuple of FluentError instances encountered during resolution (immutable)

        Note:
            This method NEVER raises exceptions. All errors are collected
            and returned in the errors list.

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
        return message_id in self._messages

    def get_message_ids(self) -> list[str]:
        """Get all message IDs in bundle.

        Returns:
            List of message identifiers
        """
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
        """
        return {
            message_id: self.get_message_variables(message_id)
            for message_id in self.get_message_ids()
        }

    def introspect_message(self, message_id: str) -> "MessageIntrospection":
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
        if message_id not in self._messages:
            msg = f"Message '{message_id}' not found"
            raise KeyError(msg)

        return introspect_message(self._messages[message_id])

    def add_function(self, name: str, func: Callable[..., str]) -> None:
        """Add custom function to bundle.

        Args:
            name: Function name (UPPERCASE by convention)
            func: Callable function that returns a string

        Example:
            >>> def CUSTOM(value):
            ...     return value.upper()
            >>> bundle.add_function("CUSTOM", CUSTOM)
        """
        self._function_registry.register(func, ftl_name=name)
        logger.debug("Added custom function: %s", name)

        # Invalidate cache (functions changed)
        if self._cache is not None:
            self._cache.clear()
            logger.debug("Cache cleared after add_function")

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
        if self._cache is not None:
            self._cache.clear()
            logger.debug("Cache manually cleared")

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
