"""Number parsing functions with locale awareness.

- parse_number() returns tuple[float | None, tuple[FluentParseError, ...]]
- parse_decimal() returns tuple[Decimal | None, tuple[FluentParseError, ...]]
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

from ftllexengine.diagnostics import FluentParseError
from ftllexengine.diagnostics.templates import ErrorTemplate
from ftllexengine.locale_utils import normalize_locale

__all__ = ["parse_decimal", "parse_number"]


def parse_number(
    value: str,
    locale_code: str,
) -> tuple[float | None, tuple[FluentParseError, ...]]:
    """Parse locale-aware number string to float.

    Warning:
        This function converts to float, which loses precision for large integers
        and certain decimal values. For financial calculations or values requiring
        exact precision, use parse_decimal() instead which returns Decimal.

        Examples of precision loss:
        - Large integers: 1234567890123456789 may round incorrectly
        - Decimal fractions: 0.1 + 0.2 != 0.3 in float arithmetic

    Args:
        value: Number string (e.g., "1 234,56" for lv_LV)
        locale_code: BCP 47 locale identifier

    Returns:
        Tuple of (result, errors):
        - result: Parsed float, or None if parsing failed
        - errors: Tuple of FluentParseError (empty tuple on success)

    Raises:
        BabelImportError: If Babel is not installed

    Examples:
        >>> result, errors = parse_number("1,234.5", "en_US")
        >>> result
        1234.5
        >>> errors
        ()

        >>> result, errors = parse_number("1 234,5", "lv_LV")
        >>> result
        1234.5

        >>> result, errors = parse_number("invalid", "en_US")
        >>> result
        None
        >>> len(errors)
        1
        >>> errors[0].parse_type
        'number'

    Thread Safety:
        Thread-safe. Uses Babel (no global state).

    See Also:
        parse_decimal: For exact precision (financial calculations)
    """
    errors: list[FluentParseError] = []

    # Lazy import to support parser-only installations
    try:
        from babel import Locale, UnknownLocaleError  # noqa: PLC0415
        from babel.numbers import NumberFormatError  # noqa: PLC0415
        from babel.numbers import parse_decimal as babel_parse_decimal  # noqa: PLC0415
    except ImportError as e:
        from ftllexengine.core.babel_compat import BabelImportError  # noqa: PLC0415

        raise BabelImportError("parse_number") from e  # noqa: EM101

    try:
        locale = Locale.parse(normalize_locale(locale_code))
    except (UnknownLocaleError, ValueError):
        diagnostic = ErrorTemplate.parse_locale_unknown(locale_code)
        errors.append(
            FluentParseError(
                diagnostic,
                input_value=value,
                locale_code=locale_code,
                parse_type="number",
            )
        )
        return (None, tuple(errors))

    try:
        parsed = babel_parse_decimal(value, locale=locale)
        return (float(parsed), tuple(errors))
    except (
        NumberFormatError,
        InvalidOperation,
        ValueError,
        AttributeError,
        TypeError,
        OverflowError,  # float() on extremely large Decimal (e.g., 1e1000)
    ) as e:
        diagnostic = ErrorTemplate.parse_number_failed(value, locale_code, str(e))
        errors.append(
            FluentParseError(
                diagnostic,
                input_value=value,
                locale_code=locale_code,
                parse_type="number",
            )
        )
        return (None, tuple(errors))


def parse_decimal(
    value: str,
    locale_code: str,
) -> tuple[Decimal | None, tuple[FluentParseError, ...]]:
    """Parse locale-aware number string to Decimal (financial precision).


    Use this for financial calculations where float precision loss
    would cause rounding errors.

    Args:
        value: Number string (e.g., "1 234,56" for lv_LV)
        locale_code: BCP 47 locale identifier

    Returns:
        Tuple of (result, errors):
        - result: Parsed Decimal, or None if parsing failed
        - errors: Tuple of FluentParseError (empty tuple on success)

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
    errors: list[FluentParseError] = []

    # Lazy import to support parser-only installations
    try:
        from babel import Locale, UnknownLocaleError  # noqa: PLC0415
        from babel.numbers import NumberFormatError  # noqa: PLC0415
        from babel.numbers import parse_decimal as babel_parse_decimal  # noqa: PLC0415
    except ImportError as e:
        from ftllexengine.core.babel_compat import BabelImportError  # noqa: PLC0415

        raise BabelImportError("parse_decimal") from e  # noqa: EM101

    try:
        locale = Locale.parse(normalize_locale(locale_code))
    except (UnknownLocaleError, ValueError):
        diagnostic = ErrorTemplate.parse_locale_unknown(locale_code)
        errors.append(
            FluentParseError(
                diagnostic,
                input_value=value,
                locale_code=locale_code,
                parse_type="decimal",
            )
        )
        return (None, tuple(errors))

    try:
        return (babel_parse_decimal(value, locale=locale), tuple(errors))
    except (NumberFormatError, InvalidOperation, ValueError, AttributeError, TypeError) as e:
        diagnostic = ErrorTemplate.parse_decimal_failed(value, locale_code, str(e))
        errors.append(
            FluentParseError(
                diagnostic,
                input_value=value,
                locale_code=locale_code,
                parse_type="decimal",
            )
        )
        return (None, tuple(errors))
