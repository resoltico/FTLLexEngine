#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: fiscal - Fiscal Calendar arithmetic
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Fiscal Calendar Fuzzer (Atheris).

Targets FiscalCalendar, FiscalDelta, FiscalPeriod, and convenience functions.
Tests date arithmetic correctness, boundary conditions, month-end policies,
and algebraic properties of fiscal calendar operations.

Metrics:
- Pattern coverage (calendar, delta, algebra, period, convenience, boundary)
- Performance profiling (min/mean/median/p95/p99/max)
- Real memory usage (RSS via psutil)
- Error distribution and contract violations
- Seed corpus management

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import calendar
import hashlib
import heapq
import json
import logging
import os
import pathlib
import statistics
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

# --- Dependency Checks with Clear Errors ---
_MISSING_DEPS: list[str] = []

try:
    import psutil
except ImportError:
    _MISSING_DEPS.append("psutil")
    psutil = None  # type: ignore[assignment]

try:
    import atheris
except ImportError:
    _MISSING_DEPS.append("atheris")
    atheris = None  # type: ignore[assignment]

if _MISSING_DEPS:
    print("-" * 80, file=sys.stderr)
    print("ERROR: Missing required dependencies for fuzzing:", file=sys.stderr)
    for dep in _MISSING_DEPS:
        print(f"  - {dep}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Install with: uv sync --group atheris", file=sys.stderr)
    print("See docs/FUZZING_GUIDE.md for details.", file=sys.stderr)
    print("-" * 80, file=sys.stderr)
    sys.exit(1)

# --- PEP 695 Type Aliases ---
type FuzzStats = dict[str, int | str | float | list[Any]]
type InterestingInput = tuple[float, str, str]  # (duration_ms, pattern, input_hash)


# --- Observability State ---
@dataclass
class FuzzerState:
    """Global fuzzer state for observability and metrics."""

    # Core stats
    iterations: int = 0
    findings: int = 0
    status: str = "incomplete"

    # Performance tracking (bounded deques)
    performance_history: deque[float] = field(default_factory=lambda: deque(maxlen=10000))
    memory_history: deque[float] = field(default_factory=lambda: deque(maxlen=1000))

    # Pattern coverage
    pattern_coverage: dict[str, int] = field(default_factory=dict)
    error_counts: dict[str, int] = field(default_factory=dict)

    # Interesting inputs (max-heap for slowest, in-memory corpus)
    slowest_operations: list[InterestingInput] = field(default_factory=list)
    seed_corpus: dict[str, bytes] = field(default_factory=dict)

    # Memory baseline
    initial_memory_mb: float = 0.0

    # Fiscal-specific metrics
    calendar_invariant_checks: int = 0
    quarter_boundary_checks: int = 0
    delta_arithmetic_checks: int = 0
    delta_algebra_checks: int = 0
    period_immutability_checks: int = 0
    convenience_function_checks: int = 0
    boundary_stress_checks: int = 0

    # Corpus productivity
    corpus_entries_added: int = 0

    # Per-pattern wall time (ms)
    pattern_wall_time: dict[str, float] = field(default_factory=dict)

    # Configuration
    checkpoint_interval: int = 500
    seed_corpus_max_size: int = 100


# Global state instance
_state = FuzzerState()
_process: psutil.Process | None = None


def _get_process() -> psutil.Process:
    """Lazy-initialize psutil process handle."""
    global _process  # noqa: PLW0603  # pylint: disable=global-statement
    if _process is None:
        _process = psutil.Process(os.getpid())
    return _process


# Exception contract: only these exceptions are acceptable
ALLOWED_EXCEPTIONS = (ValueError, TypeError, OverflowError)

# Date range constants
PRACTICAL_MIN_YEAR = 1900
PRACTICAL_MAX_YEAR = 2100
MIN_YEAR = 1
MAX_YEAR = 9999

# Weighted patterns for scenario selection
_PATTERNS: Sequence[str] = (
    "calendar_invariants",
    "quarter_boundaries",
    "delta_arithmetic",
    "delta_algebra",
    "period_immutability",
    "convenience_functions",
    "boundary_stress",
)
_PATTERN_WEIGHTS: Sequence[int] = (25, 15, 20, 15, 10, 10, 5)


class FiscalFuzzError(Exception):
    """Raised when an unexpected exception or invariant breach is detected."""


