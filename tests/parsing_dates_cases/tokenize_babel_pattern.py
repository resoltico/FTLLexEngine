# mypy: ignore-errors
"""Split test cases from tests/test_parsing_dates.py."""

from tests.parsing_dates_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# _tokenize_babel_pattern
# ============================================================================


class TestTokenizeBabelPattern:
    """Test CLDR pattern tokenizer quote handling."""

    def test_simple_quoted_literal(self) -> None:
        """Simple quoted literal is extracted as single token."""
        tokens = _tokenize_babel_pattern("h 'at' a")
        assert "at" in tokens

    def test_escaped_quote_outside(self) -> None:
        """Two quotes '' outside a quoted section produce literal quote."""
        tokens = _tokenize_babel_pattern("h''mm")
        assert "'" in tokens

    def test_escaped_quote_inside(self) -> None:
        """Two quotes '' inside quoted text produce literal quote."""
        tokens = _tokenize_babel_pattern("h 'o''clock' a")
        assert "o'clock" in tokens

    def test_irish_locale_pattern(self) -> None:
        """Quoted literals in locale patterns."""
        tokens = _tokenize_babel_pattern("d MMMM 'de' yyyy")
        assert "de" in tokens
        assert "d" in tokens
        assert "yyyy" in tokens

    def test_standard_pattern_unchanged(self) -> None:
        """Standard patterns without quotes work correctly."""
        tokens = _tokenize_babel_pattern("yyyy-MM-dd")
        assert tokens == ["yyyy", "-", "MM", "-", "dd"]

    def test_latvian_pattern(self) -> None:
        """Latvian date pattern d.MM.yyyy."""
        tokens = _tokenize_babel_pattern("d.MM.yyyy")
        assert tokens == ["d", ".", "MM", ".", "yyyy"]

    def test_empty_pattern(self) -> None:
        """Empty pattern produces empty token list."""
        assert _tokenize_babel_pattern("") == []

    def test_unclosed_quote(self) -> None:
        """Unclosed quote at end is handled gracefully."""
        tokens = _tokenize_babel_pattern("h 'unclosed")
        assert "h" in tokens
        assert "unclosed" in tokens

    def test_empty_quoted_section(self) -> None:
        """Empty quotes '' produce single quote, not empty token."""
        tokens = _tokenize_babel_pattern("a''b")
        assert "'" in tokens
        assert "a" in tokens
        assert "b" in tokens

    def test_adjacent_quoted_sections(self) -> None:
        """Multiple adjacent quotes produce multiple literal quotes."""
        tokens = _tokenize_babel_pattern("''''")
        assert tokens.count("'") == 2

    def test_just_two_quotes(self) -> None:
        """Just '' produces single quote."""
        tokens = _tokenize_babel_pattern("''")
        assert "'" in tokens

    def test_three_quotes(self) -> None:
        """Three quotes: first two produce quote, third starts section."""
        tokens = _tokenize_babel_pattern("'''")
        assert "'" in tokens

    def test_real_world_german_pattern(self) -> None:
        """German pattern with quoted 'um' literal."""
        tokens = _tokenize_babel_pattern("d. MMMM yyyy 'um' HH:mm")
        assert "um" in tokens
        assert "d" in tokens
        assert "MMMM" in tokens

    def test_real_world_at_pattern(self) -> None:
        """Pattern with 'at' literal."""
        tokens = _tokenize_babel_pattern(
            "EEEE, MMMM d, y 'at' h:mm a"
        )
        assert "at" in tokens

    def test_pattern_ending_in_quote(self) -> None:
        """Pattern ending with unclosed quote handled gracefully."""
        tokens = _tokenize_babel_pattern("yyyy 'test")
        assert "yyyy" in tokens
        assert "test" in tokens

    def test_russian_quoted_literal(self) -> None:
        """Russian pattern with quoted Cyrillic year marker."""
        pattern = "d MMMM y '\u0433'."
        tokens = _tokenize_babel_pattern(pattern)
        assert "\u0433" in tokens
        assert "d" in tokens
        assert "MMMM" in tokens
        assert "y" in tokens
        assert "." in tokens

    def test_spanish_quoted_de(self) -> None:
        """Spanish pattern d 'de' MMMM 'de' y with quoted 'de'."""
        tokens = _tokenize_babel_pattern("d 'de' MMMM 'de' y")
        assert "de" in tokens
        assert "d" in tokens
        assert "MMMM" in tokens
        assert "y" in tokens
