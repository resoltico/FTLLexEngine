# mypy: ignore-errors
"""Split test cases from tests/test_validation_resource_dependency_graph.py."""

from tests.validation_resource_dependency_graph_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# CYCLE DETECTION BRANCH COVERAGE
# ============================================================================


class TestValidationResourceBranchCoverage:
    """Test validation/resource.py cycle detection branch coverage."""

    def test_cycle_detection_loop_iterations(self) -> None:
        """Cycle detection handles term-to-term cycle correctly."""
        msg_a = Message(
            id=Identifier("a"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(id=Identifier("x"))
                    ),
                )
            ),
            attributes=(),
        )
        msg_b = Message(
            id=Identifier("b"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(id=Identifier("y"))
                    ),
                )
            ),
            attributes=(),
        )

        term_x = Term(
            id=Identifier("x"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(id=Identifier("y"))
                    ),
                )
            ),
            attributes=(),
        )
        term_y = Term(
            id=Identifier("y"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=TermReference(id=Identifier("x"))
                    ),
                )
            ),
            attributes=(),
        )

        messages_dict = {"a": msg_a, "b": msg_b}
        terms_dict = {"x": term_x, "y": term_y}

        graph = build_dependency_graph(messages_dict, terms_dict)
        warnings = _detect_circular_references(graph)

        cycle_warnings = [w for w in warnings if "circular" in w.message.lower()]
        assert len(cycle_warnings) >= 1

    def test_cross_type_cycle_detection(self) -> None:
        """Cycle detection finds message-to-term-to-message cycle."""
        msg_a = Message(
            id=Identifier("a"),
            value=Pattern(
                elements=(
                    Placeable(expression=TermReference(id=Identifier("t"))),
                )
            ),
            attributes=(),
        )

        term_t = Term(
            id=Identifier("t"),
            value=Pattern(
                elements=(
                    Placeable(expression=MessageReference(id=Identifier("a"))),
                )
            ),
            attributes=(),
        )

        messages_dict = {"a": msg_a}
        terms_dict = {"t": term_t}

        graph = build_dependency_graph(messages_dict, terms_dict)
        warnings = _detect_circular_references(graph)

        assert any("circular" in w.message.lower() for w in warnings)


class TestResourceValidationBranchCoverageExtended:
    """Extended resource validation branch coverage tests."""

    def test_cycle_detection_with_multiple_independent_cycles(self) -> None:
        """Cycle detection finds both of two independent cycles in the same resource."""
        msg_a = Message(
            id=Identifier("a"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("b"))),)
            ),
            attributes=(),
        )
        msg_b = Message(
            id=Identifier("b"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("a"))),)
            ),
            attributes=(),
        )

        msg_x = Message(
            id=Identifier("x"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("y"))),)
            ),
            attributes=(),
        )
        msg_y = Message(
            id=Identifier("y"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("x"))),)
            ),
            attributes=(),
        )

        messages_dict = {"a": msg_a, "b": msg_b, "x": msg_x, "y": msg_y}
        terms_dict: dict[str, Term] = {}

        graph = build_dependency_graph(messages_dict, terms_dict)
        warnings = _detect_circular_references(graph)

        cycle_warnings = [w for w in warnings if "circular" in w.message.lower()]
        assert len(cycle_warnings) >= 2

    def test_no_cycles_in_linear_chain(self) -> None:
        """Linear reference chain without cycles produces no cycle warnings."""
        msg_a = Message(
            id=Identifier("a"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("b"))),)
            ),
            attributes=(),
        )
        msg_b = Message(
            id=Identifier("b"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("c"))),)
            ),
            attributes=(),
        )
        msg_c = Message(
            id=Identifier("c"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("d"))),)
            ),
            attributes=(),
        )
        msg_d = Message(
            id=Identifier("d"),
            value=Pattern(elements=(TextElement("End"),)),
            attributes=(),
        )

        messages_dict = {"a": msg_a, "b": msg_b, "c": msg_c, "d": msg_d}
        terms_dict: dict[str, Term] = {}

        graph = build_dependency_graph(messages_dict, terms_dict)
        warnings = _detect_circular_references(graph)

        cycle_warnings = [w for w in warnings if "circular" in w.message.lower()]
        assert len(cycle_warnings) == 0
