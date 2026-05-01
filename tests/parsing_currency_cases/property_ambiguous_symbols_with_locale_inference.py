# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# Property: Ambiguous symbols with locale inference
# ---------------------------------------------------------------------------


class TestAmbiguousSymbolResolution:
    """Property-based tests for ambiguous symbol resolution."""

    @given(data=ambiguous_currency_inputs())
    def test_ambiguous_with_default_resolves(
        self, data: tuple[str, str, str, str]
    ) -> None:
        """PROPERTY: Ambiguous symbols with default_currency resolve."""
        value, locale, default_currency, expected = data
        event(f"locale={locale}")

        result, errors = parse_currency(
            value, locale, default_currency=default_currency,
        )
        if result is not None:
            _, code = result
            assert code == expected
            assert errors == ()

    @given(
        locale_currency=st.sampled_from([
            ("en_US", "USD"), ("en_CA", "CAD"),
            ("en_AU", "AUD"), ("en_NZ", "NZD"),
            ("es_MX", "MXN"), ("es_AR", "ARS"),
        ])
    )
    def test_dollar_locale_inference(
        self, locale_currency: tuple[str, str]
    ) -> None:
        """PROPERTY: $ with infer_from_locale resolves per locale."""
        locale, expected = locale_currency
        event(f"dollar_locale={locale}")

        result, errors = parse_currency(
            "$100", locale, infer_from_locale=True,
        )
        assert result is not None, (
            f"$ should resolve via locale {locale}"
        )
        _, code = result
        assert code == expected
        assert errors == ()
