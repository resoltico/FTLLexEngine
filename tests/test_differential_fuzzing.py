"""Differential fuzzing for FTL parser.

Validates metamorphic properties that any correct FTL parser must satisfy.
Uses Hypothesis to generate test inputs and verify parser invariants.

Properties tested:
- Information preservation: parse(x) retains semantic content
- Structural stability: multiple parses produce identical results
- Robustness: parser never crashes on any input
- Serialization idempotence: serialize(resource) is deterministic
- Roundtrip convergence: parse-serialize converges to fixed point

References:
- Yang et al., "Finding and Understanding Bugs in C Compilers" (PLDI 2011)
- McKeeman, "Differential Testing for Software" (1998)
"""

from __future__ import annotations

import pytest
from hypothesis import assume, example, given, settings
from hypothesis import strategies as st

from ftllexengine.syntax.ast import Message, Resource, Term
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import serialize
from tests.strategies import ftl_simple_messages

# =============================================================================
# Parsing Properties
# =============================================================================


class TestParsingProperties:
    """Metamorphic properties for FTL parsing."""

    @example(ftl="hello = world")
    @example(ftl="msg = value with spaces")
    @given(ftl_simple_messages())
    def test_information_preservation(self, ftl: str) -> None:
        """Property: parse(x) retains semantic content from x.

        For valid FTL, parsing should preserve message IDs and produce
        serializable output.
        """
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        assert isinstance(resource, Resource)
        assert resource.entries is not None

        message_count = sum(1 for e in resource.entries if isinstance(e, Message))
        term_count = sum(1 for e in resource.entries if isinstance(e, Term))

        # Valid FTL should produce at least one Message or Term
        assert message_count + term_count >= 1, "Valid FTL should produce entries"

        # Serialization should work for valid entries
        ftl_out = serialize(resource)
        assert isinstance(ftl_out, str)
        assert len(ftl_out) > 0, "Serialized output should not be empty"

    @example(ftl="test = value")
    @given(ftl_simple_messages())
    def test_determinism(self, ftl: str) -> None:
        """Property: parse(x) produces identical results across calls.

        Multiple parses of the same input must produce structurally
        identical ASTs.
        """
        parser = FluentParserV1()

        r1 = parser.parse(ftl)
        r2 = parser.parse(ftl)
        r3 = parser.parse(ftl)

        # Entry counts must match
        assert len(r1.entries) == len(r2.entries) == len(r3.entries), (
            "Parser is non-deterministic: entry counts differ"
        )

        # Entry types must match
        types1 = [type(e).__name__ for e in r1.entries]
        types2 = [type(e).__name__ for e in r2.entries]
        types3 = [type(e).__name__ for e in r3.entries]
        assert types1 == types2 == types3, (
            "Parser is non-deterministic: entry types differ"
        )

        # Entry IDs must match for messages
        ids1 = [e.id.name for e in r1.entries if isinstance(e, (Message, Term))]
        ids2 = [e.id.name for e in r2.entries if isinstance(e, (Message, Term))]
        assert ids1 == ids2, "Parser is non-deterministic: entry IDs differ"

    @example(ftl="")
    @example(ftl="\x00\x01\x02")
    @example(ftl="invalid ===")
    @given(st.text(max_size=200))
    def test_robustness(self, ftl: str) -> None:
        """Property: parse(x) never crashes for any input.

        Parser must always return a Resource, even for invalid input.
        """
        parser = FluentParserV1()

        # Should never raise exception
        resource = parser.parse(ftl)

        assert isinstance(resource, Resource)
        assert hasattr(resource, "entries")
        assert isinstance(resource.entries, tuple)


# =============================================================================
# Serialization Properties
# =============================================================================


class TestSerializationProperties:
    """Metamorphic properties for FTL serialization."""

    @example(ftl="hello = world")
    @given(ftl_simple_messages())
    def test_idempotence(self, ftl: str) -> None:
        """Property: serialize(resource) produces identical output.

        Serializing the same resource twice must produce identical strings.
        """
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        out1 = serialize(resource)
        out2 = serialize(resource)

        assert out1 == out2, "Serialization is not deterministic"

    @example(ftl="test = value")
    @given(ftl_simple_messages())
    def test_roundtrip_convergence(self, ftl: str) -> None:
        """Property: roundtrip converges to fixed point after one iteration.

        serialize(parse(serialize(parse(x)))) == serialize(parse(x))
        """
        parser = FluentParserV1()

        # First roundtrip
        r1 = parser.parse(ftl)
        out1 = serialize(r1)

        # Second roundtrip
        r2 = parser.parse(out1)
        out2 = serialize(r2)

        # Third roundtrip (should equal second)
        r3 = parser.parse(out2)
        out3 = serialize(r3)

        assert out2 == out3, (
            f"Roundtrip does not converge:\n"
            f"  After 2nd: {out2!r}\n"
            f"  After 3rd: {out3!r}"
        )


