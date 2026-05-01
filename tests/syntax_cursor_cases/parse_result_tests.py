# mypy: ignore-errors
"""Split test cases from tests/test_syntax_cursor.py."""

from tests.syntax_cursor_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PARSE RESULT TESTS
# ============================================================================


class TestParseResult:
    """Test ParseResult container."""

    def test_create_parse_result(self) -> None:
        """Create ParseResult with value and cursor."""
        cursor = Cursor("hello", 0)
        result = ParseResult("h", cursor.advance())

        assert result.value == "h"
        assert result.cursor.pos == 1

    def test_parse_result_immutability(self) -> None:
        """ParseResult is immutable."""
        cursor = Cursor("hello", 0)
        result = ParseResult("test", cursor)

        with pytest.raises(AttributeError):
            result.value = "new"  # type: ignore[misc]

    def test_parse_result_with_complex_value(self) -> None:
        """ParseResult can hold complex types."""
        cursor = Cursor("hello", 3)
        value = {"key": "value", "list": [1, 2, 3]}
        result = ParseResult(value, cursor)

        assert result.value == {"key": "value", "list": [1, 2, 3]}
        assert result.cursor.pos == 3
