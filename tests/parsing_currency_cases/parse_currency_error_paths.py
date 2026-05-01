# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# parse_currency: Error paths
# ---------------------------------------------------------------------------


class TestParseCurrencyErrors:
    """Test error handling in parse_currency."""

    def test_no_symbol_returns_error(self) -> None:
        """Missing currency symbol returns error."""
        result, errors = parse_currency("1,234.56", "en_US")
        assert result is None
        assert len(errors) == 1

    def test_invalid_input_returns_error(self) -> None:
        """Non-parseable input returns error."""
        result, errors = parse_currency("invalid", "en_US")
        assert result is None
        assert len(errors) == 1

    def test_invalid_number_with_symbol(self) -> None:
        """Invalid number with currency symbol returns error."""
        result, errors = parse_currency("\u20acinvalid", "en_US")
        assert result is None
        assert len(errors) == 1

    def test_empty_string(self) -> None:
        """Empty string returns error."""
        result, errors = parse_currency("", "en_US")
        assert result is None
        assert len(errors) == 1

    def test_only_symbol(self) -> None:
        """Symbol without number returns error."""
        result, errors = parse_currency("\u20ac", "en_US")
        assert result is None
        assert len(errors) == 1

    def test_invalid_locale(self) -> None:
        """Invalid locale returns error with locale info."""
        result, errors = parse_currency(
            "\u20ac10.50", "invalid_LOCALE_CODE",
        )
        assert result is None
        assert len(errors) == 1
        assert any("locale" in str(err).lower() for err in errors)

    def test_malformed_locale(self) -> None:
        """Malformed locale returns error."""
        result, errors = parse_currency("$100", "!!!invalid@@@")
        assert result is None
        assert len(errors) == 1

    def test_ambiguous_without_default_returns_error(self) -> None:
        """$ without default_currency or inference returns error."""
        result, errors = parse_currency("$100", "en_US")
        assert result is None
        assert len(errors) == 1
