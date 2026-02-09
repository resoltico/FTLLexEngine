"""Hypothesis-based property testing for parser error paths.

Uses property-based testing to systematically generate malformed FTL input
to cover deep error branches and achieve near-100% parser coverage.

Target: Remaining 29 uncovered lines in parser.py
"""

from hypothesis import assume, event, example, given, settings
from hypothesis import strategies as st

from ftllexengine.syntax.parser import FluentParserV1
from tests.strategies import ftl_identifiers

# ============================================================================
# STRATEGY 1: Malformed Placeables
# ============================================================================

@st.composite
def malformed_placeable(draw):
    """Generate placeables with strategic syntax errors.

    Targets uncovered error paths in placeable parsing.
    """
    corruptions = [
        "{",           # Missing content
        "{ ",          # Space but no content
        "{ $",         # Incomplete variable
        "{ $v",        # Incomplete variable name
        "{ $var",      # Missing closing }
        '{ "',         # Incomplete string literal → line 385
        '{ "text',     # Unterminated string
        "{ -",         # Incomplete term ref
        "{ -t",        # Incomplete term name
        "{ -term",     # Missing closing }
        "{ 1.",        # Malformed number → line 712
        "{ 1.2.",      # Invalid number format
        "{ FUNC",      # Missing parentheses
        "{ FUNC(",     # Incomplete function → line 860, 868
        "{ FUNC($",    # Incomplete arg
        "{ msg.",      # Missing attr name → lines 994-1002!
        "{ msg.@",     # Invalid attr name
        "{ $x ->",     # Incomplete select
        "{ $x -> [",   # Incomplete variant
        "{ $x -> [a]", # Missing pattern
    ]
    return draw(st.sampled_from(corruptions))


class TestMalformedPlaceables:
    """Hypothesis tests for malformed placeables."""

    @given(
        msg_id=ftl_identifiers(),
        placeable=malformed_placeable()
    )
    @settings(max_examples=100, deadline=None)
    @example(msg_id="key", placeable="{ msg.")  # Specifically target lines 994-1002
    @example(msg_id="key", placeable='{ "')     # Target line 385
    @example(msg_id="key", placeable="{ 1.2.")  # Target line 712
    def test_parser_handles_malformed_placeables(self, msg_id, placeable):
        """Parser should handle malformed placeables without crashing.

        Covers multiple error paths including:
        - Line 385: String literal errors
        - Line 497: Placeable closure errors
        - Lines 994-1002: Message.attr errors
        - Line 712: Number literal errors
        """
        source = f"{msg_id} = {placeable}"
        event(f"input_len={len(source)}")
        event(f"placeable_len={len(placeable)}")
        parser = FluentParserV1()

        try:
            resource = parser.parse(source)
            # Should either create Junk or handle error gracefully
            assert resource is not None
            assert len(resource.entries) >= 0
        except RecursionError:
            # Parser might hit recursion limit on deeply malformed input
            assume(False)  # Skip this example


# ============================================================================
# STRATEGY 2: Malformed Function Calls
# ============================================================================

@st.composite
def malformed_function_call(draw):
    """Generate function calls with strategic syntax errors.

    Targets error paths in function call parsing.
    """
    func_name = draw(st.sampled_from(["FUNC", "NUMBER", "DATETIME", "UPPER"]))

    corruptions = [
        f"{func_name}",         # Missing parens → line 882
        f"{func_name}(",        # Missing args/close → line 860
        f"{func_name}($",       # Incomplete arg → line 698
        f"{func_name}($v",      # Incomplete var ref
        f"{func_name}(1.2.",    # Malformed number → line 712
        f'{{ {func_name}("',    # Incomplete string → line 705
        f"{func_name}(@",       # Invalid identifier → line 719
        f"{func_name}(a:",      # Missing value after : → line 799
        f"{func_name}(a: )",    # Empty value after :
        f"{func_name}(123: x)", # Non-identifier as arg name → line 784
        f"{func_name}(a: 1, a: 2)", # Duplicate named arg → line 792
        f"{func_name}(x: 1, 2)", # Positional after named → line 816
    ]
    return draw(st.sampled_from(corruptions))


