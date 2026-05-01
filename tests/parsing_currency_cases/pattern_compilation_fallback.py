# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# Pattern compilation fallback
# ---------------------------------------------------------------------------


class TestPatternCompilationFallback:
    """Test pattern compilation with empty symbol maps."""

    def test_pattern_fallback_with_empty_symbols(self) -> None:
        """Pattern falls back to ISO-code-only when no symbols."""
        from ftllexengine.parsing.currency import (
            _get_currency_pattern,
        )

        _get_currency_pattern.cache_clear()

        with patch(
            "ftllexengine.parsing.currency._get_currency_maps",
            return_value=({}, set(), {}, frozenset()),
        ):
            _get_currency_pattern.cache_clear()
            pattern = _get_currency_pattern()

            assert isinstance(pattern, re.Pattern)
            assert pattern.search("USD") is not None
            assert pattern.search("\u20ac") is None

        _get_currency_pattern.cache_clear()
        _get_currency_maps.cache_clear()
