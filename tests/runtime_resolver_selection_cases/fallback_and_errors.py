# mypy: ignore-errors
# mypy: ignore-errors
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.diagnostics import ErrorCategory, FrozenFluentError
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.syntax.ast import (
    CallArguments,
    FunctionReference,
    Identifier,
    Message,
    Pattern,
    Placeable,
    SelectExpression,
    StringLiteral,
    TextElement,
    VariableReference,
    Variant,
)

# ============================================================================
# PATTERN LOOP CONTINUATION
# ============================================================================



class TestFallbackVariantNoVariants:
    """Empty variant list and missing default error paths (lines 645-648)."""

    def test_select_expression_with_no_variants_rejected_at_construction(self) -> None:
        """SelectExpression with empty variants is rejected by __post_init__."""
        selector = VariableReference(id=Identifier("count"))
        with pytest.raises(ValueError, match="requires at least one variant"):
            SelectExpression(selector=selector, variants=())

    def test_select_expression_without_default_rejected_at_construction(self) -> None:
        """SelectExpression without a default variant is rejected by __post_init__."""
        selector = VariableReference(id=Identifier("count"))
        variant = Variant(
            key=Identifier("one"),
            value=Pattern(elements=(TextElement(value="one"),)),
            default=False,
        )
        with pytest.raises(ValueError, match="exactly one default variant"):
            SelectExpression(selector=selector, variants=(variant,))

