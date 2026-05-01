# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# parse_currency: Specification examples
# ---------------------------------------------------------------------------


class TestParseCurrencySpecificationExamples:
    """Specification examples for parse_currency behavior."""

    def test_eur_symbol_prefix(self) -> None:
        """EUR symbol prefix: EUR100.50 -> (100.50, EUR)."""
        result, errors = parse_currency("\u20ac100.50", "en_US")
        assert not errors
        assert result is not None
        assert result == (Decimal("100.50"), "EUR")

    def test_eur_symbol_suffix_latvian(self) -> None:
        """EUR symbol suffix: 100,50 EUR -> (100.50, EUR) in lv_LV."""
        result, errors = parse_currency("100,50 \u20ac", "lv_LV")
        assert not errors
        assert result is not None
        assert result == (Decimal("100.50"), "EUR")

    def test_usd_with_default_currency(self) -> None:
        """$ with default_currency=USD resolves correctly."""
        result, errors = parse_currency(
            "$1,234.56", "en_US", default_currency="USD",
        )
        assert not errors
        assert result is not None
        assert result[0] == Decimal("1234.56")
        assert result[1] == "USD"

    def test_iso_code_prefix(self) -> None:
        """ISO code prefix: USD 1,234.56 -> (1234.56, USD)."""
        result, errors = parse_currency("USD 1,234.56", "en_US")
        assert not errors
        assert result is not None
        assert result == (Decimal("1234.56"), "USD")

    def test_iso_code_german_format(self) -> None:
        """German format: EUR 1.234,56 -> (1234.56, EUR)."""
        result, errors = parse_currency("EUR 1.234,56", "de_DE")
        assert not errors
        assert result is not None
        assert result == (Decimal("1234.56"), "EUR")

    def test_rupee_unambiguous(self) -> None:
        """Indian Rupee symbol is unambiguous."""
        result, errors = parse_currency("\u20b91000", "hi_IN")
        assert not errors
        assert result is not None
        assert result[1] == "INR"

    def test_arabic_indic_digits_ar_eg(self) -> None:
        """Arabic-Indic digits parse for locales with non-Latin defaults."""
        result, errors = parse_currency(
            "US$ \u0661\u0662\u066c\u0663\u0664\u0665\u066b\u0666\u0667",
            "ar_EG",
        )
        assert not errors
        assert result is not None
        assert result[0] == Decimal("12345.67")
        assert result[1] == "USD"

    def test_swiss_franc_iso(self) -> None:
        """Swiss Franc via ISO code."""
        result, errors = parse_currency("CHF 100", "de_CH")
        assert not errors
        assert result is not None
        assert result == (Decimal(100), "CHF")

    def test_cny_chinese_locale(self) -> None:
        """Yen symbol resolves to CNY in Chinese locales."""
        result, errors = parse_currency(
            "\u00a51000", "zh_CN", infer_from_locale=True,
        )
        assert not errors
        assert result is not None
        assert result[1] == "CNY"

    def test_jpy_japanese_locale(self) -> None:
        """Yen symbol resolves to JPY in Japanese locales."""
        result, errors = parse_currency(
            "\u00a512,345", "ja_JP", infer_from_locale=True,
        )
        assert not errors
        assert result is not None
        assert result[1] == "JPY"

    def test_gbp_british_locale(self) -> None:
        """Pound symbol resolves to GBP in British locales."""
        result, errors = parse_currency(
            "\u00a3999.99", "en_GB", infer_from_locale=True,
        )
        assert not errors
        assert result is not None
        assert result == (Decimal("999.99"), "GBP")
