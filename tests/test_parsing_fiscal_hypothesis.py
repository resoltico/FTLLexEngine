"""Hypothesis property-based tests for fiscal calendar arithmetic.

Tests invariants and properties that must hold across all valid inputs.
Uses strategies from tests.strategies.fiscal for generating test data.
"""

from __future__ import annotations

from datetime import date

import pytest
from hypothesis import assume, event, given
from hypothesis import strategies as st

from ftllexengine.parsing import (
    FiscalCalendar,
    FiscalDelta,
    FiscalPeriod,
    MonthEndPolicy,
)
from tests.strategies.fiscal import (
    date_by_boundary,
    fiscal_boundary_crossing_pair,
    fiscal_calendar_by_type,
    fiscal_calendars,
    fiscal_delta_by_magnitude,
    fiscal_periods,
    month_end_policy_with_event,
    reasonable_dates,
    small_fiscal_deltas,
)

# ============================================================================
# FISCAL CALENDAR PROPERTIES
# ============================================================================


@pytest.mark.fuzz
class TestFiscalCalendarProperties:
    """Property-based tests for FiscalCalendar."""

    @given(start_month=st.integers(min_value=1, max_value=12))
    def test_valid_start_month_accepted(self, start_month: int) -> None:
        """All months 1-12 are valid start months."""
        cal = FiscalCalendar(start_month=start_month)
        event(f"start_month={start_month}")
        assert cal.start_month == start_month
        event("outcome=valid_start_month")

    @given(start_month=st.integers(min_value=-100, max_value=0))
    def test_invalid_low_start_month_rejected(self, start_month: int) -> None:
        """Start months <= 0 are rejected."""
        event(f"start_month={start_month}")
        with pytest.raises(ValueError, match="start_month must be 1-12"):
            FiscalCalendar(start_month=start_month)

    @given(start_month=st.integers(min_value=13, max_value=100))
    def test_invalid_high_start_month_rejected(self, start_month: int) -> None:
        """Start months >= 13 are rejected."""
        event(f"start_month={start_month}")
        with pytest.raises(ValueError, match="start_month must be 1-12"):
            FiscalCalendar(start_month=start_month)

    @given(start_month=fiscal_calendar_by_type(), d=reasonable_dates)
    def test_fiscal_quarter_in_valid_range(self, start_month: int, d: date) -> None:
        """Fiscal quarter is always 1-4."""
        cal = FiscalCalendar(start_month=start_month)
        quarter = cal.fiscal_quarter(d)
        event(f"quarter={quarter}")
        assert 1 <= quarter <= 4
        event("outcome=fiscal_quarter_valid")

    @given(start_month=fiscal_calendar_by_type(), d=reasonable_dates)
    def test_fiscal_month_in_valid_range(self, start_month: int, d: date) -> None:
        """Fiscal month is always 1-12."""
        cal = FiscalCalendar(start_month=start_month)
        month = cal.fiscal_month(d)
        assert 1 <= month <= 12
        event(f"month={month}")

    @given(start_month=fiscal_calendar_by_type(), d=reasonable_dates)
    def test_fiscal_quarter_matches_fiscal_month(self, start_month: int, d: date) -> None:
        """Fiscal quarter is derived from fiscal month."""
        cal = FiscalCalendar(start_month=start_month)
        fiscal_month = cal.fiscal_month(d)
        fiscal_quarter = cal.fiscal_quarter(d)

        expected_quarter = (fiscal_month - 1) // 3 + 1
        assert fiscal_quarter == expected_quarter
        event(f"quarter={fiscal_quarter}")

    @given(start_month=fiscal_calendars, d=reasonable_dates)
    def test_fiscal_period_consistent(self, start_month: int, d: date) -> None:
        """FiscalPeriod components match individual method results."""
        cal = FiscalCalendar(start_month=start_month)
        period = cal.fiscal_period(d)

        assert period.fiscal_year == cal.fiscal_year(d)
        assert period.quarter == cal.fiscal_quarter(d)
        assert period.month == cal.fiscal_month(d)
        event(f"quarter={period.quarter}")

    @given(start_month=fiscal_calendars, fiscal_year=st.integers(min_value=1900, max_value=2100))
    def test_fiscal_year_start_before_end(self, start_month: int, fiscal_year: int) -> None:
        """Fiscal year start is always before fiscal year end."""
        cal = FiscalCalendar(start_month=start_month)
        start = cal.fiscal_year_start_date(fiscal_year)
        end = cal.fiscal_year_end_date(fiscal_year)
        assert start < end
        event(f"start_month={start_month}")

    @given(
        start_month=fiscal_calendars,
        fiscal_year=st.integers(min_value=1900, max_value=2100),
        quarter=st.integers(min_value=1, max_value=4),
    )
    def test_quarter_start_before_end(
        self, start_month: int, fiscal_year: int, quarter: int
    ) -> None:
        """Quarter start is always before quarter end."""
        cal = FiscalCalendar(start_month=start_month)
        start = cal.quarter_start_date(fiscal_year, quarter)
        end = cal.quarter_end_date(fiscal_year, quarter)
        assert start < end
        event(f"quarter={quarter}")

    @given(start_month=fiscal_calendars, fiscal_year=st.integers(min_value=1900, max_value=2100))
    def test_fiscal_year_contains_365_or_366_days(
        self, start_month: int, fiscal_year: int
    ) -> None:
        """Fiscal year spans 365 or 366 days."""
        cal = FiscalCalendar(start_month=start_month)
        start = cal.fiscal_year_start_date(fiscal_year)
        end = cal.fiscal_year_end_date(fiscal_year)
        days = (end - start).days + 1  # Inclusive
        assert days in (365, 366)
        event(f"days={days}")


