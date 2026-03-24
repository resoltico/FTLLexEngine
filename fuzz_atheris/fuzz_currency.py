#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: currency - CURRENCY Function Runtime Formatting (Oracle)
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""CURRENCY Function Runtime Formatting Oracle Fuzzer (Atheris).

Targets: ftllexengine.runtime.functions.currency_format

Concern boundary: This fuzzer provides deep oracle-based testing of the CURRENCY
function's runtime formatting path. It is complementary to fuzz_builtins (which
covers the full Babel boundary including NUMBER and DATETIME) and
fuzz_locale_context (which covers LocaleContext.format_currency direct API with
ROUND_HALF_EVEN oracle). This fuzzer specializes on CURRENCY-specific coverage gaps:

- Custom pattern= path oracle (highest priority): provides dedicated oracle coverage
  for the format_currency(pattern=...) execution path.
  fuzz_locale_context case 7 tests pattern= but WITHOUT an oracle.
  fuzz_builtins does not test currency pattern= at all.
- 3-decimal currencies (BHD, KWD, OMR): rounding boundary at 3 decimal places
  (x.xxx5) is distinct from the 2-decimal case and must be verified independently.
- 0-decimal currencies (JPY, KRW): rounding at 0 decimal places (x.5) uses
  ROUND_HALF_EVEN (0.5->0, 1.5->2, 2.5->2, 3.5->4).
- Display mode value preservation: currency_format with display='code'/'name'
  must produce the same FluentNumber.precision as with display='symbol'.
- Negative amounts and large amounts (>1e6) for each oracle path.
- Locale matrix: same currency must produce consistent precision across locales.
- use_grouping, currency_digits, numbering_system parameter coverage.

Patterns (11):
- currency_pattern_oracle: custom pattern= path with ROUND_HALF_EVEN oracle (weight 16)
- currency_boundary_values: x.y5 boundary values per currency precision (weight 15)
- currency_3decimal_oracle: BHD/KWD/OMR with 3-decimal oracle (weight 13)
- currency_0decimal_oracle: JPY/KRW with 0-decimal oracle (weight 12)
- currency_display_preservation: display mode precision consistency (weight 11)
- currency_negative_oracle: negative amounts with ROUND_HALF_EVEN (weight 11)
- currency_large_oracle: amounts > 1e6 with oracle (weight 11)
- currency_locale_matrix: same value/currency across multiple locales (weight 11)
- currency_use_grouping: use_grouping=True/False parameter coverage (weight 8)
- currency_digits_override: currency_digits=True/False parameter coverage (weight 8)
- currency_numbering_system: non-Latin CLDR numbering systems (weight 7)

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
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any, Literal, cast

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
class CurrencyFormatMetrics:
    """Domain-specific metrics for currency_format oracle fuzzer."""

    currency_calls: int = 0
    oracle_checks: int = 0
    oracle_violations: int = 0
    boundary_hits: int = 0
    pattern_calls: int = 0
    three_decimal_tests: int = 0
    zero_decimal_tests: int = 0
    display_preservation_checks: int = 0
    large_value_tests: int = 0


class CurrencyFuzzError(Exception):
    """Raised when a CURRENCY function formatting invariant is violated."""


# --- Constants ---

_ALLOWED_EXCEPTIONS = (
    ValueError,
    TypeError,
    OverflowError,
    ArithmeticError,
    InvalidOperation,
)

_PATTERN_WEIGHTS: tuple[tuple[str, int], ...] = (
    ("currency_pattern_oracle", 16),
    ("currency_boundary_values", 15),
    ("currency_3decimal_oracle", 13),
    ("currency_0decimal_oracle", 12),
    ("currency_display_preservation", 11),
    ("currency_negative_oracle", 11),
    ("currency_large_oracle", 11),
    ("currency_locale_matrix", 11),
    ("currency_use_grouping", 8),
    ("currency_digits_override", 8),
    ("currency_numbering_system", 7),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)

# Validated locales (ASCII-digit only): non-ASCII-digit locales (ar-EG, hi-IN)
# are excluded to avoid false oracle rejections. They are covered by
# fuzz_locale_context which uses Babel's own normalization.
_VALID_LOCALES: tuple[str, ...] = (
    "en-US", "en-GB", "de-DE", "fr-FR", "es-ES",
    "ja-JP", "zh-CN", "ko-KR",
    "sv-SE", "nb-NO", "pt-BR", "nl-NL",
)

