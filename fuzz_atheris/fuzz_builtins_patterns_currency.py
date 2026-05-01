from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import atheris
from fuzz_builtins_support import (
    _CURRENCY_DISPLAY_MODES,
    _LOCALES,
    _MAX_TIMESTAMP,
    _PRECISION_NUMBERS,
    _VALID_ISO_CURRENCIES,
    BuiltinsFuzzError,
    _domain,
    _extract_oracle_digits,
    _make_decimal,
    _pick_locale,
    _values_match,
)

from ftllexengine.core.value_types import FluentNumber
from ftllexengine.runtime.functions import (
    currency_format,
    datetime_format,
    number_format,
)


def _pattern_currency_codes(fdp: atheris.FuzzedDataProvider) -> None:
    """CURRENCY with valid/invalid ISO codes and display modes."""
    locale = _pick_locale(fdp)
    val = _make_decimal(fdp)

    # 80% valid ISO code, 20% fuzzed
    if fdp.ConsumeIntInRange(0, 4) < 4:
        currency = fdp.PickValueInList(list(_VALID_ISO_CURRENCIES))
    else:
        currency = fdp.ConsumeUnicodeNoSurrogates(3).upper()

    display = fdp.PickValueInList(list(_CURRENCY_DISPLAY_MODES))

    _domain.currency_calls += 1
    result = currency_format(
        val, locale,
        currency=currency,
        currency_display=display,
    )

    # Invariant: result must be FluentNumber
    if not isinstance(result, FluentNumber):
        msg = f"currency_format returned {type(result).__name__}"
        raise BuiltinsFuzzError(msg)

def _pattern_currency_precision(fdp: atheris.FuzzedDataProvider) -> None:
    """Currency-specific decimal digits: JPY=0, BHD=3, EUR/USD=2."""
    locale = _pick_locale(fdp)

    # Currencies with known decimal digits
    currency_decimals = {
        "JPY": 0, "KRW": 0,       # 0 decimals
        "USD": 2, "EUR": 2,       # 2 decimals
        "BHD": 3, "KWD": 3,       # 3 decimals
    }

    currency = fdp.PickValueInList(list(currency_decimals.keys()))
    val = fdp.PickValueInList(list(_PRECISION_NUMBERS))

    _domain.currency_calls += 1
    _domain.precision_checks += 1
    result = currency_format(
        val, locale,
        currency=currency,
        currency_display="code",
    )

    # Invariant: precision must be non-negative
    if isinstance(result, FluentNumber) and result.precision is not None and result.precision < 0:
        _domain.precision_violations += 1
        msg = (
            f"Negative precision {result.precision} for "
            f"currency={currency}, val={val}"
        )
        raise BuiltinsFuzzError(msg)

    # Rounding oracle: verify ROUND_HALF_EVEN for known currency decimal counts.
    # Babel's decimal_quantization=True applies ROUND_HALF_EVEN by default.
    # _extract_oracle_digits handles locale-specific separators and skips
    # non-ASCII-digit locales. NaN guard is explicit: Decimal.quantize() silently
    # propagates quiet NaN (returns Decimal('NaN')) instead of raising
    # InvalidOperation. Only Infinity raises. Without is_nan(), the oracle fires
    # a false violation when Babel formats NaN differently from str(Decimal('NaN')).
    if isinstance(result, FluentNumber) and result.precision is not None:
        val_d = result.value
        if isinstance(val_d, Decimal) and not val_d.is_nan():
            expected_prec = currency_decimals[currency]
            quantizer = Decimal(10) ** -expected_prec
            try:
                expected = abs(val_d).quantize(quantizer, rounding=ROUND_HALF_EVEN)
            except InvalidOperation:
                pass  # Infinity: skip oracle
            else:
                digits_only = _extract_oracle_digits(result.formatted, locale)
                if digits_only is not None:
                    _domain.rounding_oracle_checks += 1
                    if digits_only != str(expected):
                        _domain.rounding_oracle_violations += 1
                        msg = (
                            f"Currency rounding oracle: got {digits_only!r}, "
                            f"expected {str(expected)!r} "
                            f"for currency={currency}, val={val_d}, locale={locale}"
                        )
                        raise BuiltinsFuzzError(msg)

def _pattern_currency_cross_locale(fdp: atheris.FuzzedDataProvider) -> None:
    """Same currency amount formatted across multiple locales.

    Verifies that the same value + currency code produces valid output
    in every locale, and that the FluentNumber.value is preserved.
    """
    val = fdp.PickValueInList(list(_PRECISION_NUMBERS))
    currency = fdp.PickValueInList(list(_VALID_ISO_CURRENCIES))
    display = fdp.PickValueInList(list(_CURRENCY_DISPLAY_MODES))

    results: list[FluentNumber] = []
    num_locales = fdp.ConsumeIntInRange(3, 6)
    locales_to_test = [
        fdp.PickValueInList(list(_LOCALES)) for _ in range(num_locales)
    ]

    _domain.cross_locale_tests += 1
    for locale in locales_to_test:
        _domain.currency_calls += 1
        result = currency_format(
            val, locale,
            currency=currency,
            currency_display=display,
        )
        if isinstance(result, FluentNumber):
            results.append(result)

    # Invariant: all results should have the same underlying numeric value
    if len(results) >= 2:
        first_val = results[0].value
        for r in results[1:]:
            if not _values_match(r.value, first_val):
                msg = (
                    f"Currency value drift: {first_val} vs {r.value} "
                    f"for {currency} across locales"
                )
                raise BuiltinsFuzzError(msg)