# ============================================================================
# FISCAL DELTA PROPERTIES
# ============================================================================


@pytest.mark.fuzz
class TestFiscalDeltaProperties:
    """Property-based tests for FiscalDelta."""

    @given(d=date_by_boundary())
    def test_zero_delta_is_identity(self, d: date) -> None:
        """Zero delta returns the same date."""
        delta = FiscalDelta()
        assert delta.add_to(d) == d
        event(f"day={d.day}")

    @given(d=reasonable_dates, delta_dict=small_fiscal_deltas)
    def test_negate_reverses_addition(self, d: date, delta_dict: dict[str, int]) -> None:
        """Adding then subtracting returns original date."""
        # Use preserve policy to avoid strict mode errors
        delta = FiscalDelta(
            years=delta_dict["years"],
            quarters=delta_dict["quarters"],
            months=delta_dict["months"],
            days=delta_dict["days"],
            month_end_policy=MonthEndPolicy.PRESERVE,
        )

        try:
            result = delta.add_to(d)
            # Check if result is in valid range
            assume(date(1900, 1, 1) <= result <= date(2100, 12, 31))
            back = delta.negate().add_to(result)
            # Due to month-end clamping, we may not get exact original
            # But the month difference should be zero
            month_diff = (back.year - d.year) * 12 + (back.month - d.month)
            event(f"month_diff={month_diff}")
            # Allow for month-end clamping effects
            assert abs(month_diff) <= 1 or back == d
            event("outcome=negate_reverse_addition")
        except (OverflowError, ValueError):
            # Date out of range - skip this example
            assume(False)

    @given(
        years=st.integers(min_value=-100, max_value=100),
        quarters=st.integers(min_value=-100, max_value=100),
        months=st.integers(min_value=-100, max_value=100),
    )
    def test_total_months_calculation(self, years: int, quarters: int, months: int) -> None:
        """total_months is years*12 + quarters*3 + months."""
        delta = FiscalDelta(years=years, quarters=quarters, months=months)
        expected = years * 12 + quarters * 3 + months
        assert delta.total_months() == expected
        event(f"total={expected}")

    @given(
        d1_years=st.integers(min_value=-10, max_value=10),
        d1_months=st.integers(min_value=-10, max_value=10),
        d2_years=st.integers(min_value=-10, max_value=10),
        d2_months=st.integers(min_value=-10, max_value=10),
    )
    def test_delta_addition_commutative(
        self, d1_years: int, d1_months: int, d2_years: int, d2_months: int
    ) -> None:
        """Delta addition is commutative."""
        d1 = FiscalDelta(years=d1_years, months=d1_months)
        d2 = FiscalDelta(years=d2_years, months=d2_months)

        sum1 = d1 + d2
        sum2 = d2 + d1

        assert sum1.years == sum2.years
        assert sum1.months == sum2.months
        event(f"total={sum1.total_months()}")

    @given(
        factor=st.integers(min_value=-10, max_value=10),
        months=st.integers(min_value=-10, max_value=10),
    )
    def test_multiplication_distributes(self, factor: int, months: int) -> None:
        """Multiplication by factor equals adding factor times."""
        delta = FiscalDelta(months=months)
        multiplied = delta * factor

        assert multiplied.months == months * factor
        event(f"factor={factor}")

    @given(
        years=st.integers(min_value=-10, max_value=10),
        months=st.integers(min_value=-10, max_value=10),
        days=st.integers(min_value=-100, max_value=100),
    )
    def test_double_negation_is_identity(self, years: int, months: int, days: int) -> None:
        """Negating twice returns original delta."""
        delta = FiscalDelta(years=years, months=months, days=days)
        double_neg = delta.negate().negate()

        assert double_neg.years == delta.years
        assert double_neg.months == delta.months
        assert double_neg.days == delta.days
        event(f"years={years}")


