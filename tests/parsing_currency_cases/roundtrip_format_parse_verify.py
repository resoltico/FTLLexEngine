# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# Roundtrip: format -> parse -> verify
# ---------------------------------------------------------------------------


class TestRoundtripCurrency:
    """Test format -> parse -> verify roundtrip."""

    def test_roundtrip_usd_en_us(self) -> None:
        """Currency roundtrip for US English."""
        from ftllexengine.runtime.functions import currency_format

        original = Decimal("1234.56")
        formatted = currency_format(
            original, "en-US",
            currency="USD", currency_display="symbol",
        )
        result, errors = parse_currency(
            str(formatted), "en_US", default_currency="USD",
        )
        assert not errors
        assert result is not None
        assert result[0] == original
        assert result[1] == "USD"

    def test_roundtrip_eur_lv_lv(self) -> None:
        """Currency roundtrip for Latvian EUR."""
        from ftllexengine.runtime.functions import currency_format

        original = Decimal("1234.56")
        formatted = currency_format(
            original, "lv-LV",
            currency="EUR", currency_display="symbol",
        )
        result, errors = parse_currency(str(formatted), "lv_LV")
        assert not errors
        assert result is not None
        assert result[0] == original
        assert result[1] == "EUR"

    def test_roundtrip_usd_ar_eg_with_rtl_marks(self) -> None:
        """RTL locale currency output roundtrips through parse_currency()."""
        from ftllexengine.runtime.functions import currency_format

        original = Decimal("1234.56")
        formatted = currency_format(
            original, "ar-EG",
            currency="USD", currency_display="symbol",
        )
        result, errors = parse_currency(str(formatted), "ar_EG")
        assert not errors
        assert result is not None
        assert result[0] == original
        assert result[1] == "USD"

    def test_roundtrip_egp_ar_eg_local_symbol(self) -> None:
        """Localized Arabic EGP symbol roundtrips through parse_currency()."""
        from ftllexengine.runtime.functions import currency_format

        original = Decimal("1234.56")
        formatted = currency_format(
            original, "ar-EG",
            currency="EGP", currency_display="symbol",
        )
        result, errors = parse_currency(str(formatted), "ar_EG", default_currency="EGP")
        assert not errors
        assert result is not None
        assert result[0] == original
        assert result[1] == "EGP"

    def test_parse_currency_ignores_bidi_isolation_marks(self) -> None:
        """Invisible bidi controls are ignored at the parsing boundary."""
        result, errors = parse_currency("\u2068$123.45\u2069", "en_US", default_currency="USD")
        assert not errors
        assert result == (Decimal("123.45"), "USD")