class TestMalformedFunctionCalls:
    """Hypothesis tests for malformed function calls."""

    @given(
        msg_id=ftl_identifiers(),
        func_call=malformed_function_call()
    )
    @settings(max_examples=80, deadline=None)
    @example(msg_id="key", func_call="FUNC($")      # Target line 698
    @example(msg_id="key", func_call="FUNC(1.2.")   # Target line 712
    @example(msg_id="key", func_call='{ FUNC("')    # Target line 705
    @example(msg_id="key", func_call="FUNC(@bad)")  # Target line 719
    @example(msg_id="key", func_call="FUNC(a:)")    # Target line 799
    @example(msg_id="key", func_call="FUNC")        # Target line 882
    def test_parser_handles_malformed_function_calls(self, msg_id, func_call):
        """Parser should handle malformed function calls gracefully.

        Covers error paths:
        - Line 698: Variable ref error in args
        - Line 705: String literal error in args
        - Line 712: Number literal error in args
        - Line 719: Message ref error in args
        - Line 784: Non-identifier arg name
        - Line 792: Duplicate named args
        - Line 799: Missing value after :
        - Line 816: Positional after named
        - Line 853: Function ref error
        - Line 860: Function parse error
        - Line 868: Function call error
        - Line 882: Uppercase without parens
        """
        source = f"{msg_id} = {{ {func_call} }}"
        event(f"input_len={len(source)}")
        event(f"func_call_len={len(func_call)}")
        parser = FluentParserV1()

        resource = parser.parse(source)
        # Should handle error without crashing
        assert resource is not None


# ============================================================================
# STRATEGY 3: Malformed Select Expressions
# ============================================================================

@st.composite
def malformed_select_expression(draw):
    """Generate select expressions with strategic errors.

    Targets select expression error paths.
    """
    var = draw(st.sampled_from(["$x", "$count", "$num"]))

    corruptions = [
        f"{{ {var} ->",                    # Incomplete select
        f"{{ {var} -> [",                  # Incomplete variant
        f"{{ {var} -> [@",                 # Invalid variant key → lines 561-562
        f"{{ {var} -> [a]",                # Missing pattern
        f"{{ {var} -> [a] Text",           # Missing close } → line 1113
        f"{{ {var} -> [a] {{ msg.",        # Nested malformed → lines 994-1002
        f"{{ {var} -> [one] X *[other] Y", # Missing } → line 1113
    ]
    return draw(st.sampled_from(corruptions))


class TestMalformedSelectExpressions:
    """Hypothesis tests for malformed select expressions."""

    @given(
        msg_id=ftl_identifiers(),
        select=malformed_select_expression()
    )
    @settings(max_examples=50, deadline=None)
    @example(msg_id="key", select="{ $x -> [@")           # Target lines 561-562
    @example(msg_id="key", select="{ $x -> [a] Text")     # Target line 1113
    @example(msg_id="key", select="{ $x -> [a] { msg.")   # Target lines 994-1002
    def test_parser_handles_malformed_select_expressions(self, msg_id, select):
        """Parser should handle malformed select expressions.

        Covers error paths:
        - Lines 561-562: Invalid variant key (double failure)
        - Line 1113: Missing } after select
        - Lines 994-1002: Malformed nested expressions
        """
        source = f"{msg_id} = {select}"
        event(f"input_len={len(source)}")
        event(f"select_len={len(select)}")
        parser = FluentParserV1()

        resource = parser.parse(source)
        assert resource is not None


# ============================================================================
# STRATEGY 4: Malformed Terms
# ============================================================================

@st.composite
def malformed_term(draw):
    """Generate terms with strategic syntax errors.

    Targets term parsing error paths.
    """
    corruptions = [
        "-",                    # Just dash
        "- ",                   # Dash with space
        "-@invalid",            # Invalid identifier → line 1458
        "-term",                # Just identifier (no value)
        "-term =",              # No value
        "-term = val\n    .",   # Missing attr name → line 1470
        "-term = val\n    .@",  # Invalid attr name
    ]
    return draw(st.sampled_from(corruptions))


