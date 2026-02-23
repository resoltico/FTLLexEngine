"""Tests for fiscal calendar arithmetic.

Tests cover:
- FiscalPeriod validation and comparison
- FiscalCalendar period calculations
- FiscalCalendar date methods: fiscal_year bounds (1-9999) enforcement
- FiscalDelta arithmetic
- FiscalDelta: bool rejection for numeric fields (__post_init__ and __mul__)
- Month-end policy behavior
- _add_months: result year range enforcement
- Convenience factory functions
"""

from datetime import date

import pytest

from ftllexengine.parsing import (
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


class TestFiscalPeriod:
    """Tests for FiscalPeriod dataclass."""

    def test_create_valid_period(self) -> None:
        """FiscalPeriod can be created with valid values."""
        period = FiscalPeriod(fiscal_year=2024, quarter=1, month=1)
        assert period.fiscal_year == 2024
        assert period.quarter == 1
        assert period.month == 1

    def test_immutable(self) -> None:
        """FiscalPeriod is immutable (frozen)."""
        period = FiscalPeriod(fiscal_year=2024, quarter=1, month=1)
        with pytest.raises(AttributeError):
            period.fiscal_year = 2025  # type: ignore[misc]

    def test_hashable(self) -> None:
        """FiscalPeriod is hashable."""
        period = FiscalPeriod(fiscal_year=2024, quarter=1, month=1)
        assert hash(period) is not None
        periods = {period}
        assert len(periods) == 1

    def test_equality(self) -> None:
        """FiscalPeriod instances with same values are equal."""
        p1 = FiscalPeriod(fiscal_year=2024, quarter=1, month=1)
        p2 = FiscalPeriod(fiscal_year=2024, quarter=1, month=1)
        assert p1 == p2

    def test_ordering(self) -> None:
        """FiscalPeriods are ordered by (year, quarter, month)."""
        p1 = FiscalPeriod(fiscal_year=2023, quarter=4, month=12)
        p2 = FiscalPeriod(fiscal_year=2024, quarter=1, month=1)
        p3 = FiscalPeriod(fiscal_year=2024, quarter=2, month=4)
        assert p1 < p2 < p3

    def test_invalid_quarter_low(self) -> None:
        """FiscalPeriod rejects quarter < 1."""
        with pytest.raises(ValueError, match="Quarter must be 1-4"):
            FiscalPeriod(fiscal_year=2024, quarter=0, month=1)

    def test_invalid_quarter_high(self) -> None:
        """FiscalPeriod rejects quarter > 4."""
        with pytest.raises(ValueError, match="Quarter must be 1-4"):
            FiscalPeriod(fiscal_year=2024, quarter=5, month=1)

    def test_invalid_month_low(self) -> None:
        """FiscalPeriod rejects month < 1."""
        with pytest.raises(ValueError, match="Month must be 1-12"):
            FiscalPeriod(fiscal_year=2024, quarter=1, month=0)

    def test_invalid_month_high(self) -> None:
        """FiscalPeriod rejects month > 12."""
        with pytest.raises(ValueError, match="Month must be 1-12"):
            FiscalPeriod(fiscal_year=2024, quarter=1, month=13)

    def test_invalid_fiscal_year_zero(self) -> None:
        """FiscalPeriod rejects fiscal_year=0 (not in 1-9999 range)."""
        with pytest.raises(ValueError, match="fiscal_year must be 1-9999"):
            FiscalPeriod(fiscal_year=0, quarter=1, month=1)

    def test_invalid_fiscal_year_negative(self) -> None:
        """FiscalPeriod rejects negative fiscal_year."""
        with pytest.raises(ValueError, match="fiscal_year must be 1-9999"):
            FiscalPeriod(fiscal_year=-1, quarter=1, month=1)

    def test_invalid_fiscal_year_too_large(self) -> None:
        """FiscalPeriod rejects fiscal_year > 9999 (beyond datetime.date range)."""
        with pytest.raises(ValueError, match="fiscal_year must be 1-9999"):
            FiscalPeriod(fiscal_year=10000, quarter=1, month=1)

    def test_valid_fiscal_year_boundaries(self) -> None:
        """FiscalPeriod accepts fiscal_year at its valid boundaries (1 and 9999)."""
        p_min = FiscalPeriod(fiscal_year=1, quarter=1, month=1)
        p_max = FiscalPeriod(fiscal_year=9999, quarter=4, month=12)
        assert p_min.fiscal_year == 1
        assert p_max.fiscal_year == 9999


class TestFiscalCalendar:
    """Tests for FiscalCalendar class."""

    def test_create_default(self) -> None:
        """FiscalCalendar defaults to calendar year (start_month=1)."""
        cal = FiscalCalendar()
        assert cal.start_month == 1

    def test_create_uk_fiscal(self) -> None:
        """FiscalCalendar can be created for UK fiscal year."""
        cal = FiscalCalendar(start_month=4)
        assert cal.start_month == 4

    def test_immutable(self) -> None:
        """FiscalCalendar is immutable (frozen)."""
        cal = FiscalCalendar()
        with pytest.raises(AttributeError):
            cal.start_month = 7  # type: ignore[misc]

    def test_hashable(self) -> None:
        """FiscalCalendar is hashable."""
        cal = FiscalCalendar(start_month=4)
        assert hash(cal) is not None
        calendars = {cal}
        assert len(calendars) == 1

    def test_invalid_start_month_low(self) -> None:
        """FiscalCalendar rejects start_month < 1."""
        with pytest.raises(ValueError, match="start_month must be 1-12"):
            FiscalCalendar(start_month=0)

    def test_invalid_start_month_high(self) -> None:
        """FiscalCalendar rejects start_month > 12."""
        with pytest.raises(ValueError, match="start_month must be 1-12"):
            FiscalCalendar(start_month=13)

    def test_invalid_start_month_type(self) -> None:
        """FiscalCalendar rejects non-integer start_month."""
        with pytest.raises(TypeError, match="start_month must be int"):
            FiscalCalendar(start_month="4")  # type: ignore[arg-type]


class TestFiscalCalendarCalendarYear:
    """Tests for FiscalCalendar with calendar year (start_month=1)."""

    def setup_method(self) -> None:
        """Create calendar year fiscal calendar."""
        self.cal = FiscalCalendar(start_month=1)

    def test_fiscal_year(self) -> None:
        """Fiscal year matches calendar year for calendar year fiscal."""
        assert self.cal.fiscal_year(date(2024, 1, 1)) == 2024
        assert self.cal.fiscal_year(date(2024, 6, 15)) == 2024
        assert self.cal.fiscal_year(date(2024, 12, 31)) == 2024

    def test_fiscal_quarter(self) -> None:
        """Fiscal quarters match calendar quarters."""
        assert self.cal.fiscal_quarter(date(2024, 1, 15)) == 1
        assert self.cal.fiscal_quarter(date(2024, 4, 15)) == 2
        assert self.cal.fiscal_quarter(date(2024, 7, 15)) == 3
        assert self.cal.fiscal_quarter(date(2024, 10, 15)) == 4

    def test_fiscal_month(self) -> None:
        """Fiscal months match calendar months."""
        assert self.cal.fiscal_month(date(2024, 1, 15)) == 1
        assert self.cal.fiscal_month(date(2024, 6, 15)) == 6
        assert self.cal.fiscal_month(date(2024, 12, 15)) == 12

    def test_fiscal_year_start_date(self) -> None:
        """Fiscal year starts on January 1."""
        assert self.cal.fiscal_year_start_date(2024) == date(2024, 1, 1)

    def test_fiscal_year_end_date(self) -> None:
        """Fiscal year ends on December 31."""
        assert self.cal.fiscal_year_end_date(2024) == date(2024, 12, 31)

    def test_quarter_start_date(self) -> None:
        """Quarter start dates match calendar quarters."""
        assert self.cal.quarter_start_date(2024, 1) == date(2024, 1, 1)
        assert self.cal.quarter_start_date(2024, 2) == date(2024, 4, 1)
        assert self.cal.quarter_start_date(2024, 3) == date(2024, 7, 1)
        assert self.cal.quarter_start_date(2024, 4) == date(2024, 10, 1)

    def test_quarter_end_date(self) -> None:
        """Quarter end dates match calendar quarters."""
        assert self.cal.quarter_end_date(2024, 1) == date(2024, 3, 31)
        assert self.cal.quarter_end_date(2024, 2) == date(2024, 6, 30)
        assert self.cal.quarter_end_date(2024, 3) == date(2024, 9, 30)
        assert self.cal.quarter_end_date(2024, 4) == date(2024, 12, 31)


class TestFiscalCalendarAprilStart:
    """Tests for FiscalCalendar with April start (UK fiscal)."""

    def setup_method(self) -> None:
        """Create UK fiscal calendar."""
        self.cal = FiscalCalendar(start_month=4)

    def test_fiscal_year_before_april(self) -> None:
        """Dates before April belong to previous fiscal year label."""
        assert self.cal.fiscal_year(date(2024, 3, 31)) == 2024
        assert self.cal.fiscal_year(date(2024, 1, 1)) == 2024

    def test_fiscal_year_from_april(self) -> None:
        """Dates from April belong to next fiscal year label."""
        assert self.cal.fiscal_year(date(2024, 4, 1)) == 2025
        assert self.cal.fiscal_year(date(2024, 12, 31)) == 2025

    def test_fiscal_quarter(self) -> None:
        """Fiscal quarters for April-March year."""
        # Quarter 1 covers April through June
        assert self.cal.fiscal_quarter(date(2024, 4, 15)) == 1
        assert self.cal.fiscal_quarter(date(2024, 6, 30)) == 1
        # Quarter 2 covers July through September
        assert self.cal.fiscal_quarter(date(2024, 7, 1)) == 2
        assert self.cal.fiscal_quarter(date(2024, 9, 30)) == 2
        # Quarter 3 covers October through December
        assert self.cal.fiscal_quarter(date(2024, 10, 1)) == 3
        assert self.cal.fiscal_quarter(date(2024, 12, 31)) == 3
        # Quarter 4 covers January through March (next calendar year)
        assert self.cal.fiscal_quarter(date(2025, 1, 1)) == 4
        assert self.cal.fiscal_quarter(date(2025, 3, 31)) == 4

    def test_fiscal_month(self) -> None:
        """Fiscal months for April-March year."""
        assert self.cal.fiscal_month(date(2024, 4, 15)) == 1
        assert self.cal.fiscal_month(date(2024, 5, 15)) == 2
        assert self.cal.fiscal_month(date(2024, 12, 15)) == 9
        assert self.cal.fiscal_month(date(2025, 1, 15)) == 10
        assert self.cal.fiscal_month(date(2025, 3, 15)) == 12

    def test_fiscal_year_start_date(self) -> None:
        """FY2025 starts April 1, 2024."""
        assert self.cal.fiscal_year_start_date(2025) == date(2024, 4, 1)

    def test_fiscal_year_end_date(self) -> None:
        """FY2025 ends March 31, 2025."""
        assert self.cal.fiscal_year_end_date(2025) == date(2025, 3, 31)

    def test_quarter_start_date(self) -> None:
        """Quarter start dates for April-March year."""
        assert self.cal.quarter_start_date(2025, 1) == date(2024, 4, 1)
        assert self.cal.quarter_start_date(2025, 2) == date(2024, 7, 1)
        assert self.cal.quarter_start_date(2025, 3) == date(2024, 10, 1)
        assert self.cal.quarter_start_date(2025, 4) == date(2025, 1, 1)

    def test_quarter_end_date(self) -> None:
        """Quarter end dates for April-March year."""
        assert self.cal.quarter_end_date(2025, 1) == date(2024, 6, 30)
        assert self.cal.quarter_end_date(2025, 2) == date(2024, 9, 30)
        assert self.cal.quarter_end_date(2025, 3) == date(2024, 12, 31)
        assert self.cal.quarter_end_date(2025, 4) == date(2025, 3, 31)

    def test_fiscal_period(self) -> None:
        """fiscal_period returns complete FiscalPeriod."""
        period = self.cal.fiscal_period(date(2024, 7, 15))
        assert period.fiscal_year == 2025
        assert period.quarter == 2
        assert period.month == 4


class TestFiscalCalendarJulyStart:
    """Tests for FiscalCalendar with July start (Australia)."""

    def setup_method(self) -> None:
        """Create Australian fiscal calendar."""
        self.cal = FiscalCalendar(start_month=7)

    def test_fiscal_year(self) -> None:
        """Fiscal year for July-June year."""
        # Before July: FY2024
        assert self.cal.fiscal_year(date(2024, 6, 30)) == 2024
        # From July: FY2025
        assert self.cal.fiscal_year(date(2024, 7, 1)) == 2025

    def test_fiscal_year_start_date(self) -> None:
        """FY2025 starts July 1, 2024."""
        assert self.cal.fiscal_year_start_date(2025) == date(2024, 7, 1)

    def test_fiscal_year_end_date(self) -> None:
        """FY2025 ends June 30, 2025."""
        assert self.cal.fiscal_year_end_date(2025) == date(2025, 6, 30)


class TestFiscalCalendarOctoberStart:
    """Tests for FiscalCalendar with October start (US Federal)."""

    def setup_method(self) -> None:
        """Create US Federal fiscal calendar."""
        self.cal = FiscalCalendar(start_month=10)

    def test_fiscal_year(self) -> None:
        """Fiscal year for October-September year."""
        # Before October: FY2024
        assert self.cal.fiscal_year(date(2024, 9, 30)) == 2024
        # From October: FY2025
        assert self.cal.fiscal_year(date(2024, 10, 1)) == 2025

    def test_fiscal_year_start_date(self) -> None:
        """FY2025 starts October 1, 2024."""
        assert self.cal.fiscal_year_start_date(2025) == date(2024, 10, 1)

    def test_fiscal_year_end_date(self) -> None:
        """FY2025 ends September 30, 2025."""
        assert self.cal.fiscal_year_end_date(2025) == date(2025, 9, 30)


class TestFiscalCalendarInvalidQuarter:
    """Tests for invalid quarter arguments."""

    def setup_method(self) -> None:
        """Create fiscal calendar."""
        self.cal = FiscalCalendar()

    def test_quarter_start_date_invalid_low(self) -> None:
        """quarter_start_date rejects quarter < 1."""
        with pytest.raises(ValueError, match="Quarter must be 1-4"):
            self.cal.quarter_start_date(2024, 0)

    def test_quarter_start_date_invalid_high(self) -> None:
        """quarter_start_date rejects quarter > 4."""
        with pytest.raises(ValueError, match="Quarter must be 1-4"):
            self.cal.quarter_start_date(2024, 5)

    def test_quarter_end_date_invalid_low(self) -> None:
        """quarter_end_date rejects quarter < 1."""
        with pytest.raises(ValueError, match="Quarter must be 1-4"):
            self.cal.quarter_end_date(2024, 0)

    def test_quarter_end_date_invalid_high(self) -> None:
        """quarter_end_date rejects quarter > 4."""
        with pytest.raises(ValueError, match="Quarter must be 1-4"):
            self.cal.quarter_end_date(2024, 5)


class TestFiscalDelta:
    """Tests for FiscalDelta class."""

    def test_create_default(self) -> None:
        """FiscalDelta defaults to zero delta."""
        delta = FiscalDelta()
        assert delta.years == 0
        assert delta.quarters == 0
        assert delta.months == 0
        assert delta.days == 0
        assert delta.month_end_policy == MonthEndPolicy.PRESERVE

    def test_create_with_values(self) -> None:
        """FiscalDelta can be created with values."""
        delta = FiscalDelta(years=1, quarters=2, months=3, days=4)
        assert delta.years == 1
        assert delta.quarters == 2
        assert delta.months == 3
        assert delta.days == 4

    def test_immutable(self) -> None:
        """FiscalDelta is immutable (frozen)."""
        delta = FiscalDelta(months=1)
        with pytest.raises(AttributeError):
            delta.months = 2  # type: ignore[misc]

    def test_hashable(self) -> None:
        """FiscalDelta is hashable."""
        delta = FiscalDelta(months=1)
        assert hash(delta) is not None
        deltas = {delta}
        assert len(deltas) == 1

    def test_total_months(self) -> None:
        """total_months calculates correctly."""
        delta = FiscalDelta(years=1, quarters=2, months=3)
        # 1*12 + 2*3 + 3 = 12 + 6 + 3 = 21
        assert delta.total_months() == 21

    def test_total_months_negative(self) -> None:
        """total_months works with negative values."""
        delta = FiscalDelta(years=-1, quarters=-1, months=-1)
        # -1*12 + -1*3 + -1 = -12 - 3 - 1 = -16
        assert delta.total_months() == -16

    def test_invalid_years_type(self) -> None:
        """FiscalDelta rejects non-integer years."""
        with pytest.raises(TypeError, match="years must be int"):
            FiscalDelta(years="1")  # type: ignore[arg-type]

    def test_invalid_quarters_type(self) -> None:
        """FiscalDelta rejects non-integer quarters."""
        with pytest.raises(TypeError, match="quarters must be int"):
            FiscalDelta(quarters=1.5)  # type: ignore[arg-type]

    def test_invalid_months_type(self) -> None:
        """FiscalDelta rejects non-integer months."""
        with pytest.raises(TypeError, match="months must be int"):
            FiscalDelta(months=None)  # type: ignore[arg-type]

    def test_invalid_days_type(self) -> None:
        """FiscalDelta rejects non-integer days."""
        with pytest.raises(TypeError, match="days must be int"):
            FiscalDelta(days=[1, 2])  # type: ignore[arg-type]


class TestFiscalDeltaArithmetic:
    """Tests for FiscalDelta arithmetic operations."""

    def test_add_months_simple(self) -> None:
        """Add months to a date."""
        delta = FiscalDelta(months=1)
        result = delta.add_to(date(2024, 1, 15))
        assert result == date(2024, 2, 15)

    def test_add_months_year_boundary(self) -> None:
        """Add months across year boundary."""
        delta = FiscalDelta(months=3)
        result = delta.add_to(date(2024, 11, 15))
        assert result == date(2025, 2, 15)

    def test_add_years(self) -> None:
        """Add years to a date."""
        delta = FiscalDelta(years=2)
        result = delta.add_to(date(2024, 6, 15))
        assert result == date(2026, 6, 15)

    def test_add_quarters(self) -> None:
        """Add quarters to a date."""
        delta = FiscalDelta(quarters=1)
        result = delta.add_to(date(2024, 1, 15))
        assert result == date(2024, 4, 15)

    def test_add_days(self) -> None:
        """Add days to a date."""
        delta = FiscalDelta(days=10)
        result = delta.add_to(date(2024, 1, 20))
        assert result == date(2024, 1, 30)

    def test_add_combined(self) -> None:
        """Add years, months, and days."""
        delta = FiscalDelta(years=1, months=2, days=5)
        result = delta.add_to(date(2024, 1, 15))
        # 2024-01-15 + 1y = 2025-01-15
        # 2025-01-15 + 2m = 2025-03-15
        # 2025-03-15 + 5d = 2025-03-20
        assert result == date(2025, 3, 20)

    def test_subtract_from(self) -> None:
        """Subtract delta from a date."""
        delta = FiscalDelta(months=1)
        result = delta.subtract_from(date(2024, 3, 15))
        assert result == date(2024, 2, 15)

    def test_negate(self) -> None:
        """Negate a delta."""
        delta = FiscalDelta(years=1, months=2, days=3)
        neg = delta.negate()
        assert neg.years == -1
        assert neg.months == -2
        assert neg.days == -3

    def test_neg_operator(self) -> None:
        """Use -delta operator."""
        delta = FiscalDelta(months=1)
        neg = -delta
        assert neg.months == -1

    def test_add_deltas(self) -> None:
        """Add two deltas."""
        d1 = FiscalDelta(months=1, days=5)
        d2 = FiscalDelta(months=2, days=10)
        result = d1 + d2
        assert result.months == 3
        assert result.days == 15

    def test_subtract_deltas(self) -> None:
        """Subtract two deltas."""
        d1 = FiscalDelta(months=3, days=15)
        d2 = FiscalDelta(months=1, days=5)
        result = d1 - d2
        assert result.months == 2
        assert result.days == 10

    def test_multiply_delta(self) -> None:
        """Multiply delta by integer."""
        delta = FiscalDelta(months=1, days=5)
        result = delta * 3
        assert result.months == 3
        assert result.days == 15

    def test_rmultiply_delta(self) -> None:
        """Reverse multiply delta by integer."""
        delta = FiscalDelta(months=1)
        result = 3 * delta
        assert result.months == 3

    def test_add_with_incompatible_type(self) -> None:
        """Adding FiscalDelta to non-FiscalDelta returns NotImplemented."""
        delta = FiscalDelta(months=1)
        # Direct dunder call needed to test NotImplemented return value
        result = delta.__add__(5)  # type: ignore[operator]  # pylint: disable=unnecessary-dunder-call
        assert result is NotImplemented

    def test_subtract_with_incompatible_type(self) -> None:
        """Subtracting non-FiscalDelta from FiscalDelta returns NotImplemented."""
        delta = FiscalDelta(months=1)
        # Direct dunder call needed to test NotImplemented return value
        result = delta.__sub__("invalid")  # type: ignore[operator]  # pylint: disable=unnecessary-dunder-call
        assert result is NotImplemented

    def test_multiply_with_incompatible_type(self) -> None:
        """Multiplying FiscalDelta by non-integer returns NotImplemented."""
        delta = FiscalDelta(months=1)
        # Direct dunder call needed to test NotImplemented return value
        result = delta.__mul__(1.5)  # type: ignore[operator]  # pylint: disable=unnecessary-dunder-call
        assert result is NotImplemented


class TestMonthEndPolicyPreserve:
    """Tests for MonthEndPolicy.PRESERVE (default)."""

    def test_day_preserved_when_possible(self) -> None:
        """Day is preserved when target month has same day."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.PRESERVE)
        result = delta.add_to(date(2024, 1, 15))
        assert result == date(2024, 2, 15)

    def test_day_clamped_when_overflow(self) -> None:
        """Day is clamped when target month has fewer days."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.PRESERVE)
        # Jan 31 -> Feb (max 29 in 2024 leap year)
        result = delta.add_to(date(2024, 1, 31))
        assert result == date(2024, 2, 29)

    def test_day_clamped_non_leap_year(self) -> None:
        """Day is clamped in non-leap year February."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.PRESERVE)
        # Jan 30 -> Feb 28 in 2023 (non-leap)
        result = delta.add_to(date(2023, 1, 30))
        assert result == date(2023, 2, 28)


class TestMonthEndPolicyClamp:
    """Tests for MonthEndPolicy.CLAMP."""

    def test_month_end_stays_month_end(self) -> None:
        """Month-end date results in month-end."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.CLAMP)
        # Jan 31 (month-end) -> Feb 29 (month-end in 2024)
        result = delta.add_to(date(2024, 1, 31))
        assert result == date(2024, 2, 29)

    def test_non_month_end_preserved(self) -> None:
        """Non-month-end date preserves day when possible."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.CLAMP)
        # Jan 15 (not month-end) -> Feb 15
        result = delta.add_to(date(2024, 1, 15))
        assert result == date(2024, 2, 15)

    def test_month_end_to_shorter_month(self) -> None:
        """Month-end to shorter month lands on month-end."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.CLAMP)
        # Mar 31 (month-end) -> Apr 30 (month-end)
        result = delta.add_to(date(2024, 3, 31))
        assert result == date(2024, 4, 30)

    def test_feb_end_to_march(self) -> None:
        """Feb 29 (month-end) -> Mar 31 (month-end)."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.CLAMP)
        result = delta.add_to(date(2024, 2, 29))
        assert result == date(2024, 3, 31)


class TestMonthEndPolicyStrict:
    """Tests for MonthEndPolicy.STRICT."""

    def test_valid_day_preserved(self) -> None:
        """Valid day is preserved in strict mode."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.STRICT)
        result = delta.add_to(date(2024, 1, 15))
        assert result == date(2024, 2, 15)

    def test_overflow_raises_error(self) -> None:
        """Overflow raises ValueError in strict mode."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.STRICT)
        with pytest.raises(ValueError, match="Day 31 does not exist"):
            delta.add_to(date(2024, 1, 31))

    def test_overflow_error_message(self) -> None:
        """Error message includes day and month details."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.STRICT)
        with pytest.raises(ValueError, match="Day 31 does not exist") as exc_info:
            delta.add_to(date(2024, 1, 31))
        assert "31" in str(exc_info.value)
        assert "2024-02" in str(exc_info.value)

    def test_strict_with_last_day_of_month(self) -> None:
        """Strict mode succeeds when last day fits in target month."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.STRICT)
        # June 30 + 1 month = July 31 (valid, target month has 31 days)
        result = delta.add_to(date(2024, 6, 30))
        assert result == date(2024, 7, 30)

    def test_strict_with_negative_months(self) -> None:
        """Strict mode works with negative month deltas."""
        delta = FiscalDelta(months=-1, month_end_policy=MonthEndPolicy.STRICT)
        result = delta.add_to(date(2024, 3, 15))
        assert result == date(2024, 2, 15)

    def test_strict_overflow_with_negative_months(self) -> None:
        """Strict mode raises ValueError with negative months when day overflows."""
        delta = FiscalDelta(months=-1, month_end_policy=MonthEndPolicy.STRICT)
        # March 31 - 1 month = Feb (max 29 in 2024), should raise
        with pytest.raises(ValueError, match="Day 31 does not exist"):
            delta.add_to(date(2024, 3, 31))

    def test_strict_with_zero_months(self) -> None:
        """Strict mode with zero months returns same date."""
        delta = FiscalDelta(months=0, month_end_policy=MonthEndPolicy.STRICT)
        result = delta.add_to(date(2024, 1, 31))
        assert result == date(2024, 1, 31)

    def test_strict_day_equals_max_day(self) -> None:
        """Strict mode succeeds when day equals max day of target month."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.STRICT)
        # Feb 28 (non-leap year) + 1 month = Mar 28 (valid)
        result = delta.add_to(date(2023, 2, 28))
        assert result == date(2023, 3, 28)

    def test_strict_day_exactly_at_boundary(self) -> None:
        """Strict mode succeeds when day exactly equals target month max day."""
        delta = FiscalDelta(months=2, month_end_policy=MonthEndPolicy.STRICT)
        # Jan 28 + 2 months = Mar 28 (valid, 28 <= 31)
        result = delta.add_to(date(2024, 1, 28))
        assert result == date(2024, 3, 28)

    def test_strict_preserves_day_when_valid(self) -> None:
        """Strict mode preserves day number when target month has enough days."""
        delta = FiscalDelta(months=3, month_end_policy=MonthEndPolicy.STRICT)
        # Nov 30 + 3 months = Feb 30 (doesn't exist in any year)
        # First try a valid case: May 15 + 3 months = Aug 15
        result = delta.add_to(date(2024, 5, 15))
        assert result == date(2024, 8, 15)
        assert result.day == 15  # Day preserved

    def test_strict_with_years_component(self) -> None:
        """Strict mode works with years component in delta."""
        delta = FiscalDelta(years=1, months=1, month_end_policy=MonthEndPolicy.STRICT)
        result = delta.add_to(date(2024, 1, 15))
        assert result == date(2025, 2, 15)

    def test_strict_policy_day_less_than_target_max(self) -> None:
        """Strict policy when source day is less than target month max day."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.STRICT)
        # Jan 1 + 1 month = Feb 1 (1 is definitely < 29, the min Feb days)
        result = delta.add_to(date(2024, 1, 1))
        assert result == date(2024, 2, 1)
        assert result.day == 1

    def test_strict_policy_with_combined_delta(self) -> None:
        """Strict policy with combined years, quarters, months, and days."""
        delta = FiscalDelta(
            years=1, quarters=1, months=1, days=10, month_end_policy=MonthEndPolicy.STRICT
        )
        # Jan 5 + 1y 1q 1m 10d = Jan 5 + 16 months + 10 days = May 15
        result = delta.add_to(date(2024, 1, 5))
        # 2024-01-05 + 16 months = 2025-05-05 + 10 days = 2025-05-15
        assert result == date(2025, 5, 15)


class TestConvenienceFunctions:
    """Tests for convenience factory functions."""

    def test_fiscal_quarter_calendar_year(self) -> None:
        """fiscal_quarter with calendar year."""
        assert fiscal_quarter(date(2024, 1, 15)) == 1
        assert fiscal_quarter(date(2024, 4, 15)) == 2
        assert fiscal_quarter(date(2024, 7, 15)) == 3
        assert fiscal_quarter(date(2024, 10, 15)) == 4

    def test_fiscal_quarter_uk_fiscal(self) -> None:
        """fiscal_quarter with UK fiscal year."""
        assert fiscal_quarter(date(2024, 4, 15), start_month=4) == 1
        assert fiscal_quarter(date(2024, 7, 15), start_month=4) == 2
        assert fiscal_quarter(date(2024, 10, 15), start_month=4) == 3
        assert fiscal_quarter(date(2025, 1, 15), start_month=4) == 4

    def test_fiscal_year_calendar_year(self) -> None:
        """fiscal_year with calendar year."""
        assert fiscal_year(date(2024, 1, 15)) == 2024
        assert fiscal_year(date(2024, 6, 15)) == 2024
        assert fiscal_year(date(2024, 12, 31)) == 2024

    def test_fiscal_year_uk_fiscal(self) -> None:
        """fiscal_year with UK fiscal year."""
        assert fiscal_year(date(2024, 3, 15), start_month=4) == 2024
        assert fiscal_year(date(2024, 4, 1), start_month=4) == 2025

    def test_fiscal_month_calendar_year(self) -> None:
        """fiscal_month with calendar year."""
        assert fiscal_month(date(2024, 1, 15)) == 1
        assert fiscal_month(date(2024, 6, 15)) == 6
        assert fiscal_month(date(2024, 12, 15)) == 12

    def test_fiscal_month_uk_fiscal(self) -> None:
        """fiscal_month with UK fiscal year."""
        assert fiscal_month(date(2024, 4, 15), start_month=4) == 1
        assert fiscal_month(date(2024, 3, 15), start_month=4) == 12

    def test_fiscal_year_start_calendar_year(self) -> None:
        """fiscal_year_start with calendar year."""
        assert fiscal_year_start(2024) == date(2024, 1, 1)

    def test_fiscal_year_start_uk_fiscal(self) -> None:
        """fiscal_year_start with UK fiscal year."""
        assert fiscal_year_start(2025, start_month=4) == date(2024, 4, 1)

    def test_fiscal_year_end_calendar_year(self) -> None:
        """fiscal_year_end with calendar year."""
        assert fiscal_year_end(2024) == date(2024, 12, 31)

    def test_fiscal_year_end_uk_fiscal(self) -> None:
        """fiscal_year_end with UK fiscal year."""
        assert fiscal_year_end(2025, start_month=4) == date(2025, 3, 31)


class TestMonthEndPolicyEnum:
    """Tests for MonthEndPolicy enum."""

    def test_enum_values(self) -> None:
        """MonthEndPolicy has correct string values."""
        assert MonthEndPolicy.PRESERVE.value == "preserve"
        assert MonthEndPolicy.CLAMP.value == "clamp"
        assert MonthEndPolicy.STRICT.value == "strict"

    def test_enum_is_str(self) -> None:
        """MonthEndPolicy values are strings (StrEnum)."""
        assert isinstance(MonthEndPolicy.PRESERVE, str)
        assert isinstance(MonthEndPolicy.CLAMP, str)
        assert isinstance(MonthEndPolicy.STRICT, str)


class TestEdgeCases:
    """Tests for edge cases."""

    def test_leap_year_feb_29(self) -> None:
        """Handle Feb 29 in leap year."""
        delta = FiscalDelta(years=1)
        # 2024 is leap year, 2025 is not
        # Feb 29, 2024 + 1 year -> Feb 28, 2025 (clamped)
        result = delta.add_to(date(2024, 2, 29))
        assert result == date(2025, 2, 28)

    def test_negative_months(self) -> None:
        """Handle negative months."""
        delta = FiscalDelta(months=-1)
        result = delta.add_to(date(2024, 3, 15))
        assert result == date(2024, 2, 15)

    def test_zero_delta(self) -> None:
        """Zero delta returns same date."""
        delta = FiscalDelta()
        result = delta.add_to(date(2024, 6, 15))
        assert result == date(2024, 6, 15)

    def test_large_delta(self) -> None:
        """Handle large delta values."""
        delta = FiscalDelta(years=100)
        result = delta.add_to(date(2024, 6, 15))
        assert result == date(2124, 6, 15)

    def test_all_month_end_policies_exercise_match(self) -> None:
        """Exercise all paths through month-end policy match statement."""
        # Test that we exercise all three enum values in the match statement
        test_date = date(2024, 1, 15)

        # PRESERVE path
        delta_preserve = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.PRESERVE)
        result_preserve = delta_preserve.add_to(test_date)
        assert result_preserve == date(2024, 2, 15)

        # CLAMP path
        delta_clamp = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.CLAMP)
        result_clamp = delta_clamp.add_to(test_date)
        assert result_clamp == date(2024, 2, 15)

        # STRICT path (success case)
        delta_strict = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.STRICT)
        result_strict = delta_strict.add_to(test_date)
        assert result_strict == date(2024, 2, 15)


class TestFiscalDeltaMonthEndPolicyValidation:
    """Tests for FiscalDelta month_end_policy validation (SEC-INPUT-VALIDATION-002 fix)."""

    def test_valid_policy_preserve(self) -> None:
        """FiscalDelta accepts MonthEndPolicy.PRESERVE."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.PRESERVE)
        assert delta.month_end_policy == MonthEndPolicy.PRESERVE

    def test_valid_policy_clamp(self) -> None:
        """FiscalDelta accepts MonthEndPolicy.CLAMP."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.CLAMP)
        assert delta.month_end_policy == MonthEndPolicy.CLAMP

    def test_valid_policy_strict(self) -> None:
        """FiscalDelta accepts MonthEndPolicy.STRICT."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.STRICT)
        assert delta.month_end_policy == MonthEndPolicy.STRICT

    def test_invalid_policy_string(self) -> None:
        """FiscalDelta rejects string month_end_policy."""
        with pytest.raises(TypeError, match="month_end_policy must be MonthEndPolicy"):
            FiscalDelta(months=1, month_end_policy="preserve")  # type: ignore[arg-type]

    def test_invalid_policy_none(self) -> None:
        """FiscalDelta rejects None month_end_policy."""
        with pytest.raises(TypeError, match="month_end_policy must be MonthEndPolicy"):
            FiscalDelta(months=1, month_end_policy=None)  # type: ignore[arg-type]

    def test_invalid_policy_int(self) -> None:
        """FiscalDelta rejects integer month_end_policy."""
        with pytest.raises(TypeError, match="month_end_policy must be MonthEndPolicy"):
            FiscalDelta(months=1, month_end_policy=1)  # type: ignore[arg-type]

    def test_invalid_policy_dict(self) -> None:
        """FiscalDelta rejects dict month_end_policy."""
        with pytest.raises(TypeError, match="month_end_policy must be MonthEndPolicy"):
            FiscalDelta(months=1, month_end_policy={})  # type: ignore[arg-type]

    def test_invalid_policy_error_message_includes_type(self) -> None:
        """Error message includes the actual type provided."""
        with pytest.raises(TypeError, match="got str"):
            FiscalDelta(months=1, month_end_policy="invalid")  # type: ignore[arg-type]

        with pytest.raises(TypeError, match="got NoneType"):
            FiscalDelta(months=1, month_end_policy=None)  # type: ignore[arg-type]


class TestAddMonthsDefensiveDefaultCase:
    """Tests for _add_months defensive default case (SEC-INPUT-VALIDATION-002 fix).

    These tests verify the defense-in-depth default case in the match statement.
    Under normal operation, FiscalDelta validation prevents invalid policies from
    reaching _add_months. These tests use internal access to bypass validation.
    """

    def test_internal_function_raises_for_unknown_policy(self) -> None:
        """_add_months raises ValueError for unknown policy (defense-in-depth).

        This tests the defensive default case in the match statement. The case
        should never be reached in normal operation because FiscalDelta validates
        the policy at construction time. This is defense-in-depth.
        """
        from ftllexengine.core.fiscal import _add_months

        # Create a mock "policy" that isn't a MonthEndPolicy enum member
        # This simulates a scenario where invalid data bypasses validation
        class FakePolicy:
            """Fake policy object to test default case."""

        with pytest.raises(ValueError, match="Unknown month_end_policy"):
            _add_months(date(2024, 1, 15), 1, FakePolicy())  # type: ignore[arg-type]

    def test_internal_function_raises_for_invalid_string_policy(self) -> None:
        """_add_months raises ValueError for invalid string policy.

        Note: MonthEndPolicy is a StrEnum, so valid string values like "preserve"
        will match the enum cases. Only truly invalid strings trigger the default.
        """
        from ftllexengine.core.fiscal import _add_months

        with pytest.raises(ValueError, match="Unknown month_end_policy"):
            _add_months(date(2024, 1, 15), 1, "invalid_policy")  # type: ignore[arg-type]

    def test_internal_function_raises_for_none_policy(self) -> None:
        """_add_months raises ValueError for None policy."""
        from ftllexengine.core.fiscal import _add_months

        with pytest.raises(ValueError, match="Unknown month_end_policy"):
            _add_months(date(2024, 1, 15), 1, None)  # type: ignore[arg-type]

    def test_internal_function_works_with_valid_policies(self) -> None:
        """_add_months works correctly with valid MonthEndPolicy values."""
        from ftllexengine.core.fiscal import _add_months

        # All valid policies should work without raising
        result_preserve = _add_months(
            date(2024, 1, 15), 1, MonthEndPolicy.PRESERVE
        )
        assert result_preserve == date(2024, 2, 15)

        result_clamp = _add_months(date(2024, 1, 15), 1, MonthEndPolicy.CLAMP)
        assert result_clamp == date(2024, 2, 15)

        result_strict = _add_months(date(2024, 1, 15), 1, MonthEndPolicy.STRICT)
        assert result_strict == date(2024, 2, 15)


# pylint: disable=unidiomatic-typecheck
# Reason: We intentionally use type() instead of isinstance() to verify exact type
# preservation - isinstance() would not distinguish between subclass and base class.
class TestFiscalDeltaSubclassPolymorphism:
    """Tests for FiscalDelta operator subclass preservation (v0.89.0 fix).

    Prior to v0.89.0, operators like __add__, __sub__, __mul__ hardcoded
    FiscalDelta constructor, breaking subclass polymorphism. Now they use
    type(self)(...) to preserve subclass type.
    """

    def test_add_preserves_subclass_type(self) -> None:
        """__add__ returns same type as self for subclasses."""

        class CustomDelta(FiscalDelta):
            """Subclass for testing polymorphism."""

            custom_attr: str = "test"

        delta1 = CustomDelta(months=1)
        delta2 = FiscalDelta(months=2)

        result = delta1 + delta2
        assert type(result) is CustomDelta
        assert result.months == 3

    def test_sub_preserves_subclass_type(self) -> None:
        """__sub__ returns same type as self for subclasses."""

        class CustomDelta(FiscalDelta):
            """Subclass for testing polymorphism."""


        delta1 = CustomDelta(months=5)
        delta2 = FiscalDelta(months=2)

        result = delta1 - delta2
        assert type(result) is CustomDelta
        assert result.months == 3

    def test_mul_preserves_subclass_type(self) -> None:
        """__mul__ returns same type as self for subclasses."""

        class CustomDelta(FiscalDelta):
            """Subclass for testing polymorphism."""


        delta = CustomDelta(months=2)

        result = delta * 3
        assert type(result) is CustomDelta
        assert result.months == 6

    def test_rmul_preserves_subclass_type(self) -> None:
        """__rmul__ returns same type as self for subclasses."""

        class CustomDelta(FiscalDelta):
            """Subclass for testing polymorphism."""


        delta = CustomDelta(months=2)

        result = 3 * delta
        assert type(result) is CustomDelta
        assert result.months == 6

    def test_neg_preserves_subclass_type(self) -> None:
        """__neg__ returns same type as self for subclasses."""

        class CustomDelta(FiscalDelta):
            """Subclass for testing polymorphism."""


        delta = CustomDelta(months=5, days=10)

        result = -delta
        assert type(result) is CustomDelta
        assert result.months == -5
        assert result.days == -10

    def test_negate_preserves_subclass_type(self) -> None:
        """negate() returns same type as self for subclasses."""

        class CustomDelta(FiscalDelta):
            """Subclass for testing polymorphism."""


        delta = CustomDelta(years=1, months=6)

        result = delta.negate()
        assert type(result) is CustomDelta
        assert result.years == -1
        assert result.months == -6

    def test_base_class_operations_return_base_type(self) -> None:
        """Base FiscalDelta operations return FiscalDelta type."""
        delta1 = FiscalDelta(months=1)
        delta2 = FiscalDelta(months=2)

        result_add = delta1 + delta2
        assert type(result_add) is FiscalDelta

        result_sub = delta1 - delta2
        assert type(result_sub) is FiscalDelta

        result_mul = delta1 * 2
        assert type(result_mul) is FiscalDelta

        result_neg = -delta1
        assert type(result_neg) is FiscalDelta

    def test_chained_operations_preserve_subclass(self) -> None:
        """Chained operations preserve subclass through entire chain."""

        class CustomDelta(FiscalDelta):
            """Subclass for testing polymorphism."""


        delta = CustomDelta(months=1)
        other = FiscalDelta(months=2)

        # Expression: (delta + other) * 2 - other = (1+2)*2 - 2 = 4
        result = (delta + other) * 2 - other
        assert type(result) is CustomDelta
        assert result.months == 4


class TestFiscalDeltaPolicyConflict:
    """Tests for FiscalDelta policy conflict detection (SEM-FISCAL-DELTA-POLICY-001 fix).

    Arithmetic operations now raise ValueError when operands have different
    month_end_policy values. Use with_policy() to normalize policies before arithmetic.
    """

    def test_add_same_policy_succeeds(self) -> None:
        """Adding deltas with same policy succeeds."""
        d1 = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.PRESERVE)
        d2 = FiscalDelta(months=2, month_end_policy=MonthEndPolicy.PRESERVE)
        result = d1 + d2
        assert result.months == 3
        assert result.month_end_policy == MonthEndPolicy.PRESERVE

    def test_add_different_policy_raises(self) -> None:
        """Adding deltas with different policies raises ValueError."""
        d1 = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.PRESERVE)
        d2 = FiscalDelta(months=2, month_end_policy=MonthEndPolicy.STRICT)
        with pytest.raises(ValueError, match="different month_end_policy"):
            _ = d1 + d2

    def test_add_policy_error_includes_values(self) -> None:
        """Error message includes both policy values."""
        d1 = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.CLAMP)
        d2 = FiscalDelta(months=2, month_end_policy=MonthEndPolicy.STRICT)
        with pytest.raises(ValueError, match="different month_end_policy") as exc_info:
            _ = d1 + d2
        assert "clamp" in str(exc_info.value)
        assert "strict" in str(exc_info.value)

    def test_sub_same_policy_succeeds(self) -> None:
        """Subtracting deltas with same policy succeeds."""
        d1 = FiscalDelta(months=5, month_end_policy=MonthEndPolicy.STRICT)
        d2 = FiscalDelta(months=2, month_end_policy=MonthEndPolicy.STRICT)
        result = d1 - d2
        assert result.months == 3
        assert result.month_end_policy == MonthEndPolicy.STRICT

    def test_sub_different_policy_raises(self) -> None:
        """Subtracting deltas with different policies raises ValueError."""
        d1 = FiscalDelta(months=5, month_end_policy=MonthEndPolicy.CLAMP)
        d2 = FiscalDelta(months=2, month_end_policy=MonthEndPolicy.PRESERVE)
        with pytest.raises(ValueError, match="different month_end_policy"):
            _ = d1 - d2

    def test_all_policy_combinations_detected(self) -> None:
        """All three policies conflict with each other when different."""
        policies = [MonthEndPolicy.PRESERVE, MonthEndPolicy.CLAMP, MonthEndPolicy.STRICT]
        for p1 in policies:
            for p2 in policies:
                d1 = FiscalDelta(months=1, month_end_policy=p1)
                d2 = FiscalDelta(months=1, month_end_policy=p2)
                if p1 == p2:
                    # Same policy: should succeed
                    result = d1 + d2
                    assert result.month_end_policy == p1
                else:
                    # Different policy: should raise
                    with pytest.raises(ValueError, match="different month_end_policy"):
                        _ = d1 + d2


