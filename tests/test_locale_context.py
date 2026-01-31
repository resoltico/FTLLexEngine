"""Tests for LocaleContext - locale-aware formatting without global state.

Tests immutable locale configuration, thread-safe caching, CLDR-compliant formatting
for numbers, dates, and currency via Babel integration.

Property-Based Tests:
    Uses Hypothesis to verify mathematical properties across locale domains.

Coverage:
    Comprehensive coverage including error paths, fallback behavior, and edge cases.
"""

from __future__ import annotations

import logging
import sys
import threading
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from babel import dates as babel_dates
from babel import numbers as babel_numbers
from hypothesis import example, given, settings
from hypothesis import strategies as st

from ftllexengine.constants import MAX_LOCALE_CACHE_SIZE
from ftllexengine.core.babel_compat import BabelImportError
from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.locale_context import LocaleContext

# ============================================================================
# Cache Management Tests
# ============================================================================


class TestLocaleContextCacheManagement:
    """Test LocaleContext cache operations (clear_cache, cache_size, cache_info)."""

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
        info = LocaleContext.cache_info()

        assert isinstance(info, dict)
        assert "size" in info
        assert "max_size" in info
        assert "locales" in info
        assert isinstance(info["locales"], tuple)

    def test_cache_info_after_clear(self) -> None:
        """cache_info() returns empty after clearing."""
        LocaleContext.clear_cache()
        LocaleContext.create("en-US")

        LocaleContext.clear_cache()
        info = LocaleContext.cache_info()

        assert info["size"] == 0
        assert info["locales"] == ()

    def test_cache_returns_same_instance(self) -> None:
        """Cache returns the same instance for same locale (identity caching)."""
        LocaleContext.clear_cache()

        ctx1 = LocaleContext.create("en-US")
        ctx2 = LocaleContext.create("en-US")

        assert ctx1 is ctx2  # Identity, not just equality

    def test_cache_double_check_pattern(self) -> None:
        """Cache double-check pattern returns existing instance (line 235)."""
        LocaleContext.clear_cache()

        # Shared storage for instances
        results: list[LocaleContext] = []

        def create_context() -> None:
            ctx = LocaleContext.create("en-US")
            results.append(ctx)

        # Create two threads that will try to create the same locale simultaneously
        thread1 = threading.Thread(target=create_context)
        thread2 = threading.Thread(target=create_context)

        thread1.start()
        thread2.start()
        thread1.join()
        thread2.join()

        # Both threads should get the same cached instance
        assert len(results) == 2
        assert results[0] is results[1]

    def test_cache_eviction_on_max_size(self) -> None:
        """Cache evicts LRU entry when max size reached (line 239)."""
        LocaleContext.clear_cache()

        # Fill cache to max
        locales = ["en-US"] + [f"de-DE-x-variant{i}" for i in range(MAX_LOCALE_CACHE_SIZE)]

        for _i, locale in enumerate(locales[: MAX_LOCALE_CACHE_SIZE]):
            LocaleContext.create(locale)

        # Cache should be at max size
        assert LocaleContext.cache_size() == MAX_LOCALE_CACHE_SIZE

        # Add one more - should evict the LRU (first entry)
        LocaleContext.create(locales[MAX_LOCALE_CACHE_SIZE])

        # Cache should still be at max size
        assert LocaleContext.cache_size() == MAX_LOCALE_CACHE_SIZE

        # First locale should have been evicted
        info = LocaleContext.cache_info()
        locales_tuple = info["locales"]
        assert isinstance(locales_tuple, tuple)
        assert "en_US" not in locales_tuple


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
        """create() returns LocaleContext for unknown locale with fallback."""
        LocaleContext.clear_cache()
        result = LocaleContext.create("xx-UNKNOWN")

        assert isinstance(result, LocaleContext)
        assert result.locale_code == "xx-UNKNOWN"
        assert result.is_fallback is True

    def test_create_unknown_locale_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """create() logs warning for unknown locale."""
        LocaleContext.clear_cache()

        with caplog.at_level(logging.WARNING):
            LocaleContext.create("xx_INVALID")

        assert any(
            "Unknown locale" in record.message or "xx_INVALID" in record.message
            for record in caplog.records
        )

    def test_create_invalid_format_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        """create() logs warning for invalid locale format."""
        LocaleContext.clear_cache()

        with caplog.at_level(logging.WARNING):
            LocaleContext.create("!!!INVALID@@@")

        assert any("locale" in record.message.lower() for record in caplog.records)

    def test_create_unknown_locale_uses_en_us_formatting(self) -> None:
        """create() uses en_US formatting for invalid locales."""
        ctx = LocaleContext.create("invalid-locale-xyz")
        locale = ctx.babel_locale

        assert locale.language == "en"