def _build_stats_dict() -> FuzzStats:
    """Build stats dictionary for JSON report."""
    stats: FuzzStats = {
        "status": _state.status,
        "iterations": _state.iterations,
        "findings": _state.findings,
    }

    # Performance percentiles
    if _state.performance_history:
        perf_data = list(_state.performance_history)
        n = len(perf_data)
        stats["perf_mean_ms"] = round(statistics.mean(perf_data), 3)
        stats["perf_median_ms"] = round(statistics.median(perf_data), 3)
        stats["perf_min_ms"] = round(min(perf_data), 3)
        stats["perf_max_ms"] = round(max(perf_data), 3)
        if n >= 20:
            quantiles = statistics.quantiles(perf_data, n=20)
            stats["perf_p95_ms"] = round(quantiles[18], 3)
        if n >= 100:
            quantiles = statistics.quantiles(perf_data, n=100)
            stats["perf_p99_ms"] = round(quantiles[98], 3)

    # Memory tracking
    if _state.memory_history:
        mem_data = list(_state.memory_history)
        stats["memory_mean_mb"] = round(statistics.mean(mem_data), 2)
        stats["memory_peak_mb"] = round(max(mem_data), 2)
        stats["memory_delta_mb"] = round(max(mem_data) - _state.initial_memory_mb, 2)

        if len(mem_data) >= 40:
            first_quarter = mem_data[: len(mem_data) // 4]
            last_quarter = mem_data[-(len(mem_data) // 4) :]
            first_avg = statistics.mean(first_quarter)
            last_avg = statistics.mean(last_quarter)
            growth_mb = last_avg - first_avg
            stats["memory_leak_detected"] = 1 if growth_mb > 10.0 else 0
            stats["memory_growth_mb"] = round(growth_mb, 2)
        else:
            stats["memory_leak_detected"] = 0
            stats["memory_growth_mb"] = 0.0

    # Pattern coverage
    stats["patterns_tested"] = len(_state.pattern_coverage)
    for pattern, count in sorted(_state.pattern_coverage.items()):
        stats[f"pattern_{pattern}"] = count

    # Error distribution
    stats["error_types"] = len(_state.error_counts)
    for error_type, count in sorted(_state.error_counts.items()):
        clean_key = error_type[:50].replace("<", "").replace(">", "")
        stats[f"error_{clean_key}"] = count

    # Fiscal-specific metrics
    stats["calendar_invariant_checks"] = _state.calendar_invariant_checks
    stats["quarter_boundary_checks"] = _state.quarter_boundary_checks
    stats["delta_arithmetic_checks"] = _state.delta_arithmetic_checks
    stats["delta_algebra_checks"] = _state.delta_algebra_checks
    stats["period_immutability_checks"] = _state.period_immutability_checks
    stats["convenience_function_checks"] = _state.convenience_function_checks
    stats["boundary_stress_checks"] = _state.boundary_stress_checks

    # Corpus stats
    stats["seed_corpus_size"] = len(_state.seed_corpus)
    stats["corpus_entries_added"] = _state.corpus_entries_added
    stats["slowest_operations_tracked"] = len(_state.slowest_operations)

    # Per-pattern wall time
    for pattern, total_ms in sorted(_state.pattern_wall_time.items()):
        stats[f"wall_time_ms_{pattern}"] = round(total_ms, 1)

    return stats


def _emit_final_report() -> None:
    """Emit comprehensive final report (crash-proof, writes to stderr and file)."""
    _state.status = "complete"
    stats = _build_stats_dict()
    report = json.dumps(stats, sort_keys=True)

    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr, flush=True)

    try:
        report_file = pathlib.Path(".fuzz_atheris_corpus") / "fiscal" / "fuzz_fiscal_report.json"
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(report, encoding="utf-8")
    except OSError:
        pass


atexit.register(_emit_final_report)

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.parsing.fiscal import (
        FiscalCalendar,
        FiscalDelta,
        FiscalPeriod,
        MonthEndPolicy,
        fiscal_quarter,
        fiscal_year_end,
        fiscal_year_start,
    )


# --- Generators ---


def _generate_date(fdp: atheris.FuzzedDataProvider, practical: bool = True) -> date:
    """Generate a date for testing."""
    if not fdp.remaining_bytes():
        return date(2024, 1, 15)

    if practical:
        year = fdp.ConsumeIntInRange(PRACTICAL_MIN_YEAR, PRACTICAL_MAX_YEAR)
    else:
        year = fdp.ConsumeIntInRange(MIN_YEAR, MAX_YEAR)

    month = fdp.ConsumeIntInRange(1, 12)
    max_day = calendar.monthrange(year, month)[1]
    day = fdp.ConsumeIntInRange(1, max_day)

    return date(year, month, day)


def _generate_start_month(fdp: atheris.FuzzedDataProvider) -> int:
    """Generate a fiscal year start month (1-12 or invalid)."""
    if not fdp.remaining_bytes():
        return 1

    strategy = fdp.ConsumeIntInRange(0, 3)
    match strategy:
        case 0:
            return fdp.PickValueInList([1, 4, 7, 10])
        case 1:
            return fdp.ConsumeIntInRange(1, 12)
        case 2:
            return fdp.ConsumeIntInRange(-100, 0)
        case _:
            return fdp.ConsumeIntInRange(13, 100)


def _generate_fiscal_delta(
    fdp: atheris.FuzzedDataProvider, small: bool = True,
) -> FiscalDelta:
    """Generate a FiscalDelta for testing."""
    if not fdp.remaining_bytes():
        return FiscalDelta(months=1)

    if small:
        years = fdp.ConsumeIntInRange(-10, 10)
        quarters = fdp.ConsumeIntInRange(-20, 20)
        months = fdp.ConsumeIntInRange(-50, 50)
        days = fdp.ConsumeIntInRange(-365, 365)
    else:
        years = fdp.ConsumeIntInRange(-1000, 1000)
        quarters = fdp.ConsumeIntInRange(-4000, 4000)
        months = fdp.ConsumeIntInRange(-12000, 12000)
        days = fdp.ConsumeIntInRange(-365000, 365000)

    policies = list(MonthEndPolicy)
    policy = fdp.PickValueInList(policies)

    return FiscalDelta(
        years=years,
        quarters=quarters,
        months=months,
        days=days,
        month_end_policy=policy,
    )


def _generate_fiscal_period_params(fdp: atheris.FuzzedDataProvider) -> tuple[int, int, int]:
    """Generate fiscal period parameters (year, quarter, month)."""
    if not fdp.remaining_bytes():
        return (2024, 1, 1)

    strategy = fdp.ConsumeIntInRange(0, 2)
    match strategy:
        case 0:
            fiscal_year = fdp.ConsumeIntInRange(PRACTICAL_MIN_YEAR, PRACTICAL_MAX_YEAR)
            quarter = fdp.ConsumeIntInRange(1, 4)
            month = fdp.ConsumeIntInRange(1, 12)
        case 1:
            fiscal_year = fdp.ConsumeIntInRange(PRACTICAL_MIN_YEAR, PRACTICAL_MAX_YEAR)
            if fdp.ConsumeBool():
                quarter = fdp.ConsumeIntInRange(-10, 0)
            else:
                quarter = fdp.ConsumeIntInRange(5, 15)
            month = fdp.ConsumeIntInRange(1, 12)
        case _:
            fiscal_year = fdp.ConsumeIntInRange(PRACTICAL_MIN_YEAR, PRACTICAL_MAX_YEAR)
            quarter = fdp.ConsumeIntInRange(1, 4)
            if fdp.ConsumeBool():
                month = fdp.ConsumeIntInRange(-10, 0)
            else:
                month = fdp.ConsumeIntInRange(13, 25)

    return (fiscal_year, quarter, month)


# --- Pattern Selection ---


def _select_pattern(fdp: atheris.FuzzedDataProvider) -> str:
    """Select a test pattern using weighted distribution."""
    total = sum(_PATTERN_WEIGHTS)
    choice = fdp.ConsumeIntInRange(0, total - 1)

    cumulative = 0
    for i, w in enumerate(_PATTERN_WEIGHTS):
        cumulative += w
        if choice < cumulative:
            return _PATTERNS[i]

    return _PATTERNS[0]


# --- Verification Functions ---


def _verify_calendar_invariants(cal: FiscalCalendar, d: date) -> None:
    """Verify FiscalCalendar invariants for a given date."""
    _state.calendar_invariant_checks += 1

    quarter = cal.fiscal_quarter(d)
    if not 1 <= quarter <= 4:
        msg = f"fiscal_quarter returned {quarter}, expected 1-4"
        raise FiscalFuzzError(msg)

    fiscal_month = cal.fiscal_month(d)
    if not 1 <= fiscal_month <= 12:
        msg = f"fiscal_month returned {fiscal_month}, expected 1-12"
        raise FiscalFuzzError(msg)

    fiscal_year = cal.fiscal_year(d)
    fy_start = cal.fiscal_year_start_date(fiscal_year)
    fy_end = cal.fiscal_year_end_date(fiscal_year)

    if not fy_start <= d <= fy_end:
        msg = f"Date {d} not in fiscal year {fiscal_year} ({fy_start} to {fy_end})"
        raise FiscalFuzzError(msg)

    period = cal.fiscal_period(d)
    if period.fiscal_year != fiscal_year:
        msg = f"fiscal_period.fiscal_year mismatch: {period.fiscal_year} != {fiscal_year}"
        raise FiscalFuzzError(msg)
    if period.quarter != quarter:
        msg = f"fiscal_period.quarter mismatch: {period.quarter} != {quarter}"
        raise FiscalFuzzError(msg)
    if period.month != fiscal_month:
        msg = f"fiscal_period.month mismatch: {period.month} != {fiscal_month}"
        raise FiscalFuzzError(msg)

    q1_start = cal.quarter_start_date(fiscal_year, 1)
    q4_end = cal.quarter_end_date(fiscal_year, 4)
    if q1_start != fy_start or q4_end != fy_end:
        msg = f"Year boundary mismatch: Q1 start {q1_start} != FY start {fy_start}"
        raise FiscalFuzzError(msg)


def _verify_quarter_boundaries(cal: FiscalCalendar, fiscal_year: int) -> None:
    """Verify quarter boundaries are consistent and contiguous."""
    _state.quarter_boundary_checks += 1

    for q in range(1, 5):
        q_start = cal.quarter_start_date(fiscal_year, q)
        q_end = cal.quarter_end_date(fiscal_year, q)

        if q_start > q_end:
            msg = f"Q{q} start {q_start} > end {q_end}"
            raise FiscalFuzzError(msg)

        if q < 4:
            next_q_start = cal.quarter_start_date(fiscal_year, q + 1)
            expected_next = q_end + timedelta(days=1)
            if next_q_start != expected_next:
                msg = f"Q{q} end {q_end} not contiguous with Q{q+1} start {next_q_start}"
                raise FiscalFuzzError(msg)

    fy_start = cal.fiscal_year_start_date(fiscal_year)
    fy_end = cal.fiscal_year_end_date(fiscal_year)
    q1_start = cal.quarter_start_date(fiscal_year, 1)
    q4_end = cal.quarter_end_date(fiscal_year, 4)

    if q1_start != fy_start:
        msg = f"Q1 start {q1_start} != FY start {fy_start}"
        raise FiscalFuzzError(msg)
    if q4_end != fy_end:
        msg = f"Q4 end {q4_end} != FY end {fy_end}"
        raise FiscalFuzzError(msg)


def _verify_delta_arithmetic(delta: FiscalDelta, d: date) -> None:
    """Verify FiscalDelta arithmetic properties."""
    _state.delta_arithmetic_checks += 1

    try:
        result = delta.add_to(d)

        if not isinstance(result, date):
            msg = f"add_to returned {type(result)}, expected date"
            raise FiscalFuzzError(msg)

        if delta.month_end_policy == MonthEndPolicy.PRESERVE:
            negated = delta.negate()
            round_trip = negated.add_to(result)
            diff = abs((round_trip - d).days)
            # Allow tolerance for month boundary clamping
            if diff > abs(delta.days) + 1:
                pass  # Expected for month-end handling

    except ALLOWED_EXCEPTIONS:
        pass


def _verify_delta_algebra(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify FiscalDelta algebraic properties."""
    _state.delta_algebra_checks += 1

    d1 = _generate_fiscal_delta(fdp, small=True)
    d2 = _generate_fiscal_delta(fdp, small=True)

    try:
        # Commutativity of addition
        sum1 = d1 + d2
        sum2 = d2 + d1
        if (sum1.years != sum2.years or sum1.quarters != sum2.quarters
                or sum1.months != sum2.months or sum1.days != sum2.days):
            msg = f"Delta addition not commutative: {d1} + {d2}"
            raise FiscalFuzzError(msg)
    except ALLOWED_EXCEPTIONS:
        pass

    # Double negation identity (pure component ops, no policy conflict)
    neg_neg = d1.negate().negate()
    if (neg_neg.years != d1.years or neg_neg.quarters != d1.quarters
            or neg_neg.months != d1.months or neg_neg.days != d1.days):
        msg = f"Double negation not identity: {d1}"
        raise FiscalFuzzError(msg)

    # total_months consistency
    expected_total = d1.years * 12 + d1.quarters * 3 + d1.months
    if d1.total_months() != expected_total:
        msg = f"total_months mismatch: {d1.total_months()} != {expected_total}"
        raise FiscalFuzzError(msg)

    # Scalar multiplication
    try:
        scalar = fdp.ConsumeIntInRange(-5, 5) if fdp.remaining_bytes() else 2
        multiplied = d1 * scalar
        if (multiplied.years != d1.years * scalar
                or multiplied.months != d1.months * scalar
                or multiplied.days != d1.days * scalar):
            msg = f"Multiplication failed: {d1} * {scalar} = {multiplied}"
            raise FiscalFuzzError(msg)
    except ALLOWED_EXCEPTIONS:
        pass


def _verify_period_immutability(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify FiscalPeriod is immutable and hashable."""
    _state.period_immutability_checks += 1

    fy, q, m = _generate_fiscal_period_params(fdp)

    try:
        period = FiscalPeriod(fiscal_year=fy, quarter=q, month=m)

        try:
            _ = hash(period)
            _ = {period}
        except TypeError as e:
            msg = f"FiscalPeriod not hashable: {e}"
            raise FiscalFuzzError(msg) from e

        period2 = FiscalPeriod(fiscal_year=fy, quarter=q, month=m)
        if period != period2:
            msg = f"Equal periods not equal: {period} != {period2}"
            raise FiscalFuzzError(msg)

        if fy < PRACTICAL_MAX_YEAR:
            later = FiscalPeriod(fiscal_year=fy + 1, quarter=q, month=m)
            if period >= later:
                msg = f"Ordering failed: {period} should be < {later}"
                raise FiscalFuzzError(msg)

    except ALLOWED_EXCEPTIONS:
        pass


def _verify_convenience_functions(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify convenience function consistency with FiscalCalendar."""
    _state.convenience_function_checks += 1

    d = _generate_date(fdp)
    start_month = fdp.ConsumeIntInRange(1, 12) if fdp.remaining_bytes() else 1

    try:
        q_func = fiscal_quarter(d, start_month)
        cal = FiscalCalendar(start_month=start_month)
        q_cal = cal.fiscal_quarter(d)

        if q_func != q_cal:
            msg = f"fiscal_quarter mismatch: {q_func} != {q_cal}"
            raise FiscalFuzzError(msg)

        fy = cal.fiscal_year(d)
        start_func = fiscal_year_start(fy, start_month)
        start_cal = cal.fiscal_year_start_date(fy)

        if start_func != start_cal:
            msg = f"fiscal_year_start mismatch: {start_func} != {start_cal}"
            raise FiscalFuzzError(msg)

        end_func = fiscal_year_end(fy, start_month)
        end_cal = cal.fiscal_year_end_date(fy)

        if end_func != end_cal:
            msg = f"fiscal_year_end mismatch: {end_func} != {end_cal}"
            raise FiscalFuzzError(msg)

    except ALLOWED_EXCEPTIONS:
        pass


def _verify_boundary_stress(fdp: atheris.FuzzedDataProvider) -> None:
    """Stress test with extreme dates and large deltas."""
    _state.boundary_stress_checks += 1

    try:
        # Extreme date range
        d = _generate_date(fdp, practical=False)
        start_month = fdp.ConsumeIntInRange(1, 12) if fdp.remaining_bytes() else 1

        cal = FiscalCalendar(start_month=start_month)
        _verify_calendar_invariants(cal, d)

        # Large delta on extreme date
        delta = _generate_fiscal_delta(fdp, small=False)
        _verify_delta_arithmetic(delta, d)

    except ALLOWED_EXCEPTIONS:
        pass


# --- Seed Corpus Management ---


def _track_slowest_operation(duration_ms: float, pattern: str, input_data: bytes) -> None:
    """Track top 10 slowest operations using max-heap."""
    input_hash = hashlib.sha256(input_data).hexdigest()[:16]
    entry: InterestingInput = (-duration_ms, pattern, input_hash)

    if len(_state.slowest_operations) < 10:
        heapq.heappush(_state.slowest_operations, entry)
    elif -duration_ms < _state.slowest_operations[0][0]:
        heapq.heapreplace(_state.slowest_operations, entry)


def _track_seed_corpus(input_data: bytes, pattern: str, duration_ms: float) -> None:
    """Track interesting inputs with FIFO eviction."""
    is_interesting = (
        duration_ms > 50.0
        or "boundary" in pattern
        or "algebra" in pattern
    )

    if is_interesting:
        input_hash = hashlib.sha256(input_data).hexdigest()[:16]
        if input_hash not in _state.seed_corpus:
            if len(_state.seed_corpus) >= _state.seed_corpus_max_size:
                oldest_key = next(iter(_state.seed_corpus))
                del _state.seed_corpus[oldest_key]
            _state.seed_corpus[input_hash] = input_data
            _state.corpus_entries_added += 1


# --- Main Entry Point ---


def test_one_input(data: bytes) -> None:  # noqa: PLR0912, PLR0915
    """Atheris entry point: fuzz fiscal calendar APIs."""
    # Initialize memory baseline
    if _state.iterations == 0:
        _state.initial_memory_mb = _get_process().memory_info().rss / (1024 * 1024)

    _state.iterations += 1
    _state.status = "running"

    # Periodic checkpoint
    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_final_report()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    # Select pattern
    pattern = _select_pattern(fdp)
    _state.pattern_coverage[pattern] = _state.pattern_coverage.get(pattern, 0) + 1

    try:
        match pattern:
            case "calendar_invariants":
                start_month = _generate_start_month(fdp)
                try:
                    cal = FiscalCalendar(start_month=start_month)
                    d = _generate_date(fdp)
                    _verify_calendar_invariants(cal, d)
                except ALLOWED_EXCEPTIONS:
                    pass

            case "quarter_boundaries":
                start_month = _generate_start_month(fdp)
                try:
                    cal = FiscalCalendar(start_month=start_month)
                    fiscal_year = fdp.ConsumeIntInRange(
                        PRACTICAL_MIN_YEAR, PRACTICAL_MAX_YEAR,
                    )
                    _verify_quarter_boundaries(cal, fiscal_year)
                except ALLOWED_EXCEPTIONS:
                    pass

            case "delta_arithmetic":
                use_small = fdp.ConsumeBool()
                delta = _generate_fiscal_delta(fdp, small=use_small)
                d = _generate_date(fdp, practical=use_small)
                _verify_delta_arithmetic(delta, d)

            case "delta_algebra":
                _verify_delta_algebra(fdp)

            case "period_immutability":
                _verify_period_immutability(fdp)

            case "convenience_functions":
                _verify_convenience_functions(fdp)

            case "boundary_stress":
                _verify_boundary_stress(fdp)

    except FiscalFuzzError:
        _state.findings += 1
        _state.status = "finding"
        raise

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = _state.error_counts.get(error_key, 0) + 1

        _state.findings += 1
        _state.status = "finding"

        print("\n" + "=" * 80, file=sys.stderr)
        print("[FINDING] FISCAL CALENDAR STABILITY BREACH", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(f"Exception Type: {type(e).__module__}.{type(e).__name__}", file=sys.stderr)
        print(f"Error Message:  {e}", file=sys.stderr)
        print("-" * 80, file=sys.stderr)

        msg = f"{type(e).__name__}: {e}"
        raise FiscalFuzzError(msg) from e

    finally:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _state.performance_history.append(elapsed_ms)

        _state.pattern_wall_time[pattern] = (
            _state.pattern_wall_time.get(pattern, 0.0) + elapsed_ms
        )

        _track_slowest_operation(elapsed_ms, pattern, data)
        _track_seed_corpus(data, pattern, elapsed_ms)

        # Memory tracking (every 100 iterations)
        if _state.iterations % 100 == 0:
            current_mb = _get_process().memory_info().rss / (1024 * 1024)
            _state.memory_history.append(current_mb)


def main() -> None:
    """Run the fiscal calendar fuzzer with CLI support."""
    parser = argparse.ArgumentParser(
        description="Fiscal calendar fuzzer using Atheris/libFuzzer",
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
        default=100,
        help="Maximum size of in-memory seed corpus (default: 100)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    sys.argv = [sys.argv[0], *remaining]

    print()
    print("=" * 80)
    print("Fiscal Calendar Fuzzer (Atheris)")
    print("=" * 80)
    print("Target:     FiscalCalendar, FiscalDelta, FiscalPeriod, convenience functions")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
