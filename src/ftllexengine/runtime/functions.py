"""Fluent built-in functions with Python-native APIs.

Implements NUMBER, DATETIME, and CURRENCY functions with locale-aware formatting.
Uses snake_case parameters (PEP 8) with FTL camelCase bridge.

Architecture:
    - Python functions use snake_case (PEP 8 compliant)
    - FunctionRegistry bridges to FTL camelCase
    - FTL files still use camelCase syntax
    - No N802/N803 violations!
    - Locale-aware via LocaleContext (thread-safe, CLDR-based)

Example:
    # Python API (snake_case):
    number_format(1234.5, "en-US", minimum_fraction_digits=2)

    # FTL file (camelCase):
    price = { $amount NUMBER(minimumFractionDigits: 2) }

    # Bridge handles the conversion automatically!

Python 3.13+. Uses Babel for i18n.
"""

import functools
import logging
from datetime import datetime
from decimal import Decimal
from typing import Literal

from ftllexengine.core.babel_compat import get_babel_numbers

from .function_bridge import FunctionRegistry
from .locale_context import LocaleContext
from .value_types import _FTL_REQUIRES_LOCALE_ATTR, FluentNumber

__all__ = ["create_default_registry", "get_shared_registry"]

logger = logging.getLogger(__name__)


def _compute_visible_precision(
    formatted: str,
    decimal_symbol: str,
    *,
    max_fraction_digits: int | None = None,
) -> int:
    """Count visible fraction digits in formatted number string.

    CLDR plural rules use the 'v' operand which represents the count of visible
    fraction digits in the source number WITH trailing zeros. This function
    extracts that count from the locale-formatted string.

    Only leading consecutive digits after the decimal separator are counted.
    This correctly handles formatted strings where non-digit characters or
    literal text (e.g., currency names, custom pattern suffixes) follow the
    fractional digits.

    When max_fraction_digits is provided (from Babel pattern metadata), the
    count is capped at that value. This prevents literal digit suffixes in
    custom Babel patterns (e.g., ICU single-quote syntax ``0.0'5'``) from
    being counted as actual fraction digits.

    Args:
        formatted: Locale-formatted number string (e.g., "1,234.56" or "1.234,56")
        decimal_symbol: Locale-specific decimal separator (e.g., "." or ",")
        max_fraction_digits: Upper bound from pattern metadata (keyword-only).
            When provided, precision is capped at this value. This handles
            patterns with literal digit suffixes (e.g., ``0.0'5'`` produces
            "1.25" for input 1.2 but has frac_prec=(1,1), so precision=1).

    Returns:
        Number of leading consecutive digits after the decimal separator,
        capped by max_fraction_digits if provided, or 0 if no decimal part.

    Examples:
        >>> _compute_visible_precision("1,234.56", ".")
        2
        >>> _compute_visible_precision("1.234,56", ",")
        2
        >>> _compute_visible_precision("1,234", ".")
        0
        >>> _compute_visible_precision("1.00", ".")
        2
        >>> _compute_visible_precision("100.00 Dollars 123", ".")
        2
        >>> _compute_visible_precision("1.25", ".", max_fraction_digits=1)
        1
    """
    if decimal_symbol not in formatted:
        return 0

    # Find the last occurrence of decimal separator (handles edge cases)
    # Split from the right to handle any prefix characters
    _, fraction_part = formatted.rsplit(decimal_symbol, 1)

    # Count leading consecutive digit characters in the fraction part.
    # Stop at the first non-digit to exclude literal text that may contain
    # digits (e.g., custom Babel patterns with quoted literals like
    # "#,##0.00 'Dollars 123'" produce "100.00 Dollars 123").
    count = 0
    for char in fraction_part:
        if char.isdigit():
            count += 1
        else:
            break

    # Cap at pattern-defined maximum fraction digits when available.
    # Prevents literal digit suffixes (ICU single-quote syntax) from
    # inflating the CLDR v operand. Example: pattern "0.0'5'" has
    # frac_prec=(1,1) but produces "1.25" for 1.2 - the "5" is a
    # literal suffix, not a fraction digit of the source number.
    if max_fraction_digits is not None and count > max_fraction_digits:
        count = max_fraction_digits

    return count


