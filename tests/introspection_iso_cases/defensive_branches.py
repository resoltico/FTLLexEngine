# mypy: ignore-errors
# ruff: noqa: ARG001
# mypy: ignore-errors
from __future__ import annotations

import builtins
from unittest.mock import MagicMock, patch

import pytest

from ftllexengine.introspection import (
    BabelImportError,
)

# Private member access permitted for integration tests
from ftllexengine.introspection.iso import (
    _get_babel_currency_name,
    _get_babel_currency_symbol,
    _get_babel_territories,
)
from ftllexengine.introspection.iso_babel import _is_unknown_locale_error


class _UnexpectedTestError(Exception):
    """Custom exception for testing defensive error handling.

    Defined at module level to avoid scoping issues with pytest.raises.
    Used to verify that non-UnknownLocaleError exceptions propagate correctly.
    """

    def __str__(self) -> str:
        return "Something went wrong - internal processing error"

class _LocaleWordTestError(Exception):
    """Exception whose message contains 'locale' but is NOT UnknownLocaleError.

    Tests type-based exception matching: this must propagate even though the
    message contains the word 'locale'. The old substring-based matching would
    have incorrectly suppressed this.
    """

    def __str__(self) -> str:
        return "Failed to process locale configuration data"

class TestDefensiveExceptionPropagation:
    """Tests for defensive exception re-raising in Babel wrappers.

    iso.py catches babel.core.UnknownLocaleError by type (isinstance check)
    and re-raises all other exceptions. These tests verify that logic bugs
    and unexpected exceptions propagate, including those whose messages
    contain 'locale' or 'unknown' but are not UnknownLocaleError.
    """

    def test_currency_name_reraises_unexpected_exception(self) -> None:
        """_get_babel_currency_name re-raises non-locale exceptions.

        Tests line 196: raise statement in defensive exception handler.
        """
        # This test verifies that unexpected exceptions (not matching the
        # "locale" or "unknown" pattern) are propagated rather than suppressed.

        call_count = [0]  # Use list to allow modification in nested function
        error_msg = "Internal error"

        def mock_locale_parse(locale_str: str) -> object:
            """Mock Locale.parse to raise unexpected exception."""
            call_count[0] += 1
            raise _UnexpectedTestError(error_msg)

        # Patch Babel's Locale.parse to inject our test exception
        with patch("babel.Locale.parse", side_effect=mock_locale_parse):
            #  The exception should propagate (not be suppressed)
            exception_raised = False
            result = None
            try:
                result = _get_babel_currency_name("USD", "en")
            except _UnexpectedTestError:
                exception_raised = True
            except Exception as e:
                pytest.fail(f"Unexpected exception type: {type(e).__name__}: {e}")

            if not exception_raised:
                pytest.fail(
                    f"Expected _UnexpectedTestError to be raised. "
                    f"Mock called {call_count[0]} times. Result: {result}"
                )

    def test_currency_symbol_reraises_unexpected_exception(self) -> None:
        """_get_babel_currency_symbol re-raises non-locale exceptions.

        Tests line 217: raise statement in defensive exception handler.
        """
        error_msg = "Internal error"

        def mock_get_currency_symbol(code: str, locale: str | object = None) -> str:
            """Mock that raises unexpected exception."""
            raise _UnexpectedTestError(error_msg)

        # Patch get_currency_symbol to trigger the exception path
        with patch("babel.numbers.get_currency_symbol", side_effect=mock_get_currency_symbol):
            # The exception should propagate (not be suppressed)
            exception_raised = False
            try:
                _get_babel_currency_symbol("USD", "en")
            except _UnexpectedTestError:
                exception_raised = True

            assert exception_raised, "Expected _UnexpectedTestError to be raised"

    def test_territories_reraises_non_unknown_locale_error_with_locale_word(
        self,
    ) -> None:
        """Non-UnknownLocaleError with 'locale' in message propagates.

        Verifies type-based matching: exceptions whose message contains
        'locale' propagate if not babel.core.UnknownLocaleError.
        """
        from ftllexengine.introspection.iso import (
            _get_babel_territories,
        )

        def mock_locale_parse(locale_str: str) -> object:
            raise _LocaleWordTestError

        with (
            patch("babel.Locale.parse", side_effect=mock_locale_parse),
            pytest.raises(_LocaleWordTestError),
        ):
            _get_babel_territories("en")

    def test_currency_name_reraises_non_unknown_locale_error_with_locale_word(
        self,
    ) -> None:
        """Non-UnknownLocaleError with 'locale' in message propagates.

        Verifies type-based matching replaces fragile substring matching.
        """
        def mock_locale_parse(locale_str: str) -> object:
            raise _LocaleWordTestError

        with (
            patch("babel.Locale.parse", side_effect=mock_locale_parse),
            pytest.raises(_LocaleWordTestError),
        ):
            _get_babel_currency_name("USD", "en")

    def test_currency_symbol_reraises_non_unknown_locale_error_with_locale_word(
        self,
    ) -> None:
        """Non-UnknownLocaleError with 'locale' in message propagates.

        Verifies type-based matching replaces fragile substring matching.
        """
        def mock_symbol(
            code: str,
            locale: str | object = None,
        ) -> str:
            raise _LocaleWordTestError

        with (
            patch(
                "babel.numbers.get_currency_symbol",
                side_effect=mock_symbol,
            ),
            pytest.raises(_LocaleWordTestError),
        ):
            _get_babel_currency_symbol("USD", "en")

