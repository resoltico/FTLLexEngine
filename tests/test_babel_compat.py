"""Tests for babel_compat module - centralized Babel dependency handling.

Tests the lazy import infrastructure, error handling, and availability checking
for the optional Babel dependency.
"""

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from ftllexengine.core.babel_compat import (
    BabelImportError,
    get_babel_dates,
    get_babel_numbers,
    get_locale_class,
    get_unknown_locale_error,
    is_babel_available,
    require_babel,
)
from ftllexengine.locale_utils import get_babel_locale


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


# ============================================================================
# Property-Based Tests (Hypothesis)
# ============================================================================


class TestBabelImportErrorProperties:
    """Property-based tests for BabelImportError exception class."""

    @given(feature_name=st.text(min_size=1))
    @example(feature_name="format_currency")
    @example(feature_name="parse_number")
    @example(feature_name="FluentBundle.format")
    def test_babel_import_error_properties(self, feature_name: str) -> None:
        """BabelImportError maintains invariants across all feature names.

        Properties tested:
        1. Error is an ImportError subclass
        2. Feature name appears in error message
        3. Install instructions appear in error message
        4. Feature attribute matches constructor argument
        """
        error = BabelImportError(feature_name)

        # Property 1: Type inheritance
        assert isinstance(error, ImportError)

        # Property 2: Feature name in message
        assert feature_name in str(error)

        # Property 3: Install instructions in message
        assert "pip install ftllexengine[babel]" in str(error)

        # Property 4: Attribute storage
        assert error.feature == feature_name


class TestRequireBabelProperties:
    """Property-based tests for require_babel function."""

    @given(feature_name=st.text(min_size=1))
    @example(feature_name="format_currency")
    @example(feature_name="LocaleContext.create")
    def test_require_babel_accepts_any_feature_name(self, feature_name: str) -> None:
        """require_babel accepts any non-empty feature name when Babel is available.

        Property: When Babel is available, require_babel never raises regardless
        of the feature name provided.
        """
        # In test environment, Babel is available, so this should never raise
        require_babel(feature_name)  # Should not raise


class TestIsBabelAvailableProperties:
    """Property-based tests for is_babel_available function."""

    def test_is_babel_available_idempotence(self) -> None:
        """is_babel_available is idempotent (returns same value on repeated calls).

        Property: f(f(x)) = f(x)
        """
        result1 = is_babel_available()
        result2 = is_babel_available()
        result3 = is_babel_available()

        assert result1 == result2 == result3

    def test_is_babel_available_returns_boolean(self) -> None:
        """is_babel_available always returns exactly True or False.

        Property: Result is always a boolean type (no truthy/falsy values).
        """
        result = is_babel_available()
        assert isinstance(result, bool)
        assert result in {True, False}


# Valid locale codes strategy
_VALID_LOCALE_CODES = st.sampled_from(
    [
        "en",
        "en_US",
        "en-US",
        "de",
        "de_DE",
        "de-DE",
        "fr",
        "fr_FR",
        "fr-FR",
        "es",
        "es_ES",
        "es-ES",
        "pt",
        "pt_BR",
        "pt-BR",
        "zh",
        "zh_CN",
        "zh-CN",
        "ja",
        "ja_JP",
        "ja-JP",
        "ko",
        "ko_KR",
        "ko-KR",
        "ar",
        "ar_SA",
        "ar-SA",
        "ru",
        "ru_RU",
        "ru-RU",
        "it",
        "it_IT",
        "it-IT",
        "pl",
        "pl_PL",
        "pl-PL",
        "tr",
        "tr_TR",
        "tr-TR",
        "nl",
        "nl_NL",
        "nl-NL",
        "sv",
        "sv_SE",
        "sv-SE",
    ]
)


class TestGetBabelLocaleProperties:
    """Property-based tests for get_babel_locale function."""

    @given(locale_code=_VALID_LOCALE_CODES)
    @example(locale_code="en_US")
    @example(locale_code="en-US")
    @example(locale_code="de")
    def test_get_babel_locale_caching_property(self, locale_code: str) -> None:
        """get_babel_locale returns identical object for repeated calls (caching).

        Property: get_babel_locale(x) is get_babel_locale(x) (identity, not just equality)
        """
        locale1 = get_babel_locale(locale_code)
        locale2 = get_babel_locale(locale_code)

        # Should be exact same object (cached)
        assert locale1 is locale2

    @given(locale_code=_VALID_LOCALE_CODES)
    @example(locale_code="en_US")
    @example(locale_code="fr_FR")
    def test_get_babel_locale_returns_locale_type(self, locale_code: str) -> None:
        """get_babel_locale always returns a Babel Locale object.

        Property: Type(get_babel_locale(x)) = Locale for all valid x
        """
        locale = get_babel_locale(locale_code)
        locale_class = get_locale_class()

        assert isinstance(locale, locale_class)

    @given(locale_code=_VALID_LOCALE_CODES)
    @example(locale_code="en_US")
    @example(locale_code="en-US")
    def test_get_babel_locale_normalization_equivalence(self, locale_code: str) -> None:
        """get_babel_locale normalizes BCP-47 and POSIX formats equivalently.

        Property: Underscore and hyphen formats for the same locale produce equal results.
        """
        # Only test if locale has territory (contains separator)
        if "_" in locale_code or "-" in locale_code:
            underscore_version = locale_code.replace("-", "_")
            hyphen_version = locale_code.replace("_", "-")

            locale1 = get_babel_locale(underscore_version)
            locale2 = get_babel_locale(hyphen_version)

            # Should have same language and territory
            assert locale1.language == locale2.language
            if locale1.territory:
                assert locale1.territory == locale2.territory