class TestFiscalDeltaWithPolicy:
    """Tests for FiscalDelta.with_policy() method (SEM-FISCAL-DELTA-POLICY-001 fix).

    The with_policy() method creates a copy with a different policy, enabling
    explicit policy normalization before arithmetic.
    """

    def test_with_policy_returns_new_instance(self) -> None:
        """with_policy() returns a new instance, not self."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.PRESERVE)
        new_delta = delta.with_policy(MonthEndPolicy.STRICT)
        assert delta is not new_delta

    def test_with_policy_changes_policy(self) -> None:
        """with_policy() changes the policy."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.PRESERVE)
        new_delta = delta.with_policy(MonthEndPolicy.STRICT)
        assert new_delta.month_end_policy == MonthEndPolicy.STRICT
        # Original unchanged
        assert delta.month_end_policy == MonthEndPolicy.PRESERVE

    def test_with_policy_preserves_duration(self) -> None:
        """with_policy() preserves all duration components."""
        delta = FiscalDelta(years=1, quarters=2, months=3, days=4)
        new_delta = delta.with_policy(MonthEndPolicy.CLAMP)
        assert new_delta.years == 1
        assert new_delta.quarters == 2
        assert new_delta.months == 3
        assert new_delta.days == 4

    def test_with_policy_same_policy(self) -> None:
        """with_policy() works when setting same policy (no-op equivalent)."""
        delta = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.CLAMP)
        new_delta = delta.with_policy(MonthEndPolicy.CLAMP)
        assert new_delta.month_end_policy == MonthEndPolicy.CLAMP
        assert new_delta == delta  # Equal by value

    def test_with_policy_enables_arithmetic(self) -> None:
        """with_policy() enables arithmetic between incompatible deltas."""
        strict = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.STRICT)
        preserve = FiscalDelta(months=2, month_end_policy=MonthEndPolicy.PRESERVE)

        # Direct add fails
        with pytest.raises(ValueError, match="different month_end_policy"):
            _ = strict + preserve

        # After normalizing, add succeeds
        result = strict.with_policy(MonthEndPolicy.PRESERVE) + preserve
        assert result.months == 3
        assert result.month_end_policy == MonthEndPolicy.PRESERVE

    def test_with_policy_preserves_subclass(self) -> None:
        """with_policy() preserves subclass type."""

        class CustomDelta(FiscalDelta):
            """Subclass for testing polymorphism."""

        delta = CustomDelta(months=1)
        new_delta = delta.with_policy(MonthEndPolicy.STRICT)
        assert type(new_delta) is CustomDelta
        assert new_delta.month_end_policy == MonthEndPolicy.STRICT

    def test_with_policy_in_expression(self) -> None:
        """with_policy() works in chained expressions."""
        d1 = FiscalDelta(months=1, month_end_policy=MonthEndPolicy.STRICT)
        d2 = FiscalDelta(months=2, month_end_policy=MonthEndPolicy.PRESERVE)
        d3 = FiscalDelta(months=3, month_end_policy=MonthEndPolicy.CLAMP)

        # Convert all to PRESERVE before combining
        result = (
            d1.with_policy(MonthEndPolicy.PRESERVE)
            + d2
            + d3.with_policy(MonthEndPolicy.PRESERVE)
        )
        assert result.months == 6
        assert result.month_end_policy == MonthEndPolicy.PRESERVE