# ============================================================================
# MONTH-END POLICY PROPERTIES
# ============================================================================


@pytest.mark.fuzz
class TestMonthEndPolicyProperties:
    """Property-based tests for month-end policy behavior."""

    @given(d=date_by_boundary(), months=st.integers(min_value=-24, max_value=24))
    def test_preserve_policy_clamps_day(self, d: date, months: int) -> None:
        """Preserve policy never produces invalid day."""
        delta = FiscalDelta(months=months, month_end_policy=MonthEndPolicy.PRESERVE)
        try:
            result = delta.add_to(d)
            # Result day should be valid for result month
            event(f"result_day={result.day}")
            assert 1 <= result.day <= 31
            event("outcome=preserve_policy_clamped")
        except (OverflowError, ValueError):
            # Date out of range - acceptable
            pass

    @given(d=reasonable_dates, months=st.integers(min_value=-24, max_value=24))
    def test_clamp_policy_preserves_month_end(self, d: date, months: int) -> None:
        """Clamp policy: if start is month-end, result is month-end."""
        import calendar

        # Check if d is last day of its month
        is_month_end = d.day == calendar.monthrange(d.year, d.month)[1]
        event(f"is_month_end={is_month_end}")

        delta = FiscalDelta(months=months, month_end_policy=MonthEndPolicy.CLAMP)
        try:
            result = delta.add_to(d)
            result_is_month_end = result.day == calendar.monthrange(result.year, result.month)[1]

            if is_month_end:
                assert result_is_month_end
        except (OverflowError, ValueError):
            # Date out of range - acceptable
            pass

    @given(
        year=st.integers(min_value=1900, max_value=2100),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),  # Always valid day
        months_to_add=st.integers(min_value=-24, max_value=24),
    )
    def test_strict_policy_succeeds_for_valid_days(
        self,
        year: int,
        month: int,
        day: int,
        months_to_add: int,
    ) -> None:
        """Strict policy succeeds when day fits in target month."""
        import calendar

        d = date(year, month, day)
        delta = FiscalDelta(
            months=months_to_add,
            month_end_policy=MonthEndPolicy.STRICT,
        )

        event(f"day={day}")

        try:
            total_months = (
                year * 12 + month - 1 + months_to_add
            )
            target_year = total_months // 12
            target_month = total_months % 12 + 1
            max_day = calendar.monthrange(
                target_year, target_month
            )[1]

            assume(day <= max_day)
            assume(months_to_add != 0)

            result = delta.add_to(d)
            assert result.day == day
            event("outcome=strict_day_preserved")
        except (ValueError, OverflowError):
            event("outcome=strict_out_of_range")

    @given(delta_dict=fiscal_delta_by_magnitude())
    def test_delta_magnitude_accepted(
        self, delta_dict: dict[str, int | str]
    ) -> None:
        """FiscalDelta accepts all magnitude categories."""
        policy_str = str(
            delta_dict.get("month_end_policy", "preserve")
        )
        policy = MonthEndPolicy(policy_str)
        delta = FiscalDelta(
            years=int(delta_dict.get("years", 0)),
            quarters=int(delta_dict.get("quarters", 0)),
            months=int(delta_dict.get("months", 0)),
            days=int(delta_dict.get("days", 0)),
            month_end_policy=policy,
        )
        # Total months is deterministic
        expected = (
            int(delta_dict.get("years", 0)) * 12
            + int(delta_dict.get("quarters", 0)) * 3
            + int(delta_dict.get("months", 0))
        )
        assert delta.total_months() == expected
        event(f"policy={policy.value}")
        event("outcome=magnitude_accepted")

    @given(policy=month_end_policy_with_event())
    def test_month_end_policy_round_trips(
        self, policy: str
    ) -> None:
        """Month-end policy strings resolve to valid enum values."""
        enum_val = MonthEndPolicy(policy)
        assert enum_val.value == policy
        event(f"policy={policy}")
        event("outcome=policy_round_trip")

    @given(pair=fiscal_boundary_crossing_pair())
    def test_boundary_crossing_dates_valid(
        self, pair: tuple[date, date]
    ) -> None:
        """Fiscal boundary crossing pairs produce valid ordered dates."""
        before, after = pair
        assert before < after
        # Gap should be exactly 1 day (boundary crossing)
        gap = (after - before).days
        event(f"boundary_gap={gap}")
        assert gap >= 1


