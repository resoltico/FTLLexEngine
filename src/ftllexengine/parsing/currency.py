"""Currency parsing with locale awareness.

API: parse_currency() returns tuple[tuple[Decimal, str] | None, tuple[FrozenFluentError, ...]].
Parse errors returned in tuple. Raises BabelImportError if Babel not installed.

Thread-safe. Uses Babel for currency symbol mapping and number parsing.
All currency data sourced from Unicode CLDR via Babel.

Babel Dependency:
    This module requires Babel for CLDR data. Import is deferred to function call
    time to support parser-only installations. Clear error message provided when
    Babel is missing.

Data Architecture:
    - Fast Tier: Hardcoded common currencies for merge-priority and Babel-absent fallback
    - Full Tier: Complete CLDR scan (lazy-loaded via @functools.cache on first access)
    - Merged maps: Fast tier overrides full tier for unambiguous symbol assignments

Symbol Detection:
    Uses a single regex pattern built from the complete merged symbol set (fast tier +
    CLDR). Symbols are sorted longest-first to guarantee correct detection of multi-char
    symbols (e.g., "Rs" before "R", "kr." before "kr", "$AU" before "$"). The CLDR scan
    cost (~200-500ms) is incurred once per process on first parse_currency() call, then
    cached via @functools.cache.

Architecture:
    Uses @functools.cache for thread-safe, lazy-loaded CLDR data access.
    - Locale-aware symbol resolution for ambiguous symbols via resolve_ambiguous_symbol()
    - Consistent with dates.py pattern for CLDR data access

Python 3.13+.
"""
from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from decimal import Decimal

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
from ftllexengine.diagnostics import ErrorCategory, FrozenErrorContext, FrozenFluentError
from ftllexengine.diagnostics.templates import ErrorTemplate
from ftllexengine.parsing.currency_maps import (
    _FAST_TIER_UNAMBIGUOUS_SYMBOLS,
    ISO_CURRENCY_CODE_LENGTH,
    _build_currency_maps_from_cldr,
    _get_currency_maps,
    _get_currency_maps_fast,
    _get_currency_maps_full,
    resolve_ambiguous_symbol,
)
from ftllexengine.parsing.currency_maps import (
    clear_currency_caches as _clear_currency_maps_caches,
)

__all__ = [
    "_FAST_TIER_UNAMBIGUOUS_SYMBOLS",
    "_build_currency_maps_from_cldr",
    "_get_currency_maps",
    "_get_currency_maps_fast",
    "_get_currency_maps_full",
    "clear_currency_caches",
    "parse_currency",
    "resolve_ambiguous_symbol",
]

_PRIVATE_CURRENCY_EXPORTS = (
    _FAST_TIER_UNAMBIGUOUS_SYMBOLS,
    _build_currency_maps_from_cldr,
    _get_currency_maps_fast,
    _get_currency_maps_full,
)



def _is_valid_iso_4217_format(code: str) -> bool:
    """Check if code matches ISO 4217 format: exactly 3 uppercase ASCII letters.

    This validates format only, not existence in CLDR database.
    Per ISO 4217 standard, currency codes are exactly 3 uppercase ASCII letters.
    """
    return (
        len(code) == ISO_CURRENCY_CODE_LENGTH
        and code.isascii()
        and code.isupper()
        and code.isalpha()
    )


def _resolve_currency_code(
    currency_str: str,
    locale_code: str,
    value: str,
    *,
    default_currency: str | None,
    infer_from_locale: bool,
) -> tuple[str | None, FrozenFluentError | None]:
    """Resolve currency string to ISO code with error handling.

    Helper function to reduce statement count in parse_currency.

    Args:
        currency_str: Currency symbol or ISO code from input
        locale_code: BCP 47 locale identifier
        value: Original input value (for error messages)
        default_currency: Explicit currency for ambiguous symbols
        infer_from_locale: Whether to infer currency from locale

    Returns:
        Tuple of (currency_code, error) - one will be None
    """
    is_iso_code = _is_valid_iso_4217_format(currency_str)

    symbol_map, ambiguous_symbols, locale_to_currency, valid_iso_codes = _get_currency_maps()

    if is_iso_code:
        # ISO code - validate against CLDR data
        if currency_str not in valid_iso_codes:
            diagnostic = ErrorTemplate.parse_currency_code_invalid(currency_str, value)
            context = FrozenErrorContext(
                input_value=str(value), locale_code=locale_code, parse_type="currency"
            )
            error = FrozenFluentError(
                str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
            )
            return (None, error)
        return (currency_str, None)

    # It's a symbol - check if ambiguous
    if currency_str in ambiguous_symbols:
        if default_currency:
            # Validate default_currency is a valid ISO 4217 format
            if not _is_valid_iso_4217_format(default_currency):
                diagnostic = ErrorTemplate.parse_currency_code_invalid(default_currency, value)
                context = FrozenErrorContext(
                    input_value=str(value), locale_code=locale_code, parse_type="currency"
                )
                error = FrozenFluentError(
                    str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
                )
                return (None, error)
            return (default_currency, None)
        if infer_from_locale:
            # Locale-aware resolution for ambiguous symbols
            resolved = resolve_ambiguous_symbol(currency_str, locale_code)
            if resolved:
                return (resolved, None)
            # Fall back to locale-to-currency mapping
            inferred = locale_to_currency.get(normalize_locale(locale_code))
            if inferred:
                return (inferred, None)
        # No resolution available
        diagnostic = ErrorTemplate.parse_currency_ambiguous(currency_str, value)
        context = FrozenErrorContext(
            input_value=str(value), locale_code=locale_code, parse_type="currency"
        )
        error = FrozenFluentError(
            str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
        )
        return (None, error)

    # Unambiguous symbol - use mapping
    mapped = symbol_map.get(currency_str)
    if mapped is None:
        diagnostic = ErrorTemplate.parse_currency_symbol_unknown(currency_str, value)
        context = FrozenErrorContext(
            input_value=str(value), locale_code=locale_code, parse_type="currency"
        )
        error = FrozenFluentError(
            str(diagnostic), ErrorCategory.PARSE, diagnostic=diagnostic, context=context
        )
        return (None, error)
    return (mapped, None)


