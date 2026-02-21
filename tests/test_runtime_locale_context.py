"""Tests for LocaleContext - locale-aware formatting without global state.

Tests immutable locale configuration, thread-safe caching, CLDR-compliant
formatting for numbers, dates, and currency via Babel integration.

Covers:
- Factory methods (create, create_or_raise) and construction guard
- Cache management (identity, LRU eviction, double-check pattern)
- Number formatting (grouping, decimals, special values, validation)
- DateTime formatting (styles, patterns, ISO string input)
- Currency formatting (symbol/code/name display, patterns, boundary values)
- Internal helpers (_get_iso_code_pattern)
- Long locale code handling
- Babel import error paths

Python 3.13+.
"""

from __future__ import annotations

import logging
import sys
import threading
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from babel import Locale
from babel import dates as babel_dates
from babel import numbers as babel_numbers

import ftllexengine.core.babel_compat as _bc
from ftllexengine.constants import MAX_LOCALE_CACHE_SIZE
from ftllexengine.core.babel_compat import BabelImportError
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.locale_context import LocaleContext

# ============================================================================
# Construction Guard Tests
# ============================================================================


class TestLocaleContextConstructionGuard:
    """Test __post_init__ validation prevents direct construction."""

    def test_direct_construction_without_token_raises(self) -> None:
        """Direct construction without factory token raises TypeError."""
        babel_locale = Locale.parse("en_US")

        with pytest.raises(TypeError) as exc_info:
            LocaleContext(
                locale_code="en-US",
                _babel_locale=babel_locale,
            )

        error_msg = str(exc_info.value)
        assert "LocaleContext.create()" in error_msg
        assert "LocaleContext.create_or_raise()" in error_msg
        assert "direct construction" in error_msg

    def test_direct_construction_with_wrong_token_raises(self) -> None:
        """Direct construction with invalid token raises TypeError."""
        babel_locale = Locale.parse("en_US")
        wrong_token = object()

        with pytest.raises(TypeError) as exc_info:
            LocaleContext(
                locale_code="en-US",
                _babel_locale=babel_locale,
                _factory_token=wrong_token,
            )

        assert "LocaleContext.create()" in str(exc_info.value)

    def test_direct_construction_with_none_token_raises(self) -> None:
        """Direct construction with None token raises TypeError."""
        babel_locale = Locale.parse("en_US")

        with pytest.raises(TypeError) as exc_info:
            LocaleContext(
                locale_code="en-US",
                _babel_locale=babel_locale,
                _factory_token=None,
            )

        error_msg = str(exc_info.value)
        assert "LocaleContext.create()" in error_msg
        assert "direct construction" in error_msg

    def test_factory_methods_bypass_guard(self) -> None:
        """Factory methods bypass __post_init__ guard successfully."""
        ctx1 = LocaleContext.create("en-US")
        assert isinstance(ctx1, LocaleContext)

        ctx2 = LocaleContext.create_or_raise("de-DE")
        assert isinstance(ctx2, LocaleContext)


# ============================================================================
# Cache Management Tests
# ============================================================================


