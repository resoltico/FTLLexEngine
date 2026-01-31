"""Tests for resolver handling of malformed or edge-case AST structures.

Covers defensive programming paths that should never occur with well-formed
FTL but must be tested for 100% coverage and security (DoS via adversarial AST).

Tests focus on:
    - SelectExpression with empty variants list (bypasses AST validation)
    - SelectExpression with no default variant (bypasses AST validation)
    - Pattern elements of unknown types (defensive)
    - Variant keys of unknown types (defensive)

These cases can only occur via programmatic AST construction that bypasses
validation. Testing ensures graceful degradation even with adversarial input.
"""

from __future__ import annotations

from ftllexengine.diagnostics import ErrorCategory
from ftllexengine.runtime.function_bridge import FunctionRegistry
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


def test_select_expression_with_empty_variants_raises_error() -> None:
    """SelectExpression with empty variants list raises FrozenFluentError.

    Coverage: Lines 812-816 in resolver.py (_resolve_select_expression).

    This tests the defensive case where a programmatically constructed
    SelectExpression has no variants. The AST validation normally prevents this,
    but we bypass it using object.__setattr__ to test the resolver's defensive code.
    """
    # Create valid SelectExpression first
    selector = VariableReference(id=Identifier(name="count"))
    variant = Variant(
        key=Identifier(name="other"),
        value=Pattern(elements=(TextElement(value="test"),)),
        default=True,
    )
    select_expr = SelectExpression(selector=selector, variants=(variant,))

    # Bypass frozen dataclass validation to create empty variants list
    # This simulates adversarial AST construction
    object.__setattr__(select_expr, "variants", ())

    # Create message containing this malformed select expression
    pattern = Pattern(elements=(Placeable(expression=select_expr),))
    message = Message(
        id=Identifier(name="test"),
        value=pattern,
        attributes=(),  # Required parameter
    )

    # Create resolver
    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
    )

    # Should raise FrozenFluentError when trying to resolve
    _result, errors = resolver.resolve_message(message, args={"count": 5})

    # Verify error was collected
    assert len(errors) > 0
    assert any(e.category == ErrorCategory.RESOLUTION for e in errors)
    assert any("variant" in str(e).lower() for e in errors)


def test_select_expression_fallback_with_empty_variants_raises_error() -> None:
    """Fallback variant resolution with empty variants raises error.

    Coverage: Lines 849-853 in resolver.py (_resolve_fallback_variant).

    Tests the case where selector evaluation fails AND there are no variants
    to fall back to. This exercises _resolve_fallback_variant error path.
    """
    # Create SelectExpression with missing variable selector
    selector = VariableReference(id=Identifier(name="missing"))
    variant = Variant(
        key=Identifier(name="other"),
        value=Pattern(elements=(TextElement(value="test"),)),
        default=True,
    )
    select_expr = SelectExpression(selector=selector, variants=(variant,))

    # Bypass validation to create empty variants (simulates adversarial AST)
    object.__setattr__(select_expr, "variants", ())

    # Create message containing this malformed select expression
    pattern = Pattern(elements=(Placeable(expression=select_expr),))
    message = Message(
        id=Identifier(name="test"),
        value=pattern,
        attributes=(),
    )

    # Create resolver
    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
    )

    # Should raise error: missing variable triggers fallback, empty variants fails
    _result, errors = resolver.resolve_message(message, args={})

    # Verify errors collected (both missing variable and no variants)
    assert len(errors) >= 1
    # At minimum, should have no variants error
    assert any("variant" in str(e).lower() for e in errors)


