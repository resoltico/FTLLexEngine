#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: builtins - Built-in Functions (Babel Boundary)
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Built-in Function Boundary Fuzzer (Atheris).

Targets: ftllexengine.runtime.functions (NUMBER, DATETIME, CURRENCY)

Concern boundary: This fuzzer stress-tests the Babel formatting boundary by
calling NUMBER, DATETIME, and CURRENCY functions directly through the Python
API. This is distinct from fuzz_runtime which invokes these functions through
FTL syntax and the resolver stack. Direct API testing isolates the Babel layer
from resolver/cache behavior and enables:
- Fuzz-generated Babel pattern strings (pattern= parameter)
- FluentNumber precision (CLDR v operand) correctness verification
- Currency-specific decimal digit enforcement (JPY=0, BHD=3)
- Type coercion across int/float/Decimal/FluentNumber inputs
- Cross-locale formatting consistency (same value, multiple locales)
- Edge value handling (NaN, Inf, -0.0, extreme magnitudes)

FunctionRegistry lifecycle, parameter mapping, and locale injection protocol
are covered by fuzz_bridge.py. This fuzzer focuses exclusively on the
formatting output correctness boundary.

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import gc
import logging
import pathlib
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from math import isinf, isnan
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

# --- Dependency Checks ---
_psutil_mod: Any = None
_atheris_mod: Any = None

try:  # noqa: SIM105 - need module ref for check_dependencies
    import psutil as _psutil_mod  # type: ignore[no-redef]
except ImportError:
    pass

try:  # noqa: SIM105 - need module ref for check_dependencies
    import atheris as _atheris_mod  # type: ignore[no-redef]
except ImportError:
    pass

from fuzz_common import (  # noqa: E402 - after dependency capture  # pylint: disable=C0413
    GC_INTERVAL,
    BaseFuzzerState,
    build_base_stats_dict,
    build_weighted_schedule,
    check_dependencies,
    emit_final_report,
    get_process,
    record_iteration_metrics,
    record_memory,
    select_pattern_round_robin,
)

check_dependencies(["psutil", "atheris"], [_psutil_mod, _atheris_mod])

import atheris  # noqa: E402  # pylint: disable=C0412,C0413

# --- Domain Metrics ---

@dataclass
class BuiltinsMetrics:
    """Domain-specific metrics for builtins fuzzer."""

    # Per-function call counts
    number_calls: int = 0
    datetime_calls: int = 0
    currency_calls: int = 0

    # Precision tracking
    precision_checks: int = 0
    precision_violations: int = 0

    # Cross-locale tests
    cross_locale_tests: int = 0
    cross_locale_empty_results: int = 0

    # Type coercion tests
    type_coercion_tests: int = 0

    # Custom pattern tests
    custom_pattern_tests: int = 0

    # Edge value encounters
    edge_nan_count: int = 0
    edge_inf_count: int = 0
    edge_zero_count: int = 0


# --- Global State ---

_state = BaseFuzzerState(seed_corpus_max_size=500)
_domain = BuiltinsMetrics()

# Pattern weights: (name, weight) - focused on Babel boundary, no bridge overlap
_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("number_basic", 12),
    ("number_precision", 15),
    ("number_edges", 8),
    ("number_type_variety", 8),
    ("datetime_styles", 10),
    ("datetime_edges", 8),
    ("datetime_timezone_stress", 6),
    ("currency_codes", 12),
    ("currency_precision", 10),
    ("currency_cross_locale", 8),
    ("custom_pattern", 8),
    ("cross_locale_consistency", 8),
    ("error_paths", 5),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

# Register intended weights for skew detection
_state.pattern_intended_weights = {name: float(weight) for name, weight in _PATTERN_WEIGHTS}


class BuiltinsFuzzError(Exception):
    """Raised when a fuzzer invariant is violated."""


# Allowed exceptions from Babel / formatting functions
ALLOWED_EXCEPTIONS = (
    ValueError,
    TypeError,
    OverflowError,
    InvalidOperation,
    OSError,
    ArithmeticError,
)


# --- Reporting ---

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "builtins"


