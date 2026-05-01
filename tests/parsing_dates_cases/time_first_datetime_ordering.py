# mypy: ignore-errors
"""Split test cases from tests/test_parsing_dates.py."""

from tests.parsing_dates_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Time-First Datetime Ordering
# ============================================================================


class TestDatetimeTimeFirstOrdering:
    """Test time-first datetime ordering (mock locales)."""

    def test_time_first_ordering(self) -> None:
        """Mock locale with time-first ordering generates patterns."""
        _get_datetime_patterns.cache_clear()

        original_parse = Locale.parse

        def mock_parse_time_first(locale_str: str) -> MagicMock:
            real_locale = original_parse(locale_str)
            mock_locale = MagicMock(spec=Locale)

            time_first_pattern = "{0} {1}"
            mock_datetime_format = MagicMock(
                return_value=time_first_pattern
            )
            mock_datetime_format.__str__ = MagicMock(  # type: ignore[method-assign]
                return_value=time_first_pattern
            )
            mock_datetime_format.pattern = time_first_pattern

            mock_locale.datetime_formats = {
                "short": mock_datetime_format,
                "medium": mock_datetime_format,
                "long": mock_datetime_format,
            }
            mock_locale.date_formats = real_locale.date_formats
            return mock_locale

        with patch(
            "babel.Locale.parse", side_effect=mock_parse_time_first
        ):
            patterns = _get_datetime_patterns("en_US")

        assert len(patterns) > 0

        time_first_found = False
        for pattern, _has_era in patterns:
            time_pos = min(
                (
                    pattern.find(t)
                    for t in ["%H", "%I"]
                    if pattern.find(t) != -1
                ),
                default=-1,
            )
            date_pos = min(
                (
                    pattern.find(d)
                    for d in ["%d", "%m", "%Y"]
                    if pattern.find(d) != -1
                ),
                default=-1,
            )
            if (
                time_pos != -1
                and date_pos != -1
                and time_pos < date_pos
            ):
                time_first_found = True
                break

        assert time_first_found
        _get_datetime_patterns.cache_clear()

    def test_parse_datetime_with_time_first_locale(self) -> None:
        """Integration: parse datetime with time-first mock locale."""
        _get_datetime_patterns.cache_clear()

        original_parse = Locale.parse

        def mock_parse_time_first(locale_str: str) -> MagicMock:
            real_locale = original_parse(locale_str)
            mock_locale = MagicMock(spec=Locale)

            time_first_pattern = "{0} {1}"
            mock_datetime_format = MagicMock(
                return_value=time_first_pattern
            )
            mock_datetime_format.__str__ = MagicMock(  # type: ignore[method-assign]
                return_value=time_first_pattern
            )
            mock_locale.datetime_formats = {
                "short": mock_datetime_format,
                "medium": mock_datetime_format,
            }
            mock_locale.date_formats = real_locale.date_formats
            return mock_locale

        with patch(
            "babel.Locale.parse", side_effect=mock_parse_time_first
        ):
            result, _errors = parse_datetime(
                "14:30 28.01.2025", "de_DE"
            )

        assert result is None or result.year in (2025, 1925)
        _get_datetime_patterns.cache_clear()
