# mypy: ignore-errors
"""Split test cases from tests/test_parsing_dates.py."""

from tests.parsing_dates_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# _get_date_patterns Exception Handling
# ============================================================================


class TestGetDatePatternsExceptions:
    """Test _get_date_patterns exception handling."""

    def test_unknown_locale_returns_empty(self) -> None:
        """Unknown locale returns empty tuple."""
        _get_date_patterns.cache_clear()
        assert _get_date_patterns("xx-UNKNOWN") == ()

    def test_invalid_format_returns_empty(self) -> None:
        """Invalid format returns empty tuple."""
        _get_date_patterns.cache_clear()
        assert _get_date_patterns("not-valid-at-all-xyz-123") == ()

    def test_valid_locale_returns_patterns(self) -> None:
        """Valid locale returns non-empty patterns."""
        _get_date_patterns.cache_clear()
        assert len(_get_date_patterns("en-US")) > 0

    def test_attribute_error_in_pattern(self) -> None:
        """AttributeError accessing pattern falls back to str(fmt)."""
        _get_date_patterns.cache_clear()

        mock_format = MagicMock()
        del mock_format.pattern

        with patch.object(Locale, "parse") as mock_parse:
            mock_locale = MagicMock()
            mock_locale.date_formats = {
                "short": mock_format, "medium": mock_format,
                "long": mock_format, "full": mock_format,
            }
            mock_parse.return_value = mock_locale
            _get_date_patterns.cache_clear()
            patterns = _get_date_patterns("mock-locale-attr-err")

        assert len(patterns) > 0

    def test_raises_babel_import_error_when_babel_missing(self) -> None:
        """Raises BabelImportError when Babel unavailable."""
        _get_date_patterns.cache_clear()
        _bc._babel_available = None

        original_import = builtins.__import__

        def mock_import(
            name: str,
            globals_: dict[str, object] | None = None,
            locals_: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            if name == "babel":
                msg = "No module named 'babel'"
                raise ImportError(msg)
            return original_import(name, globals_, locals_, fromlist, level)

        try:
            with patch.object(
                builtins, "__import__", side_effect=mock_import
            ):
                with pytest.raises(
                    ImportError, match="parse"
                ) as exc_info:
                    _get_date_patterns("en_US")
                assert exc_info.typename == "BabelImportError"
                assert "parse_date" in str(exc_info.value)
        finally:
            _bc._babel_available = None

    def test_babel_import_error_feature_name(self) -> None:
        """BabelImportError contains correct feature name."""
        _get_date_patterns.cache_clear()
        _bc._babel_available = None

        babel_modules_backup = {}
        babel_keys = [
            k for k in sys.modules
            if k == "babel" or k.startswith("babel.")
        ]
        for key in babel_keys:
            babel_modules_backup[key] = sys.modules.pop(key, None)

        try:
            original_import = builtins.__import__

            def mock_import(
                name: str,
                globals_: dict[str, object] | None = None,
                locals_: dict[str, object] | None = None,
                fromlist: tuple[str, ...] = (),
                level: int = 0,
            ) -> object:
                if name == "babel" or name.startswith("babel."):
                    msg = f"No module named '{name}'"
                    raise ImportError(msg)
                return original_import(
                    name, globals_, locals_, fromlist, level
                )

            with patch.object(
                builtins, "__import__", side_effect=mock_import
            ):
                with pytest.raises(
                    ImportError, match="parse"
                ) as exc_info:
                    _get_date_patterns("en_US")
                assert "parse_date" in str(exc_info.value)
        finally:
            for key, value in babel_modules_backup.items():
                if value is not None:
                    sys.modules[key] = value
            _get_date_patterns.cache_clear()
            _bc._babel_available = None
