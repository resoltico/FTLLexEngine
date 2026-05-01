# mypy: ignore-errors
"""Split test cases from tests/test_runtime_resolver_depth_cycles.py."""

from tests.runtime_resolver_depth_cycles_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Multi-Placeable Pattern Resolution
# ============================================================================


class TestPatternMultiplePlaceables:
    """Coverage for pattern with multiple consecutive placeables."""

    def test_pattern_with_two_placeables_in_sequence(self) -> None:
        """Pattern with consecutive placeables resolves all correctly."""
        pattern = Pattern(
            elements=(
                Placeable(expression=VariableReference(id=Identifier("first"))),
                TextElement(value=" and "),
                Placeable(expression=VariableReference(id=Identifier("second"))),
            )
        )
        message = Message(id=Identifier("msg"), value=pattern, attributes=())
        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        result, errors = resolver.resolve_message(
            message, {"first": "A", "second": "B"}
        )

        assert result == "A and B"
        assert errors == ()

    @given(
        count=st.integers(min_value=2, max_value=10),
        values=st.lists(st.text(min_size=1, max_size=10), min_size=2, max_size=10),
    )
    def test_pattern_with_multiple_placeables_property(
        self, count: int, values: list[str]
    ) -> None:
        """Property: Pattern with N placeables resolves all correctly."""
        event(f"count={count}")
        values = values[:count]
        if len(values) < count:
            values.extend(["X"] * (count - len(values)))

        elements: list[TextElement | Placeable] = []
        for i in range(count):
            if i > 0:
                elements.append(TextElement(value=" "))
            elements.append(
                Placeable(expression=VariableReference(id=Identifier(f"v{i}")))
            )

        pattern = Pattern(elements=tuple(elements))
        message = Message(id=Identifier("msg"), value=pattern, attributes=())
        resolver = FluentResolver(
            locale="en",
            messages={"msg": message},
            terms={},
            function_registry=FunctionRegistry(),
            use_isolating=False,
        )

        args = {f"v{i}": values[i] for i in range(count)}
        result, errors = resolver.resolve_message(message, args)

        assert errors == ()
        assert result == " ".join(values)
