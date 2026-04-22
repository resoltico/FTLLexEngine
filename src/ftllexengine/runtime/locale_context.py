"""Locale context for thread-safe, bundle-scoped formatting.

This module provides locale-aware formatting without global state mutation.
Uses Babel for CLDR-compliant number, date, and currency formatting.

Babel Dependency:
    This module requires Babel for CLDR data. Import is deferred to function call
    time to support parser-only installations. Clear error message provided when
    Babel is missing.

Architecture:
    - LocaleContext: Immutable locale configuration container
    - Formatters use Babel (thread-safe, CLDR-based)
    - No dependency on Python's locale module (avoids global state)
    - Locale isolation: Formatting never affects global state

Instance Sharing:
    LocaleContext instances are cached and shared between FluentBundle instances
    for performance (Flyweight pattern). Since LocaleContext is frozen=True,
    sharing is safe. "Locale isolation" refers to the absence of global state
    mutation, not instance-level isolation between bundles.

Design Principles:
    - Explicit over implicit (locale always visible)
    - Immutable by default (frozen dataclass)
    - Thread-safe (no shared mutable state)
    - CLDR-compliant (matches Intl.NumberFormat semantics)
    - Explicit error handling (no silent fallbacks)

Python 3.13+. Uses Babel for i18n.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock
from typing import TYPE_CHECKING, ClassVar, Literal

from ftllexengine.constants import (
    MAX_LOCALE_CACHE_SIZE,
    MAX_LOCALE_CODE_LENGTH,
)
from ftllexengine.core.babel_compat import (
    get_locale_class,
    get_unknown_locale_error_class,
    require_babel,
)
from ftllexengine.core.locale_utils import require_locale_code
from ftllexengine.runtime.locale_formatting import (
    format_currency_for_locale,
    format_datetime_for_locale,
    format_number_for_locale,
    get_iso_code_pattern_for_locale,
)

if TYPE_CHECKING:
    from datetime import date, datetime
    from decimal import Decimal

    from babel import Locale

    from ftllexengine.core.semantic_types import LocaleCode

__all__ = ["LocaleContext"]

logger = logging.getLogger(__name__)

# Sentinel for factory method authorization.
# Only create() and create_or_raise() pass this token to __init__.
_FACTORY_TOKEN = object()


@dataclass(frozen=True, slots=True)
class LocaleContext:
    """Immutable locale configuration for formatting operations.

    Provides thread-safe, locale-specific formatting for numbers, dates, and currency
    without mutating global state. Each FluentBundle owns its LocaleContext.

    Use LocaleContext.create() factory to construct instances with proper validation.
    Direct construction via __init__ raises TypeError (enforced by sentinel guard).

    Cache Management:
        LocaleContext uses an internal LRU cache for instance reuse. Use class
        methods for cache management:
        - LocaleContext.clear_cache(): Clear all cached instances
        - LocaleContext.cache_size(): Get current cache size
        - LocaleContext.cache_info(): Get detailed cache statistics

    Examples:
        >>> from decimal import Decimal  # doctest: +SKIP
        >>> ctx = LocaleContext.create('en-US')  # doctest: +SKIP
        >>> ctx.format_number(Decimal('1234.5'), use_grouping=True)  # doctest: +SKIP
        '1,234.5'

        >>> ctx = LocaleContext.create('lv-LV')  # doctest: +SKIP
        >>> ctx.format_number(Decimal('1234.5'), use_grouping=True)  # doctest: +SKIP
        '1 234,5'

        Unknown locales fall back to `en_US` formatting rules with a warning:
        >>> ctx = LocaleContext.create('xx-UNKNOWN')  # doctest: +SKIP
        >>> ctx.locale_code  # doctest: +SKIP
        'xx_unknown'
        >>> ctx.is_fallback  # Programmatic detection of fallback  # doctest: +SKIP
        True

    Thread Safety:
        LocaleContext is immutable and thread-safe. Multiple threads can
        share the same instance without synchronization. Cache operations
        are protected by Lock.

    Babel vs locale module:
        - Babel: Thread-safe, CLDR-based, 600+ locales
        - locale: Thread-unsafe, platform-dependent, requires setlocale()
    """

    # Class-level cache for LocaleContext instances (identity caching)
    # OrderedDict provides LRU semantics with O(1) operations
    # Note: ClassVar is excluded from dataclass fields
    _cache: ClassVar[OrderedDict[str, LocaleContext]] = OrderedDict()
    _cache_lock: ClassVar[Lock] = Lock()

    locale_code: LocaleCode
    _babel_locale: Locale
    is_fallback: bool = False
    _factory_token: object = field(
        default=None, repr=False, compare=False, hash=False
    )

    def __post_init__(self) -> None:
        """Validate construction came from factory method."""
        if self._factory_token is not _FACTORY_TOKEN:
            msg = (
                "Use LocaleContext.create() or LocaleContext.create_or_raise() "
                "instead of direct construction"
            )
            raise TypeError(msg)

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the locale context cache.

        Use this method to free memory or reset state in tests.
        Thread-safe via Lock.

        Example:
            >>> LocaleContext.create('en-US')  # Cached  # doctest: +SKIP
            >>> LocaleContext.cache_size()  # doctest: +SKIP
            1
            >>> LocaleContext.clear_cache()  # doctest: +SKIP
            >>> LocaleContext.cache_size()  # doctest: +SKIP
            0
        """
        with cls._cache_lock:
            cls._cache.clear()

    @classmethod
    def cache_size(cls) -> int:
        """Get current number of cached LocaleContext instances.

        Returns:
            Number of cached instances

        Example:
            >>> LocaleContext.clear_cache()  # doctest: +SKIP
            >>> LocaleContext.create('en-US')  # doctest: +SKIP
            >>> LocaleContext.create('de-DE')  # doctest: +SKIP
            >>> LocaleContext.cache_size()  # doctest: +SKIP
            2
        """
        with cls._cache_lock:
            return len(cls._cache)

    @classmethod
    def cache_info(cls) -> dict[str, int | tuple[str, ...]]:
        """Get detailed cache statistics.

        Returns:
            Dictionary with cache statistics:
            - size: Current number of cached instances
            - max_size: Maximum cache size
            - locales: Tuple of cached locale codes (LRU order)

        Example:
            >>> LocaleContext.clear_cache()  # doctest: +SKIP
            >>> LocaleContext.create('en-US')  # doctest: +SKIP
            >>> LocaleContext.cache_info()  # doctest: +SKIP
            {'size': 1, 'max_size': 128, 'locales': ('en_us',)}
        """
        with cls._cache_lock:
            return {
                "size": len(cls._cache),
                "max_size": MAX_LOCALE_CACHE_SIZE,
                "locales": tuple(cls._cache.keys()),
            }

    @classmethod
    def create(cls, locale_code: str) -> LocaleContext:
        """Create LocaleContext with graceful fallback for unknown locales.

        Factory method that validates and canonicalizes the locale boundary before
        construction. Structurally invalid boundary values are rejected immediately.
        Unknown but structurally valid locales log a warning and fall back to en_US
        formatting rules. Use create_or_raise() if unknown locales must fail fast.

        Thread Safety:
            Uses OrderedDict with Lock for thread-safe LRU caching.
            Concurrent calls with same locale_code return the same instance.

        Args:
            locale_code: Locale identifier (e.g., 'en-US', 'lv-LV', 'de-DE')

        Returns:
            LocaleContext instance with canonical lowercase POSIX locale_code.
            Unknown locales use en_US formatting while retaining the requested
            canonical locale_code and setting is_fallback=True.

        Examples:
            >>> ctx = LocaleContext.create('en-US')  # doctest: +SKIP
            >>> ctx.locale_code  # doctest: +SKIP
            'en_us'

            >>> ctx = LocaleContext.create('xx_UNKNOWN')  # Unknown locale  # doctest: +SKIP
            >>> ctx.locale_code  # doctest: +SKIP
            'xx_unknown'
            Formatting still uses `en_US` rules, with a warning logged:
        """
        normalized_locale = require_locale_code(locale_code, "locale_code")

        # Warn for locale codes exceeding typical BCP 47 limit
        if len(normalized_locale) > MAX_LOCALE_CODE_LENGTH:
            logger.warning(
                "Locale code exceeds typical BCP 47 length of %d characters: "
                "'%s...' (%d characters). Attempting Babel validation.",
                MAX_LOCALE_CODE_LENGTH,
                normalized_locale[:50],
                len(normalized_locale),
            )

        # Thread-safe LRU caching with identity preservation
        with cls._cache_lock:
            if normalized_locale in cls._cache:
                # Move to end (mark as recently used) and return cached instance
                cls._cache.move_to_end(normalized_locale)
                return cls._cache[normalized_locale]

        require_babel("LocaleContext.create")
        locale_class = get_locale_class()
        unknown_locale_error_class = get_unknown_locale_error_class()

        # Create new instance (Locale.parse is thread-safe)
        used_fallback = False
        try:
            babel_locale = locale_class.parse(normalized_locale)
        except unknown_locale_error_class as e:
            if len(normalized_locale) > MAX_LOCALE_CODE_LENGTH:
                logger.warning(
                    "Unknown locale '%s' (exceeds %d chars): %s. Falling back to en_US",
                    normalized_locale,
                    MAX_LOCALE_CODE_LENGTH,
                    e,
                )
            else:
                logger.warning(
                    "Unknown locale '%s': %s. Falling back to en_US",
                    normalized_locale,
                    e,
                )
            babel_locale = locale_class.parse("en_US")
            used_fallback = True
        except ValueError as e:
            if len(normalized_locale) > MAX_LOCALE_CODE_LENGTH:
                logger.warning(
                    "Invalid locale format '%s' (exceeds %d chars): %s. Falling back to en_US",
                    normalized_locale,
                    MAX_LOCALE_CODE_LENGTH,
                    e,
                )
            else:
                logger.warning(
                    "Invalid locale format '%s': %s. Falling back to en_US",
                    normalized_locale,
                    e,
                )
            babel_locale = locale_class.parse("en_US")
            used_fallback = True

        ctx = cls(
            locale_code=normalized_locale,
            _babel_locale=babel_locale,
            is_fallback=used_fallback,
            _factory_token=_FACTORY_TOKEN,
        )

        # Add to cache with lock (double-check pattern for thread safety)
        with cls._cache_lock:
            if normalized_locale in cls._cache:
                return cls._cache[normalized_locale]

            # Evict LRU if cache is full
            if len(cls._cache) >= MAX_LOCALE_CACHE_SIZE:
                cls._cache.popitem(last=False)

            cls._cache[normalized_locale] = ctx
            return ctx

    @classmethod
    def create_or_raise(cls, locale_code: str) -> LocaleContext:
        """Create LocaleContext or raise on validation failure.

        Strict validation method that raises ValueError for invalid locales.
        Use this in tests or when silent fallback is not acceptable.

        Validates the locale code strictly via Babel, then delegates to
        ``create()`` for cache lookup and population. This ensures that:
        - Invalid locales raise ValueError immediately (no silent fallback).
        - Valid locales are cached and reused, matching ``create()`` semantics.
        - Subsequent ``create()`` calls for the same locale hit the cache.

        Args:
            locale_code: Locale identifier (e.g., 'en-US', 'lv-LV', 'de-DE')

        Returns:
            LocaleContext instance with valid locale (cached via ``create()``)

        Raises:
            ValueError: If locale code is invalid or unknown

        Examples:
            >>> ctx = LocaleContext.create_or_raise('en-US')  # doctest: +SKIP
            >>> ctx.locale_code  # doctest: +SKIP
            'en_us'

            >>> LocaleContext.create_or_raise(  # doctest: +IGNORE_EXCEPTION_DETAIL, +SKIP
            ...     'invalid-locale'
            ... )
            Traceback (most recent call last):
                ...
            ValueError: Unknown locale identifier 'invalid-locale'
        """
        require_babel("LocaleContext.create_or_raise")
        locale_class = get_locale_class()
        unknown_locale_error_class = get_unknown_locale_error_class()

        # Validate strictly — raises on unknown or malformed locale.
        # locale_class.parse() is called only for validation here; create()
        # will use the cache or re-parse as needed. On the first call for a
        # locale, parse() executes twice (once here, once inside create() on
        # cache miss). On subsequent calls, create() returns the cached
        # instance without re-parsing, making this effectively O(1) after
        # the first invocation. This is the correct trade-off: correctness
        # and cache coherence take precedence over avoiding one extra parse
        # on first use.
        normalized_locale = require_locale_code(locale_code, "locale_code")

        try:
            locale_class.parse(normalized_locale)
        except unknown_locale_error_class as e:
            msg = f"Unknown locale identifier '{normalized_locale}': {e}"
            raise ValueError(msg) from None
        except ValueError as e:
            msg = f"Invalid locale format '{normalized_locale}': {e}"
            raise ValueError(msg) from None

        # Locale is valid — delegate to create() for proper cache management.
        # create() will find the key in cache (populated by the parse above
        # if another thread raced) or re-parse and insert. Either way the
        # result is identical to create(locale_code) for a valid locale.
        return cls.create(normalized_locale)

    @property
    def babel_locale(self) -> Locale:
        """Get pre-validated Babel Locale object for this context.

        Returns:
            Babel Locale instance (validated during construction)
        """
        return self._babel_locale

    def format_number(
        self,
        value: int | Decimal,
        *,
        minimum_fraction_digits: int = 0,
        maximum_fraction_digits: int = 3,
        use_grouping: bool = True,
        pattern: str | None = None,
        numbering_system: str = "latn",
    ) -> str:
        """Format number with locale-specific separators."""
        return format_number_for_locale(
            locale_code=self.locale_code,
            babel_locale=self.babel_locale,
            value=value,
            minimum_fraction_digits=minimum_fraction_digits,
            maximum_fraction_digits=maximum_fraction_digits,
            use_grouping=use_grouping,
            pattern=pattern,
            numbering_system=numbering_system,
        )

    def format_datetime(
        self,
        value: date | datetime | str,
        *,
        date_style: Literal["short", "medium", "long", "full"] = "medium",
        time_style: Literal["short", "medium", "long", "full"] | None = None,
        pattern: str | None = None,
    ) -> str:
        """Format datetime with locale-specific formatting."""
        return format_datetime_for_locale(
            locale_code=self.locale_code,
            babel_locale=self.babel_locale,
            value=value,
            date_style=date_style,
            time_style=time_style,
            pattern=pattern,
        )

    def format_currency(
        self,
        value: int | Decimal,
        *,
        currency: str,
        currency_display: Literal["symbol", "code", "name"] = "symbol",
        pattern: str | None = None,
        use_grouping: bool = True,
        currency_digits: bool = True,
        numbering_system: str = "latn",
    ) -> str:
        """Format currency with locale-specific rules."""
        return format_currency_for_locale(
            locale_code=self.locale_code,
            babel_locale=self.babel_locale,
            value=value,
            currency=currency,
            currency_display=currency_display,
            pattern=pattern,
            use_grouping=use_grouping,
            currency_digits=currency_digits,
            numbering_system=numbering_system,
            debug_logger=logger,
        )

    def _get_iso_code_pattern(self) -> str | None:
        """Get CLDR pattern for ISO currency code display."""
        return get_iso_code_pattern_for_locale(
            locale_code=self.locale_code,
            babel_locale=self.babel_locale,
            debug_logger=logger,
        )
