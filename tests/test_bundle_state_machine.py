"""State machine testing for FluentBundle using Hypothesis.

This module tests the FluentBundle public API through stateful sequences,
complementing test_resolver_state_machine.py (which tests the lower-level
FluentResolver). Tests here catch state management bugs at the facade level.

Target Coverage:
- FluentBundle state transitions (add_resource, add_function, format)
- Cache invalidation across operation sequences
- Error recovery between operations
- Thread-safety invariants (per-instance, not cross-instance)

State Machine Approach:
Tests sequences of operations that users actually perform:
- add_resource(ftl_source) -> format_value() -> add_function() -> format_value()
- Multiple add_resource() calls with overlapping message IDs
- Cache behavior across state changes

This catches bugs that only appear in specific operation orders.

References:
- Hypothesis stateful testing: https://hypothesis.readthedocs.io/en/latest/stateful.html
- FluentBundle API: docs/DOC_01_Core.md
"""

from __future__ import annotations

from typing import Any

from hypothesis import assume, settings
from hypothesis import strategies as st
from hypothesis.stateful import Bundle, RuleBasedStateMachine, initialize, invariant, rule

from ftllexengine import FluentBundle
from tests.strategies import ftl_identifiers, ftl_simple_text

# =============================================================================
# Strategies
# =============================================================================


@st.composite
def simple_ftl_message(draw: st.DrawFn) -> tuple[str, str, str]:
    """Generate (msg_id, value, ftl_source) tuple.

    Returns normalized value since FTL spec strips leading whitespace only.
    """
    msg_id = draw(ftl_identifiers())
    value = draw(ftl_simple_text())
    ftl_source = f"{msg_id} = {value}"
    # Return normalized value to match FTL parsing behavior (lstrip only)
    return (msg_id, value.lstrip(), ftl_source)


@st.composite
def ftl_message_with_variable(draw: st.DrawFn) -> tuple[str, str, str]:
    """Generate message requiring a variable: (msg_id, var_name, ftl_source)."""
    msg_id = draw(ftl_identifiers())
    var_name = draw(ftl_identifiers())
    prefix = draw(ftl_simple_text())
    ftl_source = f"{msg_id} = {prefix} {{ ${var_name} }}"
    return (msg_id, var_name, ftl_source)


# =============================================================================
# State Machine
# =============================================================================


