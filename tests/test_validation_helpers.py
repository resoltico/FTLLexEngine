"""Tests for syntax/validation_helpers.py shared validation logic.

Verifies count_default_variants helper used by serializer and validator.

Python 3.13+.
"""


from ftllexengine.syntax.ast import (
    Identifier,
    NumberLiteral,
    Pattern,
    SelectExpression,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.validation_helpers import count_default_variants


class TestCountDefaultVariants:
    """Test count_default_variants() helper function."""

    def test_count_zero_when_no_default(self):
        """count_default_variants returns 0 when no default variant."""
        # Create select with no default variants
        variants = [
            Variant(key=Identifier("one"), value=Pattern(elements=()), default=False),
            Variant(key=Identifier("two"), value=Pattern(elements=()), default=False),
        ]
        expr = SelectExpression(
            selector=VariableReference(id=Identifier("count")),
            variants=tuple(variants),
        )

        assert count_default_variants(expr) == 0

    def test_count_one_when_single_default(self):
        """count_default_variants returns 1 when one default variant."""
        variants = [
            Variant(key=Identifier("one"), value=Pattern(elements=()), default=False),
            Variant(key=Identifier("other"), value=Pattern(elements=()), default=True),
        ]
        expr = SelectExpression(
            selector=VariableReference(id=Identifier("count")),
            variants=tuple(variants),
        )

        assert count_default_variants(expr) == 1

    def test_count_multiple_when_duplicate_defaults(self):
        """count_default_variants returns count when multiple defaults (invalid FTL)."""
        variants = [
            Variant(key=Identifier("one"), value=Pattern(elements=()), default=True),
            Variant(key=Identifier("other"), value=Pattern(elements=()), default=True),
            Variant(key=Identifier("few"), value=Pattern(elements=()), default=True),
        ]
        expr = SelectExpression(
            selector=VariableReference(id=Identifier("count")),
            variants=tuple(variants),
        )

        assert count_default_variants(expr) == 3

    def test_count_with_empty_variants(self):
        """count_default_variants returns 0 when no variants."""
        expr = SelectExpression(
            selector=VariableReference(id=Identifier("count")),
            variants=(),
        )

        assert count_default_variants(expr) == 0

    def test_count_mixed_default_status(self):
        """count_default_variants correctly counts in mixed scenarios."""
        variants = [
            Variant(key=Identifier("one"), value=Pattern(elements=()), default=False),
            Variant(key=Identifier("two"), value=Pattern(elements=()), default=False),
            Variant(
                key=NumberLiteral(value=42, raw="42"), value=Pattern(elements=()), default=False
            ),
            Variant(key=Identifier("other"), value=Pattern(elements=()), default=True),
        ]
        expr = SelectExpression(
            selector=VariableReference(id=Identifier("count")),
            variants=tuple(variants),
        )

        assert count_default_variants(expr) == 1