def number_format(
    value: int | float | Decimal,
    locale_code: str = "en-US",
    *,
    minimum_fraction_digits: int = 0,
    maximum_fraction_digits: int = 3,
    use_grouping: bool = True,
    pattern: str | None = None,
) -> FluentNumber:
    """Format number with locale-specific separators.

    Python-native API with snake_case parameters. FunctionRegistry bridges
    to FTL camelCase (minimumFractionDigits → minimum_fraction_digits).

    Args:
        value: Number to format (int, float, or Decimal)
        locale_code: BCP 47 locale identifier (e.g., 'en-US', 'de-DE')
        minimum_fraction_digits: Minimum decimal places (default: 0)
        maximum_fraction_digits: Maximum decimal places (default: 3)
        use_grouping: Use thousands separator (default: True)
        pattern: Custom number pattern (overrides CLDR defaults)
            Examples:
            - "#,##0.00": Always show 2 decimals
            - "#,##0.00;(#,##0.00)": Negatives in parentheses (accounting)
            - "0.000": Scientific notation with 3 decimals

    Returns:
        FluentNumber with formatted string and computed precision for plural matching

    Examples:
        >>> number_format(1234.5, "en-US")
        FluentNumber(value=1234.5, formatted='1,234.5')
        >>> number_format(1234.5, "de-DE")
        FluentNumber(value=1234.5, formatted='1.234,5')
        >>> number_format(1234.5, "lv-LV")
        FluentNumber(value=1234.5, formatted='1 234,5')
        >>> number_format(42, "en-US", minimum_fraction_digits=2)
        FluentNumber(value=42, formatted='42.00')
        >>> number_format(-1234.56, "en-US", pattern="#,##0.00;(#,##0.00)")
        FluentNumber(value=-1234.56, formatted='(1,234.56)')

    FTL Usage:
        price = { $amount NUMBER(minimumFractionDigits: 2) }
        accounting = { $amount NUMBER(pattern: "#,##0.00;(#,##0.00)") }

    Thread Safety:
        Thread-safe. Uses Babel (no global locale state mutation).

    CLDR Compliance:
        Implements CLDR formatting rules via Babel.
        Matches Intl.NumberFormat semantics.
        Custom patterns follow Babel number pattern syntax.

    Precision Calculation:
        The precision (CLDR v operand) is computed from the ACTUAL formatted
        string, not from the minimum_fraction_digits parameter. This ensures
        correct plural category matching:
        - number_format(1.2, min=0, max=3) -> "1.2" with precision=1 (not 0)
        - number_format(1.0, min=0, max=3) -> "1" with precision=0
        - number_format(1.00, min=2, max=2) -> "1.00" with precision=2
    """
    babel_numbers = get_babel_numbers()
    get_decimal_symbol = babel_numbers.get_decimal_symbol
    parse_pattern = babel_numbers.parse_pattern

    # Delegate to LocaleContext (immutable, thread-safe)
    # create() always returns LocaleContext with en_US fallback for invalid locales
    ctx = LocaleContext.create(locale_code)
    formatted = ctx.format_number(
        value,
        minimum_fraction_digits=minimum_fraction_digits,
        maximum_fraction_digits=maximum_fraction_digits,
        use_grouping=use_grouping,
        pattern=pattern,
    )

    # Compute actual visible precision from formatted string (CLDR v operand)
    # This is critical for correct plural category matching in select expressions.
    # The precision must reflect the ACTUAL formatted output, not the minimum parameter.
    decimal_symbol = get_decimal_symbol(ctx.babel_locale)

    # When a custom pattern is provided, extract max fraction digits from pattern
    # metadata to cap precision. This prevents literal digit suffixes (ICU
    # single-quote syntax like "0.0'5'") from inflating the v operand.
    max_frac: int | None = None
    if pattern is not None:
        try:
            parsed = parse_pattern(pattern)
            # frac_prec is (min_frac, max_frac) tuple
            max_frac = parsed.frac_prec[1]
        except Exception:  # pylint: disable=broad-exception-caught
            # Malformed pattern: fall back to uncapped counting.
            # Babel format_number already handled the pattern successfully,
            # so parse_pattern failure is unexpected but not fatal.
            logger.debug(
                "parse_pattern failed for NUMBER pattern %r; "
                "precision capping disabled",
                pattern,
            )

    precision = _compute_visible_precision(
        formatted, decimal_symbol, max_fraction_digits=max_frac
    )

    return FluentNumber(value=value, formatted=formatted, precision=precision)