# Currency codes grouped by CLDR decimal precision.
# Precision is derived at oracle time via babel.numbers.get_currency_precision()
# to stay in sync with CLDR rather than maintaining a parallel table.
_CURRENCIES_0_DECIMAL: tuple[str, ...] = ("JPY", "KRW")
_CURRENCIES_2_DECIMAL: tuple[str, ...] = ("USD", "EUR", "GBP", "AUD", "CAD", "CHF")
_CURRENCIES_3_DECIMAL: tuple[str, ...] = ("BHD", "KWD", "OMR")
_ALL_CURRENCIES: tuple[str, ...] = (
    *_CURRENCIES_0_DECIMAL,
    *_CURRENCIES_2_DECIMAL,
    *_CURRENCIES_3_DECIMAL,
)

# Currency display modes for display preservation test.
_DISPLAY_MODES: tuple[str, ...] = ("symbol", "code", "name")

# Custom Babel currency patterns with known maximum fraction digit counts.
# The pattern= code path calls parse_pattern() for pre-quantization.
# The oracle verifies ROUND_HALF_EVEN at the known max_frac precision.
# Used with 2-decimal currencies (USD, EUR) where the pattern precision is known.
_CURRENCY_PATTERNS_WITH_PREC: tuple[tuple[str, int], ...] = (
    ("#,##0.00 \u00a4", 2),
    ("\u00a4#,##0.00", 2),
    ("\u00a4 #,##0.##", 2),
    ("#,##0.00\u00a4", 2),
    ("\u00a4#,##0", 0),
    ("\u00a4#,##0.000", 3),
    ("#,##0.0 \u00a4", 1),
    ("\u00a40.00", 2),
)

# Rounding boundary values by precision level.
# Each value falls exactly at the midpoint where ROUND_HALF_EVEN and
# ROUND_HALF_UP diverge. Organized as (precision, value_string) pairs.
_BOUNDARY_VALUES_BY_PREC: tuple[tuple[int, str], ...] = (
    # Precision 0 (JPY, KRW): x.5 boundaries
    (0, "0.5"), (0, "1.5"), (0, "2.5"), (0, "10.5"), (0, "100.5"),
    (0, "999.5"), (0, "1000.5"),
    # Precision 2 (USD, EUR, etc.): x.005 boundaries
    (2, "0.005"), (2, "0.015"), (2, "0.025"), (2, "1.005"), (2, "9.995"),
    (2, "10.005"), (2, "100.005"), (2, "999.995"),
    # Precision 3 (BHD, KWD, OMR): x.0005 boundaries
    (3, "0.0005"), (3, "0.0015"), (3, "0.0025"), (3, "1.0005"), (3, "9.9995"),
    (3, "10.0005"), (3, "999.9995"),
)

# Large currency amounts (> 1e6) for grouping separator stress testing.
# Large values exercise group-separator handling in _extract_oracle_digits
# (de-DE uses '.' as group sep which conflicts with decimal '.').
_LARGE_AMOUNTS: tuple[str, ...] = (
    "1000000.50",
    "9999999.99",
    "1234567.005",
    "10000000.00",
    "99999999.995",
    "1000000000.50",
)


# --- Module State ---

_state = BaseFuzzerState(
    checkpoint_interval=500,
    seed_corpus_max_size=500,
    fuzzer_name="currency",
    fuzzer_target="currency_format (CURRENCY function ROUND_HALF_EVEN oracle)",
    pattern_intended_weights={name: float(w) for name, w in _PATTERN_WEIGHTS},
)
_domain = CurrencyFormatMetrics()

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "currency"
_REPORT_FILENAME = "fuzz_currency_report.json"


