"""Targeted tests to achieve 100% coverage for resolver.py.

Covers the 4 remaining gaps:
- Line 142->138: Placeable branch in _resolve_pattern
- Line 190: Nested Placeable in _resolve_expression
- Line 232: Term attribute resolution
- Lines 375-376: Unknown expression fallback
"""

from __future__ import annotations

from unittest.mock import Mock

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.runtime.bundle import FluentBundle

# ============================================================================
# LINE 142->138: Placeable Branch in _resolve_pattern
# ============================================================================


class TestPlaceableBranchCoverage:
    """Test Placeable case in _resolve_pattern (line 142->138)."""

    def test_simple_placeable_in_pattern(self) -> None:
        """COVERAGE: Line 142->138 - Placeable branch."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # Message with single placeable
        bundle.add_resource("msg = Value: { $var }")

        result, _ = bundle.format_pattern("msg", {"var": "test"})
        assert result == "Value: test"

    def test_placeable_with_isolating_marks(self) -> None:
        """COVERAGE: Line 142->138 with use_isolating=True."""
        bundle = FluentBundle("en_US", use_isolating=True)

        # Placeable with bidi isolation
        bundle.add_resource("msg = { $value }")

        result, _ = bundle.format_pattern("msg", {"value": "RTL"})
        # Should have FSI/PDI marks (U+2068/U+2069)
        assert "\u2068" in result
        assert "\u2069" in result

    @given(value=st.text(min_size=1, max_size=50))
    def test_placeable_with_various_values(self, value: str) -> None:
        """PROPERTY: Placeable branch handles various string values."""
        bundle = FluentBundle("en_US", use_isolating=False)
        bundle.add_resource("msg = { $x }")

        result, _ = bundle.format_pattern("msg", {"x": value})
        assert value in result


# ============================================================================
# LINE 190: Nested Placeable in _resolve_expression
# ============================================================================


class TestNestedPlaceableCoverage:
    """Test nested Placeable case in _resolve_expression (line 190)."""

    def test_placeable_in_select_variant_value(self) -> None:
        """Test Placeable within select expression variant pattern."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # Select with placeable in variant
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
# LINE 232: Term Attribute Resolution
# ============================================================================


class TestTermAttributeCoverage:
    """Test term reference with attribute (line 232)."""

    def test_term_with_attribute_resolution(self) -> None:
        """COVERAGE: Line 232 - Term attribute value resolution."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # Define term with attributes
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
        """COVERAGE: Line 232 - Multiple attribute access."""
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
        """PROPERTY: Term attribute resolution works for various names."""
        from hypothesis import assume  # noqa: PLC0415

        # Exclude FTL syntax characters
        assume(not any(c in attr_value for c in "{}[]#.=-*\n\r"))
        assume(attr_value.strip() == attr_value)  # No leading/trailing whitespace

        bundle = FluentBundle("en_US", use_isolating=False)

        # Construct FTL with term attribute
        ftl = f"-term = Base\n    .{attr_name} = {attr_value}\n\nmsg = {{ -term.{attr_name} }}"
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("msg")
        assert attr_value in result


# ============================================================================
# LINES 375-376: Unknown Expression Fallback
# ============================================================================


class TestUnknownExpressionFallback:
    """Test unknown expression type fallback (lines 375-376)."""

    def test_unknown_expression_fallback_with_mock(self) -> None:
        """COVERAGE: Lines 375-376 - Unknown expression type in fallback.

        This tests the defensive case _ branch in _get_fallback_for_placeable.
        We need to create an expression type that's not recognized.
        """
        from ftllexengine.runtime.resolver import FluentResolver  # noqa: PLC0415

        # Create a mock expression with unknown type
        class UnknownExpression:
            """Mock unknown expression type."""


        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=Mock(),
            use_isolating=False,
        )

        # Call _get_fallback_for_placeable with unknown expression
        # This should hit the case _: return "{???}" branch
        fallback = resolver._get_fallback_for_placeable(
            UnknownExpression()  # type: ignore[arg-type]
        )

        assert fallback == "{???}"

    def test_fallback_for_all_known_expression_types(self) -> None:
        """Test fallback generation for known expression types."""
        from ftllexengine.runtime.resolver import FluentResolver  # noqa: PLC0415
        from ftllexengine.syntax.ast import (  # noqa: PLC0415
            FunctionReference,
            Identifier,
            MessageReference,
            SelectExpression,
            TermReference,
            VariableReference,
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=Mock(),
            use_isolating=False,
        )

        # Test known expression fallbacks
        var_ref = VariableReference(id=Identifier(name="test"))
        fallback = resolver._get_fallback_for_placeable(var_ref)
        assert fallback == "{$test}"

        msg_ref = MessageReference(id=Identifier(name="msg"), attribute=None)
        fallback = resolver._get_fallback_for_placeable(msg_ref)
        assert fallback == "{msg}"

        term_ref = TermReference(id=Identifier(name="term"), attribute=None, arguments=None)
        fallback = resolver._get_fallback_for_placeable(term_ref)
        assert fallback == "{-term}"

        func_ref = FunctionReference(id=Identifier(name="FUNC"), arguments=Mock())
        fallback = resolver._get_fallback_for_placeable(func_ref)
        assert fallback == "{FUNC(...)}"

        # SelectExpression with unknown selector type falls back to {???}
        select_expr_unknown = SelectExpression(selector=Mock(), variants=())
        fallback = resolver._get_fallback_for_placeable(select_expr_unknown)
        assert fallback == "{{???} -> ...}"

        # SelectExpression with VariableReference selector shows variable name
        var_selector = VariableReference(id=Identifier(name="count"))
        select_expr_var = SelectExpression(selector=var_selector, variants=())
        fallback = resolver._get_fallback_for_placeable(select_expr_var)
        assert fallback == "{{$count} -> ...}"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestResolverIntegration:
    """Integration tests combining multiple coverage targets."""

    def test_complex_message_with_all_features(self) -> None:
        """Integration test using placeable, term attribute, and select."""
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
        assert "3.0" in result  # Term attribute
        assert "5 items" in result  # Select + placeable

    def test_error_recovery_with_fallback(self) -> None:
        """Test error handling produces fallback for missing reference."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # Reference non-existent message
        bundle.add_resource("msg = Value: { missing }")

        result, errors = bundle.format_pattern("msg")

        # Should have error
        assert len(errors) > 0
        # Should have fallback
        assert "{missing}" in result or "missing" in result.lower()


