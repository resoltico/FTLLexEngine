#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: numbers - NUMBER Function Runtime Formatting (Oracle)
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""NUMBER Function Runtime Formatting Oracle Fuzzer (Atheris).

Targets: ftllexengine.runtime.functions.number_format

Concern boundary: This fuzzer provides deep oracle-based testing of the NUMBER
function's runtime formatting path. It is complementary to fuzz_builtins (which
covers the full Babel boundary including DATETIME and CURRENCY) and
fuzz_locale_context (which covers LocaleContext direct API with ROUND_HALF_UP
oracle). This fuzzer specializes on NUMBER-specific coverage gaps:

- ROUND_HALF_UP oracle with use_grouping=True: fuzz_builtins._pattern_number_precision
  uses use_grouping=False for the oracle path. This file specifically tests the
  grouping=True path where group separators interact with oracle digit extraction.
- Rounding boundary values (x.y5 at precisions 0-3): targeted corpus that
  exposes ROUND_HALF_EVEN vs ROUND_HALF_UP differences without relying on
  coverage-guided discovery.
- Custom pattern= path oracle: format_number(pattern=...) pre-quantizes via
  parse_pattern() (v0.145.0 fix). This specific code path lacked oracle
  coverage in fuzz_builtins.
- Large integers (>1e9): grouping separators interact non-trivially with
  oracle digit extraction (de-DE uses '.' as group sep, lv-LV uses whitespace).
- Determinism: FluentNumber.formatted and .precision must be identical across
  repeated calls with identical parameters.
- Value preservation: FluentNumber.formatted must be non-empty; precision
  must be non-negative.
- min>max clamping: minimum_fraction_digits > maximum_fraction_digits silently
  clamps (matches JS Intl.NumberFormat behavior); no crash and non-empty output.

Patterns (8):
- number_grouping_oracle: ROUND_HALF_UP with use_grouping=True (weight 16)
- number_boundary_values: x.y5 at precisions 0-3 (weight 15)
- number_pattern_oracle: custom pattern= path with ROUND_HALF_UP oracle (weight 13)
- number_negative_oracle: negative value ROUND_HALF_UP verification (weight 12)
- number_large_integers: values > 1e9 with grouping separator stress (weight 11)
- number_determinism: same params -> identical FluentNumber invariant (weight 11)
- number_value_preservation: FluentNumber.formatted non-empty, precision >= 0 (weight 11)
- number_min_gt_max: minimum > maximum fraction digits clamping (weight 11)

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import gc
import logging
import pathlib
import re
import sys
import time
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, cast

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
    FuzzStats,
    build_base_stats_dict,
    build_weighted_schedule,
    check_dependencies,
    emit_checkpoint_report,
    emit_final_report,
    get_process,
    print_fuzzer_banner,
    record_iteration_metrics,
    record_memory,
    run_fuzzer,
    select_pattern_round_robin,
)

check_dependencies(["psutil", "atheris"], [_psutil_mod, _atheris_mod])

import atheris  # noqa: E402  # pylint: disable=C0412,C0413

# --- Domain Metrics ---


@dataclass
class NumbersMetrics:
    """Domain-specific metrics for number_format oracle fuzzer."""

    number_calls: int = 0
    oracle_checks: int = 0
    oracle_violations: int = 0
    min_gt_max_tests: int = 0
    boundary_hits: int = 0
    large_value_tests: int = 0
    determinism_checks: int = 0
    preservation_checks: int = 0


class NumbersFuzzError(Exception):
    """Raised when a NUMBER function formatting invariant is violated."""


# --- Constants ---

_ALLOWED_EXCEPTIONS = (
    ValueError,
    TypeError,
    OverflowError,
    ArithmeticError,
    InvalidOperation,
)

_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("number_grouping_oracle", 16),
    ("number_boundary_values", 15),
    ("number_pattern_oracle", 13),
    ("number_negative_oracle", 12),
    ("number_large_integers", 11),
    ("number_determinism", 11),
    ("number_value_preservation", 11),
    ("number_min_gt_max", 11),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