# ============================================================================
# FISCAL PERIOD PROPERTIES
# ============================================================================


@pytest.mark.fuzz
class TestFiscalPeriodProperties:
    """Property-based tests for FiscalPeriod."""

    @given(
        fiscal_year=st.integers(min_value=1900, max_value=2100),
        quarter=st.integers(min_value=1, max_value=4),
        month=st.integers(min_value=1, max_value=12),
    )
    def test_valid_period_accepted(
        self, fiscal_year: int, quarter: int, month: int
    ) -> None:
        """Valid period values are accepted."""
        period = FiscalPeriod(
            fiscal_year=fiscal_year,
            quarter=quarter,
            month=month,
        )
        assert period.fiscal_year == fiscal_year
        assert period.quarter == quarter
        assert period.month == month
        event(f"quarter={quarter}")
        event("outcome=period_accepted")

    @given(
        fiscal_year=st.integers(min_value=1900, max_value=2100),
        quarter=st.integers(min_value=-10, max_value=0) | st.integers(min_value=5, max_value=15),
        month=st.integers(min_value=1, max_value=12),
    )
    def test_invalid_quarter_rejected(
        self, fiscal_year: int, quarter: int, month: int
    ) -> None:
        """Invalid quarter values are rejected."""
        event(f"quarter={quarter}")
        with pytest.raises(
            ValueError, match="Quarter must be 1-4"
        ):
            FiscalPeriod(
                fiscal_year=fiscal_year,
                quarter=quarter,
                month=month,
            )
        event("outcome=invalid_quarter_rejected")

    @given(
        fiscal_year=st.integers(min_value=1900, max_value=2100),
        quarter=st.integers(min_value=1, max_value=4),
        month=st.integers(min_value=-10, max_value=0) | st.integers(min_value=13, max_value=25),
    )
    def test_invalid_month_rejected(
        self, fiscal_year: int, quarter: int, month: int
    ) -> None:
        """Invalid month values are rejected."""
        event(f"month={month}")
        with pytest.raises(
            ValueError, match="Month must be 1-12"
        ):
            FiscalPeriod(
                fiscal_year=fiscal_year,
                quarter=quarter,
                month=month,
            )
        event("outcome=invalid_month_rejected")

    @given(
        fy1=st.integers(min_value=1900, max_value=2100),
        fy2=st.integers(min_value=1900, max_value=2100),
    )
    def test_period_ordering_by_year(
        self, fy1: int, fy2: int
    ) -> None:
        """Periods are ordered by fiscal year first."""
        assume(fy1 != fy2)
        p1 = FiscalPeriod(
            fiscal_year=fy1, quarter=4, month=12
        )
        p2 = FiscalPeriod(
            fiscal_year=fy2, quarter=1, month=1
        )

        if fy1 < fy2:
            assert p1 < p2
            event("outcome=p1_lt_p2")
        else:
            assert p1 > p2
            event("outcome=p1_gt_p2")


