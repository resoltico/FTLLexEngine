"""Term reference, nested placeable, and full integration tests for FluentResolver.

Consolidates:
- test_resolver_placeable_and_numeric.py: TestPlaceableResolution,
  TestResolverFormattingErrorFallback, TestResolverTermNamedArguments
- test_resolver_fallback_and_terms.py: TestNestedPlaceableExpression,
  TestFallbackGeneration, TestResolverFullIntegration, TestTermReferencePositionalArguments
- test_resolver_term_and_pattern_branches.py: TestPlaceableBranchCoverage,
  TestNestedPlaceableCoverage, TestTermAttributeCoverage, TestResolverIntegration,
  TestTermCyclicReferenceCoverage, TestTermMaxDepthCoverage,
  TestEmptyPatternBranchCoverage, TestPatternElementLoopCoverage
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from hypothesis import assume, event, given
from hypothesis import strategies as st

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.resolution_context import ResolutionContext
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.syntax.ast import (
    FunctionReference,
    Identifier,
    Message,
    MessageReference,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
    StringLiteral,
    Term,
    TermReference,
    TextElement,
    VariableReference,
    Variant,
)

# ============================================================================
# PLACEABLE RESOLUTION
# ============================================================================


class TestPlaceableResolution:
    """Pattern resolution with placeables (line 286->282 coverage)."""

    def test_pattern_with_placeable_uses_isolating(self) -> None:
        """Placeable in pattern uses isolating marks."""
        pattern = Pattern(
            elements=(
                TextElement(value="Hello "),
                Placeable(expression=VariableReference(id=Identifier("name"))),
            )
        )
        message = Message(id=Identifier("greeting"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"greeting": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=True,
        )

        result, errors = resolver.resolve_message(message, {"name": "World"})
        assert not errors
        assert "\u2068" in result  # FSI
        assert "\u2069" in result  # PDI
        assert "World" in result

    def test_pattern_with_placeable_without_isolating(self) -> None:
        """Placeable in pattern without isolating marks."""
        pattern = Pattern(
            elements=(
                TextElement(value="Hello "),
                Placeable(expression=VariableReference(id=Identifier("name"))),
            )
        )
        message = Message(id=Identifier("greeting"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"greeting": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {"name": "World"})
        assert not errors
        assert "\u2068" not in result
        assert "\u2069" not in result
        assert result == "Hello World"

    @given(
        var_name=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
            min_size=1,
            max_size=10,
        ),
        value=st.text(min_size=0, max_size=20),
    )
    def test_placeable_resolution_property(self, var_name: str, value: str) -> None:
        """Property: Placeables always resolve variables from args."""
        event(f"var_name_len={len(var_name)}")
        pattern = Pattern(
            elements=(
                Placeable(expression=VariableReference(id=Identifier(var_name))),
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

        result, errors = resolver.resolve_message(message, {var_name: value})
        assert not errors
        assert value in result


class TestPlaceableBranchCoverage:
    """Test Placeable case in _resolve_pattern (line 142->138)."""

    def test_simple_placeable_in_pattern(self) -> None:
        """Placeable branch in _resolve_pattern."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("msg = Value: { $var }")

        result, _ = bundle.format_pattern("msg", {"var": "test"})
        assert result == "Value: test"

    def test_placeable_with_isolating_marks(self) -> None:
        """Placeable with bidi isolation (use_isolating=True)."""
        bundle = FluentBundle("en_US", use_isolating=True)
        bundle.add_resource("msg = { $value }")

        result, _ = bundle.format_pattern("msg", {"value": "RTL"})
        assert "\u2068" in result
        assert "\u2069" in result

    @given(value=st.text(min_size=1, max_size=50))
    def test_placeable_with_various_values(self, value: str) -> None:
        """Property: Placeable branch handles various string values."""
        event(f"value_len={len(value)}")
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("msg = { $x }")

        result, _ = bundle.format_pattern("msg", {"x": value})
        assert value in result