class TestLocaleContextCreateOrRaise:
    """Test LocaleContext.create_or_raise() factory with strict validation."""

    def test_create_or_raise_valid_locale(self) -> None:
        """create_or_raise() returns LocaleContext for valid locale."""
        ctx = LocaleContext.create_or_raise("en-US")
        assert isinstance(ctx, LocaleContext)
        assert ctx.locale_code == "en-US"
        assert ctx.is_fallback is False

    def test_create_or_raise_unknown_locale_raises(self) -> None:
        """create_or_raise() raises ValueError for unknown locale."""
        with pytest.raises(ValueError, match=r"Unknown locale identifier"):
            LocaleContext.create_or_raise("xx-INVALID")

    def test_create_or_raise_invalid_format_raises(self) -> None:
        """create_or_raise() raises ValueError for invalid format."""
        with pytest.raises(ValueError, match=r"locale"):
            LocaleContext.create_or_raise("not-a-valid-locale-at-all")

    def test_create_or_raise_error_contains_locale_code(self) -> None:
        """create_or_raise() error message includes locale code."""
        test_locales = ["bad-locale", "xyz-123"]

        for locale_code in test_locales:
            with pytest.raises(ValueError, match="locale") as exc_info:
                LocaleContext.create_or_raise(locale_code)

            assert locale_code in str(exc_info.value)


# ============================================================================
# Babel Import Error Tests (lines 209-212, 273-276)
# ============================================================================


class TestLocaleContextBabelImportErrors:
    """Test ImportError paths when Babel is not installed."""

    def test_create_raises_babel_import_error_when_babel_unavailable(self) -> None:
        """create() raises BabelImportError when Babel is not available (lines 209-212)."""
        # Clear cache to force new instance creation
        LocaleContext.clear_cache()

        # Temporarily hide babel from sys.modules
        babel_module = sys.modules.pop("babel", None)
        babel_core = sys.modules.pop("babel.core", None)
        babel_dates = sys.modules.pop("babel.dates", None)
        babel_numbers = sys.modules.pop("babel.numbers", None)

        try:
            with patch.dict(sys.modules, {"babel": None}):
                original_import = __import__

                def mock_import_babel(
                    name: str,
                    globals_dict: dict[str, object] | None = None,
                    locals_dict: dict[str, object] | None = None,
                    fromlist: tuple[str, ...] = (),
                    level: int = 0,
                ) -> object:
                    if name == "babel":
                        msg = "Mocked: Babel not installed"
                        raise ImportError(msg)
                    return original_import(name, globals_dict, locals_dict, fromlist, level)

                with patch("builtins.__import__", side_effect=mock_import_babel):
                    with pytest.raises(BabelImportError) as exc_info:
                        LocaleContext.create("en-US")

                    assert "LocaleContext.create" in str(exc_info.value)
        finally:
            # Restore babel modules
            if babel_module is not None:
                sys.modules["babel"] = babel_module
            if babel_core is not None:
                sys.modules["babel.core"] = babel_core
            if babel_dates is not None:
                sys.modules["babel.dates"] = babel_dates
            if babel_numbers is not None:
                sys.modules["babel.numbers"] = babel_numbers

            LocaleContext.clear_cache()

    def test_create_or_raise_raises_babel_import_error_when_babel_unavailable(self) -> None:
        """create_or_raise() raises BabelImportError when Babel unavailable (lines 273-276)."""
        # Temporarily hide babel from sys.modules
        babel_module = sys.modules.pop("babel", None)
        babel_core = sys.modules.pop("babel.core", None)
        babel_dates = sys.modules.pop("babel.dates", None)
        babel_numbers = sys.modules.pop("babel.numbers", None)

        try:
            with patch.dict(sys.modules, {"babel": None}):
                original_import = __import__

                def mock_import_babel(
                    name: str,
                    globals_dict: dict[str, object] | None = None,
                    locals_dict: dict[str, object] | None = None,
                    fromlist: tuple[str, ...] = (),
                    level: int = 0,
                ) -> object:
                    if name == "babel":
                        msg = "Mocked: Babel not installed"
                        raise ImportError(msg)
                    return original_import(name, globals_dict, locals_dict, fromlist, level)

                with patch("builtins.__import__", side_effect=mock_import_babel):
                    with pytest.raises(BabelImportError) as exc_info:
                        LocaleContext.create_or_raise("en-US")

                    assert "LocaleContext.create_or_raise" in str(exc_info.value)
        finally:
            # Restore babel modules
            if babel_module is not None:
                sys.modules["babel"] = babel_module
            if babel_core is not None:
                sys.modules["babel.core"] = babel_core
            if babel_dates is not None:
                sys.modules["babel.dates"] = babel_dates
            if babel_numbers is not None:
                sys.modules["babel.numbers"] = babel_numbers


