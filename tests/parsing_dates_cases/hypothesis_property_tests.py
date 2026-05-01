# mypy: ignore-errors
"""Split test cases from tests/test_parsing_dates.py."""

from tests.parsing_dates_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Hypothesis Property Tests
# ============================================================================


class TestDatetimeProperties:
    """Property-based tests for datetime parsing."""

    @given(
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
    )
    def test_parse_datetime_various_times(
        self, hour: int, minute: int
    ) -> None:
        """PROPERTY: Datetime patterns handle various times."""
        time_of_day = "morning" if hour < 12 else "afternoon"
        event(f"time_of_day={time_of_day}")

        date_str = f"28.01.25, {hour:02d}:{minute:02d}"
        result, errors = parse_datetime(date_str, "de_DE")
        assert not errors
        if result is not None:
            assert result.hour == hour
            assert result.minute == minute

    @given(
        year=st.integers(min_value=2020, max_value=2030),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
    )
    def test_datetime_roundtrip(
        self,
        year: int,
        month: int,
        day: int,
        hour: int,
        minute: int,
    ) -> None:
        """PROPERTY: Datetime ISO formatted then parsed preserves values."""
        event(f"year={year}")
        time_of_day = "morning" if hour < 12 else "afternoon"
        event(f"time_of_day={time_of_day}")

        dt = datetime(year, month, day, hour, minute, 0, tzinfo=UTC)
        iso_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        result, errors = parse_datetime(iso_str, "en_US")

        assert not errors
        if result is not None:
            assert result.year == year
            assert result.month == month
            assert result.day == day
            assert result.hour == hour
            assert result.minute == minute
