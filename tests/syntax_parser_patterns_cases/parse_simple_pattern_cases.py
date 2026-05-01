# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_patterns.py."""

from tests.syntax_parser_patterns_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PARSE_SIMPLE_PATTERN
# ============================================================================


class TestParseSimplePattern:
    """Tests for parse_simple_pattern basic behavior."""

    def test_with_variable(self) -> None:
        """Parses pattern with variable reference."""
        cursor = Cursor("Hello {$name}", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert len(result.value.elements) == 2

    def test_stops_at_bracket(self) -> None:
        """Bracket lookahead: [key]rest is literal text."""
        cursor = Cursor("Value[key]rest", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.value.elements[0].value == "Value[key]rest"  # type: ignore[union-attr]
        assert result.cursor.is_eof

        # [key] followed by } IS a variant marker
        cursor = Cursor("Value [one]}", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.value.elements[0].value == "Value "  # type: ignore[union-attr]
        assert result.cursor.current == "["

    def test_stops_at_asterisk(self) -> None:
        """Asterisk lookahead: *[ is variant, * alone is literal."""
        cursor = Cursor("Text*[other]", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.cursor.current == "*"

        cursor = Cursor("Text*rest", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.value.elements[0].value == "Text*rest"  # type: ignore[union-attr]

    def test_stops_at_brace(self) -> None:
        """Stops at } (expression end)."""
        cursor = Cursor("Value}rest", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.cursor.current == "}"

    def test_placeable_parse_fails(self) -> None:
        """Returns None when placeable parsing fails."""
        cursor = Cursor("Text {invalid", 0)
        with patch(
            "ftllexengine.syntax.parser.expressions.parse_placeable",
            return_value=None,
        ):
            result = parse_simple_pattern(cursor)
        assert result is None

    def test_variant_markers_lookahead(self) -> None:
        """Variant markers vs literal text disambiguation."""
        # *[other] IS a variant marker
        cursor = Cursor("*[other]", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert len(result.value.elements) == 0
        assert result.cursor.current == "*"

        # [INFO] followed by text is literal
        cursor = Cursor("[INFO] message", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert result.value.elements[0].value == "[INFO] message"  # type: ignore[union-attr]

    def test_malformed_placeable_returns_none(self) -> None:
        """Malformed placeable ({@) returns None."""
        cursor = Cursor("text{@", 0)
        result = parse_simple_pattern(cursor)
        assert result is None

    def test_in_select_expression(self) -> None:
        """parse_simple_pattern as used in select expression variants."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("""msg = {NUMBER(1) ->
    [one] One item
    *[other] Many items
}""")
        result, _ = bundle.format_pattern("msg")
        assert "item" in result


class TestSimplePatternTextAccDirect:
    """Tests for text_acc paths in parse_simple_pattern (Cursor-direct)."""

    def test_text_then_continuation_then_placeable(self) -> None:
        """Accumulated text merged with prior element before placeable."""
        result = parse_simple_pattern(Cursor("hello\n    {$x}", 0))
        assert result is not None
        assert len(result.value.elements) >= 2

    def test_continuation_then_placeable_no_prior(self) -> None:
        """Continuation before placeable with no prior elements."""
        result = parse_simple_pattern(Cursor("\n    {$x}", 0))
        assert result is not None

    def test_placeable_then_continuation_then_placeable(self) -> None:
        """Placeable, continuation, then another placeable."""
        result = parse_simple_pattern(Cursor("{$a}\n    {$b}", 0))
        assert result is not None

    def test_text_then_continuation_at_end(self) -> None:
        """Text followed by trailing continuation."""
        result = parse_simple_pattern(Cursor("hello\n    ", 0))
        assert result is not None

    def test_continuation_at_end_no_prior(self) -> None:
        """Trailing continuation with no prior elements."""
        result = parse_simple_pattern(Cursor("\n    ", 0))
        assert result is not None

    def test_placeable_then_continuation_at_end(self) -> None:
        """Placeable then trailing continuation."""
        result = parse_simple_pattern(Cursor("{$x}\n    ", 0))
        assert result is not None

    def test_complex_continuation_before_placeable(self) -> None:
        """Multiple continuations before placeable."""
        text = "start\n    line1\n    line2\n    {$x}"
        result = parse_simple_pattern(Cursor(text, 0))
        assert result is not None

    def test_multiple_placeables_with_continuations(self) -> None:
        """Multiple placeables separated by continuations."""
        result = parse_simple_pattern(Cursor("{$a}\n    {$b}\n    {$c}", 0))
        assert result is not None

    def test_blank_continuation_lines(self) -> None:
        """Blank lines between continuations."""
        result = parse_simple_pattern(Cursor("text\n\n    continued", 0))
        assert result is not None

    def test_continuation_before_placeable_with_text(self) -> None:
        """Leading spaces then text then placeable."""
        cursor = Cursor("    continuation{$var}", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert len(result.value.elements) >= 2

    def test_placeable_continuation_text_placeable(self) -> None:
        """Placeable, continuation with text, then another placeable."""
        cursor = Cursor("{$x}\n    text{$y}", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert len(result.value.elements) >= 3

    def test_continuation_before_text_no_prior(self) -> None:
        """Leading spaces then text, no prior elements."""
        cursor = Cursor("    line1\n    line2", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None

    def test_finalize_continuation_no_prior(self) -> None:
        """Finalize accumulated text when no prior elements."""
        cursor = Cursor("    just continuation", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert len(result.value.elements) >= 1

    def test_finalize_continuation_last_is_placeable(self) -> None:
        """Finalize accumulated text when last element is placeable."""
        cursor = Cursor("{$x}\n    continuation", 0)
        result = parse_simple_pattern(cursor)
        assert result is not None
        assert len(result.value.elements) >= 2

    def test_direct_text_acc_finalization(self) -> None:
        """Extra spaces accumulated then stop character triggers finalization."""
        source = "a\n    b\n        }"
        result = parse_simple_pattern(Cursor(source, 0))
        assert result is not None
        assert len(result.value.elements) >= 1


class TestSimplePatternTextAccVariant:
    """Tests for text_acc in variant/message context (parse_ftl/parse_message)."""

    def test_extra_spaces_before_placeable(self) -> None:
        """Extra indentation before placeable in variant pattern."""
        ftl = """msg = { $n ->
    [one]
        first
            {$count}
    *[other] items
}"""
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

    def test_trailing_extra_spaces(self) -> None:
        """Trailing extra spaces at end of variant pattern."""
        ftl = """msg = { $n ->
    [one]
        item

    *[other] items
}"""
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

    def test_continuation_extra_spaces_then_placeable(self) -> None:
        """Extra spaces before placeable via parse_message."""
        source = """msg = {$n ->
    [one] Line1
        Line2
            {$var}
    *[other] Items
}"""
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())
        assert result is not None
        message = result.value
        assert isinstance(message, Message)
        assert message.value is not None

    def test_continuation_spaces_only_then_placeable(self) -> None:
        """Blank continuation creating extra_spaces, then text+placeable."""
        source = """msg = {$n ->
    [one] Start

            text {$x}
    *[other] End
}"""
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())
        assert result is not None
        assert isinstance(result.value, Message)

    def test_trailing_extra_spaces_via_message(self) -> None:
        """Variant ending with only accumulated extra spaces."""
        variant_one = (
            "[one] Text\n        MoreText\n                "
        )
        variant_other = "*[other] Items"
        source = (
            f"msg = {{$n ->\n    {variant_one}"
            f"\n    {variant_other}\n}}"
        )
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())
        assert result is not None
        assert isinstance(result.value, Message)
        assert result.value.value is not None

    def test_extra_spaces_at_close_brace(self) -> None:
        """Trailing extra spaces ending at close brace."""
        source = """msg = {$n ->
    *[other] Text

}"""
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())
        assert result is not None
        assert isinstance(result.value, Message)

    def test_complex_spacing_finalization(self) -> None:
        """Multiple continuations ending with accumulated spaces."""
        source = """msg = {$count ->
    [one] Line one
        Line two
            Line three

    *[other] Other
}"""
        cursor = Cursor(source, 0)
        result = parse_message(cursor, ParseContext())
        assert result is not None
        message = result.value
        assert isinstance(message, Message)
        assert message.value is not None
        placeable = message.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, SelectExpression)

    def test_variant_ending_with_continuation(self) -> None:
        """Variant ending with continuation extra spaces."""
        ftl = """msg = { $n ->
    [one] value
        text

    [two] other
    *[three] default
}"""
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

    def test_variant_extra_indent_then_next(self) -> None:
        """Variant with extra indent followed by next variant."""
        ftl = """msg = { $n ->
    [one]
        line1

    [two] line2
    *[other] other
}"""
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
