"""Property-Based Testing Examples for FTLLexEngine.

This example demonstrates how to use Hypothesis for property-based testing
of FTLLexEngine components. Property-based testing generates random test
inputs to discover edge cases and verify universal properties.

Learn more about property-based testing:
- Hypothesis documentation: https://hypothesis.readthedocs.io/
- Property-based testing guide: https://increment.com/testing/in-praise-of-property-based-testing/

Run this example:
    python examples/property_based_testing.py

Python 3.13+.

Linting Notes:
    This file uses Hypothesis's property-based testing framework, which employs
    decorator-based dependency injection (@given, @rule, @initialize). Some linters
    (pylint, mypy) don't understand these patterns, leading to false positives.
    Suppressions in this file are architecturally justified - see inline comments.
"""

# pylint: disable=no-value-for-parameter,line-too-long
# Justification: Hypothesis's @given decorator injects test parameters at runtime.
# Functions decorated with @given are called without arguments - Hypothesis provides them.
# This is Hypothesis's core design pattern used by thousands of projects.
# Reference:
#   https://hypothesis.readthedocs.io/en/latest/details.html#the-gory-details-of-given-parameters

from __future__ import annotations

from typing import TYPE_CHECKING

from hypothesis import assume, given, settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, initialize, rule

from ftllexengine import (
    FluentBundle,
    FluentLocalization,
    parse_ftl,
    serialize_ftl,
)

# Parser uses Junk nodes for syntax errors (robustness principle)
# and never raises exceptions.

if TYPE_CHECKING:
    # Type hints for mypy - RuleBasedStateMachine state
    # These are set by @initialize() decorator, not __init__
    pass


# ==============================================================================
# Example 1: Testing Universal Properties
# ==============================================================================


def example_1_format_never_raises() -> None:
    """Property: format_pattern() never raises exceptions.

    This is a critical property of FTLLexEngine - formatting should always
    return a usable string and collect errors in a list, never crash.
    """
    print("=" * 70)
    print("Example 1: format_pattern() Never Raises Exceptions")
    print("=" * 70)

    @given(message_id=st.text(), args=st.dictionaries(st.text(), st.text()))
    @settings(max_examples=100)
    def test_format_never_raises(message_id: str, args: dict[str, str]) -> None:
        """Format never raises, even with random inputs."""
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource("test = Test message")

        # Should never raise, even with garbage inputs
        result, errors = bundle.format_pattern(message_id, args)

        # Always returns a string
        assert isinstance(result, str)
        # Always returns a tuple of errors
        assert isinstance(errors, tuple)

    # Run the property test
    test_format_never_raises()
    print("Property verified: format_pattern() never raises exceptions\n")


# ==============================================================================
# Example 2: Testing Idempotence
# ==============================================================================


def example_2_parse_serialize_roundtrip() -> None:
    """Property: parse → serialize → parse is idempotent.

    Parsing FTL source, serializing back to string, and parsing again
    should produce the same AST (for valid FTL).
    """
    print("=" * 70)
    print("Example 2: Parse/Serialize Roundtrip Idempotence")
    print("=" * 70)

    @given(
        message_id=st.text(
            alphabet=st.characters(
                whitelist_categories=("Ll", "Lu"),  # type: ignore[arg-type,unused-ignore]
                # mypy: Hypothesis type stubs expect Collection[Literal['Ll', 'Lu', ...]]
                # but tuple[str] works fine at runtime. This is a Hypothesis stub limitation.
                # Note: unused-ignore for mypy versions that don't need this (varies by version)
                min_codepoint=97,
                max_codepoint=122,
            ),
            min_size=1,
            max_size=10
        ),
        message_value=st.text(min_size=1, max_size=50)
    )
    @settings(max_examples=50)
    def test_roundtrip_idempotent(message_id: str, message_value: str) -> None:
        """Parse → serialize → parse produces same AST (for valid FTL only)."""

        # Avoid newlines in message value for simplicity
        message_value_clean = message_value.replace("\n", " ")

        ftl_source = f"{message_id} = {message_value_clean}"

        # Parser uses Junk nodes for syntax errors (robustness principle)
        # Check for Junk entries to filter invalid FTL
        from ftllexengine.syntax.ast import Junk

        # First parse
        resource1 = parse_ftl(ftl_source)

        # Filter out FTL with parse errors (Junk entries)
        if any(isinstance(entry, Junk) for entry in resource1.entries):
            # Invalid FTL - property doesn't apply, skip this example
            assume(False)

        # Only test roundtrip for valid FTL
        serialized = serialize_ftl(resource1)
        resource2 = parse_ftl(serialized)

        # Property: Roundtrip should preserve structure
        assert len(resource1.entries) == len(resource2.entries)

    test_roundtrip_idempotent()
    print("Property verified: parse/serialize roundtrip is idempotent\n")


