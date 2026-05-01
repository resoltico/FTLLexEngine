# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# Property: ISO code inputs always resolve correctly
# ---------------------------------------------------------------------------


class TestISOCodeParsing:
    """Property-based tests for ISO code currency parsing."""

    @settings(deadline=None)
    @given(data=iso_code_currency_inputs())
    def test_iso_code_parses_to_correct_currency(
        self, data: tuple[str, str, str]
    ) -> None:
        """PROPERTY: ISO codes resolve to the correct currency."""
        value, locale, expected_code = data
        event(f"iso_code={expected_code}")

        result, errors = parse_currency(value, locale)
        assert result is not None, f"Failed to parse: {value!r} ({locale})"
        amount, code = result
        assert code == expected_code
        assert isinstance(amount, Decimal)
        assert errors == ()
