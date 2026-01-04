"""Tests for babel_compat module - centralized Babel dependency handling.

Tests the lazy import infrastructure, error handling, and availability checking
for the optional Babel dependency.
"""

import pytest

from ftllexengine.core.babel_compat import (
    BabelImportError,
    get_babel_dates,
    get_babel_locale,
    get_babel_numbers,
    get_locale_class,
    get_unknown_locale_error,
    is_babel_available,
    require_babel,
)


class TestBabelAvailability:
    """Test Babel availability checking."""

    def test_is_babel_available_returns_bool(self) -> None:
        """is_babel_available returns a boolean."""
        result = is_babel_available()
        assert isinstance(result, bool)

    def test_is_babel_available_is_cached(self) -> None:
        """Repeated calls return consistent result (cached)."""
        result1 = is_babel_available()
        result2 = is_babel_available()
        assert result1 == result2

    def test_babel_is_available_in_test_environment(self) -> None:
        """Babel should be available in test environment (installed as dev dep)."""
        # Test environment has Babel installed
        assert is_babel_available() is True


class TestRequireBabel:
    """Test require_babel guard function."""

    def test_require_babel_does_not_raise_when_available(self) -> None:
        """require_babel does not raise when Babel is installed."""
        # Should not raise - Babel is available in test environment
        require_babel("test_function")

    def test_require_babel_accepts_feature_name(self) -> None:
        """require_babel accepts feature name parameter."""
        # Should not raise
        require_babel("format_currency")
        require_babel("parse_number")
        require_babel("select_plural_category")


class TestBabelImportError:
    """Test BabelImportError exception class."""

    def test_babel_import_error_message_includes_feature(self) -> None:
        """Error message includes the feature name."""
        error = BabelImportError("format_currency")
        assert "format_currency" in str(error)

    def test_babel_import_error_message_includes_install_instructions(self) -> None:
        """Error message includes installation instructions."""
        error = BabelImportError("test_feature")
        assert "pip install ftllexengine[babel]" in str(error)

    def test_babel_import_error_stores_feature_attribute(self) -> None:
        """Error stores feature name as attribute."""
        error = BabelImportError("my_feature")
        assert error.feature == "my_feature"

    def test_babel_import_error_is_import_error(self) -> None:
        """BabelImportError is a subclass of ImportError."""
        error = BabelImportError("test")
        assert isinstance(error, ImportError)


class TestGetBabelLocale:
    """Test get_babel_locale function."""

    def test_get_babel_locale_returns_locale_object(self) -> None:
        """get_babel_locale returns a Babel Locale object."""
        locale = get_babel_locale("en_US")
        assert locale.language == "en"
        assert locale.territory == "US"

    def test_get_babel_locale_handles_bcp47_format(self) -> None:
        """get_babel_locale handles BCP-47 hyphen format."""
        locale = get_babel_locale("en-US")
        assert locale.language == "en"
        assert locale.territory == "US"

    def test_get_babel_locale_handles_language_only(self) -> None:
        """get_babel_locale handles language-only codes."""
        locale = get_babel_locale("de")
        assert locale.language == "de"

    def test_get_babel_locale_caches_result(self) -> None:
        """get_babel_locale caches results for repeated calls."""
        locale1 = get_babel_locale("fr_FR")
        locale2 = get_babel_locale("fr_FR")
        # Should be same cached object
        assert locale1 is locale2


class TestGetLocaleClass:
    """Test get_locale_class function."""

    def test_get_locale_class_returns_locale_type(self) -> None:
        """get_locale_class returns the Babel Locale class."""
        from babel import Locale  # noqa: PLC0415

        locale_class = get_locale_class()
        assert locale_class is Locale

    def test_get_locale_class_can_construct_instances(self) -> None:
        """Returned class can construct Locale instances."""
        locale_class = get_locale_class()
        locale = locale_class.parse("en_US")
        assert locale.language == "en"


class TestGetUnknownLocaleError:
    """Test get_unknown_locale_error function."""

    def test_get_unknown_locale_error_returns_exception_class(self) -> None:
        """get_unknown_locale_error returns the UnknownLocaleError class."""
        from babel.core import UnknownLocaleError  # noqa: PLC0415

        error_class = get_unknown_locale_error()
        assert error_class is UnknownLocaleError

    def test_get_unknown_locale_error_can_catch_exceptions(self) -> None:
        """Returned class can be used in except clause."""
        error_class = get_unknown_locale_error()
        locale_class = get_locale_class()

        # Use valid format but unknown locale to trigger UnknownLocaleError
        # Note: "xx_YY" is valid format but "xx" is not a known language
        with pytest.raises(error_class):
            locale_class.parse("xx_YY")


class TestGetBabelNumbers:
    """Test get_babel_numbers function."""

    def test_get_babel_numbers_returns_module(self) -> None:
        """get_babel_numbers returns the babel.numbers module."""
        numbers = get_babel_numbers()
        # Module should have key formatting functions
        assert hasattr(numbers, "format_decimal")
        assert hasattr(numbers, "format_currency")
        assert hasattr(numbers, "format_percent")

    def test_get_babel_numbers_functions_work(self) -> None:
        """Returned module's functions work correctly."""
        numbers = get_babel_numbers()
        result = numbers.format_decimal(1234.5, locale="en_US")
        assert "1,234.5" in result or "1234.5" in result


class TestGetBabelDates:
    """Test get_babel_dates function."""

    def test_get_babel_dates_returns_module(self) -> None:
        """get_babel_dates returns the babel.dates module."""
        dates = get_babel_dates()
        # Module should have key formatting functions
        assert hasattr(dates, "format_date")
        assert hasattr(dates, "format_datetime")
        assert hasattr(dates, "format_time")

    def test_get_babel_dates_functions_work(self) -> None:
        """Returned module's functions work correctly."""
        from datetime import date  # noqa: PLC0415

        dates = get_babel_dates()
        test_date = date(2024, 1, 15)
        result = dates.format_date(test_date, locale="en_US")
        assert "2024" in result or "24" in result


class TestIntegration:
    """Integration tests for babel_compat usage patterns."""

    def test_typical_usage_pattern_with_require_babel(self) -> None:
        """Test typical usage: require_babel then use Babel functions."""
        require_babel("integration_test")
        locale = get_babel_locale("en_US")
        assert locale.language == "en"

    def test_availability_check_pattern(self) -> None:
        """Test availability check pattern before using Babel."""
        if is_babel_available():
            locale = get_babel_locale("de_DE")
            assert locale.language == "de"

    def test_exception_handling_pattern(self) -> None:
        """Test exception handling with get_unknown_locale_error."""
        error_class = get_unknown_locale_error()
        locale_class = get_locale_class()

        # Verify we can catch the error - should not raise
        caught = False
        try:
            locale_class.parse("xx_YY")
        except error_class:
            caught = True
        assert caught, "Expected UnknownLocaleError for xx_YY"