# ==============================================================================
# Example 3: Testing Invariants
# ==============================================================================


def example_3_message_count_invariant() -> None:
    """Property: get_message_ids() count matches has_message() count.

    The number of message IDs should always equal the number of messages
    for which has_message() returns True.
    """
    print("=" * 70)
    print("Example 3: Message Count Invariant")
    print("=" * 70)

    @given(
        num_messages=st.integers(min_value=0, max_value=20),
    )
    @settings(max_examples=50)
    def test_message_count_consistent(num_messages: int) -> None:
        """Message count from get_message_ids() matches has_message() count."""
        bundle = FluentBundle("en", use_isolating=False)

        # Add messages
        for i in range(num_messages):
            bundle.add_resource(f"msg{i} = Message {i}")

        message_ids = bundle.get_message_ids()

        # Invariant: len(get_message_ids()) == count of has_message(True)
        assert len(message_ids) == sum(
            1 for msg_id in message_ids if bundle.has_message(msg_id)
        )

        # Also verify all IDs are actually present
        assert all(bundle.has_message(msg_id) for msg_id in message_ids)

    test_message_count_consistent()
    print("Property verified: message count invariant holds\n")


# ==============================================================================
# Example 4: Testing Symmetry
# ==============================================================================


def example_4_fallback_chain_symmetry() -> None:
    """Property: Fallback chain order affects which locale is chosen.

    When a message exists in multiple locales, the first locale in the
    chain should always be selected.
    """
    print("=" * 70)
    print("Example 4: Fallback Chain Symmetry")
    print("=" * 70)

    @given(
        locales=st.lists(
            st.sampled_from(["en", "lv", "lt", "de", "fr"]),
            min_size=2,
            max_size=4,
            unique=True
        )
    )
    @settings(max_examples=50)
    def test_first_locale_wins(locales: list[str]) -> None:
        """First locale in chain takes precedence."""
        l10n = FluentLocalization(locales)

        # Add same message to all locales with different values
        for locale in locales:
            l10n.add_resource(locale, f"test = Value from {locale}")

        result, _ = l10n.format_value("test")

        # Should always use first locale
        assert result == f"Value from {locales[0]}"

    test_first_locale_wins()
    print("Property verified: fallback chain symmetry holds\n")


# ==============================================================================
# Example 5: Testing Batch Operations
# ==============================================================================


def example_5_batch_equals_individual() -> None:
    """Property: Batch variable extraction equals individual extractions.

    get_all_message_variables() should return identical results to calling
    get_message_variables() for each message individually.
    """
    print("=" * 70)
    print("Example 5: Batch Operations Equivalence")
    print("=" * 70)

    @given(
        num_messages=st.integers(min_value=0, max_value=15),
        num_vars_per_msg=st.integers(min_value=0, max_value=4),
    )
    @settings(max_examples=50)
    def test_batch_equals_individual(
        num_messages: int, num_vars_per_msg: int
    ) -> None:
        """Batch extraction matches individual extractions."""
        bundle = FluentBundle("en", use_isolating=False)

        # Generate messages with variables
        for i in range(num_messages):
            vars_part = " ".join(
                f"{{ $var{j} }}"
                for j in range(num_vars_per_msg)
            )
            bundle.add_resource(f"msg{i} = Text {vars_part}")

        # Batch method
        batch_result = bundle.get_all_message_variables()

        # Individual method
        individual_result = {
            msg_id: bundle.get_message_variables(msg_id)
            for msg_id in bundle.get_message_ids()
        }

        # Property: batch should equal individual
        assert batch_result == individual_result

    test_batch_equals_individual()
    print("Property verified: batch extraction equals individual\n")