def _pattern_custom_pattern(fdp: atheris.FuzzedDataProvider) -> None:
    """Custom Babel patterns for NUMBER, DATETIME, CURRENCY."""
    locale = _pick_locale(fdp)
    target = fdp.ConsumeIntInRange(0, 2)
    _domain.custom_pattern_tests += 1

    # Mix of valid and fuzzed patterns
    number_patterns = [
        "#,##0.00", "#,##0", "0.###", "#,##0.00;(#,##0.00)",
        "0.0", "#", "##0.00%",
    ]
    date_patterns = [
        "yyyy-MM-dd", "dd/MM/yyyy", "MMMM d, yyyy",
        "HH:mm:ss", "EEE, d MMM yyyy",
    ]

    match target:
        case 0:  # NUMBER with pattern
            if fdp.ConsumeBool():
                pattern = fdp.PickValueInList(number_patterns)
            else:
                pattern = fdp.ConsumeUnicodeNoSurrogates(20)
            _domain.number_calls += 1
            number_format(
                _make_decimal(fdp), locale,
                pattern=pattern,
            )
        case 1:  # DATETIME with pattern
            timestamp = abs(fdp.ConsumeFloat()) % _MAX_TIMESTAMP
            try:
                dt = datetime.fromtimestamp(timestamp, tz=UTC)
            except (OSError, OverflowError, ValueError):
                return
            if fdp.ConsumeBool():
                pattern = fdp.PickValueInList(date_patterns)
            else:
                pattern = fdp.ConsumeUnicodeNoSurrogates(20)
            _domain.datetime_calls += 1
            datetime_format(dt, locale, pattern=pattern)
        case _:  # CURRENCY with pattern
            if fdp.ConsumeBool():
                pattern = fdp.PickValueInList(number_patterns)
            else:
                pattern = fdp.ConsumeUnicodeNoSurrogates(20)
            _domain.currency_calls += 1
            currency_format(
                _make_decimal(fdp), locale,
                currency=fdp.PickValueInList(list(_VALID_ISO_CURRENCIES)),
                pattern=pattern,
            )

def _pattern_cross_locale_consistency(fdp: atheris.FuzzedDataProvider) -> None:
    """Same numeric value formatted across multiple locales.

    Verifies all locales produce a non-empty result and that the
    underlying FluentNumber.value is preserved across locales.
    """
    val = _make_decimal(fdp)
    min_frac = fdp.ConsumeIntInRange(0, 4)
    max_frac = fdp.ConsumeIntInRange(0, 8)  # Independent: allows min > max (clamp path)

    _domain.cross_locale_tests += 1
    num_locales = fdp.ConsumeIntInRange(3, 8)
    locales_to_test = [
        fdp.PickValueInList(list(_LOCALES)) for _ in range(num_locales)
    ]

    results: list[FluentNumber] = []
    for locale in locales_to_test:
        _domain.number_calls += 1
        result = number_format(
            val, locale,
            minimum_fraction_digits=min_frac,
            maximum_fraction_digits=max_frac,
        )
        if isinstance(result, FluentNumber):
            results.append(result)
            if not str(result):
                _domain.cross_locale_empty_results += 1

    # Invariant: all results should preserve the same underlying value
    if len(results) >= 2:
        first_val = results[0].value
        for r in results[1:]:
            if not _values_match(r.value, first_val):
                msg = (
                    f"Value drift across locales: {first_val} vs {r.value} "
                    f"for input {val}"
                )
                raise BuiltinsFuzzError(msg)

def _pattern_error_paths(fdp: atheris.FuzzedDataProvider) -> None:
    """Invalid inputs, type mismatches, boundary violations."""
    locale = _pick_locale(fdp)
    error_case = fdp.ConsumeIntInRange(0, 4)

    match error_case:
        case 0:
            # Invalid fraction digits (negative)
            _domain.number_calls += 1
            number_format(
                Decimal("1.5"), locale,
                minimum_fraction_digits=-1,
                maximum_fraction_digits=fdp.ConsumeIntInRange(-5, 5),
            )
        case 1:
            # Very large fraction digits
            _domain.number_calls += 1
            number_format(
                Decimal("1.5"), locale,
                minimum_fraction_digits=fdp.ConsumeIntInRange(50, 200),
                maximum_fraction_digits=fdp.ConsumeIntInRange(50, 200),
            )
        case 2:
            # Empty currency code
            _domain.currency_calls += 1
            currency_format(
                Decimal(100), locale,
                currency="",
            )
        case 3:
            # Invalid currency code (too long / too short)
            bad_code = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 50))
            _domain.currency_calls += 1
            currency_format(
                Decimal(100), locale,
                currency=bad_code,
            )
        case _:
            # Fuzzed date style strings
            timestamp = abs(fdp.ConsumeFloat()) % _MAX_TIMESTAMP
            try:
                dt = datetime.fromtimestamp(timestamp, tz=UTC)
            except (OSError, OverflowError, ValueError):
                return
            _domain.datetime_calls += 1
            datetime_format(
                dt, locale,
                date_style=fdp.ConsumeUnicodeNoSurrogates(10),
                time_style=fdp.ConsumeUnicodeNoSurrogates(10) if fdp.ConsumeBool() else None,
            )