class TestNestedPlaceableExpression:
    """Test Placeable case in _resolve_expression (line 208)."""

    def test_programmatic_nested_placeable_with_variable(self) -> None:
        """_resolve_expression handles Placeable(VariableReference)."""
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        inner_var = VariableReference(id=Identifier(name="test"))
        inner_placeable = Placeable(expression=inner_var)
        outer_placeable = Placeable(expression=inner_placeable)

        errors: list[FrozenFluentError] = []
        context = ResolutionContext()
        result = resolver._resolve_expression(
            outer_placeable, {"test": "value123"}, errors, context
        )
        assert result == "value123"

    def test_programmatic_nested_placeable_with_string_literal(self) -> None:
        """_resolve_expression handles Placeable(StringLiteral)."""
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        string_lit = StringLiteral(value="literal_text")
        placeable = Placeable(expression=string_lit)

        errors: list[FrozenFluentError] = []
        context = ResolutionContext()
        result = resolver._resolve_expression(placeable, {}, errors, context)
        assert result == "literal_text"

    def test_programmatic_nested_placeable_with_number_literal(self) -> None:
        """_resolve_expression handles Placeable(NumberLiteral)."""
        from decimal import Decimal  # noqa: PLC0415

        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        number_lit = NumberLiteral(value=Decimal("42.5"), raw="42.5")
        placeable = Placeable(expression=number_lit)

        errors: list[FrozenFluentError] = []
        context = ResolutionContext()
        result = resolver._resolve_expression(placeable, {}, errors, context)
        assert result == Decimal("42.5")

    def test_programmatic_deeply_nested_placeables(self) -> None:
        """_resolve_expression handles multiple nesting levels."""
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        string_lit = StringLiteral(value="deep")
        level1 = Placeable(expression=string_lit)
        level2 = Placeable(expression=level1)
        level3 = Placeable(expression=level2)

        errors: list[FrozenFluentError] = []
        context = ResolutionContext()
        result = resolver._resolve_expression(level3, {}, errors, context)
        assert result == "deep"


class TestNestedPlaceableCoverage:
    """Test nested Placeable case in _resolve_expression (line 190)."""

    def test_placeable_in_select_variant_value(self) -> None:
        """Placeable within select expression variant pattern."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(
            """
count = { $num ->
    [1] One: { $num }
   *[other] Many: { $num }
}
"""
        )

        result, _ = bundle.format_pattern("count", {"num": 1})
        assert "One:" in result
        assert "1" in result


# ============================================================================
# FALLBACK GENERATION
# ============================================================================


class TestFallbackGeneration:
    """Test _get_fallback_for_placeable edge cases."""

    def test_fallback_message_reference_with_attribute(self) -> None:
        """Fallback for MessageReference with attribute."""
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        msg_ref = MessageReference(
            id=Identifier(name="greeting"),
            attribute=Identifier(name="formal"),
        )
        fallback = resolver._get_fallback_for_placeable(msg_ref)
        assert fallback == "{greeting.formal}"

    def test_fallback_term_reference_with_attribute(self) -> None:
        """Fallback for TermReference with attribute."""
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        term_ref = TermReference(
            id=Identifier(name="brand"),
            attribute=Identifier(name="gender"),
            arguments=None,
        )
        fallback = resolver._get_fallback_for_placeable(term_ref)
        assert fallback == "{-brand.gender}"

    def test_fallback_function_reference(self) -> None:
        """Fallback for FunctionReference shows (...)."""
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        func_ref = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=Mock(),
        )
        fallback = resolver._get_fallback_for_placeable(func_ref)
        assert fallback == "{!NUMBER}"

    def test_fallback_select_expression(self) -> None:
        """Fallback for SelectExpression with valid construction."""
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        var_selector = VariableReference(id=Identifier(name="status"))
        default_variant = Variant(
            key=Identifier(name="other"),
            value=Pattern(elements=(TextElement(value="default"),)),
            default=True,
        )
        select_expr = SelectExpression(
            selector=var_selector,
            variants=(default_variant,),
        )
        fallback = resolver._get_fallback_for_placeable(select_expr)
        assert "{$status}" in fallback

    def test_select_expression_empty_variants_rejected(self) -> None:
        """SelectExpression with empty variants is rejected at construction."""
        with pytest.raises(ValueError, match="requires at least one variant"):
            SelectExpression(
                selector=VariableReference(id=Identifier(name="x")),
                variants=(),
            )


# ============================================================================
# TERM REFERENCES
# ============================================================================


class TestTermAttributeCoverage:
    """Test term reference with attribute (line 232)."""

    def test_term_with_attribute_resolution(self) -> None:
        """Term attribute value resolution."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(
            """
-brand = Firefox
    .gender = masculine
    .case = nominative

welcome = Welcome to { -brand.gender }!
"""
        )

        result, _ = bundle.format_pattern("welcome")
        assert "masculine" in result

    def test_term_with_multiple_attributes(self) -> None:
        """Multiple attribute access on same term."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(
            """
