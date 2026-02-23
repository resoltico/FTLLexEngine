"""Resolver error paths, unknown expression fallback, and adversarial AST tests.

Consolidates:
- test_resolver_fallback_and_terms.py: TestUnknownExpressionType
- test_resolver_term_and_pattern_branches.py: TestUnknownExpressionFallback
- test_resolver_ast_malformed.py: all module-level test functions
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from ftllexengine.diagnostics import ErrorCategory
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.resolution_context import ResolutionContext
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.syntax import (
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
from ftllexengine.syntax.ast import (
    FunctionReference,
    MessageReference,
    TermReference,
)

# ============================================================================
# UNKNOWN EXPRESSION TYPE
# ============================================================================


class TestUnknownExpressionType:
    """Test unknown expression type handling in _resolve_expression."""

    def test_unknown_expression_raises_resolution_error(self) -> None:
        """Unknown expression type raises FrozenFluentError with RESOLUTION category."""
        from ftllexengine.diagnostics import FrozenFluentError  # noqa: PLC0415

        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        class UnknownExpr:
            """Mock unknown expression type."""

        unknown = UnknownExpr()

        errors: list[FrozenFluentError] = []
        context = ResolutionContext()
        with pytest.raises(FrozenFluentError) as exc_info:
            resolver._resolve_expression(unknown, {}, errors, context)  # type: ignore[arg-type]

        assert exc_info.value.category == ErrorCategory.RESOLUTION
        error_msg = str(exc_info.value).lower()
        assert "unknown expression" in error_msg or "UnknownExpr" in str(exc_info.value)


class TestUnknownExpressionFallback:
    """Test unknown expression type fallback in _get_fallback_for_placeable."""

    def test_unknown_expression_fallback_with_mock(self) -> None:
        """Unknown expression type in _get_fallback_for_placeable returns {???}."""
        class UnknownExpression:
            """Mock unknown expression type."""

        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=Mock(),
            use_isolating=False,
        )

        fallback = resolver._get_fallback_for_placeable(
            UnknownExpression()  # type: ignore[arg-type]
        )
        assert fallback == "{???}"

    def test_fallback_for_all_known_expression_types(self) -> None:
        """Fallback generation for all known expression types produces expected strings."""
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=Mock(),
            use_isolating=False,
        )

        var_ref = VariableReference(id=Identifier(name="test"))
        assert resolver._get_fallback_for_placeable(var_ref) == "{$test}"

        msg_ref = MessageReference(id=Identifier(name="msg"), attribute=None)
        assert resolver._get_fallback_for_placeable(msg_ref) == "{msg}"

        term_ref = TermReference(id=Identifier(name="term"), attribute=None, arguments=None)
        assert resolver._get_fallback_for_placeable(term_ref) == "{-term}"

        func_ref = FunctionReference(id=Identifier(name="FUNC"), arguments=Mock())
        assert resolver._get_fallback_for_placeable(func_ref) == "{!FUNC}"

        dummy_variant = Variant(
            key=Identifier(name="other"),
            value=Pattern(elements=(TextElement(value="x"),)),
            default=True,
        )
        select_expr_unknown = SelectExpression(
            selector=Mock(), variants=(dummy_variant,)
        )
        assert resolver._get_fallback_for_placeable(select_expr_unknown) == "{{???} -> ...}"

        var_selector = VariableReference(id=Identifier(name="count"))
        select_expr_var = SelectExpression(
            selector=var_selector, variants=(dummy_variant,)
        )
        assert resolver._get_fallback_for_placeable(select_expr_var) == "{{$count} -> ...}"


# ============================================================================
# ADVERSARIAL AST TESTS (object.__setattr__ bypass of frozen dataclass validation)
# ============================================================================


def test_select_expression_with_empty_variants_raises_error() -> None:
    """SelectExpression with empty variants list raises FrozenFluentError.

    Coverage: Lines 812-816 in resolver.py (_resolve_select_expression).

    Programmatic bypass of AST validation using object.__setattr__ to test
    the resolver's defensive code against adversarial input.
    """
    selector = VariableReference(id=Identifier(name="count"))
    variant = Variant(
        key=Identifier(name="other"),
        value=Pattern(elements=(TextElement(value="test"),)),
        default=True,
    )
    select_expr = SelectExpression(selector=selector, variants=(variant,))

    # Bypass frozen dataclass validation to create empty variants list
    object.__setattr__(select_expr, "variants", ())

    pattern = Pattern(elements=(Placeable(expression=select_expr),))
    message = Message(id=Identifier(name="test"), value=pattern, attributes=())

    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
    )

    _result, errors = resolver.resolve_message(message, args={"count": 5})

    assert len(errors) > 0
    assert any(e.category == ErrorCategory.RESOLUTION for e in errors)
    assert any("variant" in str(e).lower() for e in errors)


def test_select_expression_fallback_with_empty_variants_raises_error() -> None:
    """Fallback variant resolution with empty variants raises error.

    Coverage: Lines 849-853 in resolver.py (_resolve_fallback_variant).

    Tests the case where selector evaluation fails AND there are no variants
    to fall back to. Uses object.__setattr__ to bypass AST validation.
    """
    selector = VariableReference(id=Identifier(name="missing"))
    variant = Variant(
        key=Identifier(name="other"),
        value=Pattern(elements=(TextElement(value="test"),)),
        default=True,
    )
    select_expr = SelectExpression(selector=selector, variants=(variant,))

    object.__setattr__(select_expr, "variants", ())

    pattern = Pattern(elements=(Placeable(expression=select_expr),))
    message = Message(id=Identifier(name="test"), value=pattern, attributes=())

    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
    )

    _result, errors = resolver.resolve_message(message, args={})

    assert len(errors) >= 1
    assert any("variant" in str(e).lower() for e in errors)


def test_select_expression_with_no_default_variant() -> None:
    """SelectExpression with no default variant uses first variant as fallback.

    Coverage: Line 714 in resolver.py (_find_default_variant returns None).

    When selector doesn't match and no default variant exists, resolver falls
    back to the first variant per Fluent spec graceful degradation.
    Uses object.__setattr__ to bypass AST validation.
    """
    variant1 = Variant(
        key=Identifier(name="one"),
        value=Pattern(elements=(TextElement(value="one item"),)),
        default=False,
    )
    variant2 = Variant(
        key=Identifier(name="other"),
        value=Pattern(elements=(TextElement(value="many items"),)),
        default=True,
    )

    selector = VariableReference(id=Identifier(name="count"))
    select_expr = SelectExpression(selector=selector, variants=(variant1, variant2))

    variant2_no_default = Variant(
        key=variant2.key,
        value=variant2.value,
        default=False,
    )
    object.__setattr__(select_expr, "variants", (variant1, variant2_no_default))

    pattern = Pattern(elements=(Placeable(expression=select_expr),))
    message = Message(id=Identifier(name="test"), value=pattern, attributes=())

    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
    )

    result, errors = resolver.resolve_message(message, args={"count": "unmatched"})
    assert "one item" in result
    assert len(errors) == 0


def test_pattern_with_unknown_element_type_ignored() -> None:
    """Pattern containing unknown element types is handled gracefully.

    Coverage: Branch 404->400 in resolver.py (_resolve_pattern).

    Tests defensive programming for Pattern.elements containing an unknown type.
    With proper AST construction this never happens, but the match statement
    handles it gracefully by skipping the element. Uses object.__setattr__ to
    inject an unknown element.
    """
    pattern = Pattern(
        elements=(
            TextElement(value="Hello "),
            Placeable(expression=StringLiteral(value="World")),
        )
    )

    class UnknownElement:
        """Mock element type not in AST."""

    unknown = UnknownElement()
    object.__setattr__(
        pattern,
        "elements",
        (
            TextElement(value="Hello "),
            unknown,  # Intentional: testing unknown element type handling
            Placeable(expression=StringLiteral(value="World")),
        ),
    )

    message = Message(id=Identifier(name="test"), value=pattern, attributes=())

    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
    )

    result, errors = resolver.resolve_message(message, args={})
    assert "Hello" in result
    assert "World" in result
    assert len(errors) == 0


def test_variant_key_with_unknown_type_skipped() -> None:
    """Variant with unknown key type is skipped during matching.

    Coverage: Branch 644->639 in resolver.py (_find_exact_variant).

    Tests that variant keys that are neither Identifier nor NumberLiteral
    are handled gracefully (skipped), falling back to the default variant.
    Uses object.__setattr__ to inject unknown key type.
    """
    class UnknownKeyType:
        """Mock key type not in AST."""

    variant_unknown = Variant(
        key=Identifier(name="placeholder"),
        value=Pattern(elements=(TextElement(value="should skip"),)),
        default=False,
    )
    variant_default = Variant(
        key=Identifier(name="other"),
        value=Pattern(elements=(TextElement(value="fallback"),)),
        default=True,
    )

    unknown_key = UnknownKeyType()
    object.__setattr__(variant_unknown, "key", unknown_key)

    selector = VariableReference(id=Identifier(name="count"))
    select_expr = SelectExpression(
        selector=selector,
        variants=(variant_unknown, variant_default),
    )

    pattern = Pattern(elements=(Placeable(expression=select_expr),))
    message = Message(id=Identifier(name="test"), value=pattern, attributes=())

    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
    )

    result, errors = resolver.resolve_message(message, args={"count": 1})
    assert "fallback" in result
    assert "should skip" not in result
    assert len(errors) == 0


def test_number_literal_rejects_invalid_raw() -> None:
    """NumberLiteral.__post_init__ rejects raw strings that are not valid numbers.

    Previously, programmatically constructed ASTs with invalid NumberLiteral.raw
    strings required the resolver to handle them defensively. NumberLiteral now
    enforces the invariant at construction time, preventing invalid ASTs from
    being created via the normal API.
    """
    with pytest.raises(ValueError, match="not a valid number literal"):
        NumberLiteral(value=1, raw="not-a-number")


def test_select_expression_fallback_no_default_uses_first() -> None:
    """Fallback variant resolution with no default uses first variant.

    Coverage: Line 850 in resolver.py (_resolve_fallback_variant).

    Tests the case where selector evaluation fails (missing variable),
    no default variant exists, but variants list is not empty.
    Falls back to first variant. Uses object.__setattr__ to bypass validation.
    """
    variant1 = Variant(
        key=Identifier(name="first"),
        value=Pattern(elements=(TextElement(value="first variant"),)),
        default=False,
    )
    variant2 = Variant(
        key=Identifier(name="second"),
        value=Pattern(elements=(TextElement(value="second variant"),)),
        default=True,
    )

    selector = VariableReference(id=Identifier(name="missing_var"))
    select_expr = SelectExpression(selector=selector, variants=(variant1, variant2))

    variant2_no_default = Variant(
        key=variant2.key,
        value=variant2.value,
        default=False,
    )
    object.__setattr__(select_expr, "variants", (variant1, variant2_no_default))

    pattern = Pattern(elements=(Placeable(expression=select_expr),))
    message = Message(id=Identifier(name="test"), value=pattern, attributes=())

    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
    )

    result, errors = resolver.resolve_message(message, args={})
    assert "first variant" in result
    assert len(errors) >= 1
    assert any(e.category == ErrorCategory.REFERENCE for e in errors)


def test_select_expression_no_match_no_default_uses_first() -> None:
    """SelectExpression with no match and no default uses first variant.

    Comprehensive fallback chain:
    1. No exact match
    2. No plural match (string selector)
    3. No default variant (bypassed validation)
    4. Falls back to first variant

    Ensures line 812-813 (fallback to first variant) is covered.
    """
    variant1 = Variant(
        key=Identifier(name="specific"),
        value=Pattern(elements=(TextElement(value="first"),)),
        default=False,
    )
    variant2 = Variant(
        key=Identifier(name="other"),
        value=Pattern(elements=(TextElement(value="second"),)),
        default=True,
    )

    selector = VariableReference(id=Identifier(name="value"))
    select_expr = SelectExpression(selector=selector, variants=(variant1, variant2))

    variant2_no_default = Variant(
        key=variant2.key,
        value=variant2.value,
        default=False,
    )
    object.__setattr__(select_expr, "variants", (variant1, variant2_no_default))

    pattern = Pattern(elements=(Placeable(expression=select_expr),))
    message = Message(id=Identifier(name="test"), value=pattern, attributes=())

    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
    )

    result, errors = resolver.resolve_message(message, args={"value": "no-match"})
    assert "first" in result
    assert len(errors) == 0
