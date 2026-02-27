"""Tests for runtime.functions formatting precision and error handling.

Covers _compute_visible_precision with max_fraction_digits capping,
exception handling in number_format and currency_format for malformed patterns,
and is_builtin_with_locale_requirement function.
- get_shared_registry and _create_shared_registry functions
- FluentBundle functions parameter validation (dict rejection)
- NaN/Infinity graceful handling in plural category selection

Property-based tests using Hypothesis for edge cases and invariants.
"""

from collections import OrderedDict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal, cast
from unittest.mock import MagicMock, patch

import pytest
from babel.numbers import NumberPattern
from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.function_bridge import FluentNumber
from ftllexengine.runtime.functions import (
    _compute_visible_precision,
    _mark_locale_required,
    create_default_registry,
    currency_format,
    datetime_format,
    get_shared_registry,
    is_builtin_with_locale_requirement,
    number_format,
)
from ftllexengine.runtime.plural_rules import select_plural_category


class TestComputeVisiblePrecisionCapping:
    """Tests for _compute_visible_precision max_fraction_digits capping logic."""

    def test_precision_capped_when_exceeds_max_fraction_digits(self) -> None:
        """Verify precision is capped when digit count exceeds max_fraction_digits.

        This tests line 111: if max_fraction_digits is not None and count > max_fraction_digits.
        """
        # Format: "1.25" has 2 visible fraction digits
        # But max_fraction_digits=1 caps it to 1
        result = _compute_visible_precision("1.25", ".", max_fraction_digits=1)
        assert result == 1

    def test_precision_not_capped_when_within_max_fraction_digits(self) -> None:
        """Verify precision is not capped when within max_fraction_digits."""
        # Format: "1.25" has 2 visible fraction digits
        # max_fraction_digits=3 does not cap it
        result = _compute_visible_precision("1.25", ".", max_fraction_digits=3)
        assert result == 2

    def test_precision_capped_at_exact_max_fraction_digits(self) -> None:
        """Verify precision equals max_fraction_digits when they match."""
        # Format: "1.25" has 2 visible fraction digits
        # max_fraction_digits=2 matches exactly
        result = _compute_visible_precision("1.25", ".", max_fraction_digits=2)
        assert result == 2

    def test_precision_capping_with_trailing_non_digits(self) -> None:
        """Verify capping works with trailing non-digit characters."""
        # Format: "100.00 Dollars 123" has 2 leading fraction digits
        # max_fraction_digits=1 caps to 1
        result = _compute_visible_precision(
            "100.00 Dollars 123", ".", max_fraction_digits=1
        )
        assert result == 1

    def test_precision_capping_with_comma_decimal(self) -> None:
        """Verify capping works with comma decimal separator."""
        # Format: "1,2345" has 4 visible fraction digits
        # max_fraction_digits=2 caps to 2
        result = _compute_visible_precision("1,2345", ",", max_fraction_digits=2)
        assert result == 2

    def test_cap_does_not_inflate(self) -> None:
        """Cap does not inflate precision beyond actual digits."""
        assert _compute_visible_precision("1.2", ".", max_fraction_digits=5) == 1

    def test_zero_max_fraction_digits(self) -> None:
        """max_fraction_digits=0 returns 0 precision."""
        assert _compute_visible_precision("1.25", ".", max_fraction_digits=0) == 0

    def test_no_decimal_point(self) -> None:
        """No decimal point returns 0 regardless of cap."""
        assert _compute_visible_precision("125", ".") == 0
        assert _compute_visible_precision("125", ".", max_fraction_digits=3) == 0

    @given(
        st.integers(min_value=1, max_value=10),
        st.integers(min_value=0, max_value=5),
    )
    def test_precision_capping_property_always_within_max(
        self, digit_count: int, max_frac: int
    ) -> None:
        """Property: returned precision never exceeds max_fraction_digits."""
        capped = digit_count > max_frac
        event(f"outcome={'capped' if capped else 'within'}")
        # Create formatted string with digit_count fraction digits
        formatted = "1." + "0" * digit_count
        result = _compute_visible_precision(formatted, ".", max_fraction_digits=max_frac)
        assert result <= max_frac

    @given(frac_digits=st.integers(min_value=0, max_value=20))
    def test_result_never_exceeds_actual_digits(self, frac_digits: int) -> None:
        """Result never exceeds actual fraction digit count."""
        event(f"frac_digits={frac_digits}")
        formatted = "1." + "0" * frac_digits if frac_digits > 0 else "1"
        result = _compute_visible_precision(
            formatted, ".", max_fraction_digits=100
        )
        assert result <= frac_digits


