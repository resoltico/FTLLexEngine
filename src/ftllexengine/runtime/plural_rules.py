"""CLDR plural rules implementation using Babel.

Provides plural category selection for all locales using Babel's CLDR data.

This eliminates 300+ lines of manual rule implementation and supports all CLDR locales.

Python 3.13+. Depends on Babel for CLDR data.

Reference: https://www.unicode.org/cldr/charts/47/supplemental/language_plural_rules.html
"""

from babel import Locale
from babel.core import UnknownLocaleError

from ftllexengine.locale_utils import normalize_locale


def select_plural_category(n: int | float, locale: str) -> str:
    """Select CLDR plural category for number using Babel's CLDR data.

    Args:
        n: Number to categorize
        locale: Locale code (e.g., "lv_LV", "en_US", "ar-SA")

    Returns:
        Plural category: "zero", "one", "two", "few", "many", or "other"

    Examples:
        >>> select_plural_category(0, "lv_LV")
        'zero'
        >>> select_plural_category(1, "en_US")
        'one'
        >>> select_plural_category(5, "ru_RU")
        'many'
        >>> select_plural_category(2, "ar_SA")
        'two'
        >>> select_plural_category(42, "ja_JP")
        'other'

    v0.9.0 Architecture:
        Uses Babel's Locale.plural_form which provides CLDR-compliant plural rules
        for all supported locales. This is more maintainable and complete than
        hardcoding rules for individual languages.

        Babel handles:
        - All CLDR plural categories (zero, one, two, few, many, other)
        - CLDR operands (n, i, v, w, f, t, e)
        - 200+ locales with correct rules
        - Automatic fallback to language-level rules

        If locale parsing fails, falls back to simple one/other rule.
    """
    try:
        # Parse locale (supports both en_US and en-US formats)
        locale_obj = Locale.parse(normalize_locale(locale), sep="_")
    except (UnknownLocaleError, ValueError):
        # Fallback for unknown/invalid locales
        # Most common pattern: n == 1 → "one", else → "other"
        return "one" if abs(n) == 1 else "other"

    # Get plural rule from Babel CLDR data
    # Babel always provides plural_form for valid locales
    plural_rule = locale_obj.plural_form

    # Apply CLDR plural rule
    return plural_rule(n)