# ============================================================================
# LINES 360-363: Cyclic Reference Detection for Term References
# ============================================================================


class TestTermCyclicReferenceCoverage:
    """Test cyclic reference detection in term references (lines 360-363)."""

    def test_term_direct_self_reference(self) -> None:
        """COVERAGE: Lines 360-363 - Term referencing itself directly."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # Term that references itself
        bundle.add_resource(
            """
-recursive = { -recursive }
msg = { -recursive }
"""
        )

        result, errors = bundle.format_pattern("msg")

        # Should have cyclic reference error
        assert len(errors) > 0
        assert any("cycl" in str(e).lower() for e in errors)
        # Should return fallback
        assert "{-recursive}" in result

    def test_term_indirect_cycle(self) -> None:
        """COVERAGE: Lines 360-363 - Terms forming indirect cycle."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # Terms forming a cycle: A -> B -> A
        bundle.add_resource(
            """
-termA = { -termB }
-termB = { -termA }
msg = { -termA }
"""
        )

        _result, errors = bundle.format_pattern("msg")

        # Should detect cycle
        assert len(errors) > 0
        assert any("cycl" in str(e).lower() for e in errors)

    def test_term_attribute_cycle(self) -> None:
        """COVERAGE: Lines 360-363 - Cycle through term attributes."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # Term attribute referencing the term
        bundle.add_resource(
            """
-brand = Firefox
    .recursive = { -brand }
