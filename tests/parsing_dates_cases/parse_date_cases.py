# mypy: ignore-errors
"""Split test cases from tests/test_parsing_dates.py."""

from ftllexengine.diagnostics._redaction import redacted_parse_failure
from tests.parsing_dates_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# parse_date
# ---------------------------------------------------------------------------


class TestParseDate:
    """Test parse_date() function."""

    def test_parse_date_us_format(self) -> None:
        """Parse US date format (M/d/yy - CLDR short format)."""
        result, errors = parse_date("1/28/25", "en_US")
        assert not errors
        assert result == date(2025, 1, 28)

    def test_parse_date_european_format(self) -> None:
        """Parse European date format (d.M.yy - CLDR short format)."""
        result, errors = parse_date("28.1.25", "lv_LV")
        assert not errors
        assert result == date(2025, 1, 28)

        result, errors = parse_date("28.01.25", "de_DE")
        assert not errors
        assert result == date(2025, 1, 28)

    def test_parse_date_iso_format(self) -> None:
        """Parse ISO 8601 date format."""
        result, errors = parse_date("2025-01-28", "en_US")
        assert not errors
        assert result == date(2025, 1, 28)

    def test_parse_date_ignores_bidi_isolation_marks(self) -> None:
        """Invisible bidi controls do not block ISO parsing."""
        result, errors = parse_date("\u20682025-01-28\u2069", "en_US")
        assert not errors
        assert result == date(2025, 1, 28)

    def test_parse_date_invalid_returns_error(self) -> None:
        """Invalid input returns error in tuple; function never raises."""
        result, errors = parse_date("invalid", "en_US")
        assert len(errors) > 0
        assert result is None
        assert errors[0].parse_type == "date"
        assert errors[0].input_value == redacted_parse_failure("invalid", parse_type="date")

    def test_parse_date_empty_returns_error(self) -> None:
        """Empty input returns error in list."""
        result, errors = parse_date("", "en_US")
        assert len(errors) > 0
        assert result is None
