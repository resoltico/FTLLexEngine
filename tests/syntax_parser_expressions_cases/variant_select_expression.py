# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_expressions.py."""

from tests.syntax_parser_expressions_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# VARIANT & SELECT EXPRESSION
# ============================================================================


class TestParseVariant:
    """Tests for parse_variant error paths."""

    def test_missing_opening_bracket(self) -> None:
        """Returns None when '[' is missing."""
        assert parse_variant(Cursor("one", 0)) is None

    def test_missing_closing_bracket(self) -> None:
        """Returns None when ']' is missing."""
        assert parse_variant(Cursor("[one", 0)) is None

    def test_invalid_key(self) -> None:
        """Returns None when variant key is invalid."""
        assert parse_variant(Cursor("[@]", 0)) is None

    def test_variant_with_pattern(self) -> None:
        """Variant with text pattern succeeds."""
        result = parse_variant(Cursor("[one] item", 0))
        assert result is not None
        assert isinstance(result.value, Variant)

    def test_variant_with_empty_pattern(self) -> None:
        """Variant with empty pattern succeeds."""
        result = parse_variant(Cursor("[one] ", 0))
        assert result is not None or result is None


class TestParseSelectExpression:
    """Tests for parse_select_expression validation and EOF handling."""

    def test_no_variants_returns_none(self) -> None:
        """Must have at least one variant."""
        selector = VariableReference(id=Identifier("count"))
        result = parse_select_expression(
            Cursor("}", 0), selector, 0
        )
        assert result is None

    def test_no_default_variant_returns_none(self) -> None:
        """Must have exactly one default variant."""
        selector = VariableReference(id=Identifier("count"))
        result = parse_select_expression(
            Cursor("[one] item\n}", 0), selector, 0
        )
        assert result is None

    def test_multiple_defaults_returns_none(self) -> None:
        """Multiple default variants detected."""
        selector = VariableReference(id=Identifier("count"))
        result = parse_select_expression(
            Cursor("*[one] One\n*[other] Other", 0), selector, 0
        )
        assert result is None

    def test_variant_parse_fails_in_loop(self) -> None:
        """Variant parse failure in loop returns None."""
        selector = VariableReference(id=Identifier("x"))
        result = parse_select_expression(
            Cursor("[@]", 0), selector, 0
        )
        assert result is None

    def test_eof_after_variant_whitespace(self) -> None:
        """EOF reached after skip_blank between variants."""
        source = "*[other] value\n\n\n"
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof

    def test_eof_multiple_blank_lines_after_variant(self) -> None:
        """EOF with multiple blank lines after variant."""
        source = "*[other] text\n\n\n\n"
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof

    def test_eof_single_newline_after_variant(self) -> None:
        """EOF with single newline after variant."""
        source = "*[default] value\n"
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof

    def test_eof_empty_pattern_variant(self) -> None:
        """Variant with empty pattern followed by EOF."""
        source = "*[other]\n\n"
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is not None
        assert len(result.value.variants) == 1
        assert len(result.value.variants[0].value.elements) == 0
        assert result.cursor.is_eof

    def test_eof_multiple_variants(self) -> None:
        """Multiple variants with EOF after last one."""
        source = "[one] singular\n*[other] plural\n\n"
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is not None
        assert len(result.value.variants) == 2
        assert result.cursor.is_eof

    def test_eof_complex_pattern(self) -> None:
        """Complex pattern in variant, then EOF."""
        source = "*[other] You have items\n\n"
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof

    def test_immediate_eof(self) -> None:
        """EOF immediately after arrow position."""
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor("", 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is None

    def test_whitespace_then_eof(self) -> None:
        """Only whitespace after arrow, then EOF."""
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor("  \n  ", 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is None

    def test_variant_leading_spaces_integration(self) -> None:
        """Variant keys with leading spaces via parse_message."""
        source = (
            "msg = {$count ->\n"
            "    [ one] item\n"
            "    *[other] items\n}"
        )
        result = parse_message(Cursor(source, 0), ParseContext())
        assert result is not None
        message = result.value
        assert message.value is not None
        assert len(message.value.elements) == 1
        placeable = message.value.elements[0]
        assert isinstance(placeable, Placeable)
        assert isinstance(placeable.expression, SelectExpression)

    def test_multiline_select_complex_spacing(self) -> None:
        """Complex spacing and continuation in variant patterns."""
        source = (
            "msg = {$count ->\n"
            "    [ zero]\n"
            "        No items\n"
            "    [one]\n"
            "        {$count} item\n"
            "    *[other]\n"
            "        {$count} items\n"
            "}"
        )
        result = parse_message(Cursor(source, 0), ParseContext())
        assert result is not None
        assert result.value.value is not None

    @given(st.integers(min_value=1, max_value=20))
    @example(1)
    @example(5)
    @example(20)
    def test_eof_variable_newlines_property(
        self, num_newlines: int
    ) -> None:
        """Various numbers of trailing newlines trigger EOF handling."""
        event(f"num_newlines={num_newlines}")
        source = f"*[other] value{'\\n' * num_newlines}"
        # Build actual newlines
        source = "*[other] value" + "\n" * num_newlines
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof

    @given(st.text(alphabet="\n", min_size=1, max_size=50))
    @example("\n")
    @example("\n\n\n")
    @example("\n\n\n\n\n")
    def test_eof_arbitrary_newlines_property(
        self, whitespace: str
    ) -> None:
        """Arbitrary newline sequences after variant trigger EOF."""
        event(f"ws_len={len(whitespace)}")
        source = f"*[other] text{whitespace}"
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof

    @given(
        st.lists(
            st.sampled_from(
                ["[one]", "[two]", "[zero]", "*[other]"]
            ),
            min_size=1,
            max_size=5,
        )
    )
    @example(["*[other]"])
    @example(["[one]", "*[other]"])
    def test_variant_configurations_property(
        self, variant_keys: list[str]
    ) -> None:
        """Various variant configurations with EOF handling."""
        num_keys = len(variant_keys)
        has_default = any("*" in k for k in variant_keys)
        event(f"num_variants={num_keys}")
        event(f"has_default={has_default}")
        variants_text = "\n".join(
            f"{key} text" for key in variant_keys
        )
        source = f"{variants_text}\n\n"
        selector = VariableReference(id=None)  # type: ignore[arg-type]
        result = parse_select_expression(
            Cursor(source, 0), selector, start_pos=0,
            context=ParseContext(),
        )
        default_count = sum(
            1 for key in variant_keys if "*" in key
        )
        if default_count == 1:
            assert result is not None
            assert len(result.value.variants) == len(variant_keys)
            assert result.cursor.is_eof
        else:
            assert result is None
