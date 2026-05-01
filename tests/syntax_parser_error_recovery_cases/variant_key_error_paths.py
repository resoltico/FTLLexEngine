# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_error_recovery.py."""

from tests.syntax_parser_error_recovery_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# VARIANT KEY ERROR PATHS
# ============================================================================


class TestVariantKeyErrorPaths:
    """Error paths in parse_variant_key and parse_variant."""

    def test_negative_sign_both_fail(self) -> None:
        """Hyphen: parse_number fails, parse_identifier fails too."""
        cursor = Cursor("-", 0)
        result = parse_variant_key(cursor)
        assert result is None

    def test_negative_sign_identifier_fallback_via_mock(self) -> None:
        """Lines 878-879: Number fails, identifier succeeds (defensive).

        Structurally unreachable without mocking because if cursor starts
        with '-', parse_identifier also fails (can't start with '-').
        """
        with (
            patch(
                "ftllexengine.syntax.parser.expressions.parse_number"
            ) as mock_num,
            patch(
                "ftllexengine.syntax.parser.expressions.parse_identifier"
            ) as mock_id,
        ):
            mock_num.return_value = ParseError("forced failure", Cursor("-test", 0))
            mock_id.return_value = ParseResult(
                "test", Cursor("test", 4)
            )
            cursor = Cursor("-test", 0)
            result = parse_variant_key(cursor)
            assert result is not None

    def test_variant_missing_opening_bracket(self) -> None:
        """parse_variant: no '[' at start."""
        assert parse_variant(Cursor("one", 0)) is None

    def test_variant_missing_closing_bracket(self) -> None:
        """parse_variant: no ']' after key."""
        assert parse_variant(Cursor("[one", 0)) is None

    def test_variant_invalid_key(self) -> None:
        """parse_variant: invalid key character."""
        assert parse_variant(Cursor("[@]", 0)) is None

    def test_select_no_variants(self) -> None:
        """parse_select_expression: immediate close, no variants."""
        sel = VariableReference(id=Identifier("count"))
        assert parse_select_expression(Cursor("}", 0), sel, 0) is None

    def test_select_no_default_variant(self) -> None:
        """parse_select_expression: variants without default."""
        sel = VariableReference(id=Identifier("count"))
        result = parse_select_expression(
            Cursor("[one] item\n}", 0), sel, 0
        )
        assert result is None
