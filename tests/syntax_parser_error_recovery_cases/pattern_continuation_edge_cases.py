# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_error_recovery.py."""

from tests.syntax_parser_error_recovery_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PATTERN CONTINUATION EDGE CASES
# ============================================================================


class TestPatternContinuationEdgeCases:
    """Pattern continuation and text accumulation edge cases."""

    def test_pattern_line_691_placeable_continuation(self) -> None:
        """Placeable then continuation creates new text element."""
        result = parse_pattern(Cursor("{$x}\n    {$y}", 0))
        assert result is not None

    def test_pattern_continuation_after_placeable(self) -> None:
        """Continuation text as new element after placeable."""
        result = parse_pattern(
            Cursor("{$var}\n    continuation", 0)
        )
        assert result is not None
        assert len(result.value.elements) >= 2

    def test_continuation_at_start(self) -> None:
        """Continuation at start of pattern."""
        result = parse_pattern(Cursor("\n    {$x}", 0))
        assert result is not None

    def test_simple_pattern_continuation_before_placeable(self) -> None:
        """text accumulation before placeable in simple pattern."""
        result = parse_simple_pattern(
            Cursor("hello\n world{$x}", 0)
        )
        assert result is not None

    def test_simple_pattern_continuation_at_end(self) -> None:
        """text accumulation finalized at end of simple pattern."""
        result = parse_simple_pattern(
            Cursor("hello\n world", 0)
        )
        assert result is not None

    def test_pattern_at_eof_no_newline(self) -> None:
        """Pattern ends at EOF without newline."""
        parser = FluentParserV1()
        res = parser.parse("key = value")
        assert len(res.entries) == 1

    def test_pattern_ending_at_variant_marker(self) -> None:
        """Pattern ends at start of variant marker."""
        parser = FluentParserV1()
        res = parser.parse("key = text\n    [")
        assert len(res.entries) >= 1

    def test_select_with_malformed_arrow_eof(self) -> None:
        """Incomplete arrow at EOF."""
        parser = FluentParserV1()
        res = parser.parse("key = { $var -")
        assert len(res.entries) >= 1

    def test_function_with_trailing_comma(self) -> None:
        """Function call with trailing comma."""
        parser = FluentParserV1()
        res = parser.parse("key = { FUNC(a, b,) }")
        assert len(res.entries) >= 1