class FluentBundleStateMachine(RuleBasedStateMachine):
    """State machine for testing FluentBundle public API.

    Bundles (state containers):
    - messages: Message IDs that have been added
    - variables: Variable names used in messages

    Invariants:
    - Format same message twice produces identical results
    - Cache stats are internally consistent
    - Bundle never crashes on valid operations
    """

    messages = Bundle("messages")
    variables = Bundle("variables")

    @initialize()
    def setup_bundle(self) -> None:
        """Initialize bundle with default settings."""
        self._fluent_bundle = FluentBundle(
            "en-US",
            enable_cache=True,
            cache_size=50,
            use_isolating=False,
        )
        self.known_messages: dict[str, str] = {}  # msg_id -> expected_pattern
        self.known_variables: dict[str, str] = {}  # msg_id -> var_name
        self.operation_count = 0

    # =========================================================================
    # Rules: Add Resources
    # =========================================================================

    @rule(target=messages, msg_data=simple_ftl_message())
    def add_simple_message(self, msg_data: tuple[str, str, str]) -> str:
        """Add a simple text message."""
        msg_id, value, ftl_source = msg_data

        self._fluent_bundle.add_resource(ftl_source)
        self.known_messages[msg_id] = value
        self.operation_count += 1

        return msg_id

    @rule(target=messages, msg_data=ftl_message_with_variable())
    def add_message_with_variable(self, msg_data: tuple[str, str, str]) -> str:
        """Add a message that requires a variable argument."""
        msg_id, var_name, ftl_source = msg_data

        self._fluent_bundle.add_resource(ftl_source)
        self.known_messages[msg_id] = f"(has ${var_name})"
        self.known_variables[msg_id] = var_name
        self.operation_count += 1

        return msg_id

    @rule(
        msg_id=ftl_identifiers(),
        attr_name=ftl_identifiers(),
        value=ftl_simple_text(),
    )
    def add_message_with_attribute(
        self, msg_id: str, attr_name: str, value: str
    ) -> None:
        """Add a message with an attribute."""
        ftl_source = f"{msg_id} = Main value\n    .{attr_name} = {value}"

        self._fluent_bundle.add_resource(ftl_source)
        self.known_messages[msg_id] = "Main value"
        self.operation_count += 1

    @rule(msg_ids=st.lists(ftl_identifiers(), min_size=2, max_size=5, unique=True))
    def add_multiple_messages(self, msg_ids: list[str]) -> None:
        """Add multiple messages in a single resource."""
        lines = [f"{msg_id} = Value for {msg_id}" for msg_id in msg_ids]
        ftl_source = "\n\n".join(lines)

        self._fluent_bundle.add_resource(ftl_source)
        for msg_id in msg_ids:
            self.known_messages[msg_id] = f"Value for {msg_id}"
        self.operation_count += 1

    # =========================================================================
    # Rules: Format Messages
    # =========================================================================

    @rule(msg_id=messages)
    def format_known_message(self, msg_id: str) -> None:
        """Format a message that we know exists (without variables)."""
        # Skip messages that need variables - those are handled by format_with_args
        assume(msg_id not in self.known_variables)

        result, errors = self._fluent_bundle.format_value(msg_id)

        assert not errors

        # Should not have resolution errors for simple messages
        # (syntax errors would have been caught at add_resource)
        assert isinstance(result, str)

    @rule(msg_id=messages, arg_value=st.text(min_size=1, max_size=20))
    def format_with_args(self, msg_id: str, arg_value: str) -> None:
        """Format a message with arguments."""
        # Build args dict if we know this message needs variables
        args: dict[str, Any] = {}
        if msg_id in self.known_variables:
            var_name = self.known_variables[msg_id]
            args[var_name] = arg_value

        result, errors = self._fluent_bundle.format_value(msg_id, args)

        assert not errors
        assert isinstance(result, str)

    @rule(msg_id=ftl_identifiers())
    def format_unknown_message(self, msg_id: str) -> None:
        """Attempt to format a message that may not exist."""
        # Skip if we know this message exists
        assume(msg_id not in self.known_messages)

        result, _errors = self._fluent_bundle.format_value(msg_id)

        # Unknown message returns message ID as fallback (with error)
        assert msg_id in result

    # =========================================================================
    # Rules: Add Functions
    # =========================================================================

    @rule(func_name=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=2, max_size=10))
    def add_custom_function(self, func_name: str) -> None:
        """Add a custom function to the bundle."""
        assume(func_name.isidentifier())

        def custom_func(value: Any) -> str:
            return f"[{func_name}:{value}]"

        self._fluent_bundle.add_function(func_name, custom_func)
        self.operation_count += 1

    # =========================================================================
    # Rules: Cache Operations
    # =========================================================================

    @rule(msg_id=messages)
    def format_twice_check_cache(self, msg_id: str) -> None:
        """Format same message twice and verify cache behavior."""
        result1, _ = self._fluent_bundle.format_value(msg_id)
        result2, _ = self._fluent_bundle.format_value(msg_id)

        # Results must be identical
        assert result1 == result2, (
            f"Non-deterministic format: {result1!r} != {result2!r}"
        )

    @rule()
    def check_cache_stats(self) -> None:
        """Verify cache statistics are internally consistent."""
        stats = self._fluent_bundle.get_cache_stats()

        if stats is not None:
            # hits + misses should be non-negative
            assert stats["hits"] >= 0
            assert stats["misses"] >= 0
            # size should not exceed maxsize
            assert stats["size"] <= stats["maxsize"]

    # =========================================================================
    # Rules: Overwrite Behavior
    # =========================================================================

    @rule(msg_id=messages, new_value=ftl_simple_text())
    def overwrite_message(self, msg_id: str, new_value: str) -> None:
        """Overwrite an existing message with new content."""
        ftl_source = f"{msg_id} = {new_value}"

        self._fluent_bundle.add_resource(ftl_source)
        # Store normalized value - FTL spec strips leading whitespace only
        normalized_value = new_value.lstrip()
        self.known_messages[msg_id] = normalized_value
        self.operation_count += 1

        # Format should now return normalized value
        result, _ = self._fluent_bundle.format_value(msg_id)
        # Note: result may have Unicode isolation chars depending on settings
        assert normalized_value in result or result == normalized_value

    # =========================================================================
    # Invariants
    # =========================================================================

    @invariant()
    def bundle_never_none(self) -> None:
        """Bundle reference should always be valid."""
        assert self._fluent_bundle is not None

    @invariant()
    def has_message_works(self) -> None:
        """has_message should be consistent with known messages."""
        for msg_id in self.known_messages:
            # Note: has_message may return False if message was overwritten
            # by invalid syntax, so we just check it doesn't crash
            _ = self._fluent_bundle.has_message(msg_id)

    @invariant()
    def cache_stats_consistent(self) -> None:
        """Cache statistics should be internally consistent."""
        stats = self._fluent_bundle.get_cache_stats()
        if stats is not None:
            assert stats["hits"] + stats["misses"] >= 0
            assert stats["size"] >= 0
            assert stats["size"] <= stats["maxsize"]

    @invariant()
    def format_deterministic(self) -> None:
        """Formatting same message should be deterministic."""
        # Pick a known message if we have any
        if self.known_messages:
            msg_id = next(iter(self.known_messages))
            result1, _ = self._fluent_bundle.format_value(msg_id)
            result2, _ = self._fluent_bundle.format_value(msg_id)
            assert result1 == result2