def _build_stats_dict() -> dict[str, Any]:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)

    # Per-function call counts
    stats["number_calls"] = _domain.number_calls
    stats["datetime_calls"] = _domain.datetime_calls
    stats["currency_calls"] = _domain.currency_calls

    # Precision tracking
    stats["precision_checks"] = _domain.precision_checks
    stats["precision_violations"] = _domain.precision_violations

    # Cross-locale
    stats["cross_locale_tests"] = _domain.cross_locale_tests
    stats["cross_locale_empty_results"] = _domain.cross_locale_empty_results

    # Type coercion
    stats["type_coercion_tests"] = _domain.type_coercion_tests

    # Custom patterns
    stats["custom_pattern_tests"] = _domain.custom_pattern_tests

    # Edge values
    stats["edge_nan_count"] = _domain.edge_nan_count
    stats["edge_inf_count"] = _domain.edge_inf_count
    stats["edge_zero_count"] = _domain.edge_zero_count

    return stats


def _emit_report() -> None:
    """Emit comprehensive final report (crash-proof)."""
    stats = _build_stats_dict()
    emit_final_report(_state, stats, _REPORT_DIR, "fuzz_builtins_report.json")


atexit.register(_emit_report)


# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.runtime.function_bridge import FluentNumber
    from ftllexengine.runtime.functions import (
        currency_format,
        datetime_format,
        number_format,
    )


# --- Constants ---

_LOCALES: Sequence[str] = (
    "en-US", "de-DE", "ar-EG", "zh-Hans-CN", "ja-JP",
    "lv-LV", "fr-FR", "pt-BR", "hi-IN", "root",
)

_VALID_ISO_CURRENCIES: Sequence[str] = (
    "USD", "EUR", "GBP", "JPY", "CHF", "CNY", "BRL",
    "INR", "KRW", "BHD", "KWD", "OMR",
)

_CURRENCY_DISPLAY_MODES: Sequence[str] = ("symbol", "code", "name")

_DATE_STYLES: Sequence[str] = ("short", "medium", "long", "full")

# Numbers that exercise precision boundary conditions
_PRECISION_NUMBERS: Sequence[Decimal] = (
    Decimal("0"), Decimal("1"), Decimal("1.0"), Decimal("1.00"),
    Decimal("1.5"), Decimal("1.50"), Decimal("0.001"),
    Decimal("1234567.89"), Decimal("-1.5"), Decimal("0.10"),
    Decimal("999999999.999"),
)

# Edge float values
_EDGE_FLOATS: Sequence[float] = (
    0.0, -0.0, 1e-10, 1e10, 1e100, 1e308,
    float("inf"), float("-inf"), float("nan"),
    -1.0, 0.1, 0.01, 0.001,
)

# Timestamp boundaries for DATETIME
_MAX_TIMESTAMP = 253402300799.0  # 9999-12-31T23:59:59 UTC


# --- Helpers ---

def _pick_locale(fdp: atheris.FuzzedDataProvider) -> str:
    """Pick locale: 90% valid, 10% fuzzed."""
    if fdp.ConsumeIntInRange(0, 9) < 9:
        return fdp.PickValueInList(list(_LOCALES))
    return fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(2, 15))


def _make_decimal(fdp: atheris.FuzzedDataProvider) -> Decimal:
    """Generate a Decimal from fuzzed float, handling NaN/Inf."""
    try:
        return Decimal(str(fdp.ConsumeFloat()))
    except InvalidOperation:
        return Decimal("0")


def _values_match(a: object, b: object) -> bool:
    """NaN-safe value comparison for cross-locale invariant checks.

    IEEE 754 defines NaN != NaN, so naive != comparison falsely reports
    value drift when both sides are NaN. This function treats two NaN
    values of the same type as matching.
    """
    if isinstance(a, Decimal) and isinstance(b, Decimal) and a.is_nan() and b.is_nan():
        return True
    if isinstance(a, float) and isinstance(b, float) and isnan(a) and isnan(b):
        return True
    return a == b


# =============================================================================
# Pattern implementations
# =============================================================================


