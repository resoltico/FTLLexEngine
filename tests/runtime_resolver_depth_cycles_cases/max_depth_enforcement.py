# mypy: ignore-errors
"""Split test cases from tests/test_runtime_resolver_depth_cycles.py."""

from tests.runtime_resolver_depth_cycles_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# MAX_DEPTH Enforcement
# ============================================================================


class TestMaxDepthLimit:
    """Tests for maximum resolution depth enforcement."""

    def test_max_depth_constant_exists(self) -> None:
        """MAX_DEPTH constant is defined and reasonable."""
        assert MAX_DEPTH == 100

    def test_shallow_chain_succeeds(self) -> None:
        """Chain of 5 messages resolves without error."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
m0 = { m1 }
m1 = { m2 }
m2 = { m3 }
m3 = { m4 }
m4 = Final value
"""
        )

        result, errors = bundle.format_pattern("m0")

        assert errors == ()
        assert "\u2068" in result or "Final value" in result

    def test_moderate_chain_succeeds(self) -> None:
        """Chain of 50 messages resolves without error."""
        bundle = FluentBundle("en")
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
        bundle = FluentBundle("en", strict=False)
        depth = MAX_DEPTH + 10
        lines = []
        for i in range(depth - 1):
            lines.append(f"m{i} = {{ m{i+1} }}")
        lines.append(f"m{depth-1} = Final")
        bundle.add_resource("\n".join(lines))

        _, errors = bundle.format_pattern("m0")

        assert len(errors) > 0
        depth_errors = [e for e in errors if isinstance(e, FrozenFluentError)]
        assert len(depth_errors) > 0

    def test_exactly_at_limit_succeeds(self) -> None:
        """Chain of exactly MAX_DEPTH - 1 nesting levels succeeds."""
        bundle = FluentBundle("en")
        depth = MAX_DEPTH - 1
        lines = []
        for i in range(depth - 1):
            lines.append(f"m{i} = {{ m{i+1} }}")
        lines.append(f"m{depth-1} = End")
        bundle.add_resource("\n".join(lines))

        result, _ = bundle.format_pattern("m0")

        assert "End" in result

    def test_depth_limit_error_message_contains_depth_info(self) -> None:
        """Error message for depth limit references depth."""
        bundle = FluentBundle("en", strict=False)
        depth = MAX_DEPTH + 5
        lines = []
        for i in range(depth - 1):
            lines.append(f"msg{i} = {{ msg{i+1} }}")
        lines.append(f"msg{depth-1} = End")
        bundle.add_resource("\n".join(lines))

        _, errors = bundle.format_pattern("msg0")

        assert len(errors) > 0
        error_str = str(errors[0])
        assert "depth" in error_str.lower() or "Maximum" in error_str

    def test_cyclic_detected_before_depth(self) -> None:
        """Cyclic reference is detected before hitting depth limit."""
        bundle = FluentBundle("en", strict=False)
        bundle.add_resource(
            """
a = { b }
b = { c }
c = { a }
"""
        )

        result, errors = bundle.format_pattern("a")

        assert len(errors) > 0
        assert "{" in result  # Fallback format

    def test_independent_resolutions_dont_share_depth(self) -> None:
        """Separate format_pattern calls have independent depth tracking."""
        bundle = FluentBundle("en")
        bundle.add_resource(
            """
a1 = { a2 }
a2 = { a3 }
a3 = A Done

b1 = { b2 }
b2 = B Done
"""
        )

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
        bundle.add_resource(
            """
m0 = Value
    .attr = { m1.attr }
m1 = Value
    .attr = { m2.attr }
m2 = Value
    .attr = { m3.attr }
m3 = Value
    .attr = Final
"""
        )

        result, errors = bundle.format_pattern("m0", attribute="attr")

        assert errors == ()
        assert "Final" in result
