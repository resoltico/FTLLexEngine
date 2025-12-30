"""Locale context for thread-safe, bundle-scoped formatting.

This module provides locale-aware formatting without global state mutation.
Uses Babel for CLDR-compliant number, date, and currency formatting.

Architecture:
    - LocaleContext: Immutable locale configuration container
    - Formatters use Babel (thread-safe, CLDR-based)
    - No dependency on Python's locale module (avoids global state)
    - Each FluentBundle owns its LocaleContext (locale isolation)

Design Principles:
    - Explicit over implicit (locale always visible)
    - Immutable by default (frozen dataclass)
    - Thread-safe (no shared mutable state)
    - CLDR-compliant (matches Intl.NumberFormat semantics)
    - Explicit error handling (no silent fallbacks)

Python 3.13+. Uses Babel for i18n.
"""

import logging
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from threading import RLock
from typing import ClassVar, Literal

from babel import Locale, UnknownLocaleError
from babel import dates as babel_dates
from babel import numbers as babel_numbers

from ftllexengine.constants import FALLBACK_FUNCTION_ERROR, MAX_LOCALE_CACHE_SIZE
from ftllexengine.core.errors import FormattingError
from ftllexengine.locale_utils import normalize_locale

__all__ = ["LocaleContext"]

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LocaleContext:
    """Immutable locale configuration for formatting operations.

    Provides thread-safe, locale-specific formatting for numbers, dates, and currency
    without mutating global state. Each FluentBundle owns its LocaleContext.

    Use LocaleContext.create() factory to construct instances with proper validation.
    Direct construction via __init__ is not recommended (bypasses validation).

    Cache Management:
        LocaleContext uses an internal LRU cache for instance reuse. Use class
        methods for cache management:
        - LocaleContext.clear_cache(): Clear all cached instances
        - LocaleContext.cache_size(): Get current cache size
        - LocaleContext.cache_info(): Get detailed cache statistics

    Examples:
        >>> ctx = LocaleContext.create('en-US')
        >>> ctx.format_number(1234.5, use_grouping=True)
        '1,234.5'

        >>> ctx = LocaleContext.create('lv-LV')
        >>> ctx.format_number(1234.5, use_grouping=True)
        '1 234,5'

        >>> # Invalid locales fall back to en_US with warning logged
        >>> ctx = LocaleContext.create('invalid-locale')
        >>> ctx.locale_code  # Original code preserved
        'invalid-locale'
        >>> ctx.is_fallback  # Programmatic detection of fallback
        True

    Thread Safety:
        LocaleContext is immutable and thread-safe. Multiple threads can
        share the same instance without synchronization. Cache operations
        are protected by RLock.

    Babel vs locale module:
        - Babel: Thread-safe, CLDR-based, 600+ locales
        - locale: Thread-unsafe, platform-dependent, requires setlocale()
    """

    # Class-level cache for LocaleContext instances (identity caching)
    # OrderedDict provides LRU semantics with O(1) operations
    # Note: ClassVar is excluded from dataclass fields
    _cache: ClassVar[OrderedDict[str, "LocaleContext"]] = OrderedDict()
    _cache_lock: ClassVar[RLock] = RLock()

    locale_code: str
    _babel_locale: Locale
    is_fallback: bool = False

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the locale context cache.

        Use this method to free memory or reset state in tests.
        Thread-safe via RLock.

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
            {'size': 1, 'max_size': 128, 'locales': ('en_US',)}
        """
        with cls._cache_lock:
            return {
                "size": len(cls._cache),
                "max_size": MAX_LOCALE_CACHE_SIZE,
                "locales": tuple(cls._cache.keys()),
            }

    @classmethod
    def create(cls, locale_code: str) -> "LocaleContext":
        """Create LocaleContext with graceful fallback for invalid locales.

        Factory method that validates locale code before construction.
        For unknown or invalid locales, logs a warning and falls back to en_US.
        This method always succeeds - use create_or_raise() if you need strict validation.

        Thread Safety:
            Uses OrderedDict with RLock for thread-safe LRU caching.
            Concurrent calls with same locale_code return the same instance.

        Args:
            locale_code: BCP 47 locale identifier (e.g., 'en-US', 'lv-LV', 'de-DE')

        Returns:
            LocaleContext instance. For unknown/invalid locales, uses en_US fallback
            while preserving the original locale_code for debugging.

        Examples:
            >>> ctx = LocaleContext.create('en-US')
            >>> ctx.locale_code
            'en-US'

            >>> ctx = LocaleContext.create('xx_UNKNOWN')  # Unknown locale
            >>> ctx.locale_code  # Preserved for debugging
            'xx_UNKNOWN'
            >>> # But formatting uses en_US rules (with warning logged)
        """
        # Normalize locale code for consistent cache keys
        # This ensures "en-US", "en_US", "EN-US" all map to the same cache entry
        cache_key = normalize_locale(locale_code)

        # Thread-safe LRU caching with identity preservation
        with cls._cache_lock:
            if cache_key in cls._cache:
                # Move to end (mark as recently used) and return cached instance
                cls._cache.move_to_end(cache_key)
                return cls._cache[cache_key]

        # Create new instance (Locale.parse is thread-safe)
        used_fallback = False
        try:
            babel_locale = Locale.parse(cache_key)
        except UnknownLocaleError as e:
            logger.warning("Unknown locale '%s': %s. Falling back to en_US", locale_code, e)
            babel_locale = Locale.parse("en_US")
            used_fallback = True
        except ValueError as e:
            logger.warning(
                "Invalid locale format '%s': %s. Falling back to en_US", locale_code, e
            )
            babel_locale = Locale.parse("en_US")
            used_fallback = True

        # Store with normalized cache_key, but preserve original locale_code for debugging
        ctx = cls(locale_code=locale_code, _babel_locale=babel_locale, is_fallback=used_fallback)

        # Add to cache with lock (double-check pattern for thread safety)
        with cls._cache_lock:
            if cache_key in cls._cache:
                return cls._cache[cache_key]

            # Evict LRU if cache is full
            if len(cls._cache) >= MAX_LOCALE_CACHE_SIZE:
                cls._cache.popitem(last=False)

            cls._cache[cache_key] = ctx
            return ctx

    @classmethod
    def create_or_raise(cls, locale_code: str) -> "LocaleContext":
        """Create LocaleContext or raise on validation failure.

        Strict validation method that raises ValueError for invalid locales.
        Use this in tests or when silent fallback is not acceptable.

        Args:
            locale_code: BCP 47 locale identifier (e.g., 'en-US', 'lv-LV', 'de-DE')

        Returns:
            LocaleContext instance with valid locale

        Raises:
            ValueError: If locale code is invalid or unknown

        Examples:
            >>> ctx = LocaleContext.create_or_raise('en-US')
            >>> ctx.locale_code
            'en-US'

            >>> LocaleContext.create_or_raise('invalid-locale')  # doctest: +IGNORE_EXCEPTION_DETAIL
            Traceback (most recent call last):
                ...
            ValueError: Unknown locale identifier 'invalid-locale'
        """
        try:
            normalized = normalize_locale(locale_code)
            babel_locale = Locale.parse(normalized)
            return cls(locale_code=locale_code, _babel_locale=babel_locale)
        except UnknownLocaleError as e:
            msg = f"Unknown locale identifier '{locale_code}': {e}"
            raise ValueError(msg) from None
        except ValueError as e:
            msg = f"Invalid locale format '{locale_code}': {e}"
            raise ValueError(msg) from None

    @property
    def babel_locale(self) -> Locale:
        """Get pre-validated Babel Locale object for this context.

        Returns:
            Babel Locale instance (validated during construction)
        """
        return self._babel_locale

    def format_number(
        self,
        value: int | float | Decimal,
        *,
        minimum_fraction_digits: int = 0,
        maximum_fraction_digits: int = 3,
        use_grouping: bool = True,
        pattern: str | None = None,
    ) -> str:
        """Format number with locale-specific separators.

        Implements Fluent NUMBER function semantics using Babel.

        Args:
            value: Number to format (int, float, or Decimal)
            minimum_fraction_digits: Minimum decimal places (default: 0)
            maximum_fraction_digits: Maximum decimal places (default: 3)
            use_grouping: Use thousands separator (default: True)
            pattern: Custom number pattern (overrides other parameters)

        Returns:
            Formatted number string according to locale rules

        Examples:
            >>> ctx = LocaleContext.create('en-US')
            >>> ctx.format_number(1234.5)
            '1,234.5'

            >>> ctx = LocaleContext.create('de-DE')
            >>> ctx.format_number(1234.5)
            '1.234,5'

            >>> ctx = LocaleContext.create('lv-LV')
            >>> ctx.format_number(1234.5)
            '1 234,5'

            >>> ctx = LocaleContext.create('en-US')
            >>> ctx.format_number(-1234.56, pattern="#,##0.00;(#,##0.00)")
            '(1,234.56)'

        CLDR Compliance:
            Uses Babel's format_decimal() which implements CLDR rules.
            Matches Intl.NumberFormat behavior in JavaScript.
        """
        try:
            # Use custom pattern if provided
            if pattern is not None:
                return str(
                    babel_numbers.format_decimal(
                        value,
                        format=pattern,
                        locale=self.babel_locale,
                    )
                )

            # Build format pattern from parameters
            # '#,##0' = integer with grouping
            # '#,##0.0##' = 1-3 decimal places with grouping
            # '0.00' = exactly 2 decimal places, no grouping

            # Integer part
            integer_part = "#,##0" if use_grouping else "0"

            # Decimal part
            if maximum_fraction_digits == 0:
                # No decimals - round to integer
                value = round(value)
                format_pattern = integer_part
            elif minimum_fraction_digits == maximum_fraction_digits:
                # Fixed decimals (e.g., '0.00' for exactly 2)
                decimal_part = "0" * minimum_fraction_digits
                format_pattern = f"{integer_part}.{decimal_part}"
            else:
                # Variable decimals (e.g., '0.0##' for 1-3)
                required = "0" * minimum_fraction_digits
                optional = "#" * (maximum_fraction_digits - minimum_fraction_digits)
                format_pattern = f"{integer_part}.{required}{optional}"

            # Format using Babel
            return str(
                babel_numbers.format_decimal(
                    value,
                    format=format_pattern,
                    locale=self.babel_locale,
                )
            )

        except (ValueError, TypeError, InvalidOperation, AttributeError, KeyError) as e:
            # Formatting failed - raise FormattingError with fallback value
            # The resolver will catch this error, collect it, and use the fallback
            fallback = str(value)
            msg = f"Number formatting failed for '{value}': {e}"
            raise FormattingError(msg, fallback_value=fallback) from e

    def format_datetime(
        self,
        value: datetime | str,
        *,
        date_style: Literal["short", "medium", "long", "full"] = "medium",
        time_style: Literal["short", "medium", "long", "full"] | None = None,
        pattern: str | None = None,
    ) -> str:
        """Format datetime with locale-specific formatting.

        Implements Fluent DATETIME function semantics using Babel.

        Args:
            value: datetime object or ISO 8601 string. Strings are converted
                via datetime.fromisoformat() which accepts formats like:
                - "2025-10-27" (date only)
                - "2025-10-27T14:30:00" (date and time)
                - "2025-10-27T14:30:00+00:00" (with timezone)
            date_style: Date format style (default: "medium")
            time_style: Time format style (default: None - date only)
            pattern: Custom datetime pattern (overrides style parameters)

        Returns:
            Formatted datetime string according to locale rules

        Raises:
            FormattingError: If string value is not valid ISO 8601 format

        Examples:
            >>> from datetime import datetime, UTC
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

        CLDR Compliance:
            Uses Babel's format_datetime() which implements CLDR rules.
            Matches Intl.DateTimeFormat behavior in JavaScript.
        """
        # Type narrowing: convert str to datetime
        dt_value: datetime

        if isinstance(value, str):
            try:
                dt_value = datetime.fromisoformat(value)
            except ValueError as e:
                # Invalid datetime string - raise FormattingError with fallback
                # This ensures consistent error handling across all format_* methods
                fallback = FALLBACK_FUNCTION_ERROR.format(name="DATETIME")
                msg = f"Invalid datetime string '{value}': not ISO 8601 format"
                raise FormattingError(msg, fallback_value=fallback) from e
        else:
            dt_value = value

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
                datetime_pattern = (
                    self.babel_locale.datetime_formats.get(date_style)
                    or self.babel_locale.datetime_formats.get("medium")
                    or self.babel_locale.datetime_formats.get("short")
                    or "{1} {0}"  # Ultimate fallback (Western LTR order)
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
            # Formatting failed - raise FormattingError with fallback value
            # The resolver will catch this error, collect it, and use the fallback
            fallback = dt_value.isoformat()
            msg = f"DateTime formatting failed for '{dt_value}': {e}"
            raise FormattingError(msg, fallback_value=fallback) from e

    def format_currency(
        self,
        value: int | float | Decimal,
        *,
        currency: str,
        currency_display: Literal["symbol", "code", "name"] = "symbol",
        pattern: str | None = None,
    ) -> str:
        """Format currency with locale-specific rules.

        Implements Fluent CURRENCY function semantics using Babel.

        Args:
            value: Monetary amount (int, float, or Decimal)
            currency: ISO 4217 currency code (EUR, USD, JPY, BHD, etc.)
            currency_display: Display style for currency
                - "symbol": Use currency symbol (default)
                - "code": Use currency code (EUR, USD, JPY)
                - "name": Use currency name (euros, dollars, yen)
            pattern: Custom currency pattern (overrides currency_display).
                CLDR currency pattern placeholders:
                - Use double currency sign for ISO code display
                - Standard patterns use single currency sign for symbol

        Returns:
            Formatted currency string according to locale rules

        Examples:
            >>> ctx = LocaleContext.create('en-US')
            >>> ctx.format_currency(123.45, currency='EUR')
            '€123.45'

            >>> ctx = LocaleContext.create('lv-LV')
            >>> ctx.format_currency(123.45, currency='EUR')
            '123,45 €'

            >>> ctx = LocaleContext.create('ja-JP')
            >>> ctx.format_currency(12345, currency='JPY')
            '¥12,345'

            >>> ctx = LocaleContext.create('ar-BH')
            >>> ctx.format_currency(123.456, currency='BHD')
            '123.456 د.ب.'

            >>> # Custom pattern example
            >>> ctx = LocaleContext.create('en-US')
            >>> ctx.format_currency(1234.56, currency='USD', pattern='#,##0.00 ¤')
            '1,234.56 $'

        CLDR Compliance:
            Uses Babel's format_currency() which implements CLDR rules.
            Matches Intl.NumberFormat with style: 'currency'.
            Automatically applies currency-specific decimal places:
            - JPY: 0 decimals
            - BHD, KWD, OMR: 3 decimals
            - Most others: 2 decimals
        """
        try:
            # Use custom pattern if provided (overrides currency_display)
            if pattern is not None:
                return str(
                    babel_numbers.format_currency(
                        value,
                        currency,
                        format=pattern,
                        locale=self.babel_locale,
                        currency_digits=True,
                    )
                )

            # Map currency_display to Babel's format_type parameter
            # Babel format_type must be Literal["name", "standard", "accounting"]
            if currency_display == "name":
                format_type: Literal["name", "standard", "accounting"] = "name"
                # Name format type handles display natively
                return str(
                    babel_numbers.format_currency(
                        value,
                        currency,
                        locale=self.babel_locale,
                        currency_digits=True,
                        format_type=format_type,
                    )
                )

            if currency_display == "code":
                # Use CLDR pattern with double currency sign for ISO code display
                # Get the standard currency format pattern from CLDR
                locale_currency_formats = self.babel_locale.currency_formats
                standard_pattern = locale_currency_formats.get("standard")
                if standard_pattern and hasattr(standard_pattern, "pattern"):
                    raw_pattern = standard_pattern.pattern
                    # Guard: verify currency placeholder exists before replacement
                    # Single U+00A4 = symbol, Double U+00A4 U+00A4 = ISO code per CLDR
                    if "\xa4" in raw_pattern:
                        code_pattern = raw_pattern.replace("\xa4", "\xa4\xa4")
                        return str(
                            babel_numbers.format_currency(
                                value,
                                currency,
                                format=code_pattern,
                                locale=self.babel_locale,
                                currency_digits=True,
                            )
                        )
                    # Pattern lacks currency placeholder; log and fall through
                    logger.debug(
                        "Currency pattern for locale %s lacks placeholder",
                        self.locale_code,
                    )
                # Fallback: use standard format if pattern extraction fails
                # or pattern lacks currency placeholder

            # Default: symbol display using standard format
            return str(
                babel_numbers.format_currency(
                    value,
                    currency,
                    locale=self.babel_locale,
                    currency_digits=True,
                    format_type="standard",
                )
            )

        except (ValueError, TypeError, InvalidOperation, AttributeError, KeyError) as e:
            # Formatting failed - raise FormattingError with fallback value
            # The resolver will catch this error, collect it, and use the fallback
            fallback = f"{currency} {value}"
            msg = f"Currency formatting failed for '{currency} {value}': {e}"
            raise FormattingError(msg, fallback_value=fallback) from e
