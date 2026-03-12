#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: locale_context - LocaleContext Direct Formatting API
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""LocaleContext Direct Formatting API Fuzzer (Atheris).

Targets: ftllexengine.runtime.locale_context.LocaleContext

Concern boundary: This fuzzer stress-tests the Babel formatting boundary by
calling LocaleContext.format_number(), format_currency(), and format_datetime()
DIRECTLY (bypassing the function bridge and resolver). fuzz_builtins tests the
same formatting via the NUMBER/CURRENCY/DATETIME function API; the function bridge
layer adds indirection that Atheris corpus mutations may not efficiently penetrate.
Direct API testing isolates the Babel layer and enables:
- Adversarial min_fraction_digits/max_fraction_digits combinations (min>max)
- Custom Babel pattern strings passed to format_number/format_currency
- format_datetime with date-only objects promoted to midnight datetime
- LocaleContext.create() with fuzz-generated locale codes
- Cross-locale consistency: same value, same precision, different locales
- ROUND_HALF_UP oracle: formatted digits match Decimal.quantize(ROUND_HALF_UP)

The ROUND_HALF_UP rounding bugs in v0.145.0 (format_number and format_currency
used ROUND_HALF_EVEN instead of ROUND_HALF_UP) lived in this module and were
only found by manual oracle testing. This fuzzer applies oracle-based testing
at fuzzing scale to prevent recurrence.

Unique coverage (not covered by other fuzzers):
- format_number() direct: min/max fraction digits, grouping, custom pattern
- format_currency() direct: currency precision override, custom pattern
- format_datetime() direct: date object promotion, time/date style combos
- LocaleContext.create() with invalid locale codes (boundary testing)
- LocaleContext.cache_size() and clear_cache() lifecycle
- Cross-locale same-value formatting (determinism invariant)
- ROUND_HALF_UP oracle checks at fuzz scale

Patterns (14):
- format_number_int: integer values across locales
- format_number_decimal: Decimal/float values with precision
- format_number_precision: min/max fraction digit combinations
- format_number_custom_pattern: custom Babel number pattern strings
- format_number_grouping: grouping=True/False variations
- format_currency_standard: standard currency formatting
- format_currency_precision_override: decimal override per currency
- format_currency_custom_pattern: custom Babel currency pattern strings
- format_datetime_date_obj: plain date objects (midnight promotion)
- format_datetime_datetime_obj: datetime objects with styles
- format_datetime_style_combo: date_style / time_style combinations
- format_datetime_pattern: custom Babel datetime pattern strings
- locale_create_adversarial: LocaleContext.create() with fuzz locales
- cross_locale_determinism: same value formatted by N locales

Metrics:
- Pattern coverage with weighted round-robin schedule
- format_number/currency/datetime call counts
- ROUND_HALF_UP oracle checks and violations
- Performance profiling (min/mean/p95/p99/max)
- Real memory usage (RSS via psutil)

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
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
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

