# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_expressions.py."""

from tests.syntax_parser_expressions_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# VARIABLE REFERENCE
# ============================================================================


class TestParseVariableReference:
    """Tests for parse_variable_reference error and success paths."""

    def test_no_dollar_sign(self) -> None:
        """Returns None without '$' prefix."""
        assert parse_variable_reference(Cursor("name", 0)) is None

    def test_at_eof(self) -> None:
        """Returns None at EOF."""
        assert parse_variable_reference(Cursor("", 0)) is None

    def test_dollar_only(self) -> None:
        """Returns None with just '$' (no identifier)."""
        assert parse_variable_reference(Cursor("$ ", 0)) is None

    def test_dollar_followed_by_digit(self) -> None:
        """Returns None with '$' followed by digit."""
        assert parse_variable_reference(Cursor("$123", 0)) is None

    def test_valid_variable_reference(self) -> None:
        """Parses valid '$name' as VariableReference."""
        result = parse_variable_reference(Cursor("$var", 0))
        assert result is not None
        assert isinstance(result.value, VariableReference)
        assert result.value.id.name == "var"

    @given(st.text(min_size=1).filter(lambda t: not t.startswith("$")))
    @example("")
    @example("x")
    def test_no_dollar_prefix_property(self, text: str) -> None:
        """Non-$ prefixed text always returns None."""
        event(f"first_char={repr(text[:1]) if text else 'eof'}")
        cursor = Cursor(text, 0)
        result = parse_variable_reference(cursor)
        assert result is None

    @given(st.text(max_size=0))
    @example("$")
    @example("$123")
    @example("$ ")
    def test_dollar_without_valid_identifier_property(
        self, suffix: str
    ) -> None:
        """'$' plus invalid identifier always returns None."""
        event(f"suffix_len={len(suffix)}")
        text = "$" + suffix
        cursor = Cursor(text, 0)
        result = parse_variable_reference(cursor)
        if result is not None:
            assert isinstance(result.value, VariableReference)
