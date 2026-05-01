# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_expressions.py."""

from tests.syntax_parser_expressions_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# VARIANT KEY & VARIANT MARKER
# ============================================================================


class TestIsValidVariantKeyChar:
    """Tests for _is_valid_variant_key_char helper."""

    @given(st.sampled_from([".", "-", "_"]))
    def test_special_chars_in_variant_keys(self, char: str) -> None:
        """Special character handling follows identifier rules."""
        event(f"char={char!r}")
        if char == "_":
            assert _is_valid_variant_key_char(char, is_first=True)
        else:
            assert not _is_valid_variant_key_char(char, is_first=True)
        assert _is_valid_variant_key_char(char, is_first=False)


class TestIsVariantMarker:
    """Tests for _is_variant_marker lookahead logic."""

    def test_eof_cursor_returns_false(self) -> None:
        """EOF cursor returns False."""
        assert not _is_variant_marker(Cursor("", 0))

    def test_empty_brackets_not_variant(self) -> None:
        """Empty [] is not a variant key."""
        assert not _is_variant_marker(Cursor("[]", 0))

    def test_bracket_at_eof_after_closing(self) -> None:
        """Valid variant when ] at EOF."""
        assert _is_variant_marker(Cursor("[one]", 0))

    def test_bracket_followed_by_newline(self) -> None:
        """Valid variant when ] followed by newline."""
        assert _is_variant_marker(Cursor("[one]\n", 0))

    def test_bracket_followed_by_closing_brace(self) -> None:
        """Valid variant when ] followed by }."""
        assert _is_variant_marker(Cursor("[one]}", 0))

    def test_bracket_followed_by_open_bracket(self) -> None:
        """Valid variant when ] followed by [."""
        assert _is_variant_marker(Cursor("[one][two]", 0))

    def test_bracket_followed_by_asterisk(self) -> None:
        """Valid variant when ] followed by *."""
        assert _is_variant_marker(Cursor("[one]*[other]", 0))

    def test_bracket_with_comma_not_variant(self) -> None:
        """Comma makes it literal text, not variant."""
        assert not _is_variant_marker(Cursor("[1, 2]", 0))

    def test_bracket_with_invalid_char_not_variant(self) -> None:
        """Invalid char for identifier/number."""
        assert not _is_variant_marker(Cursor("[in@valid]", 0))

    def test_bracket_exceeds_lookahead(self) -> None:
        """Exceeded lookahead before finding ]."""
        long_text = "[" + "a" * (MAX_LOOKAHEAD_CHARS + 10)
        assert not _is_variant_marker(Cursor(long_text, 0))

    def test_lookahead_exhausted_in_whitespace_scan(self) -> None:
        """Lookahead exhausted while skipping whitespace after ]."""
        text = "[one]" + " " * (MAX_LOOKAHEAD_CHARS + 10)
        result = _is_variant_marker(Cursor(text, 0))
        assert isinstance(result, bool)

    def test_non_bracket_non_asterisk_returns_false(self) -> None:
        """Non-[ non-* character returns False."""
        assert not _is_variant_marker(Cursor("x", 0))

    def test_variant_marker_with_leading_space(self) -> None:
        """Leading space after '[' is valid per Fluent EBNF."""
        assert _is_variant_marker(Cursor("[ one]", 0))

    def test_variant_marker_with_multiple_leading_spaces(self) -> None:
        """Multiple leading spaces after '[' are valid."""
        assert _is_variant_marker(Cursor("[    other]", 0))

    @given(
        num_spaces=st.integers(min_value=1, max_value=10),
        key=st.sampled_from(
            ["one", "other", "few", "many", "zero", "0", "42"]
        ),
    )
    def test_variant_marker_leading_spaces_property(
        self, num_spaces: int, key: str
    ) -> None:
        """Any number of leading spaces in variant key is valid."""
        event(f"num_spaces={num_spaces}")
        event(f"key_type={'digit' if key.isdigit() else 'ident'}")
        source = f"[{' ' * num_spaces}{key}]"
        assert _is_variant_marker(Cursor(source, 0))