-product = MyApp
    .version = 2.0
    .platform = macOS

info = { -product.version } on { -product.platform }
"""
        )

        result, _ = bundle.format_pattern("info")
        assert "2.0" in result
        assert "macOS" in result

    @given(
        attr_name=st.from_regex(r"[a-z][a-z0-9]{0,10}", fullmatch=True),
        attr_value=st.text(
            alphabet=st.characters(
                blacklist_categories=("Cc", "Cs"),
                blacklist_characters="{}[]#.=-*",
            ),
            min_size=1,
            max_size=20,
        ),
    )
    def test_term_attribute_property(self, attr_name: str, attr_value: str) -> None:
        """Property: Term attribute resolution works for various names."""
        event(f"attr_name_len={len(attr_name)}")
        assume(not any(c in attr_value for c in "{}[]#.=-*\n\r"))
        assume(attr_value.strip() == attr_value)

        bundle = FluentBundle("en_US", use_isolating=False)
        ftl = f"-term = Base\n    .{attr_name} = {attr_value}\n\nmsg = {{ -term.{attr_name} }}"
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")
        assert attr_value in result


class TestResolverTermNamedArguments:
    """Test term references with named arguments."""

    def test_term_reference_with_named_arguments(self) -> None:
        """Term references can have named arguments."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(
            """
-brand = { $case ->
    [nominative] Firefox
    *[other] Firefox
}
msg = Welcome to { -brand(case: "nominative") }
"""
        )

        result, errors = bundle.format_pattern("msg")
        assert len(errors) == 0
        assert "Firefox" in result

    def test_term_reference_multiple_named_arguments(self) -> None:
        """Term with multiple named arguments."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(
            """
-product = { $version } { $edition ->
    [pro] Professional
    *[standard] Standard
}
msg = Using { -product(version: "2.0", edition: "pro") }
"""
        )

        result, errors = bundle.format_pattern("msg")
        assert len(errors) == 0
        assert "2.0" in result
        assert "Professional" in result


class TestTermReferencePositionalArguments:
    """Test term reference with positional arguments."""

    def test_term_reference_with_positional_args(self) -> None:
        """Term reference with positional arguments emits warning.

        Covers ARCH-TERM-POSITIONAL-DISCARD-001 diagnostic path.
        """
        bundle = FluentBundle("en_US", use_isolating=False, strict=False)
        bundle.add_resource(
            """
-my-term = Term value
msg = { -my-term($arg1, $arg2) }
"""
        )

        result, errors = bundle.format_pattern("msg", {"arg1": "val1", "arg2": "val2"})
        assert result == "Term value"
        assert len(errors) == 1
        assert "positional" in str(errors[0]).lower()

    def test_term_reference_positional_args_trigger_errors(self) -> None:
        """Term reference positional args collect errors when variables missing."""
        bundle = FluentBundle("en_US", use_isolating=False, strict=False)
        bundle.add_resource(
            """
-my-term = Term value
msg = { -my-term($missing_var) }
"""
        )

        _result, errors = bundle.format_pattern("msg", {})
        assert len(errors) >= 1

    def test_term_reference_positional_args_emit_warning(self) -> None:
        """Term positional args emit warning (per Fluent spec, terms only accept named args)."""
        bundle = FluentBundle("en_US", use_isolating=False, strict=False)
        bundle.add_resource(
            """
-my-term = Term value
msg = { -my-term("val1", "val2") }
"""
        )

        result, errors = bundle.format_pattern("msg", {})
        assert result == "Term value"
        assert len(errors) == 1
        error = errors[0]
        assert "positional arguments" in str(error).lower()
        assert "my-term" in str(error)

    def test_term_reference_positional_args_warning_count(self) -> None:
        """Warning message includes count of positional arguments ignored."""
        bundle = FluentBundle("en_US", use_isolating=False, strict=False)
        bundle.add_resource(
            """
-brand = Firefox
msg = { -brand($a, $b, $c) }
"""
        )

        _result, errors = bundle.format_pattern("msg", {"a": 1, "b": 2, "c": 3})
        assert len(errors) >= 1

        positional_warning = None
        for error in errors:
            if "positional" in str(error).lower():
                positional_warning = error
                break

        assert positional_warning is not None
        assert "3" in str(positional_warning)


class TestTermCyclicReferenceCoverage:
    """Test cyclic reference detection in term references (lines 360-363)."""

    def test_term_direct_self_reference(self) -> None:
        """Term referencing itself directly produces CYCLIC error."""
        bundle = FluentBundle("en_US", use_isolating=False, strict=False)
        bundle.add_resource(
            """
