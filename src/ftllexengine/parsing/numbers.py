"""Number parsing functions with locale awareness.

- parse_decimal() returns tuple[Decimal | None, tuple[FrozenFluentError, ...]]
- Parse errors returned in tuple
- Raises BabelImportError if Babel is not installed

Babel Dependency:
    This module requires Babel for CLDR data. Import is deferred to function call
    time to support parser-only installations. Clear error message provided when
    Babel is missing.

Thread-safe. Uses Babel for CLDR-compliant parsing.

Python 3.13+.
"""

from decimal import Decimal, InvalidOperation

from ftllexengine.core.babel_compat import (
    get_locale_class,
    get_number_format_error_class,
    get_parse_decimal_func,
    get_unknown_locale_error_class,
    require_babel,
)
from ftllexengine.core.locale_utils import normalize_locale
from ftllexengine.diagnostics import ErrorCategory, FrozenErrorContext, FrozenFluentError
from ftllexengine.diagnostics.templates import ErrorTemplate

__all__ = ["parse_decimal"]


def parse_decimal(
    value: str,
    locale_code: str,
) -> tuple[Decimal | None, tuple[FrozenFluentError, ...]]:
    """Parse locale-aware number string to Decimal (financial precision).


    Use this for financial calculations where float precision loss
    would cause rounding errors.

    Args:
        value: Number string (e.g., "1 234,56" for lv_LV)
        locale_code: BCP 47 locale identifier

    Returns:
        Tuple of (result, errors):
        - result: Parsed Decimal, or None if parsing failed
        - errors: Tuple of FrozenFluentError (empty tuple on success)

    Raises:
        BabelImportError: If Babel is not installed

    Examples:
        >>> result, errors = parse_decimal("1,234.56", "en_US")
        >>> result
        Decimal('1234.56')
        >>> errors
        ()

        >>> result, errors = parse_decimal("1 234,56", "lv_LV")
        >>> result
        Decimal('1234.56')

        >>> result, errors = parse_decimal("invalid", "en_US")
        >>> result
        None
        >>> len(errors)
        1

    Financial Use Cases:
        # VAT calculations (no float precision loss)
        >>> amount, errors = parse_decimal("100,50", "lv_LV")
        >>> if amount is not None:
        ...     vat = amount * Decimal("0.21")
        ...     print(vat)
        21.105

    Thread Safety:
        Thread-safe. Uses Babel (no global state).
    """
    errors: list[FrozenFluentError] = []

    require_babel("parse_decimal")
    locale_class = get_locale_class()
    unknown_locale_error_class = get_unknown_locale_error_class()
    number_format_error_class = get_number_format_error_class()
    babel_parse_decimal = get_parse_decimal_func()

    try:
        locale = locale_class.parse(normalize_locale(locale_code))
    except (unknown_locale_error_class, ValueError):
        diagnostic = ErrorTemplate.parse_locale_unknown(locale_code)
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="decimal",
        )
        error = FrozenFluentError(
            str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
        )
        errors.append(error)
        return (None, tuple(errors))

    try:
        return (babel_parse_decimal(value, locale=locale), tuple(errors))
    except (
        number_format_error_class, InvalidOperation, ValueError, AttributeError, TypeError,
    ) as e:
        diagnostic = ErrorTemplate.parse_decimal_failed(value, locale_code, str(e))
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="decimal",
        )
        error = FrozenFluentError(
            str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
        )
        errors.append(error)
        return (None, tuple(errors))