class TestFiscalCalendarFiscalYearBounds:
    """Tests for FiscalCalendar date methods enforcing fiscal_year 1-9999.

    FiscalPeriod.__post_init__ validates fiscal_year at construction.
    The four date-returning FiscalCalendar methods accept a bare int and
    must apply the same bounds to prevent cryptic errors from date().
    """

    def setup_method(self) -> None:
        """Create calendar-year fiscal calendar."""
        self.cal = FiscalCalendar(start_month=1)

    def test_fiscal_year_start_date_zero_raises(self) -> None:
        """fiscal_year_start_date rejects fiscal_year=0."""
        with pytest.raises(ValueError, match="fiscal_year must be 1-9999"):
            self.cal.fiscal_year_start_date(0)

    def test_fiscal_year_start_date_negative_raises(self) -> None:
        """fiscal_year_start_date rejects negative fiscal_year."""
        with pytest.raises(ValueError, match="fiscal_year must be 1-9999"):
            self.cal.fiscal_year_start_date(-1)

    def test_fiscal_year_start_date_too_large_raises(self) -> None:
        """fiscal_year_start_date rejects fiscal_year > 9999."""
        with pytest.raises(ValueError, match="fiscal_year must be 1-9999"):
            self.cal.fiscal_year_start_date(10000)

    def test_fiscal_year_start_date_boundaries_valid(self) -> None:
        """fiscal_year_start_date accepts boundary values 1 and 9999."""
        assert self.cal.fiscal_year_start_date(1) == date(1, 1, 1)
        assert self.cal.fiscal_year_start_date(9999) == date(9999, 1, 1)

    def test_fiscal_year_end_date_zero_raises(self) -> None:
        """fiscal_year_end_date rejects fiscal_year=0."""
        with pytest.raises(ValueError, match="fiscal_year must be 1-9999"):
            self.cal.fiscal_year_end_date(0)

    def test_fiscal_year_end_date_too_large_raises(self) -> None:
        """fiscal_year_end_date rejects fiscal_year > 9999."""
        with pytest.raises(ValueError, match="fiscal_year must be 1-9999"):
            self.cal.fiscal_year_end_date(10000)

    def test_fiscal_year_end_date_boundaries_valid(self) -> None:
        """fiscal_year_end_date accepts boundary values 1 and 9999."""
        assert self.cal.fiscal_year_end_date(1) == date(1, 12, 31)
        assert self.cal.fiscal_year_end_date(9999) == date(9999, 12, 31)

    def test_quarter_start_date_zero_year_raises(self) -> None:
        """quarter_start_date rejects fiscal_year=0."""
        with pytest.raises(ValueError, match="fiscal_year must be 1-9999"):
            self.cal.quarter_start_date(0, 1)

    def test_quarter_start_date_too_large_year_raises(self) -> None:
        """quarter_start_date rejects fiscal_year > 9999."""
        with pytest.raises(ValueError, match="fiscal_year must be 1-9999"):
            self.cal.quarter_start_date(10000, 1)

    def test_quarter_start_date_boundaries_valid(self) -> None:
        """quarter_start_date accepts boundary fiscal year values."""
        assert self.cal.quarter_start_date(1, 1) == date(1, 1, 1)
        assert self.cal.quarter_start_date(9999, 4) == date(9999, 10, 1)

    def test_quarter_end_date_zero_year_raises(self) -> None:
        """quarter_end_date rejects fiscal_year=0."""
        with pytest.raises(ValueError, match="fiscal_year must be 1-9999"):
            self.cal.quarter_end_date(0, 1)

    def test_quarter_end_date_too_large_year_raises(self) -> None:
        """quarter_end_date rejects fiscal_year > 9999."""
        with pytest.raises(ValueError, match="fiscal_year must be 1-9999"):
            self.cal.quarter_end_date(10000, 1)

    def test_quarter_end_date_boundaries_valid(self) -> None:
        """quarter_end_date accepts boundary fiscal year values."""
        assert self.cal.quarter_end_date(1, 1) == date(1, 3, 31)
        assert self.cal.quarter_end_date(9999, 4) == date(9999, 12, 31)

    def test_non_january_start_month_bounds_apply(self) -> None:
        """Fiscal year bounds apply to non-calendar-year fiscal calendars."""
        uk_cal = FiscalCalendar(start_month=4)
        with pytest.raises(ValueError, match="fiscal_year must be 1-9999"):
            uk_cal.fiscal_year_start_date(0)
        with pytest.raises(ValueError, match="fiscal_year must be 1-9999"):
            uk_cal.fiscal_year_end_date(10000)


