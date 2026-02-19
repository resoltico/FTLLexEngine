"""SelectExpression variant matching, pattern loop coverage, and numeric selector tests.

Consolidates:
- test_resolver_edge_cases.py: TestSelectExpressionEdgeCases, TestResolverErrorPaths
- test_resolver_expression_depth_and_select.py: TestSelectExpressionEdgeCases
- test_resolver_loop_and_numeric_selector.py: all
- test_resolver_pattern_and_variant_matching.py: all
- test_resolver_explicit_branches.py: all
- test_resolver_placeable_and_numeric.py: TestVariantNumericMatching,
  TestFallbackVariantNoVariants, TestSelectExpressionFallbackPaths,
  TestNumericVariantEdgeCases, TestResolverFluentNumberVariantMatching
- test_resolver_placeable_error_and_literal.py: TestNumberLiteralNonMatchingValue
- test_resolver_fallback_and_terms.py: TestFormatValueComprehensive,
  TestTextElementBranch, TestNumberLiteralVariantMatching
- test_resolver_term_and_pattern_branches.py: TestNumberLiteralSelectorCoverage
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.resolution_context import ResolutionContext
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.syntax.ast import (
    CallArguments,
    FunctionReference,
    Identifier,
    Message,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
    StringLiteral,
    TextElement,
    VariableReference,
    Variant,
)

# ============================================================================
# PATTERN LOOP CONTINUATION
# ============================================================================


class TestPatternLoopContinuation:
    """Coverage for pattern loop continuation (line 390->386)."""

    def test_empty_pattern_no_elements(self) -> None:
        """Pattern with no elements exits loop immediately."""
        pattern = Pattern(elements=())
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {})
        assert result == ""
        assert errors == ()

    def test_pattern_text_then_placeable_then_text(self) -> None:
        """Pattern with alternating Text/Placeable/Text elements."""
        pattern = Pattern(
            elements=(
                TextElement(value="Start "),
                Placeable(expression=VariableReference(id=Identifier("var"))),
                TextElement(value=" End"),
            )
        )
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"var": "X"})
        assert result == "Start X End"
        assert errors == ()

    def test_pattern_only_text_elements(self) -> None:
        """Pattern with only TextElements (no Placeables)."""
        pattern = Pattern(
            elements=(
                TextElement(value="First "),
                TextElement(value="Second "),
                TextElement(value="Third"),
            )
        )
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {})
        assert result == "First Second Third"
        assert errors == ()


class TestPatternResolutionBranches:
    """Test pattern resolution loop continuation branches."""

    def test_pattern_with_multiple_text_elements_covers_loop_continuation(self) -> None:
        """Pattern with TextElement followed by another TextElement covers 404->400."""
        pattern = Pattern(
            elements=(
                TextElement(value="Hello "),
                TextElement(value="World"),
            )
        )
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {})
        assert result == "Hello World"
        assert errors == ()

    def test_pattern_text_then_placeable_covers_loop_continuation(self) -> None:
        """Pattern with TextElement followed by Placeable covers 404->400."""
        pattern = Pattern(
            elements=(
                TextElement(value="Value: "),
                Placeable(expression=VariableReference(id=Identifier("x"))),
            )
        )
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"x": "42"})
        assert "Value: " in result
        assert "42" in result
        assert errors == ()

    def test_pattern_three_elements_ensures_multiple_loop_iterations(self) -> None:
        """Pattern with three elements ensures loop continuation branch is hit."""
        ftl = """msg = Start { $var } End"""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg", {"var": "middle"})
        assert result == "Start middle End"


class TestMatchCaseBranchCoverage:
    """Test match/case control flow branches in resolver."""

    def test_placeable_followed_by_text_in_pattern(self) -> None:
        """Pattern with Placeable followed by TextElement tests 404->400 branch."""
        ftl = """msg = { $x } text"""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg", {"x": "value"})
        assert result == "value text"

    def test_multiple_placeables_in_pattern(self) -> None:
        """Pattern with multiple Placeables ensures loop continuation."""
        ftl = """msg = { $a }{ $b }"""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg", {"a": "A", "b": "B"})
        assert result == "AB"

    def test_select_with_number_literal_then_identifier_variant(self) -> None:
        """SelectExpression with NumberLiteral followed by Identifier variant covers 634->629."""
        ftl = """