class TestGetLocaleClassProperties:
    """Property-based tests for get_locale_class function."""

    def test_get_locale_class_idempotence(self) -> None:
        """get_locale_class returns the same class object on repeated calls.

        Property: f() is f() (identity)
        """
        class1 = get_locale_class()
        class2 = get_locale_class()
        class3 = get_locale_class()

        assert class1 is class2 is class3

    def test_get_locale_class_is_type(self) -> None:
        """get_locale_class returns a type (class) object.

        Property: isinstance(f(), type)
        """
        locale_class = get_locale_class()
        assert isinstance(locale_class, type)


class TestGetUnknownLocaleErrorProperties:
    """Property-based tests for get_unknown_locale_error function."""

    def test_get_unknown_locale_error_idempotence(self) -> None:
        """get_unknown_locale_error returns same exception class on repeated calls.

        Property: f() is f() (identity)
        """
        error1 = get_unknown_locale_error()
        error2 = get_unknown_locale_error()
        error3 = get_unknown_locale_error()

        assert error1 is error2 is error3

    def test_get_unknown_locale_error_is_exception_class(self) -> None:
        """get_unknown_locale_error returns an exception class.

        Property: issubclass(f(), BaseException)
        """
        error_class = get_unknown_locale_error()
        assert isinstance(error_class, type)
        assert issubclass(error_class, BaseException)


class TestGetBabelNumbersProperties:
    """Property-based tests for get_babel_numbers function."""

    def test_get_babel_numbers_idempotence(self) -> None:
        """get_babel_numbers returns same module on repeated calls.

        Property: f() is f() (identity)
        """
        numbers1 = get_babel_numbers()
        numbers2 = get_babel_numbers()
        numbers3 = get_babel_numbers()

        assert numbers1 is numbers2 is numbers3

    def test_get_babel_numbers_has_required_functions(self) -> None:
        """get_babel_numbers returns module with required formatting functions.

        Property: Required attributes exist and are callable.
        """
        numbers = get_babel_numbers()

        required_functions = ["format_decimal", "format_currency", "format_percent"]
        for func_name in required_functions:
            assert hasattr(numbers, func_name)
            assert callable(getattr(numbers, func_name))


class TestGetBabelDatesProperties:
    """Property-based tests for get_babel_dates function."""

    def test_get_babel_dates_idempotence(self) -> None:
        """get_babel_dates returns same module on repeated calls.

        Property: f() is f() (identity)
        """
        dates1 = get_babel_dates()
        dates2 = get_babel_dates()
        dates3 = get_babel_dates()

        assert dates1 is dates2 is dates3

    def test_get_babel_dates_has_required_functions(self) -> None:
        """get_babel_dates returns module with required formatting functions.

        Property: Required attributes exist and are callable.
        """
        dates = get_babel_dates()

        required_functions = ["format_date", "format_datetime", "format_time"]
        for func_name in required_functions:
            assert hasattr(dates, func_name)
            assert callable(getattr(dates, func_name))


class TestBreakingChangesV071:
    """Test that v0.71.0 breaking changes are correctly enforced."""

    def test_get_babel_locale_not_exported_from_babel_compat(self) -> None:
        """get_babel_locale is no longer exported from babel_compat module."""
        from ftllexengine.core import babel_compat  # noqa: PLC0415

        # get_babel_locale should NOT be in babel_compat's exports
        assert not hasattr(babel_compat, "get_babel_locale")

        # Should not be in __all__
        assert "get_babel_locale" not in babel_compat.__all__

    def test_get_babel_locale_available_from_locale_utils(self) -> None:
        """get_babel_locale is still available from canonical location."""
        from ftllexengine.locale_utils import (  # noqa: PLC0415
            get_babel_locale as canonical_get_babel_locale,
        )

        # Should work correctly from canonical location
        locale = canonical_get_babel_locale("en_US")
        assert locale.language == "en"
        assert locale.territory == "US"

    def test_importing_get_babel_locale_from_babel_compat_fails(self) -> None:
        """Attempting to import get_babel_locale from babel_compat fails."""
        with pytest.raises(ImportError, match="cannot import name 'get_babel_locale'"):
            # pylint: disable=unused-import
            from ftllexengine.core.babel_compat import (  # noqa: PLC0415
                get_babel_locale,  # noqa: F401
            )
