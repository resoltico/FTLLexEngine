# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_patterns.py."""

from tests.syntax_parser_patterns_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# MULTILINE BLANK LINES
# ============================================================================


class TestMultilineBlankLines:
    """Tests for blank line handling in multiline patterns."""

    def test_single_blank_line_before_content(self) -> None:
        """Single blank line before content strips indentation."""
        ftl = "msg =\n\n    value"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.value.elements[0].value == "value"  # type: ignore[union-attr]

    def test_multiple_blank_lines_before_content(self) -> None:
        """Multiple blank lines before content strips indentation."""
        ftl = "msg =\n\n\n\n    value"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value.elements[0].value == "value"  # type: ignore[union-attr]

    def test_with_subsequent_lines(self) -> None:
        """Blank line before content with subsequent lines."""
        ftl = "msg =\n\n    first\n    second"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert text == "first\nsecond"

    def test_with_extra_indentation(self) -> None:
        """Blank line before content preserves extra indentation."""
        ftl = "msg =\n\n    first\n        second"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert text == "first\n    second"

    def test_bundle_format(self) -> None:
        """FluentBundle correctly formats with blank line before content."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg =\n\n    Hello World")
        result, errors = bundle.format_pattern("msg")
        assert not errors
        assert result == "Hello World"

    def test_with_placeable(self) -> None:
        """Blank line before content with placeable."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg =\n\n    Hello { $name }")
        result, errors = bundle.format_pattern(
            "msg", {"name": "Alice"}
        )
        assert not errors
        assert "Hello" in result
        assert "Alice" in result

    def test_blank_line_at_end(self) -> None:
        """Blank line at end of pattern handled correctly."""
        ftl = "msg =\n    first\n\n    second"
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

    def test_mixed_blank_lines(self) -> None:
        """Blank lines at various positions."""
        ftl = "msg =\n\n    first\n\n    second\n\n    third"
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
        assert "third" in text

    def test_term_blank_line_before_content(self) -> None:
        """Term with blank line before content."""
        ftl = "-brand =\n\n    Firefox"
        resource = parse_ftl(ftl)
        term = resource.entries[0]
        assert isinstance(term, Term)
        text = "".join(
            e.value
            for e in term.value.elements
            if isinstance(e, TextElement)
        )
        assert text == "Firefox"

    def test_multiple_blank_lines_in_continuation(self) -> None:
        """Multiple consecutive blank lines within continuation."""
        ftl = "msg =\n    first\n\n\n    second"
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

    def test_term_blank_lines_in_continuation(self) -> None:
        """Term with blank lines in continuation."""
        ftl = "-term =\n\n\n    content"
        resource = parse_ftl(ftl)
        term = resource.entries[0]
        assert isinstance(term, Term)
        text = "".join(
            e.value
            for e in term.value.elements
            if isinstance(e, TextElement)
        )
        assert text == "content"

    def test_placeable_after_blanks_with_extra_indent(self) -> None:
        """Placeable after blank lines with extra indentation."""
        ftl = "msg =\n    text\n\n\n        {$var}"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        has_text = any(
            isinstance(e, TextElement) for e in msg.value.elements
        )
        has_placeable = any(
            isinstance(e, Placeable) for e in msg.value.elements
        )
        assert has_text
        assert has_placeable

    def test_only_extra_spaces_no_content(self) -> None:
        """Continuation with only extra spaces, no actual content."""
        ftl = "msg =\n    text\n\n    more"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert "text" in text
        assert "more" in text

    def test_complex_mixed_pattern(self) -> None:
        """Complex pattern mixing all edge cases."""
        ftl = "msg =\n\n\n    first\n\n        {$var}\n\n\n        last"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        has_text = any(
            isinstance(e, TextElement) for e in msg.value.elements
        )
        has_placeable = any(
            isinstance(e, Placeable) for e in msg.value.elements
        )
        assert has_text
        assert has_placeable

    def test_original_regression(self) -> None:
        """FTL-GRAMMAR-001: blank line sets common_indent to 0."""
        ftl = "msg =\n\n    value"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        element = msg.value.elements[0]  # type: ignore[union-attr]
        assert isinstance(element, TextElement)
        assert element.value == "value", (
            f"common_indent bug: expected 'value', got "
            f"'{element.value}'"
        )

    def test_regression_variant_simple_pattern(self) -> None:
        """Regression: parse_simple_pattern blank line indent."""
        ftl = """msg = { $n ->
    [one]

        item
    *[other] items
}"""
        bundle = FluentBundle("en_US")
        bundle.add_resource(ftl)
        result, errors = bundle.format_pattern("msg", {"n": 1})
        assert not errors
        assert "item" in result
        assert "        item" not in result

    @pytest.mark.parametrize(
        ("ftl", "expected"),
        [
            ("msg =\n\n    x", "x"),
            ("msg =\n\n\n    x", "x"),
            ("msg =\n\n\n\n\n    x", "x"),
            ("msg =\n\n        x", "x"),
            ("msg =\n\n            x", "x"),
        ],
    )
    def test_parametrized_blank_line_scenarios(
        self, ftl: str, expected: str
    ) -> None:
        """Various blank line scenarios all strip indentation."""
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert text == expected
