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
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from threading import Lock
from typing import TYPE_CHECKING, ClassVar, Literal

from ftllexengine.constants import (
    FALLBACK_FUNCTION_ERROR,
    MAX_FORMAT_DIGITS,
    MAX_LOCALE_CACHE_SIZE,
    MAX_LOCALE_CODE_LENGTH,
)
from ftllexengine.core.babel_compat import (
    get_babel_dates,
    get_babel_numbers,
    get_locale_class,
    get_unknown_locale_error_class,
    require_babel,
)
from ftllexengine.core.locale_utils import require_locale_code
from ftllexengine.diagnostics import ErrorCategory, FrozenErrorContext, FrozenFluentError
from ftllexengine.diagnostics.templates import ErrorTemplate

if TYPE_CHECKING:
    from babel import Locale

    from ftllexengine.localization.types import LocaleCode

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
        >>> from decimal import Decimal
        >>> ctx = LocaleContext.create('en-US')
        >>> ctx.format_number(Decimal('1234.5'), use_grouping=True)
        '1,234.5'

        >>> ctx = LocaleContext.create('lv-LV')
        >>> ctx.format_number(Decimal('1234.5'), use_grouping=True)
        '1 234,5'

        >>> # Unknown locales fall back to en_US formatting rules with a warning
        >>> ctx = LocaleContext.create('xx-UNKNOWN')
        >>> ctx.locale_code
        'xx_unknown'
        >>> ctx.is_fallback  # Programmatic detection of fallback
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
            >>> LocaleContext.create('en-US')  # Cached
            >>> LocaleContext.cache_size()
            1
            >>> LocaleContext.clear_cache()
            >>> LocaleContext.cache_size()
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
            >>> LocaleContext.clear_cache()
            >>> LocaleContext.create('en-US')
            >>> LocaleContext.create('de-DE')
            >>> LocaleContext.cache_size()
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
            >>> LocaleContext.clear_cache()
            >>> LocaleContext.create('en-US')
            >>> LocaleContext.cache_info()
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
            >>> ctx = LocaleContext.create('en-US')
            >>> ctx.locale_code
            'en_us'

            >>> ctx = LocaleContext.create('xx_UNKNOWN')  # Unknown locale
            >>> ctx.locale_code
            'xx_unknown'
            >>> # But formatting uses en_US rules (with warning logged)
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
            >>> ctx = LocaleContext.create_or_raise('en-US')
            >>> ctx.locale_code
            'en_us'

            >>> LocaleContext.create_or_raise('invalid-locale')  # doctest: +IGNORE_EXCEPTION_DETAIL
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
        """Format number with locale-specific separators.

        Implements Fluent NUMBER function semantics using Babel.

        Args:
            value: Number to format (int or Decimal). float is not accepted;
                use Decimal(str(float_val)) to convert at system boundaries.
            minimum_fraction_digits: Minimum decimal places (default: 0)
            maximum_fraction_digits: Maximum decimal places (default: 3)
            use_grouping: Use thousands separator (default: True)
            pattern: Custom number pattern (overrides other parameters)
            numbering_system: CLDR numbering system identifier (default: "latn").
                Controls which numeral glyphs are used in the output.
                Examples: "latn" (0-9), "arab" (Arabic-Indic), "deva" (Devanagari).

        Returns:
            Formatted number string according to locale rules

        Examples:
            >>> ctx = LocaleContext.create('en-US')
            >>> from decimal import Decimal
            >>> ctx.format_number(Decimal('1234.5'))
            '1,234.5'

            >>> ctx = LocaleContext.create('de-DE')
            >>> ctx.format_number(Decimal('1234.5'))
            '1.234,5'

            >>> ctx = LocaleContext.create('lv-LV')
            >>> ctx.format_number(Decimal('1234.5'))
            '1 234,5'

            >>> ctx = LocaleContext.create('en-US')
            >>> ctx.format_number(Decimal('-1234.56'), pattern="#,##0.00;(#,##0.00)")
            '(1,234.56)'

        CLDR Compliance:
            Uses Babel's format_decimal() which implements CLDR rules.
            Matches Intl.NumberFormat behavior in JavaScript.
        """
        # Validate digit parameters to prevent DoS via unbounded string allocation
        if not 0 <= minimum_fraction_digits <= MAX_FORMAT_DIGITS:
            msg = (
                f"minimum_fraction_digits must be 0-{MAX_FORMAT_DIGITS}, "
                f"got {minimum_fraction_digits}"
            )
            raise ValueError(msg)
        if not 0 <= maximum_fraction_digits <= MAX_FORMAT_DIGITS:
            msg = (
                f"maximum_fraction_digits must be 0-{MAX_FORMAT_DIGITS}, "
                f"got {maximum_fraction_digits}"
            )
            raise ValueError(msg)
        # When minimum exceeds maximum (e.g., minimumFractionDigits: 4 with
        # default maximumFractionDigits: 3), clamp maximum up to minimum.
        # Matches JavaScript Intl.NumberFormat semantics: specifying only
        # minimumFractionDigits=4 should yield 4 decimal places, not an error.
        maximum_fraction_digits = max(maximum_fraction_digits, minimum_fraction_digits)

        babel_numbers = get_babel_numbers()

        try:
            # Use custom pattern if provided.
            if pattern is not None:
                return str(
                    babel_numbers.format_decimal(
                        value,
                        format=pattern,
                        locale=self.babel_locale,
                        numbering_system=numbering_system,
                    )
                )

            # Build format pattern from parameters.
            # '#,##0' = integer with grouping; '0' = integer without grouping.
            # '#,##0.0##' = 1-3 decimal places with grouping; '0.00' = fixed 2.
            integer_part = "#,##0" if use_grouping else "0"

            if maximum_fraction_digits == 0:
                format_pattern = integer_part
            elif minimum_fraction_digits == maximum_fraction_digits:
                decimal_part = "0" * minimum_fraction_digits
                format_pattern = f"{integer_part}.{decimal_part}"
            else:
                required = "0" * minimum_fraction_digits
                optional = "#" * (maximum_fraction_digits - minimum_fraction_digits)
                format_pattern = f"{integer_part}.{required}{optional}"

            # Babel's decimal_quantization=True (default) applies ROUND_HALF_EVEN,
            # which is the IEEE 754 / CLDR-neutral rounding mode.
            return str(
                babel_numbers.format_decimal(
                    value,
                    format=format_pattern,
                    locale=self.babel_locale,
                    numbering_system=numbering_system,
                )
            )

        except (ValueError, TypeError, InvalidOperation, AttributeError, KeyError) as e:
            # Formatting failed - raise FrozenFluentError with fallback value
            # The resolver will catch this error, collect it, and use the fallback
            fallback = str(value)
            diagnostic = ErrorTemplate.formatting_failed("NUMBER", str(value), str(e))
            context = FrozenErrorContext(
                input_value=str(value),
                locale_code=self.locale_code,
                parse_type="number",
                fallback_value=fallback,
            )
            raise FrozenFluentError(
                str(diagnostic), ErrorCategory.FORMATTING, diagnostic=diagnostic, context=context
            ) from e

    def format_datetime(
        self,
        value: date | datetime | str,
        *,
        date_style: Literal["short", "medium", "long", "full"] = "medium",
        time_style: Literal["short", "medium", "long", "full"] | None = None,
        pattern: str | None = None,
    ) -> str:
        """Format datetime with locale-specific formatting.

        Implements Fluent DATETIME function semantics using Babel.

        Args:
            value: date, datetime, or ISO 8601 string. FluentValue includes both
                date and datetime, so both are accepted. Strings are converted via
                datetime.fromisoformat() which accepts formats like:
                - "2025-10-27" (date only, time defaults to 00:00:00)
                - "2025-10-27T14:30:00" (date and time)
                - "2025-10-27T14:30:00+00:00" (with timezone)

                date objects (without time): for date-only formatting (time_style=None),
                formatted directly. When time_style is also requested, the date is
                promoted to midnight datetime (00:00:00, no tzinfo) so Babel can
                format the time component. This is the natural behavior for a calendar
                date with no intrinsic time.
            date_style: Date format style (default: "medium")
            time_style: Time format style (default: None - date only)
            pattern: Custom datetime pattern (overrides style parameters)

        Returns:
            Formatted datetime string according to locale rules

        Raises:
            FrozenFluentError: If string value is not valid ISO 8601 format
                (category=FORMATTING)

        Examples:
            >>> from datetime import date, datetime, UTC
            >>> ctx = LocaleContext.create('en-US')
            >>> dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)
            >>> ctx.format_datetime(dt, date_style='short')
            '10/27/25'

            >>> ctx = LocaleContext.create('de-DE')
            >>> ctx.format_datetime(dt, date_style='short')
            '27.10.25'

            >>> ctx = LocaleContext.create('en-US')
            >>> ctx.format_datetime(dt, pattern='yyyy-MM-dd')
            '2025-10-27'

            >>> ctx = LocaleContext.create('en-US')
            >>> ctx.format_datetime(date(2025, 10, 27), date_style='short')
            '10/27/25'

        CLDR Compliance:
            Uses Babel's format_datetime() which implements CLDR rules.
            Matches Intl.DateTimeFormat behavior in JavaScript.
        """
        babel_dates = get_babel_dates()

        # Type narrowing: produce a datetime for all paths.
        # datetime must be checked before date because datetime IS a date subtype;
        # isinstance(some_datetime, date) is True, so order matters here.
        dt_value: datetime | date

        if isinstance(value, str):
            try:
                dt_value = datetime.fromisoformat(value)
            except ValueError as e:
                # Invalid datetime string - raise FrozenFluentError with fallback
                # This ensures consistent error handling across all format_* methods
                fallback = FALLBACK_FUNCTION_ERROR.format(name="DATETIME")
                diagnostic = ErrorTemplate.formatting_failed(
                    "DATETIME", value, "not ISO 8601 format"
                )
                context = FrozenErrorContext(
                    input_value=value,
                    locale_code=self.locale_code,
                    parse_type="datetime",
                    fallback_value=fallback,
                )
                raise FrozenFluentError(
                    str(diagnostic), ErrorCategory.FORMATTING,
                    diagnostic=diagnostic, context=context
                ) from e
        elif isinstance(value, datetime):
            # datetime is a subtype of date — must check datetime first
            dt_value = value
        else:
            # Plain date object.
            dt_value = value

        # Promote plain date to midnight datetime when a time component is needed.
        # babel_dates.format_datetime() and format_time() require a datetime, not
        # a bare date. A calendar date with no intrinsic time promotes to 00:00:00
        # (no tzinfo — the date carried no timezone, so none is inferred).
        if isinstance(dt_value, date) and not isinstance(dt_value, datetime) and (
            time_style is not None or pattern is not None
        ):
            dt_value = datetime(  # noqa: DTZ001 - date carries no tz; midnight promotion is explicitly naive
                dt_value.year, dt_value.month, dt_value.day
            )

        try:
            # Use custom pattern if provided
            if pattern is not None:
                return str(
                    babel_dates.format_datetime(
                        dt_value,
                        format=pattern,
                        locale=self.babel_locale,
                    )
                )

            # Map Fluent styles to Babel format strings
            if time_style:
                # Both date and time - use locale's dateTimeFormat to combine
                date_str = babel_dates.format_date(
                    dt_value, format=date_style, locale=self.babel_locale
                )
                time_str = babel_dates.format_time(
                    dt_value, format=time_style, locale=self.babel_locale
                )
                # Get locale's dateTimeFormat pattern for combining date and time
                # Pattern uses {0} for time and {1} for date per CLDR spec
                # Use multi-level fallback: requested style -> medium -> short -> hardcoded
                #
                # Ultimate fallback "{1} {0}" rationale:
                # - {1} = date, {0} = time per CLDR convention
                # - Space separator is universally acceptable (no locale uses no separator)
                # - date-before-time order is most common globally (ISO 8601, CJK, most of Europe)
                # - For locales where time-before-date is preferred (e.g., some EN variants),
                #   Babel should always provide CLDR data, so this fallback rarely triggers
                datetime_pattern = (
                    self.babel_locale.datetime_formats.get(date_style)
                    or self.babel_locale.datetime_formats.get("medium")
                    or self.babel_locale.datetime_formats.get("short")
                    or "{1} {0}"  # Ultimate fallback (Western LTR: date space time)
                )
                # DateTimePattern objects have format() method, strings use str.format()
                if hasattr(datetime_pattern, "format"):
                    return str(datetime_pattern.format(time_str, date_str))
                return str(datetime_pattern).format(time_str, date_str)
            # Date only
            return str(
                babel_dates.format_date(
                    dt_value,
                    format=date_style,
                    locale=self.babel_locale,
                )
            )

        except (ValueError, OverflowError, AttributeError, KeyError) as e:
            # Formatting failed - raise FrozenFluentError with fallback value
            # The resolver will catch this error, collect it, and use the fallback
            fallback = dt_value.isoformat()
            diagnostic = ErrorTemplate.formatting_failed(
                "DATETIME", str(dt_value), str(e)
            )
            context = FrozenErrorContext(
                input_value=str(dt_value),
                locale_code=self.locale_code,
                parse_type="datetime",
                fallback_value=fallback,
            )
            raise FrozenFluentError(
                str(diagnostic), ErrorCategory.FORMATTING,
                diagnostic=diagnostic, context=context
            ) from e

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
        """Format currency with locale-specific rules.

        Implements Fluent CURRENCY function semantics using Babel.

        Args:
            value: Monetary amount (int or Decimal). float is not accepted;
                use Decimal(str(float_val)) to convert at system boundaries.
            currency: ISO 4217 currency code (EUR, USD, JPY, BHD, etc.)
            currency_display: Display style for currency
                - "symbol": Use currency symbol (default)
                - "code": Use currency code (EUR, USD, JPY)
                - "name": Use currency name (euros, dollars, yen)
            pattern: Custom currency pattern (overrides currency_display).
                CLDR currency pattern placeholders:
                - Use double currency sign for ISO code display
                - Standard patterns use single currency sign for symbol
            use_grouping: Use thousands separator (default: True)
            currency_digits: Use ISO 4217 decimal places for the currency
                (default: True). When False, no automatic decimal place adjustment
                is made and the value is formatted as-is. Has no effect when
                ``pattern`` is provided (pattern precision takes precedence).
            numbering_system: CLDR numbering system identifier (default: "latn").
                Controls which numeral glyphs are used in the output.
                Examples: "latn" (0-9), "arab" (Arabic-Indic), "deva" (Devanagari).

        Returns:
            Formatted currency string according to locale rules

        Examples:
            >>> from decimal import Decimal
            >>> ctx = LocaleContext.create('en-US')
            >>> ctx.format_currency(Decimal('123.45'), currency='EUR')
            '€123.45'

            >>> ctx = LocaleContext.create('lv-LV')
            >>> ctx.format_currency(Decimal('123.45'), currency='EUR')
            '123,45 €'

            >>> ctx = LocaleContext.create('ja-JP')
            >>> ctx.format_currency(12345, currency='JPY')
            '¥12,345'

            >>> ctx = LocaleContext.create('ar-BH')
            >>> ctx.format_currency(Decimal('123.456'), currency='BHD')
            '123.456 د.ب.'

            >>> # Custom pattern example
            >>> ctx = LocaleContext.create('en-US')
            >>> ctx.format_currency(Decimal('1234.56'), currency='USD', pattern='#,##0.00 ¤')
            '1,234.56 $'

        CLDR Compliance:
            Uses Babel's format_currency() which implements CLDR rules.
            Matches Intl.NumberFormat with style: 'currency'.
            Automatically applies currency-specific decimal places when
            currency_digits=True (default):
            - JPY: 0 decimals
            - BHD, KWD, OMR: 3 decimals
            - Most others: 2 decimals
        """
        babel_numbers = get_babel_numbers()

        try:
            # Custom pattern overrides currency_display.
            # currency_digits=False: the pattern explicitly controls decimal places;
            # CLDR ISO 4217 defaults must not override the pattern's precision.
            if pattern is not None:
                return str(
                    babel_numbers.format_currency(
                        value,
                        currency,
                        format=pattern,
                        locale=self.babel_locale,
                        currency_digits=False,
                        group_separator=use_grouping,
                        numbering_system=numbering_system,
                    )
                )

            # Map currency_display to Babel's format_type parameter.
            if currency_display == "name":
                format_type: Literal["name", "standard", "accounting"] = "name"
                return str(
                    babel_numbers.format_currency(
                        value,
                        currency,
                        locale=self.babel_locale,
                        currency_digits=currency_digits,
                        format_type=format_type,
                        group_separator=use_grouping,
                        numbering_system=numbering_system,
                    )
                )

            if currency_display == "code":
                # Double currency sign (¤¤) per CLDR displays ISO code.
                code_pattern = self._get_iso_code_pattern()
                if code_pattern is not None:
                    return str(
                        babel_numbers.format_currency(
                            value,
                            currency,
                            format=code_pattern,
                            locale=self.babel_locale,
                            currency_digits=currency_digits,
                            group_separator=use_grouping,
                            numbering_system=numbering_system,
                        )
                    )
                # Fallback: use standard format if pattern extraction fails.

            # Default: symbol display using standard format.
            return str(
                babel_numbers.format_currency(
                    value,
                    currency,
                    locale=self.babel_locale,
                    currency_digits=currency_digits,
                    format_type="standard",
                    group_separator=use_grouping,
                    numbering_system=numbering_system,
                )
            )

        except (ValueError, TypeError, InvalidOperation, AttributeError, KeyError) as e:
            # Formatting failed - raise FrozenFluentError with fallback value
            # The resolver will catch this error, collect it, and use the fallback
            fallback = f"{currency} {value}"
            diagnostic = ErrorTemplate.formatting_failed(
                "CURRENCY", f"{currency} {value}", str(e)
            )
            context = FrozenErrorContext(
                input_value=f"{currency} {value}",
                locale_code=self.locale_code,
                parse_type="currency",
                fallback_value=fallback,
            )
            raise FrozenFluentError(
                str(diagnostic), ErrorCategory.FORMATTING,
                diagnostic=diagnostic, context=context
            ) from e

    def _get_iso_code_pattern(self) -> str | None:
        """Get CLDR pattern for ISO currency code display.

        Per CLDR specification:
        - Single currency sign (U+00A4) displays currency symbol
        - Double currency sign (U+00A4 U+00A4) displays ISO code

        This helper extracts the standard currency pattern and replaces
        single currency signs with double signs for ISO code display.

        Returns:
            Modified pattern for ISO code display, or None if extraction fails.
        """
        locale_currency_formats = self.babel_locale.currency_formats
        standard_pattern = locale_currency_formats.get("standard")
        if standard_pattern is None or not hasattr(standard_pattern, "pattern"):
            return None

        raw_pattern = standard_pattern.pattern
        # Guard: verify currency placeholder exists before replacement
        # Single U+00A4 = symbol, Double U+00A4 U+00A4 = ISO code per CLDR
        if "\xa4" not in raw_pattern:
            logger.debug(
                "Currency pattern for locale %s lacks placeholder",
                self.locale_code,
            )
            return None

        return str(raw_pattern.replace("\xa4", "\xa4\xa4"))