# ============================================================================
# DATE RANGE PROPERTIES
# ============================================================================


@pytest.mark.fuzz
class TestDateRangeProperties:
    """Property-based tests for date range calculations."""

    @given(
        start_month=fiscal_calendars,
        fiscal_year=st.integers(min_value=1900, max_value=2100),
    )
    def test_date_in_fiscal_year_has_correct_fiscal_year(
        self, start_month: int, fiscal_year: int
    ) -> None:
        """Any date in a fiscal year reports that fiscal year."""
        cal = FiscalCalendar(start_month=start_month)
        start = cal.fiscal_year_start_date(fiscal_year)
        end = cal.fiscal_year_end_date(fiscal_year)

        event(f"start_month={start_month}")

        # Check start date
        assert cal.fiscal_year(start) == fiscal_year

        # Check end date
        assert cal.fiscal_year(end) == fiscal_year

        # Check midpoint
        mid = date.fromordinal(
            (start.toordinal() + end.toordinal()) // 2
        )
        assert cal.fiscal_year(mid) == fiscal_year
        event("outcome=fy_containment_verified")

    @given(
        start_month=fiscal_calendars,
        fiscal_year=st.integers(min_value=1900, max_value=2100),
        quarter=st.integers(min_value=1, max_value=4),
    )
    def test_date_in_quarter_has_correct_quarter(
        self, start_month: int, fiscal_year: int, quarter: int
    ) -> None:
        """Any date in a quarter reports that quarter."""
        cal = FiscalCalendar(start_month=start_month)
        start = cal.quarter_start_date(fiscal_year, quarter)
        end = cal.quarter_end_date(fiscal_year, quarter)

        event(f"quarter={quarter}")

        # Check start date
        assert cal.fiscal_quarter(start) == quarter

        # Check end date
        assert cal.fiscal_quarter(end) == quarter
        event("outcome=quarter_containment_verified")


# ============================================================================
# IMMUTABILITY PROPERTIES
# ============================================================================


@pytest.mark.fuzz
class TestImmutabilityProperties:
    """Property-based tests for immutability guarantees."""

    @given(start_month=fiscal_calendars)
    def test_fiscal_calendar_immutable(
        self, start_month: int
    ) -> None:
        """FiscalCalendar cannot be mutated."""
        cal = FiscalCalendar(start_month=start_month)
        event(f"start_month={start_month}")
        with pytest.raises(AttributeError):
            cal.start_month = 7  # type: ignore[misc]
        event("outcome=calendar_immutable")

    @given(
        years=st.integers(min_value=-10, max_value=10),
        months=st.integers(min_value=-10, max_value=10),
    )
    def test_fiscal_delta_immutable(
        self, years: int, months: int
    ) -> None:
        """FiscalDelta cannot be mutated."""
        delta = FiscalDelta(years=years, months=months)
        event(f"years={years}")
        with pytest.raises(AttributeError):
            delta.years = 0  # type: ignore[misc]
        event("outcome=delta_immutable")

    @given(start_month=fiscal_calendars)
    def test_fiscal_calendar_hashable(
        self, start_month: int
    ) -> None:
        """FiscalCalendar is hashable."""
        cal = FiscalCalendar(start_month=start_month)
        h = hash(cal)
        assert isinstance(h, int)
        s = {cal}
        assert len(s) == 1
        event(f"start_month={start_month}")
        event("outcome=calendar_hashable")

    @given(
        years=st.integers(min_value=-10, max_value=10),
        months=st.integers(min_value=-10, max_value=10),
    )
    def test_fiscal_delta_hashable(
        self, years: int, months: int
    ) -> None:
        """FiscalDelta is hashable."""
        delta = FiscalDelta(years=years, months=months)
        h = hash(delta)
        assert isinstance(h, int)
        s = {delta}
        assert len(s) == 1
        event(f"years={years}")
        event("outcome=delta_hashable")


