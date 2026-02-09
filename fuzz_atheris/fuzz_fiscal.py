#!/usr/bin/env python3
# FUZZ_PLUGIN_HEADER_START
# FUZZ_PLUGIN: fiscal - Fiscal Calendar arithmetic
# Intentional: This header is intentionally placed for dynamic plugin discovery.
# CRITICAL: DO NOT REMOVE THIS HEADER - REQUIRED FOR FUZZ_ATHERIS.SH
# FUZZ_PLUGIN_HEADER_END
"""Fiscal Calendar Fuzzer (Atheris).

Targets FiscalCalendar, FiscalDelta, FiscalPeriod, MonthEndPolicy, and
convenience functions from parsing.fiscal. Tests date arithmetic correctness,
boundary conditions, month-end policy handling, algebraic properties, type
validation error paths, and immutability contracts.

Shared infrastructure from fuzz_common (BaseFuzzerState, round-robin scheduling,
stratified corpus, metrics). Domain-specific metrics in FiscalMetrics.

Requires Python 3.13+ (uses PEP 695 type aliases).
"""

from __future__ import annotations

import argparse
import atexit
import calendar
import gc
import logging
import pathlib
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

# --- Dependency Checks (deferred import pattern) ---

_psutil_mod: Any
try:
    import psutil as _psutil_mod  # type: ignore[no-redef]
except ImportError:
    _psutil_mod = None

_atheris_mod: Any
try:
    import atheris as _atheris_mod  # type: ignore[no-redef]
except ImportError:
    _atheris_mod = None

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

import atheris  # noqa: E402, I001  # pylint: disable=C0412,C0413


# --- Domain Metrics ---


@dataclass
class FiscalMetrics:
    """Domain-specific metrics for fiscal calendar fuzzer."""

    calendar_invariant_checks: int = 0
    quarter_boundary_checks: int = 0
    calendar_identity_checks: int = 0
    delta_add_subtract_checks: int = 0
    delta_algebra_checks: int = 0
    policy_cross_checks: int = 0
    delta_validation_checks: int = 0
    period_contract_checks: int = 0
    convenience_oracle_checks: int = 0
    boundary_stress_checks: int = 0


class FiscalFuzzError(Exception):
    """Raised when an unexpected exception or invariant breach is detected."""


# --- Constants ---

ALLOWED_EXCEPTIONS = (ValueError, TypeError, OverflowError)

PRACTICAL_MIN_YEAR = 1900
PRACTICAL_MAX_YEAR = 2100
MIN_YEAR = 1
MAX_YEAR = 9999

# Pattern definitions with weights
_PATTERNS: Sequence[str] = (
    # CALENDAR (3)
    "calendar_invariants",
    "quarter_boundaries",
    "calendar_identity",
    # ARITHMETIC (4)
    "delta_add_subtract",
    "delta_algebra",
    "policy_cross",
    "delta_validation",
    # CONTRACTS (2)
    "period_contracts",
    "convenience_oracle",
    # STRESS (1)
    "boundary_stress",
)
_PATTERN_WEIGHTS: Sequence[int] = (
    # CALENDAR
    15, 10, 5,
    # ARITHMETIC
    12, 12, 8, 5,
    # CONTRACTS
    8, 8,
    # STRESS
    5,
)

_SCHEDULE = build_weighted_schedule(_PATTERNS, _PATTERN_WEIGHTS)


# --- Module State ---

_state = BaseFuzzerState(
    checkpoint_interval=500,
    seed_corpus_max_size=500,
    pattern_intended_weights=dict(
        zip(_PATTERNS, _PATTERN_WEIGHTS, strict=True),
    ),
)
_domain = FiscalMetrics()

_REPORT_DIR = pathlib.Path(".fuzz_atheris_corpus") / "fiscal"
_REPORT_FILE = "fuzz_fiscal_report.json"


def _emit_report() -> None:
    """Emit crash-proof final report."""
    stats = build_base_stats_dict(_state)
    stats["calendar_invariant_checks"] = _domain.calendar_invariant_checks
    stats["quarter_boundary_checks"] = _domain.quarter_boundary_checks
    stats["calendar_identity_checks"] = _domain.calendar_identity_checks
    stats["delta_add_subtract_checks"] = _domain.delta_add_subtract_checks
    stats["delta_algebra_checks"] = _domain.delta_algebra_checks
    stats["policy_cross_checks"] = _domain.policy_cross_checks
    stats["delta_validation_checks"] = _domain.delta_validation_checks
    stats["period_contract_checks"] = _domain.period_contract_checks
    stats["convenience_oracle_checks"] = _domain.convenience_oracle_checks
    stats["boundary_stress_checks"] = _domain.boundary_stress_checks
    emit_final_report(_state, stats, _REPORT_DIR, _REPORT_FILE)


