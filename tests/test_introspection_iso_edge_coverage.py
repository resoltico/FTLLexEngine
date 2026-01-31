"""Edge case tests for 100% coverage of iso.py.

Tests cover exceptional error paths in Babel wrapper functions where:
- Babel raises non-standard exceptions
- UnknownLocaleError import fails during exception handling

These tests target lines 199-200 and 223-224 in iso.py.
"""

import builtins
from unittest.mock import MagicMock, patch

import pytest

from ftllexengine.introspection.iso import (
    _get_babel_currency_name,
    _get_babel_currency_symbol,
)


class TestBabelUnknownLocaleErrorImportFailure:
    """Tests for UnknownLocaleError import failure paths.

    These tests cover the edge case where:
    1. Babel raises a non-standard exception (not in the caught set)
    2. Attempting to import UnknownLocaleError fails with ImportError
    3. The original exception should be re-raised
    """

    def test_currency_name_exception_with_unknown_locale_error_import_failure(
        self,
    ) -> None:
        """_get_babel_currency_name re-raises when UnknownLocaleError import fails.

        Covers lines 199-200 in iso.py.
        """

        # Create a custom exception that's not in the standard set
        class CustomBabelError(Exception):
            """Custom exception to simulate unexpected Babel error."""

        custom_exc = CustomBabelError("Unexpected Babel error")

        # Mock get_currency_name to raise the custom exception
        mock_get_currency_name = MagicMock(side_effect=custom_exc)

        # Create a custom import function that:
        # 1. Allows babel.Locale to be imported
        # 2. Allows babel.numbers.get_currency_name to be imported
        # 3. Fails when trying to import babel.core.UnknownLocaleError
        original_import = builtins.__import__

        def mock_import(
            name: str,
            globals_arg: dict[str, object] | None = None,
            locals_arg: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            # Allow babel and babel.numbers imports
            if name in ("babel", "babel.numbers"):
                return original_import(name, globals_arg, locals_arg, fromlist, level)

            # Fail when trying to import from babel.core
            if name == "babel.core" and "UnknownLocaleError" in fromlist:
                msg = "Cannot import UnknownLocaleError"
                raise ImportError(msg)

            return original_import(name, globals_arg, locals_arg, fromlist, level)

        # Apply patches and verify exception is re-raised
        with (
            patch("babel.numbers.get_currency_name", mock_get_currency_name),
            patch("builtins.__import__", side_effect=mock_import),
            pytest.raises(CustomBabelError) as exc_info,
        ):
            _get_babel_currency_name("USD", "en")

        # Verify the original exception was re-raised
        assert exc_info.value is custom_exc
        assert str(exc_info.value) == "Unexpected Babel error"

    def test_currency_symbol_exception_with_unknown_locale_error_import_failure(
        self,
    ) -> None:
        """_get_babel_currency_symbol re-raises when UnknownLocaleError import fails.

        Covers lines 223-224 in iso.py.
        """

        # Create a custom exception that's not in the standard set
        class CustomBabelError(Exception):
            """Custom exception to simulate unexpected Babel error."""

        custom_exc = CustomBabelError("Unexpected symbol error")

        # Mock get_currency_symbol to raise the custom exception
        mock_get_currency_symbol = MagicMock(side_effect=custom_exc)

        # Create a custom import function that:
        # 1. Allows babel.numbers.get_currency_symbol to be imported
        # 2. Fails when trying to import babel.core.UnknownLocaleError
        original_import = builtins.__import__

        def mock_import(
            name: str,
            globals_arg: dict[str, object] | None = None,
            locals_arg: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            # Allow babel.numbers import
            if name == "babel.numbers":
                return original_import(name, globals_arg, locals_arg, fromlist, level)

            # Fail when trying to import from babel.core
            if name == "babel.core" and "UnknownLocaleError" in fromlist:
                msg = "Cannot import UnknownLocaleError"
                raise ImportError(msg)

            return original_import(name, globals_arg, locals_arg, fromlist, level)

        # Apply patches and verify exception is re-raised
        with (
            patch("babel.numbers.get_currency_symbol", mock_get_currency_symbol),
            patch("builtins.__import__", side_effect=mock_import),
            pytest.raises(CustomBabelError) as exc_info,
        ):
            _get_babel_currency_symbol("USD", "en")

        # Verify the original exception was re-raised
        assert exc_info.value is custom_exc
        assert str(exc_info.value) == "Unexpected symbol error"

    def test_currency_name_with_chained_exception(self) -> None:
        """Verify exception propagation when UnknownLocaleError import fails."""

        class UnexpectedError(Exception):
            """Simulates an unexpected Babel exception."""

        original_exc = UnexpectedError("Original error")

        mock_get_currency_name = MagicMock(side_effect=original_exc)
        original_import = builtins.__import__

        def mock_import(
            name: str,
            globals_arg: dict[str, object] | None = None,
            locals_arg: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            if name in ("babel", "babel.numbers"):
                return original_import(name, globals_arg, locals_arg, fromlist, level)
            if name == "babel.core" and "UnknownLocaleError" in fromlist:
                msg = "UnknownLocaleError unavailable"
                raise ImportError(msg)
            return original_import(name, globals_arg, locals_arg, fromlist, level)

        with (
            patch("babel.numbers.get_currency_name", mock_get_currency_name),
            patch("builtins.__import__", side_effect=mock_import),
            pytest.raises(UnexpectedError) as exc_info,
        ):
            _get_babel_currency_name("USD", "en")

        # Verify the original exception was re-raised
        assert exc_info.value is original_exc

    def test_currency_symbol_with_chained_exception(self) -> None:
        """Verify exception propagation when UnknownLocaleError import fails."""

        class UnexpectedError(Exception):
            """Simulates an unexpected Babel exception."""

        original_exc = UnexpectedError("Original symbol error")

        mock_get_currency_symbol = MagicMock(side_effect=original_exc)
        original_import = builtins.__import__

        def mock_import(
            name: str,
            globals_arg: dict[str, object] | None = None,
            locals_arg: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            if name == "babel.numbers":
                return original_import(name, globals_arg, locals_arg, fromlist, level)
            if name == "babel.core" and "UnknownLocaleError" in fromlist:
                msg = "UnknownLocaleError unavailable"
                raise ImportError(msg)
            return original_import(name, globals_arg, locals_arg, fromlist, level)

        with (
            patch("babel.numbers.get_currency_symbol", mock_get_currency_symbol),
            patch("builtins.__import__", side_effect=mock_import),
            pytest.raises(UnexpectedError) as exc_info,
        ):
            _get_babel_currency_symbol("USD", "en")

        # Verify the original exception was re-raised
        assert exc_info.value is original_exc