-recursive = { -recursive }
msg = { -recursive }
"""
        )

        result, errors = bundle.format_pattern("msg")
        assert len(errors) > 0
        assert any(e.category == ErrorCategory.CYCLIC for e in errors)
        assert "{-recursive}" in result

    def test_term_indirect_cycle(self) -> None:
        """Terms forming indirect cycle (A -> B -> A) produce CYCLIC error."""
        bundle = FluentBundle("en_US", use_isolating=False, strict=False)
        bundle.add_resource(
            """
-termA = { -termB }
-termB = { -termA }
msg = { -termA }
"""
        )

        _result, errors = bundle.format_pattern("msg")
        assert len(errors) > 0
        assert any(e.category == ErrorCategory.CYCLIC for e in errors)

    def test_term_attribute_cycle(self) -> None:
        """Cycle through term attributes resolves without crash."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(
            """
-brand = Firefox
    .recursive = { -brand }
msg = { -brand.recursive }
"""
        )

        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert result is not None


class TestTermMaxDepthCoverage:
    """Test max depth exceeded in term references (lines 367-371)."""

    def test_term_deep_nesting_exceeds_depth(self) -> None:
        """Deep term nesting exceeds max depth with low max_depth context."""
        term3 = Term(
            id=Identifier(name="term3"),
            value=Pattern(elements=(TextElement(value="Base"),)),
            attributes=(),
        )
        term2 = Term(
            id=Identifier(name="term2"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(
                            id=Identifier(name="term3"),
                            attribute=None,
                            arguments=None,
                        )
                    ),
                )
            ),
            attributes=(),
        )
        term1 = Term(
            id=Identifier(name="term1"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(
                            id=Identifier(name="term2"),
                            attribute=None,
                            arguments=None,
                        )
                    ),
                )
            ),
            attributes=(),
        )
        msg = Message(
            id=Identifier(name="msg"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(
                            id=Identifier(name="term1"),
                            attribute=None,
                            arguments=None,
                        )
                    ),
                )
            ),
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={"msg": msg},
            terms={"term1": term1, "term2": term2, "term3": term3},
            function_registry=Mock(),
            use_isolating=False,
        )

        context = ResolutionContext(max_depth=2)
        _result, errors = resolver.resolve_message(msg, args=None, context=context)

        assert len(errors) > 0
        assert any("depth" in str(e).lower() for e in errors)

    def test_term_max_depth_via_resolver_directly(self) -> None:
        """Direct resolver test with low max_depth triggers depth error."""
        term_b = Term(
            id=Identifier(name="termB"),
            value=Pattern(elements=(TextElement(value="Final"),)),
            attributes=(),
        )
        term_a = Term(
            id=Identifier(name="termA"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(
                            id=Identifier(name="termB"),
                            attribute=None,
                            arguments=None,
                        )
                    ),
                )
            ),
            attributes=(),
        )
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(
                            id=Identifier(name="termA"),
                            attribute=None,
                            arguments=None,
                        )
                    ),
                )
            ),
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={"test": msg},
            terms={"termA": term_a, "termB": term_b},
            function_registry=Mock(),
            use_isolating=False,
        )

        context = ResolutionContext(max_depth=1)
        _result, errors = resolver.resolve_message(msg, args=None, context=context)

        assert len(errors) > 0
        assert any("depth" in str(e).lower() for e in errors)


# ============================================================================
# FULL INTEGRATION
# ============================================================================


class TestResolverFormattingErrorFallback:
    """Test FormattingError fallback handling in resolver."""

    def test_formatting_error_uses_fallback_value(self) -> None:
        """FormattingError fallback value is used in pattern resolution (line 312)."""
        bundle = FluentBundle("en", use_isolating=False, strict=False)
        bundle.add_resource(
            """
msg = Value: { NUMBER($value, minimumFractionDigits: "invalid") }
"""
        )

        result, errors = bundle.format_pattern("msg", {"value": 42})
        assert len(errors) > 0
        assert "42" in result or "{!NUMBER}" in result


class TestResolverIntegration:
    """Integration tests combining multiple coverage targets."""

    def test_complex_message_with_all_features(self) -> None:
        """Integration: placeable, term attribute, and select expression."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(
            """
