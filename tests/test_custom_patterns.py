"""Tests for Phase 5: Advanced Formatting - Custom patterns."""

from datetime import UTC, datetime

from ftllexengine import FluentBundle


class TestNumberCustomPatterns:
    """Test custom pattern support for NUMBER() function."""

    def test_number_accounting_format_negative(self) -> None:
        """Accounting format shows negatives in parentheses."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            'amount = { NUMBER($value, pattern: "#,##0.00;(#,##0.00)") }'
        )

        # Negative value
        result, errors = bundle.format_pattern("amount", {"value": -1234.56})
        assert result == "(1,234.56)"
        assert errors == ()

    def test_number_accounting_format_positive(self) -> None:
        """Accounting format shows positives normally."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            'amount = { NUMBER($value, pattern: "#,##0.00;(#,##0.00)") }'
        )

        # Positive value
        result, errors = bundle.format_pattern("amount", {"value": 1234.56})
        assert result == "1,234.56"
        assert errors == ()

    def test_number_fixed_decimals_pattern(self) -> None:
        """Custom pattern with fixed decimal places."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('amount = { NUMBER($value, pattern: "#,##0.000") }')

        result, errors = bundle.format_pattern("amount", {"value": 42})
        assert result == "42.000"
        assert errors == ()

    def test_number_pattern_overrides_other_parameters(self) -> None:
        """Pattern parameter overrides other formatting parameters."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            'amount = { NUMBER($value, minimumFractionDigits: 0, pattern: "#,##0.00") }'
        )

        result, errors = bundle.format_pattern("amount", {"value": 42})
        # Pattern wins: shows 2 decimals, not 0
        assert result == "42.00"
        assert errors == ()

    def test_number_pattern_locale_aware(self) -> None:
        """Custom pattern respects locale formatting rules."""
        bundle_de = FluentBundle("de-DE", use_isolating=False)
        bundle_de.add_resource('amount = { NUMBER($value, pattern: "#,##0.00") }')

        result, _ = bundle_de.format_pattern("amount", {"value": 1234.56})
        # German format: period for thousands, comma for decimal
        assert result == "1.234,56"

    def test_number_pattern_no_grouping(self) -> None:
        """Pattern without grouping separator."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('amount = { NUMBER($value, pattern: "0.00") }')

        result, errors = bundle.format_pattern("amount", {"value": 1234.56})
        assert result == "1234.56"
        assert errors == ()


class TestDateTimeCustomPatterns:
    """Test custom pattern support for DATETIME() function."""

    def test_datetime_iso8601_pattern(self) -> None:
        """ISO 8601 date format."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('date = { DATETIME($dt, pattern: "yyyy-MM-dd") }')

        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result, errors = bundle.format_pattern("date", {"dt": dt})
        assert result == "2025-10-27"
        assert errors == ()

    def test_datetime_24hour_time_pattern(self) -> None:
        """24-hour time format."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('time = { DATETIME($dt, pattern: "HH:mm:ss") }')

        dt = datetime(2025, 10, 27, 14, 30, 45, tzinfo=UTC)
        result, errors = bundle.format_pattern("time", {"dt": dt})
        assert result == "14:30:45"
        assert errors == ()

    def test_datetime_short_month_pattern(self) -> None:
        """Short month name format."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('date = { DATETIME($dt, pattern: "MMM d, yyyy") }')

        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result, errors = bundle.format_pattern("date", {"dt": dt})
        assert result == "Oct 27, 2025"
        assert errors == ()

    def test_datetime_full_format_pattern(self) -> None:
        """Full weekday and month names."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('date = { DATETIME($dt, pattern: "EEEE, MMMM d, yyyy") }')

        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result, errors = bundle.format_pattern("date", {"dt": dt})
        assert result == "Monday, October 27, 2025"
        assert errors == ()

    def test_datetime_pattern_overrides_style(self) -> None:
        """Pattern parameter overrides dateStyle parameter."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            'date = { DATETIME($dt, dateStyle: "full", pattern: "yyyy-MM-dd") }'
        )

        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result, errors = bundle.format_pattern("date", {"dt": dt})
        # Pattern wins: ISO format, not full style
        assert result == "2025-10-27"
        assert errors == ()

    def test_datetime_pattern_locale_aware(self) -> None:
        """Custom pattern respects locale formatting rules."""
        bundle_de = FluentBundle("de-DE", use_isolating=False)
        bundle_de.add_resource('date = { DATETIME($dt, pattern: "MMMM d, yyyy") }')

        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result, _ = bundle_de.format_pattern("date", {"dt": dt})
        # German month name
        assert "Oktober" in result


