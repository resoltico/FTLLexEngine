# mypy: ignore-errors
"""Split test cases from tests/test_parsing_dates.py."""

from tests.parsing_dates_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Unknown Locale Handling
# ============================================================================


class TestParseDateUnknownLocale:
    """Test parse_date with unknown locale."""

    def test_iso_format_succeeds(self) -> None:
        """ISO format succeeds even with unknown locale."""
        result, errors = parse_date("2025-01-01", "xx-INVALID")
        assert result is not None
        assert len(errors) == 0

    def test_non_iso_format_fails(self) -> None:
        """Non-ISO format with unknown locale returns error."""
        result, errors = parse_date("01/28/2025", "xx-INVALID")
        assert result is None
        assert len(errors) == 1
        assert errors[0].parse_type == "date"

    def test_malformed_locale(self) -> None:
        """Malformed locale returns error for non-ISO format."""
        result, errors = parse_date(
            "28.01.2025", "not-a-valid-locale-format"
        )
        assert result is None
        assert len(errors) == 1


class TestParseDatetimeUnknownLocale:
    """Test parse_datetime with unknown locale."""

    def test_iso_format_succeeds(self) -> None:
        """ISO format succeeds even with unknown locale."""
        result, errors = parse_datetime(
            "2025-01-28T14:30:00", "xx-INVALID"
        )
        assert result is not None
        assert len(errors) == 0

    def test_non_iso_format_fails(self) -> None:
        """Non-ISO format with unknown locale returns error."""
        result, errors = parse_datetime(
            "01/28/2025 2:30 PM", "xx-INVALID"
        )
        assert result is None
        assert len(errors) == 1
        assert errors[0].parse_type == "datetime"
