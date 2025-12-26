"""Comprehensive tests for locale_utils.py achieving 100% coverage.

Covers normalize_locale, get_babel_locale, and get_system_locale functions.
Includes property-based tests with Hypothesis for locale normalization.

Python 3.13+.
"""

import os
from unittest.mock import patch

import pytest
from babel import Locale
from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.locale_utils import (
    get_babel_locale,
    get_system_locale,
    normalize_locale,
)


class TestNormalizeLocale:
    """Test normalize_locale function."""

    def test_bcp47_to_posix(self) -> None:
        """BCP-47 locale code converted to POSIX format."""
        assert normalize_locale("en-US") == "en_US"

    def test_already_normalized(self) -> None:
        """Already normalized locale returned unchanged."""
        assert normalize_locale("en_US") == "en_US"

    def test_simple_locale(self) -> None:
        """Simple locale without region unchanged."""
        assert normalize_locale("en") == "en"

    def test_multiple_hyphens(self) -> None:
        """Multiple hyphens all converted to underscores."""
        assert normalize_locale("zh-Hans-CN") == "zh_Hans_CN"


class TestGetBabelLocale:
    """Test get_babel_locale function with caching."""

    def test_bcp47_format(self) -> None:
        """BCP-47 format locale parsed correctly."""
        locale = get_babel_locale("en-US")
        assert isinstance(locale, Locale)
        assert locale.language == "en"
        assert locale.territory == "US"

    def test_posix_format(self) -> None:
        """POSIX format locale parsed correctly."""
        locale = get_babel_locale("de_DE")
        assert isinstance(locale, Locale)
        assert locale.language == "de"
        assert locale.territory == "DE"

    def test_simple_locale(self) -> None:
        """Simple locale without region parsed correctly."""
        locale = get_babel_locale("fr")
        assert isinstance(locale, Locale)
        assert locale.language == "fr"
        assert locale.territory is None

    def test_caching(self) -> None:
        """Repeated calls return cached Locale object."""
        locale1 = get_babel_locale("pt-BR")
        locale2 = get_babel_locale("pt-BR")
        # Same object identity proves caching
        assert locale1 is locale2

    def test_invalid_locale_raises(self) -> None:
        """Invalid locale raises ValueError."""
        with pytest.raises(ValueError, match="not a valid locale identifier"):
            get_babel_locale("invalid_locale_code_xyz")


