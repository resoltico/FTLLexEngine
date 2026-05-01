# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_runtime_resolver_state_machine.py."""

from tests.fuzz_runtime_resolver_state_machine_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# STRATEGY HELPERS
# ============================================================================


def simple_pattern(text: str) -> Pattern:
    """Create simple text pattern."""
    return Pattern(elements=(TextElement(value=text),))


def variable_pattern(var_name: str) -> Pattern:
    """Create pattern with variable reference."""
    return Pattern(
        elements=(
            Placeable(expression=VariableReference(id=Identifier(name=var_name))),
        )
    )


def term_reference_pattern(term_name: str) -> Pattern:
    """Create pattern with term reference."""
    return Pattern(
        elements=(
            Placeable(
                expression=TermReference(id=Identifier(name=term_name), attribute=None)
            ),
        )
    )


def message_reference_pattern(msg_name: str) -> Pattern:
    """Create pattern with message reference."""
    return Pattern(
        elements=(
            Placeable(
                expression=MessageReference(id=Identifier(name=msg_name), attribute=None)
            ),
        )
    )
