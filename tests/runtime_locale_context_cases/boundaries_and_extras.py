# mypy: ignore-errors
# mypy: ignore-errors
from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, get_args
from unittest.mock import MagicMock

import pytest
from babel import numbers as babel_numbers

from ftllexengine.constants import MAX_LOCALE_CACHE_SIZE
from ftllexengine.core.locale_utils import normalize_locale
from ftllexengine.runtime.locale_context import LocaleContext

# ============================================================================
# Construction Guard Tests
# ============================================================================



class TestLongLocaleCodeCoverage:
    """Tests for long locale codes exceeding BCP 47 length."""

    def test_long_valid_locale_code_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Long valid locale code triggers warning."""
        from ftllexengine.constants import (
            MAX_LOCALE_CODE_LENGTH,
        )

        LocaleContext.clear_cache()

        long_locale = "en-US-x-" + "a" * 30
        assert len(long_locale) > MAX_LOCALE_CODE_LENGTH

        with caplog.at_level(logging.WARNING):
            ctx = LocaleContext.create(long_locale)

        assert any(
            "exceeds typical BCP 47 length" in r.message
            for r in caplog.records
        )
        assert isinstance(ctx, LocaleContext)

    def test_long_unknown_locale_code_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Long unknown locale code triggers specific warning."""
        from ftllexengine.constants import (
            MAX_LOCALE_CODE_LENGTH,
        )

        LocaleContext.clear_cache()

        long_unknown = (
            "xyz-verylongvariantthatshouldexceedlimit"
        )
        assert len(long_unknown) > MAX_LOCALE_CODE_LENGTH

        with caplog.at_level(logging.WARNING):
            ctx = LocaleContext.create(long_unknown)

        relevant = [
            r.message
            for r in caplog.records
            if "Unknown locale" in r.message
        ]
        assert any("exceeds" in msg for msg in relevant)
        assert ctx.is_fallback is True

    def test_long_invalid_format_locale_code_rejected(self) -> None:
        """Long structurally invalid locale code is rejected before runtime fallback."""
        from ftllexengine.constants import (
            MAX_LOCALE_CODE_LENGTH,
        )

        LocaleContext.clear_cache()

        long_invalid = (
            "!!!INVALID@@@FORMAT###TOOLONG###LOCALE"
        )
        assert len(long_invalid) > MAX_LOCALE_CODE_LENGTH

        with pytest.raises(ValueError, match=r"Invalid locale_code:"):
            LocaleContext.create(long_invalid)

class TestCurrencyBoundaryValues:
    """Regression tests for currency formatting boundaries."""

    @pytest.mark.parametrize("value", [
        Decimal(999),
        Decimal("999.99"),
        Decimal(1000),
        Decimal("1000.00"),
        Decimal("1000.01"),
        Decimal(1001),
    ])
    def test_currency_around_1000_boundary(
        self, value: Decimal
    ) -> None:
        """Currency formatting works around 1000 boundary."""
        ctx = LocaleContext.create("en_US")
        result = ctx.format_currency(value, currency="USD")
        assert isinstance(result, str)
        assert result
        assert "$" in result or "USD" in result

    @pytest.mark.parametrize("locale", [
        "en_US", "de_DE", "fr_FR", "es_ES", "ja_JP",
        "zh_CN", "ar_SA", "ru_RU", "pt_BR", "ko_KR",
        "it_IT", "nl_NL",
    ])
    def test_currency_1000_across_locales(
        self, locale: str
    ) -> None:
        """Currency formatting for 1000 across locales."""
        ctx = LocaleContext.create(locale)
        result = ctx.format_currency(
            Decimal(1000), currency="USD"
        )
        assert isinstance(result, str)
        assert result
        assert any(c.isdigit() for c in result)

    @pytest.mark.parametrize("value", [
        Decimal(-1000),
        Decimal("-1000.00"),
    ])
    def test_negative_1000_currency(
        self, value: Decimal
    ) -> None:
        """Negative 1000 currency values format correctly."""
        ctx = LocaleContext.create("en_US")
        result = ctx.format_currency(value, currency="USD")
        assert isinstance(result, str)
        assert result
        assert "-" in result or "(" in result

    @pytest.mark.parametrize("currency", [
        "USD", "EUR", "GBP", "JPY", "CNY", "CHF", "CAD",
        "AUD",
    ])
    def test_currency_1000_multiple_currencies(
        self, currency: str
    ) -> None:
        """Currency formatting for 1000 with currencies."""
        ctx = LocaleContext.create("en_US")
        result = ctx.format_currency(
            Decimal(1000), currency=currency
        )
        assert isinstance(result, str)
        assert result
        assert any(c.isdigit() for c in result)

    def test_currency_1000_all_display_modes(self) -> None:
        """Currency formatting 1000 with all display modes."""
        ctx = LocaleContext.create("en_US")
        value = Decimal(1000)

        result_symbol = ctx.format_currency(
            value, currency="USD", currency_display="symbol"
        )
        assert "$" in result_symbol

        result_code = ctx.format_currency(
            value, currency="USD", currency_display="code"
        )
        assert "USD" in result_code

        result_name = ctx.format_currency(
            value, currency="USD", currency_display="name"
        )
        assert "dollar" in result_name.lower()

    def test_currency_integer_1000(self) -> None:
        """Currency formatting handles int 1000."""
        ctx = LocaleContext.create("en_US")
        result = ctx.format_currency(1000, currency="USD")
        assert isinstance(result, str)
        assert "$" in result or "USD" in result

    def test_currency_decimal_1000(self) -> None:
        """Currency formatting handles Decimal 1000."""
        ctx = LocaleContext.create("en_US")
        result = ctx.format_currency(Decimal(1000), currency="USD")
        assert isinstance(result, str)
        assert "$" in result or "USD" in result

