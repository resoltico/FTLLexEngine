# mypy: ignore-errors
# mypy: ignore-errors
from __future__ import annotations

from decimal import Decimal

import pytest

from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.resolution_context import ResolutionContext
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.syntax.ast import (
    Identifier,
    Message,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
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

    def test_number_literal_rejects_invalid_raw(self) -> None:
        """NumberLiteral.__post_init__ prevents construction with invalid raw strings.

        Previously, the resolver handled programmatically constructed ASTs where
        NumberLiteral.raw was unparseable as Decimal. NumberLiteral now enforces
        the invariant at construction time, making such ASTs impossible via the
        normal API.
        """
        with pytest.raises(ValueError, match="not a valid number literal"):
            NumberLiteral(value=Decimal("0.0"), raw="invalid")

    def test_deeply_nested_select_expression_fallback(self) -> None:
        """Deeply nested SelectExpression in fallback generation doesn't overflow."""
        from ftllexengine.runtime.functions import (
            create_default_registry,
        )
        from ftllexengine.syntax.ast import Expression

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