@functools.cache
def _get_currency_pattern() -> re.Pattern[str]:
    """Compile currency detection regex from merged symbol maps.

    Builds a single pattern from the complete merged symbol set (fast tier +
    CLDR). Symbols are sorted longest-first to guarantee correct detection of
    multi-char symbols before their prefixes (e.g., "Rs" before "R", "kr."
    before "kr", "$AU" before "$").

    Thread-safe via functools.cache internal locking.
    Called once per process lifetime; subsequent calls return cached result.

    Returns:
        Compiled regex pattern matching:
        - ISO 4217 3-letter currency codes (e.g., EUR, USD, JPY) - matched first
        - All symbols from merged currency maps (unambiguous and ambiguous)

    Pattern Priority:
        1. ISO codes (3 uppercase ASCII letters) - matched first to avoid
           partial symbol matches (e.g., 'F' matching before 'FFF')
        2. Longer symbols matched before shorter to prevent partial matches
           (e.g., "Rs" before "R", "kr." before "kr")
    """
    symbol_map, ambiguous, _, _ = _get_currency_maps()

    # Collect all symbols from both maps
    all_symbols: set[str] = set(symbol_map.keys()) | ambiguous

    # Sort by length descending to match longer symbols first
    # This prevents "R" matching before "Rs" or "kr" before "kr."
    sorted_symbols = sorted(all_symbols, key=len, reverse=True)

    # Escape special regex characters in symbols
    escaped_symbols = [re.escape(sym) for sym in sorted_symbols]

    # Build pattern: ISO codes FIRST, then symbols
    # ISO codes first ensures 'FFF' matches as code, not partial symbol match
    if escaped_symbols:
        symbols_pattern = "|".join(escaped_symbols)
        pattern = rf"([A-Z]{{{ISO_CURRENCY_CODE_LENGTH}}}|{symbols_pattern})"
    else:
        # Fallback if no symbols found (shouldn't happen with CLDR)
        pattern = rf"([A-Z]{{{ISO_CURRENCY_CODE_LENGTH}}})"

    return re.compile(pattern)


def _detect_currency_symbol(
    value: str,
    locale_code: str,
) -> tuple[re.Match[str] | None, FrozenFluentError | None]:
    """Detect currency symbol or ISO code in input string.

    Uses a single longest-match-first regex built from the complete merged
    symbol set (fast tier + CLDR). This guarantees multi-char symbols are
    matched before their single-char prefixes (e.g., "Rs" before "R").

    Args:
        value: Currency string to search.
        locale_code: BCP 47 locale identifier (for error context).

    Returns:
        Tuple of (match, error) - exactly one is None.
    """
    pattern = _get_currency_pattern()
    match = pattern.search(value)

    if not match:
        diagnostic = ErrorTemplate.parse_currency_failed(
            value, locale_code, "No currency symbol or code found",
        )
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="currency",
        )
        error = FrozenFluentError(
            str(diagnostic),
            ErrorCategory.PARSE,
            diagnostic=diagnostic,
            context=context,
        )
        return (None, error)

    return (match, None)


