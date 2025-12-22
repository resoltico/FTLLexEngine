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