def datetime_format(
    value: datetime | str,
    locale_code: str = "en-US",
    *,
    date_style: Literal["short", "medium", "long", "full"] = "medium",
    time_style: Literal["short", "medium", "long", "full"] | None = None,
    pattern: str | None = None,
) -> str:
    """Format datetime with locale-specific formatting.

    Python-native API with snake_case parameters. FunctionRegistry bridges
    to FTL camelCase (dateStyle → date_style, timeStyle → time_style).

    Args:
        value: datetime object or ISO string
        locale_code: BCP 47 locale identifier (e.g., 'en-US', 'de-DE')
        date_style: Date format style (default: "medium")
        time_style: Time format style (default: None - date only)
        pattern: Custom datetime pattern (overrides CLDR defaults)
            Examples:
            - "yyyy-MM-dd": ISO 8601 date (2025-01-28)
            - "HH:mm:ss": 24-hour time (14:30:00)
            - "MMM d, yyyy": Short month name (Jan 28, 2025)
            - "EEEE, MMMM d, yyyy": Full format (Monday, January 28, 2025)

    Returns:
        Formatted datetime string

    Examples:
        >>> from datetime import datetime, UTC
        >>> dt = datetime(2025, 10, 27, tzinfo=UTC)
        >>> datetime_format(dt, "en-US", date_style="short")
        '10/27/25'
        >>> datetime_format(dt, "de-DE", date_style="short")
        '27.10.25'
        >>> dt_with_time = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)
        >>> datetime_format(dt_with_time, "en-US", date_style="medium", time_style="short")
        'Oct 27, 2025, 2:30 PM'
        >>> datetime_format(dt, "en-US", pattern="yyyy-MM-dd")
        '2025-10-27'

    FTL Usage:
        today = { $date DATETIME(dateStyle: "short") }
        timestamp = { $time DATETIME(dateStyle: "medium", timeStyle: "short") }
        iso-date = { $date DATETIME(pattern: "yyyy-MM-dd") }

    Thread Safety:
        Thread-safe. Uses Babel (no global locale state mutation).

    CLDR Compliance:
        Implements CLDR formatting rules via Babel.
        Matches Intl.DateTimeFormat semantics.
        Custom patterns follow Babel datetime pattern syntax.
    """
    # Delegate to LocaleContext (immutable, thread-safe)
    # create() always returns LocaleContext with en_US fallback for invalid locales
    ctx = LocaleContext.create(locale_code)
    return ctx.format_datetime(
        value,
        date_style=date_style,
        time_style=time_style,
        pattern=pattern,
    )