def _parse_currency_amount(
    value: str,
    match: re.Match[str],
    locale: Any,
    locale_code: str,
    parse_decimal_fn: Any,
    number_format_error: type[Exception],
) -> tuple[Decimal | None, FrozenFluentError | None]:
    """Extract and parse the numeric amount from a currency string.

    Removes the matched currency symbol/code and parses the remainder
    as a locale-formatted number.

    Args:
        value: Original currency string.
        match: Regex match containing the currency symbol/code.
        locale: Babel Locale object.
        locale_code: BCP 47 locale identifier (for error context).
        parse_decimal_fn: Babel's parse_decimal function.
        number_format_error: Babel's NumberFormatError class.

    Returns:
        Tuple of (amount, error) - exactly one is None.
    """
    # Remove ONLY the matched occurrence, not all instances.
    # Prevents corruption if the symbol appears elsewhere in the string.
    number_str = (
        value[:match.start(1)] + value[match.end(1):]
    ).strip()

    try:
        amount = parse_decimal_fn(number_str, locale=locale)
    except number_format_error as e:
        diagnostic = ErrorTemplate.parse_amount_invalid(
            number_str, value, str(e),
        )
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="currency",
        )
        error = FrozenFluentError(
            str(diagnostic),
            ErrorCategory.PARSE,
            diagnostic=diagnostic,
            context=context,
        )
        return (None, error)

    return (amount, None)