class TestFiscalDeltaBoolRejection:
    """Tests for FiscalDelta rejecting bool for numeric fields.

    bool is a subclass of int in Python. FiscalDelta.__post_init__ must
    explicitly reject bool before the isinstance(value, int) check.
    """

    def test_years_bool_true_rejected(self) -> None:
        """FiscalDelta rejects True for years."""
        with pytest.raises(TypeError, match="years must be int, not bool"):
            FiscalDelta(years=True)

    def test_years_bool_false_rejected(self) -> None:
        """FiscalDelta rejects False for years."""
        with pytest.raises(TypeError, match="years must be int, not bool"):
            FiscalDelta(years=False)

    def test_quarters_bool_rejected(self) -> None:
        """FiscalDelta rejects bool for quarters."""
        with pytest.raises(TypeError, match="quarters must be int, not bool"):
            FiscalDelta(quarters=True)

    def test_months_bool_rejected(self) -> None:
        """FiscalDelta rejects bool for months."""
        with pytest.raises(TypeError, match="months must be int, not bool"):
            FiscalDelta(months=False)

    def test_days_bool_rejected(self) -> None:
        """FiscalDelta rejects bool for days."""
        with pytest.raises(TypeError, match="days must be int, not bool"):
            FiscalDelta(days=True)

    def test_mul_bool_factor_returns_not_implemented(self) -> None:
        """FiscalDelta.__mul__ returns NotImplemented for bool factor."""
        delta = FiscalDelta(months=1)
        result = delta.__mul__(True)  # pylint: disable=unnecessary-dunder-call
        assert result is NotImplemented

    def test_mul_bool_false_factor_returns_not_implemented(self) -> None:
        """FiscalDelta.__mul__ returns NotImplemented for False factor."""
        delta = FiscalDelta(months=1)
        result = delta.__mul__(False)  # pylint: disable=unnecessary-dunder-call
        assert result is NotImplemented

    def test_int_zero_still_valid(self) -> None:
        """FiscalDelta accepts int 0 (not bool, even though 0 == False)."""
        delta = FiscalDelta(years=0, months=0)
        assert delta.years == 0
        assert delta.months == 0

    def test_int_one_still_valid(self) -> None:
        """FiscalDelta accepts int 1 (not bool, even though 1 == True)."""
        delta = FiscalDelta(years=1, months=1)
        assert delta.years == 1
        assert delta.months == 1


