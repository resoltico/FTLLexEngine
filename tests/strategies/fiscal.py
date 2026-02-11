"""Hypothesis strategies for fiscal date arithmetic testing.

Provides strategies for generating valid fiscal calendar configurations,
date deltas, and date ranges for property-based testing.

Usage:
    from hypothesis import given
    from tests.strategies.fiscal import reasonable_dates, fiscal_deltas

    @given(d=reasonable_dates, delta=fiscal_deltas)
    def test_delta_property(d, delta):
        ...
"""

from __future__ import annotations

import calendar
from datetime import date
from typing import TYPE_CHECKING

from hypothesis import event
from hypothesis import strategies as st
from hypothesis.strategies import composite

if TYPE_CHECKING:
    from hypothesis.strategies import SearchStrategy

# ============================================================================
# DATE STRATEGIES
# ============================================================================

# Dates within a reasonable range for financial applications.
# Avoids edge cases at year boundaries that might overflow.
# Range: 1900-01-01 to 2100-12-31 (covers all practical fiscal scenarios)
reasonable_dates: SearchStrategy[date] = st.dates(
    min_value=date(1900, 1, 1),
    max_value=date(2100, 12, 31),
)

# Month-end dates only (useful for testing month-end policy behavior)
month_end_dates: SearchStrategy[date] = st.builds(
    lambda y, m: date(y, m, _last_day_of_month(y, m)),
    y=st.integers(min_value=1900, max_value=2100),
    m=st.integers(min_value=1, max_value=12),
)


def _last_day_of_month(year: int, month: int) -> int:
    """Get the last day of a given month."""
    return calendar.monthrange(year, month)[1]


# ============================================================================
# FISCAL CALENDAR STRATEGIES
# ============================================================================

# Valid fiscal year start months (1-12)
fiscal_year_start_months: SearchStrategy[int] = st.integers(min_value=1, max_value=12)

# Common fiscal calendar configurations used in practice
common_fiscal_calendars: SearchStrategy[int] = st.sampled_from([
    1,   # Calendar year (most common)
    4,   # UK government, Japan government
    7,   # Australia, New Zealand
    10,  # US federal government
])

# Strategy for FiscalCalendar instances (once implemented)
# Will be: st.builds(FiscalCalendar, fiscal_year_start_month=fiscal_year_start_months)
fiscal_calendars: SearchStrategy[int] = fiscal_year_start_months


# ============================================================================
# FISCAL DELTA STRATEGIES
# ============================================================================

# Month-end policy options
month_end_policies: SearchStrategy[str] = st.sampled_from([
    "preserve",
    "clamp",
    "strict",
])

# Small deltas for basic testing (avoids overflow)
small_fiscal_deltas: SearchStrategy[dict[str, int | str]] = st.fixed_dictionaries({
    "years": st.integers(min_value=-10, max_value=10),
    "quarters": st.integers(min_value=-40, max_value=40),
    "months": st.integers(min_value=-120, max_value=120),
    "days": st.integers(min_value=-365, max_value=365),
    "month_end_policy": month_end_policies,
})

# Larger deltas for stress testing (still within reasonable bounds)
fiscal_deltas: SearchStrategy[dict[str, int | str]] = st.fixed_dictionaries({
    "years": st.integers(min_value=-100, max_value=100),
    "quarters": st.integers(min_value=-400, max_value=400),
    "months": st.integers(min_value=-1200, max_value=1200),
    "days": st.integers(min_value=-36500, max_value=36500),  # ~100 years in days
    "month_end_policy": month_end_policies,
})

# Zero delta (identity element for testing)
zero_delta: SearchStrategy[dict[str, int | str]] = st.just({
    "years": 0,
    "quarters": 0,
    "months": 0,
    "days": 0,
    "month_end_policy": "clamp",
})


# ============================================================================
# PERIOD STRATEGIES
# ============================================================================

# Fiscal period types
period_types: SearchStrategy[str] = st.sampled_from([
    "month",
    "quarter",
    "year",
])

# Fiscal quarter numbers
fiscal_quarters: SearchStrategy[int] = st.integers(min_value=1, max_value=4)

# Fiscal month numbers (1-12 within fiscal year)
fiscal_months: SearchStrategy[int] = st.integers(min_value=1, max_value=12)


# ============================================================================
# EVENT-EMITTING STRATEGIES (for HypoFuzz guidance)
# ============================================================================


@composite
def fiscal_delta_by_magnitude(draw: st.DrawFn) -> dict[str, int | str]:
    """Generate fiscal delta with event emission for magnitude category.

    Events emitted:
    - fiscal_delta={zero|small|medium|large}: Delta magnitude category

    Useful for testing overflow and edge case handling at different scales.
    """
    magnitude = draw(st.sampled_from(["zero", "small", "medium", "large"]))
    delta: dict[str, int | str]

    match magnitude:
        case "zero":
            # Inline zero values instead of st.just() to add
            # variation via month_end_policy draw -- st.just()
            # is deterministic so Hypothesis skips it after 1
            delta = {
                "years": 0,
                "quarters": 0,
                "months": 0,
                "days": 0,
                "month_end_policy": draw(month_end_policies),
            }
        case "small":
            delta = {
                "years": draw(st.integers(min_value=-2, max_value=2)),
                "quarters": draw(st.integers(min_value=-8, max_value=8)),
                "months": draw(st.integers(min_value=-24, max_value=24)),
                "days": draw(st.integers(min_value=-60, max_value=60)),
                "month_end_policy": draw(month_end_policies),
            }
        case "medium":
            delta = draw(small_fiscal_deltas)
        case _:  # large
            delta = draw(fiscal_deltas)

    event(f"fiscal_delta={magnitude}")
    return delta