# ============================================================================
# Property-Based Tests (Hypothesis)
# ============================================================================


class TestLocaleContextProperties:
    """Property-based tests for LocaleContext using Hypothesis."""

    @given(
        st.text(
            alphabet=st.characters(blacklist_categories=["Cs"]),
            min_size=1,
            max_size=20,
        ).filter(lambda x: x not in {"en", "en_US", "en-US", "de", "de_DE", "lv", "lv_LV"})
    )
    @settings(max_examples=50)
    def test_create_never_crashes(self, locale_str: str) -> None:
        """create() never crashes for any locale string (property: robustness).

        Property: For all strings s, create(s) returns LocaleContext without exception.
        """
        ctx = LocaleContext.create(locale_str)

        assert isinstance(ctx, LocaleContext)
        assert ctx.babel_locale is not None

    @given(
        value=st.one_of(
            st.integers(min_value=-1_000_000, max_value=1_000_000),
            st.floats(
                min_value=-1_000_000.0,
                max_value=1_000_000.0,
                allow_nan=False,
                allow_infinity=False,
            ),
        )
    )
    @example(value=0)
    @example(value=1234.5)
    @example(value=-9999.99)
    def test_format_number_always_returns_string(self, value: int | float) -> None:
        """format_number() always returns a string (property: type safety).

        Property: For all numbers n, format_number(n) returns str.
        """
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(value)

        assert isinstance(result, str)
        assert len(result) > 0

    @given(
        locale_code=st.sampled_from(
            [
                "en-US",
                "de-DE",
                "fr-FR",
                "es-ES",
                "ja-JP",
                "zh-CN",
                "ar-SA",
                "ru-RU",
            ]
        )
    )
    @example(locale_code="en-US")
    def test_create_is_idempotent(self, locale_code: str) -> None:
        """create() is idempotent (property: caching identity).

        Property: create(x) is create(x) (identity, not just equality).
        """
        LocaleContext.clear_cache()
        ctx1 = LocaleContext.create(locale_code)
        ctx2 = LocaleContext.create(locale_code)

        assert ctx1 is ctx2

    @given(
        minimum=st.integers(min_value=0, max_value=3),
        maximum=st.integers(min_value=0, max_value=3),
    )
    @example(minimum=0, maximum=0)
    @example(minimum=2, maximum=2)
    @example(minimum=0, maximum=3)
    def test_format_number_fraction_digits_relationship(
        self, minimum: int, maximum: int
    ) -> None:
        """format_number() respects fraction digit constraints (property: validity).

        Property: When minimum <= maximum, formatting succeeds and returns valid string.
        """
        if minimum > maximum:
            return  # Skip invalid combinations

        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(
            123.456789,
            minimum_fraction_digits=minimum,
            maximum_fraction_digits=maximum,
        )

        assert isinstance(result, str)
        assert len(result) > 0


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
        """format_number() formats with fixed decimal places (lines 369-377)."""
        ctx = LocaleContext.create("en-US")

        # Fixed 2 decimals (line 371-372)
        result = ctx.format_number(1234.5, minimum_fraction_digits=2, maximum_fraction_digits=2)
        assert result == "1,234.50"

        # Fixed 0 decimals (lines 365-368)
        result = ctx.format_number(1234.567, minimum_fraction_digits=0, maximum_fraction_digits=0)
        assert result == "1,235"
        assert "." not in result

    def test_format_number_custom_pattern(self) -> None:
        """format_number() respects custom pattern."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(-1234.56, pattern="#,##0.00;(#,##0.00)")

        assert "1,234.56" in result or "1234.56" in result

    def test_format_number_preserves_decimal_precision(self) -> None:
        """format_number() preserves large decimal precision without float conversion."""
        ctx = LocaleContext.create("en-US")

        # Large decimal that would lose precision if converted to float
        large_decimal = Decimal("123456789.123456789")
        result = ctx.format_number(
            large_decimal,
            minimum_fraction_digits=2,
            maximum_fraction_digits=2,
        )

        # Should be rounded to 2 decimals: 123456789.12
        # With grouping: 123,456,789.12
        assert result == "123,456,789.12"

        # Verify no float precision artifacts (like .12000000476837158203125)
        assert result.count(".") == 1
        decimal_part = result.split(".")[-1]
        assert len(decimal_part) == 2
        assert decimal_part == "12"

    def test_format_number_error_raises_formatting_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """format_number() raises FrozenFluentError with FORMATTING category on Babel error."""
        def mock_format_decimal(*_args: object, **_kwargs: object) -> None:
            msg = "Mocked format error"
            raise ValueError(msg)

        monkeypatch.setattr(babel_numbers, "format_decimal", mock_format_decimal)

        ctx = LocaleContext.create("en-US")
        with pytest.raises(FrozenFluentError) as exc_info:
            ctx.format_number(123.45)

        assert exc_info.value.category == ErrorCategory.FORMATTING
        # After Decimal quantization with maximumFractionDigits=3 (default),
        # fallback preserves trailing zeros: "123.450" not "123.45"
        assert exc_info.value.fallback_value == "123.450"


# ============================================================================
# Number Formatting Validation Tests
# ============================================================================


class TestFormatNumberDigitValidation:
    """Test format_number() digit parameter validation (lines 378-388)."""

    def test_minimum_fraction_digits_negative_raises(self) -> None:
        """format_number() raises ValueError when minimum_fraction_digits < 0."""
        ctx = LocaleContext.create("en-US")

        with pytest.raises(ValueError, match=r"minimum_fraction_digits must be 0-100"):
            ctx.format_number(123.45, minimum_fraction_digits=-1)

    def test_minimum_fraction_digits_exceeds_max_raises(self) -> None:
        """format_number() raises ValueError when minimum_fraction_digits > MAX_FORMAT_DIGITS."""
        from ftllexengine.constants import MAX_FORMAT_DIGITS  # noqa: PLC0415

        ctx = LocaleContext.create("en-US")

        with pytest.raises(ValueError, match=r"minimum_fraction_digits must be 0-100"):
            ctx.format_number(123.45, minimum_fraction_digits=MAX_FORMAT_DIGITS + 1)

    def test_maximum_fraction_digits_negative_raises(self) -> None:
        """format_number() raises ValueError when maximum_fraction_digits < 0."""
        ctx = LocaleContext.create("en-US")

        with pytest.raises(ValueError, match=r"maximum_fraction_digits must be 0-100"):
            ctx.format_number(123.45, maximum_fraction_digits=-1)

    def test_maximum_fraction_digits_exceeds_max_raises(self) -> None:
        """format_number() raises ValueError when maximum_fraction_digits > MAX_FORMAT_DIGITS."""
        from ftllexengine.constants import MAX_FORMAT_DIGITS  # noqa: PLC0415

        ctx = LocaleContext.create("en-US")

        with pytest.raises(ValueError, match=r"maximum_fraction_digits must be 0-100"):
            ctx.format_number(123.45, maximum_fraction_digits=MAX_FORMAT_DIGITS + 1)

    @given(minimum=st.integers(max_value=-1))
    @example(minimum=-1)
    @example(minimum=-100)
    def test_minimum_fraction_digits_negative_property(self, minimum: int) -> None:
        """format_number() raises ValueError for any negative minimum_fraction_digits.

        Property: For all n < 0, format_number(x, minimum_fraction_digits=n) raises ValueError.
        """
        ctx = LocaleContext.create("en-US")

        with pytest.raises(ValueError, match=r"minimum_fraction_digits"):
            ctx.format_number(123.45, minimum_fraction_digits=minimum)

    @given(maximum=st.integers(max_value=-1))
    @example(maximum=-1)
    @example(maximum=-50)
    def test_maximum_fraction_digits_negative_property(self, maximum: int) -> None:
        """format_number() raises ValueError for any negative maximum_fraction_digits.

        Property: For all n < 0, format_number(x, maximum_fraction_digits=n) raises ValueError.
        """
        ctx = LocaleContext.create("en-US")

        with pytest.raises(ValueError, match=r"maximum_fraction_digits"):
            ctx.format_number(123.45, maximum_fraction_digits=maximum)

    @given(minimum=st.integers(min_value=101, max_value=10000))
    @example(minimum=101)
    @example(minimum=1000)
    def test_minimum_fraction_digits_exceeds_max_property(self, minimum: int) -> None:
        """format_number() raises ValueError for minimum_fraction_digits > MAX_FORMAT_DIGITS.

        Property: For all n > 100, format_number(x, minimum_fraction_digits=n) raises ValueError.
        """
        ctx = LocaleContext.create("en-US")

        with pytest.raises(ValueError, match=r"minimum_fraction_digits"):
            ctx.format_number(123.45, minimum_fraction_digits=minimum)

    @given(maximum=st.integers(min_value=101, max_value=10000))
    @example(maximum=101)
    @example(maximum=500)
    def test_maximum_fraction_digits_exceeds_max_property(self, maximum: int) -> None:
        """format_number() raises ValueError for maximum_fraction_digits > MAX_FORMAT_DIGITS.

        Property: For all n > 100, format_number(x, maximum_fraction_digits=n) raises ValueError.
        """
        ctx = LocaleContext.create("en-US")

        with pytest.raises(ValueError, match=r"maximum_fraction_digits"):
            ctx.format_number(123.45, maximum_fraction_digits=maximum)


class TestFormatNumberSpecialValues:
    """Test format_number() with special float values (line 435->439)."""

    def test_format_number_positive_infinity(self) -> None:
        """format_number() handles positive infinity without quantization."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(float("inf"))

        # Should format infinity (Babel handles special values)
        assert isinstance(result, str)
        # Common representations: "∞", "inf", "infinity"
        assert len(result) > 0

    def test_format_number_negative_infinity(self) -> None:
        """format_number() handles negative infinity without quantization."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(float("-inf"))

        # Should format negative infinity
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_number_nan(self) -> None:
        """format_number() handles NaN without quantization."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(float("nan"))

        # Should format NaN (Babel handles special values)
        assert isinstance(result, str)
        # Common representations: "NaN", "nan"
        assert len(result) > 0

    @given(
        special_value=st.sampled_from(
            [float("inf"), float("-inf"), float("nan")]
        )
    )
    @example(special_value=float("inf"))
    @example(special_value=float("-inf"))
    @example(special_value=float("nan"))
    def test_format_number_special_values_property(self, special_value: float) -> None:
        """format_number() handles all special float values without crashing.

        Property: For all special values v in {inf, -inf, nan},
        format_number(v) returns a non-empty string without raising exception.
        """
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(special_value)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_number_infinity_with_grouping(self) -> None:
        """format_number() handles infinity with use_grouping parameter."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(float("inf"), use_grouping=False)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_number_nan_with_custom_pattern(self) -> None:
        """format_number() handles NaN with custom pattern."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_number(float("nan"), pattern="#,##0.00")

        assert isinstance(result, str)
        assert len(result) > 0


