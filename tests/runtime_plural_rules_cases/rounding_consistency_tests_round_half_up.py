# mypy: ignore-errors
"""Split test cases from tests/test_runtime_plural_rules.py."""

from tests.runtime_plural_rules_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Rounding Consistency Tests (ROUND_HALF_UP)
# ============================================================================


class TestRoundingConsistency:
    """Tests that plural selection rounding matches formatting rounding.

    Both plural_rules.py and locale_context.py use ROUND_HALF_EVEN (Babel default)
    so that the displayed number and its plural form always agree.
    Half-values (x.5) round to the nearest even digit in both paths.
    """

    def test_half_value_rounds_even_for_plural(self) -> None:
        """2.5 with precision=0 rounds to 2, selecting 'other' in English."""
        # 2.5 -> 2 (ROUND_HALF_EVEN: 2 is even), which is 'other' in English
        result = select_plural_category(Decimal("2.5"), "en_US", precision=0)
        assert result == "other"

    def test_half_value_3_5_rounds_up_for_plural(self) -> None:
        """3.5 with precision=0 rounds to 4, selecting 'other' in English."""
        # 3.5 -> 4 (ROUND_HALF_EVEN: 4 is even)
        result = select_plural_category(Decimal("3.5"), "en_US", precision=0)
        assert result == "other"

    def test_half_value_0_5_rounds_to_zero_for_plural(self) -> None:
        """0.5 with precision=0 rounds to 0, selecting 'other' in English."""
        # 0.5 -> 0 (ROUND_HALF_EVEN: 0 is even), which is 'other' in English
        result = select_plural_category(Decimal("0.5"), "en_US", precision=0)
        assert result == "other"

    def test_half_value_1_5_rounds_up_for_plural(self) -> None:
        """1.5 with precision=0 rounds to 2, selecting 'other' in English."""
        # 1.5 -> 2 (ROUND_HALF_EVEN: 2 is even)
        result = select_plural_category(Decimal("1.5"), "en_US", precision=0)
        assert result == "other"

    def test_rounding_matches_formatting_at_half_values(self) -> None:
        """Verify that Decimal quantization uses ROUND_HALF_EVEN, matching Babel.

        This is the core consistency property: the number displayed to the user
        and the plural category selected must agree on rounding direction.
        """
        from decimal import ROUND_HALF_EVEN

        test_cases = [
            (Decimal("0.5"), 0, Decimal(0)),
            (Decimal("1.5"), 0, Decimal(2)),
            (Decimal("2.5"), 0, Decimal(2)),
            (Decimal("3.5"), 0, Decimal(4)),
            (Decimal("1.005"), 2, Decimal("1.00")),
            (Decimal("1.015"), 2, Decimal("1.02")),
            (Decimal("2.445"), 2, Decimal("2.44")),
        ]

        for value, precision, expected_rounded in test_cases:
            quantizer = Decimal(10) ** -precision
            rounded = value.quantize(quantizer, rounding=ROUND_HALF_EVEN)
            assert rounded == expected_rounded, (
                f"Expected {value} with precision={precision} to round to "
                f"{expected_rounded}, got {rounded}"
            )

    @given(
        n=st.decimals(
            min_value=Decimal(0), max_value=Decimal(100), allow_nan=False, allow_infinity=False
        ),
        precision=st.integers(min_value=0, max_value=4),
    )
    @example(n=Decimal("0.5"), precision=0)
    @example(n=Decimal("2.5"), precision=0)
    @example(n=Decimal("3.5"), precision=0)
    @example(n=Decimal("1.005"), precision=2)
    def test_plural_rounding_direction_property(
        self, n: Decimal, precision: int
    ) -> None:
        """Plural rounding direction matches ROUND_HALF_EVEN for all inputs.

        Property: The Decimal value used for plural selection must equal the
        value obtained by ROUND_HALF_EVEN quantization.
        """
        from decimal import ROUND_HALF_EVEN

        quantizer = Decimal(10) ** -precision
        expected = n.quantize(quantizer, rounding=ROUND_HALF_EVEN)

        # The plural category must correspond to the ROUND_HALF_EVEN result.
        # We verify indirectly: call select_plural_category with precision,
        # then call again with the explicitly-rounded value (no precision).
        category_via_precision = select_plural_category(n, "en_US", precision=precision)
        category_via_rounded = select_plural_category(expected, "en_US")

        event(f"category_via_precision={category_via_precision}")
        event(f"precision={precision}")
        assert category_via_precision == category_via_rounded, (
            f"Rounding mismatch for n={n}, precision={precision}: "
            f"precision path gave '{category_via_precision}', "
            f"explicitly rounded {expected} gave '{category_via_rounded}'"
        )