@composite
def date_by_boundary(draw: st.DrawFn) -> date:
    """Generate date with event emission for boundary category.

    Events emitted:
    - date_boundary={month_end|year_end|leap_feb|quarter_end|normal}

    Useful for testing date arithmetic at boundary conditions.
    """
    boundary = draw(
        st.sampled_from([
            "month_end",
            "year_end",
            "leap_feb",
            "quarter_end",
            "normal",
        ])
    )

    match boundary:
        case "month_end":
            d = draw(month_end_dates)
        case "year_end":
            year = draw(st.integers(min_value=1900, max_value=2100))
            d = date(year, 12, 31)
        case "leap_feb":
            # Leap year February dates
            leap_year = draw(st.sampled_from([2000, 2004, 2008, 2012, 2016, 2020, 2024]))
            day = draw(st.integers(min_value=28, max_value=29))
            d = date(leap_year, 2, day)
        case "quarter_end":
            year = draw(st.integers(min_value=1900, max_value=2100))
            quarter_end_dates = [
                date(year, 3, 31),
                date(year, 6, 30),
                date(year, 9, 30),
                date(year, 12, 31),
            ]
            d = draw(st.sampled_from(quarter_end_dates))
        case _:  # normal
            d = draw(reasonable_dates)

    event(f"date_boundary={boundary}")
    return d


@composite
def fiscal_calendar_by_type(draw: st.DrawFn) -> int:
    """Generate fiscal calendar start month with event emission.

    Events emitted:
    - fiscal_calendar={calendar_year|uk_japan|australia|us_federal|other}

    Useful for testing fiscal year start month handling.
    """
    cal_type = draw(
        st.sampled_from([
            "calendar_year",
            "uk_japan",
            "australia",
            "us_federal",
            "other",
        ])
    )

    match cal_type:
        case "calendar_year":
            month = 1
        case "uk_japan":
            month = 4
        case "australia":
            month = 7
        case "us_federal":
            month = 10
        case _:  # other
            excluded = {1, 4, 7, 10}
            month = draw(st.integers(min_value=2, max_value=12).filter(lambda m: m not in excluded))

    event(f"fiscal_calendar={cal_type}")
    return month


@composite
def month_end_policy_with_event(draw: st.DrawFn) -> str:
    """Generate month-end policy with event emission.

    Events emitted:
    - month_end_policy={preserve|clamp|strict}

    Useful for testing different month-end arithmetic behaviors.
    """
    policy = draw(month_end_policies)
    event(f"month_end_policy={policy}")
    return policy


@composite
def fiscal_periods(
    draw: st.DrawFn,
) -> tuple[int, int, int]:
    """Generate valid FiscalPeriod constructor args with events.

    Events emitted:
    - fiscal_period_quarter={1|2|3|4}: Quarter in generated period

    Returns:
        Tuple of (fiscal_year, quarter, month).
    """
    fiscal_year = draw(
        st.integers(min_value=1900, max_value=2100)
    )
    quarter = draw(st.integers(min_value=1, max_value=4))
    month = draw(st.integers(min_value=1, max_value=12))
    event(f"fiscal_period_quarter={quarter}")
    return (fiscal_year, quarter, month)


@composite
def fiscal_boundary_crossing_pair(draw: st.DrawFn) -> tuple[date, date]:
    """Generate date pair that spans a fiscal year boundary.

    D12 fix: Fiscal period calculations crossing year boundaries are the
    primary source of bugs in financial date arithmetic (Q4->Q1 transitions,
    fiscal year-end rollovers).

    Events emitted:
    - fiscal_boundary={year_end|quarter_end}: Boundary type crossed

    Returns tuple of (date_before_boundary, date_after_boundary).
    """
    # Choose fiscal calendar type
    fiscal_start = draw(
        st.sampled_from([1, 4, 7, 10])
    )

    # Calculate fiscal year end month (month before start)
    fiscal_end_month = (
        12 if fiscal_start == 1 else fiscal_start - 1
    )

    # Draw quarter unconditionally so both branches consume
    # the same number of draws -- prevents Hypothesis from
    # over-exploring the branch with more randomness
    quarter = draw(st.integers(min_value=1, max_value=4))

    # Choose boundary type
    boundary_type = draw(
        st.sampled_from(["year_end", "quarter_end"])
    )

    year = draw(st.integers(min_value=1950, max_value=2050))

    match boundary_type:
        case "year_end":
            # Last day of fiscal year -> first day of next
            last_day = _last_day_of_month(
                year, fiscal_end_month
            )
            before = date(year, fiscal_end_month, last_day)

            # Next fiscal year starts
            next_month = fiscal_start
            next_year = (
                year
                if fiscal_start > fiscal_end_month
                else year + 1
            )
            after = date(next_year, next_month, 1)
            event("fiscal_boundary=year_end")

        case _:  # quarter_end
            # End of a fiscal quarter -> start of next quarter
            # Q1=months 1-3, Q2=4-6, Q3=7-9, Q4=10-12
            # relative to fiscal start
            quarter_end_offset = quarter * 3 - 1
            quarter_end_month = (
                (fiscal_start - 1 + quarter_end_offset) % 12
            ) + 1

            # Adjust year if month wraps
            adj_year = (
                year
                if quarter_end_month >= fiscal_start
                else year + 1
            )
            last_day = _last_day_of_month(
                adj_year, quarter_end_month
            )
            before = date(
                adj_year, quarter_end_month, last_day
            )

            # Next month is start of next quarter
            next_month = (quarter_end_month % 12) + 1
            next_year = (
                adj_year
                if next_month > quarter_end_month
                else adj_year + 1
            )
            after = date(next_year, next_month, 1)
            event("fiscal_boundary=quarter_end")

    return (before, after)
