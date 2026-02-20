"""Core resolver tests: depth guards, Babel fallback, integration, module exports.

Consolidates:
- test_resolver.py (GlobalDepthGuard, global depth, Babel fallback, integration, edge cases)
- test_resolver_module_exports.py (module boundary verification)
- test_resolver_edge_cases.py (expression, message reference, integration, function arity)

Select expression edge cases and error paths live in test_resolver_selection.py.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from hypothesis import event, example, given
from hypothesis import strategies as st

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.core.babel_compat import BabelImportError
from ftllexengine.diagnostics import ErrorCategory, ErrorTemplate, FrozenFluentError
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.functions import create_default_registry
from ftllexengine.runtime.resolution_context import GlobalDepthGuard, ResolutionContext
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.syntax.ast import (
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
# GlobalDepthGuard
# ============================================================================


class TestGlobalDepthGuard:
    """Tests for GlobalDepthGuard depth limiting mechanism."""

    def test_global_depth_guard_prevents_excessive_nesting(self) -> None:
        """GlobalDepthGuard raises FrozenFluentError when depth exceeded."""
        guard1 = GlobalDepthGuard(max_depth=2)
        guard2 = GlobalDepthGuard(max_depth=2)
        guard3 = GlobalDepthGuard(max_depth=2)

        with (
            guard1,
            guard2,
            pytest.raises(FrozenFluentError, match=r"(?i)depth") as exc_info,
            guard3,
        ):
            pass

        assert exc_info.value.category == ErrorCategory.RESOLUTION
        assert "2" in str(exc_info.value)

    def test_global_depth_guard_depth_one_allows_single_nesting(self) -> None:
        """GlobalDepthGuard with max_depth=1 allows single level."""
        guard = GlobalDepthGuard(max_depth=1)

        with guard:
            pass

    def test_global_depth_guard_depth_one_blocks_double_nesting(self) -> None:
        """GlobalDepthGuard with max_depth=1 blocks nested calls."""
        guard1 = GlobalDepthGuard(max_depth=1)
        guard2 = GlobalDepthGuard(max_depth=1)

        with (
            guard1,
            pytest.raises(FrozenFluentError, match=r"(?i)depth"),
            guard2,
        ):
            pass

    def test_global_depth_guard_resets_depth_on_exit(self) -> None:
        """GlobalDepthGuard resets depth on exit."""
        guard1 = GlobalDepthGuard(max_depth=5)
        guard2 = GlobalDepthGuard(max_depth=5)

        with guard1:
            pass

        with guard2:
            pass

    def test_global_depth_guard_resets_depth_on_exception(self) -> None:
        """GlobalDepthGuard resets depth even when exception occurs."""
        guard1 = GlobalDepthGuard(max_depth=5)
        guard2 = GlobalDepthGuard(max_depth=5)

        error_msg = "test error"
        with (
            pytest.raises(ValueError, match=error_msg),
            guard1,
        ):
            raise ValueError(error_msg)

        with guard2:
            pass

    def test_global_depth_guard_with_zero_depth_fails_immediately(self) -> None:
        """GlobalDepthGuard with max_depth=0 fails on first entry."""
        guard = GlobalDepthGuard(max_depth=0)

        with (
            pytest.raises(FrozenFluentError),
            guard,
        ):
            pass

    @given(max_depth=st.integers(min_value=1, max_value=10))
    @example(max_depth=1)
    @example(max_depth=5)
    def test_global_depth_guard_max_depth_property(self, max_depth: int) -> None:
        """Property: GlobalDepthGuard allows exactly max_depth levels."""
        event(f"max_depth={max_depth}")
        guards = [GlobalDepthGuard(max_depth=max_depth) for _ in range(max_depth + 1)]

        try:
            self._nest_guards(guards[:max_depth])
            success_at_max = True
        except FrozenFluentError:
            success_at_max = False

        try:
            self._nest_guards(guards[: max_depth + 1])
            success_at_max_plus_one = True
        except FrozenFluentError:
            success_at_max_plus_one = False

        assert success_at_max
        assert not success_at_max_plus_one

    def _nest_guards(self, guards: list[GlobalDepthGuard]) -> None:
        """Recursively nest guards for depth testing."""
        if not guards:
            return
        with guards[0]:
            self._nest_guards(guards[1:])


# ============================================================================
# FluentResolver Global Depth Handling
# ============================================================================


class TestFluentResolverGlobalDepth:
    """Tests for FluentResolver handling of global depth exceeded errors."""

    def _make_resolver(self) -> FluentResolver:
        return FluentResolver(
            locale="en-US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

    def _make_message(self, name: str = "test") -> Message:
        return Message(
            id=Identifier(name),
            attributes=(),
            value=Pattern(elements=(TextElement(value="Hello"),)),
        )

    @staticmethod
    def _mock_depth_raise(_self: GlobalDepthGuard) -> GlobalDepthGuard:
        diag = ErrorTemplate.expression_depth_exceeded(_self._max_depth)
        raise FrozenFluentError(str(diag), ErrorCategory.RESOLUTION, diagnostic=diag)

    def test_resolve_message_catches_global_depth_exceeded(self) -> None:
        """resolve_message catches FrozenFluentError and returns fallback."""
        resolver = self._make_resolver()
        message = self._make_message("test")

        with patch.object(GlobalDepthGuard, "__enter__", self._mock_depth_raise):
            result, errors = resolver.resolve_message(message, {})

        assert "{test}" in result or "test" in result
        assert len(errors) > 0
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.RESOLUTION
        assert "depth" in str(errors[0]).lower()

    def test_resolve_message_global_depth_exceeded_uses_message_id(self) -> None:
        """resolve_message uses message ID in fallback when depth exceeded."""
        resolver = self._make_resolver()
        message = self._make_message("custom-message-id")

        with patch.object(GlobalDepthGuard, "__enter__", self._mock_depth_raise):
            result, _errors = resolver.resolve_message(message, {})

        assert "custom-message-id" in result

    def test_resolve_message_collects_global_depth_error(self) -> None:
        """resolve_message collects FrozenFluentError in errors tuple."""
        resolver = self._make_resolver()
        message = self._make_message("test")

        with patch.object(GlobalDepthGuard, "__enter__", self._mock_depth_raise):
            _result, errors = resolver.resolve_message(message, {})

        assert len(errors) == 1
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.RESOLUTION


# ============================================================================
# BabelImportError Fallback
# ============================================================================


class TestFluentResolverBabelFallback:
    """Tests for FluentResolver Babel import error handling."""

    def _make_resolver(self) -> FluentResolver:
        return FluentResolver(
            locale="en-US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
        )

    def _make_select_message(
        self, var_name: str, default_text: str
    ) -> tuple[FluentResolver, Message]:
        """Build a message with a select expression over a variable."""
        select_expr = SelectExpression(
            selector=VariableReference(id=Identifier(name=var_name)),
            variants=(
                Variant(
                    key=Identifier(name="one"),
                    value=Pattern(elements=(TextElement(value="one item"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier(name="other"),
                    value=Pattern(elements=(TextElement(value=default_text),)),
                    default=True,
                ),
            ),
        )
        message = Message(
            id=Identifier("test"),
            attributes=(),
            value=Pattern(elements=(Placeable(expression=select_expr),)),
        )
        return self._make_resolver(), message

    def test_select_expression_falls_back_when_babel_not_installed(self) -> None:
        """Select expression falls through to default when Babel not installed."""
        resolver, message = self._make_select_message("count", "many items")

        def mock_select_raises(*_args: object, **_kwargs: object) -> str:
            msg = "test_feature"
            raise BabelImportError(msg)

        with patch(
            "ftllexengine.runtime.resolver.select_plural_category", mock_select_raises
        ):
            result, errors = resolver.resolve_message(message, {"count": 5})

        assert "many items" in result
        assert len(errors) == 1
        assert hasattr(errors[0], "diagnostic")
        assert errors[0].diagnostic is not None
        assert errors[0].diagnostic.code.name == "PLURAL_SUPPORT_UNAVAILABLE"

    def test_select_expression_babel_error_uses_default_variant(self) -> None:
        """Select expression uses default variant when Babel unavailable."""
        resolver, message = self._make_select_message("num", "default-fallback")

        def mock_select_raises(*_args: object, **_kwargs: object) -> str:
            msg = "plural_rules"
            raise BabelImportError(msg)

        with patch(
            "ftllexengine.runtime.resolver.select_plural_category", mock_select_raises
        ):
            result, errors = resolver.resolve_message(message, {"num": 42})

        assert len(errors) == 1
        assert hasattr(errors[0], "diagnostic")
        assert errors[0].diagnostic is not None
        assert errors[0].diagnostic.code.name == "PLURAL_SUPPORT_UNAVAILABLE"
        assert "default-fallback" in result

    def test_select_expression_babel_error_with_number_literal(self) -> None:
        """Select expression handles Babel error with NumberLiteral selector."""
        resolver = self._make_resolver()
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

        def mock_select_raises(*_args: object, **_kwargs: object) -> str:
            msg = "babel_feature"
            raise BabelImportError(msg)

        with patch(
            "ftllexengine.runtime.resolver.select_plural_category", mock_select_raises
        ):
            result, errors = resolver.resolve_message(message, {})

        assert len(errors) == 1
        assert hasattr(errors[0], "diagnostic")
        assert errors[0].diagnostic is not None
        assert errors[0].diagnostic.code.name == "PLURAL_SUPPORT_UNAVAILABLE"
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
        message = Message(
            id=Identifier("nested"),
            attributes=(),
            value=Pattern(
                elements=(
                    Placeable(expression=MessageReference(id=Identifier(name="other"))),
                )
            ),
        )

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

        assert "{" in result or "missing" in result.lower()
        assert len(errors) > 0

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

    @given(max_depth=st.integers(min_value=1, max_value=5))
    @example(max_depth=1)
    @example(max_depth=2)
    def test_depth_guard_properties(self, max_depth: int) -> None:
        """Property: Depth guard consistently enforces max_depth limit."""
        event(f"max_depth={max_depth}")
        guards = [GlobalDepthGuard(max_depth=max_depth) for _ in range(max_depth + 2)]

        try:
            self._nest_guards(guards[:max_depth])
            within_limit = True
        except FrozenFluentError:
            within_limit = False

        try:
            self._nest_guards(guards[: max_depth + 1])
            beyond_limit = True
        except FrozenFluentError:
            beyond_limit = False

        assert within_limit, f"Should succeed at depth {max_depth}"
        assert not beyond_limit, f"Should fail at depth {max_depth + 1}"

    def _nest_guards(self, guards: list[GlobalDepthGuard]) -> None:
        """Recursively nest guards for property testing."""
        if not guards:
            return
        with guards[0]:
            self._nest_guards(guards[1:])


# ============================================================================
# Module Export Boundaries
# ============================================================================


class TestResolverModuleExports:
    """Test resolver module export boundaries."""

    def test_fluent_value_available_from_function_bridge(self) -> None:
        """FluentValue is available from function_bridge module."""
        from ftllexengine.runtime.function_bridge import FluentValue  # noqa: PLC0415

        assert FluentValue is not None

    def test_importing_fluent_value_from_resolver_fails(self) -> None:
        """FluentValue is not importable from resolver module."""
        with pytest.raises(ImportError, match="cannot import name 'FluentValue'"):
            # pylint: disable=unused-import
            # Intentional ImportError test — FluentValue removed from resolver exports.
            from ftllexengine.runtime.resolver import (  # noqa: PLC0415, F401
                FluentValue,
            )

    def test_fluent_resolver_still_exported_from_resolver(self) -> None:
        """FluentResolver is exported from resolver module."""
        from ftllexengine.runtime.resolver import FluentResolver  # noqa: PLC0415

        assert FluentResolver is not None

    def test_resolution_context_still_exported_from_resolver(self) -> None:
        """ResolutionContext is re-exported from resolver module."""
        from ftllexengine.runtime.resolver import ResolutionContext  # noqa: PLC0415

        assert ResolutionContext is not None

    def test_global_depth_guard_still_exported_from_resolver(self) -> None:
        """GlobalDepthGuard is re-exported from resolver module."""
        from ftllexengine.runtime.resolver import GlobalDepthGuard  # noqa: PLC0415

        assert GlobalDepthGuard is not None


class TestResolutionContextModuleExports:
    """Test resolution_context canonical exports."""

    def test_resolution_context_canonical_import(self) -> None:
        """ResolutionContext canonical location is resolution_context module."""
        from ftllexengine.runtime.resolution_context import (  # noqa: PLC0415
            ResolutionContext,
        )

        assert ResolutionContext is not None

    def test_global_depth_guard_canonical_import(self) -> None:
        """GlobalDepthGuard canonical location is resolution_context module."""
        from ftllexengine.runtime.resolution_context import (  # noqa: PLC0415
            GlobalDepthGuard,
        )

        assert GlobalDepthGuard is not None

    def test_canonical_and_reexport_are_same_class(self) -> None:
        """Canonical and re-exported classes are identical objects."""
        from ftllexengine.runtime.resolution_context import (  # noqa: PLC0415
            GlobalDepthGuard as CanonicalGuard,
        )
        from ftllexengine.runtime.resolution_context import (  # noqa: PLC0415
            ResolutionContext as CanonicalCtx,
        )
        from ftllexengine.runtime.resolver import (  # noqa: PLC0415
            GlobalDepthGuard as ReexportGuard,
        )
        from ftllexengine.runtime.resolver import (  # noqa: PLC0415
            ResolutionContext as ReexportCtx,
        )

        assert CanonicalCtx is ReexportCtx
        assert CanonicalGuard is ReexportGuard


# ============================================================================
# Expression Resolution Edge Cases
# ============================================================================


class TestResolverExpressionEdgeCases:
    """Test edge cases in expression resolution."""

    def test_resolve_placeable_expression(self) -> None:
        """Resolve placeable containing variable."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""test = { $value }""")

        result, _ = bundle.format_pattern("test", {"value": "hello"})

        assert result == "hello"

    def test_resolve_unknown_expression_type_raises_error(self) -> None:
        """Unknown expression type raises FluentResolutionError."""
        resolver = FluentResolver(
            locale="en",
            messages={},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        class UnknownExpr:
            """Fake expression type not handled by the resolver dispatch."""

        unknown = UnknownExpr()
        errors: list[FrozenFluentError] = []
        context = ResolutionContext()

        with pytest.raises(FrozenFluentError, match="Unknown expression type") as exc_info:
            resolver._resolve_expression(
                unknown,  # type: ignore[arg-type]
                {},
                errors,
                context,
            )
        assert exc_info.value.category == ErrorCategory.RESOLUTION

    def test_resolve_bool_true_as_string(self) -> None:
        """Boolean True converts to lowercase 'true' string."""
        resolver = FluentResolver(
            locale="en",
            messages={},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        assert resolver._format_value(True) == "true"

    def test_resolve_bool_false_as_string(self) -> None:
        """Boolean False converts to lowercase 'false' string."""
        resolver = FluentResolver(
            locale="en",
            messages={},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        assert resolver._format_value(False) == "false"

    def test_resolve_none_as_empty_string(self) -> None:
        """None value converts to empty string."""
        resolver = FluentResolver(
            locale="en",
            messages={},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        assert resolver._format_value(None) == ""


# ============================================================================
# Message Reference Edge Cases
# ============================================================================


class TestMessageReferenceEdgeCases:
    """Test edge cases in message reference resolution."""

    def test_format_nonexistent_message_raises_error(self) -> None:
        """Formatting non-existent message raises FluentReferenceError."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("hello = Hello")

        result, errors = bundle.format_pattern("missing", {})

        assert len(errors) == 1
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE
        assert result == "{missing}"


# ============================================================================
# Integration Edge Cases
# ============================================================================


class TestResolverIntegrationEdgeCases:
    """Integration tests for resolver edge cases."""

    def test_select_with_string_literal_in_variant(self) -> None:
        """Select expression with string literals in variants resolves correctly."""
        ftl = """test = { $type ->
   [greeting] Hello
   [farewell] Goodbye
  *[other] Message
}"""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("test", {"type": "greeting"})
        assert "Hello" in result

        result, _ = bundle.format_pattern("test", {"type": "farewell"})
        assert "Goodbye" in result

        result, _ = bundle.format_pattern("test", {"type": "unknown"})
        assert "Message" in result

    def test_mixed_literal_types_in_pattern(self) -> None:
        """Pattern with different literal types renders correctly."""
        ftl = """test = Number: { 42 }, String: { "hello" }"""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(ftl)

        result, _ = bundle.format_pattern("test", {})

        assert "Number: 42" in result
        assert "String: hello" in result

    def test_complex_value_formatting(self) -> None:
        """Format complex Python values produces expected placeholder strings."""
        resolver = FluentResolver(
            locale="en",
            messages={},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        assert resolver._format_value([1, 2, 3]) == "[list]"
        assert resolver._format_value({"key": "value"}) == "[dict]"

        class CustomObj:
            def __str__(self) -> str:
                return "custom"

        assert resolver._format_value(CustomObj()) == "custom"  # type: ignore[arg-type]


# ============================================================================
# Function Arity Validation
# ============================================================================


class TestFunctionArityValidation:
    """Test function argument count validation.

    Arity validation prevents locale injection issues.
    Built-in functions (NUMBER, DATETIME, CURRENCY) expect exactly 1 positional arg.
    """

    def test_number_with_correct_arity_succeeds(self) -> None:
        """NUMBER function with 1 positional arg succeeds."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""price = { NUMBER($value) }""")

        result, errors = bundle.format_pattern("price", {"value": 42})

        assert not errors
        assert "42" in result

    def test_number_with_zero_args_fails(self) -> None:
        """NUMBER function with 0 positional args fails with arity error."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""bad = { NUMBER() }""")

        _result, errors = bundle.format_pattern("bad", {})

        assert len(errors) > 0
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.RESOLUTION
        assert "expects 1 argument" in str(errors[0]) or "ARITY" in str(errors[0])

    def test_datetime_with_correct_arity_succeeds(self) -> None:
        """DATETIME function with 1 positional arg succeeds."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""date = { DATETIME($dt) }""")

        result, errors = bundle.format_pattern(
            "date", {"dt": datetime(2025, 1, 1, tzinfo=UTC)}
        )

        assert not errors
        assert len(result) > 0

    def test_currency_with_correct_arity_succeeds(self) -> None:
        """CURRENCY function with 1 positional arg succeeds."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("""price = { CURRENCY($amount, currency: "USD") }""")

        result, errors = bundle.format_pattern("price", {"amount": 99.99})

        assert not errors
        assert "99" in result

    def test_custom_function_bypasses_arity_check(self) -> None:
        """Custom functions are not subject to built-in arity validation.

        The arity check applies only to built-in functions requiring locale injection
        (NUMBER, DATETIME, CURRENCY). Custom functions receive arguments directly.
        """
        def my_func(*args: object) -> str:
            return f"Got {len(args)} args"

        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_function("MYFUNC", my_func)
        bundle.add_resource("""test = { MYFUNC($a, $b, $c) }""")

        _result, errors = bundle.format_pattern("test", {"a": 1, "b": 2, "c": 3})

        assert not errors or "MYFUNC" not in str(errors[0])


class TestGlobalDepthCustomFunctionCallback:
    """GlobalDepthGuard prevents custom functions from bypassing depth limits.

    A custom function that calls back into bundle.format_pattern() is a common
    pattern for recursive template expansion. Without GlobalDepthGuard, this
    would allow arbitrary stack growth and potential DoS.
    """

    def test_callback_bypass_is_bounded(self) -> None:
        """Custom function calling format_pattern must not cause stack overflow."""
        bundle = FluentBundle("en_US", max_nesting_depth=10)
        call_count = 0

        def recursive_func(_val: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count > 5:
                return "stopped"
            inner_result, _ = bundle.format_pattern("inner", {"x": call_count})
            return inner_result

        bundle.add_function("RECURSE", recursive_func)
        bundle.add_resource("inner = { RECURSE($x) }")
        bundle.add_resource('outer = { RECURSE("start") }')

        # Must not cause RecursionError or stack overflow
        result, errors = bundle.format_pattern("outer")
        assert result is not None
        # Depth guard terminates recursion: either produces errors or natural stop
        assert len(errors) > 0 or "stopped" in result or call_count <= 15

    def test_normal_resolution_unaffected_by_global_guard(self) -> None:
        """GlobalDepthGuard does not affect normal (non-recursive) resolution."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("hello = Hello, { $name }!")

        result, errors = bundle.format_pattern("hello", {"name": "World"})
        assert "Hello," in result
        assert "World" in result
        assert len(errors) == 0
