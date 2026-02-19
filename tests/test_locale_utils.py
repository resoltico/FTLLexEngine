"""Comprehensive tests for locale_utils.py achieving 100% coverage.

Covers normalize_locale, get_babel_locale, and get_system_locale functions.
Includes property-based tests with Hypothesis for locale normalization.

Python 3.13+.
"""

import builtins
import os
import sys
from unittest.mock import patch

import pytest
from babel import Locale
from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.locale_utils import (
    clear_locale_cache,
    get_babel_locale,
    get_system_locale,
    normalize_locale,
)


class TestNormalizeLocale:
    """Test normalize_locale function.

    normalize_locale lowercases output for consistent cache keys.
    BCP-47 is case-insensitive, so "en-US" and "EN-US" should be equivalent.
    """

    def test_bcp47_to_posix(self) -> None:
        """BCP-47 locale code converted to lowercase POSIX format."""
        assert normalize_locale("en-US") == "en_us"

    def test_uppercase_input_lowercased(self) -> None:
        """Uppercase input lowercased for consistent cache keys."""
        assert normalize_locale("EN-US") == "en_us"

    def test_already_normalized(self) -> None:
        """Already normalized locale lowercased."""
        assert normalize_locale("en_US") == "en_us"

    def test_simple_locale(self) -> None:
        """Simple locale without region unchanged (already lowercase)."""
        assert normalize_locale("en") == "en"

    def test_multiple_hyphens(self) -> None:
        """Multiple hyphens all converted to underscores and lowercased."""
        assert normalize_locale("zh-Hans-CN") == "zh_hans_cn"


class TestClearLocaleCache:
    """Test clear_locale_cache function."""

    def test_clear_locale_cache_runs_without_error(self) -> None:
        """clear_locale_cache() clears lru_cache without errors."""
        # Populate cache first
        get_babel_locale("en_us")
        get_babel_locale("de_de")

        # Cache info should show hits
        info_before = get_babel_locale.cache_info()
        assert info_before.currsize > 0

        # Clear the cache
        clear_locale_cache()

        # Cache should be empty
        info_after = get_babel_locale.cache_info()
        assert info_after.currsize == 0

    def test_clear_locale_cache_idempotent(self) -> None:
        """clear_locale_cache() can be called multiple times safely."""
        clear_locale_cache()
        clear_locale_cache()
        info = get_babel_locale.cache_info()
        assert info.currsize == 0

    def test_clear_locale_cache_when_empty(self) -> None:
        """clear_locale_cache() works on an already-empty cache."""
        get_babel_locale.cache_clear()  # Ensure empty
        clear_locale_cache()  # Should not raise
        info = get_babel_locale.cache_info()
        assert info.currsize == 0


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

    def test_babel_not_installed_raises_import_error(self) -> None:
        """BabelImportError with helpful message when Babel not installed (lines 102-108)."""
        # Save the original import and modules
        original_import = builtins.__import__
        saved_babel = sys.modules.get("babel")
        saved_locale = sys.modules.get("babel.core")

        # Clear caches to force re-evaluation
        get_babel_locale.cache_clear()
        import ftllexengine.core.babel_compat as _bc  # noqa: PLC0415

        _bc._babel_available = None

        def mock_import(name, globs=None, locs=None, fromlist=(), level=0):
            if name == "babel" or name.startswith("babel."):
                no_babel_msg = "No module named 'babel'"
                raise ImportError(no_babel_msg)
            return original_import(name, globs, locs, fromlist, level)

        builtins.__import__ = mock_import
        # Also remove babel from sys.modules to force reimport
        if "babel" in sys.modules:
            del sys.modules["babel"]
        if "babel.core" in sys.modules:
            del sys.modules["babel.core"]

        try:
            with pytest.raises(
                ImportError,
                match=(
                    r"get_babel_locale requires Babel for CLDR locale data.*"
                    r"pip install ftllexengine\[babel\]"
                ),
            ):
                get_babel_locale("en-US")
        finally:
            builtins.__import__ = original_import
            # Restore babel modules
            if saved_babel is not None:
                sys.modules["babel"] = saved_babel
            if saved_locale is not None:
                sys.modules["babel.core"] = saved_locale
            # Reset state for subsequent tests
            get_babel_locale.cache_clear()
            _bc._babel_available = None


