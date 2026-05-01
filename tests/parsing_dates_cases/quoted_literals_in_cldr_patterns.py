# mypy: ignore-errors
"""Split test cases from tests/test_parsing_dates.py."""

from tests.parsing_dates_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Quoted Literals in CLDR Patterns
# ============================================================================


class TestQuotedLiteralsInCLDRPatterns:
    """Test non-empty quoted literals in CLDR date patterns."""

    def test_parse_date_russian(self) -> None:
        """Russian date parsing with short format."""
        result, errors = parse_date("28.01.2025", "ru_RU")
        assert not errors
        assert result is not None
        assert result.year == 2025

    def test_parse_date_spanish(self) -> None:
        """Spanish short format d/M/yy."""
        result, errors = parse_date("28/01/25", "es_ES")
        assert not errors
        assert result is not None
        assert result.year == 2025

    def test_parse_date_portuguese(self) -> None:
        """Portuguese date format."""
        result, errors = parse_date("28/01/2025", "pt_PT")
        assert not errors
        assert result is not None
        assert result.year == 2025