def _build_stats_dict() -> FuzzStats:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)
    stats["currency_calls"] = _domain.currency_calls
    stats["oracle_checks"] = _domain.oracle_checks
    stats["oracle_violations"] = _domain.oracle_violations
    stats["boundary_hits"] = _domain.boundary_hits
    stats["pattern_calls"] = _domain.pattern_calls
    stats["three_decimal_tests"] = _domain.three_decimal_tests
    stats["zero_decimal_tests"] = _domain.zero_decimal_tests
    stats["display_preservation_checks"] = _domain.display_preservation_checks
    stats["large_value_tests"] = _domain.large_value_tests
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
    from ftllexengine.runtime.functions import currency_format


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
       Handles multi-character currency symbols (A$, CA$) that would break
       manual str.replace() chaining.
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
    currency: str,
    context: str,
) -> None:
    """ROUND_HALF_EVEN oracle: formatted digits must match Decimal.quantize(ROUND_HALF_EVEN).

    When precision is -1 (sentinel), derives the CLDR-standard decimal count via
    babel.numbers.get_currency_precision(currency). This sentinel avoids hardcoding
    per-currency precision (KWD=3, JPY=0, USD=2) and stays in sync with CLDR.

    Raises CurrencyFuzzError if a rounding mode violation is detected.
    Silently returns (no oracle applied) for NaN/Inf, unknown currency/locale,
    or when digit extraction fails.
    """
    if value.is_nan() or value.is_infinite():
        return

    # Sentinel -1: derive CLDR precision at oracle time.
    if precision == -1:
        try:
            from babel.numbers import (
                get_currency_precision,
            )
            precision = get_currency_precision(currency)
        except (ValueError, LookupError):
            return  # Unknown currency -- skip oracle

    try:
        quantizer = Decimal(10) ** -precision
        expected = abs(value).quantize(quantizer, rounding=ROUND_HALF_EVEN)
    except InvalidOperation:
        return  # Overflow -- skip

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
            f"ROUND_HALF_EVEN violation (currency={currency}, {context}): "
            f"value={value}, precision={precision}, locale={locale} "
            f"expected={expected}, got={actual} (raw='{formatted}')"
        )
        raise CurrencyFuzzError(msg)


# --- Pattern Implementations ---


def _pattern_currency_pattern_oracle(fdp: atheris.FuzzedDataProvider) -> None:
    """Custom pattern= path with ROUND_HALF_EVEN oracle.

    Provides dedicated oracle coverage for the custom pattern= execution path.

    fuzz_locale_context case 7 tests the pattern= path but without an oracle.
    fuzz_builtins does not test currency pattern= at all.
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    currency = cast("str", fdp.PickValueInList(list(_CURRENCIES_2_DECIMAL)))
    int_part = fdp.ConsumeIntInRange(0, 9999)
    frac_str = str(fdp.ConsumeIntInRange(0, 99999)).zfill(5)
    value = Decimal(f"{int_part}.{frac_str}")
    pattern, max_frac = cast(
        "tuple[str, int]",
        fdp.PickValueInList(list(_CURRENCY_PATTERNS_WITH_PREC)),
    )
    _domain.pattern_calls += 1
    _domain.currency_calls += 1
    result = currency_format(value, locale, currency=currency, pattern=pattern)
    if not isinstance(result, FluentNumber):
        msg = f"currency_format(pattern=) returned {type(result).__name__}"
        raise CurrencyFuzzError(msg)
    _run_oracle(result.formatted, value, max_frac, locale, currency, f"pattern='{pattern}'")


def _pattern_currency_boundary_values(fdp: atheris.FuzzedDataProvider) -> None:
    """Rounding boundary values per currency-specific precision.

    Tests x.y5 values at the midpoint for each currency decimal count (0, 2, 3).
    Selects a currency matching the boundary precision to ensure the oracle
    fires on the correct side of the rounding threshold.
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    precision, val_str = cast(
        "tuple[int, str]",
        fdp.PickValueInList(list(_BOUNDARY_VALUES_BY_PREC)),
    )
    match precision:
        case 0:
            currency = cast("str", fdp.PickValueInList(list(_CURRENCIES_0_DECIMAL)))
        case 3:
            currency = cast("str", fdp.PickValueInList(list(_CURRENCIES_3_DECIMAL)))
        case _:  # 2
            currency = cast("str", fdp.PickValueInList(list(_CURRENCIES_2_DECIMAL)))

    value = Decimal(val_str)
    _domain.boundary_hits += 1
    _domain.currency_calls += 1
    result = currency_format(value, locale, currency=currency)
    if not isinstance(result, FluentNumber):
        msg = f"currency_format(boundary) returned {type(result).__name__}"
        raise CurrencyFuzzError(msg)
    # Use CLDR-derived precision (sentinel -1) to stay in sync with CLDR data.
    _run_oracle(
        result.formatted, value, -1, locale, currency, f"boundary(prec={precision})"
    )