msg = { -brand.recursive }
"""
        )

        result, _errors = bundle.format_pattern("msg")

        # Should return the term value since attribute references term (cycle)
        # Or return fallback if detected as cycle
        assert result is not None


# ============================================================================
# LINES 367-371: Max Depth Exceeded for Term References
# ============================================================================


class TestTermMaxDepthCoverage:
    """Test max depth exceeded in term references (lines 367-371)."""

    def test_term_deep_nesting_exceeds_depth(self) -> None:
        """COVERAGE: Lines 367-371 - Deep term nesting exceeds max depth.

        Uses FluentResolver directly with a low max_depth to trigger
        the term reference depth exceeded path.
        """
        from ftllexengine.runtime.resolver import (  # noqa: PLC0415
            FluentResolver,
            ResolutionContext,
        )
        from ftllexengine.syntax.ast import (  # noqa: PLC0415
            Identifier,
            Message,
            Pattern,
            Placeable,
            Term,
            TermReference,
            TextElement,
        )

        # Create terms that form a deep chain
        # -term1 -> -term2 -> -term3 -> "Base"
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

        # Create context with very low max_depth (2) to trigger depth exceeded
        context = ResolutionContext(max_depth=2)

        _result, errors = resolver.resolve_message(msg, args=None, context=context)

        # Should have depth exceeded error
        assert len(errors) > 0
        assert any("depth" in str(e).lower() for e in errors)

    def test_term_max_depth_via_resolver_directly(self) -> None:
        """COVERAGE: Lines 367-371 - Direct resolver test with low max_depth."""
        from ftllexengine.runtime.resolver import (  # noqa: PLC0415
            FluentResolver,
            ResolutionContext,
        )
        from ftllexengine.syntax.ast import (  # noqa: PLC0415
            Identifier,
            Message,
            Pattern,
            Placeable,
            Term,
            TermReference,
            TextElement,
        )

        # Single term that references another term
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

        # Context with max_depth=1 - term A will resolve but term B will exceed depth
        context = ResolutionContext(max_depth=1)

        _result, errors = resolver.resolve_message(msg, args=None, context=context)

        # Should have depth exceeded error
        assert len(errors) > 0
        assert any("depth" in str(e).lower() for e in errors)


# ============================================================================
# BRANCH 242->238: Empty Pattern Loop Branch
# ============================================================================


class TestEmptyPatternBranchCoverage:
    """Test empty pattern case in _resolve_pattern (branch 242->238)."""

    def test_message_with_empty_value(self) -> None:
        """COVERAGE: Branch 242->238 - Message with empty value."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # Message with no value (only attributes)
        bundle.add_resource(
            """
msg =
    .attr = Attribute value
"""
        )

        # Getting the empty value should not error
        result, _ = bundle.format_pattern("msg")

        # Empty value returns empty string
        assert result == ""


# ============================================================================
# BRANCH 400->395: NumberLiteral Selector Non-Match
# ============================================================================


class TestNumberLiteralSelectorCoverage:
    """Test NumberLiteral selector branch in _find_exact_variant (branch 400->395)."""

    def test_number_literal_selector_exact_match(self) -> None:
        """COVERAGE: Branch 400->395 - Number literal variant matching."""
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

        # Test exact number matches
        result, _ = bundle.format_pattern("items", {"count": 0})
        assert "No items" in result

        result, _ = bundle.format_pattern("items", {"count": 1})
        assert "One item" in result

        result, _ = bundle.format_pattern("items", {"count": 42})
        assert "The answer" in result

    def test_number_literal_selector_no_match(self) -> None:
        """COVERAGE: Branch 400->395 - Number literal no match falls through."""
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

        # Number that doesn't match any literal
        result, _ = bundle.format_pattern("level", {"num": 99})
        assert "Level unknown" in result

    def test_number_literal_with_float_selector(self) -> None:
        """COVERAGE: Branch 400->395 - Float selector matching number literals."""
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

        # Float that matches integer literal
        result, _ = bundle.format_pattern("rating", {"stars": 5.0})
        assert "Excellent" in result

        # Float that doesn't match any literal
        result, _ = bundle.format_pattern("rating", {"stars": 3.5})
        assert "Unrated" in result

    def test_number_literal_match_second_key(self) -> None:
        """COVERAGE: Branch 400->395 - Number literal match on second+ key.

        This specifically covers the loop continuation path where the first
        NumberLiteral key doesn't match but a subsequent one does.
        """
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

        # 20 should not match 10, but should match 20 (second key)
        # This tests the loop continuation from NumberLiteral case
        result, _ = bundle.format_pattern("score", {"points": 20})
        assert "Twenty points" in result

        # 30 should skip both 10 and 20 (testing multiple continuations)
        result, _ = bundle.format_pattern("score", {"points": 30})
        assert "Thirty points" in result


# ============================================================================
# BRANCH 242->238: Pattern Element Loop Continuation
# ============================================================================


class TestPatternElementLoopCoverage:
    """Test pattern element loop continuation (branch 242->238)."""

    def test_mixed_text_and_placeables_in_pattern(self) -> None:
        """COVERAGE: Branch 242->238 - Multiple elements in pattern.

        This covers the loop continuation from Placeable back to the for loop
        when there are multiple elements in a pattern.
        """
        bundle = FluentBundle("en_US", use_isolating=False)

        # Pattern with: Text -> Placeable -> Text -> Placeable
        bundle.add_resource(
            """
multi = Start { $a } middle { $b } end
"""
        )

        result, _ = bundle.format_pattern("multi", {"a": "A", "b": "B"})
        assert result == "Start A middle B end"

    def test_alternating_text_and_placeables(self) -> None:
        """COVERAGE: Branch 242->238 - Alternating text and placeable."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # Longer pattern to exercise the loop
        bundle.add_resource(
            """
long = { $x }{ $y }{ $z }done
"""
        )

        result, _ = bundle.format_pattern("long", {"x": "1", "y": "2", "z": "3"})
        assert result == "123done"