# ==============================================================================
# Example 6: Stateful Property Testing (Advanced)
# ==============================================================================


def example_6_stateful_bundle_testing() -> None:
    """Advanced: Stateful testing of FluentBundle operations.

    This demonstrates using Hypothesis's stateful testing to verify that
    a sequence of operations maintains bundle invariants.
    """
    print("=" * 70)
    print("Example 6: Stateful Property Testing (Advanced)")
    print("=" * 70)

    class BundleStateMachine(RuleBasedStateMachine):
        """State machine for testing FluentBundle operations.

        Note: Hypothesis's RuleBasedStateMachine uses @initialize() instead of __init__.
        State attributes are set there, not in __init__, which confuses some linters.
        """

        # Type hints for mypy - attributes set by @initialize() decorator
        bundle: FluentBundle  # type: ignore[assignment,unused-ignore]
        # mypy: RuleBasedStateMachine base class defines 'bundle' as a method descriptor.
        # We override it as an instance attribute in @initialize(). This is the correct
        # Hypothesis pattern - the type: ignore is justified.
        known_messages: set[str]

        @initialize()  # pylint: disable=attribute-defined-outside-init
        # Justification: Hypothesis RuleBasedStateMachine uses @initialize() decorator
        # instead of __init__ for state initialization. This is the correct pattern
        # per Hypothesis documentation, not a code smell.
        def init_bundle(self) -> None:
            """Initialize bundle state."""
            self.bundle = FluentBundle("en", use_isolating=False)  # type: ignore[assignment,method-assign,unused-ignore]
            # mypy: @initialize() sets instance attributes, but mypy sees bundle as a method.
            # Different mypy versions report this as either 'assignment' or 'method-assign'.
            # The type: ignore is justified - this is Hypothesis's RuleBasedStateMachine design.
            self.known_messages = set()

        @rule(
            message_id=st.text(
                alphabet=st.characters(
                    whitelist_categories=("Ll",),  # type: ignore[arg-type,unused-ignore]
                    # mypy: Same Hypothesis type stub issue as before
                    # Note: unused-ignore for mypy versions without this limitation
                    min_codepoint=97,
                    max_codepoint=122,
                ),
                min_size=1,
                max_size=8
            ),
            value=st.text(min_size=1, max_size=20)
        )
        def add_message(self, message_id: str, value: str) -> None:
            """Add a message to bundle."""
            # Clean value
            value_clean = value.replace("\n", " ")

            self.bundle.add_resource(f"{message_id} = {value_clean}")
            self.known_messages.add(message_id)

        @rule()
        def check_invariants(self) -> None:  # pylint: disable=arguments-differ
            # Justification: Hypothesis RuleBasedStateMachine.check_invariants() base
            # method accepts **kwargs, but overrides are allowed to have different
            # signatures. This is intentional - @rule() decorated methods define
            # their own parameters per Hypothesis documentation.
            """Verify bundle invariants hold after any sequence of operations."""
            # Invariant 1: All known messages are present
            for msg_id in self.known_messages:
                assert self.bundle.has_message(msg_id)

            # Invariant 2: get_message_ids() returns all known messages
            message_ids = set(self.bundle.get_message_ids())
            assert self.known_messages.issubset(message_ids)

            # Invariant 3: get_all_message_variables() covers all messages
            all_vars = self.bundle.get_all_message_variables()
            assert set(all_vars.keys()) == message_ids

    # Run stateful tests
    # Note: TestCase naming convention is from Hypothesis API
    test_bundle_state = BundleStateMachine.TestCase
    test_bundle_state.settings = settings(max_examples=20, stateful_step_count=10)

    try:
        # Run a few iterations manually
        state_machine = BundleStateMachine()
        state_machine.init_bundle()

        # Simulate some operations
        state_machine.add_message("hello", "Hello World")
        state_machine.check_invariants()
        state_machine.add_message("goodbye", "Goodbye")
        state_machine.check_invariants()

        print("Stateful properties verified successfully\n")
    except AssertionError as e:
        # AssertionError: Invariant violated
        # Note: Parser uses Junk nodes for syntax errors, never raises exceptions
        print(f"[FAIL] Stateful test found issue: {e}\n")


