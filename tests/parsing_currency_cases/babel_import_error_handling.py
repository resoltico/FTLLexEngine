# mypy: ignore-errors
"""Split test cases from tests/test_parsing_currency.py."""

from tests.parsing_currency_cases import *  # noqa: F403 - shared split test support

# ---------------------------------------------------------------------------
# BabelImportError handling
# ---------------------------------------------------------------------------


class TestBabelImportError:
    """Test Babel import error handling."""

    def test_build_maps_returns_empty_when_babel_missing(
        self,
    ) -> None:
        """_build_currency_maps_from_cldr returns empty without Babel."""
        import ftllexengine.core.babel_compat as _bc

        _build_currency_maps_from_cldr.cache_clear()

        original_import = builtins.__import__

        def mock_import(
            name: str, *args: object, **kwargs: object
        ) -> object:
            if name == "babel" or name.startswith("babel."):
                msg = f"No module named '{name}'"
                raise ImportError(msg)
            return original_import(name, *args, **kwargs)  # type: ignore[arg-type]

        # Reset sentinel so is_babel_available() re-evaluates under the mock
        _bc._babel_available = None

        try:
            with patch(
                "builtins.__import__", side_effect=mock_import
            ):
                sym, amb, loc, codes = (
                    _build_currency_maps_from_cldr()
                )
                assert sym == {}
                assert amb == set()
                assert loc == {}
                assert codes == frozenset()
        finally:
            _build_currency_maps_from_cldr.cache_clear()
            # Reset sentinel so subsequent tests reinitialize with Babel available
            _bc._babel_available = None

    def test_parse_currency_raises_babel_import_error(
        self,
    ) -> None:
        """parse_currency raises BabelImportError without Babel."""
        import ftllexengine.core.babel_compat as _bc
        from ftllexengine.core.babel_compat import BabelImportError

        _bc._babel_available = None
        original_import = builtins.__import__

        def mock_import(
            name: str, *args: object, **kwargs: object
        ) -> object:
            if name == "babel" or name.startswith("babel."):
                msg = f"No module named '{name}'"
                raise ImportError(msg)
            return original_import(name, *args, **kwargs)  # type: ignore[arg-type]

        try:
            with patch(
                "builtins.__import__", side_effect=mock_import
            ):
                with pytest.raises(BabelImportError) as exc_info:
                    parse_currency("\u20ac100", "en_US")

                error_msg = str(exc_info.value)
                assert "parse_currency" in error_msg
        finally:
            _bc._babel_available = None