class TestLocaleContextCoverageExtra:
    """Test LocaleContext cache_info and datetime formatting branches."""

    def test_cache_info_returns_dict(self) -> None:
        """cache_info() returns dict with size, max_size, and locales keys."""
        LocaleContext.clear_cache()

        LocaleContext.create("en-US")
        LocaleContext.create("de-DE")

        info = LocaleContext.cache_info()

        assert isinstance(info, dict)
        assert "size" in info
        assert "max_size" in info
        assert "locales" in info
        assert info["size"] == 2
        locales = info["locales"]
        assert isinstance(locales, tuple)
        assert "en_us" in locales or "de_de" in locales

    def test_format_datetime_combined_styles(self) -> None:
        """format_datetime with both date and time styles produces non-empty string."""
        ctx = LocaleContext.create("en-US")

        dt = datetime(2024, 6, 15, 14, 30, 0, tzinfo=UTC)
        result = ctx.format_datetime(dt, date_style="medium", time_style="short")

        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_datetime_date_only(self) -> None:
        """format_datetime with date_style only produces non-empty string."""
        ctx = LocaleContext.create("en-US")

        dt = datetime(2024, 12, 25, 0, 0, 0, tzinfo=UTC)
        result = ctx.format_datetime(dt, date_style="long")

        assert isinstance(result, str)
        assert "2024" in result or "December" in result

class TestLocaleContextBranchCoverageExtra:
    """Additional tests for locale_context formatting branch coverage."""

    def test_format_datetime_with_string_pattern(self) -> None:
        """format_datetime with both date and time styles covers combined-pattern path."""
        ctx = LocaleContext.create("en-US")

        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)

        result1 = ctx.format_datetime(dt, date_style="short", time_style="short")
        assert isinstance(result1, str)

        result2 = ctx.format_datetime(dt, date_style="full", time_style="full")
        assert isinstance(result2, str)

    def test_format_datetime_varied_styles(self) -> None:
        """All standard datetime style combinations produce non-empty strings."""
        type _DateTimeStyle = Literal["short", "medium", "long", "full"]
        styles: tuple[_DateTimeStyle, ...] = get_args(_DateTimeStyle)

        ctx = LocaleContext.create("en-US")
        dt = datetime(2024, 3, 15, 10, 30, 0, tzinfo=UTC)

        for date_style in styles:
            for time_style in styles:
                result = ctx.format_datetime(
                    dt, date_style=date_style, time_style=time_style
                )
                assert isinstance(result, str)
                assert len(result) > 0

class TestLocaleContextCacheRaceCondition:
    """LocaleContext cache handles the double-check locking pattern."""

    def test_cache_hit_in_double_check_pattern(self) -> None:
        """Cache hit during the inner lock check returns the cached instance."""
        LocaleContext.clear_cache()

        locale_code = "en_US"
        ctx = LocaleContext.create(locale_code)

        cache_key = normalize_locale(locale_code)
        with LocaleContext._cache_lock:  # pylint: disable=protected-access
            LocaleContext._cache.clear()  # pylint: disable=protected-access
            LocaleContext._cache[cache_key] = ctx  # pylint: disable=protected-access

        result = LocaleContext.create(locale_code)
        assert result is ctx

        LocaleContext.clear_cache()

class TestLocaleContextDatetimePattern:
    """LocaleContext formats datetime values using the locale's pattern."""

    def test_datetime_pattern_without_format_method(self) -> None:
        """format_datetime produces a non-empty string for en_US short styles."""
        LocaleContext.clear_cache()

        ctx = LocaleContext.create("en_US")
        dt = datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC)

        result = ctx.format_datetime(dt, date_style="short", time_style="short")
        assert result is not None
        assert len(result) > 0

        LocaleContext.clear_cache()

