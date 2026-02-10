"""Hypothesis-based property tests for number parsing.

Functions return tuple[value, errors]:
- parse_number() returns tuple[float | None, tuple[FluentParseError, ...]]
- parse_decimal() returns tuple[Decimal | None, tuple[FluentParseError, ...]]
- Functions never raise exceptions; errors returned in tuple

Focus on precision, locale independence, and roundtrip properties.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import assume, event, given, settings
from hypothesis import strategies as st

from ftllexengine.parsing import parse_decimal, parse_number

pytestmark = pytest.mark.fuzz


class TestParseNumberHypothesis:
    """Property-based tests for parse_number()."""

    @given(
        value=st.floats(
            min_value=-999999.99,
            max_value=999999.99,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200)
    def test_parse_number_always_returns_float(self, value: float) -> None:
        """parse_number always returns float type."""
        from ftllexengine.runtime.functions import number_format

        formatted = number_format(value, "en_US")
        result, errors = parse_number(str(formatted), "en_US")
        sign = "neg" if value < 0 else "non_neg"
        event(f"value_sign={sign}")

        assert not errors
        assert isinstance(result, float)

    @given(
        value=st.floats(
            min_value=-999999.99,
            max_value=999999.99,
            allow_nan=False,
            allow_infinity=False,
        ),
        locale=st.sampled_from(["en_US", "de_DE", "fr_FR", "lv_LV", "pl_PL", "ja_JP"]),
    )
    @settings(max_examples=200)
    def test_parse_number_roundtrip_preserves_value(
        self, value: float, locale: str
    ) -> None:
        """Roundtrip (format -> parse -> format) preserves numeric value within float precision."""
        from ftllexengine.runtime.functions import number_format

        formatted = number_format(value, locale)
        parsed, errors = parse_number(str(formatted), locale)
        event(f"locale={locale}")
        sign = "neg" if value < 0 else "non_neg"
        event(f"value_sign={sign}")

        assert not errors
        assert parsed is not None
        # Float precision: allow small rounding error
        assert abs(parsed - value) < 0.01

    @given(
        invalid_input=st.one_of(
            st.text(
                alphabet=st.characters(whitelist_categories=["L"]),
                min_size=1,
                max_size=20,
            ).filter(lambda x: x.upper() not in ("NAN", "INFINITY", "INF")),
            st.just("abc"),
            st.just("xyz123"),
            st.just("!@#$%"),
            st.just(""),
        ),
    )
    @settings(max_examples=100)
    def test_parse_number_invalid_returns_error(self, invalid_input: str) -> None:
        """Invalid numbers return error in tuple; function never raises."""
        result, errors = parse_number(invalid_input, "en_US")
        is_empty = len(invalid_input) == 0
        event(f"input_empty={is_empty}")
        assert len(errors) > 0
        assert result is None

    @given(
        value=st.one_of(
            st.integers(),
            st.lists(st.integers()),
            st.dictionaries(st.text(), st.integers()),
        ),
    )
    @settings(max_examples=50)
    def test_parse_number_type_error_returns_error(self, value: object) -> None:
        """Non-string types return error in tuple; function never raises."""
        result, errors = parse_number(value, "en_US")
        event(f"input_type={type(value).__name__}")
        assert len(errors) > 0
        assert result is None


class TestParseDecimalHypothesis:
    """Property-based tests for parse_decimal()."""

    @given(
        value=st.decimals(
            min_value=Decimal("-999999.99"),
            max_value=Decimal("999999.99"),
            places=2,
        ),
    )
    @settings(max_examples=200)
    def test_parse_decimal_always_returns_decimal(self, value: Decimal) -> None:
        """parse_decimal always returns Decimal type."""
        from ftllexengine.runtime.functions import number_format

        formatted = number_format(float(value), "en_US")
        result, errors = parse_decimal(str(formatted), "en_US")
        sign = "neg" if value < 0 else "non_neg"
        event(f"value_sign={sign}")

        assert not errors
        assert isinstance(result, Decimal)

    @given(
        value=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("999999.99"),
            places=2,
        ),
        locale=st.sampled_from(["en_US", "de_DE", "fr_FR", "lv_LV", "pl_PL", "ja_JP"]),
    )
    @settings(max_examples=200)
    def test_parse_decimal_roundtrip_exact_precision(
        self, value: Decimal, locale: str
    ) -> None:
        """Roundtrip preserves exact Decimal precision (critical for financial)."""
        from ftllexengine.runtime.functions import number_format

        formatted = number_format(float(value), locale, minimum_fraction_digits=2)
        parsed, errors = parse_decimal(str(formatted), locale)
        event(f"locale={locale}")
        has_grouping = float(value) >= 1000
        event(f"has_grouping={has_grouping}")

        assert not errors
        # Decimal must preserve exact value
        assert parsed == value

    @given(
        value=st.decimals(
            min_value=Decimal("-999999.99"),
            max_value=Decimal("-0.01"),
            places=2,
        ),
    )
    @settings(max_examples=100)
    def test_parse_decimal_negative_amounts(self, value: Decimal) -> None:
        """Negative decimals parse correctly."""
        from ftllexengine.runtime.functions import number_format

        formatted = number_format(float(value), "en_US", minimum_fraction_digits=2)
        parsed, errors = parse_decimal(str(formatted), "en_US")
        magnitude = "large" if abs(value) >= 1000 else "small"
        event(f"magnitude={magnitude}")

        assert not errors
        assert parsed == value
        assert parsed < 0

    @given(
        value=st.decimals(
            min_value=Decimal("0.001"),
            max_value=Decimal("0.999"),
            places=3,
        ),
    )
    @settings(max_examples=100)
    def test_parse_decimal_fractional_precision(self, value: Decimal) -> None:
        """Sub-unit decimals preserve fractional precision."""
        from ftllexengine.runtime.functions import number_format

        formatted = number_format(float(value), "en_US", minimum_fraction_digits=3)
        parsed, errors = parse_decimal(str(formatted), "en_US")
        sub_cent = value < Decimal("0.01")
        event(f"sub_cent={sub_cent}")

        assert not errors
        assert parsed == value
        assert parsed < Decimal("1.00")

    @given(
        invalid_input=st.one_of(
            st.text(
                alphabet=st.characters(whitelist_categories=["L"]),
                min_size=1,
                max_size=20,
            ).filter(lambda x: x.upper() not in ("NAN", "INFINITY", "INF")),
            st.just("abc"),
            st.just("not-a-number"),
            st.just(""),
        ),
    )
    @settings(max_examples=100)
    def test_parse_decimal_invalid_returns_error(self, invalid_input: str) -> None:
        """Invalid decimals return error in tuple; function never raises."""
        result, errors = parse_decimal(invalid_input, "en_US")
        is_empty = len(invalid_input) == 0
        event(f"input_empty={is_empty}")
        assert len(errors) > 0
        assert result is None

    @given(
        locale=st.sampled_from(["en_US", "de_DE", "fr_FR", "lv_LV", "pl_PL", "ja_JP"]),
        value=st.decimals(
            min_value=Decimal("100.00"),
            max_value=Decimal("999999.99"),
            places=2,
        ),
    )
    @settings(max_examples=100)
    def test_parse_decimal_locale_independence_for_large_numbers(
        self, locale: str, value: Decimal
    ) -> None:
        """Large numbers with grouping parse correctly across locales."""
        from ftllexengine.runtime.functions import number_format

        formatted = number_format(
            float(value), locale, use_grouping=True, minimum_fraction_digits=2
        )
        parsed, errors = parse_decimal(str(formatted), locale)
        event(f"locale={locale}")
        magnitude = "large" if value >= 10000 else "medium"
        event(f"magnitude={magnitude}")

        assert not errors
        # Should handle grouping separators correctly
        assert parsed == value


class TestParsingMetamorphicProperties:
    """Metamorphic properties for number parsing."""

    @given(
        value=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("9999.99"),
            places=2,
        ),
    )
    @settings(max_examples=100)
    def test_parse_order_independence(self, value: Decimal) -> None:
        """Parsing result independent of intermediate formatting steps."""
        from ftllexengine.runtime.functions import number_format

        # Path 1: Direct format -> parse
        formatted1 = number_format(float(value), "en_US", minimum_fraction_digits=2)
        parsed1, errors1 = parse_decimal(str(formatted1), "en_US")

        # Path 2: Format with grouping -> parse
        formatted2 = number_format(
            float(value), "en_US", use_grouping=True, minimum_fraction_digits=2
        )
        parsed2, errors2 = parse_decimal(str(formatted2), "en_US")

        assert not errors1
        assert not errors2
        # Both paths should yield same numeric value
        assert parsed1 == parsed2 == value
        has_grouping = float(value) >= 1000
        event(f"has_grouping={has_grouping}")
        event("outcome=order_independent")

    @given(
        value=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("9999.99"),
            places=2,
        ),
    )
    @settings(max_examples=100)
    def test_parse_idempotence(self, value: Decimal) -> None:
        """Parsing formatted value multiple times yields same result."""
        from ftllexengine.runtime.functions import number_format

        formatted = number_format(float(value), "en_US", minimum_fraction_digits=2)

        # Parse multiple times
        parsed1, errors1 = parse_decimal(str(formatted), "en_US")
        parsed2, errors2 = parse_decimal(str(formatted), "en_US")
        parsed3, errors3 = parse_decimal(str(formatted), "en_US")

        assert not errors1
        assert not errors2
        assert not errors3
        # All results identical
        assert parsed1 == parsed2 == parsed3 == value
        event("outcome=idempotent")

    @given(
        value=st.decimals(
            min_value=Decimal("1.00"),
            max_value=Decimal("999.99"),
            places=2,
        ),
    )
    @settings(max_examples=100)
    def test_parse_format_parse_stability(self, value: Decimal) -> None:
        """parse(format(parse(format(x)))) == parse(format(x))."""
        from ftllexengine.runtime.functions import number_format

        # First cycle
        formatted1 = number_format(float(value), "en_US", minimum_fraction_digits=2)
        parsed1, errors1 = parse_decimal(str(formatted1), "en_US")

        assert not errors1

        # Second cycle
        value2 = float(parsed1) if parsed1 is not None else 0.0
        formatted2 = number_format(value2, "en_US", minimum_fraction_digits=2)
        parsed2, errors2 = parse_decimal(str(formatted2), "en_US")

        assert not errors2
        # Should stabilize
        assert parsed1 == parsed2
        event("outcome=format_parse_stable")

    @given(
        value=st.decimals(
            min_value=Decimal("0.00"),
            max_value=Decimal("0.00"),
        ),
    )
    @settings(max_examples=10)
    def test_parse_zero_handling(self, value: Decimal) -> None:  # noqa: ARG002
        """Zero values parse correctly."""
        result, errors = parse_decimal("0.00", "en_US")
        assert not errors
        assert result == Decimal("0.00")
        event("outcome=zero_parsed")

    @given(
        value=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("999999999999.99"),
            places=2,
        ),
    )
    @settings(max_examples=100)
    def test_parse_very_large_numbers(self, value: Decimal) -> None:
        """Very large numbers parse correctly without loss of precision."""
        from ftllexengine.runtime.functions import number_format

        formatted = number_format(float(value), "en_US", minimum_fraction_digits=2)
        parsed, errors = parse_decimal(str(formatted), "en_US")

        assert not errors
        assert parsed is not None
        # Large numbers must not lose precision
        assert abs(parsed - value) < Decimal("0.01")
        magnitude = "billions" if value >= 1_000_000_000 else "sub_billion"
        event(f"magnitude={magnitude}")

    @given(
        thousands_sep=st.sampled_from([",", ".", " ", "'"]),
        decimal_sep=st.sampled_from([".", ","]),
    )
    @settings(max_examples=50)
    def test_parse_separator_combinations(
        self, thousands_sep: str, decimal_sep: str
    ) -> None:
        """Different separator combinations should be handled correctly."""
        # Skip if separators are the same (invalid)
        if thousands_sep == decimal_sep:
            return

        # This tests locale-specific separator handling
        # Each locale has its own separator conventions
        locales = {
            (",", "."): "en_US",  # 1,234.56
            (".", ","): "de_DE",  # 1.234,56
            (" ", ","): "fr_FR",  # 1 234,56
        }

        locale_key = (thousands_sep, decimal_sep)
        if locale_key in locales:
            locale = locales[locale_key]
            # Test that parse_decimal handles this locale correctly
            from ftllexengine.runtime.functions import number_format

            value = Decimal("1234.56")
            formatted = number_format(
                float(value), locale, use_grouping=True, minimum_fraction_digits=2
            )
            parsed, errors = parse_decimal(str(formatted), locale)

            assert not errors
            assert parsed == value
            event(f"locale={locale}")
        else:
            event("locale=unmapped")


# ============================================================================
# ERROR CONTEXT IMMUTABILITY PROPERTIES
# ============================================================================


class TestErrorContextImmutabilityProperties:
    """Property: Error contexts from parse functions are frozen."""

    @given(
        value=st.text(
            alphabet=st.characters(
                whitelist_categories=["L"],
            ),
            min_size=1,
            max_size=20,
        ).filter(
            lambda x: x.upper()
            not in ("NAN", "INFINITY", "INF")
        ),
    )
    @settings(max_examples=100)
    def test_parse_number_error_context_frozen(
        self, value: str
    ) -> None:
        """Error contexts from parse_number are immutable."""
        from ftllexengine.integrity import (
            ImmutabilityViolationError,
        )

        result, errors = parse_number(value, "en_US")
        assume(result is None and len(errors) > 0)

        error = errors[0]
        assert error.verify_integrity()
        with pytest.raises(ImmutabilityViolationError):
            error._message = "tampered"
        event("outcome=number_error_frozen")

    @given(
        value=st.text(
            alphabet=st.characters(
                whitelist_categories=["L"],
            ),
            min_size=1,
            max_size=20,
        ).filter(
            lambda x: x.upper()
            not in ("NAN", "INFINITY", "INF")
        ),
    )
    @settings(max_examples=100)
    def test_parse_decimal_error_context_frozen(
        self, value: str
    ) -> None:
        """Error contexts from parse_decimal are immutable."""
        from ftllexengine.integrity import (
            ImmutabilityViolationError,
        )

        result, errors = parse_decimal(value, "en_US")
        assume(result is None and len(errors) > 0)

        error = errors[0]
        assert error.verify_integrity()
        with pytest.raises(ImmutabilityViolationError):
            error._message = "tampered"
        event("outcome=decimal_error_frozen")


# ============================================================================
# CROSS-FUNCTION ORACLE PROPERTIES
# ============================================================================


class TestCrossFunctionOracleProperties:
    """Property: parse_number and parse_decimal agree on success/failure."""

    @given(
        value=st.text(min_size=1, max_size=50),
        locale=st.sampled_from(
            ["en_US", "de_DE", "fr_FR", "lv_LV"]
        ),
    )
    @settings(max_examples=200)
    def test_number_decimal_agree_on_parsability(
        self, value: str, locale: str
    ) -> None:
        """If parse_number succeeds, parse_decimal should too."""
        num_result, num_errors = parse_number(value, locale)
        dec_result, dec_errors = parse_decimal(value, locale)

        event(f"locale={locale}")

        if num_result is not None and not num_errors:
            # parse_number succeeded; parse_decimal should too
            assert dec_result is not None
            assert not dec_errors
            event("outcome=both_succeed")
        elif dec_result is not None and not dec_errors:
            # parse_decimal succeeded; parse_number may also
            # (Decimal -> float is always possible)
            event("outcome=decimal_only")
        else:
            event("outcome=both_fail")

    @given(
        value=st.decimals(
            min_value=Decimal("0.01"),
            max_value=Decimal("99999.99"),
            places=2,
        ),
        locale=st.sampled_from(
            ["en_US", "de_DE", "fr_FR", "lv_LV"]
        ),
    )
    @settings(max_examples=200)
    def test_number_decimal_value_agreement(
        self, value: Decimal, locale: str
    ) -> None:
        """Parsed float and Decimal agree on numeric value."""
        from ftllexengine.runtime.functions import (
            number_format,
        )

        formatted = str(number_format(
            float(value),
            locale,
            minimum_fraction_digits=2,
        ))
        num_result, num_errors = parse_number(
            formatted, locale
        )
        dec_result, dec_errors = parse_decimal(
            formatted, locale
        )

        assert not num_errors
        assert not dec_errors
        assert num_result is not None
        assert dec_result is not None
        # float and Decimal should agree within precision
        diff = abs(Decimal(str(num_result)) - dec_result)
        assert diff < Decimal("0.01")
        event(f"locale={locale}")
        event("outcome=values_agree")


# ============================================================================
# INVALID LOCALE ERROR CONTEXT PROPERTIES
# ============================================================================


class TestInvalidLocaleErrorContextProperties:
    """Property: Invalid locale produces correct error context."""

    @given(
        value=st.text(min_size=1, max_size=20),
        locale=st.one_of(
            st.just("xx_INVALID"),
            st.just("zzz_YYY"),
            st.from_regex(
                r"[a-z]{1,3}_[A-Z]{3,5}",
                fullmatch=True,
            ),
        ),
    )
    @settings(max_examples=100)
    def test_parse_number_locale_error_context(
        self, value: str, locale: str
    ) -> None:
        """Invalid locale returns error with correct context."""
        result, errors = parse_number(value, locale)
        assert result is None
        assert len(errors) >= 1

        error = errors[0]
        assert error.context is not None
        assert error.context.locale_code == locale
        assert error.context.input_value == value
        assert error.context.parse_type == "number"
        event(f"locale={locale}")
        event("outcome=locale_context_correct")

    @given(
        value=st.text(min_size=1, max_size=20),
        locale=st.one_of(
            st.just("xx_INVALID"),
            st.just("zzz_YYY"),
            st.from_regex(
                r"[a-z]{1,3}_[A-Z]{3,5}",
                fullmatch=True,
            ),
        ),
    )
    @settings(max_examples=100)
    def test_parse_decimal_locale_error_context(
        self, value: str, locale: str
    ) -> None:
        """Invalid locale returns error with correct context."""
        result, errors = parse_decimal(value, locale)
        assert result is None
        assert len(errors) >= 1

        error = errors[0]
        assert error.context is not None
        assert error.context.locale_code == locale
        assert error.context.input_value == value
        assert error.context.parse_type == "decimal"
        event(f"locale={locale}")
        event("outcome=locale_context_correct")
