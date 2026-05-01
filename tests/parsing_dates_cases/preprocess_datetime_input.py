# mypy: ignore-errors
"""Split test cases from tests/test_parsing_dates.py."""

from tests.parsing_dates_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# _preprocess_datetime_input
# ============================================================================


class TestPreprocessDatetimeInput:
    """Test _preprocess_datetime_input function."""

    def test_with_has_era_true(self) -> None:
        """has_era=True triggers _strip_era."""
        result = _preprocess_datetime_input("28 Jan 2025 AD", has_era=True)
        assert "AD" not in result
        assert result == "28 Jan 2025"

    def test_with_has_era_false(self) -> None:
        """has_era=False returns value unchanged."""
        value = "2025-01-28 14:30:00"
        assert _preprocess_datetime_input(value, has_era=False) == value

    def test_with_era_and_timezone(self) -> None:
        """Era is stripped but timezone preserved."""
        result = _preprocess_datetime_input(
            "28 Jan 2025 AD PST", has_era=True
        )
        assert "AD" not in result
        assert "PST" in result
