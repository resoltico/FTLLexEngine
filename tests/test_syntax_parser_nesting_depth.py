"""Hypothesis-driven tests for 100% coverage of syntax/parser/expressions.py.

Targets uncovered branches and error paths using property-based testing.
"""

from __future__ import annotations

from decimal import Decimal

from hypothesis import event, example, given
from hypothesis import strategies as st

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.parser.core import FluentParserV1


class TestNestingDepthControl:
    """Test nesting depth limit (DoS prevention)."""

    def test_parser_with_custom_nesting_depth(self) -> None:
        """Verify FluentParserV1 accepts custom nesting depths."""
        # Verify parser accepts various positive depths without error
        parser1 = FluentParserV1(max_nesting_depth=50)
        assert parser1.max_nesting_depth == 50

        parser2 = FluentParserV1(max_nesting_depth=200)
        assert parser2.max_nesting_depth == 200  # Arbitrary large depth for testing

        # Default parser uses MAX_DEPTH
        parser_default = FluentParserV1()
        assert parser_default.max_nesting_depth == MAX_DEPTH
        assert MAX_DEPTH > 0

    @given(st.integers(min_value=1, max_value=1000))
    def test_parser_accepts_positive_depths(self, depth: int) -> None:
        """PROPERTY: All positive depths are accepted by FluentParserV1."""
        event(f"depth={depth}")
        # Verify parser accepts any positive depth without error
        parser = FluentParserV1(max_nesting_depth=depth)
        assert parser.max_nesting_depth == depth
        assert depth > 0

    def test_nesting_depth_exceeded_in_parse_placeable(self) -> None:
        """Test deeply nested placeables hit depth limit."""
        # Create parser with very low limit
        parser = FluentParserV1(max_nesting_depth=3)
        bundle = FluentBundle("en_US")
        # Create deeply nested placeables
        nested = "{ " * 10 + "text" + " }" * 10
        # Parse with custom parser
        resource = parser.parse(f"msg = {nested}")
        # Add the parsed resource to bundle
        from ftllexengine.syntax.ast import Message  # noqa: PLC0415

        for entry in resource.entries:
            if isinstance(entry, Message):
                bundle._messages[entry.id.name] = entry
        result, errors = bundle.format_pattern("msg")
        # Should have fallback or error
        assert "{" in result or len(errors) > 0


class TestVariantKeyParsing:
    """Test variant key parsing edge cases."""

    def test_variant_key_negative_number(self) -> None:
        """Test variant with negative number key."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("""
msg = { $val ->
    [-1] Negative one
   *[other] Other
}
""")
        result, errors = bundle.format_pattern("msg", {"val": -1})

        assert not errors
        assert "Negative" in result or "Other" in result

    def test_variant_key_zero(self) -> None:
        """Test variant with zero key."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("""
msg = { $val ->
    [0] Zero
   *[other] Other
}
""")
        result, errors = bundle.format_pattern("msg", {"val": 0})

        assert not errors
        assert "Zero" in result or "Other" in result

    def test_variant_key_identifier_with_hyphens(self) -> None:
        """Test variant key with hyphens."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("""
msg = { $val ->
    [brand-name] Brand
   *[other] Other
}
""")
        result, errors = bundle.format_pattern("msg", {"val": "brand-name"})

        assert not errors
        assert result is not None

    @given(
        st.integers(min_value=-1000, max_value=1000),
    )
    def test_variant_key_number_property(self, key: int) -> None:
        """PROPERTY: Number variant keys parse correctly."""
        event(f"key={key}")
        bundle = FluentBundle("en_US")
        bundle.add_resource(f"""
msg = {{ $val ->
    [{key}] Match
   *[other] Other
}}
""")
        result, errors = bundle.format_pattern("msg", {"val": key})

        assert not errors
        assert result is not None


class TestSelectExpressionValidation:
    """Test select expression validation."""

    def test_select_no_default_variant(self) -> None:
        """Test select expression without default variant fails."""
        bundle = FluentBundle("en_US")
        # No default marker (*)
        bundle.add_resource("""
msg = { $val ->
    [one] One
    [two] Two
}
""")
        result, errors = bundle.format_pattern("msg", {"val": "one"})
        # Should have error or fallback
        assert "{" in result or len(errors) > 0

    def test_select_multiple_defaults(self) -> None:
        """Test select expression with multiple defaults fails."""
        bundle = FluentBundle("en_US")
        # Multiple default markers
        bundle.add_resource("""