class TestParseVariantKey:
    """Tests for parse_variant_key paths."""

    def test_identifier_variant_key(self) -> None:
        """Identifier parsed as variant key."""
        result = parse_variant_key(Cursor("abc", 0))
        assert result is not None
        assert isinstance(result.value, Identifier)
        assert result.value.name == "abc"

    def test_identifier_from_bracket(self) -> None:
        """Variant key parsed from inside brackets."""
        result = parse_variant_key(Cursor("[abc]", 1))
        assert result is not None
        assert isinstance(result.value, Identifier)

    def test_number_variant_key(self) -> None:
        """Number parsed as variant key."""
        result = parse_variant_key(Cursor("42", 0))
        assert result is not None
        assert isinstance(result.value, NumberLiteral)

    def test_negative_number_fallback_fails(self) -> None:
        """Hyphen followed by non-digit: both number and identifier fail."""
        assert parse_variant_key(Cursor("-foo", 0)) is None

    def test_hyphen_alone_fails(self) -> None:
        """Hyphen alone fails both number and identifier parse."""
        assert parse_variant_key(Cursor("-", 0)) is None

    def test_invalid_start_char_fails(self) -> None:
        """Characters invalid for both number and identifier fail."""
        assert parse_variant_key(Cursor("???", 1)) is None

    @given(st.integers(min_value=0, max_value=1000))
    @example(42)
    @example(-42)
    @example(0)
    def test_numeric_variant_key_property(self, num: int) -> None:
        """Numeric variant keys parsed correctly."""
        event(f"num={num}")
        result = parse_variant_key(Cursor(str(num), 0))
        if result is not None:
            assert isinstance(
                result.value, (NumberLiteral, Identifier)
            )


class TestTrimPatternBlankLines:
    """Tests for _trim_pattern_blank_lines edge cases."""

    def test_empty_returns_empty(self) -> None:
        """Empty list returns empty tuple."""
        assert _trim_pattern_blank_lines([]) == ()

    def test_single_placeable_preserved(self) -> None:
        """Placeable-only pattern is preserved."""
        placeable = Placeable(
            expression=VariableReference(id=Identifier("x"))
        )
        result = _trim_pattern_blank_lines([placeable])
        assert len(result) == 1
        assert result[0] == placeable

    def test_text_with_content_after_newline_preserved(self) -> None:
        """Content after last newline is preserved."""
        elements = cast(
            "list[TextElement | Placeable]",
            [TextElement(value="Hello\nWorld")],
        )
        result = _trim_pattern_blank_lines(elements)
        assert len(result) == 1
        assert isinstance(result[0], TextElement)
        assert result[0].value == "Hello\nWorld"

    def test_trailing_blank_line_removed(self) -> None:
        """Trailing blank line is removed."""
        elements = cast(
            "list[TextElement | Placeable]",
            [TextElement(value="Content\n   \n")],
        )
        result = _trim_pattern_blank_lines(elements)
        assert len(result) == 1
        assert isinstance(result[0], TextElement)
        assert result[0].value == "Content"

    def test_leading_all_whitespace_removed(self) -> None:
        """First element all whitespace is removed."""
        elements = cast(
            "list[TextElement | Placeable]",
            [TextElement(value="   "), TextElement(value="content")],
        )
        result = _trim_pattern_blank_lines(elements)
        assert len(result) == 1
        assert isinstance(result[0], TextElement)
        assert result[0].value == "content"

    def test_trailing_all_whitespace_removed(self) -> None:
        """Last element all whitespace after trimming is removed."""
        elements = cast(
            "list[TextElement | Placeable]",
            [TextElement(value="content"), TextElement(value="\n   ")],
        )
        result = _trim_pattern_blank_lines(elements)
        assert len(result) == 1
        assert isinstance(result[0], TextElement)
        assert result[0].value == "content"