class TestGetSystemLocale:
    """Test get_system_locale function with environment and OS detection.

    All locale output is lowercased via normalize_locale.
    """

    def test_getlocale_success(self) -> None:
        """OS-level locale.getlocale() returns valid locale (lowercased)."""
        with patch("locale.getlocale", return_value=("en_US", "UTF-8")):
            result = get_system_locale()
            assert result == "en_us"

    def test_getlocale_with_encoding(self) -> None:
        """getlocale() result with encoding suffix stripped (lowercased)."""
        with patch("locale.getlocale", return_value=("de_DE.UTF-8", "UTF-8")):
            result = get_system_locale()
            assert result == "de_de"

    def test_getlocale_c_posix_filtered(self) -> None:
        """getlocale() returning 'C' or 'POSIX' triggers fallback (lowercased)."""
        with patch("locale.getlocale", return_value=("C", None)):  # noqa: SIM117
            with patch.dict(os.environ, {"LANG": "fr_FR"}, clear=False):
                result = get_system_locale()
                assert result == "fr_fr"

    def test_getlocale_posix_filtered(self) -> None:
        """getlocale() returning 'POSIX' triggers env var fallback (lowercased)."""
        with patch("locale.getlocale", return_value=("POSIX", None)):  # noqa: SIM117
            with patch.dict(os.environ, {"LANG": "it_IT"}, clear=False):
                result = get_system_locale()
                assert result == "it_it"

    def test_getlocale_none_fallback(self) -> None:
        """getlocale() returning None triggers env var fallback (lowercased)."""
        with patch("locale.getlocale", return_value=(None, None)):  # noqa: SIM117
            with patch.dict(os.environ, {"LANG": "es_ES"}, clear=False):
                result = get_system_locale()
                assert result == "es_es"

    def test_getlocale_valueerror_fallback(self) -> None:
        """getlocale() raising ValueError triggers env var fallback (lowercased)."""
        with patch("locale.getlocale", side_effect=ValueError("mock error")):  # noqa: SIM117
            with patch.dict(os.environ, {"LANG": "pt_BR"}, clear=False):
                result = get_system_locale()
                assert result == "pt_br"

    def test_getlocale_attributeerror_fallback(self) -> None:
        """getlocale() raising AttributeError triggers env var fallback (lowercased)."""
        with patch("locale.getlocale", side_effect=AttributeError("mock error")):  # noqa: SIM117
            with patch.dict(os.environ, {"LANG": "ru_RU"}, clear=False):
                result = get_system_locale()
                assert result == "ru_ru"

    def test_lc_all_priority(self) -> None:
        """LC_ALL environment variable has highest priority (lowercased)."""
        with patch("locale.getlocale", return_value=(None, None)):
            env = {"LC_ALL": "de_DE", "LC_MESSAGES": "fr_FR", "LANG": "en_US"}
            with patch.dict(os.environ, env, clear=True):
                result = get_system_locale()
                assert result == "de_de"

    def test_lc_messages_fallback(self) -> None:
        """LC_MESSAGES used if LC_ALL not set (lowercased)."""
        with patch("locale.getlocale", return_value=(None, None)):
            env = {"LC_MESSAGES": "fr_FR", "LANG": "en_US"}
            with patch.dict(os.environ, env, clear=True):
                result = get_system_locale()
                assert result == "fr_fr"

    def test_lang_fallback(self) -> None:
        """LANG environment variable used as final fallback (lowercased)."""
        with patch("locale.getlocale", return_value=(None, None)):
            env = {"LANG": "ja_JP"}
            with patch.dict(os.environ, env, clear=True):
                result = get_system_locale()
                assert result == "ja_jp"

    def test_env_var_with_encoding(self) -> None:
        """Environment variable with encoding suffix stripped (lowercased)."""
        with patch("locale.getlocale", return_value=(None, None)):
            env = {"LANG": "zh_CN.UTF-8"}
            with patch.dict(os.environ, env, clear=True):
                result = get_system_locale()
                assert result == "zh_cn"

    def test_env_var_c_filtered(self) -> None:
        """Environment variable 'C' filtered out (lowercased fallback)."""
        with patch("locale.getlocale", return_value=(None, None)):
            env = {"LC_ALL": "C", "LANG": "ko_KR"}
            with patch.dict(os.environ, env, clear=True):
                result = get_system_locale()
                assert result == "ko_kr"

    def test_env_var_posix_filtered(self) -> None:
        """Environment variable 'POSIX' filtered out (lowercased fallback)."""
        with patch("locale.getlocale", return_value=(None, None)):
            env = {"LC_ALL": "POSIX", "LANG": "ar_SA"}
            with patch.dict(os.environ, env, clear=True):
                result = get_system_locale()
                assert result == "ar_sa"

    def test_env_var_empty_filtered(self) -> None:
        """Empty environment variable filtered out (lowercased fallback)."""
        with patch("locale.getlocale", return_value=(None, None)):
            env = {"LC_ALL": "", "LANG": "he_IL"}
            with patch.dict(os.environ, env, clear=True):
                result = get_system_locale()
                assert result == "he_il"

    def test_bcp47_normalized(self) -> None:
        """BCP-47 format in env var normalized to lowercase POSIX."""
        with patch("locale.getlocale", return_value=(None, None)):
            env = {"LANG": "pt-BR"}
            with patch.dict(os.environ, env, clear=True):
                result = get_system_locale()
                assert result == "pt_br"

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
    event("outcome=idempotent")
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
    """Property: All hyphens converted to underscores and lowercased."""
    event("outcome=converted")
    bcp47 = f"{lang}-{region}"
    posix = f"{lang}_{region}".lower()
    assert normalize_locale(bcp47) == posix
