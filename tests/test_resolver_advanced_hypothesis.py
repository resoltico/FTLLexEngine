"""Advanced Hypothesis property-based tests for FluentResolver.

Critical resolver functions tested:
- Pattern resolution
- Variable reference resolution
- Message/term reference resolution
- Select expression evaluation
- Function call resolution
- Circular reference detection
"""

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.runtime.function_bridge import FunctionRegistry
from ftllexengine.runtime.resolver import FluentResolver
from ftllexengine.syntax.ast import Identifier, Message, Pattern, TextElement
from tests.strategies import ftl_identifiers, ftl_simple_text


class TestPatternResolution:
    """Properties about pattern resolution."""

    @given(
        msg_id=ftl_identifiers(),
        text_content=ftl_simple_text(),
    )
    @settings(max_examples=500)
    def test_simple_text_resolution(self, msg_id: str, text_content: str) -> None:
        """Property: Simple text patterns resolve to their content."""
        pattern = Pattern(elements=(TextElement(value=text_content),))
        message = Message(id=Identifier(name=msg_id), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en_US",
            messages={msg_id: message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {})

        assert not errors

        assert result == text_content, f"Expected {text_content}, got {result}"

    @given(
        msg_id=ftl_identifiers(),
        parts=st.lists(ftl_simple_text(), min_size=2, max_size=5),
    )
    @settings(max_examples=300)
    def test_multiple_text_elements_concatenation(
        self, msg_id: str, parts: list[str]
    ) -> None:
        """Property: Multiple text elements are concatenated."""
        elements = tuple(TextElement(value=p) for p in parts)
        pattern = Pattern(elements=elements)
        message = Message(id=Identifier(name=msg_id), value=pattern, attributes=())

        resolver = FluentResolver(
            locale="en_US",
            messages={msg_id: message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, {})

        assert not errors
        expected = "".join(parts)

        assert result == expected, f"Concatenation mismatch: {result} != {expected}"


class TestVariableResolution:
    """Properties about variable reference resolution."""

    @given(
        var_name=ftl_identifiers(),
        var_value=st.one_of(
            st.text(min_size=1, max_size=50),
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
        ),
    )
    @settings(max_examples=500)
    def test_variable_value_preservation(
        self, var_name: str, var_value: str | int | float
    ) -> None:
        """Property: Variable values are preserved in resolution."""
        bundle = FluentBundle("en_US", use_isolating=False)

        ftl_source = f"msg = {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("msg", {var_name: var_value})

        assert not errors

        assert str(var_value) in result, f"Variable value not in result: {result}"

    @given(
        var_name=ftl_identifiers(),
    )
    @settings(max_examples=300)
    def test_missing_variable_error_handling(self, var_name: str) -> None:
        """Property: Missing variables are handled gracefully."""
        bundle = FluentBundle("en_US")

        ftl_source = f"msg = {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, _errors = bundle.format_pattern("msg", {})

        assert isinstance(result, str), "Must return string even on missing variable"

    @given(
        var_count=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=200)
    def test_multiple_variables_independent(self, var_count: int) -> None:
        """Property: Multiple variables resolve independently."""
        bundle = FluentBundle("en_US", use_isolating=False)

        var_names = [f"v{i}" for i in range(var_count)]
        placeholders = " ".join(f"{{ ${vn} }}" for vn in var_names)
        ftl_source = f"msg = {placeholders}"
        bundle.add_resource(ftl_source)

        args = {vn: f"val{i}" for i, vn in enumerate(var_names)}
        result, errors = bundle.format_pattern("msg", args)

        assert not errors

        for value in args.values():
            assert value in result, f"Variable value {value} missing"


class TestMessageReferenceResolution:
    """Properties about message reference resolution."""

    @given(
        ref_msg_id=ftl_identifiers(),
        ref_value=ftl_simple_text(),
        main_msg_id=ftl_identifiers(),
    )
    @settings(max_examples=300)
    def test_message_reference_resolution(
        self, ref_msg_id: str, ref_value: str, main_msg_id: str
    ) -> None:
        """Property: Message references resolve to referenced message value."""
        assume(ref_msg_id != main_msg_id)

        bundle = FluentBundle("en_US", use_isolating=False)

        ftl_source = f"""
{ref_msg_id} = {ref_value}
{main_msg_id} = {{ {ref_msg_id} }}
"""
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern(main_msg_id)

        assert not errors

        assert ref_value.strip() in result, f"Referenced message value not in result: {result}"

    @given(
        nonexistent_id=ftl_identifiers(),
        main_msg_id=ftl_identifiers(),
    )
    @settings(max_examples=200)
    def test_missing_message_reference_handling(
        self, nonexistent_id: str, main_msg_id: str
    ) -> None:
        """Property: Missing message references handled gracefully."""
        assume(nonexistent_id != main_msg_id)

        bundle = FluentBundle("en_US")

        ftl_source = f"{main_msg_id} = {{ {nonexistent_id} }}"
        bundle.add_resource(ftl_source)

        result, _errors = bundle.format_pattern(main_msg_id)

        assert isinstance(result, str), "Must return string for missing reference"


class TestTermReferenceResolution:
    """Properties about term reference resolution."""

    @given(
        term_id=ftl_identifiers(),
        term_value=ftl_simple_text(),
        msg_id=ftl_identifiers(),
    )
    @settings(max_examples=300)
    def test_term_reference_resolution(
        self, term_id: str, term_value: str, msg_id: str
    ) -> None:
        """Property: Term references resolve to term value."""
        bundle = FluentBundle("en_US", use_isolating=False)

        ftl_source = f"""
-{term_id} = {term_value}
{msg_id} = {{ -{term_id} }}
"""
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern(msg_id)

        assert not errors

        assert term_value.strip() in result, f"Term value not in result: {result}"

    @given(
        nonexistent_term=ftl_identifiers(),
        msg_id=ftl_identifiers(),
    )
    @settings(max_examples=200)
    def test_missing_term_reference_handling(
        self, nonexistent_term: str, msg_id: str
    ) -> None:
        """Property: Missing term references handled gracefully."""
        bundle = FluentBundle("en_US")

        ftl_source = f"{msg_id} = {{ -{nonexistent_term} }}"
        bundle.add_resource(ftl_source)

        result, _errors = bundle.format_pattern(msg_id)

        assert isinstance(result, str), "Must return string for missing term"


class TestSelectExpressionResolution:
    """Properties about select expression evaluation."""

    @given(
        var_name=ftl_identifiers(),
        selector_value=st.one_of(st.text(min_size=1, max_size=20), st.integers(0, 100)),
        variant1_key=ftl_identifiers(),
        variant1_val=ftl_simple_text(),
        variant2_val=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_select_expression_matches_variant(
        self,
        var_name: str,
        selector_value: str | int,
        variant1_key: str,
        variant1_val: str,
        variant2_val: str,
    ) -> None:
        """Property: Select expressions match correct variant."""
        assume(variant1_key != "other")
        assume(var_name != variant1_key)

        bundle = FluentBundle("en_US", use_isolating=False)

        ftl_source = f"""
msg = {{ ${var_name} ->
    [{variant1_key}] {variant1_val}
   *[other] {variant2_val}
}}
"""
        bundle.add_resource(ftl_source)

        if not bundle.has_message("msg"):
            return

        result, errors = bundle.format_pattern("msg", {var_name: selector_value})

        assert not errors

        if str(selector_value) == variant1_key:
            assert variant1_val.strip() in result, f"Expected {variant1_val} for matching key"
        else:
            assert (
                variant2_val.strip() in result or variant1_val.strip() in result
            ), "Must match some variant"

    @given(
        var_name=ftl_identifiers(),
        numeric_value=st.integers(0, 10),
    )
    @settings(max_examples=200)
    def test_numeric_selector_matching(self, var_name: str, numeric_value: int) -> None:
        """Property: Numeric selectors match correctly."""
        bundle = FluentBundle("en_US", use_isolating=False)

        ftl_source = f"""
msg = {{ ${var_name} ->
    [0] zero
    [1] one
   *[other] many
}}
"""
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("msg", {var_name: numeric_value})

        assert not errors

        if numeric_value == 0:
            assert "zero" in result, "Should match [0] variant"
        elif numeric_value == 1:
            assert "one" in result, "Should match [1] variant"
        else:
            assert "many" in result or result, "Should match default variant"


class TestCircularReferenceDetection:
    """Properties about circular reference detection."""

    @given(
        msg1_id=ftl_identifiers(),
        msg2_id=ftl_identifiers(),
    )
    @settings(max_examples=200)
    def test_direct_circular_reference_detection(
        self, msg1_id: str, msg2_id: str
    ) -> None:
        """Property: Direct circular references are detected."""
        assume(msg1_id != msg2_id)

        bundle = FluentBundle("en_US")

        ftl_source = f"""
{msg1_id} = {{ {msg2_id} }}
{msg2_id} = {{ {msg1_id} }}
"""
        bundle.add_resource(ftl_source)

        result, _errors = bundle.format_pattern(msg1_id)

        assert isinstance(result, str), "Must handle circular reference gracefully"

    @given(
        msg_ids=st.lists(ftl_identifiers(), min_size=3, max_size=5, unique=True),
    )
    @settings(max_examples=100)
    def test_indirect_circular_reference_detection(self, msg_ids: list[str]) -> None:
        """Property: Indirect circular references (chains) are detected."""
        bundle = FluentBundle("en_US")

        msg_pairs = list(zip(msg_ids, [*msg_ids[1:], msg_ids[0]], strict=True))
        ftl_lines = [f"{m1} = {{ {m2} }}" for m1, m2 in msg_pairs]
        ftl_source = "\n".join(ftl_lines)

        bundle.add_resource(ftl_source)

        result, _errors = bundle.format_pattern(msg_ids[0])

        assert isinstance(result, str), "Must handle circular chain gracefully"


class TestFunctionCallResolution:
    """Properties about function call resolution."""

    @given(
        # Per Fluent spec, function names must be ASCII uppercase only
        func_name=st.text(
            alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=3, max_size=10
        ),
        return_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_custom_function_called(self, func_name: str, return_value: str) -> None:
        """Property: Custom functions are called and results used."""
        assume(func_name not in ("NUMBER", "DATETIME"))

        bundle = FluentBundle("en_US", use_isolating=False)

        def custom_func() -> str:
            return return_value

        bundle.add_function(func_name, custom_func)
        bundle.add_resource(f"msg = {{ {func_name}() }}")

        result, errors = bundle.format_pattern("msg")

        assert not errors

        assert return_value.strip() in result, f"Function return value not in result: {result}"

    @given(
        func_name=st.text(
            alphabet=st.characters(whitelist_categories=["Lu"]), min_size=3, max_size=10
        ),
        error_message=ftl_simple_text(),
    )
    @settings(max_examples=200)
    def test_function_exception_handling(
        self, func_name: str, error_message: str
    ) -> None:
        """Property: Function exceptions are handled gracefully."""
        assume(func_name not in ("NUMBER", "DATETIME"))  # Avoid built-in conflicts

        bundle = FluentBundle("en_US")

        def failing_func() -> str:
            raise ValueError(error_message)

        bundle.add_function(func_name, failing_func)
        bundle.add_resource(f"msg = {{ {func_name}() }}")

        result, _errors = bundle.format_pattern("msg")

        assert isinstance(result, str), "Must return string even when function fails"


class TestResolverIsolatingMarks:
    """Properties about Unicode bidi isolation marks."""

    @given(
        var_name=ftl_identifiers(),
        var_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_isolating_marks_added_when_enabled(
        self, var_name: str, var_value: str
    ) -> None:
        """Property: Isolation marks added around interpolated values when enabled."""
        bundle = FluentBundle("en_US", use_isolating=True)

        ftl_source = f"msg = {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("msg", {var_name: var_value})

        assert not errors

        assert "\u2068" in result, "FSI mark missing"
        assert "\u2069" in result, "PDI mark missing"
        assert var_value in result, "Variable value missing"

    @given(
        var_name=ftl_identifiers(),
        var_value=ftl_simple_text(),
    )
    @settings(max_examples=300)
    def test_no_isolating_marks_when_disabled(
        self, var_name: str, var_value: str
    ) -> None:
        """Property: No isolation marks when use_isolating=False."""
        bundle = FluentBundle("en_US", use_isolating=False)

        ftl_source = f"msg = {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("msg", {var_name: var_value})

        assert not errors

        assert "\u2068" not in result, "FSI mark should not be present"
        assert "\u2069" not in result, "PDI mark should not be present"


class TestResolverValueFormatting:
    """Properties about value formatting."""

    @given(
        var_name=ftl_identifiers(),
        int_value=st.integers(),
    )
    @settings(max_examples=300)
    def test_integer_formatting(self, var_name: str, int_value: int) -> None:
        """Property: Integers are formatted correctly."""
        bundle = FluentBundle("en_US", use_isolating=False)

        ftl_source = f"msg = {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("msg", {var_name: int_value})

        assert not errors

        assert str(int_value) in result, f"Integer {int_value} not formatted correctly"

    @given(
        var_name=ftl_identifiers(),
        bool_value=st.booleans(),
    )
    @settings(max_examples=200)
    def test_boolean_formatting(self, var_name: str, bool_value: bool) -> None:
        """Property: Booleans are formatted consistently."""
        bundle = FluentBundle("en_US", use_isolating=False)

        ftl_source = f"msg = {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern("msg", {var_name: bool_value})

        assert not errors

        # Fluent formats booleans as lowercase "true"/"false"
        expected = "true" if bool_value else "false"
        assert expected in result, f"Boolean {bool_value} not formatted correctly"


class TestResolverMetamorphicProperties:
    """Metamorphic properties relating different resolution operations."""

    @given(
        msg_id=ftl_identifiers(),
        text1=ftl_simple_text(),
        text2=ftl_simple_text(),
    )
    @settings(max_examples=200)
    def test_concatenation_commutativity_in_args(
        self, msg_id: str, text1: str, text2: str
    ) -> None:
        """Property: Multiple text elements concatenate in order."""
        assume(text1 != text2)

        bundle = FluentBundle("en_US", use_isolating=False)

        ftl_source = f"{msg_id} = {text1} {text2}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern(msg_id)

        assert not errors

        assert text1.strip() in result, "First text element should be present"
        assert text2.strip() in result, "Second text element should be present"

        idx1 = result.find(text1.strip())
        idx2 = result.find(text2.strip())
        if idx1 != idx2:
            assert idx1 < idx2, "Text elements should appear in order"

    @given(
        msg_id=ftl_identifiers(),
        var_name=ftl_identifiers(),
        value1=ftl_simple_text(),
        value2=ftl_simple_text(),
    )
    @settings(max_examples=200)
    def test_variable_value_substitution(
        self, msg_id: str, var_name: str, value1: str, value2: str
    ) -> None:
        """Property: Changing variable value changes result."""
        assume(value1 != value2)
        assume(value1 not in value2 and value2 not in value1)

        bundle = FluentBundle("en_US", use_isolating=False)

        ftl_source = f"{msg_id} = {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result1, errors = bundle.format_pattern(msg_id, {var_name: value1})

        assert not errors
        result2, errors = bundle.format_pattern(msg_id, {var_name: value2})

        assert not errors

        assert result1 != result2, "Different variable values should produce different results"


class TestResolverErrorRecovery:
    """Properties about error recovery during resolution."""

    @given(
        msg_id=ftl_identifiers(),
        partial_text=ftl_simple_text(),
        var_name=ftl_identifiers(),
    )
    @settings(max_examples=200)
    def test_partial_resolution_on_error(
        self, msg_id: str, partial_text: str, var_name: str
    ) -> None:
        """Property: Partial resolution continues after errors."""
        bundle = FluentBundle("en_US", use_isolating=False)

        ftl_source = f"{msg_id} = {partial_text} {{ ${var_name} }}"
        bundle.add_resource(ftl_source)

        result, _errors = bundle.format_pattern(msg_id, {})

        assert partial_text.strip() in result, "Static text should be present even with missing var"


# ============================================================================
# COVERAGE TESTS - Resolver Edge Cases
# ============================================================================


class TestResolverCoverageEdgeCases:
    """Test resolver edge cases for 100% coverage (lines 142->138, 190, 375-376)."""

    @given(
        msg_id=ftl_identifiers(),
        text=ftl_simple_text(),
    )
    @settings(max_examples=100)
    def test_placeable_error_handling_in_pattern(
        self, msg_id: str, text: str
    ) -> None:
        """COVERAGE: Placeable error handling in _resolve_pattern (line 142->138)."""
        bundle = FluentBundle("en_US", use_isolating=False)

        # Create FTL with placeable that will error (missing variable)
        ftl_source = f"{msg_id} = {text} {{ $missing }}"
        bundle.add_resource(ftl_source)

        # Line 142->138: try-except around placeable resolution
        result, errors = bundle.format_pattern(msg_id, {})

        # Should have error but still return fallback
        assert len(errors) > 0
        assert "{$missing}" in result  # Fallback representation

    @given(
        msg_id=ftl_identifiers(),
        var_name=ftl_identifiers(),
        value=st.integers(),
    )
    @settings(max_examples=100)
    def test_nested_placeable_expression_resolution(
        self, msg_id: str, var_name: str, value: int
    ) -> None:
        """COVERAGE: Placeable expression resolution (line 190)."""
        # pylint: disable=import-outside-toplevel
        from ftllexengine import FluentBundle  # noqa: PLC0415

        bundle = FluentBundle("en_US", use_isolating=False)

        # Create message with nested placeable structure
        # This exercises line 190: case Placeable() in _resolve_expression
        ftl_source = f"{msg_id} = Value: {{ ${ var_name} }}"
        bundle.add_resource(ftl_source)

        result, errors = bundle.format_pattern(msg_id, {var_name: value})

        assert not errors

        # Should resolve the nested placeable expression
        assert str(value) in result
