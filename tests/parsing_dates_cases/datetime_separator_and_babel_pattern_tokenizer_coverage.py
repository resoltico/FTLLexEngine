# mypy: ignore-errors
"""Split test cases from tests/test_parsing_dates.py."""

from tests.parsing_dates_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# DATETIME SEPARATOR AND BABEL PATTERN TOKENIZER COVERAGE
# ============================================================================


class TestTokenizeBabelPatternEdgeCases:
    """_tokenize_babel_pattern: patterns starting with a quote and unclosed sections."""

    def test_quoted_section_with_escaped_quote(self) -> None:
        """Escaped quote '' inside a quoted literal is unescaped to a single quote."""
        pattern = "'It''s a test'"
        tokens = _tokenize_babel_pattern(pattern)
        assert any("It's a test" in t for t in tokens)

    def test_unclosed_quoted_section(self) -> None:
        """Unclosed quoted literal collects remaining characters."""
        pattern = "'unclosed"
        tokens = _tokenize_babel_pattern(pattern)
        assert any("unclosed" in t for t in tokens)


class TestDatesQuotedLiteral:
    """Non-empty quoted literal in Babel date pattern tokenizes correctly."""

    def test_quoted_literal_in_pattern(self) -> None:
        """Spanish-style quoted separator 'de' is extracted as a token."""
        pattern = "d 'de' MMMM 'de' y"
        tokens = _tokenize_babel_pattern(pattern)
        assert "de" in tokens


class TestParseDateFourDigitYear:
    """4-digit year inputs are accepted for locales whose CLDR short format uses yy.

    CLDR short patterns often specify a 2-digit year (e.g. lv-LV: dd.MM.yy,
    en-US: M/d/yy). Documents commonly write dates with a 4-digit year for
    clarity and unambiguity. Both forms must parse successfully.
    """

    def test_lv_lv_two_digit_year_parses(self) -> None:
        """lv-LV short format (dd.MM.yy) parses 2-digit year correctly."""
        result, errors = parse_date("15.01.26", "lv_LV")
        assert not errors
        assert result == date(2026, 1, 15)

    def test_lv_lv_four_digit_year_parses(self) -> None:
        """lv-LV common form (dd.MM.yyyy) parses 4-digit year correctly."""
        result, errors = parse_date("15.01.2026", "lv_LV")
        assert not errors
        assert result == date(2026, 1, 15)

    def test_lv_lv_four_digit_year_roundtrip_identity(self) -> None:
        """Parse("15.01.2026", lv_LV) yields the same date as parse("15.01.26", lv_LV)."""
        result_2, _ = parse_date("15.01.26", "lv_LV")
        result_4, _ = parse_date("15.01.2026", "lv_LV")
        assert result_2 == result_4

    def test_de_de_four_digit_year_parses(self) -> None:
        """de-DE short format (dd.MM.yy) accepts 4-digit year variant."""
        result, errors = parse_date("28.01.2025", "de_DE")
        assert not errors
        assert result == date(2025, 1, 28)

    def test_pl_pl_four_digit_year_parses(self) -> None:
        """pl-PL short format accepts 4-digit year variant."""
        result, errors = parse_date("28.01.2025", "pl_PL")
        assert not errors
        assert result == date(2025, 1, 28)

    def test_two_digit_year_still_expands_via_cldr_semantics(self) -> None:
        """2-digit input still matches first (CLDR %y expansion: 00-68 -> 2000-2068)."""
        # %y in Python strptime: 00-68 -> 2000-2068, 69-99 -> 1969-1999
        result_short, _ = parse_date("28.01.68", "lv_LV")
        assert result_short is not None
        assert result_short.year == 2068  # %y expansion

    def test_extract_cldr_patterns_includes_four_digit_variant(self) -> None:
        """_get_date_patterns for lv_LV includes both %y and %Y variants for short style."""
        patterns = _get_date_patterns("lv_LV")
        strptime_patterns = [p for p, _ in patterns]
        has_two_digit = any("%y" in p for p in strptime_patterns)
        has_four_digit = any(("%Y" in p and ".%Y" in p) or "%Y" in p for p in strptime_patterns)
        assert has_two_digit, "2-digit year pattern (%y) must be present for lv_LV"
        assert has_four_digit, "4-digit year variant (%Y) must be generated for lv_LV"
