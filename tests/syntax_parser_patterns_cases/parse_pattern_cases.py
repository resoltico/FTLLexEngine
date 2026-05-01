# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_patterns.py."""

from tests.syntax_parser_patterns_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PARSE_PATTERN
# ============================================================================


class TestParsePatternBasic:
    """Tests for parse_pattern basic behavior."""

    def test_no_text_before_newline(self) -> None:
        """Empty pattern at newline (cursor.pos == text_start)."""
        result = parse_pattern(Cursor("\n", 0))
        assert result is not None
        assert len(result.value.elements) == 0

    def test_placeable_then_newline(self) -> None:
        """Placeable immediately followed by newline."""
        result = parse_pattern(Cursor("{$var}\n", 0))
        assert result is not None
        assert len(result.value.elements) == 1

    def test_placeable_parse_fails(self) -> None:
        """Returns None when parse_placeable fails."""
        cursor = Cursor("Text {invalid", 0)
        with patch(
            "ftllexengine.syntax.parser.expressions.parse_placeable",
            return_value=None,
        ):
            result = parse_pattern(cursor)
        assert result is None

    def test_stop_char_not_placeable(self) -> None:
        """Pattern with stop character that's not '{'."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Value\n")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert "Value" in result

    def test_empty_pattern_with_attribute(self) -> None:
        """Empty pattern followed by attribute."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg =\n    .attr = Attribute\n")
        result, errors = bundle.format_pattern("msg", attribute="attr")
        assert not errors
        assert "Attribute" in result

    def test_pattern_at_eof(self) -> None:
        """Pattern at EOF without trailing newline."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = Value at EOF")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert "Value at EOF" in result


class TestParsePatternTopLevelDelimiters:
    """Tests for top-level pattern delimiter handling.

    In top-level patterns (not inside select expressions), characters
    like }, [, * are literal text, not structural delimiters.
    """

    def test_close_brace_is_text(self) -> None:
        """} is literal text in top-level patterns."""
        result = parse_pattern(Cursor("}text", 0))
        assert result is not None
        assert len(result.value.elements) == 1
        assert result.value.elements[0].value == "}text"  # type: ignore[union-attr]

    def test_bracket_is_text(self) -> None:
        """[ is literal text in top-level patterns."""
        result = parse_pattern(Cursor("[text", 0))
        assert result is not None
        assert len(result.value.elements) == 1
        assert result.value.elements[0].value == "[text"  # type: ignore[union-attr]

    def test_asterisk_is_text(self) -> None:
        """* is literal text in top-level patterns."""
        result = parse_pattern(Cursor("*text", 0))
        assert result is not None
        assert len(result.value.elements) == 1
        assert result.value.elements[0].value == "*text"  # type: ignore[union-attr]

    def test_special_char_sequences(self) -> None:
        """Multiple delimiters are all literal text."""
        result = parse_pattern(Cursor("}}]]", 0))
        assert result is not None
        assert len(result.value.elements) == 1
        assert result.value.elements[0].value == "}}]]"  # type: ignore[union-attr]

    def test_stop_char_advances_cursor(self) -> None:
        """] at position 0 advances cursor to prevent infinite loop."""
        result = parse_pattern(Cursor("]", 0))
        assert result is not None
        assert result.cursor.pos >= 1 or result.cursor.is_eof

    def test_includes_special_chars_combined(self) -> None:
        """All delimiter characters are literal in top-level patterns."""
        for delimiter in ["}", "[", "*"]:
            result = parse_pattern(Cursor(f"text{delimiter}more", 0))
            assert result is not None
            assert len(result.value.elements) == 1
            expected = f"text{delimiter}more"
            assert result.value.elements[0].value == expected  # type: ignore[union-attr]


class TestParsePatternContinuation:
    """Tests for continuation handling in parse_pattern."""

    def test_crlf_multiline(self) -> None:
        """CRLF in multiline continuation."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = First line\r\n    Second line")
        result, _ = bundle.format_pattern("msg")
        assert "First line" in result
        assert "Second line" in result

    def test_cr_only_continuation(self) -> None:
        """CR (old Mac style) at continuation."""
        cursor = Cursor("msg = First\r    Second", 6)
        result = parse_pattern(cursor)
        assert result is not None
        assert len(result.value.elements) > 0

    def test_continuation_after_placeable(self) -> None:
        """Multiline continuation after placeable adds space element."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg = {NUMBER(5)}\n    continued text")
        result, _ = bundle.format_pattern("msg")
        assert "5" in result
        assert "continued text" in result

    def test_extra_spaces_before_placeable(self) -> None:
        """Extra indentation before placeable in top-level pattern."""
        ftl = "msg =\n    first\n        {$var}"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        has_placeable = any(
            isinstance(e, Placeable) for e in msg.value.elements
        )
        assert has_placeable

    def test_trailing_extra_spaces(self) -> None:
        """Trailing extra spaces at end of top-level pattern."""
        ftl = "msg =\n    first\n        "
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.value.elements) >= 1

    def test_extra_indent_preserved(self) -> None:
        """Extra indentation beyond common indent is preserved."""
        ftl = "msg =\n    first\n        second"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert "first" in text
        assert "second" in text

    def test_varying_extra_indent(self) -> None:
        """Multiple lines with varying extra indentation."""
        ftl = "msg =\n    base\n        extra4\n            extra8"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.value.elements) >= 1

    def test_accumulated_spaces_prepended(self) -> None:
        """Accumulated extra spaces prepended to following text."""
        ftl = "msg =\n    first\n        more text"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert "first" in text
        assert "more text" in text

    def test_multiple_continuations_varying_indent(self) -> None:
        """Multiple continuation lines with varying extra indentation."""
        ftl = "msg =\n    l1\n        l2\n            l3\n        l4"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        for line in ["l1", "l2", "l3", "l4"]:
            assert line in text

    def test_continuation_new_element_no_prior(self) -> None:
        """Accumulated continuation before text, no prior elements."""
        result = parse_pattern(Cursor("    continuation\n    more", 0))
        assert result is not None

    def test_continuation_new_element_last_placeable(self) -> None:
        """Accumulated continuation merged after placeable."""
        result = parse_pattern(Cursor("{$x}\n    text more", 0))
        assert result is not None

    def test_finalize_continuation_no_prior(self) -> None:
        """Finalize accumulated text when no prior elements."""
        result = parse_pattern(Cursor("    only continuation", 0))
        assert result is not None

    def test_finalize_continuation_last_placeable(self) -> None:
        """Finalize accumulated text when last is placeable."""
        result = parse_pattern(Cursor("{$x}\n    final", 0))
        assert result is not None

    def test_empty_pattern_continuation(self) -> None:
        """Continuation with empty elements list (newline at pos 0)."""
        result = parse_pattern(Cursor("\n    text", 0))
        assert result is not None

    def test_term_extra_indent_before_placeable(self) -> None:
        """Term with extra indentation before placeable."""
        ftl = "-term =\n    first\n        {$var}"
        resource = parse_ftl(ftl)
        term = resource.entries[0]
        assert isinstance(term, Term)
        assert term.value is not None
        has_placeable = any(
            isinstance(e, Placeable) for e in term.value.elements
        )
        assert has_placeable
