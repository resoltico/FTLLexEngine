# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# _resolve_currency_code internal paths
# ---------------------------------------------------------------------------


class TestResolveCurrencyCode:
    """Test _resolve_currency_code edge cases."""

    def test_unknown_symbol_returns_error(self) -> None:
        """Unknown symbol returns error."""
        result, error = currency_module._resolve_currency_code(
            "ZZZZZ", "en_US", "ZZZZZ 100",
            default_currency=None, infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_invalid_default_currency_format(self) -> None:
        """Ambiguous symbol with invalid default_currency returns error."""
        result, error = currency_module._resolve_currency_code(
            "$", "en_US", "$100",
            default_currency="invalid", infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_lowercase_default_currency_rejected(self) -> None:
        """Lowercase default_currency is rejected (ISO requires uppercase)."""
        result, error = currency_module._resolve_currency_code(
            "$", "en_US", "$100",
            default_currency="usd", infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_short_default_currency_rejected(self) -> None:
        """2-letter default_currency is rejected (ISO requires 3)."""
        result, error = currency_module._resolve_currency_code(
            "$", "en_US", "$100",
            default_currency="US", infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_long_default_currency_rejected(self) -> None:
        """4-letter default_currency is rejected (ISO requires 3)."""
        result, error = currency_module._resolve_currency_code(
            "$", "en_US", "$100",
            default_currency="USDD", infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_numeric_default_currency_rejected(self) -> None:
        """Numeric default_currency is rejected (ISO requires letters)."""
        result, error = currency_module._resolve_currency_code(
            "$", "en_US", "$100",
            default_currency="123", infer_from_locale=False,
        )
        assert result is None
        assert error is not None

    def test_invalid_iso_code_not_in_cldr(self) -> None:
        """3-letter uppercase code not in CLDR returns error."""
        result, errors = parse_currency("AAA 100", "en_US")
        assert result is None
        assert len(errors) == 1

    @given(
        default=st.from_regex(r"[a-z]{3}", fullmatch=True)
    )
    @settings(max_examples=20)
    def test_lowercase_codes_always_rejected(
        self, default: str
    ) -> None:
        """PROPERTY: Lowercase 3-letter codes always rejected."""
        event(f"code_sample={default[:2]}")
        result, error = currency_module._resolve_currency_code(
            "$", "en_US", "$100",
            default_currency=default, infer_from_locale=False,
        )
        assert result is None
        assert error is not None