class TestGetSystemLocale:
    """Test get_system_locale function with environment and OS detection."""

    def test_getlocale_success(self) -> None:
        """OS-level locale.getlocale() returns valid locale."""
        with patch("locale.getlocale", return_value=("en_US", "UTF-8")):
            result = get_system_locale()
            assert result == "en_US"

    def test_getlocale_with_encoding(self) -> None:
        """getlocale() result with encoding suffix stripped."""
        with patch("locale.getlocale", return_value=("de_DE.UTF-8", "UTF-8")):
            result = get_system_locale()
            assert result == "de_DE"

    def test_getlocale_c_posix_filtered(self) -> None:
        """getlocale() returning 'C' or 'POSIX' triggers fallback."""
        with patch("locale.getlocale", return_value=("C", None)):  # noqa: SIM117
            with patch.dict(os.environ, {"LANG": "fr_FR"}, clear=False):
                result = get_system_locale()
                assert result == "fr_FR"

    def test_getlocale_posix_filtered(self) -> None:
        """getlocale() returning 'POSIX' triggers env var fallback."""
        with patch("locale.getlocale", return_value=("POSIX", None)):  # noqa: SIM117
            with patch.dict(os.environ, {"LANG": "it_IT"}, clear=False):
                result = get_system_locale()
                assert result == "it_IT"

    def test_getlocale_none_fallback(self) -> None:
        """getlocale() returning None triggers env var fallback."""
        with patch("locale.getlocale", return_value=(None, None)):  # noqa: SIM117
            with patch.dict(os.environ, {"LANG": "es_ES"}, clear=False):
                result = get_system_locale()
                assert result == "es_ES"

    def test_getlocale_valueerror_fallback(self) -> None:
        """getlocale() raising ValueError triggers env var fallback."""
        with patch("locale.getlocale", side_effect=ValueError("mock error")):  # noqa: SIM117
            with patch.dict(os.environ, {"LANG": "pt_BR"}, clear=False):
                result = get_system_locale()
                assert result == "pt_BR"

    def test_getlocale_attributeerror_fallback(self) -> None:
        """getlocale() raising AttributeError triggers env var fallback."""
        with patch("locale.getlocale", side_effect=AttributeError("mock error")):  # noqa: SIM117
            with patch.dict(os.environ, {"LANG": "ru_RU"}, clear=False):
                result = get_system_locale()
                assert result == "ru_RU"

    def test_lc_all_priority(self) -> None:
        """LC_ALL environment variable has highest priority."""
        with patch("locale.getlocale", return_value=(None, None)):
            env = {"LC_ALL": "de_DE", "LC_MESSAGES": "fr_FR", "LANG": "en_US"}
            with patch.dict(os.environ, env, clear=True):
                result = get_system_locale()
                assert result == "de_DE"

    def test_lc_messages_fallback(self) -> None:
        """LC_MESSAGES used if LC_ALL not set."""
        with patch("locale.getlocale", return_value=(None, None)):
            env = {"LC_MESSAGES": "fr_FR", "LANG": "en_US"}
            with patch.dict(os.environ, env, clear=True):
                result = get_system_locale()
                assert result == "fr_FR"

    def test_lang_fallback(self) -> None:
        """LANG environment variable used as final fallback."""
        with patch("locale.getlocale", return_value=(None, None)):
            env = {"LANG": "ja_JP"}
            with patch.dict(os.environ, env, clear=True):
                result = get_system_locale()
                assert result == "ja_JP"

    def test_env_var_with_encoding(self) -> None:
        """Environment variable with encoding suffix stripped."""
        with patch("locale.getlocale", return_value=(None, None)):
            env = {"LANG": "zh_CN.UTF-8"}
            with patch.dict(os.environ, env, clear=True):
                result = get_system_locale()
                assert result == "zh_CN"

    def test_env_var_c_filtered(self) -> None:
        """Environment variable 'C' filtered out."""
        with patch("locale.getlocale", return_value=(None, None)):
            env = {"LC_ALL": "C", "LANG": "ko_KR"}
            with patch.dict(os.environ, env, clear=True):
                result = get_system_locale()
                assert result == "ko_KR"

    def test_env_var_posix_filtered(self) -> None:
        """Environment variable 'POSIX' filtered out."""
        with patch("locale.getlocale", return_value=(None, None)):
            env = {"LC_ALL": "POSIX", "LANG": "ar_SA"}
            with patch.dict(os.environ, env, clear=True):
                result = get_system_locale()
                assert result == "ar_SA"

    def test_env_var_empty_filtered(self) -> None:
        """Empty environment variable filtered out."""
        with patch("locale.getlocale", return_value=(None, None)):
            env = {"LC_ALL": "", "LANG": "he_IL"}
            with patch.dict(os.environ, env, clear=True):
                result = get_system_locale()
                assert result == "he_IL"

    def test_bcp47_normalized(self) -> None:
        """BCP-47 format in env var normalized to POSIX."""
        with patch("locale.getlocale", return_value=(None, None)):
            env = {"LANG": "pt-BR"}
            with patch.dict(os.environ, env, clear=True):
                result = get_system_locale()
                assert result == "pt_BR"

    def test_no_locale_default_fallback(self) -> None:
        """No locale detected returns en_US fallback by default."""
        with patch("locale.getlocale", return_value=(None, None)):  # noqa: SIM117
            with patch.dict(os.environ, {}, clear=True):
                result = get_system_locale()
                assert result == "en_US"

    def test_no_locale_raise_on_failure_true(self) -> None:
        """raise_on_failure=True raises RuntimeError when no locale."""
        with patch("locale.getlocale", return_value=(None, None)):  # noqa: SIM117
            with patch.dict(os.environ, {}, clear=True):
                with pytest.raises(RuntimeError) as exc_info:
                    get_system_locale(raise_on_failure=True)

                assert "Could not determine system locale" in str(exc_info.value)
                assert "LC_ALL" in str(exc_info.value)

    def test_raise_on_failure_false_returns_default(self) -> None:
        """raise_on_failure=False returns en_US when no locale."""
        with patch("locale.getlocale", return_value=(None, None)):  # noqa: SIM117
            with patch.dict(os.environ, {}, clear=True):
                result = get_system_locale(raise_on_failure=False)
                assert result == "en_US"


# Hypothesis property-based tests


@given(locale_code=st.from_regex(r"[a-z]{2}(-[A-Z]{2})?", fullmatch=True))
def test_property_normalize_locale_idempotent(locale_code: str) -> None:
    """Property: normalize_locale is idempotent."""
    normalized_once = normalize_locale(locale_code)
    normalized_twice = normalize_locale(normalized_once)
    assert normalized_once == normalized_twice


@given(
    lang=st.from_regex(r"[a-z]{2}", fullmatch=True),
    region=st.from_regex(r"[A-Z]{2}", fullmatch=True),
)
def test_property_normalize_locale_hyphen_to_underscore(
    lang: str, region: str
) -> None:
    """Property: All hyphens converted to underscores."""
    bcp47 = f"{lang}-{region}"
    posix = f"{lang}_{region}"
    assert normalize_locale(bcp47) == posix