def _pattern_currency_3decimal_oracle(fdp: atheris.FuzzedDataProvider) -> None:
    """BHD/KWD/OMR: 3-decimal ROUND_HALF_EVEN oracle.

    3-decimal currencies have a rounding boundary at x.xxx5 that differs from
    the 2-decimal case. The oracle verifies ROUND_HALF_EVEN at precision=3 across
    all ASCII-digit locales.
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    currency = cast("str", fdp.PickValueInList(list(_CURRENCIES_3_DECIMAL)))
    int_part = fdp.ConsumeIntInRange(0, 9999)
    frac_str = str(fdp.ConsumeIntInRange(0, 9999)).zfill(4)
    value = Decimal(f"{int_part}.{frac_str}")
    _domain.three_decimal_tests += 1
    _domain.currency_calls += 1
    result = currency_format(value, locale, currency=currency)
    if not isinstance(result, FluentNumber):
        msg = f"currency_format(3-decimal) returned {type(result).__name__}"
        raise CurrencyFuzzError(msg)
    _run_oracle(result.formatted, value, -1, locale, currency, "3decimal")


def _pattern_currency_0decimal_oracle(fdp: atheris.FuzzedDataProvider) -> None:
    """JPY/KRW: 0-decimal ROUND_HALF_EVEN oracle.

    0-decimal currencies round at x.5 boundaries. ROUND_HALF_EVEN rounds
    0.5->0, 1.5->2, 2.5->2, 3.5->4 (nearest even digit). The oracle verifies
    this behavior for JPY and KRW.
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    currency = cast("str", fdp.PickValueInList(list(_CURRENCIES_0_DECIMAL)))
    int_part = fdp.ConsumeIntInRange(0, 99999)
    frac_part = fdp.ConsumeIntInRange(0, 99)
    value = Decimal(f"{int_part}.{frac_part:02d}")
    _domain.zero_decimal_tests += 1
    _domain.currency_calls += 1
    result = currency_format(value, locale, currency=currency)
    if not isinstance(result, FluentNumber):
        msg = f"currency_format(0-decimal) returned {type(result).__name__}"
        raise CurrencyFuzzError(msg)
    _run_oracle(result.formatted, value, -1, locale, currency, "0decimal")


def _pattern_currency_display_preservation(fdp: atheris.FuzzedDataProvider) -> None:
    """Display mode precision consistency: symbol/code/name must yield same precision.

    The display mode only affects the formatted string representation (e.g.
    '$' vs 'USD' vs 'US dollar'). The underlying numeric precision must be
    preserved identically across all display modes for the same currency.
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    currency = cast("str", fdp.PickValueInList(list(_ALL_CURRENCIES)))
    int_part = fdp.ConsumeIntInRange(0, 9999)
    frac_part = fdp.ConsumeIntInRange(0, 99)
    value = Decimal(f"{int_part}.{frac_part:02d}")
    _domain.display_preservation_checks += 1

    results: dict[str, FluentNumber] = {}
    for _display in _DISPLAY_MODES:
        display = cast("Literal['symbol', 'code', 'name']", _display)
        _domain.currency_calls += 1
        r = currency_format(value, locale, currency=currency, currency_display=display)
        if isinstance(r, FluentNumber):
            results[display] = r

    if len(results) >= 2:
        precisions = {name: r.precision for name, r in results.items()}
        unique_prec = set(precisions.values())
        if len(unique_prec) > 1:
            _state.findings += 1
            msg = (
                f"Display mode precision divergence for {currency}, {locale}: "
                f"{precisions}"
            )
            raise CurrencyFuzzError(msg)


def _pattern_currency_negative_oracle(fdp: atheris.FuzzedDataProvider) -> None:
    """Negative amounts with ROUND_HALF_EVEN oracle.

    Verifies that negative currency amounts are handled correctly (oracle uses
    abs() before quantize, matching the formatting behavior).
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    currency = cast("str", fdp.PickValueInList(list(_ALL_CURRENCIES)))
    int_part = fdp.ConsumeIntInRange(0, 9999)
    frac_str = str(fdp.ConsumeIntInRange(0, 9999)).zfill(4)
    value = Decimal(f"-{int_part}.{frac_str}")
    _domain.currency_calls += 1
    result = currency_format(value, locale, currency=currency)
    if not isinstance(result, FluentNumber):
        msg = f"currency_format(negative) returned {type(result).__name__}"
        raise CurrencyFuzzError(msg)
    _run_oracle(result.formatted, value, -1, locale, currency, "negative")