def test_select_expression_with_no_default_variant() -> None:
    """SelectExpression with no default variant uses first variant.

    Coverage: Line 714 in resolver.py (_find_default_variant returns None).

    When selector doesn't match and no default variant exists, the resolver
    falls back to the first variant per Fluent spec. AST validation normally
    enforces exactly one default, so we bypass it for testing.
    """
    # Create variants - initially one has default to satisfy validation
    variant1 = Variant(
        key=Identifier(name="one"),
        value=Pattern(elements=(TextElement(value="one item"),)),
        default=False,
    )
    variant2 = Variant(
        key=Identifier(name="other"),
        value=Pattern(elements=(TextElement(value="many items"),)),
        default=True,  # Required by AST validation
    )

    # Create SelectExpression
    selector = VariableReference(id=Identifier(name="count"))
    select_expr = SelectExpression(selector=selector, variants=(variant1, variant2))

    # Now bypass validation to remove default from variant2
    # Simulates adversarial AST where no defaults exist
    variant2_no_default = Variant(
        key=variant2.key,
        value=variant2.value,
        default=False,
    )
    object.__setattr__(select_expr, "variants", (variant1, variant2_no_default))

    # Create message
    pattern = Pattern(elements=(Placeable(expression=select_expr),))
    message = Message(
        id=Identifier(name="test"),
        value=pattern,
        attributes=(),
    )

    # Create resolver
    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
    )

    # Use a selector value that doesn't match any variant key
    # With no default variant, should fall back to first variant
    result, errors = resolver.resolve_message(message, args={"count": "unmatched"})

    # Should resolve to first variant since no default and no match
    assert "one item" in result
    # No errors expected - graceful fallback
    assert len(errors) == 0


def test_pattern_with_unknown_element_type_ignored() -> None:
    """Pattern containing unknown element types is handled gracefully.

    Coverage: Branch 404->400 in resolver.py (_resolve_pattern).

    This tests defensive programming for the case where Pattern.elements
    contains an unknown type. With proper AST construction this never happens,
    but the match statement should handle it gracefully by skipping the element.
    """
    # Create a valid pattern first
    pattern = Pattern(
        elements=(
            TextElement(value="Hello "),
            Placeable(expression=StringLiteral(value="World")),
        )
    )

    # Create a mock object that's neither TextElement nor Placeable
    class UnknownElement:
        """Mock element type not in AST."""

    # Inject unknown element into pattern (simulates adversarial AST)
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

    message = Message(
        id=Identifier(name="test"),
        value=pattern,
        attributes=(),
    )

    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
    )

    result, errors = resolver.resolve_message(message, args={})

    # Should resolve successfully, skipping unknown element
    assert "Hello" in result
    assert "World" in result
    assert len(errors) == 0


def test_variant_key_with_unknown_type_skipped() -> None:
    """Variant with unknown key type is skipped during matching.

    Coverage: Branch 644->639 in resolver.py (_find_exact_variant).

    Tests that variant keys that are neither Identifier nor NumberLiteral
    are handled gracefully (skipped) during variant matching, falling back
    to the default variant.
    """
    # Create a mock variant key type
    class UnknownKeyType:
        """Mock key type not in AST."""

    # Create valid variants
    variant_unknown = Variant(
        key=Identifier(name="placeholder"),  # Start with valid key
        value=Pattern(elements=(TextElement(value="should skip"),)),
        default=False,
    )
    variant_default = Variant(
        key=Identifier(name="other"),
        value=Pattern(elements=(TextElement(value="fallback"),)),
        default=True,
    )

    # Replace the key with unknown type (simulates adversarial AST)
    unknown_key = UnknownKeyType()
    object.__setattr__(variant_unknown, "key", unknown_key)

    selector = VariableReference(id=Identifier(name="count"))
    select_expr = SelectExpression(
        selector=selector,
        variants=(variant_unknown, variant_default),
    )

    pattern = Pattern(elements=(Placeable(expression=select_expr),))
    message = Message(
        id=Identifier(name="test"),
        value=pattern,
        attributes=(),
    )

    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
    )

    # Should skip unknown key variant and use default
    result, errors = resolver.resolve_message(message, args={"count": 1})
    assert "fallback" in result
    assert "should skip" not in result
    assert len(errors) == 0