class TestNumberFormatPatternExceptionHandling:
    """Tests for number_format pattern parsing exception handling.

    Tests lines 205-209: Exception handling when parse_pattern fails during
    max_frac extraction (line 202), not during formatting.
    """

    def test_number_format_with_custom_pattern_succeeds(self) -> None:
        """Verify number_format with custom pattern extracts max_frac correctly.

        This tests line 204: max_frac = parsed.frac_prec[1]
        When parse_pattern succeeds, max_frac is extracted and used for precision capping.
        """
        # Use a custom pattern that limits decimals
        result = number_format(
            Decimal("123.456789"),
            "en-US",
            pattern="#,##0.00",  # Pattern with max 2 decimals
        )

        # Should return FluentNumber with formatted value
        assert isinstance(result, FluentNumber)
        assert "123" in str(result)
        # Precision should be capped at 2 (from pattern metadata)
        assert result.precision == 2

    def test_number_format_with_pattern_parse_exception_falls_back(self) -> None:
        """Verify parse_pattern exception during max_frac extraction is handled.

        This tests lines 205-209: Exception handling in number_format.
        The parse_pattern call on line 202 (for extracting max_frac metadata)
        may fail even if formatting succeeds. When it does, the function falls
        back to uncapped precision counting.
        """
        # Create a mock that succeeds for formatting but fails for metadata extraction
        original_parse = __import__("babel.numbers", fromlist=["parse_pattern"]).parse_pattern

        call_count = 0
        error_msg = "Metadata extraction failed"

        def parse_pattern_side_effect(pattern: str) -> NumberPattern:
            nonlocal call_count
            call_count += 1
            # First call (inside format_number in LocaleContext): succeed
            if call_count == 1:
                return original_parse(pattern)
            # Second call (line 202 in functions.py): fail
            raise ValueError(error_msg)

        with patch("babel.numbers.parse_pattern", side_effect=parse_pattern_side_effect):
            # The format should still succeed
            result = number_format(
                Decimal("123.456"),
                "en-US",
                pattern="#,##0.00",
                minimum_fraction_digits=2,
            )

            # Should return FluentNumber with formatted value
            assert isinstance(result, FluentNumber)
            assert "123" in str(result)
            # parse_pattern was called twice (once for format, once for metadata)
            assert call_count == 2

    def test_number_format_pattern_exception_with_various_errors(self) -> None:
        """Verify exception handling works for ValueError and AttributeError."""
        original_parse = __import__("babel.numbers", fromlist=["parse_pattern"]).parse_pattern
        error_msg = "Test error"

        # Test that (ValueError, AttributeError) catch works for documented error types
        for exception_class in (ValueError, AttributeError):
            call_count = 0

            def parse_pattern_side_effect(
                pattern: str,
                exc_class: type[Exception] = exception_class,  # Bind via default arg
            ) -> NumberPattern:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return original_parse(pattern)
                raise exc_class(error_msg)

            with patch("babel.numbers.parse_pattern", side_effect=parse_pattern_side_effect):
                result = number_format(Decimal("100.5"), "en-US", pattern="#,##0.00")

                assert isinstance(result, FluentNumber)
                assert "100" in str(result)

    @given(
        st.decimals(
            allow_nan=False, allow_infinity=False,
            min_value=Decimal("-1000000"), max_value=Decimal("1000000"),
        ),
    )
    def test_number_format_pattern_exception_property(self, value: Decimal) -> None:
        """Property: number_format succeeds even when metadata extraction fails."""
        event(f"value={type(value).__name__}")
        original_parse = __import__("babel.numbers", fromlist=["parse_pattern"]).parse_pattern

        call_count = 0
        error_msg = "Metadata extraction failed"

        def parse_pattern_side_effect(pattern: str) -> NumberPattern:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return original_parse(pattern)
            raise ValueError(error_msg)

        with patch("babel.numbers.parse_pattern", side_effect=parse_pattern_side_effect):
            result = number_format(value, "en-US", pattern="#,##0.00")

            # Should always return FluentNumber
            assert isinstance(result, FluentNumber)
            # Should have formatted string
            assert len(str(result)) > 0