def parse_currency(
    value: str,
    locale_code: str,
    *,
    default_currency: str | None = None,
    infer_from_locale: bool = False,
) -> tuple[tuple[Decimal, str] | None, tuple[FrozenFluentError, ...]]:
    """Parse locale-aware currency string to (amount, currency_code).

    Extracts both numeric value and currency code from formatted string.

    Ambiguous currency symbols ($, kr) require explicit default_currency
    or infer_from_locale=True. This prevents silent misidentification
    in multi-currency applications.

    Phases:
        1. Validate inputs (type check, locale parse)
        2. Detect currency symbol/code (longest-match-first regex)
        3. Resolve symbol to ISO 4217 code
        4. Parse numeric amount

    Args:
        value: Currency string (e.g., "100,50 EUR" for lv_LV, "$100" with default_currency)
        locale_code: BCP 47 locale identifier
        default_currency: ISO 4217 code for ambiguous symbols (e.g., "CAD" for "$")
        infer_from_locale: Infer currency from locale if symbol is ambiguous

    Returns:
        Tuple of (result, errors):
        - result: Tuple of (amount, currency_code), or None if parsing failed
        - errors: Tuple of FrozenFluentError (empty tuple on success)

    Raises:
        BabelImportError: If Babel is not installed

    Examples:
        >>> result, errors = parse_currency("EUR100.50", "en_US")  # doctest: +SKIP
        >>> result  # doctest: +SKIP
        (Decimal('100.50'), 'EUR')
        >>> errors  # doctest: +SKIP
        ()

        >>> result, errors = parse_currency("100,50 EUR", "lv_LV")  # doctest: +SKIP
        >>> result  # doctest: +SKIP
        (Decimal('100.50'), 'EUR')

        >>> result, errors = parse_currency("USD 1,234.56", "en_US")  # doctest: +SKIP
        >>> result  # doctest: +SKIP
        (Decimal('1234.56'), 'USD')

        >>> result, errors = parse_currency(  # doctest: +SKIP
        ...     "$100", "en_US", default_currency="USD"
        ... )
        >>> result  # doctest: +SKIP
        (Decimal('100'), 'USD')

        >>> result, errors = parse_currency(  # doctest: +SKIP
        ...     "$100", "en_CA", default_currency="CAD"
        ... )
        >>> result  # doctest: +SKIP
        (Decimal('100'), 'CAD')

        >>> result, errors = parse_currency(  # doctest: +SKIP
        ...     "$100", "en_CA", infer_from_locale=True
        ... )
        >>> result  # doctest: +SKIP
        (Decimal('100'), 'CAD')

        >>> result, errors = parse_currency("$100", "en_US")  # doctest: +SKIP
        >>> result is None  # doctest: +SKIP
        True
        >>> len(errors)  # doctest: +SKIP
        1

    Note:
        Ambiguous symbols: $ (USD/CAD/AUD/etc), kr (SEK/NOK/DKK/ISK)
        Always use ISO codes (USD, CAD, EUR) for unambiguous parsing.

    Thread Safety:
        Thread-safe. Uses Babel (no global state).
    """
    # Phase 1: Validate inputs
    require_babel("parse_currency")
    locale_class = get_locale_class()
    unknown_locale_error_class = get_unknown_locale_error_class()
    number_format_error_class = get_number_format_error_class()
    parse_decimal = get_parse_decimal_func()

    if not isinstance(value, str):
        diagnostic = ErrorTemplate.parse_currency_failed(  # type: ignore[unreachable]
            str(value),
            locale_code,
            f"Expected string, got {type(value).__name__}",
        )
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="currency",
        )
        return (None, (FrozenFluentError(
            str(diagnostic),
            ErrorCategory.PARSE,
            diagnostic=diagnostic,
            context=context,
        ),))

    # Guard: Babel silently accepts locale codes containing non-BCP-47 characters
    # (e.g. '/', '\x00') instead of raising UnknownLocaleError, then uses default
    # number format settings and may parse values unexpectedly.
    # Reject structurally malformed codes before reaching Babel.
    if not is_structurally_valid_locale_code(locale_code):
        diagnostic = ErrorTemplate.parse_locale_unknown(locale_code)
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="currency",
        )
        return (None, (FrozenFluentError(
            str(diagnostic),
            ErrorCategory.PARSE,
            diagnostic=diagnostic,
            context=context,
        ),))

    try:
        locale = locale_class.parse(normalize_locale(locale_code))
    except (unknown_locale_error_class, ValueError):
        diagnostic = ErrorTemplate.parse_locale_unknown(locale_code)
        context = FrozenErrorContext(
            input_value=str(value),
            locale_code=locale_code,
            parse_type="currency",
        )
        return (None, (FrozenFluentError(
            str(diagnostic),
            ErrorCategory.PARSE,
            diagnostic=diagnostic,
            context=context,
        ),))

    # Phase 2: Detect currency symbol/code
    match, detect_error = _detect_currency_symbol(value, locale_code)
    if detect_error is not None or match is None:
        if detect_error is not None:
            return (None, (detect_error,))
        # Defensive: _detect_currency_symbol contract guarantees
        # exactly one of (match, error) is non-None.
        diagnostic = ErrorTemplate.parse_currency_failed(  # pragma: no cover
            value, locale_code, "No currency symbol or code found",
        )
        context = FrozenErrorContext(  # pragma: no cover
            input_value=str(value),
            locale_code=locale_code,
            parse_type="currency",
        )
        return (None, (FrozenFluentError(  # pragma: no cover
            str(diagnostic),
            ErrorCategory.PARSE,
            diagnostic=diagnostic,
            context=context,
        ),))

    currency_str = match.group(1)

    # Phase 3: Resolve symbol to ISO 4217 code
    currency_code, resolution_error = _resolve_currency_code(
        currency_str,
        locale_code,
        value,
        default_currency=default_currency,
        infer_from_locale=infer_from_locale,
    )
    if resolution_error is not None:
        return (None, (resolution_error,))
    if currency_code is None:
        # Defensive: _resolve_currency_code contract guarantees
        # exactly one of (code, error) is non-None.
        diagnostic = ErrorTemplate.parse_currency_failed(  # pragma: no cover
            value, locale_code, "Currency resolution failed",
        )
        context = FrozenErrorContext(  # pragma: no cover
            input_value=str(value),
            locale_code=locale_code,
            parse_type="currency",
        )
        return (None, (FrozenFluentError(  # pragma: no cover
            str(diagnostic),
            ErrorCategory.PARSE,
            diagnostic=diagnostic,
            context=context,
        ),))

    # Phase 4: Parse numeric amount
    amount, amount_error = _parse_currency_amount(
        value,
        match,
        locale,
        locale_code,
        parse_decimal,
        number_format_error_class,
    )
    if amount_error is not None or amount is None:
        if amount_error is not None:
            return (None, (amount_error,))
        # Defensive: _parse_currency_amount contract guarantees
        # exactly one of (amount, error) is non-None.
        diagnostic = ErrorTemplate.parse_currency_failed(  # pragma: no cover
            value, locale_code, "Amount parsing failed",
        )
        context = FrozenErrorContext(  # pragma: no cover
            input_value=str(value),
            locale_code=locale_code,
            parse_type="currency",
        )
        return (None, (FrozenFluentError(  # pragma: no cover
            str(diagnostic),
            ErrorCategory.PARSE,
            diagnostic=diagnostic,
            context=context,
        ),))

    return ((amount, currency_code), ())


def clear_currency_caches() -> None:
    """Clear all currency-related caches.

    Clears cached CLDR currency data from:
    - _build_currency_maps_from_cldr() - symbol-to-currency maps from CLDR scan
    - _get_currency_maps() - merged fast tier + full CLDR maps
    - _get_currency_pattern() - currency detection regex pattern

    Useful for:
    - Memory reclamation in long-running applications
    - Testing scenarios requiring fresh cache state
    - After Babel/CLDR data updates

    Thread-safe via functools.cache internal locking.

    Note:
        This function does NOT require Babel. It clears the caches
        regardless of whether Babel is installed. The fast tier data
        (hardcoded common currencies) remains available immediately after
        clearing; only the full CLDR scan results are invalidated.

    Example:
        >>> from ftllexengine.parsing.currency import clear_currency_caches  # doctest: +SKIP
        >>> clear_currency_caches()  # Clears all cached currency data  # doctest: +SKIP
    """
    _clear_currency_maps_caches()
    _get_currency_pattern.cache_clear()