# Validated locales (ASCII-digit only): ar-EG and hi-IN use non-ASCII digits
# and are excluded here to avoid false oracle rejections. They are covered by
# fuzz_locale_context which uses Babel's own normalization.
_VALID_LOCALES: tuple[str, ...] = (
    "en-US", "en-GB", "de-DE", "fr-FR", "es-ES",
    "ja-JP", "zh-CN", "ko-KR",
    "sv-SE", "nb-NO", "fi-FI",
    "ru-RU", "pl-PL",
    "pt-BR", "nl-NL",
)

# Rounding boundary values organized as (precision, value_string) pairs.
# Each value falls exactly at the midpoint where ROUND_HALF_EVEN and
# ROUND_HALF_UP diverge: x.5 for precision=0, x.05 for precision=1, etc.
# Even-digit midpoints (0.5, 2.5, 4.5) round DOWN with ROUND_HALF_EVEN but
# UP with ROUND_HALF_UP; odd-digit midpoints (1.5, 3.5) both round UP.
_BOUNDARY_VALUES: tuple[tuple[int, str], ...] = (
    # Precision 0: x.5 boundaries (even halves diverge between rounding modes)
    (0, "0.5"), (0, "1.5"), (0, "2.5"), (0, "4.5"), (0, "6.5"), (0, "8.5"),
    (0, "10.5"), (0, "100.5"), (0, "1000.5"),
    # Precision 1: x.05 boundaries
    (1, "0.05"), (1, "0.15"), (1, "0.25"), (1, "0.45"), (1, "1.25"), (1, "9.95"),
    (1, "10.05"), (1, "100.15"),
    # Precision 2: x.005 boundaries
    (2, "0.005"), (2, "0.015"), (2, "0.025"), (2, "0.045"), (2, "1.005"),
    (2, "9.995"), (2, "10.005"), (2, "100.005"),
    # Precision 3: x.0005 boundaries
    (3, "0.0005"), (3, "0.0015"), (3, "0.0025"), (3, "0.0045"), (3, "1.0005"),
    (3, "9.9995"), (3, "10.0005"),
)

# Custom Babel number patterns with known maximum fraction digit counts.
# The pattern= code path calls parse_pattern() for pre-quantization (v0.145.0
# fix). The oracle verifies ROUND_HALF_UP at the known max_frac precision.
_NUMBER_PATTERNS_WITH_PREC: tuple[tuple[str, int], ...] = (
    ("#,##0.##", 2),
    ("#,##0.00", 2),
    ("#,##0", 0),
    ("0.####", 4),
    ("#0.#####", 5),
    ("#,##0.000", 3),
    ("0", 0),
    ("0.0", 1),
    ("0.00", 2),
    ("###.##", 2),
    ("0.0#", 2),
    ("#,##0.0000", 4),
)

# Large values > 1e9 for grouping separator stress testing.
# In de-DE, the group separator is '.' which conflicts with the decimal '.';
# correct oracle extraction requires removing group seps before replacing decimal.
_LARGE_VALUES: tuple[str, ...] = (
    "1000000000",
    "9999999999",
    "1234567890",
    "1000000000.50",
    "1234567890.99",
    "9999999999.005",
    "100000000000",
    "999999999999.5",
)


# --- Module State ---

_state = BaseFuzzerState(
    checkpoint_interval=500,
    seed_corpus_max_size=500,
    fuzzer_name="numbers",
    fuzzer_target="number_format (NUMBER function ROUND_HALF_UP oracle)",
    pattern_intended_weights={name: float(w) for name, w in _PATTERN_WEIGHTS},
)
_domain = NumbersMetrics()

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "numbers"
_REPORT_FILENAME = "fuzz_numbers_report.json"


def _build_stats_dict() -> FuzzStats:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)
    stats["number_calls"] = _domain.number_calls
    stats["oracle_checks"] = _domain.oracle_checks
    stats["oracle_violations"] = _domain.oracle_violations
    stats["min_gt_max_tests"] = _domain.min_gt_max_tests
    stats["boundary_hits"] = _domain.boundary_hits
    stats["large_value_tests"] = _domain.large_value_tests
    stats["determinism_checks"] = _domain.determinism_checks
    stats["preservation_checks"] = _domain.preservation_checks
    return stats