class TestLocaleContextCacheManagement:
    """Test LocaleContext cache operations."""

    def test_clear_cache_empties_cache(self) -> None:
        """clear_cache() empties the cache."""
        LocaleContext.clear_cache()
        LocaleContext.create("en-US")
        LocaleContext.create("de-DE")
        assert LocaleContext.cache_size() > 0

        LocaleContext.clear_cache()
        assert LocaleContext.cache_size() == 0

    def test_cache_size_returns_count(self) -> None:
        """cache_size() returns number of cached instances."""
        LocaleContext.clear_cache()
        assert LocaleContext.cache_size() == 0

        LocaleContext.create("en-US")
        assert LocaleContext.cache_size() == 1

        LocaleContext.create("de-DE")
        assert LocaleContext.cache_size() == 2

    def test_cache_info_returns_dict(self) -> None:
        """cache_info() returns dictionary with expected keys."""
        LocaleContext.clear_cache()
        LocaleContext.create("en-US")
        LocaleContext.create("de-DE")

        info = LocaleContext.cache_info()

        assert isinstance(info, dict)
        assert "size" in info
        assert "max_size" in info
        assert "locales" in info
        assert isinstance(info["locales"], tuple)
        assert info["size"] == 2

    def test_cache_info_after_clear(self) -> None:
        """cache_info() returns empty after clearing."""
        LocaleContext.clear_cache()
        LocaleContext.create("en-US")

        LocaleContext.clear_cache()
        info = LocaleContext.cache_info()

        assert info["size"] == 0
        assert info["locales"] == ()

    def test_cache_returns_same_instance(self) -> None:
        """Cache returns the same instance for same locale."""
        LocaleContext.clear_cache()

        ctx1 = LocaleContext.create("en-US")
        ctx2 = LocaleContext.create("en-US")

        assert ctx1 is ctx2

    def test_cache_double_check_pattern(self) -> None:
        """Cache double-check pattern returns existing instance."""
        from ftllexengine.core.locale_utils import (  # noqa: PLC0415
            normalize_locale,
        )
        from ftllexengine.runtime.locale_context import (  # noqa: PLC0415
            _FACTORY_TOKEN,
        )

        LocaleContext.clear_cache()

        cache_key = normalize_locale("en-RACE-TEST")
        pre_inserted_ctx = LocaleContext(
            locale_code="en-RACE-TEST",
            _babel_locale=Locale.parse("en_US"),
            _factory_token=_FACTORY_TOKEN,
        )

        original_parse = Locale.parse

        def parse_with_insertion(
            code: str, *args: Any, **kwargs: Any
        ) -> Locale:
            with LocaleContext._cache_lock:
                if cache_key not in LocaleContext._cache:
                    LocaleContext._cache[cache_key] = (
                        pre_inserted_ctx
                    )
            return original_parse(code, *args, **kwargs)

        with patch.object(
            Locale, "parse", side_effect=parse_with_insertion
        ):
            result = LocaleContext.create("en-RACE-TEST")

        assert result is pre_inserted_ctx

    def test_cache_thread_safety(self) -> None:
        """Cache is thread-safe under concurrent access."""
        LocaleContext.clear_cache()

        results: list[LocaleContext] = []

        def create_context() -> None:
            ctx = LocaleContext.create("en-US")
            results.append(ctx)

        thread1 = threading.Thread(target=create_context)
        thread2 = threading.Thread(target=create_context)

        thread1.start()
        thread2.start()
        thread1.join()
        thread2.join()

        assert len(results) == 2
        assert results[0] is results[1]

    def test_cache_eviction_on_max_size(self) -> None:
        """Cache evicts LRU entry when max size reached."""
        LocaleContext.clear_cache()

        locales = ["en-US"] + [
            f"de-DE-x-variant{i}"
            for i in range(MAX_LOCALE_CACHE_SIZE)
        ]

        for locale in locales[:MAX_LOCALE_CACHE_SIZE]:
            LocaleContext.create(locale)

        assert (
            LocaleContext.cache_size() == MAX_LOCALE_CACHE_SIZE
        )

        LocaleContext.create(locales[MAX_LOCALE_CACHE_SIZE])

        assert (
            LocaleContext.cache_size() == MAX_LOCALE_CACHE_SIZE
        )

        info = LocaleContext.cache_info()
        locales_tuple = info["locales"]
        assert isinstance(locales_tuple, tuple)
        assert "en_US" not in locales_tuple

    def test_clear_cache_and_recreate(self) -> None:
        """Cache clearing and recreation works correctly."""
        LocaleContext.clear_cache()

        ctx1 = LocaleContext.create("fr-FR")
        assert ctx1.locale_code == "fr-FR"

        ctx2 = LocaleContext.create("fr-FR")
        assert ctx1 is ctx2

        LocaleContext.clear_cache()
        ctx3 = LocaleContext.create("fr-FR")
        assert ctx1 is not ctx3


# ============================================================================
# Factory Methods Tests
# ============================================================================


