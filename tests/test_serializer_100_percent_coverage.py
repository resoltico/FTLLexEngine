"""Additional tests to achieve 100% coverage for serializer.py.

Targets specific branch coverage gaps identified in coverage report.

Python 3.13+.
"""

from __future__ import annotations

from decimal import Decimal
from typing import cast
from unittest.mock import patch

import pytest

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.syntax.ast import (
    CallArguments,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.serializer import (
    FluentSerializer,
    SerializationDepthError,
    serialize,
)

# ============================================================================
# Non-RESOLUTION FrozenFluentError (Lines 281-285, 360)
# ============================================================================


class TestNonResolutionErrorHandling:
    """Test defensive error handling for non-RESOLUTION FrozenFluentErrors.

    These lines are architecturally unreachable in normal operation but exist
    as defensive programming. We test them via mocking to achieve 100% coverage.
    """

    def test_validate_resource_reraises_non_resolution_error(self) -> None:
        """COVERAGE: Lines 281-285 - Re-raise non-RESOLUTION FrozenFluentError."""
        # Create a simple valid resource
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Mock _validate_pattern to raise a non-RESOLUTION FrozenFluentError
        non_resolution_error = FrozenFluentError(
            "Test error",
            ErrorCategory.FORMATTING,  # Not RESOLUTION
        )

        with patch(
            "ftllexengine.syntax.serializer._validate_pattern",
            side_effect=non_resolution_error,
        ):
            with pytest.raises(FrozenFluentError) as exc_info:
                serialize(resource, validate=True)

            # Should re-raise the original error, not wrap it
            assert exc_info.value is non_resolution_error
            assert exc_info.value.category == ErrorCategory.FORMATTING

    def test_serialize_reraises_non_resolution_error(self) -> None:
        """COVERAGE: Line 360 - Re-raise non-RESOLUTION FrozenFluentError during serialization."""
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Mock _serialize_resource to raise a non-RESOLUTION FrozenFluentError
        non_resolution_error = FrozenFluentError(
            "Serialization error",
            ErrorCategory.REFERENCE,  # Not RESOLUTION
        )

        serializer = FluentSerializer()
        with patch.object(
            serializer,
            "_serialize_resource",
            side_effect=non_resolution_error,
        ):
            with pytest.raises(FrozenFluentError) as exc_info:
                serializer.serialize(resource, validate=False)

            # Should re-raise the original error
            assert exc_info.value is non_resolution_error
            assert exc_info.value.category == ErrorCategory.REFERENCE

    def test_validate_resource_wraps_resolution_error(self) -> None:
        """Verify RESOLUTION errors ARE wrapped (existing behavior)."""
        # Create deeply nested structure to trigger depth limit
        expr: Placeable | VariableReference = VariableReference(
            id=Identifier(name="v")
        )
        for _ in range(105):  # Exceed default depth of 100
            expr = Placeable(expression=expr)

        # After 105 iterations, expr is guaranteed to be Placeable
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(cast(Placeable, expr),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        # Should wrap RESOLUTION error in SerializationDepthError
        with pytest.raises(SerializationDepthError) as exc_info:
            serialize(resource, validate=True)

        assert "depth" in str(exc_info.value).lower()


# ============================================================================
# FunctionReference argument validation branch
# ============================================================================


class TestFunctionReferenceEmptyArguments:
    """Test FunctionReference with truly empty CallArguments.

    This tests the branch where expr.arguments evaluates to empty
    (no positional and no named arguments).
    """

    def test_function_with_completely_empty_arguments(self) -> None:
        """COVERAGE: Branch 238 - FunctionReference with empty CallArguments."""
        # Create FunctionReference with explicitly empty arguments
        func_ref = FunctionReference(
            id=Identifier(name="EMPTY_FUNC"),
            arguments=CallArguments(positional=(), named=()),
        )

        pattern = Pattern(elements=(Placeable(expression=func_ref),))
        message = Message(id=Identifier(name="test"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        # Should serialize successfully even with empty arguments
        result = serialize(resource, validate=True)

        assert "EMPTY_FUNC()" in result


# ============================================================================
# Additional branch coverage tests
# ============================================================================


class TestRemainingBranches:
    """Tests for remaining branch coverage gaps."""

    def test_junk_entry_in_resource(self) -> None:
        """COVERAGE: Branch 429 - Junk case in _serialize_entry."""
        # Explicitly test Junk as an entry type
        junk1 = Junk(content="### Bad syntax ###")
        junk2 = Junk(content="More junk\n")

        resource = Resource(entries=(junk1, junk2))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        assert "### Bad syntax ###" in result
        assert "More junk" in result

    def test_placeable_in_pattern_loop(self) -> None:
        """COVERAGE: Branch 592 - Placeable isinstance in pattern loop."""
        # Create pattern with alternating TextElement and Placeable
        pattern = Pattern(
            elements=(
                TextElement(value="A"),
                Placeable(expression=VariableReference(id=Identifier(name="x"))),
                TextElement(value="B"),
                Placeable(expression=VariableReference(id=Identifier(name="y"))),
                TextElement(value="C"),
            )
        )

        message = Message(id=Identifier(name="test"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        result = serialize(resource, validate=False)

        assert "A" in result
        assert "$x" in result
        assert "B" in result
        assert "$y" in result
        assert "C" in result

    def test_nested_placeable_in_expression(self) -> None:
        """COVERAGE: Branch 693 - Placeable case in _serialize_expression."""
        # Deeply nested Placeable expressions
        inner = VariableReference(id=Identifier(name="v"))
        level1 = Placeable(expression=inner)
        level2 = Placeable(expression=level1)
        level3 = Placeable(expression=level2)

        pattern = Pattern(elements=(level3,))
        message = Message(id=Identifier(name="test"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        result = serialize(resource, validate=False)

        # Should have nested placeable structure
        assert "$v" in result
        brace_count = result.count("{")
        assert brace_count >= 3  # At least 3 levels of nesting

    def test_number_literal_variant_key_serialization(self) -> None:
        """COVERAGE: Branch 741-744 - NumberLiteral variant key."""
        # SelectExpression with NumberLiteral keys (not Identifier)
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="num")),
            variants=(
                Variant(
                    key=NumberLiteral(value=Decimal("42"), raw="42"),
                    value=Pattern(elements=(TextElement(value="Forty-two"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=Decimal("99"), raw="99"),
                    value=Pattern(elements=(TextElement(value="Ninety-nine"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select),))
        message = Message(id=Identifier(name="test"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        result = serialize(resource, validate=False)

        # Verify NumberLiteral keys are serialized
        assert "[42]" in result
        assert "*[99]" in result


# ============================================================================
# Edge case combinations
# ============================================================================


class TestEdgeCaseCombinations:
    """Test combinations of edge cases to ensure full coverage."""

    def test_all_uncovered_branches_together(self) -> None:
        """Integration: Combine all previously uncovered branches."""
        # Junk entry
        junk = Junk(content="junk\n")

        # Message with Placeable in pattern
        msg1 = Message(
            id=Identifier(name="msg1"),
            value=Pattern(
                elements=(
                    TextElement(value="Value: "),
                    Placeable(expression=VariableReference(id=Identifier(name="v"))),
                )
            ),
            attributes=(),
        )

        # Message with SelectExpression using NumberLiteral keys
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="n")),
            variants=(
                Variant(
                    key=NumberLiteral(value=Decimal("1"), raw="1"),
                    value=Pattern(elements=(TextElement(value="One"),)),
                    default=True,
                ),
            ),
        )
        msg2 = Message(
            id=Identifier(name="msg2"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )

        # Message with nested Placeable
        nested = Placeable(
            expression=Placeable(expression=VariableReference(id=Identifier(name="x")))
        )
        msg3 = Message(
            id=Identifier(name="msg3"),
            value=Pattern(elements=(nested,)),
            attributes=(),
        )

        # Message with FunctionReference with empty arguments
        func = FunctionReference(
            id=Identifier(name="FUNC"), arguments=CallArguments(positional=(), named=())
        )
        msg4 = Message(
            id=Identifier(name="msg4"),
            value=Pattern(elements=(Placeable(expression=func),)),
            attributes=(),
        )

        resource = Resource(entries=(junk, msg1, msg2, msg3, msg4))

        result = serialize(resource, validate=False)

        # Verify all elements are present
        assert "junk" in result
        assert "$v" in result
        assert "[1]" in result
        assert "$x" in result
        assert "FUNC()" in result
