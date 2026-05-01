# mypy: ignore-errors
"""Split test cases from tests/test_parsing_dates.py."""

from tests.parsing_dates_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# BabelImportError Structure
# ============================================================================


class TestBabelImportErrorBehavior:
    """Test BabelImportError structure and message format."""

    def test_babel_import_error_structure(self) -> None:
        """BabelImportError has correct structure and message."""
        from ftllexengine.core.babel_compat import BabelImportError

        error = BabelImportError("parse_date")
        assert error.feature == "parse_date"
        assert "parse_date" in str(error)
        assert "pip install ftllexengine[babel]" in str(error)
        assert isinstance(error, ImportError)

    def test_get_date_patterns_returns_valid_patterns(self) -> None:
        """_get_date_patterns returns valid (pattern, has_era) tuples."""
        from ftllexengine.parsing import dates

        dates._get_date_patterns.cache_clear()
        patterns = dates._get_date_patterns("en_US")

        assert isinstance(patterns, tuple)
        assert len(patterns) > 0
        for pattern, has_era in patterns:
            assert isinstance(pattern, str)
            assert isinstance(has_era, bool)

    def test_get_datetime_patterns_returns_valid_patterns(self) -> None:
        """_get_datetime_patterns returns valid (pattern, has_era) tuples."""
        from ftllexengine.parsing import dates

        dates._get_datetime_patterns.cache_clear()
        patterns = dates._get_datetime_patterns("en_US")

        assert isinstance(patterns, tuple)
        assert len(patterns) > 0
        for pattern, has_era in patterns:
            assert isinstance(pattern, str)
            assert isinstance(has_era, bool)

    def test_parse_date_works(self) -> None:
        """parse_date works correctly when Babel is installed."""
        result, errors = parse_date("2025-01-28", "en_US")
        assert not errors
        assert result is not None
        assert result.year == 2025

    def test_parse_datetime_works(self) -> None:
        """parse_datetime works correctly when Babel is installed."""
        result, errors = parse_datetime("2025-01-28 14:30", "en_US")
        assert not errors
        assert result is not None
        assert result.year == 2025
        assert result.hour == 14
