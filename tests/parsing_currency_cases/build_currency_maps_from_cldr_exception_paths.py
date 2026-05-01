# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# _build_currency_maps_from_cldr exception paths
# ---------------------------------------------------------------------------


class TestBuildCurrencyMapsExceptions:
    """Test _build_currency_maps_from_cldr exception handling."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self) -> None:
        _build_currency_maps_from_cldr.cache_clear()
        _get_currency_maps.cache_clear()

    def test_locale_parse_exception_handled(self) -> None:
        """Locale.parse exceptions are caught gracefully."""
        from babel import Locale

        original_parse = Locale.parse

        def mock_parse(locale_id: str) -> Any:
            if "broken" in locale_id.lower():
                msg = "Mocked parse failure"
                raise ValueError(msg)
            return original_parse(locale_id)

        with (
            patch.object(Locale, "parse", side_effect=mock_parse),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["en_US", "broken_locale", "de_DE"],
            ),
        ):
            sym, amb, loc, _ = _build_currency_maps_from_cldr()

        assert isinstance(sym, dict)
        assert isinstance(amb, set)
        assert isinstance(loc, dict)

    def test_key_error_in_currencies_access(self) -> None:
        """KeyError when accessing locale.currencies is caught."""
        mock_locale = MagicMock()
        mock_locale.currencies.keys.side_effect = KeyError("Mock")

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["test_locale"],
            ),
        ):
            sym, _, _, codes = _build_currency_maps_from_cldr()

        assert isinstance(sym, dict)
        assert isinstance(codes, frozenset)

    def test_locale_with_currencies_none(self) -> None:
        """Locale with currencies=None is handled."""
        mock_locale = MagicMock()
        mock_locale.currencies = None

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["test_locale"],
            ),
        ):
            sym, amb, loc, _ = _build_currency_maps_from_cldr()

        assert isinstance(sym, dict)
        assert isinstance(amb, set)
        assert isinstance(loc, dict)

    def test_get_currency_symbol_exception(self) -> None:
        """get_currency_symbol exceptions are caught."""

        def mock_symbol(
            currency_code: str,
            locale: object = None,  # noqa: ARG001 - unused
        ) -> str:
            if currency_code == "FAIL":
                msg = "Mock symbol failure"
                raise ValueError(msg)
            return "$" if currency_code == "USD" else currency_code

        mock_locale = MagicMock()
        mock_locale.currencies = {"USD": "Dollar", "FAIL": "Bad"}
        mock_locale.territory = "US"

        with (
            patch(
                "babel.numbers.get_currency_symbol",
                side_effect=mock_symbol,
            ),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["en_US"],
            ),
            patch("babel.Locale.parse", return_value=mock_locale),
        ):
            sym, amb, _, _ = _build_currency_maps_from_cldr()

        assert isinstance(sym, dict)
        assert isinstance(amb, set)

    def test_attribute_error_in_symbol_lookup(self) -> None:
        """AttributeError in get_currency_symbol is caught."""

        def mock_raises(
            currency_code: str,  # noqa: ARG001 - unused
            locale: object = None,  # noqa: ARG001 - unused
        ) -> str:
            msg = "Mock attribute error"
            raise AttributeError(msg)

        mock_locale = MagicMock()
        mock_locale.currencies = {"USD": "Dollar"}
        mock_locale.territory = "US"
        mock_locale.configure_mock(
            **{"__str__.return_value": "en_US"},
        )

        with (
            patch(
                "babel.numbers.get_currency_symbol",
                side_effect=mock_raises,
            ),
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["en_US"],
            ),
        ):
            sym, _, _, codes = _build_currency_maps_from_cldr()

        assert isinstance(sym, dict)
        assert isinstance(codes, frozenset)

    def test_territory_currencies_exception(self) -> None:
        """get_territory_currencies exception is caught."""

        def mock_territory(territory: str) -> list[str]:
            if territory == "XX":
                msg = "Unknown territory"
                raise ValueError(msg)
            return ["USD"]

        mock_us = MagicMock()
        mock_us.territory = "US"
        mock_us.currencies = {}
        mock_us.configure_mock(
            **{"__str__.return_value": "en_US"},
        )

        mock_xx = MagicMock()
        mock_xx.territory = "XX"
        mock_xx.currencies = {}
        mock_xx.configure_mock(
            **{"__str__.return_value": "xx_XX"},
        )

        def mock_parse(locale_id: str) -> MagicMock:
            return mock_xx if locale_id == "xx_XX" else mock_us

        with (
            patch(
                "babel.numbers.get_territory_currencies",
                side_effect=mock_territory,
            ),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["en_US", "xx_XX"],
            ),
            patch("babel.Locale.parse", side_effect=mock_parse),
        ):
            _, _, loc, _ = _build_currency_maps_from_cldr()

        assert isinstance(loc, dict)

    def test_unknown_locale_error_in_territory_lookup(self) -> None:
        """UnknownLocaleError in get_territory_currencies is caught."""

        def mock_raises(
            territory: str,  # noqa: ARG001 - unused
        ) -> list[str]:
            msg = "Mock unknown locale"
            raise UnknownLocaleError(msg)

        mock_locale = MagicMock()
        mock_locale.territory = "XX"
        mock_locale.currencies = {}
        mock_locale.configure_mock(
            **{"__str__.return_value": "xx_XX"},
        )

        with (
            patch(
                "babel.numbers.get_territory_currencies",
                side_effect=mock_raises,
            ),
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["xx_XX"],
            ),
        ):
            _, _, _, codes = _build_currency_maps_from_cldr()

        assert isinstance(codes, frozenset)

    def test_locale_without_territory(self) -> None:
        """Locale without territory is handled."""
        mock_locale = MagicMock()
        mock_locale.territory = None
        mock_locale.currencies = {}

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["en"],
            ),
        ):
            _, _, loc, _ = _build_currency_maps_from_cldr()

        assert isinstance(loc, dict)

    def test_locale_str_without_underscore_excluded(self) -> None:
        """Locale str without underscore is not in locale_to_currency."""
        mock_locale = MagicMock()
        mock_locale.territory = "XX"
        mock_locale.currencies = {}
        mock_locale.configure_mock(
            **{"__str__.return_value": "en"},
        )

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["en"],
            ),
            patch(
                "babel.numbers.get_territory_currencies",
                return_value=["GBP"],
            ),
        ):
            _, _, loc, _ = _build_currency_maps_from_cldr()

        assert "en" not in loc

    def test_empty_territory_currencies(self) -> None:
        """get_territory_currencies returning empty list is handled."""
        mock_locale = MagicMock()
        mock_locale.territory = "US"
        mock_locale.currencies = {}
        mock_locale.configure_mock(
            **{"__str__.return_value": "en_US"},
        )

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=["en_US"],
            ),
            patch(
                "babel.numbers.get_territory_currencies",
                return_value=[],
            ),
        ):
            _, _, loc, _ = _build_currency_maps_from_cldr()

        assert isinstance(loc, dict)

    @given(locale_count=st.integers(min_value=1, max_value=5))
    @settings(max_examples=10)
    def test_handles_various_locale_counts(
        self, locale_count: int
    ) -> None:
        """PROPERTY: Function handles any number of locales."""
        event(f"locale_count={locale_count}")

        _build_currency_maps_from_cldr.cache_clear()
        mock_locales = [f"mock_{i}" for i in range(locale_count)]

        mock_locale = MagicMock()
        mock_locale.territory = None
        mock_locale.currencies = {}

        with (
            patch("babel.Locale.parse", return_value=mock_locale),
            patch(
                "babel.localedata.locale_identifiers",
                return_value=mock_locales,
            ),
        ):
            sym, amb, loc, _ = _build_currency_maps_from_cldr()

        assert isinstance(sym, dict)
        assert isinstance(amb, set)
        assert isinstance(loc, dict)