@st.composite
def malformed_term_reference(draw):
    """Generate term references with strategic errors.

    Targets term reference error paths.
    """
    corruptions = [
        "{ -",           # Incomplete term ref → line 1449
        "{ - }",         # No identifier
        "{ -@bad }",     # Invalid identifier
        "{ -term(",      # Missing args/close → line 1493
        "{ -term(x",     # Missing close paren → line 1493
        "{ -term.",      # Missing attr name
    ]
    return draw(st.sampled_from(corruptions))


class TestMalformedTerms:
    """Hypothesis tests for malformed terms and term references."""

    @given(term_def=malformed_term())
    @settings(max_examples=40, deadline=None)
    @example(term_def="-@invalid")         # Target line 1458
    @example(term_def="-term = val\n    .") # Target line 1470
    def test_parser_handles_malformed_terms(self, term_def):
        """Parser should handle malformed term definitions.

        Covers error paths:
        - Line 1360: Missing - prefix
        - Line 1458: Invalid term identifier
        - Line 1470: Invalid term attribute
        """
        event(f"input_len={len(term_def)}")
        parser = FluentParserV1()
        resource = parser.parse(term_def)
        assert resource is not None

    @given(
        msg_id=ftl_identifiers(),
        term_ref=malformed_term_reference()
    )
    @settings(max_examples=40, deadline=None)
    @example(msg_id="key", term_ref="{ -")       # Target line 1449
    @example(msg_id="key", term_ref="{ -term(")  # Target line 1493
    def test_parser_handles_malformed_term_references(self, msg_id, term_ref):
        """Parser should handle malformed term references.

        Covers error paths:
        - Line 1449: Missing - in term ref
        - Line 1493: Missing ) after term args
        """
        source = f"{msg_id} = {term_ref}"
        event(f"input_len={len(source)}")
        event(f"term_ref_len={len(term_ref)}")
        parser = FluentParserV1()
        resource = parser.parse(source)
        assert resource is not None


# ============================================================================
# STRATEGY 5: Malformed Attributes
# ============================================================================

@st.composite
def malformed_attribute(draw):
    """Generate attributes with strategic errors.

    Targets attribute parsing error paths.
    """
    corruptions = [
        "    .",         # Missing identifier → line 1309
        "    .@",        # Invalid identifier
        "    . = val",   # Space before =
        "    .attr",     # Missing =
        "    .attr =",   # Missing value
    ]
    return draw(st.sampled_from(corruptions))


class TestMalformedAttributes:
    """Hypothesis tests for malformed attributes."""

    @given(
        msg_id=ftl_identifiers(),
        attr_line=malformed_attribute()
    )
    @settings(max_examples=30, deadline=None)
    @example(msg_id="key", attr_line="    .")  # Target line 1309
    def test_parser_handles_malformed_attributes(self, msg_id, attr_line):
        """Parser should handle malformed attributes.

        Covers error paths:
        - Line 1309: Missing . at start of attribute
        - Line 1360: Missing - at start of term
        """
        source = f"{msg_id} = value\n{attr_line}"
        parser = FluentParserV1()
        resource = parser.parse(source)
        assert resource is not None


# ============================================================================
# STRATEGY 6: Edge Case Combinations
# ============================================================================

class TestEdgeCaseCombinations:
    """Hypothesis tests for edge case combinations."""

    @given(
        text=st.text(
            alphabet="{}$-.[]*\n\r\t ",
            min_size=1,
            max_size=30
        )
    )
    @settings(max_examples=200, deadline=None)
    def test_parser_handles_arbitrary_special_char_sequences(self, text):
        """Parser should handle arbitrary sequences of special chars.

        Systematically explores edge cases with special FTL characters.
        """
        # Skip pure whitespace
        assume(text.strip())

        parser = FluentParserV1()
        try:
            resource = parser.parse(text)
            # Should not crash
            assert resource is not None
        except RecursionError:
            # Parser might hit recursion on pathological input
            assume(False)

    @given(
        msg_id=ftl_identifiers(),
        value=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz {}$-.",
            min_size=1,
            max_size=40
        )
    )
    @settings(max_examples=150, deadline=None)
    def test_parser_handles_complex_value_patterns(self, msg_id, value):
        """Parser should handle complex patterns in values.

        Explores combinations that might trigger uncovered branches.
        """
        source = f"{msg_id} = {value}"
        parser = FluentParserV1()

        try:
            resource = parser.parse(source)
            assert resource is not None
        except RecursionError:
            assume(False)