class TestCurrencyFormatPatternExceptionHandling:
    """Tests for currency_format pattern parsing exception handling.

    Tests lines 372-376: Exception handling when parse_pattern fails during
    max_frac extraction (line 373), not during formatting.
    """

    def test_currency_format_with_custom_pattern_succeeds(self) -> None:
        """Verify currency_format with custom pattern extracts max_frac correctly.

        This tests line 374: max_frac = parsed.frac_prec[1]
        When parse_pattern succeeds, max_frac is extracted and used for precision capping.
        """
        # Use a custom pattern that limits decimals
        result = currency_format(
            Decimal("123.456789"),
            "en-US",
            currency="USD",
            pattern="¤ #,##0.00",  # Pattern with max 2 decimals
        )

        # Should return FluentNumber with formatted value
        assert isinstance(result, FluentNumber)
        assert "123" in str(result)
        # Precision should be capped at 2 (from pattern metadata)
        assert result.precision == 2

    def test_currency_format_with_pattern_parse_exception_falls_back(self) -> None:
        """Verify parse_pattern exception during max_frac extraction is handled.

        This tests lines 372-376: Exception handling in currency_format.
        """
        original_parse = __import__("babel.numbers", fromlist=["parse_pattern"]).parse_pattern

        call_count = 0
        error_msg = "Metadata extraction failed"

        def parse_pattern_side_effect(pattern: str) -> NumberPattern:
            nonlocal call_count
            call_count += 1
            # First call (inside format_currency in LocaleContext): succeed
            if call_count == 1:
                return original_parse(pattern)
            # Second call (line 373 in functions.py): fail
            raise ValueError(error_msg)

        with patch("babel.numbers.parse_pattern", side_effect=parse_pattern_side_effect):
            result = currency_format(
                Decimal("100.50"),
                "en-US",
                currency="USD",
                pattern="¤ #,##0.00",
            )

            assert isinstance(result, FluentNumber)
            assert "100" in str(result) or "USD" in str(result)
            assert call_count == 2

    def test_currency_format_pattern_exception_with_various_errors(self) -> None:
        """Verify exception handling works for documented exception types."""
        original_parse = __import__("babel.numbers", fromlist=["parse_pattern"]).parse_pattern
        error_msg = "Test error"

        for exception_class in (ValueError, AttributeError):
            call_count = 0

            def parse_pattern_side_effect(
                pattern: str,
                exc_class: type[Exception] = exception_class,  # Bind via default arg
            ) -> NumberPattern:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return original_parse(pattern)
                raise exc_class(error_msg)

            with patch("babel.numbers.parse_pattern", side_effect=parse_pattern_side_effect):
                result = currency_format(
                    Decimal("50.25"), "en-US", currency="EUR", pattern="¤ #,##0.00"
                )

                assert isinstance(result, FluentNumber)
                assert "50" in str(result) or "EUR" in str(result)

    @given(
        st.decimals(
            allow_nan=False, allow_infinity=False,
            min_value=Decimal("0"), max_value=Decimal("1000000"),
        ),
        st.sampled_from(["USD", "EUR", "GBP", "JPY", "CHF", "BHD"]),
    )
    def test_currency_format_pattern_exception_property(
        self, value: Decimal, currency: str
    ) -> None:
        """Property: currency_format succeeds even when metadata extraction fails."""
        event(f"currency={currency}")
        original_parse = __import__("babel.numbers", fromlist=["parse_pattern"]).parse_pattern

        call_count = 0
        error_msg = "Metadata extraction failed"

        def parse_pattern_side_effect(pattern: str) -> NumberPattern:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return original_parse(pattern)
            raise ValueError(error_msg)

        with patch("babel.numbers.parse_pattern", side_effect=parse_pattern_side_effect):
            result = currency_format(
                value, "en-US", currency=currency, pattern="¤ #,##0.00"
            )

            assert isinstance(result, FluentNumber)
            assert len(str(result)) > 0