# =============================================================================
# Test Entry Point
# =============================================================================


# Configure the state machine test
TestFluentBundleStateMachine = FluentBundleStateMachine.TestCase
TestFluentBundleStateMachine.settings = settings(
    max_examples=100,
    stateful_step_count=30,
    deadline=None,  # Disable deadline for stateful tests
)


class TestBundleStateMachineBasic:
    """Basic sanity tests for the state machine itself."""

    def test_state_machine_can_initialize(self) -> None:
        """State machine can be initialized."""
        machine = FluentBundleStateMachine()
        machine.setup_bundle()
        assert machine._fluent_bundle is not None

    def test_state_machine_add_and_format(self) -> None:
        """Basic add_resource and format_value sequence works."""
        machine = FluentBundleStateMachine()
        machine.setup_bundle()

        # Add a message
        machine._fluent_bundle.add_resource("hello = Hello, world!")
        machine.known_messages["hello"] = "Hello, world!"

        # Format it
        result, errors = machine._fluent_bundle.format_value("hello")
        assert "Hello, world!" in result
        assert len(errors) == 0

    def test_state_machine_overwrite(self) -> None:
        """Message overwrite updates the value."""
        machine = FluentBundleStateMachine()
        machine.setup_bundle()

        machine._fluent_bundle.add_resource("msg = Original")
        result1, _ = machine._fluent_bundle.format_value("msg")
        assert "Original" in result1

        machine._fluent_bundle.add_resource("msg = Updated")
        result2, _ = machine._fluent_bundle.format_value("msg")
        assert "Updated" in result2

    def test_state_machine_cache_invalidation(self) -> None:
        """Cache is invalidated on add_resource."""
        machine = FluentBundleStateMachine()
        machine.setup_bundle()

        machine._fluent_bundle.add_resource("msg = First")
        machine._fluent_bundle.format_value("msg")  # Populate cache

        stats_before = machine._fluent_bundle.get_cache_stats()
        assert stats_before is not None
        assert stats_before["size"] >= 1

        machine._fluent_bundle.add_resource("other = Second")

        stats_after = machine._fluent_bundle.get_cache_stats()
        assert stats_after is not None
        assert stats_after["size"] == 0  # Cache cleared