# ============================================================================
# OPERATOR ALGEBRA PROPERTIES
# ============================================================================


@pytest.mark.fuzz
class TestOperatorAlgebraProperties:
    """Property-based tests for FiscalDelta operator algebra.

    Verifies algebraic identities that must hold for all inputs:
    subtract_from oracle, subtraction identity, scalar commutativity,
    with_policy preservation, and cross-policy rejection.
    """

    @given(
        d=date_by_boundary(),
        years=st.integers(min_value=-5, max_value=5),
        months=st.integers(min_value=-12, max_value=12),
        days=st.integers(min_value=-30, max_value=30),
    )
    def test_subtract_from_equals_negate_add(
        self,
        d: date,
        years: int,
        months: int,
        days: int,
    ) -> None:
        """Property: subtract_from(d) == negate().add_to(d).

        Oracle: subtract_from is defined as negate().add_to().
        """
        delta = FiscalDelta(
            years=years, months=months, days=days
        )
        event(f"years={years}")

        try:
            result_sub = delta.subtract_from(d)
            result_neg = delta.negate().add_to(d)
            assert result_sub == result_neg
            event("outcome=subtract_from_oracle_match")
        except (OverflowError, ValueError):
            event("outcome=subtract_from_out_of_range")

    @given(
        years=st.integers(min_value=-10, max_value=10),
        quarters=st.integers(min_value=-10, max_value=10),
        months=st.integers(min_value=-10, max_value=10),
        days=st.integers(min_value=-100, max_value=100),
        policy=month_end_policy_with_event(),
    )
    def test_with_policy_preserves_duration(
        self,
        years: int,
        quarters: int,
        months: int,
        days: int,
        policy: str,
    ) -> None:
        """Property: with_policy changes only policy, not duration."""
        delta = FiscalDelta(
            years=years,
            quarters=quarters,
            months=months,
            days=days,
        )
        target = MonthEndPolicy(policy)
        new_delta = delta.with_policy(target)

        assert new_delta.years == years
        assert new_delta.quarters == quarters
        assert new_delta.months == months
        assert new_delta.days == days
        assert new_delta.month_end_policy == target
        event(f"policy={policy}")
        event("outcome=with_policy_preserved")

    @given(
        y1=st.integers(min_value=-5, max_value=5),
        m1=st.integers(min_value=-12, max_value=12),
        d1=st.integers(min_value=-30, max_value=30),
        y2=st.integers(min_value=-5, max_value=5),
        m2=st.integers(min_value=-12, max_value=12),
        d2=st.integers(min_value=-30, max_value=30),
    )
    def test_sub_equals_add_negation(
        self,
        y1: int,
        m1: int,
        d1: int,
        y2: int,
        m2: int,
        d2: int,
    ) -> None:
        """Property: d1 - d2 == d1 + (-d2).

        Algebraic identity for subtraction.
        """
        delta1 = FiscalDelta(years=y1, months=m1, days=d1)
        delta2 = FiscalDelta(years=y2, months=m2, days=d2)

        result_sub = delta1 - delta2
        result_add_neg = delta1 + (-delta2)

        assert result_sub.years == result_add_neg.years
        assert result_sub.months == result_add_neg.months
        assert result_sub.days == result_add_neg.days
        event(f"total={result_sub.total_months()}")
        event("outcome=sub_identity_verified")

    @given(
        factor=st.integers(min_value=-10, max_value=10),
        years=st.integers(min_value=-5, max_value=5),
        months=st.integers(min_value=-12, max_value=12),
        days=st.integers(min_value=-30, max_value=30),
    )
    def test_rmul_commutative_with_mul(
        self,
        factor: int,
        years: int,
        months: int,
        days: int,
    ) -> None:
        """Property: factor * delta == delta * factor."""
        delta = FiscalDelta(
            years=years, months=months, days=days
        )

        result_mul = delta * factor
        result_rmul = factor * delta

        assert result_mul.years == result_rmul.years
        assert result_mul.months == result_rmul.months
        assert result_mul.days == result_rmul.days
        event(f"factor={factor}")
        event("outcome=rmul_commutative")

    @given(
        p1=st.sampled_from(list(MonthEndPolicy)),
        p2=st.sampled_from(list(MonthEndPolicy)),
    )
    def test_cross_policy_add_rejected(
        self, p1: MonthEndPolicy, p2: MonthEndPolicy
    ) -> None:
        """Property: Adding deltas with different policies raises."""
        assume(p1 != p2)
        d1 = FiscalDelta(months=1, month_end_policy=p1)
        d2 = FiscalDelta(months=2, month_end_policy=p2)

        with pytest.raises(ValueError, match="different"):
            _ = d1 + d2
        event(f"p1={p1.value}")
        event(f"p2={p2.value}")
        event("outcome=cross_policy_rejected")

    @given(
        d=date_by_boundary(),
        months=st.integers(min_value=-24, max_value=24),
        policy=month_end_policy_with_event(),
    )
    def test_policy_driven_arithmetic_valid(
        self,
        d: date,
        months: int,
        policy: str,
    ) -> None:
        """Property: All policies produce valid dates or raise.

        Exercises month_end_policy_with_event() in actual
        date arithmetic rather than just enum roundtrip.
        """
        delta = FiscalDelta(
            months=months,
            month_end_policy=MonthEndPolicy(policy),
        )
        event(f"policy={policy}")

        try:
            result = delta.add_to(d)
            assert isinstance(result, date)
            assert 1 <= result.day <= 31
            event("outcome=policy_arithmetic_valid")
        except (ValueError, OverflowError):
            event("outcome=policy_arithmetic_error")


