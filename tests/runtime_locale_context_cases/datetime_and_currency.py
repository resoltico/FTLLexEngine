# mypy: ignore-errors
from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from babel import dates as babel_dates
from babel import numbers as babel_numbers

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.locale_context import LocaleContext

# ============================================================================
# Construction Guard Tests
# ============================================================================



class TestFormatDatetime:
    """Test format_datetime() with various locales and parameters."""

    def test_format_datetime_en_us_short(self) -> None:
        """format_datetime() with short style for en-US."""
        ctx = LocaleContext.create("en-US")
        dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)
        result = ctx.format_datetime(dt, date_style="short")
        assert "10" in result or "27" in result

    def test_format_datetime_de_de_short(self) -> None:
        """format_datetime() with short style for de-DE."""
        ctx = LocaleContext.create("de-DE")
        dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)
        result = ctx.format_datetime(dt, date_style="short")
        assert "27" in result or "10" in result

    def test_format_datetime_custom_pattern(self) -> None:
        """format_datetime() respects custom pattern."""
        ctx = LocaleContext.create("en-US")
        dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)
        result = ctx.format_datetime(dt, pattern="yyyy-MM-dd")
        assert "2025" in result
        assert "10" in result
        assert "27" in result

    def test_format_datetime_from_iso_string(self) -> None:
        """format_datetime() accepts ISO 8601 string."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_datetime(
            "2025-10-27", date_style="short"
        )
        assert "10" in result or "27" in result

    def test_format_datetime_invalid_string_raises(
        self,
    ) -> None:
        """format_datetime() raises for invalid datetime string."""
        ctx = LocaleContext.create("en-US")
        with pytest.raises(FrozenFluentError) as exc_info:
            ctx.format_datetime(
                "not-a-date", date_style="short"
            )
        assert (
            exc_info.value.category == ErrorCategory.FORMATTING
        )
        assert "not ISO 8601 format" in str(exc_info.value)

    def test_format_datetime_with_time_style(self) -> None:
        """format_datetime() formats date and time together."""
        ctx = LocaleContext.create("en-US")
        dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)
        result = ctx.format_datetime(
            dt, date_style="short", time_style="short"
        )
        assert "10" in result or "27" in result
        has_time = (
            "14" in result
            or "2" in result
            or "30" in result
        )
        assert has_time

    def test_format_datetime_string_pattern(self) -> None:
        """format_datetime() handles string datetime_pattern."""
        ctx = LocaleContext.create("en-US")
        dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)

        with patch.object(
            ctx.babel_locale.datetime_formats, "get"
        ) as mock_get:
            mock_get.return_value = "{1} at {0}"
            result = ctx.format_datetime(
                dt, date_style="medium", time_style="short"
            )
            assert "at" in result

    def test_format_datetime_object_without_format_method(
        self,
    ) -> None:
        """format_datetime() when pattern lacks format()."""
        ctx = LocaleContext.create("en-US")
        dt = datetime(2025, 7, 15, 10, 30, 0, tzinfo=UTC)

        class PatternWithoutFormat:
            """Mock pattern without format() method."""

            def __str__(self) -> str:
                return "{1} @ {0}"

        mock_pattern = PatternWithoutFormat()
        assert not hasattr(mock_pattern, "format")

        with patch.object(
            ctx.babel_locale.datetime_formats,
            "get",
            return_value=mock_pattern,
        ):
            result = ctx.format_datetime(
                dt, date_style="medium", time_style="short"
            )
            assert " @ " in result

    def test_format_datetime_error_raises_formatting_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """format_datetime() raises FrozenFluentError on error."""
        def mock_format_date(
            *_args: object, **_kwargs: object
        ) -> None:
            msg = "Mocked format error"
            raise ValueError(msg)

        monkeypatch.setattr(
            babel_dates, "format_date", mock_format_date
        )

        ctx = LocaleContext.create("en-US")
        dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)

        with pytest.raises(FrozenFluentError) as exc_info:
            ctx.format_datetime(dt, date_style="short")
        assert (
            exc_info.value.category == ErrorCategory.FORMATTING
        )

class TestFormatCurrency:
    """Test format_currency() with various locales and parameters."""

    def test_format_currency_en_us_symbol(self) -> None:
        """format_currency() with symbol for en-US."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_currency(
            Decimal("123.45"), currency="EUR"
        )
        assert "123" in result

    def test_format_currency_lv_lv_symbol(self) -> None:
        """format_currency() with symbol for lv-LV."""
        ctx = LocaleContext.create("lv-LV")
        result = ctx.format_currency(
            Decimal("123.45"), currency="EUR"
        )
        assert "123" in result

    def test_format_currency_code_display(self) -> None:
        """format_currency() displays currency code."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_currency(
            Decimal("123.45"),
            currency="USD",
            currency_display="code",
        )
        assert "USD" in result
        assert "123.45" in result

    def test_format_currency_name_display(self) -> None:
        """format_currency() displays currency name."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_currency(
            Decimal("123.45"),
            currency="USD",
            currency_display="name",
        )
        assert isinstance(result, str)

    def test_format_currency_symbol_display_standard(
        self,
    ) -> None:
        """format_currency() with explicit symbol display."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_currency(
            Decimal("123.45"),
            currency="EUR",
            currency_display="symbol",
        )
        assert "123.45" in result

    def test_format_currency_custom_pattern(self) -> None:
        """format_currency() respects custom pattern."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_currency(
            Decimal("1234.56"),
            currency="USD",
            pattern="#,##0.00 \xa4",
        )
        assert "1,234.56" in result or "1234.56" in result

    def test_format_currency_error_raises_formatting_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """format_currency() raises FrozenFluentError on error."""
        def mock_format_currency(
            *_args: object, **_kwargs: object
        ) -> None:
            msg = "Mocked format error"
            raise ValueError(msg)

        monkeypatch.setattr(
            babel_numbers,
            "format_currency",
            mock_format_currency,
        )

        ctx = LocaleContext.create("en-US")
        with pytest.raises(FrozenFluentError) as exc_info:
            ctx.format_currency(Decimal("123.45"), currency="USD")

        assert (
            exc_info.value.category == ErrorCategory.FORMATTING
        )
        assert "USD 123.45" in exc_info.value.fallback_value