def currency_format(
    value: int | float | Decimal,
    locale_code: str = "en-US",
    *,
    currency: str,
    currency_display: Literal["symbol", "code", "name"] = "symbol",
    pattern: str | None = None,
) -> FluentNumber:
    """Format currency with locale-specific formatting.

    Python-native API with snake_case parameters. FunctionRegistry bridges
    to FTL camelCase (currencyDisplay → currency_display).

    Args:
        value: Monetary amount (int, float, or Decimal)
        locale_code: BCP 47 locale identifier (e.g., 'en-US', 'de-DE')
        currency: ISO 4217 currency code (EUR, USD, JPY, BHD, etc.)
        currency_display: Display style (default: "symbol")
            - "symbol": Use currency symbol
            - "code": Use currency code (EUR, USD, JPY)
            - "name": Use currency name (euros, dollars, yen)
        pattern: Custom currency pattern (overrides currency_display).
            CLDR currency pattern placeholders per Babel/CLDR spec.

    Returns:
        FluentNumber with formatted currency string and computed precision.
        Returning FluentNumber enables CURRENCY results to be used as selectors
        in plural/select expressions, matching NUMBER() behavior.

    Examples:
        >>> currency_format(123.45, "en-US", currency="EUR")
        FluentNumber(value=123.45, formatted='€123.45', precision=2)
        >>> currency_format(123.45, "lv-LV", currency="EUR")
        FluentNumber(value=123.45, formatted='123,45 €', precision=2)
        >>> currency_format(12345, "ja-JP", currency="JPY")
        FluentNumber(value=12345, formatted='¥12,345', precision=0)
        >>> currency_format(123.456, "ar-BH", currency="BHD")
        FluentNumber(value=123.456, formatted='123.456 د.ب.', precision=3)

    FTL Usage:
        price = { CURRENCY($amount, currency: "EUR") }
        price-code = { CURRENCY($amount, currency: $code, currencyDisplay: "code") }
        price-name = { CURRENCY($amount, currency: "EUR", currencyDisplay: "name") }

        # CURRENCY can now be used as a selector (returns FluentNumber):
        items = { CURRENCY($count, currency: "USD") ->
            [one] One dollar item
           *[other] Multiple dollar items
        }

    Thread Safety:
        Thread-safe. Uses Babel (no global locale state mutation).

    CLDR Compliance:
        Implements CLDR formatting rules via Babel.
        Matches Intl.NumberFormat with style: 'currency'.
        Automatically applies currency-specific decimal places:
        - JPY, KRW: 0 decimals
        - BHD, KWD, OMR: 3 decimals
        - Most others: 2 decimals

    Precision Calculation:
        The precision (CLDR v operand) is computed from the ACTUAL formatted
        string, not from ISO 4217 defaults. This ensures correct plural category
        matching for custom patterns or locales that deviate from standard
        decimal places.
    """
    babel_numbers = get_babel_numbers()
    get_decimal_symbol = babel_numbers.get_decimal_symbol
    parse_pattern = babel_numbers.parse_pattern

    # Delegate to LocaleContext (immutable, thread-safe)
    # create() always returns LocaleContext with en_US fallback for invalid locales
    ctx = LocaleContext.create(locale_code)
    formatted = ctx.format_currency(
        value,
        currency=currency,
        currency_display=currency_display,
        pattern=pattern,
    )

    # Compute actual visible precision from formatted string (CLDR v operand)
    # This is critical for correct plural category matching in select expressions.
    # The precision must reflect the ACTUAL formatted output, not ISO 4217 defaults.
    decimal_symbol = get_decimal_symbol(ctx.babel_locale)

    # When a custom pattern is provided, extract max fraction digits from pattern
    # metadata to cap precision. Same rationale as number_format().
    max_frac: int | None = None
    if pattern is not None:
        try:
            parsed = parse_pattern(pattern)
            max_frac = parsed.frac_prec[1]
        except Exception:  # pylint: disable=broad-exception-caught
            logger.debug(
                "parse_pattern failed for CURRENCY pattern %r; "
                "precision capping disabled",
                pattern,
            )

    precision = _compute_visible_precision(
        formatted, decimal_symbol, max_fraction_digits=max_frac
    )

    return FluentNumber(value=value, formatted=formatted, precision=precision)


# Mark built-in functions that require locale injection.
# This attribute is checked by FunctionRegistry.should_inject_locale() to determine
# whether to append the bundle's locale to the function call arguments.
# The constant _FTL_REQUIRES_LOCALE_ATTR is imported from function_bridge.py
# to ensure a single source of truth.


def _mark_locale_required(func: object) -> None:
    """Mark a function as requiring locale injection.

    Args:
        func: Function to mark with _ftl_requires_locale = True
    """
    setattr(func, _FTL_REQUIRES_LOCALE_ATTR, True)


def is_builtin_with_locale_requirement(func: object) -> bool:
    """Check if a callable is a built-in function requiring locale injection.

    This is the canonical way to check locale injection requirements,
    avoiding circular imports by using function attributes instead of
    comparing callable identity.

    Args:
        func: Callable to check

    Returns:
        True if func has _ftl_requires_locale = True, False otherwise
    """
    return getattr(func, _FTL_REQUIRES_LOCALE_ATTR, False) is True


