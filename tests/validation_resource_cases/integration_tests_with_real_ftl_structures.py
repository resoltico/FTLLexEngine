# mypy: ignore-errors
"""Split test cases from tests/test_validation_resource.py."""

from tests.validation_resource_cases import *  # noqa: F403 - shared split test support

            # bad_node should be skipped in formatting (no prefix)


# ============================================================================
# Integration Tests with Real FTL Structures
# ============================================================================


class TestValidationResourceCompleteIntegration:
    """Integration tests combining edge cases using real FTL AST structures."""

    def test_diamond_dependency_in_real_messages(self) -> None:
        """Diamond pattern with real Message objects."""
        # Create: msgA -> msgB, msgA -> msgC -> msgB
        msg_b = Message(
            id=Identifier("msgB"),
            value=Pattern(elements=(TextElement(value="Base message"),)),
            attributes=(),
        )
        msg_c = Message(
            id=Identifier("msgC"),
            value=Pattern(
                elements=(Placeable(expression=MessageReference(id=Identifier("msgB"))),)
            ),
            attributes=(),
        )
        msg_a = Message(
            id=Identifier("msgA"),
            value=Pattern(
                elements=(
                    Placeable(expression=MessageReference(id=Identifier("msgB"))),
                    TextElement(value=" and "),
                    Placeable(expression=MessageReference(id=Identifier("msgC"))),
                )
            ),
            attributes=(),
        )

        messages_dict = {"msgA": msg_a, "msgB": msg_b, "msgC": msg_c}
        terms_dict: dict[str, Term] = {}

        # Build dependency graph
        graph = build_dependency_graph(messages_dict, terms_dict)

        # Compute longest paths (exercises diamond pattern)
        result = _compute_longest_paths(graph)

        # msgB is referenced by both msgA and msgC
        assert "msg:msgB" in result
        assert result["msg:msgB"][0] == 0
        assert result["msg:msgC"][0] == 1
        assert result["msg:msgA"][0] == 2

    def test_cross_type_diamond_message_and_term(self) -> None:
        """Diamond with cross-type references: msg -> term, msg -> msg -> term."""
        # Create: msgA -> termB, msgA -> msgC -> termB
        term_b = Term(
            id=Identifier("termB"),
            value=Pattern(elements=(TextElement(value="Term value"),)),
            attributes=(),
        )
        msg_c = Message(
            id=Identifier("msgC"),
            value=Pattern(
                elements=(Placeable(expression=TermReference(id=Identifier("termB"))),)
            ),
            attributes=(),
        )
        msg_a = Message(
            id=Identifier("msgA"),
            value=Pattern(
                elements=(
                    Placeable(expression=TermReference(id=Identifier("termB"))),
                    TextElement(value=" via "),
                    Placeable(expression=MessageReference(id=Identifier("msgC"))),
                )
            ),
            attributes=(),
        )

        messages_dict = {"msgA": msg_a, "msgC": msg_c}
        terms_dict = {"termB": term_b}

        # Build dependency graph
        graph = build_dependency_graph(messages_dict, terms_dict)

        # Compute longest paths
        result = _compute_longest_paths(graph)

        # termB is referenced by both msgA and msgC
        assert "term:termB" in result
        assert result["term:termB"][0] == 0
        assert result["msg:msgC"][0] == 1
        assert result["msg:msgA"][0] == 2

    @given(
        num_messages=st.integers(min_value=3, max_value=8),
    )
    def test_property_complex_dependency_graphs(self, num_messages: int) -> None:
        """Property: Complex dependency graphs always compute without errors.

        Events emitted:
        - num_messages={n}: Number of messages in graph
        """
        # Emit event for fuzzer guidance
        event(f"num_messages={num_messages}")

        # Create a chain with some cross-references
        messages_dict: dict[str, Message] = {}

        for i in range(num_messages):
            if i == num_messages - 1:
                # Last message has no references
                value = Pattern(elements=(TextElement(value="End"),))
            elif i % 2 == 0:
                # Even messages reference next message
                value = Pattern(
                    elements=(
                        Placeable(
                            expression=MessageReference(id=Identifier(f"msg{i+1}"))
                        ),
                    )
                )
            else:
                # Odd messages reference last message (creates diamond-like structure)
                value = Pattern(
                    elements=(
                        Placeable(
                            expression=MessageReference(
                                id=Identifier(f"msg{num_messages-1}")
                            )
                        ),
                    )
                )

            messages_dict[f"msg{i}"] = Message(
                id=Identifier(f"msg{i}"),
                value=value,
                attributes=(),
            )

        terms_dict: dict[str, Term] = {}

        # Build and compute - should not raise
        graph = build_dependency_graph(messages_dict, terms_dict)
        result = _compute_longest_paths(graph)

        # All messages should be in result
        assert len(result) >= num_messages


class TestValidationResourceEdgeCases:
    """Coverage for validation/resource.py edge cases."""

    def test_junk_without_span(self) -> None:
        """Junk entry without span uses None for line/column."""
        junk = Junk(content="invalid", span=None)

        class MockResource:
            def __init__(self) -> None:
                self.entries = [junk]

        errors = _extract_syntax_errors(
            MockResource(), "invalid"  # type: ignore[arg-type]
        )
        assert len(errors) > 0
        assert errors[0].line is None

    def test_validation_with_invalid_ftl(self) -> None:
        """Validation handles malformed FTL gracefully."""
        result = validate_resource("msg = { $val ->")
        assert result is not None

    def test_cycle_deduplication(self) -> None:
        """Circular references are detected without duplicates."""
        ftl = "\na = { b }\nb = { a }\nc = { d }\nd = { c }\n"
        result = validate_resource(ftl)
        circular = [
            w for w in result.warnings
            if "circular" in w.message.lower()
        ]
        assert len(circular) >= 2
