"""Tests for babel_compat module -- centralized Babel dependency handling.

Tests the lazy import infrastructure, error handling, and availability checking
for the optional Babel dependency.

Python 3.13+.
"""

from __future__ import annotations

from hypothesis import event, example, given
from hypothesis import strategies as st

from ftllexengine.core.babel_compat import (
    BabelImportError,
    get_cldr_version,
    get_locale_class,
    is_babel_available,
    require_babel,
)
from ftllexengine.core.locale_utils import get_babel_locale

# ============================================================================
# Availability
# ============================================================================


class TestBabelAvailability:
    """Test Babel availability checking."""

    def test_is_babel_available_returns_bool(self) -> None:
        """is_babel_available returns a boolean."""
        result = is_babel_available()
        assert isinstance(result, bool)

    def test_is_babel_available_is_cached(self) -> None:
        """Repeated calls return consistent result (cached sentinel)."""
        result1 = is_babel_available()
        result2 = is_babel_available()
        assert result1 == result2

    def test_babel_is_available_in_test_environment(self) -> None:
        """Babel is available in test environment (installed as dev dep)."""
        assert is_babel_available() is True


# ============================================================================
# require_babel
# ============================================================================


class TestRequireBabel:
    """Test require_babel guard function."""

    def test_require_babel_does_not_raise_when_available(self) -> None:
        """require_babel does not raise when Babel is installed."""
        require_babel("test_function")

    def test_require_babel_accepts_feature_name(self) -> None:
        """require_babel accepts feature name parameter."""
        require_babel("format_currency")
        require_babel("parse_number")
        require_babel("select_plural_category")


# ============================================================================
# BabelImportError
# ============================================================================


class TestBabelImportError:
    """Test BabelImportError exception class."""

    def test_message_includes_feature(self) -> None:
        """Error message includes the feature name."""
        error = BabelImportError("format_currency")
        assert "format_currency" in str(error)

    def test_message_includes_install_instructions(self) -> None:
        """Error message includes installation instructions."""
        error = BabelImportError("test_feature")
        assert "pip install ftllexengine[babel]" in str(error)

    def test_stores_feature_attribute(self) -> None:
        """Error stores feature name as attribute."""
        error = BabelImportError("my_feature")
        assert error.feature == "my_feature"

    def test_is_import_error(self) -> None:
        """BabelImportError is a subclass of ImportError."""
        error = BabelImportError("test")
        assert isinstance(error, ImportError)


# ============================================================================
# get_babel_locale (from locale_utils, depends on babel_compat)
# ============================================================================


class TestGetBabelLocale:
    """Test get_babel_locale function."""

    def test_returns_locale_object(self) -> None:
        """get_babel_locale returns a Babel Locale object."""
        locale = get_babel_locale("en_US")
        assert locale.language == "en"
        assert locale.territory == "US"

    def test_handles_bcp47_format(self) -> None:
        """get_babel_locale handles BCP-47 hyphen format."""
        locale = get_babel_locale("en-US")
        assert locale.language == "en"
        assert locale.territory == "US"

    def test_handles_language_only(self) -> None:
        """get_babel_locale handles language-only codes."""
        locale = get_babel_locale("de")
        assert locale.language == "de"

    def test_caches_result(self) -> None:
        """get_babel_locale caches results for repeated calls."""
        locale1 = get_babel_locale("fr_FR")
        locale2 = get_babel_locale("fr_FR")
        assert locale1 is locale2


# ============================================================================
# get_locale_class
# ============================================================================


class TestGetLocaleClass:
    """Test get_locale_class function."""

    def test_returns_locale_type(self) -> None:
        """get_locale_class returns the Babel Locale class."""
        from babel import Locale

        locale_class = get_locale_class()
        assert locale_class is Locale

    def test_can_construct_instances(self) -> None:
        """Returned class can construct Locale instances."""
        locale_class = get_locale_class()
        locale = locale_class.parse("en_US")
        assert locale.language == "en"

    def test_idempotence(self) -> None:
        """get_locale_class returns same class on repeated calls."""
        class1 = get_locale_class()
        class2 = get_locale_class()
        class3 = get_locale_class()
        assert class1 is class2 is class3

    def test_is_type(self) -> None:
        """get_locale_class returns a type (class) object."""
        locale_class = get_locale_class()
        assert isinstance(locale_class, type)