def _emit_checkpoint() -> None:
    """Emit periodic checkpoint."""
    stats = _build_stats_dict()
    emit_checkpoint_report(_state, stats, _REPORT_DIR, _REPORT_FILENAME)


def _emit_report() -> None:
    """Emit crash-proof final report."""
    stats = _build_stats_dict()
    emit_final_report(_state, stats, _REPORT_DIR, _REPORT_FILENAME)


atexit.register(_emit_report)

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.diagnostics.errors import FrozenFluentError
    from ftllexengine.runtime.function_bridge import FluentNumber
    from ftllexengine.runtime.functions import number_format


# --- Oracle Helpers ---


def _extract_oracle_digits(formatted: str, locale: str) -> str | None:
    """Extract absolute numeric digits from a formatted string for oracle comparison.

    Uses Babel to look up locale-specific decimal and grouping separators.
    Returns None when digit extraction is not possible (non-ASCII digits,
    ambiguous separators, or unknown locale).

    Algorithm:
    1. Skip locales where any digit is non-ASCII (ar-EG, hi-IN, etc.).
    2. Look up decimal and group symbols via Babel's public API.
    3. Remove group separators (critical for de-DE where group sep is '.').
    4. Replace decimal separator with ASCII '.'.
    5. Strip remaining non-digit non-dot characters via regex.
    """
    if any(c.isdigit() and not c.isascii() for c in formatted):
        return None
    try:
        from babel.numbers import (
            get_decimal_symbol,
            get_group_symbol,
        )
        babel_locale = locale.replace("-", "_")
        decimal_sym = get_decimal_symbol(babel_locale)
        group_sym = get_group_symbol(babel_locale)
    except ValueError:
        return None
    if decimal_sym == group_sym:
        return None
    normalized = formatted.replace(group_sym, "").replace(decimal_sym, ".")
    digits = re.sub(r"[^\d.]", "", normalized)
    return digits or None