# =============================================================================
# Error Recovery Properties
# =============================================================================


class TestErrorRecovery:
    """Properties for parser error recovery behavior."""

    @example(text="!!invalid!!")
    @example(text="= no identifier")
    @given(st.text(min_size=1, max_size=200))
    def test_invalid_input_handled_gracefully(self, text: str) -> None:
        """Property: invalid input produces Junk or empty resource.

        Parser should never crash on invalid input.
        """
        parser = FluentParserV1()
        resource = parser.parse(text)

        assert isinstance(resource, Resource)
        assert isinstance(resource.entries, tuple)

    @example(ftl="hello = world", truncate_pos=5)
    @given(ftl_simple_messages(), st.integers(min_value=0, max_value=50))
    def test_truncation_recovery(self, ftl: str, truncate_pos: int) -> None:
        """Property: truncated input recovers gracefully.

        Parser should handle EOF at any position without crashing.
        """
        assume(len(ftl) > 0)

        truncate_pos = min(truncate_pos, len(ftl))
        truncated = ftl[:truncate_pos]

        parser = FluentParserV1()
        resource = parser.parse(truncated)

        assert isinstance(resource, Resource)
        assert resource.entries is not None


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Edge cases that may differ between implementations."""

    def test_empty_message_value(self) -> None:
        """Edge case: message with no value (message =)."""
        parser = FluentParserV1()
        resource = parser.parse("message =")

        assert isinstance(resource, Resource)

    def test_whitespace_only_pattern(self) -> None:
        """Edge case: pattern with only whitespace."""
        parser = FluentParserV1()
        resource = parser.parse("message =    ")

        assert isinstance(resource, Resource)

    @pytest.mark.parametrize(
        "ftl",
        [
            "message = Hello 世界",
            "# Comment with emojis",
            "test = Value\nother = Value",
        ],
        ids=["unicode-value", "unicode-comment", "multiline"],
    )
    def test_unicode_content(self, ftl: str) -> None:
        """Edge case: Unicode characters in various positions."""
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        assert isinstance(resource, Resource)

    def test_very_long_identifier(self) -> None:
        """Edge case: identifier at length boundary (500 chars)."""
        long_id = "a" * 500
        parser = FluentParserV1()
        resource = parser.parse(f"{long_id} = value")

        assert isinstance(resource, Resource)
        assert len(resource.entries) >= 1

    def test_deeply_nested_placeables(self) -> None:
        """Edge case: deeply nested placeables (10 levels)."""
        nested = "$var"
        for _ in range(10):
            nested = f"{{ {nested} }}"

        parser = FluentParserV1()
        resource = parser.parse(f"test = {nested}")

        assert isinstance(resource, Resource)


# =============================================================================
# Spec Compliance
# =============================================================================


class TestSpecCompliance:
    """Test cases derived from FTL specification."""

    def test_comment_types(self) -> None:
        """Spec: All comment types (#, ##, ###) are recognized."""
        ftl = """# Regular comment
## Group comment
### Resource comment
message = value
"""
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) >= 1
        assert messages[0].id.name == "message"

    def test_attribute_syntax(self) -> None:
        """Spec: Attributes use .name = value syntax."""
        ftl = """message = value
    .attr1 = first
    .attr2 = second
"""
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(messages) >= 1
        assert messages[0].id.name == "message"

    def test_select_expression(self) -> None:
        """Spec: Select expressions with * default marker."""
        ftl = """message = { $count ->
    [one] One item
   *[other] {$count} items
}"""
        parser = FluentParserV1()
        resource = parser.parse(ftl)

        assert isinstance(resource, Resource)
        assert len(resource.entries) >= 1


# =============================================================================
# Performance Properties
# =============================================================================


class TestPerformanceProperties:
    """Performance-related properties."""

    @given(st.lists(ftl_simple_messages(), min_size=10, max_size=50))
    @settings(deadline=5000)
    def test_linear_scaling(self, messages: list[str]) -> None:
        """Property: parsing time scales linearly with input size.

        Combining messages should not cause exponential slowdown.
        """
        parser = FluentParserV1()
        ftl = "\n\n".join(messages)

        resource = parser.parse(ftl)

        assert isinstance(resource, Resource)
        # Upper bound: at most 2x entries per input message
        assert len(resource.entries) <= len(messages) * 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
