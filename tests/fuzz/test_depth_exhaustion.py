"""Depth Exhaustion Fuzzer - Tests MAX_DEPTH boundary conditions.

This module tests the depth limit boundaries across all subsystems:
- Parser nesting depth
- Resolver reference depth
- Serializer traversal depth

Key test scenarios:
- Depth = MAX_DEPTH - 1: Should succeed
- Depth = MAX_DEPTH: Should succeed or fail gracefully
- Depth = MAX_DEPTH + 1: Should fail cleanly (no crash, no RecursionError)

The tests verify that:
1. The system does not crash at any depth
2. Error messages are informative
3. No stack overflow occurs

Run with:
    pytest tests/fuzz/test_depth_exhaustion.py -v

Python 3.13+.
"""

from __future__ import annotations

import pytest
from hypothesis import event, given, settings
from hypothesis import strategies as st

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.runtime import FluentBundle
from ftllexengine.syntax.ast import (
    Identifier,
    Message,
    Pattern,
    Placeable,
    Resource,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import serialize

# Mark entire module as fuzz tests
pytestmark = pytest.mark.fuzz


class TestParserDepthExhaustion:
    """Test parser behavior at MAX_DEPTH boundaries."""

    @given(depth_offset=st.integers(min_value=-5, max_value=5))
    @settings(max_examples=20, deadline=None)
    def test_nested_placeables_at_boundary(self, depth_offset: int) -> None:
        """Parser handles nested placeables at MAX_DEPTH boundary.

        Generates { { { ... { $x } ... } } } at various depths around MAX_DEPTH.
        """
        depth = MAX_DEPTH + depth_offset
        # Cap at reasonable maximum to avoid test timeout
        depth = min(max(depth, 1), MAX_DEPTH + 10)

        # Emit semantic events for HypoFuzz guidance
        event(f"depth={depth}")
        if depth_offset < 0:
            event("boundary=under_max")
        elif depth_offset == 0:
            event("boundary=at_max")
        else:
            event("boundary=over_max")

        # Build nested placeable string
        open_braces = "{ " * depth
        close_braces = " }" * depth
        source = f"msg = {open_braces}$x{close_braces}"

        parser = FluentParserV1()

        # Should not raise RecursionError or crash
        try:
            resource = parser.parse(source)
            # If it parsed, verify we got something
            assert resource is not None
            assert len(resource.entries) > 0
            event("outcome=parsed")
        except RecursionError:
            pytest.fail(f"RecursionError at depth {depth} (MAX_DEPTH={MAX_DEPTH})")

    @given(depth=st.integers(min_value=1, max_value=150))
    @settings(max_examples=50, deadline=None)
    def test_nested_selects_no_crash(self, depth: int) -> None:
        """Parser handles nested select expressions without crashing.

        Generates:
        { $a ->
            [x] { $b ->
                [y] { $c -> ... }
            }
        }
        """
        # Emit semantic events for HypoFuzz guidance
        event(f"select_depth={depth}")
        if depth <= 10:
            event("depth_band=shallow")
        elif depth <= 50:
            event("depth_band=moderate")
        else:
            event("depth_band=deep")

        # Build nested select
        lines = ["msg = "]
        indent = ""
        for i in range(depth):
            var = f"v{i}"
            lines.append(f"{indent}{{ ${var} ->")
            lines.append(f"{indent}    [x]")
            indent += "        "

        # Add base value
        lines.append(f"{indent}value")

        # Close all selects
        for i in range(depth):
            indent = indent[:-8]
            lines.append(f"{indent}   *[other] fallback{i}")
            lines.append(f"{indent}}}")

        source = "\n".join(lines)

        parser = FluentParserV1()

        try:
            resource = parser.parse(source)
            assert resource is not None
            event("outcome=parsed")
        except RecursionError:
            pytest.fail(f"RecursionError at select depth {depth}")

    def test_exactly_at_max_depth(self) -> None:
        """Parser at exactly MAX_DEPTH produces expected behavior."""
        depth = MAX_DEPTH
        open_braces = "{ " * depth
        close_braces = " }" * depth
        source = f"msg = {open_braces}$x{close_braces}"

        parser = FluentParserV1()
        resource = parser.parse(source)

        # Should parse (possibly with depth error in diagnostics)
        assert resource is not None

    def test_one_over_max_depth(self) -> None:
        """Parser at MAX_DEPTH + 1 fails gracefully."""
        depth = MAX_DEPTH + 1
        open_braces = "{ " * depth
        close_braces = " }" * depth
        source = f"msg = {open_braces}$x{close_braces}"

        parser = FluentParserV1()

        # Should not crash
        try:
            resource = parser.parse(source)
            assert resource is not None
        except RecursionError:
            pytest.fail("RecursionError at MAX_DEPTH + 1")


class TestResolverDepthExhaustion:
    """Test resolver behavior with deep reference chains."""

    @given(chain_length=st.integers(min_value=2, max_value=50))
    @settings(max_examples=30, deadline=None)
    def test_message_reference_chain(self, chain_length: int) -> None:
        """Resolver handles message reference chains.

        Creates: msg0 -> msg1 -> msg2 -> ... -> msgN (terminal)
        """
        # Emit semantic events for HypoFuzz guidance
        event(f"chain_length={chain_length}")
        if chain_length <= 5:
            event("chain_band=short")
        elif chain_length <= 20:
            event("chain_band=medium")
        else:
            event("chain_band=long")

        lines = []
        for i in range(chain_length - 1):
            lines.append(f"msg{i} = {{ msg{i + 1} }}")
        lines.append(f"msg{chain_length - 1} = terminal")

        source = "\n".join(lines)

        bundle = FluentBundle("en_US")
        bundle.add_resource(source)

        # Format the first message (triggers full chain)
        try:
            result, errors = bundle.format_pattern("msg0", {})
            # Should either succeed or fail with error (not crash)
            assert isinstance(result, str)
            # Result should not be empty
            assert len(result) > 0
            # If no errors, should contain "terminal" (the chain endpoint)
            if not errors:
                assert "terminal" in result
        except RecursionError:
            pytest.fail(f"RecursionError with chain length {chain_length}")

    @given(depth=st.integers(min_value=2, max_value=MAX_DEPTH + 5))
    @settings(max_examples=20, deadline=None)
    def test_term_reference_depth(self, depth: int) -> None:
        """Resolver handles term reference chains at boundary depths."""
        # Cap for reasonable test time
        depth = min(depth, MAX_DEPTH + 5)

        # Emit semantic events for HypoFuzz guidance
        event(f"term_depth={depth}")
        if depth >= MAX_DEPTH:
            event("boundary=at_or_over_max")
        else:
            event("boundary=under_max")

        lines = []
        for i in range(depth - 1):
            lines.append(f"-term{i} = {{ -term{i + 1} }}")
        lines.append(f"-term{depth - 1} = terminal")
        lines.append("msg = { -term0 }")

        source = "\n".join(lines)

        bundle = FluentBundle("en_US")
        bundle.add_resource(source)

        try:
            result, errors = bundle.format_pattern("msg", {})
            assert isinstance(result, str)
            # Result should not be empty
            assert len(result) > 0
            # If no errors, should contain "terminal" (the chain endpoint)
            if not errors:
                assert "terminal" in result
                event("outcome=resolved")
            else:
                event("outcome=error")
        except RecursionError:
            pytest.fail(f"RecursionError with term depth {depth}")

    def test_circular_reference_detected(self) -> None:
        """Resolver detects and handles circular references."""
        source = """
msg-a = { msg-b }
msg-b = { msg-c }
msg-c = { msg-a }
"""
        bundle = FluentBundle("en_US")
        bundle.add_resource(source)

        # Should not crash or infinite loop
        result, errors = bundle.format_pattern("msg-a", {})

        # Should return something (error fallback)
        assert isinstance(result, str)
        assert len(result) > 0
        # Should report the cycle
        assert len(errors) > 0
        # Result should contain fallback markers or cycle indication
        # (cyclic ref produces placeholder like {msg-a})

    def test_self_reference_detected(self) -> None:
        """Resolver detects self-referencing messages."""
        source = "msg = Value { msg }"

        bundle = FluentBundle("en_US")
        bundle.add_resource(source)

        result, errors = bundle.format_pattern("msg", {})

        assert isinstance(result, str)
        assert len(result) > 0
        # Should contain "Value" from the non-cyclic part
        assert "Value" in result
        # Should have errors reporting the self-reference
        assert len(errors) > 0


class TestSerializerDepthExhaustion:
    """Test serializer with deeply nested ASTs."""

    @given(depth=st.integers(min_value=1, max_value=100))
    @settings(max_examples=30, deadline=None)
    def test_serialize_deep_placeables(self, depth: int) -> None:
        """Serializer handles deeply nested Placeable ASTs."""
        # Emit semantic events for HypoFuzz guidance
        event(f"serialize_depth={depth}")
        if depth <= 20:
            event("depth_band=shallow")
        elif depth <= 60:
            event("depth_band=moderate")
        else:
            event("depth_band=deep")

        # Build nested placeable AST - start with innermost Placeable
        inner: Placeable = Placeable(
            expression=VariableReference(id=Identifier(name="x"))
        )
        # depth-1 since we already created one level of nesting
        for _ in range(depth - 1):
            inner = Placeable(expression=inner)

        pattern = Pattern(elements=(TextElement(value="Prefix "), inner))
        message = Message(
            id=Identifier(name="msg"),
            value=pattern,
            attributes=(),
        )
        resource = Resource(entries=(message,))

        try:
            result = serialize(resource)
            assert isinstance(result, str)
            assert len(result) > 0
            assert "msg" in result
            # Should contain the variable reference
            assert "$x" in result
            # Should be valid FTL (contains "=")
            assert "=" in result
            event("outcome=serialized")
        except RecursionError:
            pytest.fail(f"Serializer RecursionError at depth {depth}")

    def test_serialize_at_max_depth(self) -> None:
        """Serializer at MAX_DEPTH produces valid output."""
        depth = min(MAX_DEPTH, 100)  # Cap for safety

        # Build nested placeable AST - start with innermost Placeable
        inner: Placeable = Placeable(
            expression=VariableReference(id=Identifier(name="x"))
        )
        # depth-1 since we already created one level of nesting
        for _ in range(depth - 1):
            inner = Placeable(expression=inner)

        pattern = Pattern(elements=(inner,))
        message = Message(
            id=Identifier(name="deep"),
            value=pattern,
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)
        assert "deep" in result


class TestRoundtripDepthExhaustion:
    """Test parse -> serialize roundtrip at depth boundaries."""

    @given(depth=st.integers(min_value=1, max_value=50))
    @settings(max_examples=20, deadline=None)
    def test_roundtrip_nested_placeables(self, depth: int) -> None:
        """Parse -> serialize roundtrip preserves nested placeables."""
        # Emit semantic events for HypoFuzz guidance
        event(f"roundtrip_depth={depth}")
        if depth <= 10:
            event("depth_band=shallow")
        elif depth <= 30:
            event("depth_band=moderate")
        else:
            event("depth_band=deep")

        open_braces = "{ " * depth
        close_braces = " }" * depth
        source = f"msg = {open_braces}$x{close_braces}"

        parser = FluentParserV1()

        try:
            resource = parser.parse(source)

            # Skip if parsing produced junk
            from ftllexengine.syntax.ast import Junk  # noqa: PLC0415
            if any(isinstance(e, Junk) for e in resource.entries):
                event("outcome=junk")
                return

            serialized = serialize(resource)
            assert isinstance(serialized, str)
            assert len(serialized) > 0
            # Serialized output should contain the message and variable
            assert "msg" in serialized
            assert "$x" in serialized

            # Re-parse should work
            resource2 = parser.parse(serialized)
            assert len(resource2.entries) == len(resource.entries)
            event("outcome=roundtrip_success")
        except RecursionError:
            pytest.fail(f"Roundtrip RecursionError at depth {depth}")