class TestLocaleContextCreate:
    """Test LocaleContext.create() factory with graceful fallback."""

    def test_create_valid_locale(self) -> None:
        """create() returns LocaleContext for valid locale."""
        ctx = LocaleContext.create("en-US")
        assert isinstance(ctx, LocaleContext)
        assert ctx.locale_code == "en-US"

    def test_create_unknown_locale_returns_context(self) -> None:
        """create() returns LocaleContext for unknown locale."""
        LocaleContext.clear_cache()
        result = LocaleContext.create("xx-UNKNOWN")

        assert isinstance(result, LocaleContext)
        assert result.locale_code == "xx-UNKNOWN"
        assert result.is_fallback is True

    def test_create_unknown_locale_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """create() logs warning for unknown locale."""
        LocaleContext.clear_cache()

        with caplog.at_level(logging.WARNING):
            LocaleContext.create("xx_INVALID")

        assert any(
            "Unknown locale" in r.message
            or "xx_INVALID" in r.message
            for r in caplog.records
        )

    def test_create_invalid_format_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """create() logs warning for invalid locale format."""
        LocaleContext.clear_cache()

        with caplog.at_level(logging.WARNING):
            LocaleContext.create("!!!INVALID@@@")

        assert any(
            "locale" in r.message.lower()
            for r in caplog.records
        )

    def test_create_unknown_locale_uses_en_us(self) -> None:
        """create() uses en_US formatting for invalid locales."""
        ctx = LocaleContext.create("invalid-locale-xyz")
        locale = ctx.babel_locale

        assert locale.language == "en"


class TestLocaleContextCreateOrRaise:
    """Test create_or_raise() factory with strict validation."""

    def test_create_or_raise_valid_locale(self) -> None:
        """create_or_raise() returns LocaleContext for valid locale."""
        ctx = LocaleContext.create_or_raise("en-US")
        assert isinstance(ctx, LocaleContext)
        assert ctx.locale_code == "en-US"
        assert ctx.is_fallback is False

    def test_create_or_raise_unknown_locale_raises(self) -> None:
        """create_or_raise() raises ValueError for unknown locale."""
        with pytest.raises(
            ValueError, match=r"Unknown locale identifier"
        ):
            LocaleContext.create_or_raise("xx-INVALID")

    def test_create_or_raise_invalid_format_raises(self) -> None:
        """create_or_raise() raises ValueError for invalid format."""
        with pytest.raises(ValueError, match=r"locale"):
            LocaleContext.create_or_raise(
                "not-a-valid-locale-at-all"
            )

    def test_create_or_raise_error_contains_locale_code(
        self,
    ) -> None:
        """create_or_raise() error message includes locale code."""
        test_locales = ["bad-locale", "xyz-123"]

        for locale_code in test_locales:
            with pytest.raises(
                ValueError, match="locale"
            ) as exc_info:
                LocaleContext.create_or_raise(locale_code)

            assert locale_code in str(exc_info.value)


# ============================================================================
# Babel Import Error Tests
# ============================================================================