class TestIsBuiltinWithLocaleRequirement:
    """Tests for is_builtin_with_locale_requirement function.

    Tests line 414: The function body that checks _ftl_requires_locale attribute.
    """

    def test_is_builtin_with_locale_requirement_for_builtin_functions(self) -> None:
        """Verify built-in functions are recognized as requiring locale."""
        # Built-in functions should have _ftl_requires_locale = True
        assert is_builtin_with_locale_requirement(number_format) is True
        assert is_builtin_with_locale_requirement(datetime_format) is True
        assert is_builtin_with_locale_requirement(currency_format) is True

    def test_is_builtin_with_locale_requirement_for_non_builtin(self) -> None:
        """Verify non-built-in functions return False."""

        def custom_function() -> str:
            return "custom"

        assert is_builtin_with_locale_requirement(custom_function) is False

    def test_is_builtin_with_locale_requirement_for_marked_function(self) -> None:
        """Verify functions marked with _mark_locale_required return True."""

        def test_function() -> str:
            return "test"

        # Initially False
        assert is_builtin_with_locale_requirement(test_function) is False

        # Mark it
        _mark_locale_required(test_function)

        # Now True
        assert is_builtin_with_locale_requirement(test_function) is True

    def test_is_builtin_with_locale_requirement_for_non_callable(self) -> None:
        """Verify non-callable objects return False."""
        assert is_builtin_with_locale_requirement("string") is False
        assert is_builtin_with_locale_requirement(42) is False
        assert is_builtin_with_locale_requirement(None) is False
        assert is_builtin_with_locale_requirement([]) is False

    def test_is_builtin_with_locale_requirement_with_mock(self) -> None:
        """Verify function works with mock objects."""
        mock_with_attr = MagicMock()
        mock_with_attr._ftl_requires_locale = True
        assert is_builtin_with_locale_requirement(mock_with_attr) is True

        mock_without_attr = MagicMock()
        del mock_without_attr._ftl_requires_locale
        assert is_builtin_with_locale_requirement(mock_without_attr) is False


class TestSharedRegistryFunctions:
    """Tests for get_shared_registry and _create_shared_registry functions.

    Tests lines 474-476 and 530: Registry singleton creation and retrieval.
    """

    def test_get_shared_registry_returns_frozen_registry(self) -> None:
        """Verify get_shared_registry returns a frozen registry."""
        registry = get_shared_registry()

        # Should be frozen
        assert registry.frozen is True

        # Should have built-in functions
        assert "NUMBER" in registry
        assert "DATETIME" in registry
        assert "CURRENCY" in registry

    def test_get_shared_registry_returns_same_instance(self) -> None:
        """Verify get_shared_registry returns singleton instance."""
        registry1 = get_shared_registry()
        registry2 = get_shared_registry()

        # Should be the same object (singleton pattern via lru_cache)
        assert registry1 is registry2

    def test_get_shared_registry_is_immutable(self) -> None:
        """Verify shared registry cannot be modified."""
        registry = get_shared_registry()

        def custom_func() -> str:
            return "test"

        # Attempting to register should raise TypeError
        with pytest.raises(TypeError, match=r"frozen|immutable"):
            registry.register(custom_func, ftl_name="CUSTOM")

    def test_shared_registry_vs_default_registry_independence(self) -> None:
        """Verify shared registry is independent from create_default_registry."""
        shared = get_shared_registry()
        default = create_default_registry()

        # Shared is frozen, default is not
        assert shared.frozen is True
        assert default.frozen is False

        # Modifying default does not affect shared
        def custom_func() -> str:
            return "custom"

        default.register(custom_func, ftl_name="CUSTOM")

        assert "CUSTOM" in default
        assert "CUSTOM" not in shared

    def test_shared_registry_contains_correct_functions(self) -> None:
        """Verify shared registry has all built-in functions with correct metadata."""
        registry = get_shared_registry()

        # Check NUMBER function
        number_info = registry.get_function_info("NUMBER")
        assert number_info is not None
        assert number_info.python_name == "number_format"
        assert number_info.ftl_name == "NUMBER"

        # Check DATETIME function
        datetime_info = registry.get_function_info("DATETIME")
        assert datetime_info is not None
        assert datetime_info.python_name == "datetime_format"
        assert datetime_info.ftl_name == "DATETIME"

        # Check CURRENCY function
        currency_info = registry.get_function_info("CURRENCY")
        assert currency_info is not None
        assert currency_info.python_name == "currency_format"
        assert currency_info.ftl_name == "CURRENCY"


