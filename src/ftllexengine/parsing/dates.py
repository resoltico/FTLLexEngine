"""Date and datetime parsing functions with locale awareness.

- parse_date() returns tuple[date | None, tuple[FrozenFluentError, ...]]
- parse_datetime() returns tuple[datetime | None, tuple[FrozenFluentError, ...]]
- Parse errors returned in tuple
- Raises BabelImportError if Babel is not installed
- Pattern generation is cached per locale

Babel Dependency:
    This module requires Babel for CLDR data. Import is deferred to function call
    time to support parser-only installations. Clear error message provided when
    Babel is missing.

Timezone Handling:
    UTC offset patterns (Z, ZZ, ZZZ, ZZZZZ, x, xx, xxx, xxxx, xxxxx,
    X, XX, XXX, XXXX, XXXXX) are supported via strptime %z.

    Localized GMT format (ZZZZ) produces "GMT-08:00" which Python's strptime
    cannot parse. ZZZZ is silently skipped like timezone name patterns.

    Timezone NAME patterns (z, zz, zzz, zzzz, ZZZZ, v, vvvv, V, VV, VVV, VVVV, O, OOOO)
    are NOT supported for parsing. These tokens are stripped from the pattern,
    but the input is NOT pre-processed. Users must pre-strip timezone names
    from input or use UTC offset patterns instead.

    This limitation exists because timezone names are locale-specific (e.g.,
    "Pacific Standard Time" in English vs "Heure normale du Pacifique" in French)
    and Python's strptime has no built-in timezone name parsing.

Hour-24 Limitation:
    CLDR patterns using k/kk tokens (hour 1-24) are mapped to Python's %H (0-23).
    Input "24:00" will fail to parse. Users needing hour-24 support must
    preprocess input to normalize "24:00" to "00:00" with day increment.

Thread-safe. Uses Python 3.13 stdlib + Babel CLDR patterns.

Python 3.13+.
"""

from datetime import date, datetime, timezone
from importlib import import_module
from typing import TYPE_CHECKING, cast

from ftllexengine.diagnostics import ErrorCategory, FrozenErrorContext, FrozenFluentError
from ftllexengine.diagnostics.templates import ErrorTemplate

from .date_patterns import (
    _BABEL_TOKEN_MAP,
    _extract_datetime_separator,
    _extract_era_strings_from_babel_locale,
    _get_date_patterns,
    _get_datetime_patterns,
    _get_localized_era_strings,
    _is_word_boundary,
    _preprocess_datetime_input,
    _strip_era,
    _tokenize_babel_pattern,
    clear_date_caches,
)

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = [
    "_BABEL_TOKEN_MAP",
    "_babel_to_strptime",
    "_extract_datetime_separator",
    "_extract_era_strings_from_babel_locale",
    "_get_date_patterns",
    "_get_datetime_patterns",
    "_get_localized_era_strings",
    "_is_word_boundary",
    "_preprocess_datetime_input",
    "_strip_era",
    "_tokenize_babel_pattern",
    "clear_date_caches",
    "parse_date",
    "parse_datetime",
]

_DATE_PATTERNS_MODULE = import_module("ftllexengine.parsing.date_patterns")
_PRIVATE_DATE_EXPORTS = (
    _BABEL_TOKEN_MAP,
    _extract_datetime_separator,
    _extract_era_strings_from_babel_locale,
    _get_localized_era_strings,
    _is_word_boundary,
    _strip_era,
    _tokenize_babel_pattern,
)


def _babel_to_strptime(babel_pattern: str) -> tuple[str, bool]:
    """Convert one CLDR pattern using the patchable module-level token map."""
    module_vars = vars(_DATE_PATTERNS_MODULE)
    original_map = cast("dict[str, str | None]", module_vars["_BABEL_TOKEN_MAP"])
    module_vars["_BABEL_TOKEN_MAP"] = _BABEL_TOKEN_MAP
    try:
        converter = cast("Callable[[str], tuple[str, bool]]", module_vars["_babel_to_strptime"])
        return converter(babel_pattern)
    finally:
        module_vars["_BABEL_TOKEN_MAP"] = original_map