class TestLocaleContextBabelImportErrors:
    """Test ImportError paths when Babel is not installed."""

    def test_create_raises_babel_import_error(self) -> None:
        """create() raises BabelImportError when Babel unavailable."""
        LocaleContext.clear_cache()

        babel_module = sys.modules.pop("babel", None)
        babel_core = sys.modules.pop("babel.core", None)
        babel_dates_mod = sys.modules.pop("babel.dates", None)
        babel_nums = sys.modules.pop("babel.numbers", None)

        # Reset sentinel so _check_babel_available() re-evaluates under the mock
        _bc._babel_available = None

        try:
            with patch.dict(sys.modules, {"babel": None}):
                original_import = __import__

                def mock_import(
                    name: str,
                    globals_dict: (
                        dict[str, object] | None
                    ) = None,
                    locals_dict: (
                        dict[str, object] | None
                    ) = None,
                    fromlist: tuple[str, ...] = (),
                    level: int = 0,
                ) -> object:
                    if name == "babel":
                        msg = "Mocked: Babel not installed"
                        raise ImportError(msg)
                    return original_import(
                        name,
                        globals_dict,
                        locals_dict,
                        fromlist,
                        level,
                    )

                with patch(
                    "builtins.__import__",
                    side_effect=mock_import,
                ):
                    with pytest.raises(
                        BabelImportError
                    ) as exc_info:
                        LocaleContext.create("en-US")

                    assert "LocaleContext.create" in str(
                        exc_info.value
                    )
        finally:
            if babel_module is not None:
                sys.modules["babel"] = babel_module
            if babel_core is not None:
                sys.modules["babel.core"] = babel_core
            if babel_dates_mod is not None:
                sys.modules["babel.dates"] = babel_dates_mod
            if babel_nums is not None:
                sys.modules["babel.numbers"] = babel_nums
            # Reset sentinel so subsequent tests reinitialize with Babel available
            _bc._babel_available = None
            LocaleContext.clear_cache()

    def test_create_or_raise_raises_babel_import_error(
        self,
    ) -> None:
        """create_or_raise() raises BabelImportError."""
        babel_module = sys.modules.pop("babel", None)
        babel_core = sys.modules.pop("babel.core", None)
        babel_dates_mod = sys.modules.pop("babel.dates", None)
        babel_nums = sys.modules.pop("babel.numbers", None)

        # Reset sentinel so _check_babel_available() re-evaluates under the mock
        _bc._babel_available = None

        try:
            with patch.dict(sys.modules, {"babel": None}):
                original_import = __import__

                def mock_import(
                    name: str,
                    globals_dict: (
                        dict[str, object] | None
                    ) = None,
                    locals_dict: (
                        dict[str, object] | None
                    ) = None,
                    fromlist: tuple[str, ...] = (),
                    level: int = 0,
                ) -> object:
                    if name == "babel":
                        msg = "Mocked: Babel not installed"
                        raise ImportError(msg)
                    return original_import(
                        name,
                        globals_dict,
                        locals_dict,
                        fromlist,
                        level,
                    )

                with patch(
                    "builtins.__import__",
                    side_effect=mock_import,
                ):
                    with pytest.raises(
                        BabelImportError
                    ) as exc_info:
                        LocaleContext.create_or_raise("en-US")

                    assert "create_or_raise" in str(
                        exc_info.value
                    )
        finally:
            if babel_module is not None:
                sys.modules["babel"] = babel_module
            if babel_core is not None:
                sys.modules["babel.core"] = babel_core
            if babel_dates_mod is not None:
                sys.modules["babel.dates"] = babel_dates_mod
            if babel_nums is not None:
                sys.modules["babel.numbers"] = babel_nums
            # Reset sentinel so subsequent tests reinitialize with Babel available
            _bc._babel_available = None


# ============================================================================
# Number Formatting Tests
# ============================================================================


