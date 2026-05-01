# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_expressions.py."""

from tests.syntax_parser_expressions_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PARSE CONTEXT
# ============================================================================


class TestParseContextDepthExceeded:
    """Tests for ParseContext._depth_exceeded_flag edge case."""

    def test_mark_depth_exceeded_with_none_flag(self) -> None:
        """Handle _depth_exceeded_flag being None gracefully."""
        context = object.__new__(ParseContext)
        object.__setattr__(context, "max_nesting_depth", 5)
        object.__setattr__(context, "current_depth", 0)
        object.__setattr__(context, "_depth_exceeded_flag", None)
        context.mark_depth_exceeded()
        assert context._depth_exceeded_flag is None