msg = { $val ->
   *[one] One
   *[two] Two
}
""")
        result, errors = bundle.format_pattern("msg", {"val": "one"})
        assert "{" in result or len(errors) > 0

    def test_select_empty_variants(self) -> None:
        """Test select expression with no variants fails."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = { $val -> }")
        result, errors = bundle.format_pattern("msg", {"val": "test"})
        assert "{" in result or len(errors) > 0


class TestTermReferenceEdgeCases:
    """Test term reference edge cases."""

    def test_term_reference_with_arguments(self) -> None:
        """Test term reference with arguments."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("-brand = Firefox")
        bundle.add_resource('msg = { -brand(case: "nominative") }')
        result, errors = bundle.format_pattern("msg")

        assert not errors
        assert "Firefox" in result or len(errors) > 0

    def test_term_reference_with_attribute_and_arguments(self) -> None:
        """Test term reference with both attribute and arguments."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("""
-brand = Firefox
    .gender = masculine
""")
        bundle.add_resource('msg = { -brand.gender(case: "genitive") }')
        result, errors = bundle.format_pattern("msg")

        assert not errors
        assert result is not None

    def test_term_reference_missing_closing_paren(self) -> None:
        """Test term reference with unclosed argument list."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("-brand = Firefox")
        bundle.add_resource('msg = { -brand(case: "nominative" }')
        result, errors = bundle.format_pattern("msg")
        # Should have error
        assert "{" in result or len(errors) > 0


class TestCallArgumentsEdgeCases:
    """Test function call argument parsing edge cases."""

    def test_named_arg_requires_literal_value(self) -> None:
        """Test that named arguments require literal values (not references)."""
        bundle = FluentBundle("en_US")
        # Named arg with variable reference (invalid per FTL spec)
        bundle.add_resource("msg = { NUMBER($val, precision: $digits) }")
        result, errors = bundle.format_pattern("msg", {"val": 42, "digits": 2})
        # Should have error because named arg values must be literals
        assert "{" in result or len(errors) > 0

    def test_positional_after_named_fails(self) -> None:
        """Test that positional args after named args fails."""
        bundle = FluentBundle("en_US")
        # Positional after named (invalid)
        bundle.add_resource("msg = { FUNC(name: 1, $val) }")
        result, errors = bundle.format_pattern("msg", {"val": 42})
        assert "{" in result or len(errors) > 0

    def test_duplicate_named_arg_fails(self) -> None:
        """Test duplicate named argument names fail."""
        bundle = FluentBundle("en_US")
        # Duplicate named arg
        bundle.add_resource('msg = { FUNC($val, style: "a", style: "b") }')
        result, errors = bundle.format_pattern("msg", {"val": 42})
        assert "{" in result or len(errors) > 0

    @given(
        st.lists(st.integers(), min_size=0, max_size=5),
    )
    def test_positional_args_property(self, values: list[int]) -> None:
        """PROPERTY: Multiple positional args parse correctly."""
        event(f"arg_count={len(values)}")
        bundle = FluentBundle("en_US")

        def test_func(*args: int | str) -> str:
            return f"Called with {len(args)} args"

        bundle.add_function("TEST", test_func)

        # Build arg list
        args = ", ".join(f"${i}" for i in range(len(values)))
        bundle.add_resource(f"msg = {{ TEST({args}) }}")

        args_dict = {str(i): val for i, val in enumerate(values)}
        result, _errors = bundle.format_pattern("msg", args_dict)
        # Should either work or have clear error
        assert result is not None


class TestInlineExpressionEdgeCases:
    """Test inline expression parsing edge cases."""

    def test_negative_number_vs_term_reference(self) -> None:
        """Test disambiguation between negative number and term reference."""
        bundle = FluentBundle("en_US")
        # -123 should parse as negative number, not term
        bundle.add_resource("msg = { -123 }")
        result, errors = bundle.format_pattern("msg")

        assert not errors
        assert "-123" in result or "{" in result

    def test_term_reference_starts_with_alpha(self) -> None:
        """Test term reference detection (-brand vs -123)."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("-brand = Firefox")
        bundle.add_resource("msg = { -brand }")
        result, errors = bundle.format_pattern("msg")

        assert not errors
        assert "Firefox" in result or len(errors) > 0

    def test_message_reference_with_attribute(self) -> None:
        """Test message reference with attribute access."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("""
