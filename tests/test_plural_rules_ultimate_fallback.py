"""Test ultimate fallback in plural_rules.py for 100% coverage.

Tests the defensive nested exception handler that catches failures
when even the 'root' locale cannot be loaded.

Note: With lazy imports in plural_rules.py, patch the original module
location (ftllexengine.locale_utils.get_babel_locale) not the importing
module location.
"""

from unittest.mock import patch

from babel.core import UnknownLocaleError

from ftllexengine.runtime.plural_rules import select_plural_category


class TestPluralRulesUltimateFallback:
    """Test ultimate fallback when both locale and root fail."""

    def test_ultimate_fallback_when_root_locale_also_fails(self) -> None:
        """Return 'other' when even root locale loading fails.

        This tests lines 71-73 in plural_rules.py - the ultimate fallback
        that should theoretically never execute since 'root' is always valid
        in Babel, but exists as defensive programming.
        """
        # Mock get_babel_locale to fail for both the invalid locale AND root
        # Patch at the source location since lazy import happens inside function
        with patch("ftllexengine.locale_utils.get_babel_locale") as mock_get:
            # First call (invalid locale) raises
            # Second call (root) also raises
            mock_get.side_effect = UnknownLocaleError("mocked failure")

            # Should not crash, should return "other"
            result = select_plural_category(42, "completely_invalid_locale")
            assert result == "other"

    def test_ultimate_fallback_with_value_error(self) -> None:
        """Return 'other' when get_babel_locale raises ValueError."""
        # Patch at the source location since lazy import happens inside function
        with patch("ftllexengine.locale_utils.get_babel_locale") as mock_get:
            # Both calls raise ValueError instead of UnknownLocaleError
            mock_get.side_effect = ValueError("mocked failure")

            result = select_plural_category(1, "invalid")
            assert result == "other"

            result = select_plural_category(0, "invalid")
            assert result == "other"

            result = select_plural_category(100, "invalid")
            assert result == "other"
