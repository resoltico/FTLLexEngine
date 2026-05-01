# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# Property: Invalid inputs never crash, always return errors
# ---------------------------------------------------------------------------


class TestInvalidCurrencyInputs:
    """Property-based tests for invalid currency input handling."""

    @given(data=invalid_currency_inputs())
    def test_invalid_input_returns_error(
        self, data: tuple[str, str]
    ) -> None:
        """PROPERTY: Invalid inputs return error tuple, never crash."""
        value, locale = data
        is_empty = value == ""
        event(f"is_empty={is_empty}")

        result, errors = parse_currency(value, locale)
        assert result is None
        assert len(errors) > 0

    @given(
        invalid_value=st.text(min_size=1, max_size=30).filter(
            lambda x: not any(c.isdigit() for c in x)
        )
    )
    def test_no_digits_always_fails(
        self, invalid_value: str
    ) -> None:
        """PROPERTY: Values without digits always fail to parse."""
        has_currency_char = any(
            c in invalid_value for c in "\u20ac$\u00a3\u00a5\u20b9"
        )
        event(f"has_currency_char={has_currency_char}")
        val_len = "short" if len(invalid_value) <= 5 else "long"
        event(f"value_length={val_len}")

        result, _ = parse_currency(invalid_value, "en_US")
        assert result is None