# Mark built-in functions at module load time
_mark_locale_required(number_format)
_mark_locale_required(datetime_format)
_mark_locale_required(currency_format)


def create_default_registry() -> FunctionRegistry:
    """Create a new FunctionRegistry with built-in FTL functions registered.

    Returns a fresh, isolated registry instance containing the standard Fluent
    functions (NUMBER, DATETIME, CURRENCY). Each call returns a new instance,
    ensuring no shared mutable state between different FluentBundle instances.

    Returns:
        FunctionRegistry with NUMBER, DATETIME, and CURRENCY functions registered.

    Example:
        >>> registry = create_default_registry()
        >>> "NUMBER" in registry
        True
        >>> "DATETIME" in registry
        True
        >>> "CURRENCY" in registry
        True

    Use Case:
        FluentBundle uses this internally to create isolated function registries.
        Users who need custom registries can call this and then modify the result:

        >>> registry = create_default_registry()
        >>> registry.register(my_custom_func, ftl_name="CUSTOM")
        >>> bundle = FluentBundle("en", functions=registry)

    See Also:
        get_shared_registry: Returns a shared cached registry for performance.
    """
    registry = FunctionRegistry()

    # Register NUMBER function with camelCase parameter mapping
    registry.register(number_format, ftl_name="NUMBER")

    # Register DATETIME function with camelCase parameter mapping
    registry.register(datetime_format, ftl_name="DATETIME")

    # Register CURRENCY function with camelCase parameter mapping
    registry.register(currency_format, ftl_name="CURRENCY")

    return registry


@functools.lru_cache(maxsize=1)
def _create_shared_registry() -> FunctionRegistry:
    """Thread-safe singleton factory for shared registry.

    Uses lru_cache to ensure thread-safe initialization. The cache guarantees
    that only one registry is ever created, even under concurrent access.
    """
    registry = create_default_registry()
    registry.freeze()  # Protect from accidental modification
    return registry


def get_shared_registry() -> FunctionRegistry:
    """Get a shared, frozen FunctionRegistry with built-in functions.

    Returns a module-level cached registry instance that can be shared across
    multiple FluentBundle instances. This avoids the overhead of creating and
    registering functions for each bundle.

    Immutability:
        The returned registry is FROZEN. Calling register() on it will raise
        TypeError. This prevents accidental pollution of the shared singleton.
        To add custom functions, use copy() or create_default_registry().

    Thread Safety:
        Fully thread-safe. Uses functools.lru_cache internally to guarantee
        that concurrent calls always return the same instance without race
        conditions. The registry is frozen, so writes are not possible.
        For custom functions, use create_default_registry() to get a fresh,
        isolated copy.

    Performance:
        Using the shared registry avoids:
        - Creating a new FunctionRegistry object per bundle
        - Re-registering NUMBER, DATETIME, CURRENCY for each bundle
        - Memory overhead of duplicate function metadata

        For applications with many bundles (e.g., one per locale), this provides
        significant memory and initialization savings.

    Returns:
        Frozen shared FunctionRegistry with NUMBER, DATETIME, and CURRENCY.

    Raises:
        TypeError: If you attempt to call register() on the returned registry.

    Example:
        >>> # Efficient: Share registry across multiple bundles
        >>> shared = get_shared_registry()
        >>> bundle_en = FluentBundle("en", functions=shared)
        >>> bundle_de = FluentBundle("de", functions=shared)
        >>> bundle_fr = FluentBundle("fr", functions=shared)
        >>>
        >>> # Registry is frozen - attempting to modify raises TypeError
        >>> shared.register(my_func)  # Raises TypeError!
        >>>
        >>> # To add custom functions, use copy() to get unfrozen copy:
        >>> my_registry = shared.copy()
        >>> my_registry.register(my_custom_func, ftl_name="CUSTOM")

    See Also:
        create_default_registry: Creates a new unfrozen registry for customization.
    """
    return _create_shared_registry()