def _pattern_currency_large_oracle(fdp: atheris.FuzzedDataProvider) -> None:
    """Large amounts (> 1e6) with ROUND_HALF_EVEN oracle.

    Large amounts stress group-separator handling in _extract_oracle_digits.
    In de-DE, the group separator is '.' which conflicts with the decimal '.';
    removing group separators before replacing decimal is critical.
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    currency = cast("str", fdp.PickValueInList(list(_CURRENCIES_2_DECIMAL)))
    val_str = cast("str", fdp.PickValueInList(list(_LARGE_AMOUNTS)))
    value = Decimal(val_str)
    _domain.large_value_tests += 1
    _domain.currency_calls += 1
    result = currency_format(value, locale, currency=currency)
    if not isinstance(result, FluentNumber):
        msg = f"currency_format(large) returned {type(result).__name__}"
        raise CurrencyFuzzError(msg)
    if not result.formatted:
        msg = f"currency_format({value}, {currency}, {locale}) returned empty formatted"
        raise CurrencyFuzzError(msg)
    _run_oracle(result.formatted, value, -1, locale, currency, "large")


def _pattern_currency_locale_matrix(fdp: atheris.FuzzedDataProvider) -> None:
    """Same value/currency formatted across multiple locales.

    Verifies that FluentNumber.precision is consistent across all locales for
    a given currency (CLDR precision is per-currency, not per-territory, so
    all locales must produce the same decimal count for the same currency).
    """
    currency = cast("str", fdp.PickValueInList(list(_ALL_CURRENCIES)))
    int_part = fdp.ConsumeIntInRange(0, 9999)
    frac_part = fdp.ConsumeIntInRange(0, 99)
    value = Decimal(f"{int_part}.{frac_part:02d}")
    num_locales = fdp.ConsumeIntInRange(3, min(6, len(_VALID_LOCALES)))

    precisions: list[int] = []
    for locale in list(_VALID_LOCALES)[:num_locales]:
        _domain.currency_calls += 1
        r = currency_format(value, locale, currency=currency)
        if isinstance(r, FluentNumber) and r.precision is not None:
            precisions.append(r.precision)

    if len(precisions) >= 2 and len(set(precisions)) > 1:
        _state.findings += 1
        msg = (
            f"Locale matrix precision inconsistency for {currency}: "
            f"precisions={precisions} across {num_locales} locales"
        )
        raise CurrencyFuzzError(msg)


def _pattern_currency_use_grouping(fdp: atheris.FuzzedDataProvider) -> None:
    """use_grouping parameter on currency_format: True/False variations.

    Verifies that currency_format respects the use_grouping parameter.
    Large amounts (> 1000) are used to ensure the grouping separator
    would appear with use_grouping=True.
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    currency = cast("str", fdp.PickValueInList(list(_ALL_CURRENCIES)))
    value = Decimal(fdp.ConsumeIntInRange(1000, 9_999_999))
    use_grouping = fdp.ConsumeBool()
    _domain.currency_calls += 1
    result = currency_format(value, locale, currency=currency, use_grouping=use_grouping)
    if not isinstance(result, FluentNumber):
        msg = (
            f"currency_format(use_grouping={use_grouping}) "
            f"returned {type(result).__name__}"
        )
        raise CurrencyFuzzError(msg)
    if not result.formatted:
        msg = (
            f"currency_format({value}, {currency}, use_grouping={use_grouping}) "
            f"returned empty formatted string for {locale}"
        )
        raise CurrencyFuzzError(msg)


