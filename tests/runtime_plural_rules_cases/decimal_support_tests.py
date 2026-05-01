# mypy: ignore-errors
"""Split test cases from tests/test_runtime_plural_rules.py."""

from tests.runtime_plural_rules_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Decimal Support Tests
# ============================================================================


class TestDecimalSupport:
    """Test Decimal type support in plural category selection."""

    @given(n=st.integers(min_value=0, max_value=1000))
    @example(n=0)
    @example(n=1)
    @example(n=5)
    def test_decimal_matches_integer(self, n: int) -> None:
        """Decimal and integer with same value produce same category.

        Property: For all n in Z, f(n) = f(Decimal(n))
        """
        int_result = select_plural_category(n, "en_US")
        decimal_result = select_plural_category(Decimal(n), "en_US")

        event(f"category={int_result}")
        assert int_result == decimal_result

    def test_decimal_one_is_one(self) -> None:
        """Decimal(1) matches 'one' category in English."""
        result = select_plural_category(Decimal(1), "en_US")
        assert result == "one"

    def test_decimal_zero_is_other(self) -> None:
        """Decimal(0) matches 'other' category in English."""
        result = select_plural_category(Decimal(0), "en_US")
        assert result == "other"

    def test_decimal_fractional_is_other(self) -> None:
        """Decimal fractional values match 'other' category in English."""
        result = select_plural_category(Decimal("1.5"), "en_US")
        assert result == "other"