class TestSelectExpressionFallbackPaths:
    """Test fallback variant selection logic."""

    def test_selector_error_uses_default_variant(self) -> None:
        """When selector fails due to missing variable, uses default variant."""
        selector = VariableReference(id=Identifier("missing"))
        variants = (
            Variant(
                key=Identifier("one"),
                value=Pattern(elements=(TextElement(value="variant one"),)),
                default=False,
            ),
            Variant(
                key=Identifier("other"),
                value=Pattern(elements=(TextElement(value="default variant"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, errors = resolver.resolve_message(message, {})
        assert "default variant" in result
        assert len(errors) > 0

    def test_selector_error_uses_default_variant_fallback(self) -> None:
        """When selector fails, the marked default variant is selected."""
        selector = VariableReference(id=Identifier("missing"))
        variants = (
            Variant(
                key=Identifier("first"),
                value=Pattern(elements=(TextElement(value="first variant"),)),
                default=False,
            ),
            Variant(
                key=Identifier("second"),
                value=Pattern(elements=(TextElement(value="default variant"),)),
                default=True,
            ),
        )
        select_expr = SelectExpression(selector=selector, variants=variants)
        pattern = Pattern(elements=(Placeable(expression=select_expr),))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
        )

        result, _errors = resolver.resolve_message(message, {})
        assert "default variant" in result

class TestResolverFluentNumberVariantMatching:
    """Test FluentNumber handling in variant selection."""

    def test_fluent_number_matches_numeric_variant_key(self) -> None:
        """FluentNumber value extraction for numeric variant matching (line 502)."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(
            """
msg = { NUMBER($count) ->
    [1000] Exactly one thousand
    *[other] Other value
}
"""
        )

        result, errors = bundle.format_pattern("msg", {"count": 1000})
        assert len(errors) == 0
        assert "Exactly one thousand" in result

    def test_fluent_number_plural_category_selection(self) -> None:
        """FluentNumber value extraction for CLDR plural matching (line 608)."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(
            """
msg = { NUMBER($count) ->
    [one] One item
    *[other] Many items
}
"""
        )

        result, errors = bundle.format_pattern("msg", {"count": 1})
        assert len(errors) == 0
        assert "One item" in result

    def test_fluent_number_with_formatted_display(self) -> None:
        """FluentNumber preserves numeric value for matching while showing formatted string."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(
            """
msg = { NUMBER($amount, minimumFractionDigits: 2) ->
    [1000] Exactly one thousand
    *[other] Other
}
"""
        )

        result, errors = bundle.format_pattern("msg", {"amount": 1000})
        assert len(errors) == 0
        assert "Exactly one thousand" in result

class TestFormatValueComprehensive:
    """Test _format_value with all FluentValue types."""

    def _make_resolver(self) -> FluentResolver:
        return FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

    def test_format_value_with_string(self) -> None:
        """Verify _format_value handles strings."""
        resolver = self._make_resolver()
        assert resolver._format_value("test") == "test"
        assert resolver._format_value("") == ""

    def test_format_value_with_bool_true(self) -> None:
        """Verify _format_value handles True as 'true'."""
        assert self._make_resolver()._format_value(True) == "true"

    def test_format_value_with_bool_false(self) -> None:
        """Verify _format_value handles False as 'false'."""
        assert self._make_resolver()._format_value(False) == "false"

    def test_format_value_with_int(self) -> None:
        """Verify _format_value handles integers."""
        resolver = self._make_resolver()
        assert resolver._format_value(42) == "42"
        assert resolver._format_value(0) == "0"
        assert resolver._format_value(-100) == "-100"

    def test_format_value_with_decimal(self) -> None:
        """Verify _format_value handles Decimal values."""
        resolver = self._make_resolver()
        assert resolver._format_value(Decimal("3.14")) == "3.14"
        assert resolver._format_value(Decimal(0)) == "0"
        assert resolver._format_value(Decimal("123.45")) == "123.45"

    def test_format_value_with_none(self) -> None:
        """Verify _format_value handles None as empty string."""
        assert self._make_resolver()._format_value(None) == ""

    def test_format_value_with_datetime(self) -> None:
        """Verify _format_value handles datetime via str()."""
        dt = datetime(2025, 12, 11, 15, 30, 45, tzinfo=UTC)
        result = self._make_resolver()._format_value(dt)
        assert "2025" in result
        assert "12" in result
        assert "11" in result

    @given(
        value=st.one_of(
            st.text(),
            st.integers(),
            st.decimals(allow_nan=False, allow_infinity=False),
            st.booleans(),
            st.none(),
        )
    )
    def test_format_value_never_raises(self, value: str | int | Decimal | bool | None) -> None:
        """Property: _format_value never raises exceptions."""
        event(f"value_type={type(value).__name__}")
        result = self._make_resolver()._format_value(value)
        assert isinstance(result, str)

class TestResolverErrorPaths:
    """Test error handling paths in resolver."""

    def test_missing_variable_returns_error_message(self) -> None:
        """Missing variable in select expression returns error with fallback."""
        ftl = """test = { $x ->
   [a] Value A
  *[b] Default
}
"""
        bundle = FluentBundle("en", use_isolating=False, strict=False)
        bundle.add_resource(ftl)

        result, errors = bundle.format_pattern("test", {})
        assert len(errors) > 0
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.REFERENCE
        assert errors[0].diagnostic is not None
        assert errors[0].diagnostic.code.name == "VARIABLE_NOT_PROVIDED"
        assert result == "Default"

class TestPlaceableWithFormattingError:
    """Coverage for Placeable exception path with FrozenFluentError FORMATTING."""

    def test_placeable_formatting_error_with_fallback(self) -> None:
        """Placeable that raises FrozenFluentError (FORMATTING) uses fallback value."""
        from ftllexengine.diagnostics import (
            FrozenErrorContext,
        )

        def raise_formatting_error(_value: str) -> str:
            context = FrozenErrorContext(
                input_value="test",
                locale_code="en",
                parse_type="number",
                fallback_value="FALLBACK",
            )
            msg = "Custom formatting error"
            raise FrozenFluentError(
                msg,
                ErrorCategory.FORMATTING,
                context=context,
            )

        registry = FunctionRegistry()
        registry.register(raise_formatting_error, ftl_name="ERROR_FUNC")

        func_call = FunctionReference(
            id=Identifier("ERROR_FUNC"),
            arguments=CallArguments(
                positional=(StringLiteral(value="test"),),
                named=(),
            ),
        )

        pattern = Pattern(
            elements=(
                TextElement(value="Before "),
                Placeable(expression=func_call),
                TextElement(value=" After"),
            )
        )
        message = Message(id=Identifier("msg"), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=registry,
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {})
        assert result == "Before FALLBACK After"
        assert len(errors) == 1
        assert isinstance(errors[0], FrozenFluentError)
        assert errors[0].category == ErrorCategory.FORMATTING