def _run_oracle(
    formatted: str,
    value: Decimal,
    precision: int,
    locale: str,
    context: str,
) -> None:
    """ROUND_HALF_UP oracle: formatted digits must match Decimal.quantize(ROUND_HALF_UP).

    Raises NumbersFuzzError if the oracle detects a rounding mode violation.
    Silently returns (no oracle applied) for NaN/Inf, or when digit extraction
    fails (non-ASCII digits, ambiguous separators, unknown locale).
    """
    if value.is_nan() or value.is_infinite():
        return
    try:
        quantizer = Decimal(10) ** -precision
        expected = abs(value).quantize(quantizer, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return  # Overflow in quantize -- skip

    digits = _extract_oracle_digits(formatted, locale)
    if digits is None:
        return  # Non-ASCII digits or ambiguous separators

    try:
        actual = Decimal(digits)
    except InvalidOperation:
        return

    _domain.oracle_checks += 1
    if actual != expected:
        _domain.oracle_violations += 1
        _state.findings += 1
        msg = (
            f"ROUND_HALF_UP violation ({context}): "
            f"value={value}, precision={precision}, locale={locale} "
            f"expected={expected}, got={actual} (raw='{formatted}')"
        )
        raise NumbersFuzzError(msg)


# --- Pattern Implementations ---


def _pattern_number_grouping_oracle(fdp: atheris.FuzzedDataProvider) -> None:
    """ROUND_HALF_UP oracle with use_grouping=True.

    fuzz_builtins._pattern_number_precision uses use_grouping=False for the
    oracle path. This pattern tests the grouping=True path where group
    separators interact with oracle digit extraction (_extract_oracle_digits
    must strip them before identifying the decimal point).
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    int_part = fdp.ConsumeIntInRange(-9999, 9999)
    frac_str = str(fdp.ConsumeIntInRange(0, 9999)).zfill(4)
    value = Decimal(f"{int_part}.{frac_str}")
    max_frac = fdp.ConsumeIntInRange(0, 4)
    min_frac = fdp.ConsumeIntInRange(0, max_frac)

    _domain.number_calls += 1
    result = number_format(
        value, locale,
        minimum_fraction_digits=min_frac,
        maximum_fraction_digits=max_frac,
        use_grouping=True,
    )
    if not isinstance(result, FluentNumber):
        msg = f"number_format returned {type(result).__name__}, expected FluentNumber"
        raise NumbersFuzzError(msg)
    if result.precision is not None:
        _run_oracle(result.formatted, value, max_frac, locale, "grouping=True")


def _pattern_number_boundary_values(fdp: atheris.FuzzedDataProvider) -> None:
    """Rounding boundary values: x.y5 at precisions 0-3.

    These values fall exactly at the midpoint where ROUND_HALF_EVEN and
    ROUND_HALF_UP diverge (e.g., 2.5 rounds to 2 with HALF_EVEN but 3 with
    HALF_UP). Using a targeted corpus avoids depending on coverage-guided
    discovery to find these rare values.
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    precision, val_str = cast(
        "tuple[int, str]",
        fdp.PickValueInList(list(_BOUNDARY_VALUES)),
    )
    value = Decimal(val_str)
    _domain.boundary_hits += 1
    _domain.number_calls += 1
    result = number_format(
        value, locale,
        minimum_fraction_digits=precision,
        maximum_fraction_digits=precision,
        use_grouping=fdp.ConsumeBool(),
    )
    if not isinstance(result, FluentNumber):
        msg = f"number_format(boundary) returned {type(result).__name__}"
        raise NumbersFuzzError(msg)
    if result.precision is not None:
        _run_oracle(
            result.formatted, value, precision, locale, f"boundary(prec={precision})"
        )


def _pattern_number_pattern_oracle(fdp: atheris.FuzzedDataProvider) -> None:
    """Custom pattern= path with ROUND_HALF_UP oracle.

    The custom pattern= code path calls parse_pattern() for pre-quantization
    (the v0.145.0 fix). This pattern provides dedicated oracle coverage for
    that specific execution path, which was uncovered in fuzz_builtins.
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    int_part = fdp.ConsumeIntInRange(-999, 999)
    frac_str = str(fdp.ConsumeIntInRange(0, 99999)).zfill(5)
    value = Decimal(f"{int_part}.{frac_str}")
    pattern, max_frac = cast(
        "tuple[str, int]",
        fdp.PickValueInList(list(_NUMBER_PATTERNS_WITH_PREC)),
    )
    _domain.number_calls += 1
    result = number_format(value, locale, pattern=pattern)
    if not isinstance(result, FluentNumber):
        msg = f"number_format(pattern=) returned {type(result).__name__}"
        raise NumbersFuzzError(msg)
    _run_oracle(result.formatted, value, max_frac, locale, f"pattern='{pattern}'")


def _pattern_number_negative_oracle(fdp: atheris.FuzzedDataProvider) -> None:
    """ROUND_HALF_UP oracle for negative values.

    Verifies that negative values are handled correctly by the oracle
    (oracle uses abs() before quantize, matching the formatting behavior).
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    int_part = fdp.ConsumeIntInRange(0, 9999)
    frac_str = str(fdp.ConsumeIntInRange(0, 9999)).zfill(4)
    value = Decimal(f"-{int_part}.{frac_str}")
    max_frac = fdp.ConsumeIntInRange(0, 4)
    min_frac = fdp.ConsumeIntInRange(0, max_frac)
    _domain.number_calls += 1
    result = number_format(
        value, locale,
        minimum_fraction_digits=min_frac,
        maximum_fraction_digits=max_frac,
        use_grouping=fdp.ConsumeBool(),
    )
    if not isinstance(result, FluentNumber):
        msg = f"number_format(negative) returned {type(result).__name__}"
        raise NumbersFuzzError(msg)
    if result.precision is not None:
        _run_oracle(result.formatted, value, max_frac, locale, "negative")


def _pattern_number_large_integers(fdp: atheris.FuzzedDataProvider) -> None:
    """Values > 1e9: grouping separator interaction with oracle extraction.

    Large values stress the group-separator handling in _extract_oracle_digits.
    In de-DE, the group separator is '.' which conflicts with the decimal '.';
    correct extraction requires removing group separators before replacing decimal.
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    val_str = cast("str", fdp.PickValueInList(list(_LARGE_VALUES)))
    value = Decimal(val_str)
    _domain.large_value_tests += 1
    _domain.number_calls += 1
    result = number_format(
        value, locale,
        minimum_fraction_digits=0,
        maximum_fraction_digits=2,
        use_grouping=fdp.ConsumeBool(),
    )
    if not isinstance(result, FluentNumber):
        msg = f"number_format(large) returned {type(result).__name__}"
        raise NumbersFuzzError(msg)
    if not result.formatted:
        msg = f"number_format({value}, {locale}) returned empty formatted string"
        raise NumbersFuzzError(msg)
    _run_oracle(result.formatted, value, 2, locale, "large_integer")


def _pattern_number_determinism(fdp: atheris.FuzzedDataProvider) -> None:
    """Determinism: same value/locale/params must produce identical FluentNumber.

    Tests that number_format is a pure function with no hidden mutable state
    that could produce different results on successive calls with equal inputs.
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    int_part = fdp.ConsumeIntInRange(-999, 999)
    frac_part = fdp.ConsumeIntInRange(0, 99)
    value = Decimal(f"{int_part}.{frac_part:02d}")
    min_frac = fdp.ConsumeIntInRange(0, 3)
    max_frac = fdp.ConsumeIntInRange(min_frac, 4)
    grouping = fdp.ConsumeBool()

    _domain.determinism_checks += 1
    _domain.number_calls += 2

    r1 = number_format(
        value, locale,
        minimum_fraction_digits=min_frac,
        maximum_fraction_digits=max_frac,
        use_grouping=grouping,
    )
    r2 = number_format(
        value, locale,
        minimum_fraction_digits=min_frac,
        maximum_fraction_digits=max_frac,
        use_grouping=grouping,
    )

    if not (isinstance(r1, FluentNumber) and isinstance(r2, FluentNumber)):
        return
    if r1.formatted != r2.formatted:
        _state.findings += 1
        msg = (
            f"Determinism violation: number_format({value!r}, {locale!r}) "
            f"produced '{r1.formatted}' then '{r2.formatted}'"
        )
        raise NumbersFuzzError(msg)
    if r1.precision != r2.precision:
        _state.findings += 1
        msg = (
            f"Precision non-determinism: number_format({value!r}, {locale!r}) "
            f"produced precision {r1.precision} then {r2.precision}"
        )
        raise NumbersFuzzError(msg)


def _pattern_number_value_preservation(fdp: atheris.FuzzedDataProvider) -> None:
    """FluentNumber invariants: non-empty formatted string and non-negative precision.

    Verifies the basic FluentNumber contract: formatted must be a non-empty
    string for any finite numeric input, and precision must be >= 0 when set.
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    int_part = fdp.ConsumeIntInRange(-9999, 9999)
    frac_str = str(fdp.ConsumeIntInRange(0, 9999999)).zfill(7)
    value = Decimal(f"{int_part}.{frac_str}")
    _domain.preservation_checks += 1
    _domain.number_calls += 1

    result = number_format(value, locale)

    if not isinstance(result, FluentNumber):
        msg = f"number_format returned {type(result).__name__}, expected FluentNumber"
        raise NumbersFuzzError(msg)
    if not result.formatted:
        msg = f"number_format({value!r}, {locale!r}) returned empty formatted string"
        raise NumbersFuzzError(msg)
    if result.precision is not None and result.precision < 0:
        _state.findings += 1
        msg = (
            f"Negative precision {result.precision} for "
            f"number_format({value!r}, {locale!r})"
        )
        raise NumbersFuzzError(msg)


def _pattern_number_min_gt_max(fdp: atheris.FuzzedDataProvider) -> None:
    """minimum_fraction_digits > maximum_fraction_digits clamping.

    When min > max, format_number silently bumps maximum to match minimum,
    matching JS Intl.NumberFormat behavior. Verifies no crash and non-empty
    output across all locale/value combinations.
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    int_part = fdp.ConsumeIntInRange(-999, 999)
    frac_part = fdp.ConsumeIntInRange(0, 99)
    value = Decimal(f"{int_part}.{frac_part:02d}")
    max_frac = fdp.ConsumeIntInRange(0, 4)
    min_frac = fdp.ConsumeIntInRange(max_frac + 1, max_frac + 5)  # guarantees min > max
    _domain.min_gt_max_tests += 1
    _domain.number_calls += 1
    result = number_format(
        value, locale,
        minimum_fraction_digits=min_frac,
        maximum_fraction_digits=max_frac,
    )
    if not isinstance(result, FluentNumber):
        msg = f"number_format(min>max) returned {type(result).__name__}"
        raise NumbersFuzzError(msg)
    if not result.formatted:
        msg = (
            f"number_format({value}, min={min_frac}, max={max_frac}) "
            f"returned empty formatted string"
        )
        raise NumbersFuzzError(msg)


# --- Pattern Dispatch ---

_PATTERN_DISPATCH = {
    "number_grouping_oracle": _pattern_number_grouping_oracle,
    "number_boundary_values": _pattern_number_boundary_values,
    "number_pattern_oracle": _pattern_number_pattern_oracle,
    "number_negative_oracle": _pattern_number_negative_oracle,
    "number_large_integers": _pattern_number_large_integers,
    "number_determinism": _pattern_number_determinism,
    "number_value_preservation": _pattern_number_value_preservation,
    "number_min_gt_max": _pattern_number_min_gt_max,
}


# --- Main Entry Point ---


def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test NUMBER function ROUND_HALF_UP formatting invariants."""
    if _state.iterations == 0:
        _state.initial_memory_mb = (
            get_process().memory_info().rss / (1024 * 1024)
        )

    _state.iterations += 1
    _state.status = "running"

    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_checkpoint()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    pattern_name = select_pattern_round_robin(_state, _PATTERN_SCHEDULE)
    _state.pattern_coverage[pattern_name] = (
        _state.pattern_coverage.get(pattern_name, 0) + 1
    )

    try:
        handler = _PATTERN_DISPATCH[pattern_name]
        handler(fdp)
    except (*_ALLOWED_EXCEPTIONS, FrozenFluentError) as e:
        error_type = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_type] = (
            _state.error_counts.get(error_type, 0) + 1
        )
    except NumbersFuzzError:
        _state.findings += 1
        raise
    except Exception:
        _state.findings += 1
        raise
    finally:
        is_interesting = (
            "oracle" in pattern_name
            or pattern_name in ("number_boundary_values", "number_min_gt_max")
            or (time.perf_counter() - start_time) * 1000 > 1.0
        )
        record_iteration_metrics(
            _state, pattern_name, start_time, data,
            is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)


def main() -> None:
    """Run the number_format oracle fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="NUMBER function runtime formatting oracle fuzzer (Atheris)",
        epilog="All unrecognized arguments are passed to libFuzzer.",
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=500,
        help="Emit report every N iterations (default: 500)",
    )
    parser.add_argument(
        "--seed-corpus-size",
        type=int,
        default=500,
        help="Maximum in-memory seed corpus size (default: 500)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size
    sys.argv = [sys.argv[0], *remaining]

    print_fuzzer_banner(
        title="NUMBER Function Runtime Formatting Oracle Fuzzer (Atheris)",
        target="ftllexengine.runtime.functions.number_format",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
        extra_lines=[
            f"Patterns:   {len(_PATTERN_WEIGHTS)}"
            f" ({sum(w for _, w in _PATTERN_WEIGHTS)} weighted slots)",
            f"Locales:    {len(_VALID_LOCALES)} validated (ASCII-digit only)",
            f"Boundaries: {len(_BOUNDARY_VALUES)} x.y5 values across precisions 0-3",
            "Oracle:     ROUND_HALF_UP via Decimal.quantize(ROUND_HALF_UP)",
        ],
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
