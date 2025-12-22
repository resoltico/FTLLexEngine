"""Targeted tests for introspection.py to achieve 100% branch coverage.

Covers missing branches:
- Line 198->exit: TextElement in pattern (pass statement)
- Line 218->exit: Select expression branch
- Line 235->251: Function without arguments
- Line 238->237: Function with positional arguments
- Line 296->300: Message without value (only attributes)
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.introspection import introspect_message
from ftllexengine.syntax.ast import Message
from ftllexengine.syntax.parser import FluentParserV1

# ============================================================================
# COVERAGE TARGET: Line 198->exit (TextElement)
# ============================================================================


class TestTextElementBranchCoverage:
    """Test TextElement branch in _visit_pattern_element (line 198->exit)."""

    def test_message_with_only_text_elements(self) -> None:
        """COVERAGE: Line 198->exit - Pattern with only TextElement."""
        parser = FluentParserV1()
        ftl_source = "msg = Plain text without any placeables"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        # Introspect - should handle TextElement (pass branch)
        result = introspect_message(msg)

        # No variables, functions, or selectors in plain text
        assert len(result.get_variable_names()) == 0
        assert len(result.get_function_names()) == 0
        assert not result.has_selectors

    @given(
        text=st.text(min_size=1, max_size=50).filter(
            lambda s: s.strip()
            and "{" not in s
            and "}" not in s
            and "[" not in s
            and "]" not in s
            and "#" not in s
            and "-" not in s[0:1]
            and "." not in s[0:1]
        )
    )
    def test_text_only_message_property(self, text: str) -> None:
        """PROPERTY: Messages with only text have no extracted metadata."""
        parser = FluentParserV1()
        safe_text = text.replace("\\", "\\\\").replace("\n", " ").strip()
        if not safe_text:
            safe_text = "text"

        ftl_source = f"msg = {safe_text}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]

        # Skip if parsing produced Junk (FTL syntax collision)
        if not isinstance(msg, Message):
            return

        result = introspect_message(msg)

        # Text-only messages have no variables or functions
        assert len(result.get_variable_names()) == 0
        assert len(result.get_function_names()) == 0


# ============================================================================
# COVERAGE TARGET: Line 218->exit (Select Expression)
# ============================================================================


class TestSelectExpressionBranchCoverage:
    """Test select expression branch in _visit_expression (line 218->exit)."""

    def test_select_expression_detection(self) -> None:
        """COVERAGE: Line 218->exit - Select expression sets has_selectors."""
        parser = FluentParserV1()
        ftl_source = """
msg = { $count ->
    [0] No items
    [1] One item
   *[other] Many items
}
"""

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        result = introspect_message(msg)

        # Select expression should set has_selectors flag
        assert result.has_selectors is True

    def test_select_with_variable_in_selector(self) -> None:
        """COVERAGE: Line 218->exit - Select expression with variable selector."""
        parser = FluentParserV1()
        ftl_source = """
msg = { $value ->
    [a] Value A
   *[other] Other value
}
"""

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        result = introspect_message(msg)

        # Should detect selector variable and set has_selectors
        assert "value" in result.get_variable_names()
        assert result.has_selectors is True

    @given(var_name=st.from_regex(r"[a-z]+", fullmatch=True))
    def test_select_expression_property(self, var_name: str) -> None:
        """PROPERTY: Select expressions always set has_selectors flag."""
        parser = FluentParserV1()
        ftl_source = f"""
