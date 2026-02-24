"""Hypothesis-based property tests for number parsing.

Functions return tuple[value, errors]:
- parse_decimal() returns tuple[Decimal | None, tuple[FluentParseError, ...]]
- Functions never raise exceptions; errors returned in tuple

Focus on precision, locale independence, and roundtrip properties.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import assume, event, given, settings
from hypothesis import strategies as st

from ftllexengine.parsing import parse_decimal

pytestmark = pytest.mark.fuzz


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

        formatted = number_format(value, "en_US")
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

        formatted = number_format(value, locale, minimum_fraction_digits=2)
        parsed, errors = parse_decimal(str(formatted), locale)
        event(f"locale={locale}")
        has_grouping = value >= 1000
        event(f"has_grouping={has_grouping}")

        assert not errors
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

        formatted = number_format(value, "en_US", minimum_fraction_digits=2)
        parsed, errors = parse_decimal(str(formatted), "en_US")
        magnitude = "large" if abs(value) >= 1000 else "small"
        event(f"magnitude={magnitude}")

        assert not errors
        assert parsed == value
        assert parsed is not None
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

        formatted = number_format(value, "en_US", minimum_fraction_digits=3)
        parsed, errors = parse_decimal(str(formatted), "en_US")
        sub_cent = value < Decimal("0.01")
        event(f"sub_cent={sub_cent}")

        assert not errors
        assert parsed == value
        assert parsed is not None
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
            value, locale, use_grouping=True, minimum_fraction_digits=2
        )
        parsed, errors = parse_decimal(str(formatted), locale)
        event(f"locale={locale}")
        magnitude = "large" if value >= 10000 else "medium"
        event(f"magnitude={magnitude}")

        assert not errors
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

        formatted1 = number_format(value, "en_US", minimum_fraction_digits=2)
        parsed1, errors1 = parse_decimal(str(formatted1), "en_US")

        formatted2 = number_format(
            value, "en_US", use_grouping=True, minimum_fraction_digits=2
        )
        parsed2, errors2 = parse_decimal(str(formatted2), "en_US")

        assert not errors1
        assert not errors2
        assert parsed1 == parsed2 == value
        has_grouping = value >= 1000
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

        formatted = number_format(value, "en_US", minimum_fraction_digits=2)

        parsed1, errors1 = parse_decimal(str(formatted), "en_US")
        parsed2, errors2 = parse_decimal(str(formatted), "en_US")
        parsed3, errors3 = parse_decimal(str(formatted), "en_US")

        assert not errors1
        assert not errors2
        assert not errors3
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

        formatted1 = number_format(value, "en_US", minimum_fraction_digits=2)
        parsed1, errors1 = parse_decimal(str(formatted1), "en_US")

        assert not errors1
        assert parsed1 is not None

        formatted2 = number_format(parsed1, "en_US", minimum_fraction_digits=2)
        parsed2, errors2 = parse_decimal(str(formatted2), "en_US")

        assert not errors2
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

        formatted = number_format(value, "en_US", minimum_fraction_digits=2)
        parsed, errors = parse_decimal(str(formatted), "en_US")

        assert not errors
        assert parsed is not None
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
        if thousands_sep == decimal_sep:
            return

        locales = {
            (",", "."): "en_US",
            (".", ","): "de_DE",
            (" ", ","): "fr_FR",
        }

        locale_key = (thousands_sep, decimal_sep)
        if locale_key in locales:
            locale = locales[locale_key]
            from ftllexengine.runtime.functions import number_format

            value = Decimal("1234.56")
            formatted = number_format(
                value, locale, use_grouping=True, minimum_fraction_digits=2
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
                r"[qxz]{2}_[A-Z]{2}",
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