class TestFormatNumber:
    """Test format_number() with various locales and parameters."""

    def test_format_number_en_us_grouping(self) -> None:
        """format_number() formats with grouping for en-US."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(1234.5, use_grouping=True)
        assert "1,234" in result or "1234" in result

    def test_format_number_de_de_grouping(self) -> None:
        """format_number() formats with grouping for de-DE."""
        ctx = LocaleContext.create("de-DE")
        result = ctx.format_number(1234.5, use_grouping=True)
        assert "1.234" in result or "1234" in result

    def test_format_number_fixed_decimals(self) -> None:
        """format_number() formats with fixed decimal places."""
        ctx = LocaleContext.create("en-US")

        result = ctx.format_number(
            1234.5,
            minimum_fraction_digits=2,
            maximum_fraction_digits=2,
        )
        assert result == "1,234.50"

        result = ctx.format_number(
            1234.567,
            minimum_fraction_digits=0,
            maximum_fraction_digits=0,
        )
        assert result == "1,235"
        assert "." not in result

    def test_format_number_fixed_three_decimals(self) -> None:
        """format_number() with fixed 3 decimal places."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(
            123.4,
            minimum_fraction_digits=3,
            maximum_fraction_digits=3,
        )
        assert result == "123.400"

    def test_format_number_custom_pattern(self) -> None:
        """format_number() respects custom pattern."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(
            -1234.56, pattern="#,##0.00;(#,##0.00)"
        )
        assert "1,234.56" in result or "1234.56" in result

    def test_format_number_preserves_decimal_precision(
        self,
    ) -> None:
        """format_number() preserves large decimal precision."""
        ctx = LocaleContext.create("en-US")

        large_decimal = Decimal("123456789.123456789")
        result = ctx.format_number(
            large_decimal,
            minimum_fraction_digits=2,
            maximum_fraction_digits=2,
        )

        assert result == "123,456,789.12"
        assert result.count(".") == 1
        decimal_part = result.split(".")[-1]
        assert len(decimal_part) == 2

    def test_format_number_with_decimal_type(self) -> None:
        """format_number() with Decimal type for fixed decimals."""
        ctx = LocaleContext.create("de-DE")

        value = Decimal("1234.5")
        result = ctx.format_number(
            value,
            minimum_fraction_digits=2,
            maximum_fraction_digits=2,
        )

        assert "," in result
        assert result == "1.234,50"

    def test_format_number_error_raises_formatting_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """format_number() raises FrozenFluentError on error."""
        def mock_format_decimal(
            *_args: object, **_kwargs: object
        ) -> None:
            msg = "Mocked format error"
            raise ValueError(msg)

        monkeypatch.setattr(
            babel_numbers,
            "format_decimal",
            mock_format_decimal,
        )

        ctx = LocaleContext.create("en-US")
        with pytest.raises(FrozenFluentError) as exc_info:
            ctx.format_number(123.45)

        assert (
            exc_info.value.category == ErrorCategory.FORMATTING
        )
        assert exc_info.value.fallback_value == "123.450"


# ============================================================================
# Number Formatting Validation Tests
# ============================================================================


class TestFormatNumberDigitValidation:
    """Test format_number() digit parameter validation."""

    def test_minimum_fraction_digits_negative_raises(
        self,
    ) -> None:
        """Raises ValueError for negative minimum."""
        ctx = LocaleContext.create("en-US")
        with pytest.raises(
            ValueError,
            match=r"minimum_fraction_digits must be",
        ):
            ctx.format_number(
                123.45, minimum_fraction_digits=-1
            )

    def test_minimum_fraction_digits_exceeds_max_raises(
        self,
    ) -> None:
        """Raises ValueError when exceeding MAX_FORMAT_DIGITS."""
        from ftllexengine.constants import (  # noqa: PLC0415
            MAX_FORMAT_DIGITS,
        )

        ctx = LocaleContext.create("en-US")
        with pytest.raises(
            ValueError,
            match=r"minimum_fraction_digits must be",
        ):
            ctx.format_number(
                123.45,
                minimum_fraction_digits=MAX_FORMAT_DIGITS + 1,
            )

    def test_maximum_fraction_digits_negative_raises(
        self,
    ) -> None:
        """Raises ValueError for negative maximum."""
        ctx = LocaleContext.create("en-US")
        with pytest.raises(
            ValueError,
            match=r"maximum_fraction_digits must be",
        ):
            ctx.format_number(
                123.45, maximum_fraction_digits=-1
            )

    def test_maximum_fraction_digits_exceeds_max_raises(
        self,
    ) -> None:
        """Raises ValueError when exceeding MAX_FORMAT_DIGITS."""
        from ftllexengine.constants import (  # noqa: PLC0415
            MAX_FORMAT_DIGITS,
        )

        ctx = LocaleContext.create("en-US")
        with pytest.raises(
            ValueError,
            match=r"maximum_fraction_digits must be",
        ):
            ctx.format_number(
                123.45,
                maximum_fraction_digits=MAX_FORMAT_DIGITS + 1,
            )


class TestFormatNumberSpecialValues:
    """Test format_number() with special float values."""

    def test_format_number_positive_infinity(self) -> None:
        """format_number() handles positive infinity."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(float("inf"))
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_number_negative_infinity(self) -> None:
        """format_number() handles negative infinity."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(float("-inf"))
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_number_nan(self) -> None:
        """format_number() handles NaN."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(float("nan"))
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_number_infinity_with_grouping(self) -> None:
        """format_number() handles infinity with use_grouping."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(
            float("inf"), use_grouping=False
        )
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_number_nan_with_custom_pattern(self) -> None:
        """format_number() handles NaN with custom pattern."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(
            float("nan"), pattern="#,##0.00"
        )
        assert isinstance(result, str)
        assert len(result) > 0


