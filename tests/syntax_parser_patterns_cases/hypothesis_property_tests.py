# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_patterns.py."""

from tests.syntax_parser_patterns_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# HYPOTHESIS PROPERTY TESTS
# ============================================================================


class TestPatternsHypothesis:
    """Property-based tests for pattern and whitespace handling."""

    @given(st.integers(min_value=0, max_value=100))
    def test_skip_blank_inline_various_counts(
        self, space_count: int
    ) -> None:
        """Any number of spaces skipped by skip_blank_inline."""
        event(f"space_count={space_count}")
        source = " " * space_count + "hello"
        cursor = Cursor(source=source, pos=0)
        assert skip_blank_inline(cursor).pos == space_count

    @given(st.integers(min_value=1, max_value=20))
    def test_is_indented_continuation_various(
        self, indent_count: int
    ) -> None:
        """Any indentation level detected as continuation."""
        event(f"indent_count={indent_count}")
        source = "\n" + " " * indent_count + "text"
        cursor = Cursor(source=source, pos=0)
        assert is_indented_continuation(cursor) is True

    @given(
        extra_indent=st.integers(min_value=1, max_value=12),
        base_indent=st.integers(min_value=4, max_value=8),
    )
    def test_extra_spaces_before_placeable(
        self, extra_indent: int, base_indent: int
    ) -> None:
        """Extra indentation before placeable is preserved."""
        boundary = "deep" if extra_indent > 8 else "shallow"
        event(f"boundary={boundary}")
        event(f"base_indent={base_indent}")
        base = " " * base_indent
        extra = " " * (base_indent + extra_indent)
        ftl = f"msg =\n{base}text\n{extra}{{$var}}"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        elements = msg.value.elements
        assert len(elements) >= 2
        assert isinstance(elements[-1], Placeable)

    @given(trailing_spaces=st.integers(min_value=1, max_value=20))
    def test_trailing_spaces_handled(
        self, trailing_spaces: int
    ) -> None:
        """Patterns with trailing spaces parse successfully."""
        event(f"trailing_spaces={trailing_spaces}")
        spaces = " " * trailing_spaces
        ftl = f"msg =\n    text\n{spaces}"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None

    @given(
        base_indent=st.integers(min_value=4, max_value=8),
        extra_indent=st.integers(min_value=1, max_value=8),
    )
    def test_extra_indent_handling(
        self, base_indent: int, extra_indent: int
    ) -> None:
        """Extra indentation correctly accumulated."""
        event(f"extra_indent={extra_indent}")
        event(f"base_indent={base_indent}")
        base = " " * base_indent
        extra = " " * (base_indent + extra_indent)
        ftl = f"msg =\n{base}first\n{extra}second"
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

    @given(
        num_lines=st.integers(min_value=2, max_value=5),
        indent_base=st.integers(min_value=4, max_value=8),
    )
    def test_multiline_extra_indent_accumulation(
        self, num_lines: int, indent_base: int
    ) -> None:
        """Multiple lines with extra indent accumulate correctly."""
        event(f"num_lines={num_lines}")
        event(f"indent_base={indent_base}")
        lines_ftl = [f"line{i}" for i in range(num_lines)]
        base = " " * indent_base
        ftl_lines = ["msg ="]
        ftl_lines.append(f"{base}{lines_ftl[0]}")
        for i in range(1, num_lines):
            extra = " " * (i % 3)
            ftl_lines.append(f"{base}{extra}{lines_ftl[i]}")
        ftl = "\n".join(ftl_lines)
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        for line_text in lines_ftl:
            assert line_text in text

    @given(
        extra_indent=st.integers(min_value=1, max_value=8),
        base_indent=st.integers(min_value=4, max_value=8),
    )
    def test_term_extra_indent(
        self, extra_indent: int, base_indent: int
    ) -> None:
        """Terms handle extra indentation like messages."""
        event(f"extra_indent={extra_indent}")
        event(f"base_indent={base_indent}")
        base = " " * base_indent
        extra = " " * (base_indent + extra_indent)
        ftl = f"-term =\n{base}first\n{extra}second"
        resource = parse_ftl(ftl)
        term = resource.entries[0]
        assert isinstance(term, Term)
        text = "".join(
            e.value
            for e in term.value.elements
            if isinstance(e, TextElement)
        )
        assert "first" in text
        assert "second" in text

    @given(
        num_blank_lines=st.integers(min_value=1, max_value=10),
        indent_size=st.integers(min_value=1, max_value=8),
    )
    def test_blank_lines_and_indentation(
        self, num_blank_lines: int, indent_size: int
    ) -> None:
        """Any blank lines before content strip indent."""
        event(f"num_blank_lines={num_blank_lines}")
        event(f"indent_size={indent_size}")
        blank_lines = "\n" * num_blank_lines
        indent = " " * indent_size
        ftl = f"msg ={blank_lines}{indent}content"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert msg.value.elements[0].value == "content"  # type: ignore[union-attr]

    @given(
        content=st.text(
            min_size=1,
            max_size=50,
            alphabet="abcdefghijklmnopqrstuvwxyz",
        )
    )
    def test_content_preserved_after_blank_lines(
        self, content: str
    ) -> None:
        """Content after blank lines is preserved exactly."""
        event(f"content_length={len(content)}")
        ftl = f"msg =\n\n    {content}"
        resource = parse_ftl(ftl)
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        text = "".join(
            e.value
            for e in msg.value.elements  # type: ignore[union-attr]
            if isinstance(e, TextElement)
        )
        assert text == content

    @example("Hello")
    @example("Line1\nLine2")
    @given(st.text(min_size=1, max_size=50))
    def test_parse_simple_pattern_property(
        self, text: str
    ) -> None:
        """parse_simple_pattern handles arbitrary text."""
        if not text or text[0] in ("}", "[", "*"):
            return
        has_newline = "\n" in text
        event(f"has_newline={has_newline}")
        cursor = Cursor(text, 0)
        result = parse_simple_pattern(cursor)
        outcome = "parsed" if result else "none"
        event(f"outcome={outcome}")
        assert result is None or isinstance(result.value, Pattern)

    @example("value")
    @example("{$x}")
    @given(st.text(min_size=1, max_size=50))
    def test_parse_pattern_property(self, text: str) -> None:
        """parse_pattern handles arbitrary text."""
        has_placeable = "{" in text
        event(f"has_placeable={has_placeable}")
        cursor = Cursor(text, 0)
        result = parse_pattern(cursor)
        outcome = "parsed" if result else "none"
        event(f"outcome={outcome}")
        assert result is None or isinstance(result.value, Pattern)