class TestDatetimeFormatBasic:
    """Basic tests for datetime_format to ensure core paths are covered."""

    def test_datetime_format_basic_date_only(self) -> None:
        """Verify datetime_format with date only works correctly.

        Tests lines 274-275: LocaleContext.create and format_datetime delegation.
        """
        dt = datetime(2025, 1, 28, tzinfo=UTC)
        result = datetime_format(dt, "en-US", date_style="medium")

        assert isinstance(result, str)
        assert len(result) > 0
        # Should contain date elements
        assert "2025" in result or "25" in result

    def test_datetime_format_with_time(self) -> None:
        """Verify datetime_format with both date and time styles."""
        dt = datetime(2025, 1, 28, 14, 30, tzinfo=UTC)
        result = datetime_format(dt, "en-US", date_style="medium", time_style="short")

        assert isinstance(result, str)
        assert len(result) > 0


class TestComprehensiveEdgeCases:
    """Comprehensive property-based tests for edge cases and invariants."""

    @given(
        st.decimals(
            min_value=Decimal("-1e10"),
            max_value=Decimal("1e10"),
            allow_nan=False,
            allow_infinity=False,
        )
    )
    def test_number_format_precision_invariant(self, value: Decimal) -> None:
        """Property: FluentNumber.precision is always non-negative integer."""
        result = number_format(value, "en-US")
        event(f"precision={result.precision}")
        assert isinstance(result.precision, int)
        assert result.precision >= 0

    @given(
        st.decimals(
            min_value=Decimal("0"),
            max_value=Decimal("1e10"),
            allow_nan=False,
            allow_infinity=False,
        ),
        st.sampled_from(["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD"]),
    )
    def test_currency_format_precision_invariant(
        self, value: Decimal, currency: str
    ) -> None:
        """Property: Currency formatting always produces non-negative precision."""
        event(f"currency={currency}")
        result = currency_format(value, "en-US", currency=currency)
        assert isinstance(result.precision, int)
        assert result.precision >= 0

    @given(st.datetimes(timezones=st.just(UTC)))
    def test_datetime_format_always_returns_non_empty_string(
        self, dt: datetime
    ) -> None:
        """Property: datetime_format always returns non-empty string."""
        event(f"year={dt.year}")
        result = datetime_format(dt, "en-US")
        assert isinstance(result, str)
        assert len(result) > 0

    @given(
        st.decimals(
            allow_nan=False, allow_infinity=False,
            min_value=Decimal("-100000000"), max_value=Decimal("100000000"),
        ),
        st.integers(min_value=0, max_value=6),
        st.integers(min_value=0, max_value=6),
    )
    def test_number_format_min_max_fraction_relationship(
        self, value: Decimal, min_frac: int, max_frac: int
    ) -> None:
        """Property: number_format handles min/max fraction digit relationship correctly."""
        # Ensure min <= max
        if min_frac > max_frac:
            min_frac, max_frac = max_frac, min_frac
        same = min_frac == max_frac
        event(f"boundary={'equal' if same else 'range'}_frac")

        result = number_format(
            value,
            "en-US",
            minimum_fraction_digits=min_frac,
            maximum_fraction_digits=max_frac,
        )

        # Should always succeed
        assert isinstance(result, FluentNumber)
        # Precision should be within bounds (precision is always int for our functions)
        assert result.precision is not None
        assert min_frac <= result.precision <= max_frac

    @given(
        st.sampled_from(["en-US", "de-DE", "fr-FR", "ja-JP", "ar-SA", "lv-LV"]),
        st.integers(min_value=0, max_value=1000000),
    )
    def test_number_format_locale_consistency(
        self, locale_code: str, value: int
    ) -> None:
        """Property: number_format produces consistent results for same locale/value."""
        event(f"locale={locale_code}")
        result1 = number_format(value, locale_code)
        result2 = number_format(value, locale_code)

        # Should be identical
        assert str(result1) == str(result2)
        assert result1.precision == result2.precision

    @given(
        st.sampled_from(["USD", "EUR", "GBP", "JPY", "CHF"]),
        st.sampled_from(["symbol", "code", "name"]),
        st.decimals(
            allow_nan=False, allow_infinity=False,
            min_value=Decimal("0"), max_value=Decimal("1000000"),
        ),
    )
    def test_currency_format_display_style_consistency(
        self, currency: str, display: str, value: Decimal
    ) -> None:
        """Property: currency_format with same parameters produces consistent results."""
        event(f"currency={currency}")
        event(f"display={display}")
        # Cast display to correct type for type checker
        display_style = cast(Literal["symbol", "code", "name"], display)

        result1 = currency_format(
            value, "en-US", currency=currency, currency_display=display_style
        )
        result2 = currency_format(
            value, "en-US", currency=currency, currency_display=display_style
        )

        # Should be identical
        assert str(result1) == str(result2)
        assert result1.precision == result2.precision