# ============================================================================
# get_cldr_version
# ============================================================================


class TestGetCldrVersion:
    """Tests for get_cldr_version() function."""

    def test_returns_string(self) -> None:
        """get_cldr_version() returns a version string."""
        version = get_cldr_version()
        assert isinstance(version, str)
        assert version

    def test_returns_valid_version_format(self) -> None:
        """Version string is a valid CLDR version number."""
        version = get_cldr_version()
        assert version.replace(".", "").isdigit() or version.isdigit()

    def test_idempotence(self) -> None:
        """get_cldr_version returns consistent results."""
        version1 = get_cldr_version()
        version2 = get_cldr_version()
        version3 = get_cldr_version()
        assert version1 == version2 == version3

    def test_babel_minimum_cldr_version(self) -> None:
        """Babel 2.18.0+ returns CLDR 47 or higher."""
        version = get_cldr_version()
        major_version = int(version.split(".", maxsplit=1)[0])
        assert major_version >= 47

    def test_importable_from_introspection(self) -> None:
        """get_cldr_version is available from introspection module."""
        from ftllexengine.introspection import (
            get_cldr_version as introspection_cldr,
        )

        version = introspection_cldr()
        assert isinstance(version, str)
        assert version

    def test_matches_babel_direct_call(self) -> None:
        """get_cldr_version returns same value as direct Babel call."""
        from babel.core import get_cldr_version as babel_cldr_version

        wrapper_result = get_cldr_version()
        direct_result = babel_cldr_version()
        assert wrapper_result == direct_result


# ============================================================================
# Integration
# ============================================================================


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


# ============================================================================
# Module Exports
# ============================================================================


class TestBabelCompatModuleExports:
    """Test babel_compat module export boundaries."""

    def test_get_babel_locale_not_exported_from_babel_compat(self) -> None:
        """get_babel_locale is not exported from babel_compat module."""
        from ftllexengine.core import babel_compat

        assert not hasattr(babel_compat, "get_babel_locale")
        assert "get_babel_locale" not in babel_compat.__all__

    def test_get_babel_locale_available_from_core_locale_utils(self) -> None:
        """get_babel_locale is available from canonical location in core."""
        from ftllexengine.core.locale_utils import (
            get_babel_locale as canonical_get_babel_locale,
        )

        locale = canonical_get_babel_locale("en_US")
        assert locale.language == "en"
        assert locale.territory == "US"

    def test_removed_apis_not_exported(self) -> None:
        """Removed APIs are not in babel_compat exports."""
        from ftllexengine.core import babel_compat

        removed = [
            "BabelNumbersProtocol",
            "BabelDatesProtocol",
            "get_babel_numbers",
            "get_babel_dates",
            "get_unknown_locale_error",
        ]
        for name in removed:
            assert name not in babel_compat.__all__

    def test_expected_exports_present(self) -> None:
        """All expected APIs are in babel_compat exports."""
        from ftllexengine.core import babel_compat

        expected = [
            "BabelImportError",
            "get_cldr_version",
            "get_locale_class",
            "is_babel_available",
            "require_babel",
        ]
        for name in expected:
            assert name in babel_compat.__all__


# ============================================================================
# Hypothesis Property-Based Tests
# ============================================================================


class TestBabelImportErrorProperties:
    """Property-based tests for BabelImportError exception class."""

    @given(feature_name=st.text(min_size=1))
    @example(feature_name="format_currency")
    @example(feature_name="parse_number")
    @example(feature_name="FluentBundle.format")
    def test_invariants(self, feature_name: str) -> None:
        """BabelImportError maintains invariants across all feature names.

        Properties tested:
        1. Error is an ImportError subclass
        2. Feature name appears in error message
        3. Install instructions appear in error message
        4. Feature attribute matches constructor argument
        """
        has_spaces = " " in feature_name
        event(f"feature_has_spaces={has_spaces}")
        length = "short" if len(feature_name) <= 10 else "long"
        event(f"feature_length={length}")

        error = BabelImportError(feature_name)

        assert isinstance(error, ImportError)
        assert feature_name in str(error)
        assert "pip install ftllexengine[babel]" in str(error)
        assert error.feature == feature_name