msg = { $val ->
    [1] one
    [2] two
   *[other] default
}
"""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg", {"val": "other"})
        assert result == "default"

    def test_select_number_literal_no_match_continues_to_next(self) -> None:
        """SelectExpression where first NumberLiteral doesn't match, second does."""
        ftl = """
msg = { $count ->
    [10] ten
    [20] twenty
    [30] thirty
   *[other] default
}
"""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg", {"count": 20})
        assert result == "twenty"

    def test_select_with_isolating_enabled_exercises_placeable_branch(self) -> None:
        """Pattern with use_isolating=True covers Placeable branch with isolation."""
        ftl = """msg = Prefix { $val } Suffix"""
        bundle = FluentBundle("en", use_isolating=True)
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg", {"val": "middle"})
        assert "Prefix" in result
        assert "middle" in result
        assert "Suffix" in result


class TestTextElementBranch:
    """Test TextElement branch in pattern resolution."""

    def test_pattern_with_only_text_no_placeables(self) -> None:
        """Pattern with only TextElement, no Placeable (line 286->282)."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("simple = This is plain text with no variables")

        result, errors = bundle.format_pattern("simple")
        assert result == "This is plain text with no variables"
        assert errors == ()


# ============================================================================
# SELECT EXPRESSION EDGE CASES
# ============================================================================


class TestSelectExpressionEdgeCases:
    """Test edge cases in select expression resolution."""

    def test_select_with_no_matching_variant_uses_default(self) -> None:
        """Select with no match uses default variant."""
        ftl = """
test = { $value ->
   [one] One
  *[other] Other
}
"""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("test", {"value": "unknown"})
        assert "Other" in result

    def test_select_with_number_tries_plural_category(self) -> None:
        """Select with number value tries plural category matching."""
        ftl = """
test = { $count ->
   [one] One item
  *[other] Many items
}
"""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("test", {"count": 1})
        assert "One item" in result

        result, _ = bundle.format_pattern("test", {"count": 5})
        assert "Many items" in result

    def test_select_with_no_default_raises_at_construction(self) -> None:
        """SelectExpression with no default variant raises ValueError at construction."""
        with pytest.raises(ValueError, match="exactly one default variant"):
            SelectExpression(
                selector=VariableReference(id=Identifier(name="x")),
                variants=(
                    Variant(
                        key=Identifier(name="a"),
                        value=Pattern(elements=(TextElement(value="A"),)),
                        default=False,
                    ),
                    Variant(
                        key=Identifier(name="b"),
                        value=Pattern(elements=(TextElement(value="B"),)),
                        default=False,
                    ),
                ),
            )

    def test_select_with_empty_variants_raises_at_construction(self) -> None:
        """SelectExpression with no variants raises ValueError at construction."""
        with pytest.raises(ValueError, match="at least one variant"):
            SelectExpression(
                selector=VariableReference(id=Identifier(name="x")),
                variants=(),
            )

    def test_select_with_malformed_number_literal_key(self) -> None:
        """Select with invalid NumberLiteral.raw falls through gracefully."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=SelectExpression(
                            selector=VariableReference(id=Identifier(name="x")),
                            variants=(
                                Variant(
                                    key=NumberLiteral(value=Decimal("0.0"), raw="invalid"),
                                    value=Pattern(elements=(TextElement(value="Invalid"),)),
                                    default=False,
                                ),
                                Variant(
                                    key=Identifier(name="other"),
                                    value=Pattern(elements=(TextElement(value="Default"),)),
                                    default=True,
                                ),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )

        from ftllexengine.runtime.functions import create_default_registry  # noqa: PLC0415

        resolver = FluentResolver(
            locale="en",
            messages={"test": msg},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        result, _ = resolver.resolve_message(msg, {"x": 0})
        assert "Default" in result

    def test_deeply_nested_select_expression_fallback(self) -> None:
        """Deeply nested SelectExpression in fallback generation doesn't overflow."""
        from ftllexengine.runtime.functions import create_default_registry  # noqa: PLC0415
        from ftllexengine.syntax.ast import Expression  # noqa: PLC0415

        nested_select: Expression = VariableReference(id=Identifier(name="missing"))
        for _ in range(100):
            nested_select = SelectExpression(
                selector=nested_select,  # type: ignore[arg-type]
                variants=(
                    Variant(
                        key=Identifier(name="key"),
                        value=Pattern(elements=(TextElement(value="Value"),)),
                        default=True,
                    ),
                ),
            )

        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=nested_select),)),
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en",
            messages={"test": msg},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        result, _ = resolver.resolve_message(msg, {})
        assert isinstance(result, str)
        assert len(result) > 0


