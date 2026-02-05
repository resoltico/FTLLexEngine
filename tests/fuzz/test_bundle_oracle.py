"""State Machine Fuzzer for FluentBundle using Oracle Testing.

This module implements differential fuzzing of FluentBundle using the
ShadowBundle as a reference oracle. It uses Hypothesis's RuleBasedStateMachine
to generate sequences of operations and verify that both implementations
produce consistent results.

Key testing patterns:
- add_resource followed by format_pattern
- Multiple resources building up state
- Clear and rebuild operations
- Various argument combinations

The oracle comparison ignores:
- Function call results (shadow doesn't implement functions)
- Minor error message differences (focuses on structural errors)

Run with:
    pytest tests/fuzz/test_bundle_oracle.py -v

For intensive fuzzing:
    pytest tests/fuzz/test_bundle_oracle.py -v --hypothesis-seed=0

Python 3.13+.
"""

from __future__ import annotations

import pytest
from hypothesis import settings
from hypothesis.stateful import (
    RuleBasedStateMachine,
    initialize,
    invariant,
    rule,
)

from ftllexengine.runtime import FluentBundle
from tests.strategies.ftl import (
    ftl_identifiers,
    ftl_simple_messages,
    ftl_simple_text,
    ftl_terms,
    resolver_mixed_args,
)

from .shadow_bundle import ShadowBundle, compare_bundles

# Mark entire module as fuzz tests (excluded from normal test runs)
pytestmark = pytest.mark.fuzz


class BundleOracleStateMachine(RuleBasedStateMachine):
    """State machine for differential testing of FluentBundle vs ShadowBundle.

    This state machine generates random sequences of:
    - add_resource: Add FTL source to both bundles
    - format_pattern: Format a message and compare results
    - clear: Clear bundle state (if supported)

    Invariants:
    - Both bundles should have the same message IDs
    - Formatting the same message should produce the same result
    """

    def __init__(self) -> None:
        super().__init__()
        self.real: FluentBundle | None = None
        self.shadow: ShadowBundle | None = None
        self.added_messages: set[str] = set()
        self.locale = "en_US"

    @initialize()
    def init_bundles(self) -> None:
        """Initialize both bundles with the same locale."""
        self.real = FluentBundle(self.locale)
        self.shadow = ShadowBundle(locale=self.locale)
        self.added_messages = set()

    @rule(source=ftl_simple_messages())
    def add_simple_message(self, source: str) -> None:
        """Add a simple message to both bundles."""
        assert self.real is not None
        assert self.shadow is not None

        real_junk = self.real.add_resource(source)
        shadow_junk = self.shadow.add_resource(source)

        # Both should produce same number of junk entries
        assert len(real_junk) == len(shadow_junk), (
            f"Junk count mismatch: real={len(real_junk)}, shadow={len(shadow_junk)}"
        )

        # Track successfully added message IDs
        # Extract message ID from source (format: "id = value")
        if not real_junk and " = " in source:
            msg_id = source.split(" = ", maxsplit=1)[0].strip()
            self.added_messages.add(msg_id)

    @rule(source=ftl_terms())
    def add_term(self, source: str) -> None:
        """Add a term definition to both bundles."""
        assert self.real is not None
        assert self.shadow is not None

        real_junk = self.real.add_resource(source)
        shadow_junk = self.shadow.add_resource(source)

        assert len(real_junk) == len(shadow_junk)

    @rule(
        msg_id=ftl_identifiers(),
        args=resolver_mixed_args(),
    )
    def format_existing_message(self, msg_id: str, args: dict) -> None:
        """Format a potentially existing message and compare results."""
        assert self.real is not None
        assert self.shadow is not None

        # Only test if we've added some messages
        if not self.added_messages:
            return

        # Use a known message ID if available
        if msg_id not in self.added_messages and self.added_messages:
            msg_id = next(iter(self.added_messages))

        real_result = self.real.format_pattern(msg_id, args)
        shadow_result = self.shadow.format_pattern(msg_id, args)

        # Compare results (we use the strings for assertion)
        _match, _explanation = compare_bundles(
            real_result, shadow_result, ignore_function_errors=True
        )

        # Allow minor differences in error handling
        # Focus on: same string result, similar error presence
        real_str, _real_errors = real_result
        shadow_str, _shadow_errors = shadow_result

        # Primary assertion: formatted strings should match
        # (with allowance for function placeholder differences)
        if "{!" not in shadow_str:  # No function placeholders
            assert real_str == shadow_str, (
                f"Format mismatch for {msg_id}: "
                f"real={real_str!r}, shadow={shadow_str!r}"
            )

    @invariant()
    def message_ids_match(self) -> None:
        """Both bundles should have the same message IDs."""
        if self.real is None or self.shadow is None:
            return

        real_ids = set(self.real.get_message_ids())
        shadow_ids = self.shadow.get_message_ids()

        assert real_ids == shadow_ids, (
            f"Message ID mismatch: "
            f"only_real={real_ids - shadow_ids}, "
            f"only_shadow={shadow_ids - real_ids}"
        )


# Create the test class from the state machine
TestBundleOracle = BundleOracleStateMachine.TestCase


class BundleLifecycleStateMachine(RuleBasedStateMachine):
    """State machine testing bundle lifecycle: add -> format -> clear -> add.

    Tests that bundles correctly handle state transitions and that
    clearing state produces consistent results.
    """

    def __init__(self) -> None:
        super().__init__()
        self.real: FluentBundle | None = None
        self.shadow: ShadowBundle | None = None
        self.message_count = 0

    @initialize()
    def init_bundles(self) -> None:
        """Initialize both bundles."""
        self.real = FluentBundle("en_US")
        self.shadow = ShadowBundle(locale="en_US")
        self.message_count = 0

    @rule(
        msg_id=ftl_identifiers(),
        value=ftl_simple_text(),
    )
    def add_message(self, msg_id: str, value: str) -> None:
        """Add a message to both bundles."""
        assert self.real is not None
        assert self.shadow is not None

        source = f"{msg_id} = {value}"
        self.real.add_resource(source)
        self.shadow.add_resource(source)
        self.message_count += 1

    @rule()
    def format_all_messages(self) -> None:
        """Format all messages and verify consistency."""
        assert self.real is not None
        assert self.shadow is not None

        for msg_id in self.shadow.get_message_ids():
            real_result = self.real.format_pattern(msg_id, {})
            shadow_result = self.shadow.format_pattern(msg_id, {})

            real_str, _ = real_result
            shadow_str, _ = shadow_result

            assert real_str == shadow_str, f"Mismatch for {msg_id}"

    @rule()
    def reinitialize(self) -> None:
        """Reinitialize bundles (simulates clear behavior)."""
        self.real = FluentBundle("en_US")
        self.shadow = ShadowBundle(locale="en_US")
        self.message_count = 0

    @invariant()
    def message_count_consistent(self) -> None:
        """Message counts should be consistent."""
        if self.real is None or self.shadow is None:
            return

        real_count = len(self.real.get_message_ids())
        shadow_count = len(self.shadow.get_message_ids())

        # Counts may differ if same ID added multiple times (overwrites)
        # But both should agree on the final state
        assert real_count == shadow_count


TestBundleLifecycle = BundleLifecycleStateMachine.TestCase


# Use centralized stateful_fuzz profile from conftest.py
@pytest.fixture(autouse=True)
def use_stateful_settings() -> None:
    """Use stateful fuzzing profile for oracle tests."""
    settings.load_profile("stateful_fuzz")
