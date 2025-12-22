"""Coverage tests for LocaleContext edge cases and error paths.

Targets uncovered lines in locale_context.py:
- Unknown locale handling in create() (fallback to en_US)
- Number formatting error paths (lines 175-176)
- Datetime formatting error paths (lines 257-258)
- Currency formatting error paths (lines 348-349)
"""

import logging
from datetime import UTC, datetime

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.locale_context import LocaleContext


class TestLocaleContextUnknownLocale:
    """Test LocaleContext with unknown/invalid locales.

    Since v0.14.0, create() always returns LocaleContext with en_US fallback.
    Use create_or_raise() when strict validation is required.
    """

    def test_unknown_locale_warns_on_create(self, caplog: pytest.LogCaptureFixture) -> None:
        """Unknown locale logs warning during create()."""
        with caplog.at_level(logging.WARNING):
            ctx = LocaleContext.create("xx_INVALID")

        # Should log warning about unknown locale
        assert any("Unknown locale" in record.message or "xx_INVALID" in record.message
                   for record in caplog.records)
        # Should still return LocaleContext
        assert isinstance(ctx, LocaleContext)

    def test_unknown_locale_fallback_to_en_us(self) -> None:
        """Unknown locale falls back to en_US for formatting."""
        ctx = LocaleContext.create("xx_NONEXISTENT")
        locale = ctx.babel_locale

        # Should fallback to en_US
        assert locale.language == "en"

    def test_completely_invalid_locale_string(self) -> None:
        """Completely malformed locale string triggers fallback in create()."""
        ctx = LocaleContext.create("!!!INVALID@@@")
        locale = ctx.babel_locale

        # Should still fallback gracefully
        assert locale.language == "en"

    @given(
        st.text(
            alphabet=st.characters(blacklist_categories=("Cs",)),  # type: ignore[arg-type]
            min_size=1,
            max_size=20,
        ).filter(lambda x: x not in ["en", "en_US", "en-US", "de", "de_DE", "lv", "lv_LV"])
    )
    @settings(max_examples=50)
    def test_arbitrary_locale_never_crashes_create(self, locale_str: str) -> None:
        """Any locale string should create context without crashing via create() (Hypothesis)."""
        # create() should never raise, might warn/debug log
        ctx = LocaleContext.create(locale_str)

        # Should be able to get babel_locale (might fallback)
        locale = ctx.babel_locale
        assert locale is not None

        # Should be able to format
        result = ctx.format_number(123.45)
        assert isinstance(result, str)


class TestNumberFormattingErrorPaths:
    """Test number formatting error paths."""

    def test_format_number_with_invalid_pattern_params(self) -> None:
        """Invalid fraction digits should trigger error path (lines 175-176)."""
        ctx = LocaleContext.create_or_raise("en_US")

        # This hits the error path but may not log depending on Babel behavior
        result = ctx.format_number(123.45, minimum_fraction_digits=-1)

        # Should return some valid string (either formatted or fallback)
        assert isinstance(result, str)

    def test_format_number_value_error_path(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ValueError in format_number hits lines 175-176."""
        from babel import numbers as babel_numbers

        ctx = LocaleContext.create_or_raise("en_US")

        original_format_decimal = babel_numbers.format_decimal

        def mock_format_decimal(*_args, **_kwargs):
            # Raise ValueError to hit the specific exception handler
            msg = "Mocked ValueError for testing"
            raise ValueError(msg)

        monkeypatch.setattr(babel_numbers, "format_decimal", mock_format_decimal)

        with caplog.at_level(logging.WARNING):
            result = ctx.format_number(123.45)

        # Should have logged warning and returned fallback
        assert isinstance(result, str)
        # Verify fallback contains the original value
        assert "123" in result

        # Restore (monkeypatch handles this)
        monkeypatch.setattr(babel_numbers, "format_decimal", original_format_decimal)


class TestDatetimeFormattingErrorPaths:
    """Test datetime formatting error paths."""

    def test_format_datetime_invalid_value_type(self) -> None:
        """Invalid datetime type should trigger error path (lines 257-258)."""
        ctx = LocaleContext.create_or_raise("en_US")

        # Pass something that can't be formatted as datetime
        result = ctx.format_datetime("not-a-datetime")

        # Should return fallback string
        assert isinstance(result, str)

    def test_format_datetime_babel_error_path(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Babel error in format_datetime hits exception handler."""
        from babel import dates as babel_dates

        ctx = LocaleContext.create_or_raise("en_US")

        def mock_format_datetime(*_args, **_kwargs):
            msg = "Mocked Babel error"
            raise ValueError(msg)

        monkeypatch.setattr(babel_dates, "format_datetime", mock_format_datetime)

        now = datetime.now(tz=UTC)
        with caplog.at_level(logging.WARNING):
            result = ctx.format_datetime(now)

        # Should return ISO format fallback
        assert isinstance(result, str)


class TestCurrencyFormattingErrorPaths:
    """Test currency formatting error paths."""

    def test_format_currency_invalid_currency_code(self) -> None:
        """Invalid currency code should trigger error path (lines 348-349)."""
        ctx = LocaleContext.create_or_raise("en_US")

        # Pass invalid currency code
        result = ctx.format_currency(100.0, currency="INVALID")

        # Should return fallback string
        assert isinstance(result, str)

    def test_format_currency_babel_error_path(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Babel error in format_currency hits exception handler."""
        from babel import numbers as babel_numbers

        ctx = LocaleContext.create_or_raise("en_US")

        def mock_format_currency(*_args, **_kwargs):
            msg = "Mocked currency error"
            raise ValueError(msg)

        monkeypatch.setattr(babel_numbers, "format_currency", mock_format_currency)

        with caplog.at_level(logging.WARNING):
            result = ctx.format_currency(100.0, currency="USD")

        # Should return fallback string
        assert isinstance(result, str)
        assert "100" in result or "USD" in result


class TestLocaleContextValidLocales:
    """Test LocaleContext with valid locales."""

    def test_common_locales_work(self) -> None:
        """Common locales should work without issues."""
        locales = ["en-US", "en_US", "de-DE", "fr-FR", "lv-LV", "es-ES", "zh-CN"]

        for locale_code in locales:
            ctx = LocaleContext.create_or_raise(locale_code)
            assert ctx.locale_code == locale_code

            # Should be able to format
            num = ctx.format_number(1234.56)
            assert isinstance(num, str)

    def test_create_and_create_or_raise_same_for_valid(self) -> None:
        """create() and create_or_raise() give same result for valid locales."""
        locale = "en-US"

        ctx1 = LocaleContext.create(locale)
        ctx2 = LocaleContext.create_or_raise(locale)

        assert ctx1.locale_code == ctx2.locale_code
        assert ctx1.babel_locale.language == ctx2.babel_locale.language
