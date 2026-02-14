"""Absolute coverage tests for runtime resolver module.

Tests for specific branches to achieve 100% line and branch coverage.
Targets uncovered branches identified by coverage analysis:
- GlobalDepthGuard edge cases
- Pattern resolution edge cases
- Variant matching with malformed NumberLiterals
- Fallback depth protection
"""

from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.constants import FALLBACK_INVALID
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.resolution_context import GlobalDepthGuard
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.syntax.ast import (
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


class TestGlobalDepthGuardEdgeCases:
    """Coverage for GlobalDepthGuard.__exit__ edge case (line 124->exit)."""

    def test_exit_without_enter(self) -> None:
        """Guard exit without enter leaves _token as None."""
        guard = GlobalDepthGuard(max_depth=100)
        # Explicitly do NOT call __enter__, so _token remains None
        # Call __exit__ directly to cover the "if self._token is not None" branch
        # where _token is None (defensive programming case)
        guard.__exit__(None, None, None)
        # No assertion needed - we're testing that this doesn't crash

    def test_exit_returns_none(self) -> None:
        """Guard __exit__ always returns None (doesn't suppress exceptions)."""
        guard = GlobalDepthGuard(max_depth=100)
        with guard:
            pass
        # __exit__ implicitly called by context manager, returns None (no exception suppression)


class TestPatternMultiplePlaceables:
    """Coverage for pattern with multiple consecutive placeables (line 390->386)."""

    def test_pattern_with_two_placeables_in_sequence(self) -> None:
        """Pattern with consecutive placeables iterates loop correctly."""
        # Create pattern: "{ $first } and { $second }"
        pattern = Pattern(
            elements=(
                Placeable(expression=VariableReference(id=Identifier("first"))),
                TextElement(value=" and "),
                Placeable(expression=VariableReference(id=Identifier("second"))),
            )
        )
        message = Message(
            id=Identifier("msg"),
            value=pattern,
            attributes=(),
        )

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(
            message, {"first": "A", "second": "B"}
        )
        assert result == "A and B"
        assert errors == ()

    @given(
        count=st.integers(min_value=2, max_value=10),
        values=st.lists(st.text(min_size=1, max_size=10), min_size=2, max_size=10),
    )
    def test_pattern_with_multiple_placeables_property(
        self, count: int, values: list[str]
    ) -> None:
        """Pattern with N placeables resolves all correctly."""
        event(f"count={count}")
        # Ensure values list matches count
        values = values[:count]
        if len(values) < count:
            values.extend(["X"] * (count - len(values)))

        # Build pattern with N placeables separated by spaces
        elements: list[TextElement | Placeable] = []
        for i in range(count):
            if i > 0:
                elements.append(TextElement(value=" "))
            elements.append(
                Placeable(expression=VariableReference(id=Identifier(f"v{i}")))
            )

        pattern = Pattern(elements=tuple(elements))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        args = {f"v{i}": values[i] for i in range(count)}
        result, errors = resolver.resolve_message(message, args)

        assert errors == ()
        assert result == " ".join(values)


class TestVariantMatchingMalformedNumberLiteral:
    """Coverage for InvalidOperation handling in _find_exact_variant (line 616->611)."""

    def test_malformed_number_literal_raw_skipped(self) -> None:
        """Variant with malformed NumberLiteral.raw is skipped gracefully."""
        # Construct a SelectExpression with a variant containing an invalid
        # NumberLiteral.raw string. This can only happen via programmatic
        # AST construction (parser would reject it).
        # The InvalidOperation exception should be caught and the variant skipped.

        # Create malformed NumberLiteral with invalid raw string
        malformed_variant = Variant(
            key=NumberLiteral(value=42, raw="not_a_number"),
            value=Pattern(elements=(TextElement(value="malformed"),)),
            default=False,
        )

        # Create valid default variant
        default_variant = Variant(
            key=Identifier("other"),
            value=Pattern(elements=(TextElement(value="default"),)),
            default=True,
        )

        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("count")),
            variants=(malformed_variant, default_variant),
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

        # Pass a numeric value that would match if the raw string was valid
        result, errors = resolver.resolve_message(message, {"count": 42})

        # Should fall back to default variant since malformed variant is skipped
        assert result == "default"
        assert errors == ()

    def test_multiple_malformed_literals_all_skipped(self) -> None:
        """Multiple malformed NumberLiterals are all skipped."""
        variants = [
            Variant(
                key=NumberLiteral(value=1, raw="invalid1"),
                value=Pattern(elements=(TextElement(value="v1"),)),
                default=False,
            ),
            Variant(
                key=NumberLiteral(value=2, raw="also_invalid"),
                value=Pattern(elements=(TextElement(value="v2"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="fallback"),)),
                default=True,
            ),
        ]

        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("n")),
            variants=tuple(variants),
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

        result, errors = resolver.resolve_message(message, {"n": 1})
        assert result == "fallback"
        assert errors == ()


