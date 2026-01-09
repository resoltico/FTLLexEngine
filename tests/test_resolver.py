"""Comprehensive tests for runtime.resolver module.

Property-based tests for Fluent message resolver ensuring correct pattern
resolution, depth limiting, error handling, and Babel integration fallbacks.

Coverage Focus:
    - GlobalDepthGuard depth limiting (line 111)
    - FluentResolutionError handling in resolve_message (lines 353-357)
    - BabelImportError fallback in select expressions (lines 736-738)
    - Edge cases and error paths
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.core.babel_compat import BabelImportError
from ftllexengine.diagnostics import ErrorTemplate, FluentResolutionError
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.resolver import FluentResolver, GlobalDepthGuard
from ftllexengine.syntax import (
    Identifier,
    Message,
    MessageReference,
    NumberLiteral,
    Pattern,
    Placeable,
    SelectExpression,
    TextElement,
    VariableReference,
    Variant,
)

# ============================================================================
# GlobalDepthGuard Tests
# ============================================================================


class TestGlobalDepthGuard:
    """Tests for GlobalDepthGuard depth limiting mechanism."""

    def test_global_depth_guard_prevents_excessive_nesting(self) -> None:
        """GlobalDepthGuard raises FluentResolutionError when depth exceeded (line 111)."""
        # Create a guard with max_depth=2
        guard1 = GlobalDepthGuard(max_depth=2)
        guard2 = GlobalDepthGuard(max_depth=2)
        guard3 = GlobalDepthGuard(max_depth=2)

        # First level should succeed
        with (
            guard1,
            guard2,
            pytest.raises(FluentResolutionError, match=r"(?i)depth") as exc_info,
            guard3,
        ):
            pass

        assert "2" in str(exc_info.value)

    def test_global_depth_guard_depth_one_allows_single_nesting(self) -> None:
        """GlobalDepthGuard with max_depth=1 allows single level."""
        guard = GlobalDepthGuard(max_depth=1)

        # Should succeed
        with guard:
            pass

    def test_global_depth_guard_depth_one_blocks_double_nesting(self) -> None:
        """GlobalDepthGuard with max_depth=1 blocks nested calls (line 111)."""
        guard1 = GlobalDepthGuard(max_depth=1)
        guard2 = GlobalDepthGuard(max_depth=1)

        with (
            guard1,
            pytest.raises(FluentResolutionError, match=r"(?i)depth"),
            guard2,
        ):
            pass

    def test_global_depth_guard_resets_depth_on_exit(self) -> None:
        """GlobalDepthGuard resets depth on exit (line 124-125)."""
        guard1 = GlobalDepthGuard(max_depth=5)
        guard2 = GlobalDepthGuard(max_depth=5)

        # First guard succeeds and exits
        with guard1:
            pass

        # Second guard should also succeed (depth was reset)
        with guard2:
            pass

    def test_global_depth_guard_resets_depth_on_exception(self) -> None:
        """GlobalDepthGuard resets depth even when exception occurs (line 124-125)."""
        guard1 = GlobalDepthGuard(max_depth=5)
        guard2 = GlobalDepthGuard(max_depth=5)

        # Raise exception inside guard
        error_msg = "test error"
        with (
            pytest.raises(ValueError, match=error_msg),
            guard1,
        ):
            raise ValueError(error_msg)

        # Depth should be reset, so guard2 should succeed
        with guard2:
            pass

    @given(max_depth=st.integers(min_value=1, max_value=10))
    @example(max_depth=1)
    @example(max_depth=5)
    def test_global_depth_guard_max_depth_property(self, max_depth: int) -> None:
        """Property: GlobalDepthGuard allows exactly max_depth levels."""
        guards = [GlobalDepthGuard(max_depth=max_depth) for _ in range(max_depth + 1)]

        # Should be able to nest up to max_depth levels
        try:
            self._nest_guards(guards[:max_depth])
            success_at_max = True
        except FluentResolutionError:
            success_at_max = False

        # Should fail at max_depth + 1
        try:
            self._nest_guards(guards[: max_depth + 1])
            success_at_max_plus_one = True
        except FluentResolutionError:
            success_at_max_plus_one = False

        assert success_at_max
        assert not success_at_max_plus_one

    def _nest_guards(self, guards: list[GlobalDepthGuard]) -> None:
        """Helper to nest guards recursively."""
        if not guards:
            return
        with guards[0]:
            self._nest_guards(guards[1:])


# ============================================================================
# FluentResolver Global Depth Tests
# ============================================================================


class TestFluentResolverGlobalDepth:
    """Tests for FluentResolver handling of global depth exceeded errors."""

    def test_resolve_message_catches_global_depth_exceeded(self) -> None:
        """resolve_message catches FluentResolutionError and returns fallback (lines 353-357)."""
        # Create a resolver
        resolver = FluentResolver(
            locale="en-US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # Create a simple message
        message = Message(
            id=Identifier("test"),
            attributes=(),
            value=Pattern(elements=(TextElement(value="Hello"),)),
        )

        # Mock GlobalDepthGuard to always raise FluentResolutionError
        def mock_enter_raises(_self: GlobalDepthGuard) -> GlobalDepthGuard:
            raise FluentResolutionError(
                ErrorTemplate.expression_depth_exceeded(_self._max_depth)
            )

        with patch.object(GlobalDepthGuard, "__enter__", mock_enter_raises):
            result, errors = resolver.resolve_message(message, {})

            # Should return fallback
            assert "{test}" in result or "test" in result
            assert len(errors) > 0
            assert isinstance(errors[0], FluentResolutionError)
            assert "depth" in str(errors[0]).lower()

    def test_resolve_message_global_depth_exceeded_uses_message_id(self) -> None:
        """resolve_message uses message ID in fallback when depth exceeded (line 356)."""
        resolver = FluentResolver(
            locale="en-US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # Create message with specific ID
        message = Message(
            id=Identifier("custom-message-id"),
            attributes=(),
            value=Pattern(elements=(TextElement(value="Hello"),)),
        )

        # Mock GlobalDepthGuard to raise
        def mock_enter_raises(_self: GlobalDepthGuard) -> GlobalDepthGuard:
            raise FluentResolutionError(
                ErrorTemplate.expression_depth_exceeded(_self._max_depth)
            )

        with patch.object(GlobalDepthGuard, "__enter__", mock_enter_raises):
            result, _errors = resolver.resolve_message(message, {})

            # Fallback should contain the message ID
            assert "custom-message-id" in result

    def test_resolve_message_collects_global_depth_error(self) -> None:
        """resolve_message collects FluentResolutionError in errors tuple (line 355)."""
        resolver = FluentResolver(
            locale="en-US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        message = Message(
            id=Identifier("test"),
            attributes=(),
            value=Pattern(elements=(TextElement(value="Hello"),)),
        )

        # Mock to raise FluentResolutionError
        def mock_enter_raises(_self: GlobalDepthGuard) -> GlobalDepthGuard:
            raise FluentResolutionError(
                ErrorTemplate.expression_depth_exceeded(_self._max_depth)
            )

        with patch.object(GlobalDepthGuard, "__enter__", mock_enter_raises):
            _result, errors = resolver.resolve_message(message, {})

            # Error should be collected
            assert len(errors) == 1
            assert isinstance(errors[0], FluentResolutionError)


# ============================================================================
# BabelImportError Fallback Tests
# ============================================================================


class TestFluentResolverBabelFallback:
    """Tests for FluentResolver Babel import error handling."""

    def test_select_expression_falls_back_when_babel_not_installed(self) -> None:
        """Select expression falls through to default when Babel not installed (lines 736-738)."""
        # We need to test the BabelImportError path in _resolve_select_expression
        # This occurs when select_plural_category raises BabelImportError

        resolver = FluentResolver(
            locale="en-US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # Create a select expression with plural selector and default variant
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier(name="count")),
            variants=(
                Variant(
                    key=Identifier(name="one"),
                    value=Pattern(elements=(TextElement(value="one item"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier(name="other"),
                    value=Pattern(elements=(TextElement(value="many items"),)),
                    default=True,
                ),
            ),
        )

        # Create message with select expression
        message = Message(
            id=Identifier("test"),
            attributes=(),
            value=Pattern(elements=(Placeable(expression=select_expr),)),
        )

        # Mock select_plural_category to raise BabelImportError
        feature_name = "test_feature"
        def mock_select_raises(*_args: object, **_kwargs: object) -> str:
            raise BabelImportError(feature_name)

        with patch(
            "ftllexengine.runtime.resolver.select_plural_category", mock_select_raises
        ):
            result, errors = resolver.resolve_message(message, {"count": 5})

            # Should fall back to default variant
            assert "many items" in result
            # Should not have errors (Babel fallback is graceful)
            assert len(errors) == 0

    def test_select_expression_babel_error_uses_default_variant(self) -> None:
        """Select expression uses default variant when Babel unavailable (line 738)."""
        resolver = FluentResolver(
            locale="en-US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # Create select with specific default variant text
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier(name="num")),
            variants=(
                Variant(
                    key=Identifier(name="one"),
                    value=Pattern(elements=(TextElement(value="singular"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier(name="other"),
                    value=Pattern(elements=(TextElement(value="default-fallback"),)),
                    default=True,
                ),
            ),
        )

        message = Message(
            id=Identifier("test"),
            attributes=(),
            value=Pattern(elements=(Placeable(expression=select_expr),)),
        )

        # Mock Babel to raise
        feature_name = "plural_rules"
        def mock_select_raises(*_args: object, **_kwargs: object) -> str:
            raise BabelImportError(feature_name)

        with patch(
            "ftllexengine.runtime.resolver.select_plural_category", mock_select_raises
        ):
            result, errors = resolver.resolve_message(message, {"num": 42})

            assert not errors

            # Should use default variant
            assert "default-fallback" in result

    def test_select_expression_babel_error_with_number_literal(self) -> None:
        """Select expression handles Babel error with NumberLiteral selector (lines 736-738)."""
        resolver = FluentResolver(
            locale="en-US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # Use NumberLiteral as selector to trigger numeric path
        select_expr = SelectExpression(
            selector=NumberLiteral(raw="5", value=5),
            variants=(
                Variant(
                    key=Identifier(name="one"),
                    value=Pattern(elements=(TextElement(value="one"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier(name="other"),
                    value=Pattern(elements=(TextElement(value="fallback"),)),
                    default=True,
                ),
            ),
        )

        message = Message(
            id=Identifier("test"),
            attributes=(),
            value=Pattern(elements=(Placeable(expression=select_expr),)),
        )

        # Mock to raise BabelImportError
        feature_name = "babel_feature"
        def mock_select_raises(*_args: object, **_kwargs: object) -> str:
            raise BabelImportError(feature_name)

        with patch(
            "ftllexengine.runtime.resolver.select_plural_category", mock_select_raises
        ):
            result, errors = resolver.resolve_message(message, {})

            assert not errors

            # Should fall back to default
            assert "fallback" in result


# ============================================================================
# Integration Tests
# ============================================================================


class TestFluentResolverIntegration:
    """Integration tests combining multiple resolver features."""

    def test_global_depth_guard_integrates_with_resolver(self) -> None:
        """GlobalDepthGuard integrates properly with resolver operations."""
        resolver = FluentResolver(
            locale="en-US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # Create deeply nested message reference
        message = Message(
            id=Identifier("nested"),
            attributes=(),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier(name="other"))),)
            ),
        )

        # Should work with normal depth
        with GlobalDepthGuard(max_depth=MAX_DEPTH):
            result, _errors = resolver.resolve_message(message, {})
            assert isinstance(result, str)

    def test_resolver_handles_multiple_error_types(self) -> None:
        """Resolver correctly handles and collects multiple error types."""
        resolver = FluentResolver(
            locale="en-US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        # Message with missing variable
        message = Message(
            id=Identifier("test"),
            attributes=(),
            value=Pattern(
                elements=(
                    TextElement(value="Hello "),
                    Placeable(expression=VariableReference(id=Identifier(name="missing"))),
                )
            ),
        )

        result, errors = resolver.resolve_message(message, {})

        # Should have fallback for missing variable
        assert "{" in result or "missing" in result.lower()
        # Should collect error
        assert len(errors) > 0

    @given(max_depth=st.integers(min_value=1, max_value=5))
    @example(max_depth=1)
    @example(max_depth=2)
    def test_depth_guard_properties(self, max_depth: int) -> None:
        """Property: Depth guard consistently enforces max_depth limit."""
        guards = [GlobalDepthGuard(max_depth=max_depth) for _ in range(max_depth + 2)]

        # Should succeed up to max_depth
        try:
            self._nest_guards_property(guards[:max_depth])
            within_limit = True
        except FluentResolutionError:
            within_limit = False

        # Should fail beyond max_depth
        try:
            self._nest_guards_property(guards[: max_depth + 1])
            beyond_limit = True
        except FluentResolutionError:
            beyond_limit = False

        assert within_limit, f"Should succeed at depth {max_depth}"
        assert not beyond_limit, f"Should fail at depth {max_depth + 1}"

    def _nest_guards_property(self, guards: list[GlobalDepthGuard]) -> None:
        """Helper to nest guards for property testing."""
        if not guards:
            return
        with guards[0]:
            self._nest_guards_property(guards[1:])


# ============================================================================
# Edge Cases and Error Paths
# ============================================================================


class TestFluentResolverEdgeCases:
    """Edge case tests for resolver error handling."""

    def test_global_depth_guard_with_zero_depth_fails_immediately(self) -> None:
        """GlobalDepthGuard with max_depth=0 fails on first entry."""
        guard = GlobalDepthGuard(max_depth=0)

        with (
            pytest.raises(FluentResolutionError),
            guard,
        ):
            pass

    def test_resolve_message_returns_tuple_on_success(self) -> None:
        """resolve_message returns (str, tuple) even on success."""
        resolver = FluentResolver(
            locale="en-US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        message = Message(
            id=Identifier("test"),
            attributes=(),
            value=Pattern(elements=(TextElement(value="Hello"),)),
        )

        result, errors = resolver.resolve_message(message, {})

        assert isinstance(result, str)
        assert isinstance(errors, tuple)
        assert result == "Hello"
        assert len(errors) == 0

    def test_resolve_message_with_empty_pattern(self) -> None:
        """resolve_message handles empty pattern correctly."""
        resolver = FluentResolver(
            locale="en-US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

        message = Message(
            id=Identifier("empty"),
            attributes=(),
            value=Pattern(elements=()),
        )

        result, errors = resolver.resolve_message(message, {})

        assert result == ""
        assert len(errors) == 0

    def test_babel_import_error_includes_feature_name(self) -> None:
        """BabelImportError includes feature name in message."""
        error = BabelImportError("test_feature")

        assert "test_feature" in str(error)
        assert "babel" in str(error).lower() or "install" in str(error).lower()