class TestLocaleContextCacheLimitCoverage:
    """LocaleContext LRU cache eviction at MAX_LOCALE_CACHE_SIZE."""

    def test_cache_at_limit_evicts_lru_entry(self) -> None:
        """When cache reaches MAX_LOCALE_CACHE_SIZE, LRU entry is evicted on next create."""
        LocaleContext.clear_cache()

        locales_to_fill = [f"en_TEST{i:04d}" for i in range(MAX_LOCALE_CACHE_SIZE)]

        for locale_code in locales_to_fill:
            ctx = LocaleContext.create(locale_code)
            assert ctx is not None

        cache_size = LocaleContext.cache_size()
        assert cache_size >= MAX_LOCALE_CACHE_SIZE

        size_before = cache_size

        ctx = LocaleContext.create("de_TESTOVERFLOW")
        assert ctx is not None

        cache_size_after = LocaleContext.cache_size()
        assert cache_size_after <= MAX_LOCALE_CACHE_SIZE
        assert cache_size_after <= size_before + 1

        LocaleContext.clear_cache()

class TestLocaleContextUnexpectedErrorPropagation:
    """Unexpected errors propagate instead of being silently caught."""

    def test_format_number_unexpected_error_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RuntimeError in format_number propagates for debugging."""
        ctx = LocaleContext.create_or_raise("en_US")

        def mock_format_decimal(*_args: object, **_kwargs: object) -> str:
            msg = "Mocked RuntimeError for testing"
            raise RuntimeError(msg)

        monkeypatch.setattr(babel_numbers, "format_decimal", mock_format_decimal)

        with pytest.raises(RuntimeError, match="Mocked RuntimeError"):
            ctx.format_number(Decimal("123.45"))

    def test_format_currency_unexpected_error_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """RuntimeError in format_currency propagates for debugging."""
        ctx = LocaleContext.create_or_raise("en_US")

        def mock_format_currency(*_args: object, **_kwargs: object) -> str:
            msg = "Mocked RuntimeError for testing"
            raise RuntimeError(msg)

        monkeypatch.setattr(babel_numbers, "format_currency", mock_format_currency)

        with pytest.raises(RuntimeError, match="Mocked RuntimeError"):
            ctx.format_currency(Decimal(100), currency="USD")

class TestLocaleContextCustomPatternCoverage:
    """Custom pattern and currency code fallback branches in format_currency."""

    def test_format_currency_with_custom_pattern(self) -> None:
        """Custom pattern in format_currency is applied to the result."""
        ctx = LocaleContext.create_or_raise("en_US")

        result = ctx.format_currency(Decimal("1234.56"), currency="USD", pattern="#,##0.00 \xa4")

        assert isinstance(result, str)
        assert "1,234.56" in result or "1234.56" in result

    def test_format_currency_code_display_fallback(
        self, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """format_currency logs debug when locale pattern lacks currency placeholder."""
        mock_locale = MagicMock()
        mock_pattern = MagicMock()
        mock_pattern.pattern = "#,##0.00"  # No currency placeholder (missing \xa4)
        mock_locale.currency_formats = {"standard": mock_pattern}

        ctx = LocaleContext.create_or_raise("en_US")
        original_babel_locale = ctx._babel_locale  # pylint: disable=protected-access

        object.__setattr__(ctx, "_babel_locale", mock_locale)

        monkeypatch.setattr(
            babel_numbers,
            "format_currency",
            lambda *_args, **_kwargs: "$100.00",
        )

        try:
            with caplog.at_level(logging.DEBUG):
                result = ctx.format_currency(
                    Decimal(100), currency="USD", currency_display="code"
                )

            assert isinstance(result, str)

            assert any(
                "lacks placeholder" in record.message
                for record in caplog.records
            )
        finally:
            object.__setattr__(ctx, "_babel_locale", original_babel_locale)

class TestLocaleContextCurrencyCodeFallback:
    """Currency code display fallback when standard_pattern is None or lacks attributes."""

    def test_format_currency_code_no_standard_pattern(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """format_currency falls through to default when standard_pattern is None."""
        ctx = LocaleContext.create_or_raise("en_US")
        original_babel_locale = ctx._babel_locale  # pylint: disable=protected-access

        mock_locale = MagicMock()
        mock_locale.currency_formats = {"standard": None}

        object.__setattr__(ctx, "_babel_locale", mock_locale)

        monkeypatch.setattr(
            babel_numbers,
            "format_currency",
            lambda *_args, **_kwargs: "$100.00",
        )

        try:
            result = ctx.format_currency(Decimal(100), currency="USD", currency_display="code")
            assert isinstance(result, str)
        finally:
            object.__setattr__(ctx, "_babel_locale", original_babel_locale)

    def test_format_currency_code_pattern_no_attr(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """format_currency falls through to default when standard_pattern lacks 'pattern' attr."""
        ctx = LocaleContext.create_or_raise("en_US")
        original_babel_locale = ctx._babel_locale  # pylint: disable=protected-access

        mock_locale = MagicMock()
        mock_pattern = object()  # Plain object with no attributes
        mock_locale.currency_formats = {"standard": mock_pattern}

        object.__setattr__(ctx, "_babel_locale", mock_locale)

        monkeypatch.setattr(
            babel_numbers,
            "format_currency",
            lambda *_args, **_kwargs: "$100.00",
        )

        try:
            result = ctx.format_currency(Decimal(100), currency="USD", currency_display="code")
            assert isinstance(result, str)
        finally:
            object.__setattr__(ctx, "_babel_locale", original_babel_locale)
