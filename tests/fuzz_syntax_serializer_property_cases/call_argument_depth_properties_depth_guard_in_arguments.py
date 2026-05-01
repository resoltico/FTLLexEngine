# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_syntax_serializer_property.py."""

from tests.fuzz_syntax_serializer_property_cases import *  # noqa: F403 - shared split test support

# =============================================================================
# Call Argument Depth Properties (Depth Guard in Arguments)
# =============================================================================


class TestCallArgumentDepthProperties:
    """Test depth guard enforcement within call arguments.

    Serializer wraps each positional and named argument expression
    in depth_guard. Nested term/function calls must respect limits.
    """

    @given(depth=st.integers(min_value=1, max_value=8))
    def test_nested_call_arguments_serialize(
        self, depth: int
    ) -> None:
        """PROPERTY: Nested call arguments within limits serialize.

        Events emitted:
        - call_arg_depth={n}: Nesting depth of call arguments
        - outcome=nested_args_ok: Serialization succeeded
        """
        event(f"call_arg_depth={depth}")

        # Build: NUMBER(-t0(-t1(-t2(...$x...))))
        inner: VariableReference | TermReference
        inner = VariableReference(id=Identifier(name="x"))
        for i in range(depth):
            inner = TermReference(
                id=Identifier(name=f"t{i}"),
                arguments=CallArguments(
                    positional=(inner,), named=()
                ),
            )
        func = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(inner,), named=()
            ),
        )
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(Placeable(expression=func),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)
        event("outcome=nested_args_ok")
        assert "-t0(" in result
        assert "$x" in result

    def test_deep_call_args_exceed_depth_limit(self) -> None:
        """Deeply nested call arguments exceed depth limit."""
        inner: VariableReference | TermReference
        inner = VariableReference(id=Identifier(name="x"))
        for i in range(20):
            inner = TermReference(
                id=Identifier(name=f"t{i}"),
                arguments=CallArguments(
                    positional=(inner,), named=()
                ),
            )
        func = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(inner,), named=()
            ),
        )
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(Placeable(expression=func),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        with pytest.raises(SerializationDepthError):
            serialize(resource, validate=True, max_depth=10)

    @given(
        depth=st.integers(min_value=1, max_value=5),
        named_val=st.sampled_from(["decimal", "percent"]),
    )
    def test_named_args_in_nested_calls(
        self, depth: int, named_val: str
    ) -> None:
        """PROPERTY: Named arguments in nested calls serialize.

        Events emitted:
        - call_arg_depth={n}: Nesting depth
        - has_named_arg=True: Named argument present
        """
        event(f"call_arg_depth={depth}")
        event("has_named_arg=True")

        inner: VariableReference | TermReference
        inner = VariableReference(id=Identifier(name="x"))
        for i in range(depth):
            named = NamedArgument(
                name=Identifier(name="style"),
                value=StringLiteral(value=named_val),
            )
            inner = TermReference(
                id=Identifier(name=f"t{i}"),
                arguments=CallArguments(
                    positional=(inner,), named=(named,)
                ),
            )
        func = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(inner,), named=()
            ),
        )
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(Placeable(expression=func),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)
        assert f'style: "{named_val}"' in result