class TestRequireBabelProperties:
    """Property-based tests for require_babel function."""

    @given(feature_name=st.text(min_size=1))
    @example(feature_name="format_currency")
    @example(feature_name="LocaleContext.create")
    def test_accepts_any_feature_name(self, feature_name: str) -> None:
        """require_babel accepts any non-empty feature name when Babel available.

        Property: When Babel is available, require_babel never raises.
        """
        length = "short" if len(feature_name) <= 10 else "long"
        event(f"feature_length={length}")

        require_babel(feature_name)


class TestIsBabelAvailableProperties:
    """Property-based tests for is_babel_available function."""

    def test_idempotence(self) -> None:
        """is_babel_available is idempotent.

        Property: f() == f() == f()
        """
        result1 = is_babel_available()
        result2 = is_babel_available()
        result3 = is_babel_available()

        assert result1 == result2 == result3

    def test_returns_boolean(self) -> None:
        """is_babel_available always returns exactly True or False.

        Property: Result is always a boolean type (not truthy/falsy).
        """
        result = is_babel_available()
        assert isinstance(result, bool)
        assert result in {True, False}


_VALID_LOCALE_CODES = st.sampled_from(
    [
        "en", "en_US", "en-US",
        "de", "de_DE", "de-DE",
        "fr", "fr_FR", "fr-FR",
        "es", "es_ES", "es-ES",
        "pt", "pt_BR", "pt-BR",
        "zh", "zh_CN", "zh-CN",
        "ja", "ja_JP", "ja-JP",
        "ko", "ko_KR", "ko-KR",
        "ar", "ar_SA", "ar-SA",
        "ru", "ru_RU", "ru-RU",
        "it", "it_IT", "it-IT",
        "pl", "pl_PL", "pl-PL",
        "tr", "tr_TR", "tr-TR",
        "nl", "nl_NL", "nl-NL",
        "sv", "sv_SE", "sv-SE",
    ]
)


class TestGetBabelLocaleProperties:
    """Property-based tests for get_babel_locale function."""

    @given(locale_code=_VALID_LOCALE_CODES)
    @example(locale_code="en_US")
    @example(locale_code="en-US")
    @example(locale_code="de")
    def test_caching_identity(self, locale_code: str) -> None:
        """get_babel_locale returns identical object for repeated calls.

        Property: get_babel_locale(x) is get_babel_locale(x)
        """
        has_territory = "_" in locale_code or "-" in locale_code
        event(f"has_territory={has_territory}")
        separator = (
            "hyphen" if "-" in locale_code
            else "underscore" if "_" in locale_code
            else "none"
        )
        event(f"separator={separator}")

        locale1 = get_babel_locale(locale_code)
        locale2 = get_babel_locale(locale_code)

        assert locale1 is locale2

    @given(locale_code=_VALID_LOCALE_CODES)
    @example(locale_code="en_US")
    @example(locale_code="fr_FR")
    def test_returns_locale_type(self, locale_code: str) -> None:
        """get_babel_locale always returns a Babel Locale object.

        Property: type(get_babel_locale(x)) = Locale
        """
        event(f"locale={locale_code}")

        locale = get_babel_locale(locale_code)
        locale_class = get_locale_class()

        assert isinstance(locale, locale_class)

    @given(locale_code=_VALID_LOCALE_CODES)
    @example(locale_code="en_US")
    @example(locale_code="en-US")
    def test_normalization_equivalence(self, locale_code: str) -> None:
        """get_babel_locale normalizes BCP-47 and POSIX equivalently.

        Property: Underscore and hyphen formats produce equal results.
        """
        has_territory = "_" in locale_code or "-" in locale_code
        event(f"has_territory={has_territory}")

        if has_territory:
            underscore_version = locale_code.replace("-", "_")
            hyphen_version = locale_code.replace("_", "-")

            locale1 = get_babel_locale(underscore_version)
            locale2 = get_babel_locale(hyphen_version)

            assert locale1.language == locale2.language
            if locale1.territory:
                assert locale1.territory == locale2.territory