class TestGetFallbackForPlaceableDepthProtection:
    """Coverage for depth protection in _get_fallback_for_placeable (line 932)."""

    def test_fallback_depth_zero_returns_invalid(self) -> None:
        """Fallback with depth=0 returns FALLBACK_INVALID immediately."""
        resolver = FluentResolver(
            locale="en",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # Call _get_fallback_for_placeable with depth=0
        # Use a SelectExpression to test the recursive case
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("x")),
            variants=(
                Variant(
                    key=Identifier("other"),
                    value=Pattern(elements=(TextElement(value="v"),)),
                    default=True,
                ),
            ),
        )

        result = resolver._get_fallback_for_placeable(
            select_expr, depth=0
        )
        assert result == FALLBACK_INVALID

    def test_fallback_negative_depth_returns_invalid(self) -> None:
        """Fallback with negative depth returns FALLBACK_INVALID."""
        resolver = FluentResolver(
            locale="en",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result = resolver._get_fallback_for_placeable(
            VariableReference(id=Identifier("x")), depth=-1
        )
        assert result == FALLBACK_INVALID

    @given(depth=st.integers(max_value=0))
    def test_fallback_non_positive_depth_property(self, depth: int) -> None:
        """Any non-positive depth returns FALLBACK_INVALID immediately."""
        event(f"depth={depth}")
        resolver = FluentResolver(
            locale="en",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # Use StringLiteral as simplest expression type
        result = resolver._get_fallback_for_placeable(
            StringLiteral(value="test"), depth=depth
        )
        assert result == FALLBACK_INVALID

    def test_fallback_depth_one_processes_normally(self) -> None:
        """Fallback with depth=1 processes expression normally."""
        resolver = FluentResolver(
            locale="en",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # VariableReference with depth=1 should return {$varname}
        result = resolver._get_fallback_for_placeable(
            VariableReference(id=Identifier("count")), depth=1
        )
        assert result == "{$count}"

    def test_fallback_select_expression_depth_decremented(self) -> None:
        """SelectExpression fallback decrements depth for recursive call."""
        resolver = FluentResolver(
            locale="en",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # Create SelectExpression with VariableReference selector
        # The fallback will recursively call itself for the selector
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier("count")),
            variants=(
                Variant(
                    key=Identifier("x"),
                    value=Pattern(elements=(TextElement(value="variant"),)),
                    default=True,
                ),
            ),
        )

        # With depth=1, the outer select should process successfully
        # and generate "{{selector} -> ...}" format, where selector is
        # the fallback from the recursive call with depth=0, which returns FALLBACK_INVALID
        result = resolver._get_fallback_for_placeable(
            select_expr, depth=1
        )
        # Result should be "{{{???}} -> ...}" since depth-1=0 returns {???}
        assert FALLBACK_INVALID in result
        assert " -> ..." in result