class TestAddMonthsYearRangeBounds:
    """Tests for _add_months raising ValueError when result year is out of range.

    _add_months computes target_year arithmetically and must validate the
    result is within 1-9999 before calling date().
    """

    def test_overflow_future_raises_value_error(self) -> None:
        """Adding months that push year beyond 9999 raises ValueError."""
        delta = FiscalDelta(months=24)
        with pytest.raises(ValueError, match="out of the supported range"):
            delta.add_to(date(9999, 1, 1))

    def test_overflow_past_raises_value_error(self) -> None:
        """Subtracting months that push year below 1 raises ValueError."""
        delta = FiscalDelta(months=-24)
        with pytest.raises(ValueError, match="out of the supported range"):
            delta.add_to(date(1, 12, 31))

    def test_large_positive_month_delta_raises(self) -> None:
        """Large positive month delta raises for dates near year 9999."""
        delta = FiscalDelta(months=13)
        with pytest.raises(ValueError, match="out of the supported range"):
            delta.add_to(date(9999, 6, 1))

    def test_large_negative_month_delta_raises(self) -> None:
        """Large negative month delta raises for dates near year 1."""
        delta = FiscalDelta(months=-13)
        with pytest.raises(ValueError, match="out of the supported range"):
            delta.add_to(date(1, 6, 1))

    def test_valid_large_delta_within_range(self) -> None:
        """Large month delta is valid when result stays within 1-9999."""
        delta = FiscalDelta(months=120)
        result = delta.add_to(date(2020, 1, 15))
        assert result == date(2030, 1, 15)
