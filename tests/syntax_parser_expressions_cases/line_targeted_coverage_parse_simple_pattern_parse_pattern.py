# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_expressions.py."""

from tests.syntax_parser_expressions_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# LINE-TARGETED COVERAGE (parse_simple_pattern / parse_pattern)
# ============================================================================


class TestSimplePatternLineCoverage:
    """Targeted line coverage for parse_simple_pattern."""

    def test_accumulated_text_before_placeable_prepend(self) -> None:
        """Accumulated text merged with last element before placeable."""
        result = parse_simple_pattern(
            Cursor("First\n    continued{$var}", 0)
        )
        assert result is not None

    def test_accumulated_text_before_placeable_new(self) -> None:
        """Accumulated text as new element before placeable."""
        result = parse_simple_pattern(
            Cursor("\n    start{$var}", 0)
        )
        assert result is not None

    def test_finalize_accumulated_merged(self) -> None:
        """Finalize accumulated text merged with existing element."""
        result = parse_simple_pattern(
            Cursor("Text\n    more continuation", 0)
        )
        assert result is not None

    def test_finalize_accumulated_new_element(self) -> None:
        """Finalize accumulated text as new element."""
        result = parse_simple_pattern(
            Cursor("{$var}\n    ending text", 0)
        )
        assert result is not None

    def test_variant_continuation_extra_spaces(self) -> None:
        """Variant value with extra indent before placeable."""
        source = (
            "msg = {$count ->\n"
            "    [one] Items:\n"
            "            {$count}\n"
            "    *[other] Items\n"
            "}"
        )
        result = parse_message(Cursor(source, 0), ParseContext())
        assert result is not None
        assert isinstance(result.value, Message)

    def test_variant_trailing_accumulated_spaces(self) -> None:
        """Variant ending with accumulated extra spaces."""
        source = (
            "msg = {$count ->\n"
            "    [one] Items\n\n"
            "    *[other] More\n"
            "}"
        )
        result = parse_message(Cursor(source, 0), ParseContext())
        assert result is not None
        assert isinstance(result.value, Message)


class TestPatternLineCoverage:
    """Targeted line coverage for parse_pattern."""

    def test_accumulated_as_new_element(self) -> None:
        """Accumulated continuation becomes new element."""
        result = parse_pattern(
            Cursor("{$x}\n    text after placeable", 0)
        )
        assert result is not None

    def test_finalize_merged(self) -> None:
        """Finalize merged with existing element."""
        result = parse_pattern(
            Cursor("Text\n    final continuation", 0)
        )
        assert result is not None

    def test_finalize_new_element(self) -> None:
        """Finalize as new element."""
        result = parse_pattern(
            Cursor("{$x}\n    final", 0)
        )
        assert result is not None