atexit.register(_emit_report)

# --- Suppress logging and instrument imports ---
logging.getLogger("ftllexengine").setLevel(logging.CRITICAL)

with atheris.instrument_imports(include=["ftllexengine"]):
    from ftllexengine.parsing.fiscal import (
        FiscalCalendar,
        FiscalDelta,
        FiscalPeriod,
        MonthEndPolicy,
        fiscal_month,
        fiscal_quarter,
        fiscal_year,
        fiscal_year_end,
        fiscal_year_start,
    )


# --- Generators ---


def _generate_date(fdp: atheris.FuzzedDataProvider, *, practical: bool = True) -> date:
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


def _generate_month_end_date(fdp: atheris.FuzzedDataProvider) -> date:
    """Generate a date that is the last day of its month."""
    if not fdp.remaining_bytes():
        return date(2024, 1, 31)

    year = fdp.ConsumeIntInRange(PRACTICAL_MIN_YEAR, PRACTICAL_MAX_YEAR)
    month = fdp.ConsumeIntInRange(1, 12)
    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, max_day)


def _generate_start_month(fdp: atheris.FuzzedDataProvider) -> int:
    """Generate a fiscal year start month (1-12 or invalid for validation)."""
    if not fdp.remaining_bytes():
        return 1

    strategy = fdp.ConsumeIntInRange(0, 3)
    match strategy:
        case 0:
            return int(fdp.PickValueInList([1, 4, 7, 10]))
        case 1:
            return int(fdp.ConsumeIntInRange(1, 12))
        case 2:
            return int(fdp.ConsumeIntInRange(-100, 0))
        case _:
            return int(fdp.ConsumeIntInRange(13, 100))


def _generate_valid_start_month(fdp: atheris.FuzzedDataProvider) -> int:
    """Generate a valid fiscal year start month (1-12 only)."""
    if not fdp.remaining_bytes():
        return 1

    if fdp.ConsumeBool():
        return int(fdp.PickValueInList([1, 4, 7, 10]))
    return int(fdp.ConsumeIntInRange(1, 12))


