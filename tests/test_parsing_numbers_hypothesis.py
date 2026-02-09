"""Hypothesis-based property tests for number parsing.

Functions return tuple[value, errors]:
- parse_number() returns tuple[float | None, tuple[FluentParseError, ...]]
- parse_decimal() returns tuple[Decimal | None, tuple[FluentParseError, ...]]
- Functions never raise exceptions; errors returned in tuple

Focus on precision, locale independence, and roundtrip properties.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.parsing import parse_decimal, parse_number


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
