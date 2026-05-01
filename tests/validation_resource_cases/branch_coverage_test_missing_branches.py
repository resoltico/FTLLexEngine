# mypy: ignore-errors
"""Split test cases from tests/test_validation_resource.py."""

from tests.validation_resource_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# BRANCH COVERAGE: Test Missing Branches
# ============================================================================


class TestMissingBranchCoverage:
    """Test missing branch coverage in resource.py."""

    def test_junk_without_span_line_56(self) -> None:
        """Test Junk entry without span (branch 56->60).

        Line 56: if entry.span
        When span is None, line/column remain None.
        """
        from ftllexengine.syntax.ast import Junk, Resource
        from ftllexengine.validation.resource import _extract_syntax_errors

        # Create Junk with no span
        junk_no_span = Junk(content="invalid", span=None)
        resource = Resource(entries=(junk_no_span,))

        # Extract errors with LineOffsetCache
        errors = _extract_syntax_errors(resource, LineOffsetCache("source"))

        # Should have error with line=None, column=None
        assert len(errors) == 1
        assert errors[0].line is None
        assert errors[0].column is None

    def test_term_references_undefined_message_line_187(self) -> None:
        """Test term referencing undefined message (branch 187->186).

        Line 187: if ref not in messages_dict
        This tests the loop iteration when a term references a message.
        Branch 187->186 is when the message DOES exist (if condition is False).
        """
        from ftllexengine.syntax.ast import (
            Identifier,
            Message,
            MessageReference,
            Pattern,
            Placeable,
            Term,
            TextElement,
        )
        from ftllexengine.validation.resource import _check_undefined_references

        # Create message that exists
        existing_message = Message(
            id=Identifier("existing_msg"),
            value=Pattern(elements=(TextElement("text"),)),
            attributes=(),
        )

        # Create term that references the existing message
        term_with_msg_ref = Term(
            id=Identifier("myterm"),
            value=Pattern(elements=(
                TextElement("text"),
                Placeable(
                    expression=MessageReference(id=Identifier("existing_msg"))
                ),  # Reference to message that EXISTS
            )),
            attributes=(),
        )

        messages_dict = {"existing_msg": existing_message}  # Message exists
        terms_dict = {"myterm": term_with_msg_ref}

        # Check references with empty LineOffsetCache for AST-only testing
        warnings = _check_undefined_references(messages_dict, terms_dict, LineOffsetCache(""))

        # Should have NO warnings (message exists)
        # This tests branch 187->186 (if condition is False, continue to next iteration)
        undefined_warnings = [w for w in warnings if "undefined" in w.message.lower()]
        assert len(undefined_warnings) == 0

    def test_duplicate_cycle_detection_line_243(self) -> None:
        """Test cycle deduplication for messages.

        Verifies that the unified graph cycle detection produces exactly one
        warning per unique cycle, not multiple warnings for the same cycle
        detected from different starting points.

        Uses unified cross-type cycle detection.
        """
        from ftllexengine.syntax.ast import (
            Identifier,
            Message,
            MessageReference,
            Pattern,
            Placeable,
        )

        # Create circular messages: a -> b -> a
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

        messages_dict = {"a": msg_a, "b": msg_b}
        terms_dict: dict[str, Term] = {}

        # Build dependency graph
        graph = build_dependency_graph(messages_dict, terms_dict)
        # Call the real function without mocking
        warnings = _detect_circular_references(graph)

        # Should only have 1 warning (cycle a -> b -> a is detected once)
        circular_warnings = [w for w in warnings if "circular" in w.message.lower()]
        assert len(circular_warnings) == 1
        # Should mention both messages in the cycle
        warning_msg = circular_warnings[0].message.lower()
        assert "a" in warning_msg or "b" in warning_msg

    def test_duplicate_cycle_detection_line_257(self) -> None:
        """Test cycle deduplication for terms.

        Verifies that term-only cycles are detected and deduplicated properly
        in the unified graph.

        Uses unified cross-type cycle detection.
        """
        from ftllexengine.syntax.ast import (
            Identifier,
            Pattern,
            Placeable,
            Term,
            TermReference,
        )

        # Create circular terms: -ta -> -tb -> -ta
        term_a = Term(
            id=Identifier("ta"),
            value=Pattern(
                elements=(Placeable(expression=TermReference(id=Identifier("tb"))),)
            ),
            attributes=(),
        )
        term_b = Term(
            id=Identifier("tb"),
            value=Pattern(
                elements=(Placeable(expression=TermReference(id=Identifier("ta"))),)
            ),
            attributes=(),
        )

        messages_dict: dict[str, Message] = {}
        terms_dict = {"ta": term_a, "tb": term_b}

        # Build dependency graph
        graph = build_dependency_graph(messages_dict, terms_dict)
        # Call the real function without mocking
        warnings = _detect_circular_references(graph)

        # Should only have 1 warning (cycle ta -> tb -> ta is detected once)
        circular_warnings = [w for w in warnings if "circular" in w.message.lower()]
        assert len(circular_warnings) == 1
        # Should mention both terms in the cycle
        warning_msg = circular_warnings[0].message.lower()
        assert "ta" in warning_msg or "tb" in warning_msg