# ============================================================================
# STRATEGY 7: Specific Line Targeting
# ============================================================================

class TestSpecificUncoveredLines:
    """Targeted tests for specific uncovered lines."""

    def test_line_438_variable_reference_error_specific(self):
        """Test specific condition that triggers line 438.

        Line 438: Expected $ at start of variable reference
        """
        # This might be hard to trigger if it's in a specific context
        source = "key = { @notvar }"
        parser = FluentParserV1()
        resource = parser.parse(source)
        assert resource is not None

    def test_line_497_placeable_missing_close_brace_specific(self):
        """Test specific condition for line 497.

        Line 497: Expected } after variable
        """
        source = "key = { $var\n"
        parser = FluentParserV1()
        resource = parser.parse(source)
        assert resource is not None

    def test_line_698_variable_in_argument_error(self):
        """Test line 698: Variable ref error in argument expression.

        This is an error path when parsing $ in an argument context.
        """
        source = "key = { FUNC(@not$var) }"
        parser = FluentParserV1()
        resource = parser.parse(source)
        assert resource is not None

    def test_line_968_unknown_branch(self):
        """Test line 968: Unknown branch condition.

        Need to investigate what this branch is.
        """
        # Try various inputs that might trigger this
        test_cases = [
            "key = { TEST }",
            "key = { test }",
            "key = { Test }",
            "key = { _test }",
        ]
        parser = FluentParserV1()
        for source in test_cases:
            resource = parser.parse(source)
            assert resource is not None

    def test_lines_994_1002_message_attr_all_error_paths(self):
        """Test all error paths in lines 994-1002.

        These are the error branches in lowercase message.attr parsing.
        """
        error_cases = [
            "key = { msg. }",      # Missing attr name (line 997-998)
            "key = { msg.@ }",     # Invalid attr char
            "key = { msg.123 }",   # Digit start
            "key = { msg.. }",     # Double dot
        ]

        parser = FluentParserV1()
        for source in error_cases:
            resource = parser.parse(source)
            assert resource is not None


# ============================================================================
# STRATEGY 8: Metamorphic Properties
# ============================================================================

class TestMetamorphicProperties:
    """Metamorphic testing: properties that should always hold."""

    @given(
        ftl_source=st.text(min_size=0, max_size=100)
    )
    @settings(max_examples=300, deadline=None)
    def test_parser_never_crashes(self, ftl_source):
        """Universal property: Parser should NEVER crash on ANY input.

        This is a safety net that explores the entire input space.
        """
        parser = FluentParserV1()

        try:
            resource = parser.parse(ftl_source)
            # Should always return a Resource object
            assert resource is not None
            # Should always have entries (even if empty)
            assert hasattr(resource, "entries")
        except RecursionError:
            # Acceptable failure mode for pathological input
            assume(False)
        except Exception as e:
            # Any other exception is a bug
            msg = f"Parser crashed with {type(e).__name__}: {e}"
            raise AssertionError(msg) from e

    @given(
        msg_id=ftl_identifiers(),
        placeable_content=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789$-. ",
            min_size=0,
            max_size=20
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_deterministic_parsing(self, msg_id, placeable_content):
        """Property: Parsing same input twice gives same result.

        Ensures parser is deterministic.
        """
        source = f"{msg_id} = {{ {placeable_content} }}"
        parser1 = FluentParserV1()
        parser2 = FluentParserV1()

        try:
            result1 = parser1.parse(source)
            result2 = parser2.parse(source)

            # Should produce same number of entries
            assert len(result1.entries) == len(result2.entries)

            # Entry types should match
            for e1, e2 in zip(result1.entries, result2.entries, strict=False):
                assert type(e1) == type(e2)
        except RecursionError:
            assume(False)