def _pattern_currency_digits_override(fdp: atheris.FuzzedDataProvider) -> None:
    """currency_digits=True/False on currency_format.

    When currency_digits=True (default), ISO 4217 decimal count overrides
    min/max fraction digits (JPY=0, BHD=3, USD=2). When False, no automatic
    ISO 4217 adjustment is applied, so the default 2 fraction digits are used.
    Verifies non-crash and non-empty output for both modes.
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    currency = cast("str", fdp.PickValueInList(list(_ALL_CURRENCIES)))
    int_part = fdp.ConsumeIntInRange(0, 9999)
    frac_part = fdp.ConsumeIntInRange(0, 99)
    value = Decimal(f"{int_part}.{frac_part:02d}")
    currency_digits = fdp.ConsumeBool()
    _domain.currency_calls += 1
    result = currency_format(
        value, locale, currency=currency, currency_digits=currency_digits,
    )
    if not isinstance(result, FluentNumber):
        msg = (
            f"currency_format(currency_digits={currency_digits}) "
            f"returned {type(result).__name__}"
        )
        raise CurrencyFuzzError(msg)
    if not result.formatted:
        msg = (
            f"currency_format({value}, {currency}, "
            f"currency_digits={currency_digits}) returned empty for {locale}"
        )
        raise CurrencyFuzzError(msg)


def _pattern_currency_numbering_system(fdp: atheris.FuzzedDataProvider) -> None:
    """Non-Latin numbering systems on currency_format.

    Verifies that currency_format accepts a numbering_system parameter and
    returns a non-empty FluentNumber for known-good CLDR numbering systems.
    """
    locale = cast("str", fdp.PickValueInList(list(_VALID_LOCALES)))
    currency = cast("str", fdp.PickValueInList(list(_ALL_CURRENCIES)))
    int_part = fdp.ConsumeIntInRange(0, 9999)
    frac_part = fdp.ConsumeIntInRange(0, 99)
    value = Decimal(f"{int_part}.{frac_part:02d}")
    numbering_system = cast(
        "str",
        fdp.PickValueInList(["latn", "arab", "arabext", "deva", "beng"]),
    )
    _domain.currency_calls += 1
    result = currency_format(
        value, locale, currency=currency, numbering_system=numbering_system,
    )
    if not isinstance(result, FluentNumber):
        msg = (
            f"currency_format(numbering_system={numbering_system!r}) "
            f"returned {type(result).__name__}"
        )
        raise CurrencyFuzzError(msg)
    if not result.formatted:
        msg = (
            f"currency_format({value}, {currency}, "
            f"numbering_system={numbering_system!r}) returned empty for {locale}"
        )
        raise CurrencyFuzzError(msg)


# --- Pattern Dispatch ---

_PATTERN_DISPATCH = {
    "currency_pattern_oracle": _pattern_currency_pattern_oracle,
    "currency_boundary_values": _pattern_currency_boundary_values,
    "currency_3decimal_oracle": _pattern_currency_3decimal_oracle,
    "currency_0decimal_oracle": _pattern_currency_0decimal_oracle,
    "currency_display_preservation": _pattern_currency_display_preservation,
    "currency_negative_oracle": _pattern_currency_negative_oracle,
    "currency_large_oracle": _pattern_currency_large_oracle,
    "currency_locale_matrix": _pattern_currency_locale_matrix,
    "currency_use_grouping": _pattern_currency_use_grouping,
    "currency_digits_override": _pattern_currency_digits_override,
    "currency_numbering_system": _pattern_currency_numbering_system,
}


# --- Main Entry Point ---


def test_one_input(data: bytes) -> None:
    """Atheris entry point: Test CURRENCY function ROUND_HALF_EVEN formatting invariants."""
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
    except CurrencyFuzzError:
        _state.findings += 1
        raise
    except Exception:
        _state.findings += 1
        raise
    finally:
        is_interesting = (
            "oracle" in pattern_name
            or pattern_name in ("currency_boundary_values", "currency_locale_matrix")
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
    """Run the currency_format oracle fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="CURRENCY function runtime formatting oracle fuzzer (Atheris)",
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
        title="CURRENCY Function Runtime Formatting Oracle Fuzzer (Atheris)",
        target="ftllexengine.runtime.functions.currency_format",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
        extra_lines=[
            f"Patterns:   {len(_PATTERN_WEIGHTS)}"
            f" ({sum(w for _, w in _PATTERN_WEIGHTS)} weighted slots)",
            f"Locales:    {len(_VALID_LOCALES)} validated (ASCII-digit only)",
            f"Currencies: {len(_ALL_CURRENCIES)}"
            f" ({len(_CURRENCIES_0_DECIMAL)} zero-dec,"
            f" {len(_CURRENCIES_2_DECIMAL)} two-dec,"
            f" {len(_CURRENCIES_3_DECIMAL)} three-dec)",
            "Oracle:     ROUND_HALF_EVEN via Decimal.quantize + CLDR precision",
        ],
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
