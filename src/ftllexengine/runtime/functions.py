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

import logging
from datetime import datetime
from decimal import Decimal
from typing import Literal

from .function_bridge import _FTL_REQUIRES_LOCALE_ATTR, FluentNumber, FunctionRegistry
from .locale_context import LocaleContext

__all__ = ["create_default_registry", "get_shared_registry"]

logger = logging.getLogger(__name__)


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
        Formatted number string

    Examples:
        >>> number_format(1234.5, "en-US")
        '1,234.5'
        >>> number_format(1234.5, "de-DE")
        '1.234,5'
        >>> number_format(1234.5, "lv-LV")
        '1 234,5'
        >>> number_format(42, "en-US", minimum_fraction_digits=2)
        '42.00'
        >>> number_format(-1234.56, "en-US", pattern="#,##0.00;(#,##0.00)")
        '(1,234.56)'

    FTL Usage:
        price = { $amount NUMBER(minimumFractionDigits: 2) }
        accounting = { $amount NUMBER(pattern: "#,##0.00;(#,##0.00)") }

    Thread Safety:
        Thread-safe. Uses Babel (no global locale state mutation).

    CLDR Compliance:
        Implements CLDR formatting rules via Babel.
        Matches Intl.NumberFormat semantics.
        Custom patterns follow Babel number pattern syntax.
    """
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
    # Return FluentNumber preserving both formatted output and numeric value
    # for proper plural category matching in select expressions.
    return FluentNumber(value=value, formatted=formatted)


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
) -> str:
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
        Formatted currency string

    Examples:
        >>> currency_format(123.45, "en-US", currency="EUR")
        '€123.45'
        >>> currency_format(123.45, "lv-LV", currency="EUR")
        '123,45 €'
        >>> currency_format(12345, "ja-JP", currency="JPY")
        '¥12,345'
        >>> currency_format(123.456, "ar-BH", currency="BHD")
        '123.456 د.ب.'

    FTL Usage:
        price = { CURRENCY($amount, currency: "EUR") }
        price-code = { CURRENCY($amount, currency: $code, currencyDisplay: "code") }
        price-name = { CURRENCY($amount, currency: "EUR", currencyDisplay: "name") }

    Thread Safety:
        Thread-safe. Uses Babel (no global locale state mutation).

    CLDR Compliance:
        Implements CLDR formatting rules via Babel.
        Matches Intl.NumberFormat with style: 'currency'.
        Automatically applies currency-specific decimal places:
        - JPY, KRW: 0 decimals
        - BHD, KWD, OMR: 3 decimals
        - Most others: 2 decimals
    """
    # Delegate to LocaleContext (immutable, thread-safe)
    # create() always returns LocaleContext with en_US fallback for invalid locales
    ctx = LocaleContext.create(locale_code)
    return ctx.format_currency(
        value,
        currency=currency,
        currency_display=currency_display,
        pattern=pattern,
    )


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


# Module-level cached default registry for sharing across bundles.
# Initialized lazily on first access to avoid import-time side effects.
_SHARED_REGISTRY: FunctionRegistry | None = None


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
        Reading is thread-safe. The registry is frozen, so writes are not
        possible. For custom functions, use create_default_registry() to get
        a fresh, isolated copy.

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
    # pylint: disable=global-statement
    # Lazy initialization of module-level singleton.
    # Global is intentional for shared state across calls.
    global _SHARED_REGISTRY  # noqa: PLW0603
    if _SHARED_REGISTRY is None:
        _SHARED_REGISTRY = create_default_registry()
        _SHARED_REGISTRY.freeze()  # Protect from accidental modification
    return _SHARED_REGISTRY
