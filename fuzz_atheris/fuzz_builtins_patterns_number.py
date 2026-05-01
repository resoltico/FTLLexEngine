from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from math import isinf, isnan
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import atheris
from fuzz_builtins_support import (
    _EDGE_FLOATS,
    _PRECISION_NUMBERS,
    BuiltinsFuzzError,
    _domain,
    _extract_oracle_digits,
    _make_decimal,
    _pick_locale,
)

from ftllexengine.core.value_types import FluentNumber
from ftllexengine.runtime.functions import number_format


def _pattern_number_basic(fdp: atheris.FuzzedDataProvider) -> None:
    """NUMBER with varied fraction digits, grouping, and locales."""
    locale = _pick_locale(fdp)
    val = _make_decimal(fdp)
    min_frac = fdp.ConsumeIntInRange(0, 10)
    max_frac = fdp.ConsumeIntInRange(0, 20)  # Independent: allows min > max (clamp path)
    grouping = fdp.ConsumeBool()

    _domain.number_calls += 1
    result = number_format(
        val, locale,
        minimum_fraction_digits=min_frac,
        maximum_fraction_digits=max_frac,
        use_grouping=grouping,
    )

    # Invariant: result must be FluentNumber
    if not isinstance(result, FluentNumber):
        msg = f"number_format returned {type(result).__name__}, expected FluentNumber"
        raise BuiltinsFuzzError(msg)

def _pattern_number_precision(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify FluentNumber precision (CLDR v operand) correctness.

    The v operand is the count of visible fraction digits in the formatted
    output. This is critical for plural rule matching.
    """
    locale = _pick_locale(fdp)
    # Use precision-sensitive numbers
    val = (
        fdp.PickValueInList(list(_PRECISION_NUMBERS))
        if fdp.ConsumeBool()
        else _make_decimal(fdp)
    )

    min_frac = fdp.ConsumeIntInRange(0, 6)
    max_frac = fdp.ConsumeIntInRange(0, 10)  # Independent: allows min > max (clamp path)
    if min_frac > max_frac:
        _domain.min_gt_max_tests += 1

    _domain.number_calls += 1
    _domain.precision_checks += 1
    result = number_format(
        val, locale,
        minimum_fraction_digits=min_frac,
        maximum_fraction_digits=max_frac,
        use_grouping=False,
    )

    # Invariant: precision must be non-negative integer
    if not isinstance(result, FluentNumber):
        return
    if result.precision is not None and result.precision < 0:
        _domain.precision_violations += 1
        msg = (
            f"Negative precision {result.precision} for val={val}, "
            f"locale={locale}, min={min_frac}, max={max_frac}"
        )
        raise BuiltinsFuzzError(msg)

    # Rounding oracle: verify ROUND_HALF_EVEN across all ASCII-digit locales.
    # Babel uses decimal_quantization=True by default, which applies ROUND_HALF_EVEN
    # (IEEE 754 banker's rounding). _extract_oracle_digits handles locale-specific
    # decimal and group separators; returns None for non-ASCII-digit locales (ar-EG).
    # NaN guard is explicit: Decimal.quantize() does NOT raise InvalidOperation for
    # quiet NaN -- it silently propagates and returns Decimal('NaN'). Only Infinity
    # raises InvalidOperation. Without the is_nan() check, the oracle compares
    # 'NaN' against whatever Babel emits for NaN input, producing a false violation.
    val_d = result.value
    if isinstance(val_d, Decimal) and result.precision is not None and not val_d.is_nan():
        prec = result.precision
        try:
            expected = abs(val_d).quantize(Decimal(10) ** -prec, rounding=ROUND_HALF_EVEN)
        except InvalidOperation:
            pass  # Infinity: skip oracle
        else:
            digits_only = _extract_oracle_digits(result.formatted, locale)
            if digits_only is not None:
                _domain.rounding_oracle_checks += 1
                if digits_only != str(expected):
                    _domain.rounding_oracle_violations += 1
                    msg = (
                        f"Rounding oracle: got {digits_only!r}, expected {str(expected)!r} "
                        f"for val={val_d}, locale={locale}, min={min_frac}, max={max_frac}"
                    )
                    raise BuiltinsFuzzError(msg)

def _pattern_number_edges(fdp: atheris.FuzzedDataProvider) -> None:
    """Edge float values: NaN, Inf, -0.0, huge, tiny."""
    locale = _pick_locale(fdp)
    val_float = fdp.PickValueInList(list(_EDGE_FLOATS))

    # Track edge value types
    if isnan(val_float):
        _domain.edge_nan_count += 1
    elif isinf(val_float):
        _domain.edge_inf_count += 1
    elif val_float == 0.0:
        _domain.edge_zero_count += 1

    # Decimal(str(float)) never raises for NaN/Inf:
    # float('nan') -> 'nan' -> Decimal('NaN'), float('inf') -> Decimal('Infinity').
    val = Decimal(str(val_float))

    _domain.number_calls += 1
    number_format(
        val, locale,
        minimum_fraction_digits=fdp.ConsumeIntInRange(0, 5),
        maximum_fraction_digits=fdp.ConsumeIntInRange(0, 10),
        use_grouping=fdp.ConsumeBool(),
    )

def _pattern_number_type_variety(fdp: atheris.FuzzedDataProvider) -> None:
    """Test NUMBER with int, float, Decimal, and FluentNumber inputs.

    Verifies type coercion works correctly across all numeric types
    that could be passed as FTL variable values.
    """
    locale = _pick_locale(fdp)
    _domain.type_coercion_tests += 1
    _domain.number_calls += 1

    input_type = fdp.ConsumeIntInRange(0, 3)
    match input_type:
        case 0:
            # int input
            val = Decimal(fdp.ConsumeIntInRange(-999999, 999999))
        case 1:
            # float input (via Decimal conversion)
            val = _make_decimal(fdp)
        case 2:
            # Precision-sensitive Decimal
            val = fdp.PickValueInList(list(_PRECISION_NUMBERS))
        case _:
            # FluentNumber as input (result of previous NUMBER call)
            inner = number_format(
                Decimal(str(fdp.ConsumeIntInRange(1, 100))), locale,
                minimum_fraction_digits=2,
            )
            # Format the FluentNumber again (nested call)
            val = Decimal(str(inner.value)) if isinstance(inner, FluentNumber) else Decimal(0)

    result = number_format(
        val, locale,
        minimum_fraction_digits=fdp.ConsumeIntInRange(0, 6),
        maximum_fraction_digits=fdp.ConsumeIntInRange(0, 10),
    )

    if not isinstance(result, FluentNumber):
        msg = f"number_format returned {type(result).__name__} for {type(val).__name__} input"
        raise BuiltinsFuzzError(msg)
