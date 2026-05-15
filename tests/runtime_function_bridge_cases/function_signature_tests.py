# mypy: ignore-errors
"""Split test cases from tests/test_runtime_function_bridge.py."""

from tests.runtime_function_bridge_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# FUNCTION SIGNATURE TESTS
# ============================================================================


class TestFunctionSignature:
    """Test FunctionSignature dataclass."""

    def test_create_function_signature(self) -> None:
        """Create FunctionSignature with all fields."""
        sig = FunctionSignature(
            python_name="test_func",
            ftl_name="TEST",
            param_mapping=(("minimumValue", "minimum_value"),),
            callable=str,
            cacheable=False,
        )

        assert sig.python_name == "test_func"
        assert sig.ftl_name == "TEST"
        assert sig.param_mapping == (("minimumValue", "minimum_value"),)

    def test_function_signature_immutable(self) -> None:
        """FunctionSignature is immutable."""
        sig = FunctionSignature(
            python_name="test",
            ftl_name="TEST",
            param_mapping=(),
            callable=lambda: "test",
            cacheable=False,
        )

        with pytest.raises(AttributeError):
            sig.python_name = "new_name"  # type: ignore[misc]
