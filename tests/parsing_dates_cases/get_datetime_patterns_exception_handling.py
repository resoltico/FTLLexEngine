# mypy: ignore-errors
"""Split test cases from tests/test_parsing_dates.py."""

from tests.parsing_dates_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# _get_datetime_patterns Exception Handling
# ============================================================================


class TestGetDatetimePatternsExceptions:
    """Test _get_datetime_patterns exception handling."""

    def test_unknown_locale_returns_empty(self) -> None:
        """Unknown locale returns empty tuple."""
        _get_datetime_patterns.cache_clear()
        assert _get_datetime_patterns("xx-UNKNOWN") == ()

    def test_invalid_format_returns_empty(self) -> None:
        """Invalid format returns empty tuple."""
        _get_datetime_patterns.cache_clear()
        assert _get_datetime_patterns("invalid-locale-format-xyz") == ()

    def test_valid_locale_returns_patterns(self) -> None:
        """Valid locale returns non-empty patterns."""
        _get_datetime_patterns.cache_clear()
        assert len(_get_datetime_patterns("en-US")) > 0

    def test_cldr_pattern_success_path(self) -> None:
        """Successful CLDR datetime pattern extraction via mock."""
        _get_datetime_patterns.cache_clear()
        _get_date_patterns.cache_clear()

        class MockDateTimeFormat:
            def __init__(self, pattern_str: str) -> None:
                self._pattern = pattern_str

            @property
            def pattern(self) -> str:
                return self._pattern

        mock_short = MockDateTimeFormat("M/d/yy, h:mm a")
        mock_medium = MockDateTimeFormat("MMM d, yyyy, h:mm:ss a")
        mock_long = MockDateTimeFormat("MMMM d, yyyy 'at' h:mm:ss a")

        with patch.object(Locale, "parse") as mock_parse:
            mock_locale = MagicMock()
            mock_datetime_formats = MagicMock()
            mock_datetime_formats.__getitem__ = MagicMock(
                side_effect=lambda k: {
                    "short": mock_short,
                    "medium": mock_medium,
                    "long": mock_long,
                }.get(k, mock_short)
            )
            mock_datetime_formats.get = MagicMock(
                return_value="{1}, {0}"
            )
            mock_locale.datetime_formats = mock_datetime_formats

            mock_date_format = MockDateTimeFormat("M/d/yy")
            mock_date_formats = MagicMock()
            mock_date_formats.__getitem__ = MagicMock(
                return_value=mock_date_format
            )
            mock_locale.date_formats = mock_date_formats
            mock_parse.return_value = mock_locale

            _get_datetime_patterns.cache_clear()
            _get_date_patterns.cache_clear()
            patterns = _get_datetime_patterns("mock-cldr-success-v1")

        assert len(patterns) > 0
        pattern_str = " ".join(p[0] for p in patterns)
        assert "%" in pattern_str

    def test_attribute_error_in_pattern(self) -> None:
        """AttributeError accessing datetime pattern handled gracefully."""
        _get_datetime_patterns.cache_clear()
        _get_date_patterns.cache_clear()

        class RaisingFormat:
            @property
            def pattern(self) -> str:
                msg = "no pattern attribute"
                raise AttributeError(msg)

        mock_format = RaisingFormat()

        with patch.object(Locale, "parse") as mock_parse:
            mock_locale = MagicMock()
            mock_datetime_formats = MagicMock()
            mock_datetime_formats.__getitem__ = MagicMock(
                return_value=mock_format
            )
            mock_datetime_formats.get = MagicMock(return_value=None)
            mock_locale.datetime_formats = mock_datetime_formats
            mock_date_formats = MagicMock()
            mock_date_formats.__getitem__ = MagicMock(
                return_value=mock_format
            )
            mock_locale.date_formats = mock_date_formats
            mock_parse.return_value = mock_locale

            _get_datetime_patterns.cache_clear()
            _get_date_patterns.cache_clear()
            patterns = _get_datetime_patterns(
                "mock-locale-datetime-attr-err-v3"
            )

        assert len(patterns) > 0

    def test_key_error_via_missing_key(self) -> None:
        """KeyError accessing datetime style handled gracefully."""
        _get_datetime_patterns.cache_clear()
        _get_date_patterns.cache_clear()

        with patch.object(Locale, "parse") as mock_parse:
            mock_locale = MagicMock()
            mock_datetime_formats = MagicMock()
            mock_datetime_formats.__getitem__ = MagicMock(
                side_effect=KeyError("No format")
            )
            mock_datetime_formats.get = MagicMock(return_value=None)
            mock_locale.datetime_formats = mock_datetime_formats
            mock_date_formats = MagicMock()
            mock_date_formats.__getitem__ = MagicMock(
                side_effect=KeyError("No format")
            )
            mock_locale.date_formats = mock_date_formats
            mock_parse.return_value = mock_locale

            _get_datetime_patterns.cache_clear()
            _get_date_patterns.cache_clear()
            patterns = _get_datetime_patterns(
                "mock-locale-keyerror-v2"
            )

        assert patterns == ()

    def test_raises_babel_import_error_when_babel_missing(self) -> None:
        """Raises BabelImportError when Babel unavailable."""
        _get_datetime_patterns.cache_clear()
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
                    _get_datetime_patterns("en_US")
                assert exc_info.typename == "BabelImportError"
                assert "parse_datetime" in str(exc_info.value)
        finally:
            _bc._babel_available = None

    def test_babel_import_error_feature_name(self) -> None:
        """BabelImportError contains correct feature name."""
        _get_datetime_patterns.cache_clear()
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
                    _get_datetime_patterns("en_US")
                assert "parse_datetime" in str(exc_info.value)
        finally:
            for key, value in babel_modules_backup.items():
                if value is not None:
                    sys.modules[key] = value
            _get_datetime_patterns.cache_clear()
            _get_date_patterns.cache_clear()
            _bc._babel_available = None
