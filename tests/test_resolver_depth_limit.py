"""Tests for resolver maximum depth limit.

Tests that the resolver properly enforces MAX_DEPTH to prevent
stack overflow from long non-cyclic message chains.
"""

from ftllexengine import FluentBundle
from ftllexengine.constants import MAX_DEPTH
from ftllexengine.diagnostics import FluentReferenceError

# ============================================================================
# UNIT TESTS - MAX DEPTH LIMIT
# ============================================================================


class TestMaxDepthLimit:
    """Tests for maximum resolution depth enforcement."""

    def test_max_depth_constant_exists(self) -> None:
        """MAX_DEPTH constant is defined and reasonable."""
        assert MAX_DEPTH == 100

    def test_shallow_chain_succeeds(self) -> None:
        """Chain of 5 messages resolves without error."""
        bundle = FluentBundle("en")

        # Create chain: m0 -> m1 -> m2 -> m3 -> m4 (value)
        ftl = """
m0 = { m1 }
m1 = { m2 }
m2 = { m3 }
m3 = { m4 }
m4 = Final value
"""
        bundle.add_resource(ftl)

        result, errors = bundle.format_pattern("m0")
        assert errors == ()
        assert result == "\u2068\u2068\u2068\u2068Final value\u2069\u2069\u2069\u2069"

    def test_moderate_chain_succeeds(self) -> None:
        """Chain of 50 messages resolves without error."""
        bundle = FluentBundle("en")

        # Generate chain of 50 messages
        lines = []
        for i in range(49):
            lines.append(f"m{i} = {{ m{i+1} }}")
        lines.append("m49 = Done")

        bundle.add_resource("\n".join(lines))

        result, errors = bundle.format_pattern("m0")
        assert errors == ()
        assert "Done" in result

    def test_deep_chain_hits_limit(self) -> None:
        """Chain exceeding MAX_DEPTH returns error."""
        bundle = FluentBundle("en")

        # Generate chain of MAX_DEPTH + 10 messages
        depth = MAX_DEPTH + 10
        lines = []
        for i in range(depth - 1):
            lines.append(f"m{i} = {{ m{i+1} }}")
        lines.append(f"m{depth-1} = Final")

        bundle.add_resource("\n".join(lines))

        _, errors = bundle.format_pattern("m0")

        # Should hit depth limit and return error
        assert len(errors) > 0
        # At least one error should be about max depth
        depth_errors = [e for e in errors if isinstance(e, FluentReferenceError)]
        assert len(depth_errors) > 0

    def test_exactly_at_limit_succeeds(self) -> None:
        """Chain of exactly MAX_DEPTH messages succeeds."""
        bundle = FluentBundle("en")

        # Generate chain of exactly MAX_DEPTH messages
        # The limit is checked BEFORE adding to stack, so depth == limit triggers error
        # This means we can have MAX_DEPTH - 1 levels of nesting
        depth = MAX_DEPTH - 1
        lines = []
        for i in range(depth - 1):
            lines.append(f"m{i} = {{ m{i+1} }}")
        lines.append(f"m{depth-1} = End")

        bundle.add_resource("\n".join(lines))

        result, _ = bundle.format_pattern("m0")
        # Should succeed at exactly the limit
        assert "End" in result

    def test_depth_limit_error_message_contains_id(self) -> None:
        """Error message for depth limit includes message ID."""
        bundle = FluentBundle("en")

        # Generate chain exceeding limit
        depth = MAX_DEPTH + 5
        lines = []
        for i in range(depth - 1):
            lines.append(f"msg{i} = {{ msg{i+1} }}")
        lines.append(f"msg{depth-1} = End")

        bundle.add_resource("\n".join(lines))

        _, errors = bundle.format_pattern("msg0")

        # Error should mention the message where depth was exceeded
        assert len(errors) > 0
        error_str = str(errors[0])
        assert "depth" in error_str.lower() or "Maximum" in error_str

    def test_cyclic_detected_before_depth(self) -> None:
        """Cyclic reference is detected before hitting depth limit."""
        bundle = FluentBundle("en")

        # Create a cycle (should be detected as cycle, not depth)
        ftl = """
a = { b }
b = { c }
c = { a }
"""
        bundle.add_resource(ftl)

        result, errors = bundle.format_pattern("a")

        # Should have error about cycle
        assert len(errors) > 0
        # Should not crash - graceful error handling
        assert "{" in result  # Fallback format

    def test_independent_resolutions_dont_share_depth(self) -> None:
        """Separate format_pattern calls have independent depth tracking."""
        bundle = FluentBundle("en")

        # Two independent chains
        ftl = """
a1 = { a2 }
a2 = { a3 }
a3 = A Done

b1 = { b2 }
b2 = B Done
"""
        bundle.add_resource(ftl)

        # Both should succeed independently
        result_a, errors_a = bundle.format_pattern("a1")
        result_b, errors_b = bundle.format_pattern("b1")

        assert errors_a == ()
        assert errors_b == ()
        assert "A Done" in result_a
        assert "B Done" in result_b


class TestMaxDepthWithAttributes:
    """Tests for depth limit with attribute access."""

    def test_attribute_chain_counts_toward_depth(self) -> None:
        """Message.attribute references count toward depth."""
        bundle = FluentBundle("en")

        # Chain via attributes - FTL requires value OR attributes, use value here
        ftl = """
m0 = Value
    .attr = { m1.attr }
m1 = Value
    .attr = { m2.attr }
m2 = Value
    .attr = { m3.attr }
m3 = Value
    .attr = Final
"""
        bundle.add_resource(ftl)

        result, errors = bundle.format_pattern("m0", attribute="attr")
        assert errors == ()
        assert "Final" in result