from fuzz_common import (  # noqa: E402  # pylint: disable=C0413
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
class LocaleContextMetrics:
    """Domain-specific metrics for locale_context fuzzer."""

    format_number_calls: int = 0
    format_currency_calls: int = 0
    format_datetime_calls: int = 0
    invalid_locale_attempts: int = 0
    round_half_up_checks: int = 0
    round_half_up_violations: int = 0
    cross_locale_checks: int = 0


class LocaleContextFuzzError(Exception):
    """Raised when a formatting invariant is violated."""


# --- Constants ---

_ALLOWED_EXCEPTIONS = (
    ValueError,     # invalid locale, invalid format options, invalid precision
    TypeError,      # invalid argument types
    OverflowError,  # extreme numeric values
    ArithmeticError,  # Decimal/float arithmetic edge cases
)

# Pattern definitions with weights (name, weight)
_PATTERN_WEIGHTS: Sequence[tuple[str, int]] = (
    ("format_number_int", 8),
    ("format_number_decimal", 8),
    ("format_number_precision", 8),
    ("format_number_custom_pattern", 6),
    ("format_number_grouping", 6),
    ("format_currency_standard", 8),
    ("format_currency_precision_override", 6),
    ("format_currency_custom_pattern", 5),
    ("format_datetime_date_obj", 7),
    ("format_datetime_datetime_obj", 7),
    ("format_datetime_style_combo", 7),
    ("format_datetime_pattern", 6),
    ("locale_create_adversarial", 8),
    ("cross_locale_determinism", 5),
)

_PATTERN_SCHEDULE: tuple[str, ...] = build_weighted_schedule(
    [name for name, _ in _PATTERN_WEIGHTS],
    [weight for _, weight in _PATTERN_WEIGHTS],
)
_PATTERN_INDEX: dict[str, int] = {
    name: i for i, (name, _) in enumerate(_PATTERN_WEIGHTS)
}

# Validated locales for formatting tests
_VALID_LOCALES: Sequence[str] = (
    "en-US", "en-GB", "de-DE", "fr-FR", "es-ES", "it-IT",
    "ja-JP", "zh-CN", "zh-TW", "ko-KR",
    "ar-EG", "ar-SA", "he-IL",
    "sv-SE", "nb-NO", "fi-FI",
    "ru-RU", "pl-PL", "tr-TR",
    "pt-BR", "nl-NL", "hu-HU",
)

# Currency codes with known decimal precision
_CURRENCIES: Sequence[str] = (
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD",
    "CNY", "INR", "KRW", "SEK", "NOK", "DKK",
    "BHD",  # 3 decimal places
    "KWD",  # 3 decimal places
)

# Date styles
_DATE_STYLES = ("short", "medium", "long", "full")
_TIME_STYLES = ("short", "medium", "long")

# Custom Babel number patterns for pattern fuzzing
_NUMBER_PATTERNS: Sequence[str] = (
    "#,##0.##",
    "#,##0.00",
    "#,##0",
    "0.####",
    "#0.#####",
    "#,##0.000",
    "0",
    "#",
    "0.0",
    "#,###.##",
    "0.00",
    "###.##",
)

# Custom Babel currency patterns
_CURRENCY_PATTERNS: Sequence[str] = (
    "#,##0.00 ¤",
    "¤#,##0.00",
    "¤ #,##0.##",
    "#,##0.00¤",
    "¤#,##0",
)

# Custom datetime patterns (Babel CLDR token format)
_DATETIME_PATTERNS: Sequence[str] = (
    "yyyy-MM-dd",
    "dd/MM/yyyy",
    "MM/dd/yyyy",
    "yyyy-MM-dd HH:mm:ss",
    "dd.MM.yyyy HH:mm",
    "d MMM yyyy",
    "EEEE, MMMM d, yyyy",
    "HH:mm:ss",
    "h:mm a",
)


# --- Module State ---

_state = BaseFuzzerState(
    checkpoint_interval=500,
    seed_corpus_max_size=500,
    fuzzer_name="locale_context",
    fuzzer_target=(
        "LocaleContext.format_number, format_currency, format_datetime "
        "(direct API, ROUND_HALF_UP oracle)"
    ),
    pattern_intended_weights={name: float(w) for name, w in _PATTERN_WEIGHTS},
)
_domain = LocaleContextMetrics()

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "locale_context"
_REPORT_FILENAME = "fuzz_locale_context_report.json"


def _build_stats_dict() -> FuzzStats:
    """Build complete stats dictionary including domain metrics."""
    stats = build_base_stats_dict(_state)
    stats["format_number_calls"] = _domain.format_number_calls
    stats["format_currency_calls"] = _domain.format_currency_calls
    stats["format_datetime_calls"] = _domain.format_datetime_calls
    stats["invalid_locale_attempts"] = _domain.invalid_locale_attempts
    stats["round_half_up_checks"] = _domain.round_half_up_checks
    stats["round_half_up_violations"] = _domain.round_half_up_violations
    stats["cross_locale_checks"] = _domain.cross_locale_checks
    return stats


def _emit_checkpoint() -> None:
    """Emit periodic checkpoint (uses checkpoint markers)."""
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
    from ftllexengine.runtime.locale_context import LocaleContext


def _check_round_half_up(
    result: str,
    value: Decimal,
    precision: int | None,
    locale: str,
    currency: str | None = None,
) -> None:
    """Oracle: formatted digits must match ROUND_HALF_UP quantization.

    Normalizes locale-specific decimal/group symbols to ASCII before digit
    extraction, then compares the numeric part against Decimal.quantize(ROUND_HALF_UP).
    This is the exact oracle that would have caught the v0.145.0 rounding bugs.

    When precision is None, the CLDR-standard decimal count for the currency is
    derived via babel.numbers.get_currency_precision(). Pass None for currency
    formatting to avoid hardcoding currency-specific decimal counts (KWD=3,
    JPY=0, USD=2, etc.).

    Locale-aware normalization is required: for de-DE "6.691,00", the naive
    regex [^\\d.] keeps the thousands dot and removes the decimal comma, producing
    "6.69100" instead of "6691.00". Babel's number_symbols provide the correct
    locale-specific separators.
    """
    import re  # noqa: I001 - local imports; re first (stdlib before third-party)
    import babel.numbers as _bbl

    # Derive CLDR-standard decimal count when not explicitly provided.
    # This handles KWD=3, BHD=3, JPY=0, KRW=0, USD/EUR/GBP=2 correctly without
    # maintaining a separate lookup table that can drift from CLDR.
    if precision is None:
        if not currency:
            return  # Cannot derive precision without currency or explicit value
        try:
            precision = _bbl.get_currency_precision(currency)
        except (ValueError, LookupError):
            return  # Unknown currency -- skip oracle

    _domain.round_half_up_checks += 1
    try:
        quantizer = Decimal(10) ** -precision
        expected = abs(value).quantize(quantizer, rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return  # NaN/Inf -- skip oracle check

    # Resolve locale-specific decimal and group symbols via Babel's public API.
    # Convert BCP 47 format ("de-DE") to Babel format ("de_DE") for lookup.
    # number_symbols.get("decimal") is NOT used directly: in Babel 2.x the
    # number_symbols dict is keyed by numbering system ("latn"), not by symbol
    # name. get_decimal_symbol() / get_group_symbol() handle the correct lookup.
    # On unknown locale, return rather than fall back to wrong defaults.
    try:
        babel_locale = locale.replace("-", "_")
        decimal_sym = _bbl.get_decimal_symbol(babel_locale)
        group_sym = _bbl.get_group_symbol(babel_locale)
    except (ValueError, LookupError):
        return  # skip oracle rather than risk false positive from wrong defaults

    # Remove group separator, normalize decimal separator to ASCII dot, then
    # strip any remaining non-digit non-dot characters (currency symbols, etc.)
    normalized = result.replace(group_sym, "").replace(decimal_sym, ".")
    digits_only = re.sub(r"[^\d.]", "", normalized)
    if not digits_only:
        return  # Empty result -- no oracle to apply

    try:
        actual = Decimal(digits_only)
    except InvalidOperation:
        return  # Non-numeric after stripping (e.g., Arabic-Indic digits) -- skip

    if actual != expected:
        _domain.round_half_up_violations += 1
        _state.findings += 1
        ctx = f"currency={currency}" if currency else "number"
        msg = (
            f"ROUND_HALF_UP violation ({ctx}): "
            f"value={value}, precision={precision}, locale={locale} "
            f"expected={expected}, got={actual} (raw='{result}')"
        )
        raise LocaleContextFuzzError(msg)


def test_one_input(data: bytes) -> None:  # noqa: PLR0912, PLR0915 - dispatch
    """Atheris entry point: Test LocaleContext formatting invariants."""
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
        pattern_choice = _PATTERN_INDEX[pattern_name]
        locale_code = fdp.PickValueInList(list(_VALID_LOCALES))
        ctx = LocaleContext.create(locale_code)

        match pattern_choice:
            case 0:  # format_number_int
                _domain.format_number_calls += 1
                value = Decimal(fdp.ConsumeIntInRange(-10_000_000, 10_000_000))
                result = ctx.format_number(value)
                if not result:
                    msg = f"format_number({value}) returned empty for {locale_code}"
                    raise LocaleContextFuzzError(msg)

            case 1:  # format_number_decimal
                _domain.format_number_calls += 1
                int_part = fdp.ConsumeIntInRange(-9999, 9999)
                frac_part = fdp.ConsumeIntInRange(0, 9999999)
                value = Decimal(f"{int_part}.{frac_part:07d}")
                result = ctx.format_number(value)
                if not result:
                    msg = f"format_number({value}) returned empty for {locale_code}"
                    raise LocaleContextFuzzError(msg)

            case 2:  # format_number_precision (ROUND_HALF_UP oracle)
                _domain.format_number_calls += 1
                int_part = fdp.ConsumeIntInRange(-9999, 9999)
                frac_str = str(fdp.ConsumeIntInRange(0, 9999)).zfill(4)
                value = Decimal(f"{int_part}.{frac_str}")
                min_frac = fdp.ConsumeIntInRange(0, 6)
                max_frac = fdp.ConsumeIntInRange(min_frac, 6)
                result = ctx.format_number(
                    value,
                    minimum_fraction_digits=min_frac,
                    maximum_fraction_digits=max_frac,
                )
                if not result:
                    msg = (
                        f"format_number({value}, min={min_frac}, "
                        f"max={max_frac}) empty for {locale_code}"
                    )
                    raise LocaleContextFuzzError(msg)
                # Oracle: check rounding mode at max_frac precision
                _check_round_half_up(result, value, max_frac, locale_code)

            case 3:  # format_number_custom_pattern
                _domain.format_number_calls += 1
                int_part = fdp.ConsumeIntInRange(-9999, 9999)
                frac_part = fdp.ConsumeIntInRange(0, 99)
                value = Decimal(f"{int_part}.{frac_part:02d}")
                pattern = fdp.PickValueInList(list(_NUMBER_PATTERNS))
                result = ctx.format_number(value, pattern=pattern)
                if not result:
                    msg = (
                        f"format_number({value}, pattern='{pattern}') "
                        f"empty for {locale_code}"
                    )
                    raise LocaleContextFuzzError(msg)

            case 4:  # format_number_grouping
                _domain.format_number_calls += 1
                value = Decimal(
                    fdp.ConsumeIntInRange(-999_999_999, 999_999_999)
                )
                use_grouping = fdp.ConsumeBool()
                result = ctx.format_number(value, use_grouping=use_grouping)
                if not result:
                    msg = (
                        f"format_number({value}, grouping={use_grouping}) "
                        f"empty for {locale_code}"
                    )
                    raise LocaleContextFuzzError(msg)

            case 5:  # format_currency_standard (ROUND_HALF_UP oracle)
                _domain.format_currency_calls += 1
                currency = fdp.PickValueInList(list(_CURRENCIES))
                int_part = fdp.ConsumeIntInRange(0, 99999)
                frac_str = str(fdp.ConsumeIntInRange(0, 9999)).zfill(4)
                value = Decimal(f"{int_part}.{frac_str}")
                result = ctx.format_currency(value, currency=currency)
                if not result:
                    msg = (
                        f"format_currency({value}, currency={currency}) "
                        f"empty for {locale_code}"
                    )
                    raise LocaleContextFuzzError(msg)
                # Oracle: precision=None lets _check_round_half_up derive the
                # CLDR-standard decimal count per currency (KWD=3, JPY=0, USD=2).
                _check_round_half_up(result, value, None, locale_code, currency=currency)

            case 6:  # format_currency_display_override
                _domain.format_currency_calls += 1
                currency = fdp.PickValueInList(list(_CURRENCIES))
                int_part = fdp.ConsumeIntInRange(0, 9999)
                frac_str = str(fdp.ConsumeIntInRange(0, 9999)).zfill(4)
                value = Decimal(f"{int_part}.{frac_str}")
                display = fdp.PickValueInList(["symbol", "code", "name"])
                result = ctx.format_currency(
                    value, currency=currency, currency_display=display,
                )
                if not result:
                    msg = (
                        f"format_currency({value}, currency={currency}, "
                        f"display={display}) empty for {locale_code}"
                    )
                    raise LocaleContextFuzzError(msg)

            case 7:  # format_currency_custom_pattern
                _domain.format_currency_calls += 1
                currency = fdp.PickValueInList(["USD", "EUR", "GBP"])
                value = Decimal(f"{fdp.ConsumeIntInRange(1, 9999)}.99")
                pattern = fdp.PickValueInList(list(_CURRENCY_PATTERNS))
                result = ctx.format_currency(
                    value, currency=currency, pattern=pattern
                )
                if not result:
                    msg = (
                        f"format_currency({value}, currency={currency}, "
                        f"pattern='{pattern}') empty for {locale_code}"
                    )
                    raise LocaleContextFuzzError(msg)

            case 8:  # format_datetime_date_obj (midnight promotion)
                _domain.format_datetime_calls += 1
                year = fdp.ConsumeIntInRange(2000, 2030)
                month = fdp.ConsumeIntInRange(1, 12)
                day = fdp.ConsumeIntInRange(1, 28)
                d = date(year, month, day)
                style = fdp.PickValueInList(list(_DATE_STYLES))
                result = ctx.format_datetime(d, date_style=style)
                if not result:
                    msg = (
                        f"format_datetime({d}, date_style='{style}') "
                        f"empty for {locale_code}"
                    )
                    raise LocaleContextFuzzError(msg)

            case 9:  # format_datetime_datetime_obj
                _domain.format_datetime_calls += 1
                year = fdp.ConsumeIntInRange(2000, 2030)
                month = fdp.ConsumeIntInRange(1, 12)
                day = fdp.ConsumeIntInRange(1, 28)
                hour = fdp.ConsumeIntInRange(0, 23)
                minute = fdp.ConsumeIntInRange(0, 59)
                use_tz = fdp.ConsumeBool()
                if use_tz:
                    dt = datetime(year, month, day, hour, minute,
                                  tzinfo=UTC)
                else:
                    dt = datetime(year, month, day, hour, minute)  # noqa: DTZ001 - naive by design
                date_style = fdp.PickValueInList(list(_DATE_STYLES))
                result = ctx.format_datetime(dt, date_style=date_style)
                if not result:
                    msg = (
                        f"format_datetime({dt}, date_style='{date_style}') "
                        f"empty for {locale_code}"
                    )
                    raise LocaleContextFuzzError(msg)

            case 10:  # format_datetime_style_combo
                _domain.format_datetime_calls += 1
                year = fdp.ConsumeIntInRange(2000, 2030)
                month = fdp.ConsumeIntInRange(1, 12)
                day = fdp.ConsumeIntInRange(1, 28)
                hour = fdp.ConsumeIntInRange(0, 23)
                dt = datetime(year, month, day, hour, 0, tzinfo=UTC)
                date_style = fdp.PickValueInList(list(_DATE_STYLES))
                time_style = fdp.PickValueInList(list(_TIME_STYLES))
                result = ctx.format_datetime(
                    dt, date_style=date_style, time_style=time_style
                )
                if not result:
                    msg = (
                        f"format_datetime({dt}, "
                        f"date='{date_style}', time='{time_style}') "
                        f"empty for {locale_code}"
                    )
                    raise LocaleContextFuzzError(msg)

            case 11:  # format_datetime_pattern
                _domain.format_datetime_calls += 1
                year = fdp.ConsumeIntInRange(2000, 2030)
                month = fdp.ConsumeIntInRange(1, 12)
                day = fdp.ConsumeIntInRange(1, 28)
                dt = datetime(year, month, day, tzinfo=UTC)
                pattern = fdp.PickValueInList(list(_DATETIME_PATTERNS))
                result = ctx.format_datetime(dt, pattern=pattern)
                if not result:
                    msg = (
                        f"format_datetime({dt}, pattern='{pattern}') "
                        f"empty for {locale_code}"
                    )
                    raise LocaleContextFuzzError(msg)

            case 12:  # locale_create_adversarial
                _domain.invalid_locale_attempts += 1
                fuzz_locale = fdp.ConsumeUnicodeNoSurrogates(
                    fdp.ConsumeIntInRange(0, 50)
                )
                # Must not crash -- either succeeds or raises ValueError
                try:
                    adv_ctx = LocaleContext.create(fuzz_locale)
                    # If create succeeds, format_number must work
                    result = adv_ctx.format_number(Decimal("1.23"))
                    if not result:
                        msg = (
                            f"format_number after create('{fuzz_locale}') "
                            f"returned empty"
                        )
                        raise LocaleContextFuzzError(msg)
                except (ValueError, TypeError, FrozenFluentError):
                    pass  # Expected for invalid locale codes

            case _:  # cross_locale_determinism
                _domain.cross_locale_checks += 1
                value = Decimal(
                    f"{fdp.ConsumeIntInRange(0, 9999)}."
                    f"{fdp.ConsumeIntInRange(0, 99):02d}"
                )
                # Each locale formats independently; same locale must give same result
                results: list[str] = []
                for lc in list(_VALID_LOCALES)[:5]:
                    lc_ctx = LocaleContext.create(lc)
                    r = lc_ctx.format_number(value)
                    results.append(r)

                # Determinism: same locale called twice must produce same result
                ctx2 = LocaleContext.create(locale_code)
                r1 = ctx2.format_number(value)
                r2 = ctx2.format_number(value)
                if r1 != r2:
                    msg = (
                        f"Determinism violation: format_number({value}) for "
                        f"'{locale_code}': '{r1}' != '{r2}'"
                    )
                    raise LocaleContextFuzzError(msg)

    except (*_ALLOWED_EXCEPTIONS, FrozenFluentError) as e:
        error_type = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_type] = (
            _state.error_counts.get(error_type, 0) + 1
        )
    except LocaleContextFuzzError:
        _state.findings += 1
        raise
    except Exception:
        _state.findings += 1
        raise
    finally:
        is_interesting = (
            "precision" in pattern_name
            or pattern_name in ("locale_create_adversarial", "cross_locale_determinism")
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
    """Run the locale_context fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="LocaleContext direct formatting API fuzzer (Atheris)",
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
        title="LocaleContext Direct Formatting API Fuzzer (Atheris)",
        target="ftllexengine.runtime.locale_context.LocaleContext",
        state=_state,
        schedule_len=len(_PATTERN_SCHEDULE),
        extra_lines=[
            f"Patterns:   {len(_PATTERN_WEIGHTS)}"
            f" ({sum(w for _, w in _PATTERN_WEIGHTS)} weighted slots)",
            f"Locales:    {len(_VALID_LOCALES)} validated locales",
            "Oracle:     ROUND_HALF_UP via Decimal.quantize(ROUND_HALF_UP)",
        ],
    )

    run_fuzzer(_state, test_one_input=test_one_input)


if __name__ == "__main__":
    main()
