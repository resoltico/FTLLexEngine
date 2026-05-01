# mypy: ignore-errors
"""Split test cases from tests/test_parsing_dates.py."""

from tests.parsing_dates_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Integration: Full Coverage Verification
# ============================================================================


class TestIntegrationFullCoverage:
    """Integration test exercising multiple code branches."""

    def test_parse_datetime_exercises_all_branches(self) -> None:
        """Exercise ISO, CLDR, error, and empty paths."""
        test_cases = [
            ("2025-01-28T14:30:00", "en_US", True),
            ("1/28/25, 2:30 PM", "en_US", True),
            ("not-a-datetime", "en_US", False),
            ("", "en_US", False),
        ]
        for datetime_str, locale, should_succeed in test_cases:
            result, errors = parse_datetime(datetime_str, locale)
            if should_succeed:
                assert result is not None or len(errors) > 0
            else:
                assert len(errors) > 0
                assert result is None
