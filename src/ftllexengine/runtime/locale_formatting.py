"""Locale-scoped formatting helpers used by ``LocaleContext``.

Keeps the public ``LocaleContext`` facade focused on cache and lifecycle
management while the heavy number/date/currency formatting machinery lives in a
dedicated internal module.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Literal

from ftllexengine.constants import FALLBACK_FUNCTION_ERROR, MAX_FORMAT_DIGITS
from ftllexengine.core.babel_compat import get_babel_dates, get_babel_numbers
from ftllexengine.diagnostics import ErrorCategory, FrozenErrorContext, FrozenFluentError
from ftllexengine.diagnostics.templates import ErrorTemplate

if TYPE_CHECKING:
    from babel import Locale

    from ftllexengine.core.semantic_types import LocaleCode

logger = logging.getLogger(__name__)

__all__ = [
    "format_currency_for_locale",
    "format_datetime_for_locale",
    "format_number_for_locale",
    "get_iso_code_pattern_for_locale",
]


def format_number_for_locale(
    *,
    locale_code: LocaleCode,
    babel_locale: Locale,
    value: int | Decimal,
    minimum_fraction_digits: int = 0,
    maximum_fraction_digits: int = 3,
    use_grouping: bool = True,
    pattern: str | None = None,
    numbering_system: str = "latn",
) -> str:
    """Format a number using the supplied Babel locale."""
    if not 0 <= minimum_fraction_digits <= MAX_FORMAT_DIGITS:
        msg = (
            f"minimum_fraction_digits must be 0-{MAX_FORMAT_DIGITS}, "
            f"got {minimum_fraction_digits}"
        )
        raise ValueError(msg)
    if not 0 <= maximum_fraction_digits <= MAX_FORMAT_DIGITS:
        msg = (
            f"maximum_fraction_digits must be 0-{MAX_FORMAT_DIGITS}, "
            f"got {maximum_fraction_digits}"
        )
        raise ValueError(msg)
    maximum_fraction_digits = max(maximum_fraction_digits, minimum_fraction_digits)

    babel_numbers = get_babel_numbers()

    try:
        if pattern is not None:
            return str(
                babel_numbers.format_decimal(
                    value,
                    format=pattern,
                    locale=babel_locale,
                    numbering_system=numbering_system,
                )
            )

        integer_part = "#,##0" if use_grouping else "0"

        if maximum_fraction_digits == 0:
            format_pattern = integer_part
        elif minimum_fraction_digits == maximum_fraction_digits:
            decimal_part = "0" * minimum_fraction_digits
            format_pattern = f"{integer_part}.{decimal_part}"
        else:
            required = "0" * minimum_fraction_digits
            optional = "#" * (maximum_fraction_digits - minimum_fraction_digits)
            format_pattern = f"{integer_part}.{required}{optional}"

        return str(
            babel_numbers.format_decimal(
                value,
                format=format_pattern,
                locale=babel_locale,
                numbering_system=numbering_system,
            )
        )

    except (ValueError, TypeError, InvalidOperation, AttributeError, KeyError) as e:
        fallback = str(value)
        diagnostic = ErrorTemplate.formatting_failed("NUMBER", str(value), str(e))
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="number",
            fallback_value=fallback,
        )
        raise FrozenFluentError(
            str(diagnostic),
            ErrorCategory.FORMATTING,
            diagnostic=diagnostic,
            context=context,
        ) from e


def format_datetime_for_locale(
    *,
    locale_code: LocaleCode,
    babel_locale: Locale,
    value: date | datetime | str,
    date_style: Literal["short", "medium", "long", "full"] = "medium",
    time_style: Literal["short", "medium", "long", "full"] | None = None,
    pattern: str | None = None,
) -> str:
    """Format a date or datetime using the supplied Babel locale."""
    babel_dates = get_babel_dates()
    dt_value: datetime | date

    if isinstance(value, str):
        try:
            dt_value = datetime.fromisoformat(value)
        except ValueError as e:
            fallback = FALLBACK_FUNCTION_ERROR.format(name="DATETIME")
            diagnostic = ErrorTemplate.formatting_failed(
                "DATETIME", value, "not ISO 8601 format"
            )
            context = FrozenErrorContext(
                input_value=value,
                locale_code=locale_code,
                parse_type="datetime",
                fallback_value=fallback,
            )
            raise FrozenFluentError(
                str(diagnostic),
                ErrorCategory.FORMATTING,
                diagnostic=diagnostic,
                context=context,
            ) from e
    elif isinstance(value, datetime):
        dt_value = value
    else:
        dt_value = value

    if isinstance(dt_value, date) and not isinstance(dt_value, datetime) and (
        time_style is not None or pattern is not None
    ):
        dt_value = datetime(  # noqa: DTZ001 - date carries no tz; midnight promotion is explicitly naive
            dt_value.year,
            dt_value.month,
            dt_value.day,
        )

    try:
        if pattern is not None:
            return str(
                babel_dates.format_datetime(
                    dt_value,
                    format=pattern,
                    locale=babel_locale,
                )
            )

        if time_style:
            date_str = babel_dates.format_date(
                dt_value,
                format=date_style,
                locale=babel_locale,
            )
            time_str = babel_dates.format_time(
                dt_value,
                format=time_style,
                locale=babel_locale,
            )
            datetime_pattern = (
                babel_locale.datetime_formats.get(date_style)
                or babel_locale.datetime_formats.get("medium")
                or babel_locale.datetime_formats.get("short")
                or "{1} {0}"
            )
            if hasattr(datetime_pattern, "format"):
                return str(datetime_pattern.format(time_str, date_str))
            return str(datetime_pattern).format(time_str, date_str)

        return str(
            babel_dates.format_date(
                dt_value,
                format=date_style,
                locale=babel_locale,
            )
        )

    except (ValueError, OverflowError, AttributeError, KeyError) as e:
        fallback = dt_value.isoformat()
        diagnostic = ErrorTemplate.formatting_failed("DATETIME", str(dt_value), str(e))
        context = FrozenErrorContext(
            input_value=str(dt_value),
            locale_code=locale_code,
            parse_type="datetime",
            fallback_value=fallback,
        )
        raise FrozenFluentError(
            str(diagnostic),
            ErrorCategory.FORMATTING,
            diagnostic=diagnostic,
            context=context,
        ) from e


def format_currency_for_locale(
    *,
    locale_code: LocaleCode,
    babel_locale: Locale,
    value: int | Decimal,
    currency: str,
    currency_display: Literal["symbol", "code", "name"] = "symbol",
    pattern: str | None = None,
    use_grouping: bool = True,
    currency_digits: bool = True,
    numbering_system: str = "latn",
    debug_logger: logging.Logger | None = None,
) -> str:
    """Format a currency value using the supplied Babel locale."""
    babel_numbers = get_babel_numbers()

    try:
        if pattern is not None:
            return str(
                babel_numbers.format_currency(
                    value,
                    currency,
                    format=pattern,
                    locale=babel_locale,
                    currency_digits=False,
                    group_separator=use_grouping,
                    numbering_system=numbering_system,
                )
            )

        if currency_display == "name":
            format_type: Literal["name", "standard", "accounting"] = "name"
            return str(
                babel_numbers.format_currency(
                    value,
                    currency,
                    locale=babel_locale,
                    currency_digits=currency_digits,
                    format_type=format_type,
                    group_separator=use_grouping,
                    numbering_system=numbering_system,
                )
            )

        if currency_display == "code":
            code_pattern = get_iso_code_pattern_for_locale(
                locale_code=locale_code,
                babel_locale=babel_locale,
                debug_logger=debug_logger,
            )
            if code_pattern is not None:
                return str(
                    babel_numbers.format_currency(
                        value,
                        currency,
                        format=code_pattern,
                        locale=babel_locale,
                        currency_digits=currency_digits,
                        group_separator=use_grouping,
                        numbering_system=numbering_system,
                    )
                )

        return str(
            babel_numbers.format_currency(
                value,
                currency,
                locale=babel_locale,
                currency_digits=currency_digits,
                format_type="standard",
                group_separator=use_grouping,
                numbering_system=numbering_system,
            )
        )

    except (ValueError, TypeError, InvalidOperation, AttributeError, KeyError) as e:
        fallback = f"{currency} {value}"
        diagnostic = ErrorTemplate.formatting_failed(
            "CURRENCY", f"{currency} {value}", str(e)
        )
        context = FrozenErrorContext(
            input_value=f"{currency} {value}",
            locale_code=locale_code,
            parse_type="currency",
            fallback_value=fallback,
        )
        raise FrozenFluentError(
            str(diagnostic),
            ErrorCategory.FORMATTING,
            diagnostic=diagnostic,
            context=context,
        ) from e


def get_iso_code_pattern_for_locale(
    *,
    locale_code: LocaleCode,
    babel_locale: Locale,
    debug_logger: logging.Logger | None = None,
) -> str | None:
    """Return a CLDR currency pattern rewritten for ISO code display."""
    active_logger = logger if debug_logger is None else debug_logger
    locale_currency_formats = babel_locale.currency_formats
    standard_pattern = locale_currency_formats.get("standard")
    if standard_pattern is None or not hasattr(standard_pattern, "pattern"):
        return None

    raw_pattern = standard_pattern.pattern
    if "\xa4" not in raw_pattern:
        active_logger.debug(
            "Currency pattern for locale %s lacks placeholder",
            locale_code,
        )
        return None

    return str(raw_pattern.replace("\xa4", "\xa4\xa4"))