class TestPatternBackwardCompatibility:
    """Test backward compatibility when pattern parameter not used."""

    def test_number_without_pattern_works(self) -> None:
        """NUMBER() without pattern still works as before."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource("amount = { NUMBER($value, minimumFractionDigits: 2) }")

        result, errors = bundle.format_pattern("amount", {"value": 42})
        assert result == "42.00"
        assert errors == ()

    def test_datetime_without_pattern_works(self) -> None:
        """DATETIME() without pattern still works as before."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('date = { DATETIME($dt, dateStyle: "short") }')

        dt = datetime(2025, 10, 27, tzinfo=UTC)
        result, errors = bundle.format_pattern("date", {"dt": dt})
        assert result == "10/27/25"
        assert errors == ()


class TestPatternUseCases:
    """Test real-world use cases for custom patterns."""

    def test_regulatory_iso8601_date(self) -> None:
        """ISO 8601 dates for regulatory compliance."""
        bundle = FluentBundle("lv-LV", use_isolating=False)
        bundle.add_resource(
            'export-date = Eksportēts: { DATETIME($date, pattern: "yyyy-MM-dd") }'
        )

        dt = datetime(2025, 1, 28, tzinfo=UTC)
        result, errors = bundle.format_pattern("export-date", {"date": dt})
        assert result == "Eksportēts: 2025-01-28"
        assert errors == ()

    def test_accounting_negative_format(self) -> None:
        """Accounting format for financial statements."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            'balance = Balance: { NUMBER($amount, pattern: "#,##0.00;(#,##0.00)") }'
        )

        # Negative balance
        result, _ = bundle.format_pattern("balance", {"amount": -5000.00})
        assert result == "Balance: (5,000.00)"

        # Positive balance
        result, _ = bundle.format_pattern("balance", {"amount": 5000.00})
        assert result == "Balance: 5,000.00"

    def test_timestamp_with_seconds(self) -> None:
        """Precise timestamp with seconds."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource(
            'timestamp = Last updated: { DATETIME($time, pattern: "HH:mm:ss") }'
        )

        dt = datetime(2025, 10, 27, 14, 30, 45, tzinfo=UTC)
        result, errors = bundle.format_pattern("timestamp", {"time": dt})
        assert result == "Last updated: 14:30:45"
        assert errors == ()


class TestPatternValidationIntegration:
    """Test that invalid patterns are handled gracefully."""

    def test_invalid_number_pattern_degrades_gracefully(self) -> None:
        """Invalid number pattern does not crash application."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('amount = { NUMBER($value, pattern: "invalid{") }')

        # Should not crash - graceful degradation
        # Babel interprets invalid patterns literally
        result, _ = bundle.format_pattern("amount", {"value": 42})
        # Returns some result (may be malformed but doesn't crash)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_invalid_datetime_pattern_degrades_gracefully(self) -> None:
        """Invalid datetime pattern does not crash application."""
        bundle = FluentBundle("en-US", use_isolating=False)
        bundle.add_resource('date = { DATETIME($dt, pattern: "invalid{") }')

        dt = datetime(2025, 10, 27, tzinfo=UTC)
        # Should not crash - graceful degradation
        # Babel interprets invalid patterns literally
        result, _ = bundle.format_pattern("date", {"dt": dt})
        # Returns some result (may be malformed but doesn't crash)
        assert isinstance(result, str)
        assert len(result) > 0