class TestRegistryIntegrationWithSharedRegistry:
    """Integration tests verifying shared registry behavior in context."""

    def test_multiple_bundles_can_share_registry(self) -> None:
        """Verify multiple bundles can safely share the same frozen registry."""
        shared = get_shared_registry()

        # Simulate multiple bundles using the same registry
        # This would happen in a real application with many locales
        registries = [shared for _ in range(10)]

        # All should be the same object
        for reg in registries:
            assert reg is shared

        # All should have the same functions
        for reg in registries:
            assert "NUMBER" in reg
            assert "DATETIME" in reg
            assert "CURRENCY" in reg

    def test_shared_registry_copy_is_independent(self) -> None:
        """Verify copying shared registry creates independent unfrozen copy."""
        shared = get_shared_registry()
        copy = shared.copy()

        # Copy should not be frozen
        assert copy.frozen is False
        assert shared.frozen is True

        # Copy should have same functions initially
        assert len(copy) == len(shared)

        # Modifying copy doesn't affect shared
        def custom_func() -> str:
            return "custom"

        copy.register(custom_func, ftl_name="CUSTOM")

        assert "CUSTOM" in copy
        assert "CUSTOM" not in shared


class TestDictFunctionsRejected:
    """FluentBundle rejects dict as functions parameter."""

    def test_dict_raises_type_error(self) -> None:
        """Passing a dict for functions raises TypeError at init time."""
        with pytest.raises(TypeError, match="FunctionRegistry"):
            FluentBundle(
                "en_US",
                functions={"UPPER": str.upper},  # type: ignore[arg-type]
            )

    def test_none_functions_accepted(self) -> None:
        """None for functions creates default registry."""
        bundle = FluentBundle("en_US", functions=None)
        assert bundle is not None

    def test_ordered_dict_rejected(self) -> None:
        """OrderedDict also rejected (has .copy() but not FunctionRegistry)."""
        with pytest.raises(TypeError, match="FunctionRegistry"):
            FluentBundle(
                "en_US",
                functions=OrderedDict(),  # type: ignore[arg-type]
            )


class TestNaNPluralHandling:
    """NaN and Infinity values fall through to 'other' plural category."""

    def test_decimal_nan_returns_other(self) -> None:
        """Decimal('NaN') returns 'other' plural category."""
        result = select_plural_category(Decimal("NaN"), "en_US")
        assert result == "other"

    def test_decimal_inf_returns_other(self) -> None:
        """Decimal('Infinity') returns 'other' plural category."""
        result = select_plural_category(Decimal("Infinity"), "en_US")
        assert result == "other"

    def test_decimal_neg_inf_returns_other(self) -> None:
        """Decimal('-Infinity') returns 'other' plural category."""
        result = select_plural_category(Decimal("-Infinity"), "en_US")
        assert result == "other"

    def test_normal_numbers_still_work(self) -> None:
        """Normal numbers still get proper plural categories."""
        assert select_plural_category(1, "en_US") == "one"
        assert select_plural_category(0, "en_US") == "other"
        assert select_plural_category(2, "en_US") == "other"

    def test_nan_in_select_expression(self) -> None:
        """NaN in select expression falls through to default variant."""
        bundle = FluentBundle("en_US")
        bundle.add_resource(
            "msg = { NUMBER($count) ->\n"
            "    [one] one item\n"
            "   *[other] many items\n"
            "}"
        )
        result, _errors = bundle.format_pattern(
            "msg", {"count": Decimal("NaN")}
        )
        assert "many items" in result