# ============================================================================
# DateTime Formatting Tests
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


# ============================================================================
# Currency Formatting Tests
# ============================================================================


class TestFormatCurrency:
    """Test format_currency() with various locales and parameters."""

    def test_format_currency_en_us_symbol(self) -> None:
        """format_currency() with symbol for en-US."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_currency(
            123.45, currency="EUR"
        )
        assert "123" in result

    def test_format_currency_lv_lv_symbol(self) -> None:
        """format_currency() with symbol for lv-LV."""
        ctx = LocaleContext.create("lv-LV")
        result = ctx.format_currency(
            123.45, currency="EUR"
        )
        assert "123" in result

    def test_format_currency_code_display(self) -> None:
        """format_currency() displays currency code."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_currency(
            123.45,
            currency="USD",
            currency_display="code",
        )
        assert "USD" in result
        assert "123.45" in result

    def test_format_currency_name_display(self) -> None:
        """format_currency() displays currency name."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_currency(
            123.45,
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
            123.45,
            currency="EUR",
            currency_display="symbol",
        )
        assert "123.45" in result

    def test_format_currency_custom_pattern(self) -> None:
        """format_currency() respects custom pattern."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_currency(
            1234.56,
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
            ctx.format_currency(123.45, currency="USD")

        assert (
            exc_info.value.category == ErrorCategory.FORMATTING
        )
        assert "USD 123.45" in exc_info.value.fallback_value


# ============================================================================
# Internal Helper Tests
# ============================================================================


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


# ============================================================================
# Currency Pattern Fallback Tests
# ============================================================================


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
                123.45,
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
                123.45,
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
                123.45,
                currency="USD",
                currency_display="code",
            )
            assert isinstance(result, str)
            assert "123" in result


# ============================================================================
# Long Locale Code Tests
# ============================================================================


class TestLongLocaleCodeCoverage:
    """Tests for long locale codes exceeding BCP 47 length."""

    def test_long_valid_locale_code_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Long valid locale code triggers warning."""
        from ftllexengine.constants import (  # noqa: PLC0415
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
        from ftllexengine.constants import (  # noqa: PLC0415
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

    def test_long_invalid_format_locale_code_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Long invalid format locale code triggers warning."""
        from ftllexengine.constants import (  # noqa: PLC0415
            MAX_LOCALE_CODE_LENGTH,
        )

        LocaleContext.clear_cache()

        long_invalid = (
            "!!!INVALID@@@FORMAT###TOOLONG###LOCALE"
        )
        assert len(long_invalid) > MAX_LOCALE_CODE_LENGTH

        with caplog.at_level(logging.WARNING):
            ctx = LocaleContext.create(long_invalid)

        relevant = [
            r.message
            for r in caplog.records
            if "locale" in r.message.lower()
        ]
        assert any(
            "exceeds" in msg
            and ("Invalid" in msg or "invalid" in msg)
            for msg in relevant
        )
        assert ctx.is_fallback is True


# ============================================================================
# Currency Boundary Value Tests
# ============================================================================


class TestCurrencyBoundaryValues:
    """Regression tests for currency formatting boundaries."""

    @pytest.mark.parametrize("value", [
        Decimal("999"),
        Decimal("999.99"),
        Decimal("1000"),
        Decimal("1000.00"),
        Decimal("1000.01"),
        Decimal("1001"),
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
            Decimal("1000"), currency="USD"
        )
        assert isinstance(result, str)
        assert result
        assert any(c.isdigit() for c in result)

    @pytest.mark.parametrize("value", [
        Decimal("-1000"),
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
            Decimal("1000"), currency=currency
        )
        assert isinstance(result, str)
        assert result
        assert any(c.isdigit() for c in result)

    def test_currency_1000_all_display_modes(self) -> None:
        """Currency formatting 1000 with all display modes."""
        ctx = LocaleContext.create("en_US")
        value = Decimal("1000")

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

    def test_currency_float_1000(self) -> None:
        """Currency formatting handles float 1000.0."""
        ctx = LocaleContext.create("en_US")
        result = ctx.format_currency(1000.0, currency="USD")
        assert isinstance(result, str)
        assert "$" in result or "USD" in result