-app = MyApp
    .version = 3.0

status = { -app.version } - { $count ->
    [0] No items
    [1] { $count } item
   *[other] { $count } items
}
"""
        )

        result, _ = bundle.format_pattern("status", {"count": 5})
        assert "3.0" in result
        assert "5 items" in result

    def test_error_recovery_with_fallback(self) -> None:
        """Error handling produces fallback for missing reference."""
        bundle = FluentBundle("en_US", use_isolating=False, strict=False)
        bundle.add_resource("msg = Value: { missing }")

        result, errors = bundle.format_pattern("msg")
        assert len(errors) > 0
        assert "{missing}" in result or "missing" in result.lower()


class TestResolverFullIntegration:
    """Integration tests covering full resolution paths."""

    def test_message_with_variable_and_text_elements(self) -> None:
        """Pattern with TextElement and Placeable(VariableReference)."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("greeting = Hello, { $name }!")

        result, errors = bundle.format_pattern("greeting", {"name": "Alice"})
        assert result == "Hello, Alice!"
        assert len(errors) == 0

    def test_message_with_multiple_placeables(self) -> None:
        """Pattern with multiple placeables."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("info = Name: { $name }, Age: { $age }, City: { $city }")

        result, errors = bundle.format_pattern("info", {"name": "Bob", "age": 30, "city": "NYC"})
        assert "Bob" in result
        assert "30" in result
        assert "NYC" in result
        assert len(errors) == 0

    def test_message_with_isolating_enabled(self) -> None:
        """Placeables with Unicode bidi isolation marks."""
        bundle = FluentBundle("en_US", use_isolating=True)
        bundle.add_resource("rtl = Value: { $text }")

        result, errors = bundle.format_pattern("rtl", {"text": "العربية"})
        assert "\u2068" in result
        assert "\u2069" in result
        assert "العربية" in result
        assert len(errors) == 0

    def test_error_in_placeable_produces_fallback(self) -> None:
        """Error in placeable resolution produces fallback."""
        bundle = FluentBundle("en_US", use_isolating=False, strict=False)
        bundle.add_resource("msg = Start { $missing } End")

        result, errors = bundle.format_pattern("msg")
        assert len(errors) == 1
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE
        assert "Start" in result
        assert "End" in result
        assert "{$missing}" in result

    def test_resolution_with_empty_args(self) -> None:
        """Resolution with None args is treated as empty dict."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("simple = Just text")

        result, errors = bundle.format_pattern("simple", None)
        assert result == "Just text"
        assert len(errors) == 0

    @given(
        text=st.text(min_size=0, max_size=100),
        var_value=st.text(min_size=1, max_size=50),
    )
    def test_resolution_with_arbitrary_text(self, text: str, var_value: str) -> None:
        """Property: Resolver handles arbitrary text and variable values."""
        event(f"text_len={len(text)}")
        assume(not any(c in text for c in "{}[]#.=-*\n\r"))
        assume(text.strip() == text)

        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(f"msg = {text} {{ $var }}")

        result, errors = bundle.format_pattern("msg", {"var": var_value})
        assert not errors
        assert var_value in result
        if text:
            assert text in result


# ============================================================================
# EMPTY PATTERN AND PATTERN ELEMENT LOOP
# ============================================================================


class TestEmptyPatternBranchCoverage:
    """Test empty pattern case in _resolve_pattern (branch 242->238)."""

    def test_message_with_empty_value(self) -> None:
        """Message with no value (only attributes) returns empty string."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(
            """
msg =
    .attr = Attribute value
"""
        )

        result, _ = bundle.format_pattern("msg")
        assert result == ""


class TestPatternElementLoopCoverage:
    """Test pattern element loop continuation (branch 242->238)."""

    def test_mixed_text_and_placeables_in_pattern(self) -> None:
        """Multiple elements in pattern (Text -> Placeable -> Text -> Placeable)."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(
            """
multi = Start { $a } middle { $b } end
"""
        )

        result, _ = bundle.format_pattern("multi", {"a": "A", "b": "B"})
        assert result == "Start A middle B end"

    def test_alternating_text_and_placeables(self) -> None:
        """Alternating placeables and text exercises loop continuation."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource(
            """
long = { $x }{ $y }{ $z }done
"""
        )

        result, _ = bundle.format_pattern("long", {"x": "1", "y": "2", "z": "3"})
        assert result == "123done"