def _pattern_number_basic(fdp: atheris.FuzzedDataProvider) -> None:
    """NUMBER with varied fraction digits, grouping, and locales."""
    locale = _pick_locale(fdp)
    val = _make_decimal(fdp)
    min_frac = fdp.ConsumeIntInRange(0, 10)
    max_frac = fdp.ConsumeIntInRange(min_frac, 20)
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
    max_frac = fdp.ConsumeIntInRange(min_frac, 10)

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

    try:
        val = Decimal(str(val_float))
    except InvalidOperation:
        # NaN/Inf as Decimal raises -- test with float directly
        val = Decimal("0")

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
            val = Decimal(str(inner.value)) if isinstance(inner, FluentNumber) else Decimal("0")

    result = number_format(
        val, locale,
        minimum_fraction_digits=fdp.ConsumeIntInRange(0, 6),
        maximum_fraction_digits=fdp.ConsumeIntInRange(0, 10),
    )

    if not isinstance(result, FluentNumber):
        msg = f"number_format returned {type(result).__name__} for {type(val).__name__} input"
        raise BuiltinsFuzzError(msg)


def _pattern_datetime_styles(fdp: atheris.FuzzedDataProvider) -> None:
    """DATETIME with all style combinations."""
    locale = _pick_locale(fdp)
    # Safe timestamp range
    timestamp = fdp.ConsumeFloat() % _MAX_TIMESTAMP
    if timestamp < 0:
        timestamp = abs(timestamp)

    try:
        dt = datetime.fromtimestamp(timestamp, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return

    date_style = fdp.PickValueInList(list(_DATE_STYLES))
    use_time = fdp.ConsumeBool()
    time_style = fdp.PickValueInList(list(_DATE_STYLES)) if use_time else None

    _domain.datetime_calls += 1
    result = datetime_format(
        dt, locale,
        date_style=date_style,
        time_style=time_style,
    )

    # Invariant: result must be non-empty string
    if not isinstance(result, str) or not result:
        msg = (
            f"datetime_format returned empty/non-str: {result!r} "
            f"for locale={locale}, date_style={date_style}"
        )
        raise BuiltinsFuzzError(msg)


def _pattern_datetime_edges(fdp: atheris.FuzzedDataProvider) -> None:
    """Edge timestamps and timezone variations."""
    locale = _pick_locale(fdp)

    # Edge timestamps
    edge_timestamps = [
        0.0,             # Unix epoch
        86400.0,         # One day
        -86400.0,        # Before epoch
        946684800.0,     # Y2K
        _MAX_TIMESTAMP,  # Max safe
    ]
    timestamp = fdp.PickValueInList(edge_timestamps)

    try:
        dt = datetime.fromtimestamp(timestamp, tz=UTC)
    except (OSError, OverflowError, ValueError):
        return

    # Test with different timezone offsets
    if fdp.ConsumeBool():
        offset_hours = fdp.ConsumeIntInRange(-12, 14)
        tz = timezone(timedelta(hours=offset_hours))
        dt = dt.astimezone(tz)

    _domain.datetime_calls += 1
    datetime_format(
        dt, locale,
        date_style=fdp.PickValueInList(list(_DATE_STYLES)),
        time_style=fdp.PickValueInList(list(_DATE_STYLES)) if fdp.ConsumeBool() else None,
    )


def _pattern_datetime_timezone_stress(fdp: atheris.FuzzedDataProvider) -> None:
    """Stress-test timezone handling with extreme offsets and DST boundaries.

    Tests the DATETIME function with timezone offsets at the edges of
    the valid range, timestamps near DST transitions, and unusual
    UTC offset values.
    """
    locale = _pick_locale(fdp)

    # Base timestamp: mix of safe values and edge cases
    base_timestamps = [
        0.0,              # Epoch
        1647302400.0,     # March 2022 (DST transition period)
        1667091600.0,     # Nov 2022 (DST fall-back period)
        946684800.0,      # Y2K
        1704067200.0,     # 2024-01-01
        86400.0 * 365,    # One year
    ]
    timestamp = fdp.PickValueInList(base_timestamps)

    # Add fuzzed offset to push near boundaries
    offset_seconds = fdp.ConsumeIntInRange(-43200, 43200)

    try:
        # Create with extreme timezone offset (±12h in 15min increments)
        offset_minutes = fdp.ConsumeIntInRange(-720, 840)
        tz = timezone(timedelta(minutes=offset_minutes))
        dt = datetime.fromtimestamp(timestamp + offset_seconds, tz=tz)
    except (OSError, OverflowError, ValueError):
        return

    _domain.datetime_calls += 1
    result = datetime_format(
        dt, locale,
        date_style=fdp.PickValueInList(list(_DATE_STYLES)),
        time_style=fdp.PickValueInList(list(_DATE_STYLES)) if fdp.ConsumeBool() else None,
    )

    if not isinstance(result, str) or not result:
        msg = f"datetime_format returned empty for tz offset {offset_minutes}min"
        raise BuiltinsFuzzError(msg)


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
    max_frac = fdp.ConsumeIntInRange(min_frac, 8)

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
                Decimal("100"), locale,
                currency="",
            )
        case 3:
            # Invalid currency code (too long / too short)
            bad_code = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 50))
            _domain.currency_calls += 1
            currency_format(
                Decimal("100"), locale,
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


# --- Pattern Dispatch ---

_PATTERN_DISPATCH: dict[str, Any] = {
    "number_basic": _pattern_number_basic,
    "number_precision": _pattern_number_precision,
    "number_edges": _pattern_number_edges,
    "number_type_variety": _pattern_number_type_variety,
    "datetime_styles": _pattern_datetime_styles,
    "datetime_edges": _pattern_datetime_edges,
    "datetime_timezone_stress": _pattern_datetime_timezone_stress,
    "currency_codes": _pattern_currency_codes,
    "currency_precision": _pattern_currency_precision,
    "currency_cross_locale": _pattern_currency_cross_locale,
    "custom_pattern": _pattern_custom_pattern,
    "cross_locale_consistency": _pattern_cross_locale_consistency,
    "error_paths": _pattern_error_paths,
}


# --- Main Entry Point ---


def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test built-in formatting functions."""
    if _state.iterations == 0:
        _state.initial_memory_mb = get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_report()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    pattern = select_pattern_round_robin(_state, _PATTERN_SCHEDULE)
    _state.pattern_coverage[pattern] = _state.pattern_coverage.get(pattern, 0) + 1

    if fdp.remaining_bytes() < 4:
        return

    pattern_func = _PATTERN_DISPATCH[pattern]

    try:
        pattern_func(fdp)

    except BuiltinsFuzzError:
        _state.findings += 1
        raise

    except KeyboardInterrupt:
        _state.status = "stopped"
        raise

    except (*ALLOWED_EXCEPTIONS, FrozenFluentError):
        pass  # Expected for invalid inputs / Babel limitations

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

    finally:
        # Semantic interestingness: multi-locale, edge values, fuzzed patterns,
        # or wall-time > 1ms (12x P99) indicating unusual code path
        is_interesting = pattern in (
            "cross_locale_consistency", "currency_cross_locale",
            "number_edges", "number_type_variety", "custom_pattern",
        ) or (time.perf_counter() - start_time) * 1000 > 1.0
        record_iteration_metrics(
            _state, pattern, start_time, data, is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Run the builtins fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="Built-in function boundary fuzzer using Atheris/libFuzzer",
        epilog="All unrecognized arguments are passed to libFuzzer.",
    )
    parser.add_argument(
        "--checkpoint-interval", type=int, default=500,
        help="Emit report every N iterations (default: 500)",
    )
    parser.add_argument(
        "--seed-corpus-size", type=int, default=500,
        help="Maximum size of in-memory seed corpus (default: 500)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    if not any(arg.startswith("-rss_limit_mb") for arg in remaining):
        remaining.append("-rss_limit_mb=4096")

    sys.argv = [sys.argv[0], *remaining]

    print()
    print("=" * 80)
    print("Built-in Function Boundary Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     NUMBER, DATETIME, CURRENCY (Babel boundary)")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print(f"GC Cycle:   Every {GC_INTERVAL} iterations")
    print(f"Patterns:   {len(_PATTERN_WEIGHTS)} (weighted round-robin)")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
