"""Number parsing functions with locale awareness.

- parse_decimal() returns ParseResult[Decimal]
- parse_fluent_number() returns ParseResult[FluentNumber]
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
from ftllexengine.core.locale_utils import (
    is_structurally_valid_locale_code,
    normalize_locale,
)
from ftllexengine.core.value_types import FluentNumber, make_fluent_number
from ftllexengine.diagnostics import (
    ErrorCategory,
    FrozenErrorContext,
    FrozenFluentError,
    ParseResult,
)
from ftllexengine.diagnostics.templates import ErrorTemplate

__all__ = ["parse_decimal", "parse_fluent_number"]


def _validate_group_positions(
    value: str,
    group_sep: str,
    decimal_sep: str,
    primary_group: int,
    secondary_group: int,
) -> bool:
    """Return True if group separators appear at correct digit-boundary positions.

    Babel's parse_decimal strips group separators without validating their
    positions: "1,2,3" passes through as Decimal("123") for en_US. This guard
    rejects inputs where non-leftmost groups have an unexpected digit count.

    Args:
        value: Raw input string.
        group_sep: Locale's thousands separator character.
        decimal_sep: Locale's decimal separator character.
        primary_group: Expected digit count for the rightmost mandatory group.
        secondary_group: Expected digit count for all other non-leftmost groups.
    """
    int_part = value.split(decimal_sep, maxsplit=1)[0] if decimal_sep in value else value
    int_part = int_part.lstrip("+-").strip()
    if group_sep not in int_part:
        return True
    groups = int_part.split(group_sep)
    # Non-digit content means Babel will reject the input independently;
    # skip grouping check to avoid duplicate error reporting.
    if not all(g.isdigit() for g in groups):
        return True
    # Rightmost non-leftmost group must have exactly primary_group digits.
    if len(groups[-1]) != primary_group:
        return False
    # Middle groups (between leftmost and rightmost) must have secondary_group digits.
    for group in groups[1:-1]:
        if len(group) != secondary_group:
            return False
    # Leftmost group may have 1..secondary_group digits.
    return 1 <= len(groups[0]) <= secondary_group


def parse_decimal(
    value: str,
    locale_code: str,
) -> ParseResult[Decimal]:
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

    # Guard: Babel silently accepts locale codes containing non-BCP-47 characters
    # (e.g. '/', '\x00') instead of raising UnknownLocaleError, then uses default
    # number format settings and parses any valid-looking number successfully.
    # Reject structurally malformed codes before reaching Babel.
    if not is_structurally_valid_locale_code(locale_code):
        diagnostic = ErrorTemplate.parse_locale_unknown(locale_code)
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="decimal",
        )
        errors.append(FrozenFluentError(
            str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
        ))
        return (None, tuple(errors))

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

    # Guard: Babel strips group separators without validating their positions.
    # Extract the locale's group/decimal symbols and expected group sizes, then
    # reject inputs where non-leftmost groups have the wrong digit count (e.g.,
    # "1,2,3" for en_US becomes Decimal("123") without this check).
    try:
        _ns = locale.number_symbols[locale.default_numbering_system]
        group_sep: str = _ns.get("group", "")
        decimal_sep: str = _ns.get("decimal", ".")
        fmt = locale.decimal_formats[None]
        raw_grouping = getattr(fmt, "grouping", (3, 3))
        primary_group: int = raw_grouping[0] if raw_grouping else 3
        secondary_group: int = (
            raw_grouping[1]
            if len(raw_grouping) > 1 and raw_grouping[1] != 0
            else primary_group
        )
    except (AttributeError, KeyError, IndexError, TypeError):
        group_sep, decimal_sep, primary_group, secondary_group = "", ".", 3, 3

    if (
        group_sep
        and group_sep in value
        and not _validate_group_positions(
            value, group_sep, decimal_sep, primary_group, secondary_group
        )
    ):
        diagnostic = ErrorTemplate.parse_decimal_failed(
            value, locale_code, "group separators not at standard digit-boundary positions"
        )
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="decimal",
        )
        error = FrozenFluentError(
            str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
        )
        return (None, (error,))

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


def parse_fluent_number(
    value: str,
    locale_code: str,
) -> ParseResult[FluentNumber]:
    """Parse locale-aware number string directly to FluentNumber.

    This is the public composition of ``parse_decimal()`` and
    ``make_fluent_number()``. It preserves the original localized display text
    while keeping the exact numeric identity and visible-precision metadata
    needed by Fluent select expressions.

    Args:
        value: Number string as entered or stored in localized form
        locale_code: BCP 47 locale identifier

    Returns:
        Tuple of (result, errors):
        - result: Parsed FluentNumber, or None if parsing failed
        - errors: Tuple of FrozenFluentError (empty tuple on success)

    Raises:
        BabelImportError: If Babel is not installed

    Examples:
        >>> result, errors = parse_fluent_number("1 234,50", "lv_LV")
        >>> str(result)
        '1 234,50'
        >>> result.value
        Decimal('1234.50')
        >>> result.precision
        2
    """
    require_babel("parse_fluent_number")
    parsed, errors = parse_decimal(value, locale_code)
    if parsed is None:
        return (None, errors)
    return (make_fluent_number(parsed, formatted=value), errors)
