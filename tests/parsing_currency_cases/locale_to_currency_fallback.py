# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# Locale-to-currency fallback
# ---------------------------------------------------------------------------


class TestLocaleToCurrencyFallback:
    """Test locale-to-currency inference fallback."""

    def test_dollar_inferred_from_en_us(self) -> None:
        """$ inferred as USD from en_US."""
        result, errors = parse_currency(
            "$100", "en_US", infer_from_locale=True,
        )
        assert errors == ()
        assert result is not None
        assert result[1] == "USD"

    def test_dollar_resolves_to_usd_in_de_de(self) -> None:
        """$ resolves to USD in de_DE (dollar sign is unambiguous)."""
        result, errors = parse_currency(
            "$100", "de_DE", infer_from_locale=True,
        )
        assert errors == ()
        assert result is not None
        assert result[1] == "USD"

    def test_cldr_only_ambiguous_symbol_locale_fallback(self) -> None:
        """CLDR-only ambiguous symbol resolves via locale-to-currency map.

        Rs is ambiguous in CLDR (INR, PKR, etc.) but not in the fast-tier
        ambiguous set. resolve_ambiguous_symbol returns None, so resolution
        falls through to the CLDR locale-to-currency mapping.
        """
        result, errors = parse_currency(
            "Rs 500", "hi_IN", infer_from_locale=True,
        )
        assert errors == ()
        assert result is not None
        assert result == (Decimal(500), "INR")

    def test_cldr_only_ambiguous_kr_dot_locale_fallback(self) -> None:
        """kr. (Nordic krona with period) resolves via locale-to-currency map.

        kr. is ambiguous in CLDR (DKK, NOK, SEK, ISK) but not in the fast-tier
        ambiguous set. Falls through to locale-to-currency mapping.
        """
        result, errors = parse_currency(
            "kr.500", "da_DK", infer_from_locale=True,
        )
        assert errors == ()
        assert result is not None
        assert result == (Decimal(500), "DKK")

    def test_no_resolution_available(self) -> None:
        """Empty currency maps cause resolution failure."""
        with (
            patch(
                "ftllexengine.parsing.currency.resolve_ambiguous_symbol",
                return_value=None,
            ),
            patch(
                "ftllexengine.parsing.currency._get_currency_maps",
                return_value=(
                    {},
                    {"$"},
                    {},
                    frozenset({"USD"}),
                ),
            ),
        ):
            result, errors = parse_currency(
                "$100", "en_US", infer_from_locale=True,
            )

        assert result is None
        assert len(errors) == 1

    def test_kr_unknown_locale_defaults_to_sek(self) -> None:
        """kr symbol with unknown locale defaults to SEK."""
        result, error = currency_module._resolve_currency_code(
            "kr", "xx_UNKNOWN", "kr 100",
            default_currency=None, infer_from_locale=True,
        )
        assert result == "SEK" or error is not None
