# mypy: ignore-errors
"""Split test cases from tests/test_parsing_dates.py."""

from tests.parsing_dates_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# parse_datetime
# ---------------------------------------------------------------------------


class TestParseDatetime:
    """Test parse_datetime() function."""

    def test_parse_datetime_us_format(self) -> None:
        """Parse US datetime format (M/d/yy + time - CLDR)."""
        result, errors = parse_datetime("1/28/25, 14:30", "en_US")
        assert not errors
        assert result == datetime(2025, 1, 28, 14, 30)

    def test_parse_datetime_european_format(self) -> None:
        """Parse European datetime format (d.M.yy + time - CLDR)."""
        result, errors = parse_datetime("28.1.25 14:30", "lv_LV")
        assert not errors
        assert result == datetime(2025, 1, 28, 14, 30)

    def test_parse_datetime_with_timezone(self) -> None:
        """Parse datetime and apply timezone."""
        result, errors = parse_datetime(
            "2025-01-28 14:30", "en_US", tzinfo=UTC
        )
        assert not errors
        assert result == datetime(2025, 1, 28, 14, 30, tzinfo=UTC)

    def test_parse_datetime_ignores_bidi_isolation_marks(self) -> None:
        """Invisible bidi controls do not block ISO datetime parsing."""
        result, errors = parse_datetime("\u20682025-01-28 14:30:00\u2069", "en_US")
        assert not errors
        assert result == datetime(2025, 1, 28, 14, 30)

    def test_parse_datetime_invalid_returns_error(self) -> None:
        """Invalid input returns error in tuple; function never raises."""
        result, errors = parse_datetime("invalid", "en_US")
        assert len(errors) > 0
        assert result is None
        assert errors[0].parse_type == "datetime"

    def test_parse_datetime_empty_returns_error(self) -> None:
        """Empty input returns error in list."""
        result, errors = parse_datetime("", "en_US")
        assert len(errors) > 0
        assert result is None

    def test_parse_datetime_with_seconds(self) -> None:
        """Datetime parsing with seconds component."""
        result, errors = parse_datetime("28.01.25, 14:30:45", "de_DE")
        assert not errors
        assert result is not None
        assert result.hour == 14
        assert result.minute == 30
        assert result.second == 45

    def test_parse_datetime_iso_format_all_locales(self) -> None:
        """ISO format works across all locales."""
        iso_str = "2025-01-28 14:30:00"
        for locale in [
            "en_US", "de_DE", "fr_FR", "es_ES", "ja_JP", "zh_CN"
        ]:
            result, errors = parse_datetime(iso_str, locale)
            assert not errors
            assert result is not None, f"ISO format failed for {locale}"
            assert result.year == 2025
            assert result.month == 1
            assert result.day == 28

    def test_parse_datetime_with_working_formats(self) -> None:
        """Datetime parsing with CLDR locale-specific separators."""
        test_cases = [
            ("01/28/25, 14:30", "en_US"),
            ("01/28/25, 02:30 PM", "en_US"),
            ("28.01.25, 14:30", "de_DE"),
        ]
        for date_str, locale in test_cases:
            result, errors = parse_datetime(date_str, locale)
            assert not errors
            assert result is not None, (
                f"Failed to parse '{date_str}' for {locale}"
            )
            assert result.year == 2025
            assert result.month == 1
            assert result.day == 28