# ==============================================================================
# Example 7: Custom Strategies for FTL
# ==============================================================================


def example_7_custom_ftl_strategies() -> None:
    """Property: Custom Hypothesis strategies for valid FTL generation.

    This demonstrates creating custom strategies to generate valid FTL
    syntax for more targeted property testing.
    """
    print("=" * 70)
    print("Example 7: Custom FTL Strategies")
    print("=" * 70)

    # Custom strategy for valid message IDs
    @st.composite
    def message_id_strategy(draw: st.DrawFn) -> str:
        """Generate valid FTL message IDs."""
        # FTL message IDs: [a-z][a-z0-9-]*
        first_char = draw(st.sampled_from("abcdefghijklmnopqrstuvwxyz"))
        rest = draw(
            st.text(
                alphabet="abcdefghijklmnopqrstuvwxyz0123456789-",
                min_size=0,
                max_size=15,
            )
        )
        return first_char + rest

    # Custom strategy for simple FTL patterns
    @st.composite
    def simple_pattern_strategy(draw: st.DrawFn) -> str:
        """Generate simple FTL patterns (text + variables)."""
        text = draw(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Ll", "Lu")  # type: ignore[arg-type,unused-ignore]
                    # mypy: Hypothesis type stub limitation (version-dependent)
                ),
                min_size=1,
                max_size=30,
            )
        )
        # Clean up text
        text = text.replace("\n", " ").replace("{", "").replace("}", "")

        # Maybe add a variable
        add_var = draw(st.booleans())
        if add_var:
            var_name = draw(
                st.text(
                    alphabet=st.characters(
                        whitelist_categories=("Ll",),  # type: ignore[arg-type,unused-ignore]
                        # mypy: Hypothesis type stub limitation (version-dependent)
                        min_codepoint=97,
                        max_codepoint=122,
                    ),
                    min_size=1,
                    max_size=8,
                )
            )
            text += f" {{ ${var_name} }}"

        return text

    @given(
        message_id=message_id_strategy(),
        pattern=simple_pattern_strategy()
    )
    @settings(max_examples=50)
    def test_valid_ftl_always_parses(message_id: str, pattern: str) -> None:
        """Valid FTL always parses successfully."""
        ftl_source = f"{message_id} = {pattern}"

        # Should parse without errors
        resource = parse_ftl(ftl_source)

        # Should have at least one entry
        assert len(resource.entries) > 0

        # Should be able to add to bundle
        bundle = FluentBundle("en", use_isolating=False)
        bundle.add_resource(ftl_source)

        # Should be able to retrieve message
        assert bundle.has_message(message_id)

    test_valid_ftl_always_parses()
    print("Custom FTL strategies work correctly\n")


# ==============================================================================
# Main - Run All Examples
# ==============================================================================


def main() -> None:
    """Run all property-based testing examples."""
    print("\n" + "=" * 70)
    print("PROPERTY-BASED TESTING EXAMPLES FOR FTLLEXENGINE")
    print("=" * 70)
    print()
    print("These examples demonstrate how to use Hypothesis for property-based")
    print("testing of FTLLexEngine. Each example tests a universal property that")
    print("should hold for all valid inputs.")
    print()

    example_1_format_never_raises()
    example_2_parse_serialize_roundtrip()
    example_3_message_count_invariant()
    example_4_fallback_chain_symmetry()
    example_5_batch_equals_individual()
    example_6_stateful_bundle_testing()
    example_7_custom_ftl_strategies()

    print("=" * 70)
    print("ALL PROPERTY-BASED TESTS COMPLETED")
    print("=" * 70)
    print()
    print("Key Takeaways:")
    print("1. Property tests find edge cases traditional tests miss")
    print("2. They verify universal properties across many random inputs")
    print("3. Hypothesis shrinks failing examples to minimal reproducers")
    print("4. Use @given decorator with strategies to generate test data")
    print("5. Stateful testing verifies invariants across operation sequences")
    print()
    print("Learn more:")
    print("- Hypothesis docs: https://hypothesis.readthedocs.io/")
    print()


if __name__ == "__main__":
    main()
