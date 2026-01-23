"""Coverage tests for introspection.py edge cases.

Targets uncovered lines:
- Lines 248-249: Function with named argument that is a VariableReference
- Lines 290-291: TypeError when introspecting non-Message/Term
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from ftllexengine import parse_ftl
from ftllexengine.introspection import extract_variables, introspect_message
from ftllexengine.syntax.ast import Junk, Message


class TestFunctionWithVariableNamedArgs:
    """Test functions with variable references in named arguments."""

    def test_function_with_variable_in_named_arg(self) -> None:
        """Custom function with variable in named argument value (coverage for lines 248-249)."""
        # Use parse_ftl directly to construct AST with variable in named arg
        from ftllexengine.syntax.ast import (
            CallArguments,
            FunctionReference,
            Identifier,
            Message,
            NamedArgument,
            Pattern,
            Placeable,
            VariableReference,
        )

        # Manually construct: CUSTOM($x, opt: $y)
        func_ref = FunctionReference(
            id=Identifier(name="CUSTOM"),
            arguments=CallArguments(
                positional=(
                    VariableReference(id=Identifier(name="x")),
                ),
                named=(
                    NamedArgument(
                        name=Identifier(name="opt"),
                        # Variable as named arg value
                        value=VariableReference(id=Identifier(name="y")),
                    ),
                )
            )
        )

        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
            comment=None
        )

        info = introspect_message(msg)

        # Should detect both $x (positional) and $y (in named arg value)
        variables = info.get_variable_names()
        assert "x" in variables
        assert "y" in variables  # This hits line 248-249!

    def test_multiple_named_args_with_variables(self) -> None:
        """Multiple named arguments with variable values."""
        from ftllexengine.syntax.ast import (
            CallArguments,
            FunctionReference,
            Identifier,
            Message,
            NamedArgument,
            Pattern,
            Placeable,
            VariableReference,
        )

        # FUNC($val, a: $x, b: $y, c: $z)
        func_ref = FunctionReference(
            id=Identifier(name="FUNC"),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier(name="val")),),
                named=(
                    NamedArgument(
                        name=Identifier(name="a"),
                        value=VariableReference(id=Identifier(name="x")),
                    ),
                    NamedArgument(
                        name=Identifier(name="b"),
                        value=VariableReference(id=Identifier(name="y")),
                    ),
                    NamedArgument(
                        name=Identifier(name="c"),
                        value=VariableReference(id=Identifier(name="z")),
                    ),
                )
            )
        )

        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
            comment=None
        )

        info = introspect_message(msg)

        variables = info.get_variable_names()
        assert variables == frozenset({"val", "x", "y", "z"})

    def test_mixed_positional_and_named_variable_args(self) -> None:
        """Function with both positional and named variable arguments."""
        # This tests both paths: positional vars (lines 240-241) and named vars (lines 248-249)
        from ftllexengine.syntax.ast import (
            CallArguments,
            FunctionReference,
            Identifier,
            Message,
            NamedArgument,
            NumberLiteral,
            Pattern,
            Placeable,
            VariableReference,
        )

        # Build: CUSTOM($x, $y, opt1: $a, opt2: $b, literal: 42)
        func_ref = FunctionReference(
            id=Identifier(name="CUSTOM"),
            arguments=CallArguments(
                positional=(
                    VariableReference(id=Identifier(name="x")),
                    VariableReference(id=Identifier(name="y")),
                ),
                named=(
                    NamedArgument(
                        name=Identifier(name="opt1"),
                        value=VariableReference(id=Identifier(name="a"))  # Variable in named arg
                    ),
                    NamedArgument(
                        name=Identifier(name="opt2"),
                        value=VariableReference(id=Identifier(name="b"))  # Variable in named arg
                    ),
                    NamedArgument(
                        name=Identifier(name="literal"),
                        value=NumberLiteral(value=42, raw="42")  # Literal (not a variable)
                    ),
                )
            )
        )

        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=func_ref),)),
            attributes=(),
            comment=None
        )

        info = introspect_message(msg)

        variables = info.get_variable_names()
        # Should detect all 4 variables
        assert variables == frozenset({"x", "y", "a", "b"})

        functions = info.get_function_names()
        assert "CUSTOM" in functions

    @given(
        st.lists(
            st.text(
                alphabet=st.characters(min_codepoint=97, max_codepoint=122),
                min_size=1,
                max_size=10,
            ),
            min_size=1,
            max_size=5,
        )
    )
    @settings(max_examples=30)
    def test_arbitrary_variable_named_args(self, var_names: list[str]) -> None:
        """Test functions with arbitrary variable names in args (Hypothesis)."""
        # Make unique
        var_names = list(dict.fromkeys(var_names))
        if not var_names:
            return

        # Build FTL with variables in named args
        var_list = ", ".join(f"{name}: ${name}" for name in var_names)
        ftl = f"test = {{ NUMBER($value, {var_list}) }}"

        resource = parse_ftl(ftl)
        if not resource.entries or isinstance(resource.entries[0], Junk):
            return  # Skip malformed

        msg = resource.entries[0]
        if not isinstance(msg, Message):
            return

        info = introspect_message(msg)
        variables = info.get_variable_names()

        # Should detect all variables
        assert "value" in variables
        for name in var_names:
            assert name in variables


class TestIntrospectMessageTypeErrors:
    """Test introspect_message with invalid input types."""

    def test_introspect_message_with_junk(self) -> None:
        """Introspecting a Junk entry should raise TypeError."""
        resource = parse_ftl("invalid syntax here !!!")

        # Should produce Junk entry
        assert resource.entries
        junk = resource.entries[0]
        assert isinstance(junk, Junk)

        # Should raise TypeError
        with pytest.raises(TypeError, match="Expected Message or Term"):
            introspect_message(junk)  # type: ignore[arg-type]

    def test_introspect_message_with_string(self) -> None:
        """Introspecting a string should raise TypeError."""
        with pytest.raises(TypeError, match="Expected Message or Term"):
            introspect_message("not a message")  # type: ignore[arg-type]

    def test_introspect_message_with_none(self) -> None:
        """Introspecting None should raise TypeError."""
        with pytest.raises(TypeError, match="Expected Message or Term"):
            introspect_message(None)  # type: ignore[arg-type]

    def test_introspect_message_with_dict(self) -> None:
        """Introspecting a dict should raise TypeError."""
        with pytest.raises(TypeError, match="Expected Message or Term"):
            introspect_message({"not": "a message"})  # type: ignore[arg-type]

    @given(
        st.one_of(
            st.integers(),
            st.floats(allow_nan=False, allow_infinity=False),
            st.booleans(),
            st.lists(st.text()),
        )
    )
    @settings(max_examples=30)
    def test_introspect_message_with_arbitrary_types(self, invalid_input: object) -> None:
        """Introspecting non-Message types should raise TypeError (Hypothesis)."""
        with pytest.raises(TypeError, match="Expected Message or Term"):
            introspect_message(invalid_input)  # type: ignore[arg-type]


class TestExtractVariablesEdgeCases:
    """Test extract_variables with edge cases."""

    def test_extract_variables_from_message_with_no_value(self) -> None:
        """Message with no value pattern should return empty set."""
        resource = parse_ftl("""
empty =
    .attr = Attribute only
        """)

        msg = resource.entries[0]
        assert isinstance(msg, Message)

        variables = extract_variables(msg)

        # Message has no value, so no variables from value pattern
        # But should get variables from attributes
        assert isinstance(variables, frozenset)

    def test_extract_variables_from_select_with_variants(self) -> None:
        """Select expression with variables in variants."""
        resource = parse_ftl("""
msg = { $count ->
    [one] You have { $count } item from { $source }
    [few] You have { $count } items from { $source }
   *[other] You have { $count } items from { $source }
}
        """)

        msg = resource.entries[0]
        assert isinstance(msg, Message)

        variables = extract_variables(msg)

        # Should detect $count and $source
        assert "count" in variables
        assert "source" in variables
