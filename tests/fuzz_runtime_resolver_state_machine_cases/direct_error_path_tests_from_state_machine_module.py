# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_runtime_resolver_state_machine.py."""

from tests.fuzz_runtime_resolver_state_machine_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# DIRECT ERROR PATH TESTS (from state machine module)
# ============================================================================


class TestStatefulErrorPaths:
    """Direct tests for specific error paths that are hard to reach via state machine."""

    def test_term_not_found_direct(self) -> None:
        """Term not found error (line 176)."""
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(
                            id=Identifier(name="nonexistent"),
                            attribute=None,
                        )
                    ),
                )
            ),
            attributes=(),
            comment=None,
        )

        result, errors = resolver.resolve_message(message, args={})
        assert len(errors) > 0
        assert "{-nonexistent}" in result

    def test_term_attribute_not_found_direct(self) -> None:
        """Term attribute not found error (lines 182-185)."""
        from ftllexengine.syntax import Term

        term = Term(
            id=Identifier(name="brand"),
            value=simple_pattern("Firefox"),
            attributes=(),
            comment=None,
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={"brand": term},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        message = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(
                            id=Identifier(name="brand"),
                            attribute=Identifier(name="nonexistent"),
                        )
                    ),
                )
            ),
            attributes=(),
            comment=None,
        )

        result, errors = resolver.resolve_message(message, args={})
        assert len(errors) > 0
        assert "{-brand.nonexistent}" in result

    def test_message_not_found_reference(self) -> None:
        """Message not found when referenced from another message (line 164)."""
        message = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=MessageReference(
                            id=Identifier(name="nonexistent"),
                            attribute=None,
                        )
                    ),
                )
            ),
            attributes=(),
            comment=None,
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={"test": message},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, args={})
        assert len(errors) > 0
        assert "{nonexistent}" in result

    def test_variable_not_provided(self) -> None:
        """Variable not provided in args (line 157)."""
        message = Message(
            id=Identifier(name="test"),
            value=variable_pattern("missing_var"),
            attributes=(),
            comment=None,
        )

        resolver = FluentResolver(
            locale="en_US",
            messages={"test": message},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(message, args={})
        assert len(errors) > 0
        assert "{$missing_var}" in result

    @given(st.data())
    def test_format_value_edge_cases(self, data: st.DataObject) -> None:
        """Property: _format_value never crashes, always returns string (lines 268-278)."""
        resolver = FluentResolver(
            locale="en_US",
            messages={},
            terms={},
            function_registry=create_default_registry(),
            use_isolating=False,
        )

        test_values: list[FluentValue] = [
            data.draw(st.text()),
            data.draw(st.integers()),
            data.draw(st.decimals(allow_nan=False, allow_infinity=False)),
            data.draw(st.booleans()),
            None,
        ]

        value = None
        for value in test_values:
            result = resolver._format_value(value)
            assert isinstance(result, str), f"_format_value({value}) should return string"
        val_type = type(value).__name__
        event(f"last_value_type={val_type}")

    def test_select_expression_no_variants(self) -> None:
        """SelectExpression with no variants raises ValueError at construction."""
        with pytest.raises(ValueError, match="at least one variant"):
            SelectExpression(
                selector=NumberLiteral(value=1, raw="1"),
                variants=(),
            )
