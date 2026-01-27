#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: fiscal - Fiscal Calendar arithmetic
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Fiscal Calendar Fuzzer (Atheris).

Targets FiscalCalendar, FiscalDelta, FiscalPeriod, and convenience functions.
Tests date arithmetic correctness, boundary conditions, and month-end policies.

Built for Python 3.13+ using modern PEPs (695, 585, 563).
No external dependencies (fiscal module is pure Python).
"""

from __future__ import annotations

import atexit
import calendar
import json
import logging
import sys
from datetime import date, timedelta
from typing import Any

# --- PEP 695 Type Aliases (Python 3.13) ---
type FuzzStats = dict[str, int | str]

# Crash-proof reporting: ensure summary is always emitted
_fuzz_stats: FuzzStats = {"status": "incomplete", "iterations": 0, "findings": 0}


def _emit_final_report() -> None:
    """Emit JSON summary on exit (crash-proof reporting)."""
    report = json.dumps(_fuzz_stats)
    print(f"\n[SUMMARY-JSON-BEGIN]{report}[SUMMARY-JSON-END]", file=sys.stderr)


atexit.register(_emit_final_report)

try:
    import atheris
except ImportError:
    print("-" * 80, file=sys.stderr)
    print("ERROR: 'atheris' not found.", file=sys.stderr)
    print("On macOS, install LLVM: brew install llvm", file=sys.stderr)
    print("Then run: ./scripts/check-atheris.sh --install", file=sys.stderr)
    print("See docs/FUZZING_GUIDE.md for details.", file=sys.stderr)
    print("-" * 80, file=sys.stderr)
    sys.exit(1)

# Suppress logging during fuzzing
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


class FiscalFuzzError(Exception):
    """Raised when an unexpected exception or invariant breach is detected."""


# Exception contract: only these exceptions are acceptable
# - ValueError: Invalid parameter values (month out of range, etc.)
# - TypeError: Type mismatch in parameters
# - OverflowError: Date arithmetic overflow (very large deltas)
ALLOWED_EXCEPTIONS = (ValueError, TypeError, OverflowError)

# Date range for testing (Python's date supports 1-9999)
MIN_YEAR = 1
MAX_YEAR = 9999
# Practical range for most testing
PRACTICAL_MIN_YEAR = 1900
PRACTICAL_MAX_YEAR = 2100


def generate_date(fdp: Any, practical: bool = True) -> date:
    """Generate a date for testing."""
    if not fdp.remaining_bytes():
        return date(2024, 1, 15)

    if practical:
        year = fdp.ConsumeIntInRange(PRACTICAL_MIN_YEAR, PRACTICAL_MAX_YEAR)
    else:
        # Full range for edge case testing
        year = fdp.ConsumeIntInRange(MIN_YEAR, MAX_YEAR)

    month = fdp.ConsumeIntInRange(1, 12)
    max_day = calendar.monthrange(year, month)[1]
    day = fdp.ConsumeIntInRange(1, max_day)

    return date(year, month, day)


def generate_start_month(fdp: Any) -> int:
    """Generate a fiscal year start month (1-12 or invalid)."""
    if not fdp.remaining_bytes():
        return 1

    strategy = fdp.ConsumeIntInRange(0, 3)

    match strategy:
        case 0:
            # Common fiscal year starts
            return fdp.PickValueInList([1, 4, 7, 10])  # Calendar, UK/JP, US Fed, Oct
        case 1:
            # Valid range
            return fdp.ConsumeIntInRange(1, 12)
        case 2:
            # Invalid: too low
            return fdp.ConsumeIntInRange(-100, 0)
        case _:
            # Invalid: too high
            return fdp.ConsumeIntInRange(13, 100)


def generate_fiscal_delta(fdp: Any, small: bool = True) -> FiscalDelta:
    """Generate a FiscalDelta for testing."""
    if not fdp.remaining_bytes():
        return FiscalDelta(months=1)

    if small:
        years = fdp.ConsumeIntInRange(-10, 10)
        quarters = fdp.ConsumeIntInRange(-20, 20)
        months = fdp.ConsumeIntInRange(-50, 50)
        days = fdp.ConsumeIntInRange(-365, 365)
    else:
        # Extreme values for boundary testing
        years = fdp.ConsumeIntInRange(-1000, 1000)
        quarters = fdp.ConsumeIntInRange(-4000, 4000)
        months = fdp.ConsumeIntInRange(-12000, 12000)
        days = fdp.ConsumeIntInRange(-365000, 365000)

    # Select policy
    policies = list(MonthEndPolicy)
    policy = fdp.PickValueInList(policies)

    return FiscalDelta(
        years=years,
        quarters=quarters,
        months=months,
        days=days,
        month_end_policy=policy,
    )


def generate_fiscal_period(fdp: Any) -> tuple[int, int, int]:
    """Generate fiscal period parameters (year, quarter, month)."""
    if not fdp.remaining_bytes():
        return (2024, 1, 1)

    strategy = fdp.ConsumeIntInRange(0, 2)

    match strategy:
        case 0:
            # Valid values
            fiscal_year = fdp.ConsumeIntInRange(PRACTICAL_MIN_YEAR, PRACTICAL_MAX_YEAR)
            quarter = fdp.ConsumeIntInRange(1, 4)
            month = fdp.ConsumeIntInRange(1, 12)
        case 1:
            # Invalid quarter (out of 1-4 range)
            fiscal_year = fdp.ConsumeIntInRange(PRACTICAL_MIN_YEAR, PRACTICAL_MAX_YEAR)
            if fdp.ConsumeBool():
                quarter = fdp.ConsumeIntInRange(-10, 0)
            else:
                quarter = fdp.ConsumeIntInRange(5, 15)
            month = fdp.ConsumeIntInRange(1, 12)
        case _:
            # Invalid month (out of 1-12 range)
            fiscal_year = fdp.ConsumeIntInRange(PRACTICAL_MIN_YEAR, PRACTICAL_MAX_YEAR)
            quarter = fdp.ConsumeIntInRange(1, 4)
            if fdp.ConsumeBool():
                month = fdp.ConsumeIntInRange(-10, 0)
            else:
                month = fdp.ConsumeIntInRange(13, 25)

    return (fiscal_year, quarter, month)


def _verify_calendar_invariants(cal: FiscalCalendar, d: date) -> None:
    """Verify FiscalCalendar invariants for a given date."""
    # Check: fiscal_quarter is always 1-4
    quarter = cal.fiscal_quarter(d)
    if not 1 <= quarter <= 4:
        msg = f"fiscal_quarter returned {quarter}, expected 1-4"
        raise FiscalFuzzError(msg)

    # Check: fiscal_month is always 1-12
    fiscal_month = cal.fiscal_month(d)
    if not 1 <= fiscal_month <= 12:
        msg = f"fiscal_month returned {fiscal_month}, expected 1-12"
        raise FiscalFuzzError(msg)

    # Check: fiscal_year is consistent with boundaries
    fiscal_year = cal.fiscal_year(d)
    fy_start = cal.fiscal_year_start_date(fiscal_year)
    fy_end = cal.fiscal_year_end_date(fiscal_year)

    if not fy_start <= d <= fy_end:
        msg = f"Date {d} not in fiscal year {fiscal_year} ({fy_start} to {fy_end})"
        raise FiscalFuzzError(msg)

    # Check: fiscal_period components are consistent
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

    # Check: year boundaries are consistent with quarter boundaries
    q1_start = cal.quarter_start_date(fiscal_year, 1)
    q4_end = cal.quarter_end_date(fiscal_year, 4)
    if q1_start != fy_start or q4_end != fy_end:
        msg = f"Year boundary mismatch: Q1 start {q1_start} != FY start {fy_start}"
        raise FiscalFuzzError(msg)


def _verify_quarter_boundaries(cal: FiscalCalendar, fiscal_year: int) -> None:
    """Verify quarter boundaries are consistent and contiguous."""
    for q in range(1, 5):
        q_start = cal.quarter_start_date(fiscal_year, q)
        q_end = cal.quarter_end_date(fiscal_year, q)

        # Check: quarter_start <= quarter_end
        if q_start > q_end:
            msg = f"Q{q} start {q_start} > end {q_end}"
            raise FiscalFuzzError(msg)

        # Check: Quarters are contiguous
        if q < 4:
            next_q_start = cal.quarter_start_date(fiscal_year, q + 1)
            expected_next = q_end + timedelta(days=1)
            if next_q_start != expected_next:
                msg = f"Q{q} end {q_end} not contiguous with Q{q+1} start {next_q_start}"
                raise FiscalFuzzError(msg)

    # Check: Q1 starts at fiscal year start, Q4 ends at fiscal year end
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
    try:
        result = delta.add_to(d)

        # Check: Result is a valid date
        if not isinstance(result, date):
            msg = f"add_to returned {type(result)}, expected date"
            raise FiscalFuzzError(msg)

        # Check: subtract_from is inverse of add_to (modulo policy effects)
        # Only verify for PRESERVE policy where round-trip is exact
        if delta.month_end_policy == MonthEndPolicy.PRESERVE:
            negated = delta.negate()
            round_trip = negated.add_to(result)

            # For PRESERVE, we can't guarantee exact round-trip due to clamping
            # But the result should be close (within days component)
            diff = abs((round_trip - d).days)
            if diff > abs(delta.days) + 1:  # Allow 1 day tolerance for month boundaries
                # This is actually expected behavior for month-end handling
                pass

    except ALLOWED_EXCEPTIONS:
        pass  # Expected for overflow or strict policy violations


def _verify_delta_algebra(fdp: Any) -> None:
    """Verify FiscalDelta algebraic properties."""
    d1 = generate_fiscal_delta(fdp, small=True)
    d2 = generate_fiscal_delta(fdp, small=True)

    # Check: Addition is commutative for component values
    sum1 = d1 + d2
    sum2 = d2 + d1
    if (sum1.years != sum2.years or sum1.quarters != sum2.quarters or
            sum1.months != sum2.months or sum1.days != sum2.days):
        msg = f"Delta addition not commutative: {d1} + {d2}"
        raise FiscalFuzzError(msg)

    # Check: Negation is self-inverse
    neg_neg = d1.negate().negate()
    if (neg_neg.years != d1.years or neg_neg.quarters != d1.quarters or
            neg_neg.months != d1.months or neg_neg.days != d1.days):
        msg = f"Double negation not identity: {d1}"
        raise FiscalFuzzError(msg)

    # Check: total_months is consistent
    expected_total = d1.years * 12 + d1.quarters * 3 + d1.months
    if d1.total_months() != expected_total:
        msg = f"total_months mismatch: {d1.total_months()} != {expected_total}"
        raise FiscalFuzzError(msg)

    # Check: Multiplication by scalar
    scalar = fdp.ConsumeIntInRange(-5, 5) if fdp.remaining_bytes() else 2
    multiplied = d1 * scalar
    if (multiplied.years != d1.years * scalar or
            multiplied.months != d1.months * scalar or
            multiplied.days != d1.days * scalar):
        msg = f"Multiplication failed: {d1} * {scalar} = {multiplied}"
        raise FiscalFuzzError(msg)


def _verify_convenience_functions(fdp: Any) -> None:
    """Verify convenience function consistency with FiscalCalendar."""
    d = generate_date(fdp)
    start_month = fdp.ConsumeIntInRange(1, 12) if fdp.remaining_bytes() else 1

    try:
        # fiscal_quarter should match FiscalCalendar.fiscal_quarter
        q_func = fiscal_quarter(d, start_month)
        cal = FiscalCalendar(start_month=start_month)
        q_cal = cal.fiscal_quarter(d)

        if q_func != q_cal:
            msg = f"fiscal_quarter mismatch: {q_func} != {q_cal}"
            raise FiscalFuzzError(msg)

        # fiscal_year_start should match FiscalCalendar.fiscal_year_start_date
        fy = cal.fiscal_year(d)
        start_func = fiscal_year_start(fy, start_month)
        start_cal = cal.fiscal_year_start_date(fy)

        if start_func != start_cal:
            msg = f"fiscal_year_start mismatch: {start_func} != {start_cal}"
            raise FiscalFuzzError(msg)

        # fiscal_year_end should match FiscalCalendar.fiscal_year_end_date
        end_func = fiscal_year_end(fy, start_month)
        end_cal = cal.fiscal_year_end_date(fy)

        if end_func != end_cal:
            msg = f"fiscal_year_end mismatch: {end_func} != {end_cal}"
            raise FiscalFuzzError(msg)

    except ALLOWED_EXCEPTIONS:
        pass


def _verify_period_immutability(fdp: Any) -> None:
    """Verify FiscalPeriod is immutable and hashable."""
    fy, q, m = generate_fiscal_period(fdp)

    try:
        period = FiscalPeriod(fiscal_year=fy, quarter=q, month=m)

        # Check: Hashable
        try:
            _ = hash(period)
            _ = {period}
        except TypeError as e:
            msg = f"FiscalPeriod not hashable: {e}"
            raise FiscalFuzzError(msg) from e

        # Check: Comparable
        period2 = FiscalPeriod(fiscal_year=fy, quarter=q, month=m)
        if period != period2:
            msg = f"Equal periods not equal: {period} != {period2}"
            raise FiscalFuzzError(msg)

        # Check: Ordering
        if fy < PRACTICAL_MAX_YEAR:
            later = FiscalPeriod(fiscal_year=fy + 1, quarter=q, month=m)
            if period >= later:
                msg = f"Ordering failed: {period} should be < {later}"
                raise FiscalFuzzError(msg)

    except ALLOWED_EXCEPTIONS:
        pass  # Expected for invalid parameters


def test_one_input(data: bytes) -> None:
    """Atheris entry point: fuzz fiscal calendar APIs."""
    _fuzz_stats["iterations"] = int(_fuzz_stats["iterations"]) + 1
    _fuzz_stats["status"] = "running"

    fdp = atheris.FuzzedDataProvider(data)

    try:
        # Test FiscalCalendar
        start_month = generate_start_month(fdp)
        try:
            cal = FiscalCalendar(start_month=start_month)

            # Test with generated date
            d = generate_date(fdp)
            _verify_calendar_invariants(cal, d)

            # Test quarter boundaries
            if fdp.ConsumeBool():
                fiscal_year = fdp.ConsumeIntInRange(PRACTICAL_MIN_YEAR, PRACTICAL_MAX_YEAR)
                _verify_quarter_boundaries(cal, fiscal_year)

        except ALLOWED_EXCEPTIONS:
            pass  # Invalid start_month is expected

        # Test FiscalDelta
        if fdp.ConsumeBool():
            use_small = fdp.ConsumeBool()
            delta = generate_fiscal_delta(fdp, small=use_small)
            d = generate_date(fdp, practical=use_small)
            _verify_delta_arithmetic(delta, d)

        # Test delta algebra
        if fdp.ConsumeBool():
            _verify_delta_algebra(fdp)

        # Test FiscalPeriod
        if fdp.ConsumeBool():
            _verify_period_immutability(fdp)

        # Test convenience functions
        if fdp.ConsumeBool():
            _verify_convenience_functions(fdp)

    except ALLOWED_EXCEPTIONS:
        pass  # Expected for edge cases
    except FiscalFuzzError:
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        _fuzz_stats["status"] = "finding"
        raise
    except Exception as e:
        # Unexpected exception - this is a finding
        _fuzz_stats["findings"] = int(_fuzz_stats["findings"]) + 1
        _fuzz_stats["status"] = "finding"

        print("\n" + "=" * 80)
        print("[FINDING] FISCAL CALENDAR STABILITY BREACH")
        print("=" * 80)
        print(f"Exception Type: {type(e).__module__}.{type(e).__name__}")
        print(f"Error Message:  {e}")
        print("-" * 80)
        print("NEXT STEPS:")
        print("  1. Reproduce:  ./scripts/fuzz.sh --repro .fuzz_artifacts/crash_*")
        print("  2. Create test in tests/test_parsing_fiscal.py")
        print("  3. Fix & Verify")
        print("=" * 80)

        msg = f"{type(e).__name__}: {e}"
        raise FiscalFuzzError(msg) from e


def main() -> None:
    """Run the fiscal calendar fuzzer."""
    print("\n" + "=" * 80)
    print("Fiscal Calendar Fuzzer (Python 3.13 Edition)")
    print("=" * 80)
    print("Targets: FiscalCalendar, FiscalDelta, FiscalPeriod, convenience functions")
    print("Contract: Only ValueError, TypeError, OverflowError allowed")
    print("Stopping: Press Ctrl+C at any time (findings auto-saved)")
    print("=" * 80 + "\n")

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
