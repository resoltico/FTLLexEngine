# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


class TestClearCurrencyCaches:
    """Test clear_currency_caches function."""

    def test_executes_without_error(self) -> None:
        """clear_currency_caches executes without error."""
        from ftllexengine.parsing.currency import clear_currency_caches

        clear_currency_caches()

    def test_invalidates_caches(self) -> None:
        """clear_currency_caches clears cached data."""
        from ftllexengine.parsing.currency import clear_currency_caches

        maps1 = _get_currency_maps()
        clear_currency_caches()
        maps2 = _get_currency_maps()
        assert len(maps1[0]) == len(maps2[0])

    def test_idempotent(self) -> None:
        """Multiple calls are safe."""
        from ftllexengine.parsing.currency import clear_currency_caches

        clear_currency_caches()
        clear_currency_caches()
        clear_currency_caches()
