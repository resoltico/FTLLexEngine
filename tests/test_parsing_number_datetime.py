"""NUMBER() and DATETIME() custom format pattern tests.

Verifies the behavioral contracts of the ``pattern:`` parameter in the
NUMBER() and DATETIME() formatting functions: sign invariants, format-string
compliance, locale awareness, precedence over style parameters, and graceful
degradation for invalid pattern strings.

Python 3.13+.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine import FluentBundle


class TestNumberCustomPatterns:
    """NUMBER() custom format pattern behavioral contracts."""

    def test_number_accounting_format_negative(self) -> None:
        """Accounting format expresses negative values in parentheses."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            'amount = { NUMBER($value, pattern: "#,##0.00;(#,##0.00)") }'
        )
        result, errors = bundle.format_pattern("amount", {"value": -1234.56})
        assert result == "(1,234.56)"
        assert errors == ()

    def test_number_accounting_format_positive(self) -> None:
        """Accounting format expresses positive values without parentheses."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            'amount = { NUMBER($value, pattern: "#,##0.00;(#,##0.00)") }'
        )
        result, errors = bundle.format_pattern("amount", {"value": 1234.56})
        assert result == "1,234.56"
        assert errors == ()

    def test_number_fixed_decimals_pattern(self) -> None:
        """Custom pattern with fixed decimal places pads to the specified count."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('amount = { NUMBER($value, pattern: "#,##0.000") }')
        result, errors = bundle.format_pattern("amount", {"value": 42})
        assert result == "42.000"
        assert errors == ()

    def test_number_pattern_overrides_minimumfractiondigits(self) -> None:
        """The pattern: parameter takes precedence over minimumFractionDigits."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            'amount = { NUMBER($value, minimumFractionDigits: 0, pattern: "#,##0.00") }'
        )
        result, errors = bundle.format_pattern("amount", {"value": 42})
        assert result == "42.00"
        assert errors == ()

    def test_number_pattern_locale_aware(self) -> None:
        """Custom pattern respects locale-specific decimal and grouping separators."""
        bundle_de = FluentBundle("de-DE", use_isolating=False)
        bundle_de.add_resource('amount = { NUMBER($value, pattern: "#,##0.00") }')
        result, _ = bundle_de.format_pattern("amount", {"value": 1234.56})
        assert result == "1.234,56"

    def test_number_pattern_no_grouping(self) -> None:
        """Pattern without grouping separator omits the thousands separator."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('amount = { NUMBER($value, pattern: "0.00") }')
        result, errors = bundle.format_pattern("amount", {"value": 1234.56})
        assert result == "1234.56"
        assert errors == ()

    @given(
        value=st.floats(
            min_value=0.01,
            max_value=1e12,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    @settings(max_examples=50)
    def test_accounting_positive_never_has_parentheses(self, value: float) -> None:
        """Property: positive values with accounting format never produce parentheses."""
        magnitude = "small" if value < 1_000 else "medium" if value < 1_000_000 else "large"
        event(f"magnitude={magnitude}")
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            'amount = { NUMBER($value, pattern: "#,##0.00;(#,##0.00)") }'
        )
        result, errors = bundle.format_pattern("amount", {"value": value})
        assert errors == ()
        assert "(" not in result
        assert ")" not in result

    @given(
        value=st.floats(
            min_value=-1e12,
            max_value=-0.01,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    @settings(max_examples=50)
    def test_accounting_negative_always_has_parentheses(self, value: float) -> None:
        """Property: negative values with accounting format always produce parentheses."""
        magnitude = "small" if value > -1_000 else "medium" if value > -1_000_000 else "large"
        event(f"magnitude={magnitude}")
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            'amount = { NUMBER($value, pattern: "#,##0.00;(#,##0.00)") }'
        )
        result, errors = bundle.format_pattern("amount", {"value": value})
        assert errors == ()
        assert result.startswith("(")
        assert result.endswith(")")


class TestDateTimeCustomPatterns:
    """DATETIME() custom format pattern behavioral contracts."""

    def test_datetime_iso8601_pattern(self) -> None:
        """ISO 8601 date format pattern produces YYYY-MM-DD output."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('date = { DATETIME($dt, pattern: "yyyy-MM-dd") }')
        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result, errors = bundle.format_pattern("date", {"dt": dt})
        assert result == "2025-10-27"
        assert errors == ()

    def test_datetime_24hour_time_pattern(self) -> None:
        """24-hour time format pattern produces HH:MM:SS output."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('time = { DATETIME($dt, pattern: "HH:mm:ss") }')
        dt = datetime(2025, 10, 27, 14, 30, 45, tzinfo=UTC)
        result, errors = bundle.format_pattern("time", {"dt": dt})
        assert result == "14:30:45"
        assert errors == ()

    def test_datetime_short_month_pattern(self) -> None:
        """Short month name pattern produces abbreviated month name."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('date = { DATETIME($dt, pattern: "MMM d, yyyy") }')
        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result, errors = bundle.format_pattern("date", {"dt": dt})
        assert result == "Oct 27, 2025"
        assert errors == ()

    def test_datetime_full_format_pattern(self) -> None:
        """Full weekday and month name pattern produces unabbreviated output."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('date = { DATETIME($dt, pattern: "EEEE, MMMM d, yyyy") }')
        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result, errors = bundle.format_pattern("date", {"dt": dt})
        assert result == "Monday, October 27, 2025"
        assert errors == ()

    def test_datetime_pattern_overrides_datestyle(self) -> None:
        """The pattern: parameter takes precedence over dateStyle."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            'date = { DATETIME($dt, dateStyle: "full", pattern: "yyyy-MM-dd") }'
        )
        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result, errors = bundle.format_pattern("date", {"dt": dt})
        assert result == "2025-10-27"
        assert errors == ()

    def test_datetime_pattern_locale_aware(self) -> None:
        """Custom pattern respects locale-specific month names."""
        bundle_de = FluentBundle("de-DE", use_isolating=False)
        bundle_de.add_resource('date = { DATETIME($dt, pattern: "MMMM d, yyyy") }')
        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result, _ = bundle_de.format_pattern("date", {"dt": dt})
        assert "Oktober" in result

    @given(
        year=st.integers(min_value=1900, max_value=2099),
        month=st.integers(min_value=1, max_value=12),
        day=st.integers(min_value=1, max_value=28),
    )
    @settings(max_examples=50)
    def test_iso8601_pattern_always_matches_expected_format(
        self, year: int, month: int, day: int
    ) -> None:
        """Property: yyyy-MM-dd pattern always produces YYYY-MM-DD format."""
        era = "pre_2000" if year < 2000 else "modern"
        event(f"era={era}")
        dt = datetime(year, month, day, tzinfo=UTC)
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('date = { DATETIME($dt, pattern: "yyyy-MM-dd") }')
        result, errors = bundle.format_pattern("date", {"dt": dt})
        assert errors == ()
        assert re.match(r"^\d{4}-\d{2}-\d{2}$", result) is not None, (
            f"Expected YYYY-MM-DD format, got: {result!r}"
        )

    @given(
        hour=st.integers(min_value=0, max_value=23),
        minute=st.integers(min_value=0, max_value=59),
        second=st.integers(min_value=0, max_value=59),
    )
    @settings(max_examples=50)
    def test_24hour_pattern_always_zero_pads(
        self, hour: int, minute: int, second: int
    ) -> None:
        """Property: HH:mm:ss pattern always zero-pads all time components."""
        time_range = "midnight" if hour == 0 else "noon" if hour == 12 else "general"
        event(f"time_range={time_range}")
        dt = datetime(2025, 1, 15, hour, minute, second, tzinfo=UTC)
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('time = { DATETIME($dt, pattern: "HH:mm:ss") }')
        result, errors = bundle.format_pattern("time", {"dt": dt})
        assert errors == ()
        expected = f"{hour:02d}:{minute:02d}:{second:02d}"
        assert result == expected


class TestFormattingFunctionsWithoutPattern:
    """NUMBER() and DATETIME() standard behavior without the pattern: parameter."""

    def test_number_without_pattern_uses_minimumfractiondigits(self) -> None:
        """NUMBER() without pattern applies minimumFractionDigits as expected."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource("amount = { NUMBER($value, minimumFractionDigits: 2) }")
        result, errors = bundle.format_pattern("amount", {"value": 42})
        assert result == "42.00"
        assert errors == ()

    def test_datetime_without_pattern_uses_datestyle(self) -> None:
        """DATETIME() without pattern applies dateStyle as expected."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('date = { DATETIME($dt, dateStyle: "short") }')
        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result, errors = bundle.format_pattern("date", {"dt": dt})
        assert result == "10/27/25"
        assert errors == ()


class TestPatternUseCases:
    """Real-world use cases for NUMBER() and DATETIME() custom patterns."""

    def test_regulatory_iso8601_date(self) -> None:
        """ISO 8601 dates for regulatory compliance are produced correctly."""
        bundle = FluentBundle("lv-LV", use_isolating=False)
        bundle.add_resource(
            'export-date = Eksportēts: { DATETIME($date, pattern: "yyyy-MM-dd") }'
        )
        dt = datetime(2025, 1, 28, tzinfo=UTC)
        result, errors = bundle.format_pattern("export-date", {"date": dt})
        assert result == "Eksportēts: 2025-01-28"
        assert errors == ()

    def test_accounting_format_in_financial_context(self) -> None:
        """Accounting format for financial statements renders correctly."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            'balance = Balance: { NUMBER($amount, pattern: "#,##0.00;(#,##0.00)") }'
        )
        result, _ = bundle.format_pattern("balance", {"amount": -5000.00})
        assert result == "Balance: (5,000.00)"
        result, _ = bundle.format_pattern("balance", {"amount": 5000.00})
        assert result == "Balance: 5,000.00"

    def test_precise_timestamp_with_seconds(self) -> None:
        """Timestamp with seconds precision is rendered correctly."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            'timestamp = Last updated: { DATETIME($time, pattern: "HH:mm:ss") }'
        )
        dt = datetime(2025, 10, 27, 14, 30, 45, tzinfo=UTC)
        result, errors = bundle.format_pattern("timestamp", {"time": dt})
        assert result == "Last updated: 14:30:45"
        assert errors == ()


class TestPatternValidationIntegration:
    """Invalid pattern graceful degradation contracts."""

    def test_invalid_number_pattern_returns_a_string(self) -> None:
        """Invalid number pattern does not crash; returns a string result."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('amount = { NUMBER($value, pattern: "invalid{") }')
        result, _ = bundle.format_pattern("amount", {"value": 42})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_invalid_datetime_pattern_returns_a_string(self) -> None:
        """Invalid datetime pattern does not crash; returns a string result."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('date = { DATETIME($dt, pattern: "invalid{") }')
        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result, _ = bundle.format_pattern("date", {"dt": dt})
        assert isinstance(result, str)
        assert len(result) > 0
