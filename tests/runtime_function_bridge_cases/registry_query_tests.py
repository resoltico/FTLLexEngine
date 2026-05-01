# mypy: ignore-errors
"""Split test cases from tests/test_runtime_function_bridge.py."""

from tests.runtime_function_bridge_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# REGISTRY QUERY TESTS
# ============================================================================


class TestRegistryQueries:
    """Test registry query methods."""

    def test_has_function_returns_true_when_registered(self) -> None:
        """has_function returns True for registered function."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="UPPER")

        assert registry.has_function("UPPER")

    def test_has_function_returns_false_when_not_registered(self) -> None:
        """has_function returns False for unregistered function."""
        registry = FunctionRegistry()

        assert not registry.has_function("UNKNOWN")

    def test_get_python_name_returns_name_when_registered(self) -> None:
        """get_python_name returns Python function name."""
        registry = FunctionRegistry()
        registry.register(simple_function, ftl_name="UPPER")

        python_name = registry.get_python_name("UPPER")

        assert python_name == "simple_function"

    def test_get_python_name_returns_none_when_not_registered(self) -> None:
        """get_python_name returns None for unregistered function."""
        registry = FunctionRegistry()

        python_name = registry.get_python_name("UNKNOWN")

        assert python_name is None
