# mypy: ignore-errors
"""Split test cases from tests/test_runtime_function_bridge.py."""

from tests.runtime_function_bridge_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# HELPER FUNCTIONS FOR TESTING
# ============================================================================


def sample_function(value: int, *, minimum_fraction_digits: int = 0) -> str:
    """Sample function with snake_case parameters."""
    return f"{value:.{minimum_fraction_digits}f}"


def simple_function(text: str) -> str:
    """Simple function with single parameter."""
    return text.upper()


def positional_only_function(value: int, /) -> str:
    """Function with positional-only parameter."""
    return str(value * 2)


def mixed_params_function(
    value: int, /, *, use_grouping: bool = False, date_style: str = "short"
) -> str:
    """Function with mixed parameter types."""
    result = str(value)
    if use_grouping:
        result = f"{value:,}"
    return f"{result} ({date_style})"