msg = {{ ${var_name} ->
    [yes] Yes
   *[other] No
}}
"""

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        result = introspect_message(msg)

        assert result.has_selectors is True


# ============================================================================
# COVERAGE TARGET: Line 235->251 (Function without Arguments)
# ============================================================================


class TestFunctionWithoutArgumentsCoverage:
    """Test function without arguments branch (line 235->251)."""

    def test_function_call_no_arguments(self) -> None:
        """COVERAGE: Line 235->251 - Function call with no arguments."""
        parser = FluentParserV1()
        ftl_source = "msg = Result: { BUILTIN() }"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        result = introspect_message(msg)

        # Should detect function even without arguments
        func_names = result.get_function_names()
        assert "BUILTIN" in func_names

    @given(func_name=st.from_regex(r"[A-Z][A-Z0-9]{0,10}", fullmatch=True))
    def test_no_args_function_property(self, func_name: str) -> None:
        """PROPERTY: Functions without arguments are detected."""
        parser = FluentParserV1()
        ftl_source = f"msg = {{ {func_name}() }}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        result = introspect_message(msg)

        assert func_name in result.get_function_names()


# ============================================================================
# COVERAGE TARGET: Line 238->237 (Function with Positional Arguments)
# ============================================================================


class TestFunctionPositionalArgumentsCoverage:
    """Test function with positional arguments branch (line 238->237)."""

    def test_function_with_positional_args(self) -> None:
        """COVERAGE: Line 238->237 - Function with positional arguments."""
        parser = FluentParserV1()
        ftl_source = "msg = { NUMBER($value) }"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        result = introspect_message(msg)

        # Should detect function and variable in argument
        assert "NUMBER" in result.get_function_names()
        assert "value" in result.get_variable_names()

    def test_function_multiple_positional_args(self) -> None:
        """COVERAGE: Line 238->237 - Loop over multiple positional args."""
        parser = FluentParserV1()
        ftl_source = "msg = { FUNC($a, $b, $c) }"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        result = introspect_message(msg)

        # All positional argument variables should be detected
        variables = result.get_variable_names()
        assert "a" in variables
        assert "b" in variables
        assert "c" in variables

    @given(
        var1=st.from_regex(r"[a-z]+", fullmatch=True),
        var2=st.from_regex(r"[a-z]+", fullmatch=True),
    )
    def test_positional_args_property(self, var1: str, var2: str) -> None:
        """PROPERTY: All positional arguments are extracted."""
        from hypothesis import assume  # noqa: PLC0415

        assume(var1 != var2)

        parser = FluentParserV1()
        ftl_source = f"msg = {{ FUNC(${var1}, ${var2}) }}"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        result = introspect_message(msg)

        variables = result.get_variable_names()
        assert var1 in variables
        assert var2 in variables


# ============================================================================
# COVERAGE TARGET: Line 296->300 (Message without Value)
# ============================================================================


class TestMessageWithoutValueCoverage:
    """Test message without value branch (line 296->300)."""

    def test_message_without_value_only_attributes(self) -> None:
        """COVERAGE: Line 296->300 - Message with no value, only attributes."""
        parser = FluentParserV1()
        ftl_source = """
msg =
    .attr1 = Value 1
    .attr2 = Value 2
"""

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        # Introspect - should handle message without value
        result = introspect_message(msg)

        # Should still introspect (no crash)
        assert result.message_id == "msg"

    def test_message_attributes_with_variables(self) -> None:
        """COVERAGE: Line 296->300 - Message without value but attributes have variables."""
        parser = FluentParserV1()
        ftl_source = """
msg =
    .formal = Hello { $name }
    .casual = Hi { $name }
"""

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        result = introspect_message(msg)

        # Should detect variables in attributes even without value
        assert "name" in result.get_variable_names()

    @given(attr_name=st.from_regex(r"[a-z]+", fullmatch=True))
    def test_attribute_only_message_property(self, attr_name: str) -> None:
        """PROPERTY: Messages without value but with attributes introspect correctly."""
        parser = FluentParserV1()
        ftl_source = f"msg =\n    .{attr_name} = Text"

        resource = parser.parse(ftl_source)
        msg = resource.entries[0]
        assert isinstance(msg, Message)

        result = introspect_message(msg)

        # Should not crash
        assert result.message_id == "msg"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestIntrospectionIntegration:
    """Integration tests combining multiple coverage targets."""

    def test_complex_message_all_branches(self) -> None:
        """Integration: Message exercising all coverage branches."""
        parser = FluentParserV1()
        ftl_source = """
greeting = Plain text { $name } and { UPPER($title) }
    .formal = Dear { $name },

status = { $count ->
    [0] No items
    [1] One item
   *[other] Many items
}

simple = Just text
    .attr = Also just text
"""

        resource = parser.parse(ftl_source)

        # Test first message - has text, variables, functions
        msg1 = resource.entries[0]
        assert isinstance(msg1, Message)
        result1 = introspect_message(msg1)
        assert "name" in result1.get_variable_names()
        assert "title" in result1.get_variable_names()
        assert "UPPER" in result1.get_function_names()

        # Test second message - has select expression
        msg2 = resource.entries[1]
        assert isinstance(msg2, Message)
        result2 = introspect_message(msg2)
        assert result2.has_selectors is True
        assert "count" in result2.get_variable_names()

        # Test third message - only text elements
        msg3 = resource.entries[2]
        assert isinstance(msg3, Message)
        result3 = introspect_message(msg3)
        assert len(result3.get_variable_names()) == 0
        assert not result3.has_selectors
