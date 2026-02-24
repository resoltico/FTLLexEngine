"""CLDR plural rules implementation using Babel.

Provides plural category selection for all locales using Babel's CLDR data.

This eliminates 300+ lines of manual rule implementation and supports all CLDR locales.

Babel Dependency:
    This module requires Babel for CLDR data. All Babel access goes through
    ftllexengine.core.babel_compat for consistent optional-dependency handling.

Python 3.13+.

Reference: https://www.unicode.org/cldr/charts/latest/supplemental/language_plural_rules.html
"""

from decimal import ROUND_HALF_UP, Decimal

from ftllexengine.core.babel_compat import get_unknown_locale_error_class, require_babel
from ftllexengine.core.locale_utils import get_babel_locale

__all__ = ["select_plural_category"]


def select_plural_category(
    n: int | Decimal,
    locale: str,
    precision: int | None = None,
) -> str:
    """Select CLDR plural category for number using Babel's CLDR data.

    Args:
        n: Number to categorize (int or Decimal). float is not accepted;
            use Decimal(str(float_val)) to convert at system boundaries.
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

        If locale parsing fails, falls back to CLDR root locale.

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
    require_babel("select_plural_category")
    unknown_locale_error_class = get_unknown_locale_error_class()

    try:
        # Use cached locale parsing for performance
        locale_obj = get_babel_locale(locale)
    except (unknown_locale_error_class, ValueError):
        # Fallback to CLDR root locale for unknown/invalid locales
        # CLDR root returns "other" for all values, which is the safest
        # default since it makes no assumptions about language-specific rules.
        try:
            locale_obj = get_babel_locale("root")
        except (unknown_locale_error_class, ValueError):  # pragma: no cover
            # Should not happen, but ultimate fallback
            return "other"

    # Non-finite Decimal guard: NaN and Infinity cannot be categorized by CLDR rules.
    # Babel's plural_rule() raises ValueError for non-finite Decimal values.
    # Per Fluent spec, resolution must never fail catastrophically.
    # Return "other" (safest category) for non-finite values.
    if isinstance(n, Decimal) and (n.is_nan() or n.is_infinite()):
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
        quantizer = Decimal(10) ** -precision
        # ROUND_HALF_UP matches the rounding mode used by locale_context.py
        # for number formatting, ensuring plural category and displayed number agree.
        decimal_value = Decimal(str(n)).quantize(quantizer, rounding=ROUND_HALF_UP)
        return plural_rule(decimal_value)

    # Apply CLDR plural rule with original value
    return plural_rule(n)
