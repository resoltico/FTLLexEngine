# mypy: ignore-errors
"""Split test cases from tests/test_runtime_plural_rules.py."""

from tests.runtime_plural_rules_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Ultimate Fallback Tests
# ============================================================================


class TestUltimateFallback:
    """Test ultimate fallback when both locale and root fail."""

    def test_ultimate_fallback_when_root_locale_also_fails(self) -> None:
        """Return 'other' when even root locale loading fails (lines 83-87).

        This is defensive programming - should never happen with valid Babel installation.
        """
        with patch("ftllexengine.core.locale_utils.get_babel_locale") as mock_get:
            mock_get.side_effect = UnknownLocaleError("mocked failure")

            result = select_plural_category(42, "completely_invalid_locale")
            assert result == "other"

    def test_ultimate_fallback_with_value_error(self) -> None:
        """Return 'other' when get_babel_locale raises ValueError (lines 83-87)."""
        with patch("ftllexengine.core.locale_utils.get_babel_locale") as mock_get:
            mock_get.side_effect = ValueError("mocked failure")

            result = select_plural_category(1, "invalid")
            assert result == "other"

            result = select_plural_category(0, "invalid")
            assert result == "other"

            result = select_plural_category(100, "invalid")
            assert result == "other"