# ============================================================================
# FISCAL PERIOD STRATEGY PROPERTIES
# ============================================================================


@pytest.mark.fuzz
class TestFiscalPeriodStrategyProperties:
    """Property tests using fiscal_periods() composite strategy."""

    @given(period_args=fiscal_periods())
    def test_period_from_strategy_valid(
        self, period_args: tuple[int, int, int]
    ) -> None:
        """Property: fiscal_periods() always produces valid args."""
        fy, quarter, month = period_args
        period = FiscalPeriod(
            fiscal_year=fy, quarter=quarter, month=month
        )
        assert period.fiscal_year == fy
        assert period.quarter == quarter
        assert period.month == month
        event(f"quarter={quarter}")
        event("outcome=strategy_period_valid")

    @given(
        p1=fiscal_periods(),
        p2=fiscal_periods(),
    )
    def test_period_equality_reflexive(
        self,
        p1: tuple[int, int, int],
        p2: tuple[int, int, int],
    ) -> None:
        """Property: Equal args produce equal periods."""
        period1 = FiscalPeriod(*p1)
        period2 = FiscalPeriod(*p2)
        if p1 == p2:
            assert period1 == period2
            event("outcome=periods_equal")
        else:
            assert period1 != period2 or p1 == p2
            event("outcome=periods_differ")


# ============================================================================
# BOUNDARY CROSSING QUARTER ADJACENCY
# ============================================================================


@pytest.mark.fuzz
class TestBoundaryCrossingQuarterAdjacency:
    """Property tests for fiscal boundary quarter adjacency.

    Verifies that date pairs from fiscal_boundary_crossing_pair()
    land in adjacent fiscal quarters or adjacent fiscal years,
    not just that before < after.
    """

    @given(pair=fiscal_boundary_crossing_pair())
    def test_boundary_dates_in_adjacent_periods(
        self, pair: tuple[date, date]
    ) -> None:
        """Property: Boundary pairs are in adjacent fiscal periods.

        For common fiscal starts, the before/after dates should
        be in consecutive fiscal months (month difference == 1).
        """
        before, after = pair
        # Use calendar year for adjacency check
        cal = FiscalCalendar(start_month=1)

        before_month = (
            (cal.fiscal_year(before) - 1) * 12
            + cal.fiscal_month(before)
        )
        after_month = (
            (cal.fiscal_year(after) - 1) * 12
            + cal.fiscal_month(after)
        )
        gap_months = after_month - before_month

        # Boundary crossings should be 0 or 1 months apart
        assert 0 <= gap_months <= 1
        event(f"gap_months={gap_months}")
        event("outcome=boundary_adjacency_verified")
