# mypy: ignore-errors
"""Split test cases from tests/test_parsing_dates.py."""

from tests.parsing_dates_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Babel Datetime Format Conversion (Mock)
# ============================================================================


class TestBabelDatetimeFormatConversion:
    """Test Babel datetime format conversion with mock pattern objects."""

    def test_babel_datetime_format_with_mock(self) -> None:
        """Mock Babel to return pattern object for datetime_formats."""
        from ftllexengine.parsing import dates

        dates._get_datetime_patterns.cache_clear()
        dates._get_date_patterns.cache_clear()

        try:
            mock_pattern = Mock()
            mock_pattern.pattern = "M/d/yy, h:mm a"

            mock_locale = Mock()
            mock_locale.datetime_formats = {
                "short": mock_pattern, "medium": mock_pattern,
            }
            mock_date_format = Mock()
            mock_date_format.pattern = "M/d/yy"
            mock_locale.date_formats = {"short": mock_date_format}

            with patch("babel.Locale") as mock_locale_class:
                mock_locale_class.parse.return_value = mock_locale
                patterns = dates._get_datetime_patterns(
                    "test_mock_locale"
                )
                assert len(patterns) > 0
        finally:
            dates._get_datetime_patterns.cache_clear()
            dates._get_date_patterns.cache_clear()