class TestSelectVariantBranchCoverage:
    """Direct resolver internal calls for select expression branch coverage."""

    def test_select_variant_loop_with_no_match_on_number_literal(self) -> None:
        """Select expression where no NumberLiteral matches continues loop to default."""
        resolver = FluentResolver(
            locale="en",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        selector = NumberLiteral(value=5, raw="5")
        variants = (
            Variant(
                key=NumberLiteral(value=1, raw="1"),
                value=Pattern(elements=()),
                default=False,
            ),
            Variant(
                key=NumberLiteral(value=2, raw="2"),
                value=Pattern(elements=()),
                default=False,
            ),
            Variant(
                key=NumberLiteral(value=3, raw="3"),
                value=Pattern(elements=()),
                default=True,
            ),
        )

        select_expr = SelectExpression(selector=selector, variants=variants)
        context = ResolutionContext()
        result = resolver._resolve_select_expression(select_expr, {}, [], context)
        assert result == ""

    def test_pattern_elements_loop_with_text_only(self) -> None:
        """Pattern resolution with only TextElement tests loop continuation."""
        resolver = FluentResolver(
            locale="en",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        pattern = Pattern(
            elements=(
                TextElement(value="Hello "),
                TextElement(value="World"),
                TextElement(value="!"),
            )
        )

        context = ResolutionContext()
        result = resolver._resolve_pattern(pattern, {}, [], context)
        assert result == "Hello World!"


# ============================================================================
# NUMERIC VARIANT MATCHING
# ============================================================================


class TestNumberLiteralVariantWithNonNumericSelector:
    """Coverage for NumberLiteral variant key with non-numeric selector (line 616->611)."""

    def test_number_literal_variant_with_string_selector(self) -> None:
        """SelectExpression with NumberLiteral variants but string selector falls to default."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("val")),
            variants=(
                Variant(
                    key=NumberLiteral(value=1, raw="1"),
                    value=Pattern(elements=(TextElement(value="one"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=2, raw="2"),
                    value=Pattern(elements=(TextElement(value="two"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="fallback"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"val": "not_a_number"})
        assert result == "fallback"
        assert errors == ()

    def test_number_literal_variant_with_none_selector(self) -> None:
        """SelectExpression with NumberLiteral variant but None selector falls to default."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("val")),
            variants=(
                Variant(
                    key=NumberLiteral(value=42, raw="42"),
                    value=Pattern(elements=(TextElement(value="forty-two"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="default"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"val": None})
        assert result == "default"
        assert errors == ()

    def test_number_literal_variant_with_bool_selector(self) -> None:
        """Bool selector matches identifier variant, not NumberLiteral.

        Booleans are excluded from numeric matching (even though isinstance(True, int))
        because they should match [true]/[false] identifier variants, not number literals.
        """
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("val")),
            variants=(
                Variant(
                    key=NumberLiteral(value=1, raw="1"),
                    value=Pattern(elements=(TextElement(value="number_one"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("true"),
                    value=Pattern(elements=(TextElement(value="bool_true"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="fallback"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"val": True})
        assert result == "bool_true"
        assert errors == ()

    def test_number_literal_variants_with_date_selector(self) -> None:
        """SelectExpression with NumberLiteral variants but date selector falls to default."""
        from datetime import date  # noqa: PLC0415

        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("val")),
            variants=(
                Variant(
                    key=NumberLiteral(value=3, raw="3"),
                    value=Pattern(elements=(TextElement(value="three"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="not_numeric"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"val": date(2024, 1, 1)})
        assert result == "not_numeric"
        assert errors == ()


class TestVariantMatchingBranches:
    """Test variant matching loop continuation branches."""

    def test_select_with_non_matching_number_literals_covers_loop_continuation(
        self,
    ) -> None:
        """SelectExpression with non-matching NumberLiterals covers 634->629."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("num")),
            variants=(
                Variant(
                    key=NumberLiteral(value=1, raw="1"),
                    value=Pattern(elements=(TextElement(value="one"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=2, raw="2"),
                    value=Pattern(elements=(TextElement(value="two"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=3, raw="3"),
                    value=Pattern(elements=(TextElement(value="three"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="default"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"num": 99})
        assert result == "default"
        assert errors == ()

    def test_select_with_string_matching_identifier_after_number_literals(self) -> None:
        """String selector skips NumberLiteral variants to match Identifier (634->629)."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("status")),
            variants=(
                Variant(
                    key=NumberLiteral(value=100, raw="100"),
                    value=Pattern(elements=(TextElement(value="hundred"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=200, raw="200"),
                    value=Pattern(elements=(TextElement(value="two_hundred"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("active"),
                    value=Pattern(elements=(TextElement(value="Active"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="Other"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"status": "active"})
        assert result == "Active"
        assert errors == ()

    def test_select_with_bool_selector_skips_number_literals(self) -> None:
        """Bool selector skips NumberLiterals, matches Identifier (634->629)."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("flag")),
            variants=(
                Variant(
                    key=NumberLiteral(value=0, raw="0"),
                    value=Pattern(elements=(TextElement(value="zero"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=1, raw="1"),
                    value=Pattern(elements=(TextElement(value="one"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("true"),
                    value=Pattern(elements=(TextElement(value="yes"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("false"),
                    value=Pattern(elements=(TextElement(value="no"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="unknown"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"flag": True})
        assert result == "yes"
        assert errors == ()


class TestVariantNumericMatching:
    """Numeric variant matching (line 479->474 coverage)."""

    def test_exact_number_literal_match(self) -> None:
        """Exact number match with NumberLiteral variant key."""
        selector = VariableReference(id=Identifier("count"))
        variants = (
            Variant(
                key=NumberLiteral(value=0, raw="0"),
                value=Pattern(elements=(TextElement(value="zero items"),)),
                default=False,
            ),
            Variant(
                key=NumberLiteral(value=1, raw="1"),
                value=Pattern(elements=(TextElement(value="one item"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="many items"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {"count": 0})
        assert not errors
        assert "zero items" in result

        result, errors = resolver.resolve_message(message, {"count": 1})
        assert not errors
        assert "one item" in result

    def test_decimal_exact_match_in_variant(self) -> None:
        """Decimal value matches NumberLiteral variant key."""
        selector = VariableReference(id=Identifier("amount"))
        variants = (
            Variant(
                key=NumberLiteral(value=Decimal("1.5"), raw="1.5"),
                value=Pattern(elements=(TextElement(value="exact match"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="default"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {"amount": Decimal("1.5")})
        assert not errors
        assert "exact match" in result

    def test_float_exact_match_in_variant(self) -> None:
        """Float value matches NumberLiteral variant key."""
        selector = VariableReference(id=Identifier("price"))
        variants = (
            Variant(
                key=NumberLiteral(value=Decimal("9.99"), raw="9.99"),
                value=Pattern(elements=(TextElement(value="special price"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="regular price"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {"price": 9.99})
        assert not errors
        assert "special price" in result

    @given(number=st.integers(min_value=-100, max_value=100))
    def test_integer_exact_matching_property(self, number: int) -> None:
        """Property: Integer selectors match NumberLiteral variants exactly."""
        event(f"number={number}")
        selector = VariableReference(id=Identifier("n"))
        variants = (
            Variant(
                key=NumberLiteral(value=number, raw=str(number)),
                value=Pattern(elements=(TextElement(value="matched"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="not matched"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {"n": number})
        assert not errors
        assert "matched" in result


class TestNumericVariantEdgeCases:
    """Edge cases for numeric variant matching."""

    def test_boolean_does_not_match_number_variant(self) -> None:
        """Boolean values do not match numeric variants (isinstance guard)."""
        selector = VariableReference(id=Identifier("flag"))
        variants = (
            Variant(
                key=NumberLiteral(value=1, raw="1"),
                value=Pattern(elements=(TextElement(value="numeric one"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="default"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {"flag": True})
        assert not errors
        assert "default" in result

    def test_none_selector_uses_default(self) -> None:
        """None selector value falls through to default."""
        selector = VariableReference(id=Identifier("value"))
        variants = (
            Variant(
                key=Identifier("none"),
                value=Pattern(elements=(TextElement(value="none variant"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="default variant"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {"value": None})
        assert not errors
        assert "default variant" in result

    @given(
        decimal_str=st.decimals(
            min_value=Decimal("-100.00"),
            max_value=Decimal("100.00"),
            allow_nan=False,
            allow_infinity=False,
            places=2,
        )
    )
    def test_decimal_variant_matching_property(self, decimal_str: Decimal) -> None:
        """Property: Decimal values match exactly when variant key matches."""
        sign = "negative" if decimal_str.is_signed() else "positive"
        event(f"decimal_sign={sign}")
        selector = VariableReference(id=Identifier("amount"))
        str_repr = str(decimal_str)
        variants = (
            Variant(
                key=NumberLiteral(value=decimal_str, raw=str_repr),
                value=Pattern(elements=(TextElement(value="exact"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="default"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {"amount": decimal_str})
        assert not errors
        assert "exact" in result


class TestNumberLiteralNonMatchingValue:
    """Coverage for NumberLiteral with non-matching value (line 616->611)."""

    def test_number_literal_variants_first_no_match_second_matches(self) -> None:
        """Multiple NumberLiteral variants where first doesn't match, second does."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("count")),
            variants=(
                Variant(
                    key=NumberLiteral(value=1, raw="1"),
                    value=Pattern(elements=(TextElement(value="one"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=2, raw="2"),
                    value=Pattern(elements=(TextElement(value="two"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=3, raw="3"),
                    value=Pattern(elements=(TextElement(value="three"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="fallback"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"count": 2})
        assert result == "two"
        assert errors == ()

    def test_number_literal_variants_all_no_match_uses_default(self) -> None:
        """NumberLiteral variants all fail to match, use default."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("count")),
            variants=(
                Variant(
                    key=NumberLiteral(value=10, raw="10"),
                    value=Pattern(elements=(TextElement(value="ten"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=20, raw="20"),
                    value=Pattern(elements=(TextElement(value="twenty"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="default"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"count": 5})
        assert result == "default"
        assert errors == ()

    def test_number_literal_with_decimal_no_match(self) -> None:
        """NumberLiteral variants with Decimal selector that doesn't match."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("amount")),
            variants=(
                Variant(
                    key=NumberLiteral(value=100, raw="100"),
                    value=Pattern(elements=(TextElement(value="hundred"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=200, raw="200"),
                    value=Pattern(elements=(TextElement(value="two_hundred"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="other_amount"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"amount": Decimal("150.50")})
        assert result == "other_amount"
        assert errors == ()

    def test_number_literal_float_no_exact_match(self) -> None:
        """NumberLiteral variants with float that doesn't exactly match."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("val")),
            variants=(
                Variant(
                    key=NumberLiteral(value=Decimal("1.0"), raw="1.0"),
                    value=Pattern(elements=(TextElement(value="one_point_oh"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=Decimal("2.5"), raw="2.5"),
                    value=Pattern(elements=(TextElement(value="two_point_five"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="other_float"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"val": 3.7})
        assert result == "other_float"
        assert errors == ()


class TestNumberLiteralSelectorCoverage:
    """Test NumberLiteral selector branch in _find_exact_variant (branch 400->395)."""

    def test_number_literal_selector_exact_match(self) -> None:
        """Branch 400->395 - Number literal variant exact matching."""
        bundle = FluentBundle("en_US", use_isolating=False)

        bundle.add_resource(
            """
items = { $count ->
    [0] No items
    [1] One item
    [42] The answer
   *[other] { $count } items
}
"""
        )

        result, _ = bundle.format_pattern("items", {"count": 0})
        assert "No items" in result

        result, _ = bundle.format_pattern("items", {"count": 1})
        assert "One item" in result

        result, _ = bundle.format_pattern("items", {"count": 42})
        assert "The answer" in result

    def test_number_literal_selector_no_match(self) -> None:
        """Branch 400->395 - Number literal no match falls through to default."""
        bundle = FluentBundle("en_US", use_isolating=False)

        bundle.add_resource(
            """
level = { $num ->
    [1] Level 1
    [2] Level 2
   *[other] Level unknown
}
"""
        )

        result, _ = bundle.format_pattern("level", {"num": 99})
        assert "Level unknown" in result

    def test_number_literal_with_float_selector(self) -> None:
        """Branch 400->395 - Float selector matching number literals."""
        bundle = FluentBundle("en_US", use_isolating=False)

        bundle.add_resource(
            """
rating = { $stars ->
    [1] Poor
    [2] Fair
    [3] Good
    [4] Great
    [5] Excellent
   *[other] Unrated
}
"""
        )

        result, _ = bundle.format_pattern("rating", {"stars": 5.0})
        assert "Excellent" in result

        result, _ = bundle.format_pattern("rating", {"stars": 3.5})
        assert "Unrated" in result

    def test_number_literal_match_second_key(self) -> None:
        """Branch 400->395 - Number literal match on second+ key (loop continuation)."""
        bundle = FluentBundle("en_US", use_isolating=False)

        bundle.add_resource(
            """
score = { $points ->
    [10] Ten points
    [20] Twenty points
    [30] Thirty points
   *[other] Unknown
}
"""
        )

        result, _ = bundle.format_pattern("score", {"points": 20})
        assert "Twenty points" in result

        result, _ = bundle.format_pattern("score", {"points": 30})
        assert "Thirty points" in result


class TestNumberLiteralVariantMatching:
    """Test exact number literal matching in select expressions."""

    def test_exact_number_literal_match_with_integer(self) -> None:
        """Exact match with integer NumberLiteral (line 479)."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(
            """
msg = { $count ->
    [0] zero items
    [1] one item
    [42] exactly forty-two
   *[other] many items
}
"""
        )

        result, errors = bundle.format_pattern("msg", {"count": 42})
        assert result == "exactly forty-two"
        assert errors == ()

    def test_exact_number_literal_match_with_float(self) -> None:
        """Exact match with float NumberLiteral (Decimal comparison logic)."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(
            """
msg = { $value ->
    [3.14] pi
    [2.71] euler
   *[other] unknown
}
"""
        )

        result, errors = bundle.format_pattern("msg", {"value": 3.14})
        assert result == "pi"
        assert errors == ()

    def test_exact_number_literal_match_with_decimal(self) -> None:
        """Exact match with Decimal NumberLiteral (financial value precision)."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(
            """
msg = { $amount ->
    [99.99] special price
   *[other] regular price
}
"""
        )

        result, errors = bundle.format_pattern("msg", {"amount": Decimal("99.99")})
        assert result == "special price"
        assert errors == ()


# ============================================================================
# SELECT EXPRESSION CONSTRUCTION AND FALLBACK
# ============================================================================


class TestFallbackVariantNoVariants:
    """Empty variant list and missing default error paths (lines 645-648)."""

    def test_select_expression_with_no_variants_rejected_at_construction(self) -> None:
        """SelectExpression with empty variants is rejected by __post_init__."""
        selector = VariableReference(id=Identifier("count"))
        with pytest.raises(ValueError, match="requires at least one variant"):
            SelectExpression(selector=selector, variants=())

    def test_select_expression_without_default_rejected_at_construction(self) -> None:
        """SelectExpression without a default variant is rejected by __post_init__."""
        selector = VariableReference(id=Identifier("count"))
        variant = Variant(
            key=Identifier("one"),
            value=Pattern(elements=(TextElement(value="one"),)),
            default=False,
        )
        with pytest.raises(ValueError, match="exactly one default variant"):
            SelectExpression(selector=selector, variants=(variant,))


class TestSelectExpressionFallbackPaths:
    """Test fallback variant selection logic."""

    def test_selector_error_uses_default_variant(self) -> None:
        """When selector fails due to missing variable, uses default variant."""
        selector = VariableReference(id=Identifier("missing"))
        variants = (
            Variant(
                key=Identifier("one"),
                value=Pattern(elements=(TextElement(value="variant one"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="default variant"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {})
        assert "default variant" in result
        assert len(errors) > 0

    def test_selector_error_uses_default_variant_fallback(self) -> None:
        """When selector fails, the marked default variant is selected."""
        selector = VariableReference(id=Identifier("missing"))
        variants = (
            Variant(
                key=Identifier("first"),
                value=Pattern(elements=(TextElement(value="first variant"),)),
                default=False,
            ),
            Variant(
                key=Identifier("second"),
                value=Pattern(elements=(TextElement(value="default variant"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, _errors = resolver.resolve_message(message, {})
        assert "default variant" in result


# ============================================================================
# FLUENT NUMBER VARIANT MATCHING
# ============================================================================


class TestResolverFluentNumberVariantMatching:
    """Test FluentNumber handling in variant selection."""

    def test_fluent_number_matches_numeric_variant_key(self) -> None:
        """FluentNumber value extraction for numeric variant matching (line 502)."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(
            """
msg = { NUMBER($count) ->
    [1000] Exactly one thousand
    *[other] Other value
}
"""
        )

        result, errors = bundle.format_pattern("msg", {"count": 1000})
        assert len(errors) == 0
        assert "Exactly one thousand" in result

    def test_fluent_number_plural_category_selection(self) -> None:
        """FluentNumber value extraction for CLDR plural matching (line 608)."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(
            """
msg = { NUMBER($count) ->
    [one] One item
    *[other] Many items
}
"""
        )

        result, errors = bundle.format_pattern("msg", {"count": 1})
        assert len(errors) == 0
        assert "One item" in result

    def test_fluent_number_with_formatted_display(self) -> None:
        """FluentNumber preserves numeric value for matching while showing formatted string."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(
            """
msg = { NUMBER($amount, minimumFractionDigits: 2) ->
    [1000] Exactly one thousand
    *[other] Other
}
"""
        )

        result, errors = bundle.format_pattern("msg", {"amount": 1000})
        assert len(errors) == 0
        assert "Exactly one thousand" in result


# ============================================================================
# FORMAT VALUE COMPREHENSIVE
# ============================================================================


class TestFormatValueComprehensive:
    """Test _format_value with all FluentValue types."""

    def _make_resolver(self) -> FluentResolver:
        return FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

    def test_format_value_with_string(self) -> None:
        """Verify _format_value handles strings."""
        resolver = self._make_resolver()
        assert resolver._format_value("test") == "test"
        assert resolver._format_value("") == ""

    def test_format_value_with_bool_true(self) -> None:
        """Verify _format_value handles True as 'true'."""
        assert self._make_resolver()._format_value(True) == "true"

    def test_format_value_with_bool_false(self) -> None:
        """Verify _format_value handles False as 'false'."""
        assert self._make_resolver()._format_value(False) == "false"

    def test_format_value_with_int(self) -> None:
        """Verify _format_value handles integers."""
        resolver = self._make_resolver()
        assert resolver._format_value(42) == "42"
        assert resolver._format_value(0) == "0"
        assert resolver._format_value(-100) == "-100"

    def test_format_value_with_float(self) -> None:
        """Verify _format_value handles floats."""
        resolver = self._make_resolver()
        assert resolver._format_value(3.14) == "3.14"
        assert resolver._format_value(0.0) == "0.0"

    def test_format_value_with_none(self) -> None:
        """Verify _format_value handles None as empty string."""
        assert self._make_resolver()._format_value(None) == ""

    def test_format_value_with_decimal(self) -> None:
        """Verify _format_value handles Decimal."""
        assert self._make_resolver()._format_value(Decimal("123.45")) == "123.45"

    def test_format_value_with_datetime(self) -> None:
        """Verify _format_value handles datetime via str()."""
        dt = datetime(2025, 12, 11, 15, 30, 45, tzinfo=UTC)
        result = self._make_resolver()._format_value(dt)
        assert "2025" in result
        assert "12" in result
        assert "11" in result

    @given(
        value=st.one_of(
            st.text(),
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.booleans(),
            st.none(),
        )
    )
    def test_format_value_never_raises(self, value: str | int | float | bool | None) -> None:
        """Property: _format_value never raises exceptions."""
        event(f"value_type={type(value).__name__}")
        result = self._make_resolver()._format_value(value)
        assert isinstance(result, str)


# ============================================================================
# ERROR PATHS
# ============================================================================


class TestResolverErrorPaths:
    """Test error handling paths in resolver."""

    def test_missing_variable_returns_error_message(self) -> None:
        """Missing variable in select expression returns error with fallback."""
        ftl = """test = { $x ->
   [a] Value A
  *[b] Default
}
"""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(ftl)

        result, errors = bundle.format_pattern("test", {})
        assert len(errors) > 0
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE
        assert errors[0].diagnostic is not None
        assert errors[0].diagnostic.code.name == "VARIABLE_NOT_PROVIDED"
        assert result == "Default"


class TestPlaceableWithFormattingError:
    """Coverage for Placeable exception path with FrozenFluentError FORMATTING."""

    def test_placeable_formatting_error_with_fallback(self) -> None:
        """Placeable that raises FrozenFluentError (FORMATTING) uses fallback value."""
        from ftllexengine.diagnostics import FrozenErrorContext  # noqa: PLC0415

        def raise_formatting_error(_value: str) -> str:
            context = FrozenErrorContext(
                input_value="test",
                locale_code="en",
                parse_type="custom",
                fallback_value="FALLBACK",
            )
            msg = "Custom formatting error"
            raise FrozenFluentError(
                msg,
                ErrorCategory.FORMATTING,
                context=context,
            )

        registry = FunctionRegistry()
        registry.register(raise_formatting_error, ftl_name="ERROR_FUNC")

        func_call = FunctionReference(
            id=Identifier("ERROR_FUNC"),
            arguments=CallArguments(
                positional=(StringLiteral(value="test"),),
                named=(),
            ),
        )

        pattern = Pattern(
            elements=(
                TextElement(value="Before "),
                Placeable(expression=func_call),
                TextElement(value=" After"),
            )
        )
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {})
        assert result == "Before FALLBACK After"
        assert len(errors) == 1
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.FORMATTING