def _generate_fiscal_delta(
    fdp: atheris.FuzzedDataProvider, *, small: bool = True,
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


def _generate_policy(fdp: atheris.FuzzedDataProvider) -> MonthEndPolicy:
    """Generate a MonthEndPolicy value."""
    return fdp.PickValueInList(list(MonthEndPolicy))


# --- Pattern Functions ---


def _pattern_calendar_invariants(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify FiscalCalendar cross-consistency: year/quarter/month/period agree."""
    _domain.calendar_invariant_checks += 1

    start_month = _generate_start_month(fdp)
    try:
        cal = FiscalCalendar(start_month=start_month)
    except ALLOWED_EXCEPTIONS:
        return

    d = _generate_date(fdp)

    quarter = cal.fiscal_quarter(d)
    if not 1 <= quarter <= 4:
        msg = f"fiscal_quarter returned {quarter}, expected 1-4"
        raise FiscalFuzzError(msg)

    fm = cal.fiscal_month(d)
    if not 1 <= fm <= 12:
        msg = f"fiscal_month returned {fm}, expected 1-12"
        raise FiscalFuzzError(msg)

    # fiscal_quarter must agree with fiscal_month
    expected_quarter = (fm - 1) // 3 + 1
    if quarter != expected_quarter:
        msg = (
            f"quarter {quarter} inconsistent with fiscal_month {fm} "
            f"(expected Q{expected_quarter})"
        )
        raise FiscalFuzzError(msg)

    fy = cal.fiscal_year(d)
    fy_start = cal.fiscal_year_start_date(fy)
    fy_end = cal.fiscal_year_end_date(fy)

    if not fy_start <= d <= fy_end:
        msg = f"Date {d} not in fiscal year {fy} ({fy_start} to {fy_end})"
        raise FiscalFuzzError(msg)

    # fiscal_period must agree with individual methods
    period = cal.fiscal_period(d)
    if period.fiscal_year != fy:
        msg = f"fiscal_period.fiscal_year {period.fiscal_year} != {fy}"
        raise FiscalFuzzError(msg)
    if period.quarter != quarter:
        msg = f"fiscal_period.quarter {period.quarter} != {quarter}"
        raise FiscalFuzzError(msg)
    if period.month != fm:
        msg = f"fiscal_period.month {period.month} != {fm}"
        raise FiscalFuzzError(msg)

    # Q1 start and Q4 end must match FY boundaries
    q1_start = cal.quarter_start_date(fy, 1)
    q4_end = cal.quarter_end_date(fy, 4)
    if q1_start != fy_start:
        msg = f"Q1 start {q1_start} != FY start {fy_start}"
        raise FiscalFuzzError(msg)
    if q4_end != fy_end:
        msg = f"Q4 end {q4_end} != FY end {fy_end}"
        raise FiscalFuzzError(msg)


def _pattern_quarter_boundaries(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify quarter boundaries are contiguous and span full fiscal year."""
    _domain.quarter_boundary_checks += 1

    start_month = _generate_start_month(fdp)
    try:
        cal = FiscalCalendar(start_month=start_month)
    except ALLOWED_EXCEPTIONS:
        return

    fy = fdp.ConsumeIntInRange(PRACTICAL_MIN_YEAR, PRACTICAL_MAX_YEAR)

    for q in range(1, 5):
        q_start = cal.quarter_start_date(fy, q)
        q_end = cal.quarter_end_date(fy, q)

        if q_start > q_end:
            msg = f"Q{q} start {q_start} > end {q_end}"
            raise FiscalFuzzError(msg)

        if q < 4:
            next_q_start = cal.quarter_start_date(fy, q + 1)
            expected_next = q_end + timedelta(days=1)
            if next_q_start != expected_next:
                msg = (
                    f"Q{q} end {q_end} not contiguous with "
                    f"Q{q + 1} start {next_q_start}"
                )
                raise FiscalFuzzError(msg)

    fy_start = cal.fiscal_year_start_date(fy)
    fy_end = cal.fiscal_year_end_date(fy)
    q1_start = cal.quarter_start_date(fy, 1)
    q4_end = cal.quarter_end_date(fy, 4)

    if q1_start != fy_start:
        msg = f"Q1 start {q1_start} != FY start {fy_start}"
        raise FiscalFuzzError(msg)
    if q4_end != fy_end:
        msg = f"Q4 end {q4_end} != FY end {fy_end}"
        raise FiscalFuzzError(msg)

    # Year spans exactly 365 or 366 days
    span = (fy_end - fy_start).days + 1
    if span not in (365, 366):
        msg = f"FY {fy} spans {span} days, expected 365 or 366"
        raise FiscalFuzzError(msg)


def _pattern_calendar_identity(fdp: atheris.FuzzedDataProvider) -> None:  # noqa: PLR0912, PLR0915
    """Test FiscalCalendar identity: hash, repr, equality, frozen, validation."""
    _domain.calendar_identity_checks += 1

    variant = fdp.ConsumeIntInRange(0, 5)

    match variant:
        case 0:
            # Hash and equality: same start_month -> same hash and eq
            sm = _generate_valid_start_month(fdp)
            cal1 = FiscalCalendar(start_month=sm)
            cal2 = FiscalCalendar(start_month=sm)
            if cal1 != cal2:
                msg = f"Equal calendars not equal: {cal1} != {cal2}"
                raise FiscalFuzzError(msg)
            if hash(cal1) != hash(cal2):
                msg = f"Equal calendars different hash: {hash(cal1)} != {hash(cal2)}"
                raise FiscalFuzzError(msg)

        case 1:
            # Inequality: different start_month -> not equal
            sm1 = fdp.ConsumeIntInRange(1, 6)
            sm2 = fdp.ConsumeIntInRange(7, 12)
            cal1 = FiscalCalendar(start_month=sm1)
            cal2 = FiscalCalendar(start_month=sm2)
            if cal1 == cal2:
                msg = f"Different calendars are equal: {cal1} == {cal2}"
                raise FiscalFuzzError(msg)

        case 2:
            # repr contains start_month
            sm = _generate_valid_start_month(fdp)
            cal = FiscalCalendar(start_month=sm)
            r = repr(cal)
            if str(sm) not in r or "FiscalCalendar" not in r:
                msg = f"repr missing info: {r}"
                raise FiscalFuzzError(msg)

        case 3:
            # Frozen: cannot set attributes
            cal = FiscalCalendar(start_month=1)
            try:
                cal.start_month = 4  # type: ignore[misc]
                msg = "FiscalCalendar is not frozen"
                raise FiscalFuzzError(msg)
            except AttributeError:
                pass

        case 4:
            # Type validation: non-int start_month raises TypeError
            try:
                FiscalCalendar(start_month="4")  # type: ignore[arg-type]
                msg = "FiscalCalendar accepted string start_month"
                raise FiscalFuzzError(msg)
            except TypeError:
                pass

        case _:
            # Range validation: out-of-range raises ValueError
            sm = _generate_start_month(fdp)
            if not 1 <= sm <= 12:
                try:
                    FiscalCalendar(start_month=sm)
                    msg = f"FiscalCalendar accepted invalid start_month={sm}"
                    raise FiscalFuzzError(msg)
                except ValueError:
                    pass
            else:
                cal = FiscalCalendar(start_month=sm)
                if cal.start_month != sm:
                    msg = f"start_month mismatch: {cal.start_month} != {sm}"
                    raise FiscalFuzzError(msg)


def _pattern_delta_add_subtract(fdp: atheris.FuzzedDataProvider) -> None:
    """Test add_to and subtract_from with all MonthEndPolicy behaviors."""
    _domain.delta_add_subtract_checks += 1

    variant = fdp.ConsumeIntInRange(0, 3)

    match variant:
        case 0:
            # add_to returns a date
            delta = _generate_fiscal_delta(fdp, small=True)
            d = _generate_date(fdp)
            try:
                result = delta.add_to(d)
                if not isinstance(result, date):
                    msg = f"add_to returned {type(result)}, expected date"
                    raise FiscalFuzzError(msg)
            except ALLOWED_EXCEPTIONS:
                pass

        case 1:
            # subtract_from == negate().add_to()
            delta = _generate_fiscal_delta(fdp, small=True)
            d = _generate_date(fdp)
            try:
                sub_result = delta.subtract_from(d)
                neg_add_result = delta.negate().add_to(d)
                if sub_result != neg_add_result:
                    msg = (
                        f"subtract_from != negate().add_to(): "
                        f"{sub_result} != {neg_add_result}"
                    )
                    raise FiscalFuzzError(msg)
            except ALLOWED_EXCEPTIONS:
                pass

        case 2:
            # CLAMP policy: month-end in -> month-end out
            d = _generate_month_end_date(fdp)
            months = fdp.ConsumeIntInRange(-24, 24)
            delta = FiscalDelta(months=months, month_end_policy=MonthEndPolicy.CLAMP)
            try:
                result = delta.add_to(d)
                max_day = calendar.monthrange(result.year, result.month)[1]
                if result.day != max_day:
                    msg = (
                        f"CLAMP: month-end {d} + {months}m = {result}, "
                        f"but result day {result.day} != last day {max_day}"
                    )
                    raise FiscalFuzzError(msg)
            except ALLOWED_EXCEPTIONS:
                pass

        case _:
            # STRICT policy: day overflow raises ValueError
            # Jan 31 + 3 months -> April 31 does not exist -> ValueError
            d = date(2024, 1, 31)
            delta = FiscalDelta(
                months=3, month_end_policy=MonthEndPolicy.STRICT,
            )
            try:
                delta.add_to(d)
                msg = "STRICT policy did not raise ValueError for day overflow"
                raise FiscalFuzzError(msg)
            except ValueError:
                pass


def _pattern_delta_algebra(fdp: atheris.FuzzedDataProvider) -> None:
    """Test algebraic properties: __add__, __sub__, __neg__, __mul__, __rmul__."""
    _domain.delta_algebra_checks += 1

    d1 = _generate_fiscal_delta(fdp, small=True)
    # Normalize d2 to same policy so arithmetic works
    d2_raw = _generate_fiscal_delta(fdp, small=True)
    d2 = d2_raw.with_policy(d1.month_end_policy)

    try:
        # Commutativity of addition
        sum1 = d1 + d2
        sum2 = d2 + d1
        if (
            sum1.years != sum2.years
            or sum1.quarters != sum2.quarters
            or sum1.months != sum2.months
            or sum1.days != sum2.days
        ):
            msg = f"Addition not commutative: {d1} + {d2}"
            raise FiscalFuzzError(msg)
    except ALLOWED_EXCEPTIONS:
        pass

    # Double negation identity
    neg_neg = d1.negate().negate()
    if (
        neg_neg.years != d1.years
        or neg_neg.quarters != d1.quarters
        or neg_neg.months != d1.months
        or neg_neg.days != d1.days
    ):
        msg = f"Double negation not identity: {d1}"
        raise FiscalFuzzError(msg)

    # __neg__ == negate()
    neg1 = -d1
    neg2 = d1.negate()
    if (
        neg1.years != neg2.years
        or neg1.quarters != neg2.quarters
        or neg1.months != neg2.months
        or neg1.days != neg2.days
    ):
        msg = f"__neg__ != negate(): {neg1} vs {neg2}"
        raise FiscalFuzzError(msg)

    # total_months consistency
    expected_total = d1.years * 12 + d1.quarters * 3 + d1.months
    if d1.total_months() != expected_total:
        msg = f"total_months mismatch: {d1.total_months()} != {expected_total}"
        raise FiscalFuzzError(msg)

    # Scalar multiplication + __rmul__
    try:
        scalar = fdp.ConsumeIntInRange(-5, 5) if fdp.remaining_bytes() else 2
        mul1 = d1 * scalar
        mul2 = scalar * d1
        if (
            mul1.years != mul2.years
            or mul1.quarters != mul2.quarters
            or mul1.months != mul2.months
            or mul1.days != mul2.days
        ):
            msg = f"__mul__ != __rmul__: {mul1} vs {mul2}"
            raise FiscalFuzzError(msg)
        if mul1.years != d1.years * scalar:
            msg = f"mul years: {mul1.years} != {d1.years * scalar}"
            raise FiscalFuzzError(msg)
    except ALLOWED_EXCEPTIONS:
        pass

    # __sub__: d1 - d2 == d1 + (-d2) component-wise
    try:
        diff = d1 - d2
        add_neg = d1 + (-d2)
        if (
            diff.years != add_neg.years
            or diff.quarters != add_neg.quarters
            or diff.months != add_neg.months
            or diff.days != add_neg.days
        ):
            msg = f"d1 - d2 != d1 + (-d2): {diff} vs {add_neg}"
            raise FiscalFuzzError(msg)
    except ALLOWED_EXCEPTIONS:
        pass


def _pattern_policy_cross(fdp: atheris.FuzzedDataProvider) -> None:
    """Test with_policy and cross-policy ValueError on arithmetic."""
    _domain.policy_cross_checks += 1

    variant = fdp.ConsumeIntInRange(0, 3)

    match variant:
        case 0:
            # with_policy creates copy with new policy, components preserved
            delta = _generate_fiscal_delta(fdp, small=True)
            new_policy = _generate_policy(fdp)
            converted = delta.with_policy(new_policy)
            if converted.month_end_policy != new_policy:
                msg = (
                    f"with_policy: {converted.month_end_policy} != {new_policy}"
                )
                raise FiscalFuzzError(msg)
            if (
                converted.years != delta.years
                or converted.months != delta.months
                or converted.days != delta.days
            ):
                msg = f"with_policy changed components: {delta} -> {converted}"
                raise FiscalFuzzError(msg)

        case 1:
            # Cross-policy __add__ raises ValueError
            d1 = FiscalDelta(
                months=1, month_end_policy=MonthEndPolicy.PRESERVE,
            )
            d2 = FiscalDelta(
                months=2, month_end_policy=MonthEndPolicy.CLAMP,
            )
            try:
                _ = d1 + d2
                msg = "Cross-policy add did not raise ValueError"
                raise FiscalFuzzError(msg)
            except ValueError:
                pass

        case 2:
            # Cross-policy __sub__ raises ValueError
            d1 = FiscalDelta(
                months=1, month_end_policy=MonthEndPolicy.PRESERVE,
            )
            d2 = FiscalDelta(
                months=2, month_end_policy=MonthEndPolicy.STRICT,
            )
            try:
                _ = d1 - d2
                msg = "Cross-policy sub did not raise ValueError"
                raise FiscalFuzzError(msg)
            except ValueError:
                pass

        case _:
            # All three policies produce valid dates for same delta
            months = fdp.ConsumeIntInRange(-12, 12)
            d = _generate_date(fdp)
            for policy in MonthEndPolicy:
                delta = FiscalDelta(months=months, month_end_policy=policy)
                try:
                    result = delta.add_to(d)
                    if not isinstance(result, date):
                        msg = f"Policy {policy.value}: not a date"
                        raise FiscalFuzzError(msg)
                except ALLOWED_EXCEPTIONS:
                    pass


def _pattern_delta_validation(fdp: atheris.FuzzedDataProvider) -> None:
    """Test FiscalDelta __post_init__ type validation."""
    _domain.delta_validation_checks += 1

    variant = fdp.ConsumeIntInRange(0, 2)

    match variant:
        case 0:
            # Non-int field raises TypeError
            try:
                FiscalDelta(years=1.5)  # type: ignore[arg-type]
                msg = "FiscalDelta accepted float years"
                raise FiscalFuzzError(msg)
            except TypeError:
                pass

        case 1:
            # Non-MonthEndPolicy raises TypeError
            try:
                FiscalDelta(
                    months=1,
                    month_end_policy="invalid",  # type: ignore[arg-type]
                )
                msg = "FiscalDelta accepted string month_end_policy"
                raise FiscalFuzzError(msg)
            except TypeError:
                pass

        case _:
            # Valid construction preserves all fields
            y = fdp.ConsumeIntInRange(-10, 10)
            q = fdp.ConsumeIntInRange(-10, 10)
            m = fdp.ConsumeIntInRange(-10, 10)
            d = fdp.ConsumeIntInRange(-100, 100)
            policy = _generate_policy(fdp)
            delta = FiscalDelta(
                years=y, quarters=q, months=m, days=d,
                month_end_policy=policy,
            )
            if (
                delta.years != y or delta.quarters != q
                or delta.months != m or delta.days != d
                or delta.month_end_policy != policy
            ):
                msg = "FiscalDelta field mismatch after construction"
                raise FiscalFuzzError(msg)


def _pattern_period_contracts(fdp: atheris.FuzzedDataProvider) -> None:  # noqa: PLR0912, PLR0915
    """Test FiscalPeriod: hash, eq, ordering, frozen, repr, validation."""
    _domain.period_contract_checks += 1

    variant = fdp.ConsumeIntInRange(0, 5)

    match variant:
        case 0:
            # Hash and equality
            fy = fdp.ConsumeIntInRange(PRACTICAL_MIN_YEAR, PRACTICAL_MAX_YEAR)
            q = fdp.ConsumeIntInRange(1, 4)
            m = fdp.ConsumeIntInRange(1, 12)
            p1 = FiscalPeriod(fiscal_year=fy, quarter=q, month=m)
            p2 = FiscalPeriod(fiscal_year=fy, quarter=q, month=m)
            if p1 != p2:
                msg = f"Equal periods not equal: {p1} != {p2}"
                raise FiscalFuzzError(msg)
            if hash(p1) != hash(p2):
                msg = "Equal periods have different hash"
                raise FiscalFuzzError(msg)
            if len({p1, p2}) != 1:
                msg = "Equal periods not deduplicated in set"
                raise FiscalFuzzError(msg)

        case 1:
            # Full ordering: <, <=, >, >=
            fy = fdp.ConsumeIntInRange(
                PRACTICAL_MIN_YEAR, PRACTICAL_MAX_YEAR - 1,
            )
            q = fdp.ConsumeIntInRange(1, 4)
            m = fdp.ConsumeIntInRange(1, 12)
            earlier = FiscalPeriod(fiscal_year=fy, quarter=q, month=m)
            later = FiscalPeriod(fiscal_year=fy + 1, quarter=q, month=m)
            # Each operator tested individually to exercise __lt__, __gt__,
            # __le__, __ge__ dispatch (frozen dataclass order=True).
            if not earlier < later:  # pylint: disable=C0117
                msg = f"Ordering: {earlier} should be < {later}"
                raise FiscalFuzzError(msg)
            if not later > earlier:  # pylint: disable=C0117
                msg = f"Ordering: {later} should be > {earlier}"
                raise FiscalFuzzError(msg)
            if not earlier <= later:  # pylint: disable=C0117
                msg = f"Ordering: {earlier} should be <= {later}"
                raise FiscalFuzzError(msg)
            if not later >= earlier:  # pylint: disable=C0117
                msg = f"Ordering: {later} should be >= {earlier}"
                raise FiscalFuzzError(msg)

        case 2:
            # Frozen: cannot mutate
            p = FiscalPeriod(fiscal_year=2024, quarter=1, month=1)
            try:
                p.fiscal_year = 2025  # type: ignore[misc]
                msg = "FiscalPeriod is not frozen"
                raise FiscalFuzzError(msg)
            except AttributeError:
                pass

        case 3:
            # repr contains class name
            fy = fdp.ConsumeIntInRange(PRACTICAL_MIN_YEAR, PRACTICAL_MAX_YEAR)
            q = fdp.ConsumeIntInRange(1, 4)
            m = fdp.ConsumeIntInRange(1, 12)
            p = FiscalPeriod(fiscal_year=fy, quarter=q, month=m)
            r = repr(p)
            if "FiscalPeriod" not in r:
                msg = f"repr missing class name: {r}"
                raise FiscalFuzzError(msg)

        case 4:
            # Validation: invalid quarter or month raises ValueError
            try:
                FiscalPeriod(fiscal_year=2024, quarter=0, month=1)
                msg = "FiscalPeriod accepted quarter=0"
                raise FiscalFuzzError(msg)
            except ValueError:
                pass
            try:
                FiscalPeriod(fiscal_year=2024, quarter=5, month=1)
                msg = "FiscalPeriod accepted quarter=5"
                raise FiscalFuzzError(msg)
            except ValueError:
                pass
            try:
                FiscalPeriod(fiscal_year=2024, quarter=1, month=0)
                msg = "FiscalPeriod accepted month=0"
                raise FiscalFuzzError(msg)
            except ValueError:
                pass
            try:
                FiscalPeriod(fiscal_year=2024, quarter=1, month=13)
                msg = "FiscalPeriod accepted month=13"
                raise FiscalFuzzError(msg)
            except ValueError:
                pass

        case _:
            # Fuzzed construction with valid params
            fy = fdp.ConsumeIntInRange(PRACTICAL_MIN_YEAR, PRACTICAL_MAX_YEAR)
            q = fdp.ConsumeIntInRange(1, 4)
            m = fdp.ConsumeIntInRange(1, 12)
            p = FiscalPeriod(fiscal_year=fy, quarter=q, month=m)
            if p.fiscal_year != fy or p.quarter != q or p.month != m:
                msg = "FiscalPeriod field mismatch after construction"
                raise FiscalFuzzError(msg)


def _pattern_convenience_oracle(fdp: atheris.FuzzedDataProvider) -> None:
    """Verify ALL 5 convenience functions agree with FiscalCalendar methods."""
    _domain.convenience_oracle_checks += 1

    d = _generate_date(fdp)
    sm = _generate_valid_start_month(fdp)
    cal = FiscalCalendar(start_month=sm)

    # fiscal_quarter
    q_func = fiscal_quarter(d, sm)
    q_cal = cal.fiscal_quarter(d)
    if q_func != q_cal:
        msg = f"fiscal_quarter mismatch: {q_func} != {q_cal}"
        raise FiscalFuzzError(msg)

    # fiscal_year
    fy_func = fiscal_year(d, sm)
    fy_cal = cal.fiscal_year(d)
    if fy_func != fy_cal:
        msg = f"fiscal_year mismatch: {fy_func} != {fy_cal}"
        raise FiscalFuzzError(msg)

    # fiscal_month
    fm_func = fiscal_month(d, sm)
    fm_cal = cal.fiscal_month(d)
    if fm_func != fm_cal:
        msg = f"fiscal_month mismatch: {fm_func} != {fm_cal}"
        raise FiscalFuzzError(msg)

    # fiscal_year_start
    fy = cal.fiscal_year(d)
    start_func = fiscal_year_start(fy, sm)
    start_cal = cal.fiscal_year_start_date(fy)
    if start_func != start_cal:
        msg = f"fiscal_year_start mismatch: {start_func} != {start_cal}"
        raise FiscalFuzzError(msg)

    # fiscal_year_end
    end_func = fiscal_year_end(fy, sm)
    end_cal = cal.fiscal_year_end_date(fy)
    if end_func != end_cal:
        msg = f"fiscal_year_end mismatch: {end_func} != {end_cal}"
        raise FiscalFuzzError(msg)


def _pattern_boundary_stress(fdp: atheris.FuzzedDataProvider) -> None:
    """Stress test with extreme dates (year 1-9999) and large deltas."""
    _domain.boundary_stress_checks += 1

    try:
        d = _generate_date(fdp, practical=False)
        sm = _generate_valid_start_month(fdp)
        cal = FiscalCalendar(start_month=sm)

        quarter = cal.fiscal_quarter(d)
        if not 1 <= quarter <= 4:
            msg = f"Extreme date: fiscal_quarter returned {quarter}"
            raise FiscalFuzzError(msg)

        fm = cal.fiscal_month(d)
        if not 1 <= fm <= 12:
            msg = f"Extreme date: fiscal_month returned {fm}"
            raise FiscalFuzzError(msg)

        fy = cal.fiscal_year(d)
        fy_start = cal.fiscal_year_start_date(fy)
        fy_end = cal.fiscal_year_end_date(fy)
        if not fy_start <= d <= fy_end:
            msg = f"Extreme date {d} not in FY {fy}"
            raise FiscalFuzzError(msg)

        # Large delta on extreme date
        delta = _generate_fiscal_delta(fdp, small=False)
        result = delta.add_to(d)
        if not isinstance(result, date):
            msg = f"Large delta returned non-date: {type(result)}"
            raise FiscalFuzzError(msg)

    except ALLOWED_EXCEPTIONS:
        pass


# --- Pattern dispatch ---

_PATTERN_DISPATCH: dict[str, Callable[[Any], None]] = {
    "calendar_invariants": _pattern_calendar_invariants,
    "quarter_boundaries": _pattern_quarter_boundaries,
    "calendar_identity": _pattern_calendar_identity,
    "delta_add_subtract": _pattern_delta_add_subtract,
    "delta_algebra": _pattern_delta_algebra,
    "policy_cross": _pattern_policy_cross,
    "delta_validation": _pattern_delta_validation,
    "period_contracts": _pattern_period_contracts,
    "convenience_oracle": _pattern_convenience_oracle,
    "boundary_stress": _pattern_boundary_stress,
}


# --- Main Entry Point ---


def test_one_input(data: bytes) -> None:
    """Atheris entry point: fuzz fiscal calendar APIs."""
    if _state.iterations == 0:
        _state.initial_memory_mb = (
            get_process().memory_info().rss / (1024 * 1024)
        )

    _state.iterations += 1
    _state.status = "running"

    if _state.iterations % _state.checkpoint_interval == 0:
        _emit_report()

    start_time = time.perf_counter()
    fdp = atheris.FuzzedDataProvider(data)

    pattern = select_pattern_round_robin(_state, _SCHEDULE)
    _state.pattern_coverage[pattern] = (
        _state.pattern_coverage.get(pattern, 0) + 1
    )

    try:
        handler = _PATTERN_DISPATCH[pattern]
        handler(fdp)

    except FiscalFuzzError:
        _state.findings += 1
        _state.status = "finding"
        raise

    except Exception as e:  # pylint: disable=broad-exception-caught
        error_key = f"{type(e).__name__}_{str(e)[:30]}"
        _state.error_counts[error_key] = (
            _state.error_counts.get(error_key, 0) + 1
        )

        _state.findings += 1
        _state.status = "finding"

        print("\n" + "=" * 80, file=sys.stderr)
        print("[FINDING] FISCAL CALENDAR STABILITY BREACH", file=sys.stderr)
        print("=" * 80, file=sys.stderr)
        print(
            f"Exception Type: {type(e).__module__}.{type(e).__name__}",
            file=sys.stderr,
        )
        print(f"Error Message:  {e}", file=sys.stderr)
        print("-" * 80, file=sys.stderr)

        msg = f"{type(e).__name__}: {e}"
        raise FiscalFuzzError(msg) from e

    finally:
        # Semantic interestingness: patterns exercising complex paths,
        # error paths, or wall-time > 1ms indicating unusual code path
        is_interesting = pattern in (
            "delta_add_subtract", "policy_cross", "delta_algebra",
            "boundary_stress", "delta_validation",
            "calendar_identity", "period_contracts", "convenience_oracle",
        ) or (time.perf_counter() - start_time) * 1000 > 1.0
        record_iteration_metrics(
            _state, pattern, start_time, data, is_interesting=is_interesting,
        )

        if _state.iterations % GC_INTERVAL == 0:
            gc.collect()

        if _state.iterations % 100 == 0:
            record_memory(_state)


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
        default=500,
        help="Maximum size of in-memory seed corpus (default: 500)",
    )

    args, remaining = parser.parse_known_args()
    _state.checkpoint_interval = args.checkpoint_interval
    _state.seed_corpus_max_size = args.seed_corpus_size

    sys.argv = [sys.argv[0], *remaining]

    print()
    print("=" * 80)
    print("Fiscal Calendar Fuzzer (Atheris)")
    print("=" * 80)
    print(
        "Target:     FiscalCalendar, FiscalDelta, FiscalPeriod, "
        "MonthEndPolicy, convenience functions",
    )
    print(f"Patterns:   {len(_PATTERNS)} ({sum(_PATTERN_WEIGHTS)} weighted slots)")
    print(f"Checkpoint: Every {_state.checkpoint_interval} iterations")
    print(f"Corpus Max: {_state.seed_corpus_max_size} entries")
    print("Stopping:   Press Ctrl+C (findings auto-saved)")
    print("=" * 80)
    print()

    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
