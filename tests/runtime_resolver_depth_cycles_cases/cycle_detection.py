# mypy: ignore-errors
"""Split test cases from tests/test_runtime_resolver_depth_cycles.py."""

from tests.runtime_resolver_depth_cycles_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# Cycle Detection
# ============================================================================


class TestDirectCycles:
    """Tests for direct self-referential cycles."""

    def test_message_references_itself(self) -> None:
        """Direct cycle: message references itself."""
        bundle = FluentBundle("en-US", strict=False)
        bundle.add_resource("self = { self }")

        result, errors = bundle.format_pattern("self")

        assert isinstance(result, str)
        assert len(errors) > 0
        cyclic_errors = [
            e for e in errors
            if isinstance(e, FrozenFluentError) and e.category == ErrorCategory.CYCLIC
        ]
        assert len(cyclic_errors) > 0

    def test_term_references_itself(self) -> None:
        """Direct cycle: term references itself."""
        bundle = FluentBundle("en-US", strict=False)
        bundle.add_resource(
            """
-self = { -self }
msg = { -self }
"""
        )

        result, errors = bundle.format_pattern("msg")

        assert isinstance(result, str)
        assert len(errors) > 0


class TestIndirectCycles:
    """Tests for indirect cycles through chains."""

    def test_two_message_cycle(self) -> None:
        """Indirect cycle: a -> b -> a."""
        bundle = FluentBundle("en-US", strict=False)
        bundle.add_resource(
            """
msg-a = { msg-b }
msg-b = { msg-a }
"""
        )

        result, errors = bundle.format_pattern("msg-a")

        assert isinstance(result, str)
        assert len(errors) > 0
        cyclic_errors = [
            e for e in errors
            if isinstance(e, FrozenFluentError) and e.category == ErrorCategory.CYCLIC
        ]
        assert len(cyclic_errors) > 0

    def test_three_message_cycle(self) -> None:
        """Indirect cycle: a -> b -> c -> a."""
        bundle = FluentBundle("en-US", strict=False)
        bundle.add_resource(
            """
msg-a = { msg-b }
msg-b = { msg-c }
msg-c = { msg-a }
"""
        )

        result, errors = bundle.format_pattern("msg-a")

        assert isinstance(result, str)
        assert len(errors) > 0

    def test_term_to_message_cycle(self) -> None:
        """Mixed cycle: term -> message -> term."""
        bundle = FluentBundle("en-US", strict=False)
        bundle.add_resource(
            """
-brand = { product }
product = { -brand } Browser
"""
        )

        result, _ = bundle.format_pattern("product")

        assert isinstance(result, str)


class TestDeepChains:
    """Tests for deep non-cyclic chains."""

    def test_chain_at_depth_limit(self) -> None:
        """Chain shorter than MAX_DEPTH resolves to leaf value."""
        depth = min(MAX_DEPTH - 1, 50)
        messages = []
        for i in range(depth):
            if i < depth - 1:
                messages.append(f"msg{i} = {{ msg{i + 1} }}")
            else:
                messages.append(f"msg{i} = End")

        bundle = FluentBundle("en-US")
        bundle.add_resource("\n".join(messages))

        result, _ = bundle.format_pattern("msg0")

        assert isinstance(result, str)
        assert "End" in result

    def test_chain_exceeding_depth_limit(self) -> None:
        """Chain exceeding MAX_DEPTH produces error."""
        depth = MAX_DEPTH + 10
        messages = []
        for i in range(depth):
            if i < depth - 1:
                messages.append(f"msg{i} = {{ msg{i + 1} }}")
            else:
                messages.append(f"msg{i} = End")

        bundle = FluentBundle("en-US", strict=False)
        bundle.add_resource("\n".join(messages))

        result, errors = bundle.format_pattern("msg0")

        assert isinstance(result, str)
        assert len(errors) > 0
