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


def select_plural_category(n: int | float | Decimal, locale: str) -> str:
    """Select CLDR plural category for number using Babel's CLDR data.

    Args:
        n: Number to categorize
        locale: Locale code (e.g., "lv_LV", "en_US", "ar-SA")

    Returns:
        Plural category: "zero", "one", "two", "few", "many", or "other"

    Raises:
        BabelImportError: If Babel is not installed

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
    """
    # Lazy import to support parser-only installations
    try:
        from babel.core import UnknownLocaleError  # noqa: PLC0415
    except ImportError as e:
        from ftllexengine.core.babel_compat import BabelImportError  # noqa: PLC0415

        raise BabelImportError("select_plural_category") from e  # noqa: EM101

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

    # Apply CLDR plural rule
    return plural_rule(n)
