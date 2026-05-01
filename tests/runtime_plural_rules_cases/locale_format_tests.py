# mypy: ignore-errors
"""Split test cases from tests/test_runtime_plural_rules.py."""

from tests.runtime_plural_rules_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Locale Format Tests
# ============================================================================


class TestLocaleFormats:
    """Test various locale code formats."""

    def test_locale_case_insensitive(self) -> None:
        """Locale code is case-insensitive."""
        result_upper = select_plural_category(0, "LV_LV")
        result_lower = select_plural_category(0, "lv_lv")
        result_mixed = select_plural_category(0, "Lv_LV")

        assert result_upper == "zero"
        assert result_lower == "zero"
        assert result_mixed == "zero"

    def test_short_locale_code_without_region(self) -> None:
        """Short locale codes (without region) work correctly."""
        result = select_plural_category(0, "lv")
        assert result == "zero"

    def test_bcp47_hyphen_format_supported(self) -> None:
        """BCP-47 format with hyphens (en-US) works correctly."""
        result = select_plural_category(1, "en-US")
        assert result == "one"

        result = select_plural_category(0, "lv-LV")
        assert result == "zero"
