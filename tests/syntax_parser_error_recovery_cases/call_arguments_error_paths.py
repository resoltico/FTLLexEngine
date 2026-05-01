# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_error_recovery.py."""

from tests.syntax_parser_error_recovery_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# CALL ARGUMENTS ERROR PATHS
# ============================================================================


class TestCallArgumentsErrorPaths:
    """Error paths in parse_call_arguments."""

    def test_named_arg_name_not_identifier(self) -> None:
        """Named argument name must be identifier (not variable)."""
        result = parse_call_arguments(Cursor('$var: "value")', 0))
        assert result is None

    def test_duplicate_named_argument(self) -> None:
        """Duplicate named argument names."""
        assert parse_call_arguments(Cursor("x: 1, x: 2)", 0)) is None

    def test_named_arg_missing_value(self) -> None:
        """Expected value after ':' but got ')'."""
        assert parse_call_arguments(Cursor("x: )", 0)) is None

    def test_named_arg_value_parse_fails(self) -> None:
        """Value expression parse fails after ':'."""
        assert parse_call_arguments(Cursor("x: @)", 0)) is None

    def test_named_arg_eof_after_colon(self) -> None:
        """EOF after ':' in named argument."""
        assert parse_call_arguments(Cursor("x:", 0)) is None

    def test_positional_after_named(self) -> None:
        """Positional args must come before named."""
        assert parse_call_arguments(Cursor("x: 1, $var)", 0)) is None

    def test_named_arg_non_literal_value(self) -> None:
        """Named argument value must be literal."""
        assert parse_call_arguments(
            Cursor("x: $var)", 0)
        ) is None

    def test_trailing_comma(self) -> None:
        """Trailing comma in argument list."""
        result = parse_call_arguments(Cursor("1, 2, )", 0))
        assert result is not None
        assert len(result.value.positional) == 2

    def test_argument_expression_fails_in_loop(self) -> None:
        """Argument expression fails at '@'."""
        assert parse_call_arguments(Cursor("@)", 0)) is None
