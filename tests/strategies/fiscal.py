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

from hypothesis import strategies as st

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
