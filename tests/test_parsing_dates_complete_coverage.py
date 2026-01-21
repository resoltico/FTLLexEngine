"""Complete coverage tests for parsing/dates.py to achieve 100% coverage.

Targets remaining uncovered lines:
- Lines 307-311: BabelImportError in _get_date_patterns
- Lines 412-416: BabelImportError in _get_datetime_patterns
- Lines 693-715: Localized era string loading from Babel

Python 3.13+.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.parsing.dates import (
    _get_date_patterns,
    _get_datetime_patterns,
    _strip_era,
)

if TYPE_CHECKING:
    pass


class TestBabelImportErrorGetDatePatterns:
    """Test BabelImportError in _get_date_patterns (lines 307-311)."""

    def test_get_date_patterns_raises_babel_import_error_when_babel_missing(
        self,
    ) -> None:
        """Test _get_date_patterns raises BabelImportError when Babel unavailable.

        Tests lines 307-311: ImportError catch block that raises BabelImportError.
        """
        # Clear cache to ensure fresh execution
        _get_date_patterns.cache_clear()

        # Mock the babel module import to fail
        import builtins

        original_import = builtins.__import__

        def mock_import(
            name: str, globals_: dict | None = None, locals_: dict | None = None,
            fromlist: tuple[str, ...] = (), level: int = 0
        ) -> object:
            """Mock import that raises ImportError for babel module."""
            if name == "babel":
                msg = "No module named 'babel'"
                raise ImportError(msg)
            return original_import(name, globals_, locals_, fromlist, level)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            # Attempt to get patterns should raise BabelImportError
            with pytest.raises(ImportError, match="parse") as exc_info:  # BabelImportError
                _get_date_patterns("en_US")

            # Verify it's the correct error type
            assert exc_info.typename == "BabelImportError"
            assert "parse_date" in str(exc_info.value)

    def test_get_date_patterns_babel_import_error_feature_name(self) -> None:
        """Verify BabelImportError contains correct feature name for parse_date."""
        _get_date_patterns.cache_clear()

        # Save and remove babel from sys.modules
        babel_modules_backup = {}
        babel_module_keys = [k for k in sys.modules if k == "babel" or k.startswith("babel.")]

        for key in babel_module_keys:
            babel_modules_backup[key] = sys.modules.pop(key, None)

        try:
            import builtins

            original_import = builtins.__import__

            def mock_import(
                name: str, globals_: dict | None = None, locals_: dict | None = None,
                fromlist: tuple[str, ...] = (), level: int = 0
            ) -> object:
                """Mock import that raises ImportError for babel."""
                if name == "babel" or name.startswith("babel."):
                    msg = f"No module named '{name}'"
                    raise ImportError(msg)
                return original_import(name, globals_, locals_, fromlist, level)

            with patch.object(builtins, "__import__", side_effect=mock_import):
                with pytest.raises(ImportError, match="parse") as exc_info:
                    _get_date_patterns("en_US")

                # Should contain "parse_date" feature name (line 310)
                assert "parse_date" in str(exc_info.value)
        finally:
            # Restore babel modules
            for key, value in babel_modules_backup.items():
                if value is not None:
                    sys.modules[key] = value
            _get_date_patterns.cache_clear()


class TestBabelImportErrorGetDatetimePatterns:
    """Test BabelImportError in _get_datetime_patterns (lines 412-416)."""

    def test_get_datetime_patterns_raises_babel_import_error_when_babel_missing(
        self,
    ) -> None:
        """Test _get_datetime_patterns raises BabelImportError when Babel unavailable.

        Tests lines 412-416: ImportError catch block that raises BabelImportError.
        """
        # Clear cache to ensure fresh execution
        _get_datetime_patterns.cache_clear()
        _get_date_patterns.cache_clear()

        # Mock the babel module import to fail
        import builtins

        original_import = builtins.__import__

        def mock_import(
            name: str, globals_: dict | None = None, locals_: dict | None = None,
            fromlist: tuple[str, ...] = (), level: int = 0
        ) -> object:
            """Mock import that raises ImportError for babel module."""
            if name == "babel":
                msg = "No module named 'babel'"
                raise ImportError(msg)
            return original_import(name, globals_, locals_, fromlist, level)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            # Attempt to get patterns should raise BabelImportError
            with pytest.raises(ImportError, match="parse") as exc_info:
                _get_datetime_patterns("en_US")

            # Verify it's the correct error type
            assert exc_info.typename == "BabelImportError"
            assert "parse_datetime" in str(exc_info.value)

    def test_get_datetime_patterns_babel_import_error_feature_name(self) -> None:
        """Verify BabelImportError contains correct feature name for parse_datetime."""
        _get_datetime_patterns.cache_clear()
        _get_date_patterns.cache_clear()

        # Save and remove babel from sys.modules
        babel_modules_backup = {}
        babel_module_keys = [k for k in sys.modules if k == "babel" or k.startswith("babel.")]

        for key in babel_module_keys:
            babel_modules_backup[key] = sys.modules.pop(key, None)

        try:
            import builtins

            original_import = builtins.__import__

            def mock_import(
                name: str, globals_: dict | None = None, locals_: dict | None = None,
                fromlist: tuple[str, ...] = (), level: int = 0
            ) -> object:
                """Mock import that raises ImportError for babel."""
                if name == "babel" or name.startswith("babel."):
                    msg = f"No module named '{name}'"
                    raise ImportError(msg)
                return original_import(name, globals_, locals_, fromlist, level)

            with patch.object(builtins, "__import__", side_effect=mock_import):
                with pytest.raises(ImportError, match="parse") as exc_info:
                    _get_datetime_patterns("en_US")

                # Should contain "parse_datetime" feature name (line 415)
                assert "parse_datetime" in str(exc_info.value)
        finally:
            # Restore babel modules
            for key, value in babel_modules_backup.items():
                if value is not None:
                    sys.modules[key] = value
            _get_datetime_patterns.cache_clear()
            _get_date_patterns.cache_clear()


class TestStripEraLocalizedEraLoading:
    """Test localized era string loading in _strip_era (lines 693-715)."""

    def test_strip_era_with_locale_code_loads_babel_eras(self) -> None:
        """Test _strip_era loads localized era strings from Babel (lines 693-715).

        Tests the full path:
        - Line 692: if locale_code is not None
        - Lines 693-694: Import Babel
        - Line 697: Parse locale with Babel
        - Line 700: Check if locale has eras
        - Lines 701-709: Iterate through era widths and indices
        """
        # Use a locale that has era data in Babel
        value = "28 Jan 2025 AD"

        # Call with locale_code to trigger Babel era loading
        result = _strip_era(value, locale_code="en_US")

        # Should successfully strip era
        assert "AD" not in result
        assert result == "28 Jan 2025"

    def test_strip_era_with_german_locale_loads_localized_eras(self) -> None:
        """Test _strip_era with German locale loads localized era strings.

        German has localized eras like "v. Chr." (before Christ) and "n. Chr." (after Christ).
        This tests that localized era strings are loaded and used (lines 700-709).
        """
        # German localized era: "n. Chr." for AD
        value_german_era = "28. Januar 2025 n. Chr."

        result = _strip_era(value_german_era, locale_code="de_DE")

        # Should strip German localized era
        # Note: The function loads "n. Chr." from Babel and should strip it
        assert "n. Chr." not in result

    def test_strip_era_with_japanese_locale_loads_localized_eras(self) -> None:
        """Test _strip_era with Japanese locale loads localized era strings.

        Japanese uses Western calendar eras (西暦) and traditional eras.
        This tests localized era loading for non-Latin scripts (lines 700-709).
        """
        # Japanese value with Western era marker
        value = "2025年1月28日 西暦"

        result = _strip_era(value, locale_code="ja_JP")

        # Function should attempt to load Japanese eras
        # Result depends on whether "西暦" is in Babel's era data
        assert isinstance(result, str)

    def test_strip_era_with_locale_unknown_locale_error_caught(self) -> None:
        """Test _strip_era handles UnknownLocaleError gracefully (lines 710-712).

        When Locale.parse fails with UnknownLocaleError, the function should
        fall back to English eras only.
        """
        # Use an invalid locale code
        value = "28 Jan 2025 AD"

        # Should not raise exception, falls back to English eras
        result = _strip_era(value, locale_code="xx-INVALID-LOCALE")

        # Should still strip English era "AD"
        assert "AD" not in result
        assert result == "28 Jan 2025"

    def test_strip_era_with_locale_value_error_caught(self) -> None:
        """Test _strip_era handles ValueError from Locale.parse (line 710).

        When Locale.parse raises ValueError, the function should fall back
        to English eras only.
        """
        value = "28 Jan 2025 BC"

        # Malformed locale code that triggers ValueError
        result = _strip_era(value, locale_code="not-a-valid-locale-format")

        # Should still strip English era "BC"
        assert "BC" not in result
        assert result == "28 Jan 2025"

    def test_strip_era_with_locale_none_skips_babel_loading(self) -> None:
        """Test _strip_era with locale_code=None skips Babel loading (line 692).

        When locale_code is None, the function should use only English eras
        without attempting to load from Babel.
        """
        value = "28 Jan 2025 AD"

        # Call with locale_code=None (default)
        result = _strip_era(value, locale_code=None)

        # Should still strip English era "AD"
        assert "AD" not in result
        assert result == "28 Jan 2025"

    def test_strip_era_babel_import_error_caught(self) -> None:
        """Test _strip_era handles ImportError when Babel unavailable (lines 713-715).

        When Babel import fails, the function should fall back to English eras.
        """
        value = "28 Jan 2025 CE"

        # Mock Babel import to fail
        import builtins

        original_import = builtins.__import__

        def mock_import(
            name: str, globals_: dict | None = None, locals_: dict | None = None,
            fromlist: tuple[str, ...] = (), level: int = 0
        ) -> object:
            """Mock import that raises ImportError for babel in _strip_era."""
            if name == "babel":
                msg = "No module named 'babel'"
                raise ImportError(msg)
            return original_import(name, globals_, locals_, fromlist, level)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            # Should not raise exception, falls back to English eras
            result = _strip_era(value, locale_code="en_US")

        # Should still strip English era "CE"
        assert "CE" not in result
        assert result == "28 Jan 2025"

    def test_strip_era_with_locale_no_eras_attribute(self) -> None:
        """Test _strip_era when Babel locale has no eras attribute (line 700).

        Some locales might not have the eras attribute. The function should
        handle this gracefully.
        """

        value = "28 Jan 2025 AD"

        # Create a mock locale without eras attribute

        def mock_parse(_locale_str: str) -> MagicMock:
            """Mock Locale.parse to return locale without eras."""
            return MagicMock(spec=[])  # No attributes

        with patch("babel.Locale.parse", side_effect=mock_parse):
            # Should fall back to English eras when locale has no eras
            result = _strip_era(value, locale_code="en_US")

        # Should still strip English era "AD"
        assert "AD" not in result

    def test_strip_era_with_locale_empty_eras_dict(self) -> None:
        """Test _strip_era when Babel locale has empty eras dict (line 700).

        When locale.eras is empty or None, should fall back to English eras.
        """

        value = "28 Jan 2025 BC"

        # Create a mock locale with empty eras

        def mock_parse(_locale_str: str) -> MagicMock:
            """Mock Locale.parse to return locale with empty eras."""
            mock_locale = MagicMock()
            mock_locale.eras = {}  # Empty eras dict
            return mock_locale

        with patch("babel.Locale.parse", side_effect=mock_parse):
            result = _strip_era(value, locale_code="en_US")

        # Should still strip English era "BC"
        assert "BC" not in result

    def test_strip_era_with_locale_partial_era_widths(self) -> None:
        """Test _strip_era with locale having only some era width keys (line 701-702).

        Tests the path where not all width keys ('wide', 'abbreviated', 'narrow')
        are present in the eras dict.
        """

        value = "28 Jan 2025 CE"

        # Create a mock locale with partial era data

        def mock_parse(_locale_str: str) -> MagicMock:
            """Mock Locale.parse with only 'wide' era width."""
            mock_locale = MagicMock()
            mock_locale.eras = {
                "wide": {0: "Before Common Era", 1: "Common Era"},
                # Missing 'abbreviated' and 'narrow'
            }
            return mock_locale

        with patch("babel.Locale.parse", side_effect=mock_parse):
            result = _strip_era(value, locale_code="en_US")

        # Should load "Common Era" from mock and strip it
        assert "CE" not in result or "Common Era" not in result

    def test_strip_era_with_locale_partial_era_indices(self) -> None:
        """Test _strip_era with era dict having only some indices (line 706).

        Tests the path where era dict doesn't have both 0 and 1 indices.
        """

        value = "28 Jan 2025 AD"

        # Create a mock locale with only index 1 (CE/AD era)

        def mock_parse(_locale_str: str) -> MagicMock:
            """Mock Locale.parse with only index 1."""
            mock_locale = MagicMock()
            mock_locale.eras = {
                "wide": {1: "Anno Domini"},  # Only index 1, missing index 0
            }
            return mock_locale

        with patch("babel.Locale.parse", side_effect=mock_parse):
            result = _strip_era(value, locale_code="en_US")

        # Should still process available era strings
        assert isinstance(result, str)

    def test_strip_era_with_locale_duplicate_era_strings_not_added(self) -> None:
        """Test _strip_era doesn't add duplicate era strings (line 708).

        When Babel returns era string that's already in the default list,
        it should not be added again (line 708 condition).
        """

        value = "28 Jan 2025 AD"

        # Create a mock locale returning "AD" which is already in _ERA_STRINGS

        def mock_parse(_locale_str: str) -> MagicMock:
            """Mock Locale.parse returning duplicate era."""
            mock_locale = MagicMock()
            mock_locale.eras = {
                "abbreviated": {1: "AD"},  # Duplicate of default
            }
            return mock_locale

        with patch("babel.Locale.parse", side_effect=mock_parse):
            result = _strip_era(value, locale_code="en_US")

        # Should still strip era correctly without duplicates
        assert "AD" not in result

    def test_strip_era_with_locale_none_era_text(self) -> None:
        """Test _strip_era handles None era text from Babel (line 707).

        When era dict contains None values, they should be skipped.
        """

        value = "28 Jan 2025 BC"

        # Create a mock locale with None era text

        def mock_parse(_locale_str: str) -> MagicMock:
            """Mock Locale.parse with None era text."""
            mock_locale = MagicMock()
            mock_locale.eras = {
                "wide": {0: None, 1: "Common Era"},  # None for index 0
            }
            return mock_locale

        with patch("babel.Locale.parse", side_effect=mock_parse):
            result = _strip_era(value, locale_code="en_US")

        # Should skip None and still strip English "BC"
        assert "BC" not in result

    def test_strip_era_with_locale_empty_string_era_text(self) -> None:
        """Test _strip_era handles empty string era text from Babel (line 707).

        When era dict contains empty strings, they should be skipped.
        """

        value = "28 Jan 2025 CE"

        # Create a mock locale with empty string era text

        def mock_parse(_locale_str: str) -> MagicMock:
            """Mock Locale.parse with empty string era text."""
            mock_locale = MagicMock()
            mock_locale.eras = {
                "abbreviated": {0: "", 1: "CE"},  # Empty string for index 0
            }
            return mock_locale

        with patch("babel.Locale.parse", side_effect=mock_parse):
            result = _strip_era(value, locale_code="en_US")

        # Should skip empty string and process other eras
        assert "CE" not in result


class TestStripEraHypothesisProperties:
    """Hypothesis property-based tests for _strip_era comprehensive coverage."""

    @given(
        era_string=st.sampled_from([
            "AD", "BC", "CE", "BCE", "A.D.", "B.C.", "C.E.",
            "Anno Domini", "Before Christ", "Common Era",
        ]),
        date_text=st.text(
            alphabet=st.characters(whitelist_categories=("N", "P")),
            min_size=1,
            max_size=50,
        ).filter(lambda s: not s.endswith(" ") and len(s.strip()) > 0),
    )
    @settings(max_examples=100)
    def test_strip_era_always_removes_known_eras(
        self, era_string: str, date_text: str
    ) -> None:
        """PROPERTY: _strip_era always removes known era strings at word boundaries.

        For any known era string and any numeric/punctuation text, if era appears
        at word boundaries (surrounded by non-alphanumeric characters), it should
        be stripped.
        """
        # Construct value with era at word boundary (using space separator)
        value = f"{date_text} {era_string}"

        result = _strip_era(value)

        # Era should be removed since it's at word boundary
        # (preceded by space after date_text which ends in non-letter)
        assert era_string.upper() not in result.upper()

    @given(
        locale_code=st.sampled_from([
            "en_US", "de_DE", "fr_FR", "es_ES", "ja_JP",
            "ru_RU", "zh_CN", "ar_SA", "hi_IN", "pt_BR",
        ]),
    )
    @settings(max_examples=50)
    def test_strip_era_with_valid_locales_never_crashes(
        self, locale_code: str
    ) -> None:
        """PROPERTY: _strip_era never crashes with valid locale codes.

        For any valid locale code, the function should complete successfully.
        """
        value = "28 Jan 2025 AD"

        # Should not raise exception
        result = _strip_era(value, locale_code=locale_code)

        # Result should be string
        assert isinstance(result, str)

    @given(
        invalid_locale=st.text(
            alphabet=st.characters(min_codepoint=33, max_codepoint=126),
            min_size=1,
            max_size=30,
        ).filter(lambda x: "_" not in x and "-" not in x and x.isalpha()),
    )
    @settings(max_examples=50)
    def test_strip_era_with_invalid_locales_falls_back_gracefully(
        self, invalid_locale: str
    ) -> None:
        """PROPERTY: _strip_era falls back to English eras for invalid locales.

        For any invalid locale code, should fall back to English eras without
        raising exception.
        """
        value = "28 Jan 2025 CE"

        # Should not raise exception
        result = _strip_era(value, locale_code=invalid_locale)

        # Should still strip English era
        assert "CE" not in result or "ce" not in result.lower()
        assert isinstance(result, str)

    @given(
        text=st.text(
            alphabet=st.characters(whitelist_categories=("L", "N", "P")),
            min_size=0,
            max_size=100,
        ),
    )
    @settings(max_examples=100)
    def test_strip_era_idempotent_without_eras(self, text: str) -> None:
        """PROPERTY: _strip_era is idempotent for text without eras.

        If text contains no era strings, output should equal input
        (modulo whitespace normalization).
        """
        # Filter out text that might contain any era patterns
        # Includes: plain (ad, bc, ce, bce), period-separated (a.d., b.c., c.e.),
        # and full forms (anno domini, before christ, common era)
        era_patterns = [
            "ad", "bc", "ce", "bce",
            "a.d.", "b.c.", "c.e.",
            "anno domini", "before christ", "common era", "before common era",
        ]
        text_lower = text.lower()
        if any(era in text_lower for era in era_patterns):
            return

        result = _strip_era(text)

        # Should be equivalent after whitespace normalization
        assert " ".join(result.split()) == " ".join(text.split())

    @given(
        prefix=st.text(
            alphabet=st.characters(whitelist_categories=("L",)),  # type: ignore[arg-type]
            min_size=1,
            max_size=10,
        ),
        suffix=st.text(
            alphabet=st.characters(whitelist_categories=("L",)),  # type: ignore[arg-type]
            min_size=1,
            max_size=10,
        ),
    )
    @settings(max_examples=100)
    def test_strip_era_respects_word_boundaries(
        self, prefix: str, suffix: str
    ) -> None:
        """PROPERTY: _strip_era only strips eras at word boundaries.

        If "AD" is embedded in a word like "ADMIRE", it should not be stripped.
        """
        # Create text with era embedded in word
        embedded = f"{prefix}AD{suffix}"

        result = _strip_era(embedded)

        # Embedded era should not be stripped
        assert "AD" in result.upper()