# ============================================================================
# DateTime Formatting Tests
# ============================================================================


class TestFormatDatetime:
    """Test format_datetime() with various locales and parameters."""

    def test_format_datetime_en_us_short(self) -> None:
        """format_datetime() formats date with short style for en-US."""
        ctx = LocaleContext.create("en-US")
        dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)
        result = ctx.format_datetime(dt, date_style="short")

        assert "10" in result or "27" in result

    def test_format_datetime_de_de_short(self) -> None:
        """format_datetime() formats date with short style for de-DE."""
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
        result = ctx.format_datetime("2025-10-27", date_style="short")

        assert "10" in result or "27" in result

    def test_format_datetime_invalid_string_raises(self) -> None:
        """format_datetime() raises FrozenFluentError for invalid datetime string."""
        ctx = LocaleContext.create("en-US")

        with pytest.raises(FrozenFluentError) as exc_info:
            ctx.format_datetime("not-a-date", date_style="short")

        assert exc_info.value.category == ErrorCategory.FORMATTING
        assert "not ISO 8601 format" in str(exc_info.value)

    def test_format_datetime_with_time_style(self) -> None:
        """format_datetime() formats both date and time when time_style provided."""
        ctx = LocaleContext.create("en-US")
        dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)
        result = ctx.format_datetime(dt, date_style="short", time_style="short")

        assert "10" in result or "27" in result
        assert "14" in result or "2" in result or "30" in result

    def test_format_datetime_string_pattern(self) -> None:
        """format_datetime() handles string datetime_pattern (line 499)."""
        from unittest.mock import patch  # noqa: PLC0415

        ctx = LocaleContext.create("en-US")
        dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)

        # Mock datetime_formats.get to return a string pattern
        with patch.object(ctx.babel_locale.datetime_formats, "get") as mock_get:
            mock_get.return_value = "{1} at {0}"  # String without format() method

            result = ctx.format_datetime(dt, date_style="medium", time_style="short")

            # Should use string's .format() method (line 499)
            assert "at" in result


    def test_format_datetime_error_raises_formatting_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """format_datetime() raises FrozenFluentError with FORMATTING category on Babel error."""
        def mock_format_date(*_args: object, **_kwargs: object) -> None:
            msg = "Mocked format error"
            raise ValueError(msg)

        monkeypatch.setattr(babel_dates, "format_date", mock_format_date)

        ctx = LocaleContext.create("en-US")
        dt = datetime(2025, 10, 27, 14, 30, tzinfo=UTC)

        with pytest.raises(FrozenFluentError) as exc_info:
            ctx.format_datetime(dt, date_style="short")
        assert exc_info.value.category == ErrorCategory.FORMATTING