class TestGetIsoCodePattern:
    """Test _get_iso_code_pattern() internal helper."""

    def test_returns_string_or_none(self) -> None:
        """_get_iso_code_pattern() returns string or None."""
        ctx = LocaleContext.create("en-US")
        result = ctx._get_iso_code_pattern()
        assert result is None or isinstance(result, str)

    def test_doubles_currency_sign(self) -> None:
        """Doubles currency sign per CLDR spec."""
        ctx = LocaleContext.create("en-US")
        result = ctx._get_iso_code_pattern()
        if result is not None:
            assert "\xa4\xa4" in result

    def test_none_when_no_standard(self) -> None:
        """Returns None when standard pattern missing."""
        ctx = LocaleContext.create("en-US")

        mock_formats: dict[str, None] = {"standard": None}
        mock_locale = MagicMock()
        type(mock_locale).currency_formats = PropertyMock(
            return_value=mock_formats
        )

        original_locale = ctx._babel_locale
        object.__setattr__(ctx, "_babel_locale", mock_locale)

        try:
            result = ctx._get_iso_code_pattern()
            assert result is None
        finally:
            object.__setattr__(
                ctx, "_babel_locale", original_locale
            )

    def test_none_when_no_pattern_attribute(self) -> None:
        """Returns None when pattern attribute missing."""
        ctx = LocaleContext.create("en-US")

        mock_pattern = MagicMock(spec=[])
        mock_formats = {"standard": mock_pattern}
        mock_locale = MagicMock()
        type(mock_locale).currency_formats = PropertyMock(
            return_value=mock_formats
        )

        original_locale = ctx._babel_locale
        object.__setattr__(ctx, "_babel_locale", mock_locale)

        try:
            result = ctx._get_iso_code_pattern()
            assert result is None
        finally:
            object.__setattr__(
                ctx, "_babel_locale", original_locale
            )

    def test_none_when_no_currency_placeholder(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Returns None and logs when no placeholder."""
        ctx = LocaleContext.create("en-US")

        mock_pattern = MagicMock()
        mock_pattern.pattern = "#,##0.00"
        mock_formats = {"standard": mock_pattern}
        mock_locale = MagicMock()
        type(mock_locale).currency_formats = PropertyMock(
            return_value=mock_formats
        )

        original_locale = ctx._babel_locale
        object.__setattr__(ctx, "_babel_locale", mock_locale)

        try:
            with caplog.at_level(logging.DEBUG):
                result = ctx._get_iso_code_pattern()

            assert result is None
            assert any(
                "lacks placeholder" in r.message
                for r in caplog.records
            )
        finally:
            object.__setattr__(
                ctx, "_babel_locale", original_locale
            )

class TestCurrencyPatternFallback:
    """Test currency code display fallback paths."""

    def test_code_display_with_invalid_pattern(self) -> None:
        """Code display when pattern lacks placeholder."""
        ctx = LocaleContext.create("en-US")

        class MockPattern:
            """Mock pattern without currency placeholder."""

            pattern = "#,##0.00"

        with (
            patch.object(
                ctx.babel_locale.currency_formats,
                "get",
                return_value=MockPattern(),
            ),
            patch(
                "ftllexengine.runtime.locale_context.logger"
            ) as mock_logger,
        ):
            result = ctx.format_currency(
                Decimal("123.45"),
                currency="USD",
                currency_display="code",
            )

            assert isinstance(result, str)
            assert "123" in result
            mock_logger.debug.assert_called()

    def test_code_display_with_no_pattern_attribute(
        self,
    ) -> None:
        """Code display when pattern lacks attribute."""
        ctx = LocaleContext.create("en-US")

        class MockPatternWithoutAttr:
            """Mock pattern without pattern attribute."""

        mock_obj = MockPatternWithoutAttr()
        assert not hasattr(mock_obj, "pattern")

        with patch.object(
            ctx.babel_locale.currency_formats,
            "get",
            return_value=mock_obj,
        ):
            result = ctx.format_currency(
                Decimal("123.45"),
                currency="USD",
                currency_display="code",
            )
            assert isinstance(result, str)
            assert "123" in result

    def test_code_display_with_none_pattern(self) -> None:
        """Code display when standard pattern is None."""
        ctx = LocaleContext.create("en-US")

        with patch.object(
            ctx.babel_locale.currency_formats,
            "get",
            return_value=None,
        ):
            result = ctx.format_currency(
                Decimal("123.45"),
                currency="USD",
                currency_display="code",
            )
            assert isinstance(result, str)
            assert "123" in result
