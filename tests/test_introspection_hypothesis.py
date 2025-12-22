"""Hypothesis property-based tests for message introspection.

Tests variable extraction, function detection, reference tracking properties.
Complements test_introspection.py with property-based testing.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine.introspection import extract_variables, introspect_message
from ftllexengine.syntax.ast import Message
from ftllexengine.syntax.parser import FluentParserV1

# ============================================================================
# HYPOTHESIS STRATEGIES
# ============================================================================


# Strategy for variable names (FTL identifiers) - use st.from_regex per hypothesis.md
variable_names = st.from_regex(r"[a-z]+", fullmatch=True)

# Strategy for message IDs - use st.from_regex per hypothesis.md
message_ids = st.from_regex(r"[a-z]+", fullmatch=True)


# ============================================================================
# PROPERTY TESTS - VARIABLE EXTRACTION
# ============================================================================


class TestVariableExtractionProperties:
    """Test variable extraction invariants and properties."""

    @given(var_name=variable_names)
    @settings(max_examples=200)
    def test_simple_variable_always_extracted(self, var_name: str) -> None:
        """PROPERTY: Simple { $var } always extracts var."""
        parser = FluentParserV1()
        ftl_source = f"msg = Hello {{ ${var_name} }}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        variables = extract_variables(msg)

        assert var_name in variables

    @given(var_name=variable_names)
    @settings(max_examples=200)
    def test_duplicate_variables_deduplicated(self, var_name: str) -> None:
        """PROPERTY: Duplicate { $var } { $var } extracts var once."""
        parser = FluentParserV1()
        ftl_source = f"msg = Hello {{ ${var_name} }} {{ ${var_name} }}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        variables = extract_variables(msg)

        # Should only appear once (frozenset deduplication)
        assert var_name in variables
        assert len([v for v in variables if v == var_name]) == 1

    @given(
        var1=variable_names,
        var2=variable_names,
    )
    @settings(max_examples=200)
    def test_multiple_variables_all_extracted(self, var1: str, var2: str) -> None:
        """PROPERTY: { $a } { $b } extracts both a and b."""
        parser = FluentParserV1()
        ftl_source = f"msg = Hello {{ ${var1} }} {{ ${var2} }}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        variables = extract_variables(msg)

        assert var1 in variables
        if var1 != var2:
            assert var2 in variables

    @given(msg_id=message_ids)
    @settings(max_examples=100)
    def test_no_variables_returns_empty_set(self, msg_id: str) -> None:
        """PROPERTY: Message with no variables returns empty set."""
        parser = FluentParserV1()
        ftl_source = f"{msg_id} = Hello World"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        variables = extract_variables(msg)

        assert len(variables) == 0

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_variable_in_function_extracted(self, var_name: str) -> None:
        """PROPERTY: NUMBER($var) extracts var."""
        parser = FluentParserV1()
        ftl_source = f"msg = {{ NUMBER(${var_name}) }}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        variables = extract_variables(msg)

        assert var_name in variables

    @given(
        var_name=variable_names,
        attr_name=st.from_regex(r"[a-z]+", fullmatch=True),  # Use st.from_regex
    )
    @settings(max_examples=100)
    def test_attribute_variable_extracted(self, var_name: str, attr_name: str) -> None:
        """PROPERTY: Variables in attributes are extracted."""
        parser = FluentParserV1()
        ftl_source = f"msg = Hello\n    .{attr_name} = {{ ${var_name} }}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        introspection = introspect_message(msg)
        variables = introspection.get_variable_names()

        assert var_name in variables


# ============================================================================
# PROPERTY TESTS - INTROSPECTION RESULTS
# ============================================================================


class TestIntrospectionProperties:
    """Test MessageIntrospection result properties."""

    @given(msg_id=message_ids)
    @settings(max_examples=200)
    def test_message_id_preserved(self, msg_id: str) -> None:
        """PROPERTY: introspect_message preserves message ID."""
        parser = FluentParserV1()
        ftl_source = f"{msg_id} = Hello"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        introspection = introspect_message(msg)

        assert introspection.message_id == msg_id

    @given(var_name=variable_names)
    @settings(max_examples=200)
    def test_get_variable_names_consistent_with_variables(
        self, var_name: str
    ) -> None:
        """PROPERTY: get_variable_names() equals variable names from variables."""
        parser = FluentParserV1()
        ftl_source = f"msg = Hello {{ ${var_name} }}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        introspection = introspect_message(msg)

        var_names = introspection.get_variable_names()
        assert var_name in var_names

        # All variables should have corresponding names
        assert len(introspection.variables) == len(var_names)

    @given(var_name=variable_names)
    @settings(max_examples=200)
    def test_requires_variable_matches_extraction(self, var_name: str) -> None:
        """PROPERTY: requires_variable(x) iff x in get_variable_names()."""
        parser = FluentParserV1()
        ftl_source = f"msg = Hello {{ ${var_name} }}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        introspection = introspect_message(msg)

        # If requires_variable returns True, should be in variable names
        if introspection.requires_variable(var_name):
            assert var_name in introspection.get_variable_names()

        # If in variable names, requires_variable should return True
        if var_name in introspection.get_variable_names():
            assert introspection.requires_variable(var_name)

    @given(msg_id=message_ids)
    @settings(max_examples=100)
    def test_no_selectors_when_no_select_expression(self, msg_id: str) -> None:
        """PROPERTY: Simple message has has_selectors=False."""
        parser = FluentParserV1()
        ftl_source = f"{msg_id} = Hello"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        introspection = introspect_message(msg)

        assert introspection.has_selectors is False

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_select_expression_sets_has_selectors(self, var_name: str) -> None:
        """PROPERTY: Message with select expression has has_selectors=True."""
        parser = FluentParserV1()
        ftl_source = f"""msg = {{ ${var_name} ->
    [one] One item
   *[other] Many items
}}"""

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        introspection = introspect_message(msg)

        assert introspection.has_selectors is True


# ============================================================================
# PROPERTY TESTS - FUNCTION DETECTION
# ============================================================================


class TestFunctionDetectionProperties:
    """Test function call detection properties."""

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_number_function_detected(self, var_name: str) -> None:
        """PROPERTY: NUMBER($var) detected as function call."""
        parser = FluentParserV1()
        ftl_source = f"msg = {{ NUMBER(${var_name}) }}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        introspection = introspect_message(msg)
        function_names = introspection.get_function_names()

        assert "NUMBER" in function_names

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_datetime_function_detected(self, var_name: str) -> None:
        """PROPERTY: DATETIME($var) detected as function call."""
        parser = FluentParserV1()
        ftl_source = f"msg = {{ DATETIME(${var_name}) }}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        introspection = introspect_message(msg)
        function_names = introspection.get_function_names()

        assert "DATETIME" in function_names

    @given(msg_id=message_ids)
    @settings(max_examples=100)
    def test_no_functions_returns_empty_set(self, msg_id: str) -> None:
        """PROPERTY: Message with no functions returns empty set."""
        parser = FluentParserV1()
        ftl_source = f"{msg_id} = Hello World"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        introspection = introspect_message(msg)
        function_names = introspection.get_function_names()

        assert len(function_names) == 0


# ============================================================================
# PROPERTY TESTS - IMMUTABILITY
# ============================================================================


class TestIntrospectionImmutability:
    """Test MessageIntrospection immutability properties."""

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_variables_frozenset_immutable(self, var_name: str) -> None:
        """PROPERTY: variables is a frozenset (immutable)."""
        parser = FluentParserV1()
        ftl_source = f"msg = Hello {{ ${var_name} }}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        introspection = introspect_message(msg)

        # Should be frozenset
        assert isinstance(introspection.variables, frozenset)

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_get_variable_names_returns_frozenset(self, var_name: str) -> None:
        """PROPERTY: get_variable_names() returns frozenset."""
        parser = FluentParserV1()
        ftl_source = f"msg = Hello {{ ${var_name} }}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        introspection = introspect_message(msg)
        var_names = introspection.get_variable_names()

        assert isinstance(var_names, frozenset)

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_get_function_names_returns_frozenset(self, var_name: str) -> None:
        """PROPERTY: get_function_names() returns frozenset."""
        parser = FluentParserV1()
        ftl_source = f"msg = {{ NUMBER(${var_name}) }}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        introspection = introspect_message(msg)
        func_names = introspection.get_function_names()

        assert isinstance(func_names, frozenset)


# ============================================================================
# PROPERTY TESTS - IDEMPOTENCE
# ============================================================================


class TestIntrospectionIdempotence:
    """Test idempotent introspection operations."""

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_extract_variables_idempotent(self, var_name: str) -> None:
        """PROPERTY: Multiple extract_variables() calls return same result."""
        parser = FluentParserV1()
        ftl_source = f"msg = Hello {{ ${var_name} }}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        result1 = extract_variables(msg)
        result2 = extract_variables(msg)
        result3 = extract_variables(msg)

        assert result1 == result2 == result3

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_introspect_message_idempotent(self, var_name: str) -> None:
        """PROPERTY: Multiple introspect_message() calls return equivalent results."""
        parser = FluentParserV1()
        ftl_source = f"msg = Hello {{ ${var_name} }}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        result1 = introspect_message(msg)
        result2 = introspect_message(msg)

        assert result1.message_id == result2.message_id
        assert result1.variables == result2.variables
        assert result1.functions == result2.functions
        assert result1.references == result2.references
        assert result1.has_selectors == result2.has_selectors

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_get_variable_names_idempotent(self, var_name: str) -> None:
        """PROPERTY: Multiple get_variable_names() calls return same result."""
        parser = FluentParserV1()
        ftl_source = f"msg = Hello {{ ${var_name} }}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        introspection = introspect_message(msg)

        result1 = introspection.get_variable_names()
        result2 = introspection.get_variable_names()
        result3 = introspection.get_variable_names()

        assert result1 == result2 == result3


# ============================================================================
# PROPERTY TESTS - ROBUSTNESS
# ============================================================================


class TestIntrospectionRobustness:
    """Test introspection robustness with edge cases."""

    @given(
        vars_list=st.lists(variable_names, min_size=0, max_size=10, unique=True),
    )
    @settings(max_examples=50)
    def test_multiple_variables_all_captured(self, vars_list: list[str]) -> None:
        """ROBUSTNESS: All variables in message are captured."""
        if not vars_list:
            return  # Skip empty list

        parser = FluentParserV1()
        # Build FTL with all variables
        placeables = " ".join([f"{{ ${v} }}" for v in vars_list])
        ftl_source = f"msg = {placeables}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        variables = extract_variables(msg)

        # All variables should be extracted
        for var in vars_list:
            assert var in variables

        # Should have exactly the right count
        assert len(variables) == len(vars_list)

    @given(msg_id=message_ids)
    @settings(max_examples=100)
    def test_minimal_message_introspection(self, msg_id: str) -> None:
        """ROBUSTNESS: Minimal valid message can be introspected."""
        parser = FluentParserV1()
        ftl_source = f"{msg_id} = X"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        # Should not raise
        introspection = introspect_message(msg)

        # Should have empty results (no variables/functions)
        assert len(introspection.get_variable_names()) == 0
        assert len(introspection.get_function_names()) == 0
        assert introspection.has_selectors is False