def test_select_expression_with_invalid_number_literal_raw() -> None:
    """Variant with malformed NumberLiteral.raw is skipped gracefully.

    Coverage: Lines 670-675 in resolver.py (_find_exact_variant).

    Tests that when NumberLiteral.raw cannot be parsed as Decimal
    (from programmatic AST construction), the variant is skipped instead
    of crashing.
    """
    # Create a variant with malformed NumberLiteral.raw
    # In normal parsing this cannot occur, but programmatic construction allows it
    malformed_variant = Variant(
        key=NumberLiteral(value=1, raw="not-a-number"),  # Invalid raw
        value=Pattern(elements=(TextElement(value="malformed"),)),
        default=False,
    )
    valid_variant = Variant(
        key=Identifier(name="other"),
        value=Pattern(elements=(TextElement(value="fallback"),)),
        default=True,
    )

    selector = VariableReference(id=Identifier(name="count"))
    select_expr = SelectExpression(
        selector=selector,
        variants=(malformed_variant, valid_variant),
    )

    pattern = Pattern(elements=(Placeable(expression=select_expr),))
    message = Message(
        id=Identifier(name="test"),
        value=pattern,
        attributes=(),
    )

    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
    )

    # Should skip malformed variant and use default
    result, errors = resolver.resolve_message(message, args={"count": 1})

    # Should fall back to valid variant since malformed is skipped
    assert "fallback" in result
    assert "malformed" not in result
    # No errors expected - graceful skip
    assert len(errors) == 0


def test_select_expression_fallback_no_default_uses_first() -> None:
    """Fallback variant resolution with no default uses first variant.

    Coverage: Line 850 in resolver.py (_resolve_fallback_variant).

    Tests the case where selector evaluation fails (missing variable),
    no default variant exists, but variants list is not empty.
    Should fall back to first variant.
    """
    # Create variants without default (bypass validation)
    variant1 = Variant(
        key=Identifier(name="first"),
        value=Pattern(elements=(TextElement(value="first variant"),)),
        default=False,
    )
    variant2 = Variant(
        key=Identifier(name="second"),
        value=Pattern(elements=(TextElement(value="second variant"),)),
        default=True,  # Required by validation
    )

    # Selector references missing variable (will trigger fallback)
    selector = VariableReference(id=Identifier(name="missing_var"))
    select_expr = SelectExpression(
        selector=selector,
        variants=(variant1, variant2),
    )

    # Bypass validation to remove default
    variant2_no_default = Variant(
        key=variant2.key,
        value=variant2.value,
        default=False,
    )
    object.__setattr__(select_expr, "variants", (variant1, variant2_no_default))

    pattern = Pattern(elements=(Placeable(expression=select_expr),))
    message = Message(
        id=Identifier(name="test"),
        value=pattern,
        attributes=(),
    )

    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
    )

    # Missing variable triggers fallback path, no default, should use first
    result, errors = resolver.resolve_message(message, args={})

    # Should use first variant as fallback
    assert "first variant" in result
    # Should have error for missing variable
    assert len(errors) >= 1
    assert any(e.category == ErrorCategory.REFERENCE for e in errors)


def test_select_expression_no_match_no_default_uses_first() -> None:
    """SelectExpression with no match and no default uses first variant.

    Comprehensive test ensuring fallback chain:
    1. No exact match
    2. No plural match (string selector)
    3. No default variant (bypassed validation)
    4. Falls back to first variant

    This ensures line 812-813 (fallback to first variant) is covered.
    """
    # Create variants - initially with default to pass validation
    variant1 = Variant(
        key=Identifier(name="specific"),
        value=Pattern(elements=(TextElement(value="first"),)),
        default=False,
    )
    variant2 = Variant(
        key=Identifier(name="other"),
        value=Pattern(elements=(TextElement(value="second"),)),
        default=True,  # Required by validation
    )

    selector = VariableReference(id=Identifier(name="value"))
    select_expr = SelectExpression(
        selector=selector,
        variants=(variant1, variant2),
    )

    # Bypass validation to remove default
    variant2_no_default = Variant(
        key=variant2.key,
        value=variant2.value,
        default=False,
    )
    object.__setattr__(select_expr, "variants", (variant1, variant2_no_default))

    pattern = Pattern(elements=(Placeable(expression=select_expr),))
    message = Message(
        id=Identifier(name="test"),
        value=pattern,
        attributes=(),
    )

    resolver = FluentResolver(
        locale="en",
        messages={},
        terms={},
        function_registry=FunctionRegistry(),
    )

    # Selector value doesn't match any variant key
    result, errors = resolver.resolve_message(message, args={"value": "no-match"})

    # Should use first variant as ultimate fallback
    assert "first" in result
    assert len(errors) == 0
