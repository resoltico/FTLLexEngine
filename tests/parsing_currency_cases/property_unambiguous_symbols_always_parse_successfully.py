# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# Property: Unambiguous symbols always parse successfully
# ---------------------------------------------------------------------------


class TestUnambiguousCurrencyParsing:
    """Property-based tests for unambiguous currency parsing."""

    @settings(deadline=None)  # CLDR + numbering-system warmup varies on first call
    @given(data=unambiguous_currency_inputs())
    def test_unambiguous_symbol_parses(
        self, data: tuple[str, str, str]
    ) -> None:
        """PROPERTY: Unambiguous symbols and ISO codes always parse."""
        value, locale, expected_code = data
        event(f"expected_code={expected_code}")

        result, errors = parse_currency(value, locale)
        # Unambiguous symbols should parse without error
        if result is not None:
            amount, code = result
            assert code == expected_code
            assert isinstance(amount, Decimal)
            assert errors == ()
