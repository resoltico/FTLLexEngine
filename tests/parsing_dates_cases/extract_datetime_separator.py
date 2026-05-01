# mypy: ignore-errors
"""Split test cases from tests/test_parsing_dates.py."""

from tests.parsing_dates_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# _extract_datetime_separator
# ============================================================================


class TestExtractDatetimeSeparator:
    """Test _extract_datetime_separator edge cases."""

    def test_normal_order(self) -> None:
        """en_US uses date-first order."""
        locale = Locale.parse("en_US")
        separator, is_time_first = _extract_datetime_separator(locale)
        assert isinstance(separator, str)
        assert is_time_first is False

    def test_fallback_on_missing(self) -> None:
        """Missing datetime_format returns fallback space."""
        mock_locale = MagicMock()
        mock_locale.datetime_formats.get.return_value = None
        separator, is_time_first = _extract_datetime_separator(mock_locale)
        assert separator == " "
        assert is_time_first is False

    def test_missing_placeholders(self) -> None:
        """Pattern without placeholders returns fallback."""
        mock_locale = MagicMock()
        mock_locale.datetime_formats.get.return_value = (
            "no placeholders here"
        )
        separator, is_time_first = _extract_datetime_separator(mock_locale)
        assert separator == " "
        assert is_time_first is False

    def test_reversed_order(self) -> None:
        """Pattern with {0} before {1} detects time-first."""
        mock_locale = MagicMock()
        mock_locale.datetime_formats.get.return_value = "{0} at {1}"
        separator, is_time_first = _extract_datetime_separator(mock_locale)
        assert separator == " at "
        assert is_time_first is True

    def test_adjacent_placeholders(self) -> None:
        """Adjacent placeholders return fallback separator."""
        mock_locale = MagicMock()
        mock_locale.datetime_formats.get.return_value = "{1}{0}"
        separator, is_time_first = _extract_datetime_separator(mock_locale)
        assert separator == " "
        assert is_time_first is False

    def test_exception_handling(self) -> None:
        """AttributeError returns fallback."""
        mock_locale = MagicMock()
        mock_locale.datetime_formats.get.side_effect = AttributeError(
            "mock error"
        )
        separator, is_time_first = _extract_datetime_separator(mock_locale)
        assert separator == " "
        assert is_time_first is False