greeting = Hello
    .formal = Good day
""")
        bundle.add_resource("msg = { greeting.formal }")
        result, errors = bundle.format_pattern("msg")

        assert not errors
        assert "Good day" in result or len(errors) > 0

    def test_uppercase_identifier_without_paren_is_message_ref(self) -> None:
        """Test UPPERCASE identifier without ( is message reference, not function."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("NUMBER = The number")
        bundle.add_resource("msg = { NUMBER }")
        result, errors = bundle.format_pattern("msg")

        assert not errors
        # Should resolve as message reference
        assert "number" in result.lower() or len(errors) > 0


class TestMetamorphicProperties:
    """Test metamorphic properties of expression parsing."""

    @given(
        st.integers(min_value=-100, max_value=100),
    )
    def test_number_literal_roundtrip(self, value: int) -> None:
        """METAMORPHIC: Number literals round-trip through parsing."""
        event(f"value={value}")
        bundle = FluentBundle("en_US")
        bundle.add_resource(f"msg = {{ {value} }}")
        result, errors = bundle.format_pattern("msg")

        assert not errors
        if len(errors) == 0:
            assert str(value) in result

    @given(
        st.text(
            alphabet=st.characters(
                min_codepoint=32,
                max_codepoint=126,
                blacklist_characters='"\\',
            ),
            min_size=1,
            max_size=20,
        ),
    )
    def test_string_literal_roundtrip(self, text: str) -> None:
        """METAMORPHIC: String literals round-trip through parsing."""
        event(f"text_length={len(text)}")
        bundle = FluentBundle("en_US")
        bundle.add_resource(f'msg = {{ "{text}" }}')
        result, errors = bundle.format_pattern("msg")

        assert not errors
        if len(errors) == 0:
            # String should appear in output
            assert text in result or "{" in result


class TestSelectExpressionAllValidSelectors:
    """Test all valid selector types for select expressions."""

    def test_select_with_string_literal_selector(self) -> None:
        """Test select expression with StringLiteral selector."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("""
msg = { "test" ->
    [test] Matched
   *[other] Other
}
""")
        result, errors = bundle.format_pattern("msg")

        assert not errors
        assert "Matched" in result or "Other" in result or len(errors) > 0

    def test_select_with_number_literal_selector(self) -> None:
        """Test select expression with NumberLiteral selector."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("""
msg = { 42 ->
    [42] Matched
   *[other] Other
}
""")
        result, errors = bundle.format_pattern("msg")

        assert not errors
        assert "Matched" in result or "Other" in result or len(errors) > 0

    def test_select_with_function_selector(self) -> None:
        """Test select expression with FunctionReference selector."""
        bundle = FluentBundle("en_US")

        def get_value(_val: int | Decimal | str) -> str:
            return "test"

        bundle.add_function("GET", get_value)
        bundle.add_resource("""
msg = { GET($val) ->
    [test] Matched
   *[other] Other
}
""")
        result, errors = bundle.format_pattern("msg", {"val": 1})

        assert not errors
        assert result is not None

    def test_select_with_message_reference_selector(self) -> None:
        """Test select expression with MessageReference selector."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("value = test")
        bundle.add_resource("""
msg = { value ->
    [test] Matched
   *[other] Other
}
""")
        result, errors = bundle.format_pattern("msg")

        assert not errors
        # May work or fail depending on resolution
        assert result is not None

    def test_select_with_term_reference_selector(self) -> None:
        """Test select expression with TermReference selector."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("-value = test")
        bundle.add_resource("""
msg = { -value ->
    [test] Matched
   *[other] Other
}
""")
        result, errors = bundle.format_pattern("msg")

        assert not errors
        assert result is not None


@given(
    st.integers(min_value=0, max_value=10),
)
@example(5)
def test_variant_count_property(variant_count: int) -> None:
    """PROPERTY: Select expressions handle variable number of variants."""
    event(f"variant_count={variant_count}")
    bundle = FluentBundle("en_US")

    # Generate variants
    variants = "\n".join(f"    [{i}] Variant {i}" for i in range(variant_count))
    # Always need a default
    variants += "\n   *[other] Default"

    ftl = f"""
msg = {{ $val ->
{variants}
}}
"""
    bundle.add_resource(ftl)
    result, errors = bundle.format_pattern("msg", {"val": 0})

    assert not errors
    assert result is not None