class TestUnknownLocaleErrorImportFailure:
    """Tests for UnknownLocaleError import failure paths.

    These tests cover the edge case where:
    1. Babel raises a non-standard exception (not in the caught set)
    2. Attempting to import UnknownLocaleError fails with ImportError
    3. The original exception should be re-raised
    """

    def test_currency_name_reraises_when_import_fails(self) -> None:
        """_get_babel_currency_name re-raises when UnknownLocaleError import fails."""

        class CustomBabelError(Exception):
            """Custom exception to simulate unexpected Babel error."""

        custom_exc = CustomBabelError("Unexpected Babel error")
        mock_get_currency_name = MagicMock(side_effect=custom_exc)
        original_import = builtins.__import__

        def mock_import(
            name: str,
            globals_arg: dict[str, object] | None = None,
            locals_arg: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            if name in ("babel", "babel.numbers"):
                return original_import(
                    name, globals_arg, locals_arg, fromlist, level
                )
            if name == "babel.core" and "UnknownLocaleError" in fromlist:
                msg = "Cannot import UnknownLocaleError"
                raise ImportError(msg)
            return original_import(
                name, globals_arg, locals_arg, fromlist, level
            )

        with (
            patch(
                "babel.numbers.get_currency_name",
                mock_get_currency_name,
            ),
            patch("builtins.__import__", side_effect=mock_import),
            pytest.raises(CustomBabelError) as exc_info,
        ):
            _get_babel_currency_name("USD", "en")

        assert exc_info.value is custom_exc

    def test_currency_symbol_reraises_when_import_fails(self) -> None:
        """_get_babel_currency_symbol re-raises when UnknownLocaleError import fails."""

        class CustomBabelError(Exception):
            """Custom exception to simulate unexpected Babel error."""

        custom_exc = CustomBabelError("Unexpected symbol error")
        mock_get_currency_symbol = MagicMock(side_effect=custom_exc)
        original_import = builtins.__import__

        def mock_import(
            name: str,
            globals_arg: dict[str, object] | None = None,
            locals_arg: dict[str, object] | None = None,
            fromlist: tuple[str, ...] = (),
            level: int = 0,
        ) -> object:
            if name == "babel.numbers":
                return original_import(
                    name, globals_arg, locals_arg, fromlist, level
                )
            if name == "babel.core" and "UnknownLocaleError" in fromlist:
                msg = "Cannot import UnknownLocaleError"
                raise ImportError(msg)
            return original_import(
                name, globals_arg, locals_arg, fromlist, level
            )

        with (
            patch(
                "babel.numbers.get_currency_symbol",
                mock_get_currency_symbol,
            ),
            patch("builtins.__import__", side_effect=mock_import),
            pytest.raises(CustomBabelError) as exc_info,
        ):
            _get_babel_currency_symbol("USD", "en")

        assert exc_info.value is custom_exc

    def test_currency_name_chained_exception_propagation(self) -> None:
        """Exception propagation when UnknownLocaleError import fails."""

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
                return original_import(
                    name, globals_arg, locals_arg, fromlist, level
                )
            if name == "babel.core" and "UnknownLocaleError" in fromlist:
                msg = "UnknownLocaleError unavailable"
                raise ImportError(msg)
            return original_import(
                name, globals_arg, locals_arg, fromlist, level
            )

        with (
            patch(
                "babel.numbers.get_currency_name",
                mock_get_currency_name,
            ),
            patch("builtins.__import__", side_effect=mock_import),
            pytest.raises(UnexpectedError) as exc_info,
        ):
            _get_babel_currency_name("USD", "en")

        assert exc_info.value is original_exc

    def test_currency_symbol_chained_exception_propagation(self) -> None:
        """Exception propagation when UnknownLocaleError import fails."""

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
                return original_import(
                    name, globals_arg, locals_arg, fromlist, level
                )
            if name == "babel.core" and "UnknownLocaleError" in fromlist:
                msg = "UnknownLocaleError unavailable"
                raise ImportError(msg)
            return original_import(
                name, globals_arg, locals_arg, fromlist, level
            )

        with (
            patch(
                "babel.numbers.get_currency_symbol",
                mock_get_currency_symbol,
            ),
            patch("builtins.__import__", side_effect=mock_import),
            pytest.raises(UnexpectedError) as exc_info,
        ):
            _get_babel_currency_symbol("USD", "en")

        assert exc_info.value is original_exc

class TestIsoBabelDefensiveBranches:
    """Direct coverage for defensive helper branches in iso_babel.py."""

    def test_is_unknown_locale_error_returns_false_when_babel_is_unavailable(self) -> None:
        """BabelImportError while resolving the error class yields False."""
        with patch(
            "ftllexengine.introspection.iso_babel.get_unknown_locale_error_class",
            side_effect=BabelImportError("UnknownLocaleError"),
        ):
            assert _is_unknown_locale_error(ValueError("not a locale error")) is False

    def test_is_unknown_locale_error_returns_true_for_matching_exception(self) -> None:
        """The helper returns True when the exception matches Babel's error class."""

        class FakeUnknownLocaleError(Exception):
            """Stand-in for babel.core.UnknownLocaleError."""

        with patch(
            "ftllexengine.introspection.iso_babel.get_unknown_locale_error_class",
            return_value=FakeUnknownLocaleError,
        ):
            assert _is_unknown_locale_error(FakeUnknownLocaleError("bad locale")) is True

    def test_get_babel_territories_without_unknown_locale_class_success(self) -> None:
        """The no-UnknownLocaleError branch still returns territory data when lookup succeeds."""

        class FakeLocale:
            def __init__(self) -> None:
                self.territories = {"US": "United States"}

        with (
            patch(
                "ftllexengine.introspection.iso_babel._maybe_unknown_locale_error_class",
                return_value=None,
            ),
            patch(
                "ftllexengine.introspection.iso_babel._get_babel_locale",
                return_value=FakeLocale(),
            ),
        ):
            assert _get_babel_territories("en") == {"US": "United States"}

    def test_get_babel_territories_without_unknown_locale_class_failure(self) -> None:
        """The no-UnknownLocaleError branch returns an empty mapping on locale lookup errors."""
        with (
            patch(
                "ftllexengine.introspection.iso_babel._maybe_unknown_locale_error_class",
                return_value=None,
            ),
            patch(
                "ftllexengine.introspection.iso_babel._get_babel_locale",
                side_effect=ValueError("bad locale"),
            ),
        ):
            assert _get_babel_territories("en") == {}

    def test_get_babel_currency_name_without_unknown_locale_class_success(self) -> None:
        """The no-UnknownLocaleError branch returns the localized currency name."""

        class FakeLocale:
            def __init__(self) -> None:
                self.currencies = {"USD": "US Dollar"}

        class FakeLocaleClass:
            @staticmethod
            def parse(_locale_str: str) -> FakeLocale:
                return FakeLocale()

        class FakeNumbers:
            @staticmethod
            def get_currency_name(_code: str, *, locale: str) -> str:
                assert locale == "en"
                return "US Dollar"

        with (
            patch(
                "ftllexengine.introspection.iso_babel._maybe_unknown_locale_error_class",
                return_value=None,
            ),
            patch(
                "ftllexengine.introspection.iso_babel.get_locale_class",
                return_value=FakeLocaleClass,
            ),
            patch(
                "ftllexengine.introspection.iso_babel.get_babel_numbers",
                return_value=FakeNumbers,
            ),
        ):
            assert _get_babel_currency_name("USD", "en") == "US Dollar"

    def test_get_babel_currency_name_without_unknown_locale_class_failure(self) -> None:
        """The no-UnknownLocaleError branch returns None on locale parse errors."""

        class FakeLocaleClass:
            @staticmethod
            def parse(_locale_str: str) -> object:
                msg = "bad locale"
                raise ValueError(msg)

        with (
            patch(
                "ftllexengine.introspection.iso_babel._maybe_unknown_locale_error_class",
                return_value=None,
            ),
            patch(
                "ftllexengine.introspection.iso_babel.get_locale_class",
                return_value=FakeLocaleClass,
            ),
            patch(
                "ftllexengine.introspection.iso_babel.get_babel_numbers",
                return_value=MagicMock(),
            ),
        ):
            assert _get_babel_currency_name("USD", "en") is None

    def test_get_babel_currency_name_without_unknown_locale_class_missing_code(self) -> None:
        """The no-UnknownLocaleError branch returns None for absent currency codes."""

        class FakeLocale:
            def __init__(self) -> None:
                self.currencies = {"EUR": "Euro"}

        class FakeLocaleClass:
            @staticmethod
            def parse(_locale_str: str) -> FakeLocale:
                return FakeLocale()

        with (
            patch(
                "ftllexengine.introspection.iso_babel._maybe_unknown_locale_error_class",
                return_value=None,
            ),
            patch(
                "ftllexengine.introspection.iso_babel.get_locale_class",
                return_value=FakeLocaleClass,
            ),
            patch(
                "ftllexengine.introspection.iso_babel.get_babel_numbers",
                return_value=MagicMock(),
            ),
        ):
            assert _get_babel_currency_name("USD", "en") is None

    def test_get_babel_currency_symbol_without_unknown_locale_class_success(self) -> None:
        """The no-UnknownLocaleError branch returns the localized symbol when lookup succeeds."""

        class FakeNumbers:
            @staticmethod
            def get_currency_symbol(_code: str, *, locale: str) -> str:
                assert locale == "en"
                return "$"

        with (
            patch(
                "ftllexengine.introspection.iso_babel._maybe_unknown_locale_error_class",
                return_value=None,
            ),
            patch(
                "ftllexengine.introspection.iso_babel.get_babel_numbers",
                return_value=FakeNumbers,
            ),
        ):
            assert _get_babel_currency_symbol("USD", "en") == "$"

    def test_get_babel_currency_symbol_without_unknown_locale_class_failure(self) -> None:
        """The no-UnknownLocaleError branch falls back to the code on lookup errors."""

        class FakeNumbers:
            @staticmethod
            def get_currency_symbol(_code: str, *, locale: str) -> str:
                _ = locale
                msg = "bad locale"
                raise ValueError(msg)

        with (
            patch(
                "ftllexengine.introspection.iso_babel._maybe_unknown_locale_error_class",
                return_value=None,
            ),
            patch(
                "ftllexengine.introspection.iso_babel.get_babel_numbers",
                return_value=FakeNumbers,
            ),
        ):
            assert _get_babel_currency_symbol("USD", "en") == "USD"