# ============================================================================
# Currency Formatting Tests
# ============================================================================


class TestFormatCurrency:
    """Test format_currency() with various locales and parameters."""

    def test_format_currency_en_us_symbol(self) -> None:
        """format_currency() formats with symbol for en-US."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_currency(123.45, currency="EUR")

        assert "123" in result

    def test_format_currency_lv_lv_symbol(self) -> None:
        """format_currency() formats with symbol for lv-LV."""
        ctx = LocaleContext.create("lv-LV")
        result = ctx.format_currency(123.45, currency="EUR")

        assert "123" in result

    def test_format_currency_code_display(self) -> None:
        """format_currency() displays currency code when requested (lines 604-616)."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_currency(123.45, currency="USD", currency_display="code")

        # Should use ISO code instead of symbol (line 607-616)
        assert "USD" in result
        assert "123.45" in result

    def test_format_currency_name_display(self) -> None:
        """format_currency() displays currency name when requested."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_currency(123.45, currency="USD", currency_display="name")

        assert isinstance(result, str)

    def test_format_currency_custom_pattern(self) -> None:
        """format_currency() respects custom pattern."""
        ctx = LocaleContext.create("en-US")
        result = ctx.format_currency(1234.56, currency="USD", pattern="#,##0.00 ¤")

        assert "1,234.56" in result or "1234.56" in result


    def test_format_currency_error_raises_formatting_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """format_currency() raises FrozenFluentError with FORMATTING category on Babel error."""
        def mock_format_currency(*_args: object, **_kwargs: object) -> None:
            msg = "Mocked format error"
            raise ValueError(msg)

        monkeypatch.setattr(babel_numbers, "format_currency", mock_format_currency)

        ctx = LocaleContext.create("en-US")
        with pytest.raises(FrozenFluentError) as exc_info:
            ctx.format_currency(123.45, currency="USD")

        assert exc_info.value.category == ErrorCategory.FORMATTING
        assert "USD 123.45" in exc_info.value.fallback_value


# ============================================================================
# Internal Helper Tests
# ============================================================================


class TestGetIsoCodePattern:
    """Test _get_iso_code_pattern() internal helper."""

    def test_get_iso_code_pattern_returns_string_or_none(self) -> None:
        """_get_iso_code_pattern() returns string or None."""
        ctx = LocaleContext.create("en-US")
        result = ctx._get_iso_code_pattern()

        assert result is None or isinstance(result, str)

    def test_get_iso_code_pattern_doubles_currency_sign(self) -> None:
        """_get_iso_code_pattern() doubles currency sign per CLDR spec."""
        ctx = LocaleContext.create("en-US")
        result = ctx._get_iso_code_pattern()

        if result is not None:
            assert "\xa4\xa4" in result or "\xa4" not in result

    def test_get_iso_code_pattern_none_when_no_standard(self) -> None:
        """_get_iso_code_pattern() returns None when standard pattern missing (line 653)."""
        ctx = LocaleContext.create("en-US")

        # Mock currency_formats to return None for standard
        mock_formats: dict[str, None] = {"standard": None}
        mock_locale = MagicMock()
        type(mock_locale).currency_formats = PropertyMock(return_value=mock_formats)

        # Use object.__setattr__ to bypass frozen dataclass restriction
        original_locale = ctx._babel_locale
        object.__setattr__(ctx, "_babel_locale", mock_locale)

        try:
            result = ctx._get_iso_code_pattern()
            assert result is None
        finally:
            object.__setattr__(ctx, "_babel_locale", original_locale)

    def test_get_iso_code_pattern_none_when_no_pattern_attribute(self) -> None:
        """_get_iso_code_pattern() returns None when pattern attribute missing (line 653)."""
        ctx = LocaleContext.create("en-US")

        # Mock standard pattern without pattern attribute
        mock_pattern = MagicMock(spec=[])  # spec=[] means no attributes
        mock_formats = {"standard": mock_pattern}
        mock_locale = MagicMock()
        type(mock_locale).currency_formats = PropertyMock(return_value=mock_formats)

        # Use object.__setattr__ to bypass frozen dataclass restriction
        original_locale = ctx._babel_locale
        object.__setattr__(ctx, "_babel_locale", mock_locale)

        try:
            result = ctx._get_iso_code_pattern()
            assert result is None
        finally:
            object.__setattr__(ctx, "_babel_locale", original_locale)

    def test_get_iso_code_pattern_none_when_no_currency_placeholder(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """_get_iso_code_pattern() returns None and logs debug when no placeholder."""
        ctx = LocaleContext.create("en-US")

        # Mock standard pattern without currency placeholder
        mock_pattern = MagicMock()
        mock_pattern.pattern = "#,##0.00"  # No ¤ placeholder
        mock_formats = {"standard": mock_pattern}
        mock_locale = MagicMock()
        type(mock_locale).currency_formats = PropertyMock(return_value=mock_formats)

        # Use object.__setattr__ to bypass frozen dataclass restriction
        original_locale = ctx._babel_locale
        object.__setattr__(ctx, "_babel_locale", mock_locale)

        try:
            with caplog.at_level(logging.DEBUG):
                result = ctx._get_iso_code_pattern()

            assert result is None
            assert any("lacks placeholder" in record.message for record in caplog.records)
        finally:
            object.__setattr__(ctx, "_babel_locale", original_locale)
