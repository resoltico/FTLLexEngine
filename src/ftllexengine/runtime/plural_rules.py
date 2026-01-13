"""CLDR plural rules implementation using Babel.

Provides plural category selection for all locales using Babel's CLDR data.

This eliminates 300+ lines of manual rule implementation and supports all CLDR locales.

Babel Dependency:
    This module requires Babel for CLDR data. Import is deferred to function call
    time to support parser-only installations. Clear error message provided when
    Babel is missing.

Python 3.13+.

Reference: https://www.unicode.org/cldr/charts/47/supplemental/language_plural_rules.html
"""

from decimal import Decimal

__all__ = ["select_plural_category"]


def select_plural_category(
    n: int | float | Decimal,
    locale: str,
    precision: int | None = None,
) -> str:
    """Select CLDR plural category for number using Babel's CLDR data.

    Args:
        n: Number to categorize
        locale: Locale code (e.g., "lv_LV", "en_US", "ar-SA")
        precision: Minimum fraction digits (for CLDR v operand), None if not specified.
            When set, number is formatted with this precision before plural matching.
            Critical for NUMBER() formatting: 1 with precision=2 becomes "1.00" which
            has v=2 (fraction digit count), affecting plural category selection.

    Returns:
        Plural category: "zero", "one", "two", "few", "many", or "other"

    Raises:
        BabelImportError: If Babel is not installed

    Examples:
        >>> select_plural_category(0, "lv_LV")
        'zero'
        >>> select_plural_category(1, "en_US")
        'one'
        >>> select_plural_category(1, "en_US", precision=2)  # "1.00" has v=2
        'other'
        >>> select_plural_category(5, "ru_RU")
        'many'
        >>> select_plural_category(2, "ar_SA")
        'two'
        >>> select_plural_category(42, "ja_JP")
        'other'

    Architecture:
        Uses Babel's Locale.plural_form which provides CLDR-compliant plural rules
        for all supported locales. This is more maintainable and complete than
        hardcoding rules for individual languages.

        Babel handles:
        - All CLDR plural categories (zero, one, two, few, many, other)
        - CLDR operands (n, i, v, w, f, t, e)
        - 200+ locales with correct rules
        - Automatic fallback to language-level rules

        If locale parsing fails, falls back to simple one/other rule.

    Performance:
        Uses cached locale parsing via get_babel_locale() to avoid
        repeated Locale.parse() overhead in hot paths.

    Precision Handling:
        When precision is provided, the number is converted to Decimal with the
        specified fraction digits. This ensures CLDR plural rules see the correct
        v operand (fraction digit count):
        - select_plural_category(1, "en_US") -> "one" (v=0: integer)
        - select_plural_category(1, "en_US", precision=2) -> "other" (v=2: "1.00")
    """
    # Lazy import to support parser-only installations
    try:
        from babel.core import UnknownLocaleError  # noqa: PLC0415
    except ImportError as e:
        from ftllexengine.core.babel_compat import BabelImportError  # noqa: PLC0415

        feature = "select_plural_category"
        raise BabelImportError(feature) from e

    from ftllexengine.locale_utils import get_babel_locale  # noqa: PLC0415

    try:
        # Use cached locale parsing for performance
        locale_obj = get_babel_locale(locale)
    except (UnknownLocaleError, ValueError):
        # Fallback to CLDR root locale for unknown/invalid locales
        # CLDR root returns "other" for all values, which is the safest
        # default since it makes no assumptions about language-specific rules.
        # The previous abs(n) == 1 heuristic was too simplistic and didn't
        # handle precision-based rules (e.g., 1 vs 1.0 distinctions).
        try:
            locale_obj = get_babel_locale("root")
        except (UnknownLocaleError, ValueError):
            # Should not happen, but ultimate fallback
            return "other"

    # Get plural rule from Babel CLDR data
    # Babel always provides plural_form for valid locales
    plural_rule = locale_obj.plural_form

    # Apply precision if specified (for CLDR v operand)
    # Use >= 0 to ensure precision=0 also triggers quantization (round to integer)
    if precision is not None and precision >= 0:
        # Convert to Decimal with specified fraction digits
        # This ensures Babel's plural rule sees the correct v operand.
        # Example: 1 with precision=2 becomes Decimal("1.00"), which has v=2.
        # Example: 1.5 with precision=0 becomes Decimal("2"), which is integer.
        # The quantize() method formats the Decimal with exact precision.

        # Create quantizer with desired precision (e.g., 0.01 for 2 digits, 1 for 0 digits)
        quantizer = Decimal(10) ** -precision
        # Convert number to Decimal and quantize
        decimal_value = Decimal(str(n)).quantize(quantizer)
        return plural_rule(decimal_value)

    # Apply CLDR plural rule with original value
    return plural_rule(n)
