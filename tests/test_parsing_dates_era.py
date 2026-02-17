"""Era handling tests for parsing/dates.py.

Tests _strip_era word-boundary logic, _babel_to_strptime era token detection,
localized era loading from Babel (mock and real), early-return paths in
_extract_era_strings_from_babel_locale, ImportError fallback in
_get_localized_era_strings, and property-based era stripping invariants.

Python 3.13+.
"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from hypothesis import event, given, settings
from hypothesis import strategies as st

import ftllexengine.core.babel_compat as _bc
from ftllexengine.parsing.dates import (
    _babel_to_strptime,
    _extract_era_strings_from_babel_locale,
    _get_localized_era_strings,
    _strip_era,
    parse_date,
    parse_datetime,
)

if TYPE_CHECKING:
    pass


# ============================================================================
# _strip_era: Word-Boundary Logic
# ============================================================================


class TestStripEraWordBoundary:
    """Test _strip_era word-boundary matching and whitespace normalization."""

    def test_strip_era_with_ad(self) -> None:
        """_strip_era removes 'AD' at word boundary."""
        assert _strip_era("28 Jan 2025 AD") == "28 Jan 2025"

    def test_strip_era_with_anno_domini(self) -> None:
        """_strip_era removes 'Anno Domini' multi-word era."""
        assert _strip_era("Anno Domini 2025-01-28") == "2025-01-28"

    def test_strip_era_with_bc(self) -> None:
        """_strip_era removes 'BC'."""
        assert _strip_era("100 BC") == "100"

    def test_strip_era_with_ce(self) -> None:
        """_strip_era removes 'CE'."""
        assert _strip_era("2025 CE") == "2025"

    def test_strip_era_with_bce(self) -> None:
        """_strip_era removes 'BCE'."""
        assert _strip_era("100 BCE") == "100"

    def test_strip_era_case_insensitive(self) -> None:
        """_strip_era is case-insensitive."""
        assert _strip_era("2025 ad") == "2025"
        assert _strip_era("2025 AD") == "2025"
        assert _strip_era("2025 Ad") == "2025"

    def test_strip_era_normalizes_whitespace(self) -> None:
        """_strip_era collapses multiple spaces to single space."""
        assert _strip_era("28   Jan    2025   AD") == "28 Jan 2025"

    def test_strip_era_no_era_present(self) -> None:
        """_strip_era returns value unchanged when no era present."""
        assert _strip_era("2025-01-28") == "2025-01-28"

    def test_strip_era_multiple_eras(self) -> None:
        """_strip_era removes all era strings from value."""
        result = _strip_era("AD 2025 CE")
        assert "AD" not in result
        assert "CE" not in result
        assert result == "2025"

    def test_strip_era_embedded_in_word_not_stripped(self) -> None:
        """_strip_era does NOT strip era embedded in words."""
        assert _strip_era("ADMIRE 2025") == "ADMIRE 2025"
        assert _strip_era("ABCD 100") == "ABCD 100"
        assert _strip_era("ONCE upon 2025") == "ONCE upon 2025"

    def test_strip_era_at_word_boundary_start_not_end(self) -> None:
        """Era at start but not end word boundary is not stripped."""
        assert "Admiral" in _strip_era("Admiral 2025")

    def test_strip_era_at_word_boundary_end_not_start(self) -> None:
        """Era at end but not start word boundary is not stripped."""
        assert "CAD" in _strip_era("CAD 2025")


# ============================================================================
# _strip_era: Localized Era Loading (Babel)
# ============================================================================


class TestStripEraLocalizedLoading:
    """Test _strip_era with locale-aware era strings loaded from Babel."""

    def test_strip_era_with_locale_code_loads_babel_eras(self) -> None:
        """_strip_era loads localized era strings when locale_code given."""
        result = _strip_era("28 Jan 2025 AD", locale_code="en_US")
        assert "AD" not in result
        assert result == "28 Jan 2025"

    def test_strip_era_with_german_locale(self) -> None:
        """_strip_era strips German localized era 'n. Chr.'."""
        result = _strip_era("28. Januar 2025 n. Chr.", locale_code="de_DE")
        assert "n. Chr." not in result

    def test_strip_era_with_japanese_locale(self) -> None:
        """_strip_era handles Japanese locale without crashing."""
        result = _strip_era("2025年1月28日 西暦", locale_code="ja_JP")
        assert isinstance(result, str)

    def test_strip_era_unknown_locale_falls_back(self) -> None:
        """_strip_era falls back to English eras for unknown locale."""
        result = _strip_era("28 Jan 2025 AD", locale_code="xx-INVALID-LOCALE")
        assert "AD" not in result
        assert result == "28 Jan 2025"

    def test_strip_era_value_error_falls_back(self) -> None:
        """_strip_era falls back to English eras on ValueError."""
        result = _strip_era(
            "28 Jan 2025 BC", locale_code="not-a-valid-locale-format"
        )
        assert "BC" not in result
        assert result == "28 Jan 2025"

    def test_strip_era_locale_none_skips_babel(self) -> None:
        """_strip_era with locale_code=None uses only English eras."""
        result = _strip_era("28 Jan 2025 AD", locale_code=None)
        assert "AD" not in result
        assert result == "28 Jan 2025"

    def test_strip_era_babel_import_error_falls_back(self) -> None:
        """_strip_era falls back to English eras when Babel unavailable."""
        original_import = builtins.__import__

        def mock_import(
            name: str,
            globals_: dict[str, object] | None = None,
            locals_: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            if name == "babel":
                msg = "No module named 'babel'"
                raise ImportError(msg)
            return original_import(name, globals_, locals_, fromlist, level)

        with patch.object(builtins, "__import__", side_effect=mock_import):
            result = _strip_era("28 Jan 2025 CE", locale_code="en_US")

        assert "CE" not in result
        assert result == "28 Jan 2025"

    def test_strip_era_locale_no_eras_attribute(self) -> None:
        """_strip_era handles locale without eras attribute."""

        def mock_parse(_locale_str: str) -> MagicMock:
            return MagicMock(spec=[])

        with patch("babel.Locale.parse", side_effect=mock_parse):
            result = _strip_era("28 Jan 2025 AD", locale_code="en_US")

        assert "AD" not in result

    def test_strip_era_locale_empty_eras_dict(self) -> None:
        """_strip_era handles locale with empty eras dict."""

        def mock_parse(_locale_str: str) -> MagicMock:
            mock_locale = MagicMock()
            mock_locale.eras = {}
            return mock_locale

        with patch("babel.Locale.parse", side_effect=mock_parse):
            result = _strip_era("28 Jan 2025 BC", locale_code="en_US")

        assert "BC" not in result

    def test_strip_era_locale_partial_era_widths(self) -> None:
        """_strip_era handles locale with only some era width keys."""

        def mock_parse(_locale_str: str) -> MagicMock:
            mock_locale = MagicMock()
            mock_locale.eras = {
                "wide": {0: "Before Common Era", 1: "Common Era"},
            }
            return mock_locale

        with patch("babel.Locale.parse", side_effect=mock_parse):
            result = _strip_era("28 Jan 2025 CE", locale_code="en_US")

        assert "CE" not in result or "Common Era" not in result

    def test_strip_era_locale_partial_era_indices(self) -> None:
        """_strip_era handles era dict with only some indices."""

        def mock_parse(_locale_str: str) -> MagicMock:
            mock_locale = MagicMock()
            mock_locale.eras = {
                "wide": {1: "Anno Domini"},
            }
            return mock_locale

        with patch("babel.Locale.parse", side_effect=mock_parse):
            result = _strip_era("28 Jan 2025 AD", locale_code="en_US")

        assert isinstance(result, str)

    def test_strip_era_locale_duplicate_era_not_added(self) -> None:
        """_strip_era does not add duplicate era strings."""

        def mock_parse(_locale_str: str) -> MagicMock:
            mock_locale = MagicMock()
            mock_locale.eras = {"abbreviated": {1: "AD"}}
            return mock_locale

        with patch("babel.Locale.parse", side_effect=mock_parse):
            result = _strip_era("28 Jan 2025 AD", locale_code="en_US")

        assert "AD" not in result

    def test_strip_era_locale_none_era_text(self) -> None:
        """_strip_era handles None era text from Babel."""

        def mock_parse(_locale_str: str) -> MagicMock:
            mock_locale = MagicMock()
            mock_locale.eras = {"wide": {0: None, 1: "Common Era"}}
            return mock_locale

        with patch("babel.Locale.parse", side_effect=mock_parse):
            result = _strip_era("28 Jan 2025 BC", locale_code="en_US")

        assert "BC" not in result

    def test_strip_era_locale_empty_string_era_text(self) -> None:
        """_strip_era handles empty string era text from Babel."""

        def mock_parse(_locale_str: str) -> MagicMock:
            mock_locale = MagicMock()
            mock_locale.eras = {"abbreviated": {0: "", 1: "CE"}}
            return mock_locale

        with patch("babel.Locale.parse", side_effect=mock_parse):
            result = _strip_era("28 Jan 2025 CE", locale_code="en_US")

        assert "CE" not in result


# ============================================================================
# _babel_to_strptime: Era Token Detection
# ============================================================================


class TestBabelToStrptimeEraToken:
    """Test _babel_to_strptime era token handling."""

    def test_era_token_g(self) -> None:
        """'G' token sets has_era=True and is removed."""
        pattern, has_era = _babel_to_strptime("d MMM y G")
        assert has_era is True
        assert "G" not in pattern

    def test_era_token_gg(self) -> None:
        """'GG' token sets has_era=True."""
        _, has_era = _babel_to_strptime("y-MM-dd GG")
        assert has_era is True

    def test_era_token_ggg(self) -> None:
        """'GGG' token sets has_era=True."""
        _, has_era = _babel_to_strptime("GGG y MMMM d")
        assert has_era is True

    def test_era_token_gggg(self) -> None:
        """'GGGG' full era token sets has_era=True."""
        pattern, has_era = _babel_to_strptime("d MMMM y GGGG")
        assert has_era is True
        assert "GGGG" not in pattern

    def test_no_era_token(self) -> None:
        """Pattern without era token has has_era=False."""
        pattern, has_era = _babel_to_strptime("d MMM y")
        assert has_era is False
        assert "%d" in pattern
        assert "%b" in pattern
        assert "%Y" in pattern


# ============================================================================
# _extract_era_strings_from_babel_locale: Early Return
# ============================================================================


class TestExtractEraStringsEarlyReturn:
    """Test early return paths in _extract_era_strings_from_babel_locale."""

    def test_locale_without_eras_attribute(self) -> None:
        """Returns empty list when locale lacks eras attribute."""
        mock_locale = MagicMock(spec=[])
        assert _extract_era_strings_from_babel_locale(mock_locale) == []

    def test_locale_with_none_eras(self) -> None:
        """Returns empty list when locale.eras is None."""
        mock_locale = MagicMock()
        mock_locale.eras = None
        assert _extract_era_strings_from_babel_locale(mock_locale) == []

    def test_locale_with_empty_eras_dict(self) -> None:
        """Returns empty list when locale.eras is empty dict."""
        mock_locale = MagicMock()
        mock_locale.eras = {}
        assert _extract_era_strings_from_babel_locale(mock_locale) == []


# ============================================================================
# _get_localized_era_strings: ImportError Handling
# ============================================================================


class TestGetLocalizedEraStringsImportError:
    """Test _get_localized_era_strings ImportError fallback."""

    def test_returns_empty_tuple_without_babel(self) -> None:
        """Returns empty tuple when Babel is not available."""
        _get_localized_era_strings.cache_clear()
        _bc._babel_available = None

        original_import = builtins.__import__

        def mock_import(
            name: str,
            globals_: dict[str, object] | None = None,
            locals_: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            if name == "babel":
                msg = "No module named 'babel'"
                raise ImportError(msg)
            return original_import(name, globals_, locals_, fromlist, level)

        try:
            with patch.object(
                builtins, "__import__", side_effect=mock_import
            ):
                result = _get_localized_era_strings("en_US")

            assert result == ()
        finally:
            _get_localized_era_strings.cache_clear()
            _bc._babel_available = None

    def test_import_error_result_is_cached(self) -> None:
        """ImportError result is cached (only one import attempt)."""
        _get_localized_era_strings.cache_clear()
        _bc._babel_available = None

        original_import = builtins.__import__
        import_call_count = 0

        def mock_import_counting(
            name: str,
            globals_: dict[str, object] | None = None,
            locals_: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            nonlocal import_call_count
            if name == "babel":
                import_call_count += 1
                msg = "No module named 'babel'"
                raise ImportError(msg)
            return original_import(name, globals_, locals_, fromlist, level)

        try:
            with patch.object(
                builtins, "__import__", side_effect=mock_import_counting
            ):
                result1 = _get_localized_era_strings("en_US")
                result2 = _get_localized_era_strings("en_US")

            assert result1 == ()
            assert result2 == ()
            assert import_call_count == 1
        finally:
            _get_localized_era_strings.cache_clear()
            _bc._babel_available = None

    @given(
        locale_code=st.text(
            alphabet=st.characters(whitelist_categories=("L", "P")),
            min_size=2,
            max_size=10,
        ).filter(
            lambda x: x.isalnum() or "_" in x or "-" in x
        ),
    )
    @settings(max_examples=50)
    def test_any_locale_returns_empty_without_babel(
        self, locale_code: str
    ) -> None:
        """PROPERTY: Always returns empty tuple without Babel.

        For any locale code, if Babel is unavailable, returns empty tuple
        without raising exception.
        """
        _get_localized_era_strings.cache_clear()
        _bc._babel_available = None

        has_separator = "_" in locale_code or "-" in locale_code
        event(f"has_separator={has_separator}")

        original_import = builtins.__import__

        def mock_import(
            name: str,
            globals_: dict[str, object] | None = None,
            locals_: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            if name == "babel":
                msg = "No module named 'babel'"
                raise ImportError(msg)
            return original_import(name, globals_, locals_, fromlist, level)

        try:
            with patch.object(
                builtins, "__import__", side_effect=mock_import
            ):
                result = _get_localized_era_strings(locale_code)

            assert result == ()
        finally:
            _get_localized_era_strings.cache_clear()
            _bc._babel_available = None


# ============================================================================
# _strip_era: Hypothesis Properties
# ============================================================================


class TestStripEraProperties:
    """Property-based tests for _strip_era invariants."""

    @given(
        era_string=st.sampled_from([
            "AD", "BC", "CE", "BCE", "A.D.", "B.C.", "C.E.",
            "Anno Domini", "Before Christ", "Common Era",
        ]),
        date_text=st.text(
            alphabet=st.characters(whitelist_categories=("N", "P")),
            min_size=1,
            max_size=50,
        ).filter(
            lambda s: not s.endswith(" ") and len(s.strip()) > 0
        ),
    )
    @settings(max_examples=100)
    def test_always_removes_known_eras(
        self, era_string: str, date_text: str
    ) -> None:
        """PROPERTY: Known era strings at word boundaries are always removed."""
        event(f"era={era_string}")

        value = f"{date_text} {era_string}"
        result = _strip_era(value)
        assert era_string.upper() not in result.upper()

    @given(
        locale_code=st.sampled_from([
            "en_US", "de_DE", "fr_FR", "es_ES", "ja_JP",
            "ru_RU", "zh_CN", "ar_SA", "hi_IN", "pt_BR",
        ]),
    )
    @settings(max_examples=50)
    def test_valid_locales_never_crash(self, locale_code: str) -> None:
        """PROPERTY: _strip_era never crashes with valid locale codes."""
        event(f"locale={locale_code}")

        result = _strip_era("28 Jan 2025 AD", locale_code=locale_code)
        assert isinstance(result, str)

    @given(
        invalid_locale=st.text(
            alphabet=st.characters(
                min_codepoint=33, max_codepoint=126
            ),
            min_size=1,
            max_size=30,
        ).filter(
            lambda x: "_" not in x and "-" not in x and x.isalpha()
        ),
    )
    @settings(max_examples=50)
    def test_invalid_locales_fall_back(self, invalid_locale: str) -> None:
        """PROPERTY: Invalid locales fall back to English eras."""
        length = "short" if len(invalid_locale) <= 5 else "long"
        event(f"locale_length={length}")

        result = _strip_era("28 Jan 2025 CE", locale_code=invalid_locale)
        assert "CE" not in result or "ce" not in result.lower()
        assert isinstance(result, str)

    @given(
        text=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "P")
            ),
            min_size=0,
            max_size=100,
        ),
    )
    @settings(max_examples=100)
    def test_idempotent_without_eras(self, text: str) -> None:
        """PROPERTY: Text without eras is unchanged (modulo whitespace)."""
        era_patterns = [
            "ad", "bc", "ce", "bce",
            "a.d.", "b.c.", "c.e.",
            "anno domini", "before christ",
            "common era", "before common era",
        ]
        text_lower = text.lower()
        if any(era in text_lower for era in era_patterns):
            return

        has_whitespace = " " in text
        event(f"has_whitespace={has_whitespace}")

        result = _strip_era(text)
        assert " ".join(result.split()) == " ".join(text.split())

    @given(
        prefix=st.text(
            alphabet=st.characters(
                whitelist_categories=("L",)  # type: ignore[arg-type]
            ),
            min_size=1,
            max_size=10,
        ),
        suffix=st.text(
            alphabet=st.characters(
                whitelist_categories=("L",)  # type: ignore[arg-type]
            ),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(max_examples=100)
    def test_respects_word_boundaries(
        self, prefix: str, suffix: str
    ) -> None:
        """PROPERTY: Era embedded in word is not stripped."""
        embedded = f"{prefix}AD{suffix}"
        event(f"prefix_len={len(prefix)}")

        result = _strip_era(embedded)
        assert "AD" in result.upper()


# ============================================================================
# Integration: Date/Datetime Parsing with Era
# ============================================================================


class TestDateParsingWithEra:
    """Integration tests for date/datetime parsing with era strings."""

    def test_parse_date_with_era_in_locale(self) -> None:
        """parse_date handles era string in locale-specific input."""
        _result, errors = parse_date("28.01.2025 n. Chr.", "de_DE")
        assert errors is not None

    def test_parse_datetime_with_era(self) -> None:
        """parse_datetime handles era string in input."""
        _result, errors = parse_datetime("2025-01-28 14:30 AD", "en_US")
        assert errors is not None


# ============================================================================
# Asian Locale Datetime Ordering (exercises era + ordering paths)
# ============================================================================


class TestAsianLocaleDatetimeOrdering:
    """Test Asian locales which may use different datetime orderings."""

    @given(
        locale_code=st.sampled_from(
            ["zh_CN", "ja_JP", "ko_KR", "th_TH"]
        ),
    )
    @settings(max_examples=10)
    def test_asian_locales_datetime_patterns(
        self, locale_code: str
    ) -> None:
        """PROPERTY: Asian locale datetime patterns are valid tuples."""
        from ftllexengine.parsing.dates import _get_datetime_patterns

        event(f"locale={locale_code}")

        _get_datetime_patterns.cache_clear()
        patterns = _get_datetime_patterns(locale_code)
        assert isinstance(patterns, tuple)
        _get_datetime_patterns.cache_clear()
