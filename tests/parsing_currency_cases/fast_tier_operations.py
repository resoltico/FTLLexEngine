# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# Fast tier operations
# ---------------------------------------------------------------------------


class TestFastTierOperations:
    """Test fast tier currency operations (no CLDR scan)."""

    def test_fast_tier_symbols_available(self) -> None:
        """Fast tier unambiguous symbols always available."""
        from ftllexengine.parsing.currency import (
            _FAST_TIER_UNAMBIGUOUS_SYMBOLS,
            _get_currency_maps_fast,
        )

        symbols, _, _, _ = _get_currency_maps_fast()
        assert len(symbols) > 0
        assert "\u20ac" in symbols
        assert symbols["\u20ac"] == "EUR"
        assert symbols == _FAST_TIER_UNAMBIGUOUS_SYMBOLS

    def test_currency_pattern_compiles_and_matches(self) -> None:
        """Currency regex pattern compiles and matches."""
        from ftllexengine.parsing.currency import (
            _get_currency_pattern,
        )

        _get_currency_pattern.cache_clear()
        try:
            pattern = _get_currency_pattern()
            assert pattern.search("\u20ac100") is not None
            assert pattern.search("USD 100") is not None
        finally:
            _get_currency_pattern.cache_clear()

    def test_currency_pattern_longest_match_first(self) -> None:
        """Currency pattern matches multi-char symbols before prefixes."""
        from ftllexengine.parsing.currency import (
            _get_currency_pattern,
        )

        _get_currency_pattern.cache_clear()
        try:
            pattern = _get_currency_pattern()
            # Rs must match before R
            m = pattern.search("Rs100")
            assert m is not None
            assert m.group() == "Rs"
            # kr. must match before kr
            m = pattern.search("kr.500")
            assert m is not None
            assert m.group() == "kr."
        finally:
            _get_currency_pattern.cache_clear()
