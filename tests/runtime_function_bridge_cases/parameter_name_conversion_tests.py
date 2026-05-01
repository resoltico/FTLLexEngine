# mypy: ignore-errors
"""Split test cases from tests/test_runtime_function_bridge.py."""

from tests.runtime_function_bridge_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PARAMETER NAME CONVERSION TESTS
# ============================================================================


class TestParameterNameConversion:
    """Test snake_case <-> camelCase conversion."""

    def test_to_camel_case_single_word(self) -> None:
        """Convert single word (no change)."""
        result = FunctionRegistry._to_camel_case("value")

        assert result == "value"

    def test_to_camel_case_two_words(self) -> None:
        """Convert two_words to twoWords."""
        result = FunctionRegistry._to_camel_case("minimum_value")

        assert result == "minimumValue"

    def test_to_camel_case_multiple_words(self) -> None:
        """Convert multiple_word_name to multipleWordName."""
        result = FunctionRegistry._to_camel_case("minimum_fraction_digits")

        assert result == "minimumFractionDigits"

    def test_to_camel_case_already_camel(self) -> None:
        """Convert camelCase (no underscores) stays same."""
        result = FunctionRegistry._to_camel_case("alreadyCamel")

        assert result == "alreadyCamel"