def parse_date(
    value: str,
    locale_code: str,
) -> tuple[date | None, tuple[FrozenFluentError, ...]]:
    """Parse locale-aware date string to date object.

    Only ISO 8601 and locale-specific CLDR patterns are supported.
    Ambiguous formats like "1/2/25" will ONLY match if locale CLDR pattern matches.

    Warning:
        Timezone names (PST, EST, CET, etc.) are NOT supported. The parser strips
        timezone name tokens from patterns but does NOT strip them from input.
        If your input contains timezone names, pre-strip them before calling this
        function, or use UTC offset patterns (e.g., "+05:00") which are supported.

    Args:
        value: Date string (e.g., "28.01.25" for lv_LV, "2025-01-28" for ISO 8601)
        locale_code: BCP 47 locale identifier (e.g., "en_US", "lv_LV", "de_DE")

    Returns:
        Tuple of (result, errors):
        - result: Parsed date object, or None if parsing failed
        - errors: Tuple of FrozenFluentError (empty tuple on success)

    Raises:
        BabelImportError: If Babel is not installed

    Examples:
        >>> result, errors = parse_date("2025-01-28", "en_US")  # ISO 8601  # doctest: +SKIP
        >>> result  # doctest: +SKIP
        datetime.date(2025, 1, 28)
        >>> errors  # doctest: +SKIP
        ()

        >>> result, errors = parse_date("1/28/25", "en_US")  # US locale format  # doctest: +SKIP
        >>> result  # doctest: +SKIP
        datetime.date(2025, 1, 28)

        >>> result, errors = parse_date("invalid", "en_US")  # doctest: +SKIP
        >>> result is None  # doctest: +SKIP
        True
        >>> len(errors)  # doctest: +SKIP
        1

    Thread Safety:
        Thread-safe. Uses Babel + stdlib (no global state).
    """
    errors: list[FrozenFluentError] = []

    # Type check: value must be string (runtime defense for untyped callers)
    if not isinstance(value, str):
        diagnostic = ErrorTemplate.parse_date_failed(  # type: ignore[unreachable]
            str(value), locale_code, f"Expected string, got {type(value).__name__}"
        )
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="date",
        )
        error = FrozenFluentError(
            str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
        )
        errors.append(error)
        return (None, tuple(errors))

    # Try ISO 8601 first (fastest path)
    try:
        return (datetime.fromisoformat(value).date(), tuple(errors))
    except ValueError:
        pass

    # Try locale-specific CLDR patterns
    patterns = _get_date_patterns(locale_code)
    if not patterns:
        # Unknown locale
        diagnostic = ErrorTemplate.parse_locale_unknown(locale_code)
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="date",
        )
        error = FrozenFluentError(
            str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
        )
        errors.append(error)
        return (None, tuple(errors))

    for pattern, has_era in patterns:
        try:
            # Preprocess for era tokens before strptime (with localized era names)
            parse_value = _preprocess_datetime_input(value, locale_code, has_era=has_era)
            return (datetime.strptime(parse_value, pattern).date(), tuple(errors))
        except ValueError:
            continue

    # All patterns failed
    diagnostic = ErrorTemplate.parse_date_failed(
        value, locale_code, "No matching date pattern found"
    )
    context = FrozenErrorContext(
        input_value=str(value),
        locale_code=locale_code,
        parse_type="date",
    )
    error = FrozenFluentError(
        str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
    )
    errors.append(error)
    return (None, tuple(errors))


def parse_datetime(
    value: str,
    locale_code: str,
    *,
    tzinfo: timezone | None = None,
) -> tuple[datetime | None, tuple[FrozenFluentError, ...]]:
    """Parse locale-aware datetime string to datetime object.

    Only ISO 8601 and locale-specific CLDR patterns are supported.

    Warning:
        Timezone names (PST, EST, CET, etc.) are NOT supported. The parser strips
        timezone name tokens from patterns but does NOT strip them from input.
        If your input contains timezone names, pre-strip them before calling this
        function, or use UTC offset patterns (e.g., "+05:00") which are supported.

    Args:
        value: DateTime string (e.g., "2025-01-28 14:30" for ISO 8601)
        locale_code: BCP 47 locale identifier (e.g., "en_US", "lv_LV", "de_DE")
        tzinfo: Timezone to assign if not in string (default: None - naive datetime)

    Returns:
        Tuple of (result, errors):
        - result: Parsed datetime object, or None if parsing failed
        - errors: Tuple of FrozenFluentError (empty tuple on success)

    Raises:
        BabelImportError: If Babel is not installed

    Examples:
        >>> result, errors = parse_datetime(  # ISO 8601  # doctest: +SKIP
        ...     "2025-01-28 14:30", "en_US"
        ... )
        >>> result  # doctest: +SKIP
        datetime.datetime(2025, 1, 28, 14, 30)
        >>> errors  # doctest: +SKIP
        ()

        >>> result, errors = parse_datetime(  # US locale  # doctest: +SKIP
        ...     "1/28/25 2:30 PM", "en_US"
        ... )
        >>> result  # doctest: +SKIP
        datetime.datetime(2025, 1, 28, 14, 30)

        >>> result, errors = parse_datetime("invalid", "en_US")  # doctest: +SKIP
        >>> result is None  # doctest: +SKIP
        True
        >>> len(errors)  # doctest: +SKIP
        1

    Thread Safety:
        Thread-safe. Uses Babel + stdlib (no global state).
    """
    errors: list[FrozenFluentError] = []

    # Type check: value must be string (runtime defense for untyped callers)
    if not isinstance(value, str):
        diagnostic = ErrorTemplate.parse_datetime_failed(  # type: ignore[unreachable]
            str(value), locale_code, f"Expected string, got {type(value).__name__}"
        )
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="datetime",
        )
        error = FrozenFluentError(
            str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
        )
        errors.append(error)
        return (None, tuple(errors))

    # Try ISO 8601 first (fastest path)
    try:
        parsed = datetime.fromisoformat(value)
        if tzinfo is not None and parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=tzinfo)
        return (parsed, tuple(errors))
    except (ValueError, TypeError):
        pass

    # Try locale-specific CLDR patterns
    patterns = _get_datetime_patterns(locale_code)
    if not patterns:
        # Unknown locale
        diagnostic = ErrorTemplate.parse_locale_unknown(locale_code)
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="datetime",
        )
        error = FrozenFluentError(
            str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
        )
        errors.append(error)
        return (None, tuple(errors))

    for pattern, has_era in patterns:
        try:
            # Preprocess for era tokens before strptime (with localized era names)
            parse_value = _preprocess_datetime_input(value, locale_code, has_era=has_era)
            parsed = datetime.strptime(parse_value, pattern)
            if tzinfo is not None and parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=tzinfo)
            return (parsed, tuple(errors))
        except ValueError:
            continue

    # All patterns failed
    diagnostic = ErrorTemplate.parse_datetime_failed(
        value, locale_code, "No matching datetime pattern found"
    )
    context = FrozenErrorContext(
        input_value=str(value),
        locale_code=locale_code,
        parse_type="datetime",
    )
    error = FrozenFluentError(
        str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
    )
    errors.append(error)
    return (None, tuple(errors))
