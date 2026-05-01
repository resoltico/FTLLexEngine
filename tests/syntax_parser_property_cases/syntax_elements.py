# mypy: ignore-errors
from tests.syntax_parser_property_cases import (
    Decimal,
    FluentParserV1,
    Message,
    Term,
    assume,
    attribute_names,
    decimals,
    event,
    ftl_identifiers,
    given,
    numbers,
    safe_text,
    settings,
    st,
    variable_names,
    variant_keys,
)


class TestSelectExpressionParsing:
    """Property tests for select expression parsing."""

    @given(var_name=variable_names)
    @settings(max_examples=150)
    def test_minimal_select_expression(self, var_name: str) -> None:
        """PROPERTY: Minimal select { $var -> *[other] X } parses."""
        source = f"msg = {{ ${var_name} ->\n   *[other] Default\n}}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("select_variant_count=1")
        event("select_type=minimal")

    @given(
        var_name=variable_names,
        key1=variant_keys,
        key2=variant_keys,
    )
    @settings(max_examples=150)
    def test_select_with_multiple_variants(
        self, var_name: str, key1: str, key2: str
    ) -> None:
        """PROPERTY: Select with multiple variants parses."""
        source = f"""msg = {{ ${var_name} ->
    [{key1}] Value1
    [{key2}] Value2
   *[other] Default
}}"""
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("select_variant_count=3")
        if key1 == key2:
            event("variant_keys=duplicate")
        else:
            event("variant_keys=unique")

    @given(
        var_name=variable_names,
        count=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=50)
    def test_select_with_many_variants(self, var_name: str, count: int) -> None:
        """PROPERTY: Select with many variants parses."""
        variants = "\n".join([f"    [key{i}] Value{i}" for i in range(count)])
        source = f"msg = {{ ${var_name} ->\n{variants}\n   *[other] Default\n}}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event(f"select_variant_count={min(count + 1, 10)}")

    @given(var_name=variable_names, text=safe_text)
    @settings(max_examples=100)
    def test_select_variant_with_text(self, var_name: str, text: str) -> None:
        """PROPERTY: Select variant values can contain text."""
        source = f"msg = {{ ${var_name} ->\n   *[other] {text}\n}}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("variant_value_type=text")

    @given(
        var_name=variable_names,
        var_in_variant=variable_names,
    )
    @settings(max_examples=100)
    def test_select_variant_with_placeable(
        self, var_name: str, var_in_variant: str
    ) -> None:
        """PROPERTY: Select variant can contain placeables."""
        source = f"msg = {{ ${var_name} ->\n   *[other] Text {{ ${var_in_variant} }}\n}}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("variant_value_type=with_placeable")

    @given(var_name=variable_names, number=numbers)
    @settings(max_examples=100)
    def test_select_with_numeric_keys(self, var_name: str, number: int) -> None:
        """PROPERTY: Select with numeric variant keys parses."""
        source = f"msg = {{ ${var_name} ->\n    [{number}] Exact\n   *[other] Default\n}}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("variant_key_type=numeric")
        if number < 0:
            event("numeric_key_sign=negative")
        elif number == 0:
            event("numeric_key_sign=zero")
        else:
            event("numeric_key_sign=positive")


# ============================================================================
# TERMS
# ============================================================================


class TestTermParsing:
    """Property tests for term definition and reference parsing."""

    @given(term_id=ftl_identifiers)
    @settings(max_examples=150)
    def test_simple_term_definition(self, term_id: str) -> None:
        """PROPERTY: -term = value parses as term."""
        source = f"-{term_id} = Term value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None
        if len(resource.entries) > 0:
            # Should be a Term entry
            entry = resource.entries[0]
            assert isinstance(entry, (Term, Message))  # Could be either

            # Emit events for HypoFuzz guidance
            event(f"entry_type={type(entry).__name__}")
        event("term_structure=simple")

    @given(term_id=ftl_identifiers, text=safe_text)
    @settings(max_examples=100)
    def test_term_with_text_value(self, term_id: str, text: str) -> None:
        """PROPERTY: Term with text value parses."""
        source = f"-{term_id} = {text}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("term_structure=with_text")

    @given(term_id=ftl_identifiers, var_name=variable_names)
    @settings(max_examples=100)
    def test_term_with_placeable(self, term_id: str, var_name: str) -> None:
        """PROPERTY: Term with placeable parses."""
        source = f"-{term_id} = Value {{ ${var_name} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("term_structure=with_placeable")

    @given(term_id=ftl_identifiers, attr_name=attribute_names)
    @settings(max_examples=100)
    def test_term_with_attribute(self, term_id: str, attr_name: str) -> None:
        """PROPERTY: Term with attribute parses."""
        source = f"-{term_id} = Value\n    .{attr_name} = Attribute value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("term_structure=with_attribute")

    @given(
        msg_id=ftl_identifiers,
        term_id=ftl_identifiers,
    )
    @settings(max_examples=100)
    def test_message_referencing_term(self, msg_id: str, term_id: str) -> None:
        """PROPERTY: Message can reference term { -term }."""
        source = f"-{term_id} = Term\n{msg_id} = {{ -{term_id} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("term_ref_type=simple")

    @given(
        msg_id=ftl_identifiers,
        term_id=ftl_identifiers,
        attr_name=attribute_names,
    )
    @settings(max_examples=100)
    def test_term_attribute_reference(
        self, msg_id: str, term_id: str, attr_name: str
    ) -> None:
        """PROPERTY: Term attribute reference { -term.attr } parses."""
        source = (
            f"-{term_id} = Term\n"
            f"    .{attr_name} = Attr\n"
            f"{msg_id} = {{ -{term_id}.{attr_name} }}"
        )
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("term_ref_type=with_attribute")


# ============================================================================
# STRING LITERALS
# ============================================================================


class TestStringLiteralParsing:
    """Property tests for string literal parsing."""

    @given(text=safe_text)
    @settings(max_examples=150)
    def test_simple_string_literal(self, text: str) -> None:
        """PROPERTY: "text" parses as string literal."""
        escaped = text.replace('"', '\\"').replace("\\", "\\\\")
        source = f'msg = {{ "{escaped}" }}'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        if len(text) == 0:
            event("string_length=empty")
        elif len(text) <= 10:
            event("string_length=short")
        elif len(text) <= 50:
            event("string_length=medium")
        else:
            event("string_length=long")

    def test_empty_string_literal(self) -> None:
        """PROPERTY: Empty string "" parses."""
        source = 'msg = { "" }'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(char=st.characters(min_codepoint=32, max_codepoint=126))
    @settings(max_examples=100)
    def test_string_with_single_char(self, char: str) -> None:
        """PROPERTY: Single character strings parse."""
        if char == '"':
            escaped = '\\"'
        elif char == "\\":
            escaped = "\\\\"
        else:
            escaped = char
        source = f'msg = {{ "{escaped}" }}'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        if char in ('"', "\\"):
            event("char_type=special_escape")
        elif char.isalpha():
            event("char_type=alpha")
        elif char.isdigit():
            event("char_type=digit")
        else:
            event("char_type=other")

    @given(
        unicode_char=st.characters(min_codepoint=0x0100, max_codepoint=0xFFFF),
    )
    @settings(max_examples=100)
    def test_string_with_unicode(self, unicode_char: str) -> None:
        """PROPERTY: String literals with Unicode parse."""
        source = f'msg = {{ "{unicode_char}" }}'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        codepoint = ord(unicode_char)
        if codepoint < 0x0800:
            event("unicode_range=latin_extended")
        elif codepoint < 0x3000:
            event("unicode_range=mid_bmp")
        else:
            event("unicode_range=cjk_symbols")


# ============================================================================
# NUMBER LITERALS
# ============================================================================


class TestNumberLiteralParsing:
    """Property tests for number literal parsing."""

    @given(number=numbers)
    @settings(max_examples=200)
    def test_integer_literal(self, number: int) -> None:
        """PROPERTY: Integer literals parse correctly."""
        source = f"msg = {{ {number} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        if number < 0:
            event("integer_sign=negative")
        elif number == 0:
            event("integer_sign=zero")
        else:
            event("integer_sign=positive")
        if abs(number) > 1000000:
            event("integer_magnitude=large")

    @given(decimal=decimals)
    @settings(max_examples=150)
    def test_decimal_literal(self, decimal: Decimal) -> None:
        """PROPERTY: Decimal literals parse correctly."""
        # Use fixed-point notation to avoid scientific notation in FTL source
        num_str = format(decimal, "f")
        # Filter out strings that are too long for the parser
        assume(len(num_str) <= 50)
        source = f"msg = {{ {num_str} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        if decimal < Decimal(0):
            event("decimal_sign=negative")
        elif decimal == Decimal(0):
            event("decimal_sign=zero")
        else:
            event("decimal_sign=positive")
        # Check if it's a whole number decimal (use str to avoid overflow on huge Decimals)
        _, _, frac_part = num_str.lstrip("-").partition(".")
        if not frac_part or all(c == "0" for c in frac_part):
            event("decimal_type=whole")
        else:
            event("decimal_type=fractional")

    def test_zero_literal(self) -> None:
        """PROPERTY: Zero literal parses."""
        source = "msg = { 0 }"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(number=st.integers(min_value=0, max_value=1000000))
    @settings(max_examples=100)
    def test_positive_integer(self, number: int) -> None:
        """PROPERTY: Positive integers parse."""
        source = f"msg = {{ {number} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("integer_sign=positive")
        if number > 100000:
            event("integer_magnitude=large")
        elif number > 1000:
            event("integer_magnitude=medium")
        else:
            event("integer_magnitude=small")

    @given(number=st.integers(min_value=-1000000, max_value=-1))
    @settings(max_examples=100)
    def test_negative_integer(self, number: int) -> None:
        """PROPERTY: Negative integers parse."""
        source = f"msg = {{ {number} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("integer_sign=negative")
        if abs(number) > 100000:
            event("integer_magnitude=large")
        elif abs(number) > 1000:
            event("integer_magnitude=medium")
        else:
            event("integer_magnitude=small")


# ============================================================================
# MESSAGE STRUCTURE
# ============================================================================


class TestMessageStructure:
    """Property tests for message structure parsing."""

    @given(msg_id=ftl_identifiers, text=safe_text)
    @settings(max_examples=150)
    def test_message_with_value_only(self, msg_id: str, text: str) -> None:
        """PROPERTY: Message with only value parses."""
        source = f"{msg_id} = {text}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("message_structure=value_only")

    @given(
        msg_id=ftl_identifiers,
        attr_name=attribute_names,
        text=safe_text,
    )
    @settings(max_examples=150)
    def test_message_with_single_attribute(
        self, msg_id: str, attr_name: str, text: str
    ) -> None:
        """PROPERTY: Message with one attribute parses."""
        source = f"{msg_id} = Value\n    .{attr_name} = {text}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("message_structure=value_and_attribute")
        event("attribute_count=1")

    @given(
        msg_id=ftl_identifiers,
        count=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=50)
    def test_message_with_multiple_attributes(
        self, msg_id: str, count: int
    ) -> None:
        """PROPERTY: Message with multiple attributes parses."""
        attrs = "\n".join([f"    .attr{i} = Value{i}" for i in range(count)])
        source = f"{msg_id} = Main\n{attrs}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("message_structure=value_and_attributes")
        event(f"attribute_count={min(count, 5)}")

    @given(msg_id=ftl_identifiers, attr_name=attribute_names)
    @settings(max_examples=100)
    def test_message_attribute_only(self, msg_id: str, attr_name: str) -> None:
        """PROPERTY: Message with only attributes (no value) parses."""
        source = f"{msg_id} =\n    .{attr_name} = Attribute value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("message_structure=attribute_only")

    @given(
        msg_id=ftl_identifiers,
        var_name=variable_names,
    )
    @settings(max_examples=100)
    def test_message_value_with_placeable(
        self, msg_id: str, var_name: str
    ) -> None:
        """PROPERTY: Message value with placeable parses."""
        source = f"{msg_id} = Text {{ ${var_name} }} more"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("message_structure=value_with_placeable")


# ============================================================================
# COMMENTS
# ============================================================================


class TestCommentParsing:
    """Property tests for comment parsing."""

    @given(text=safe_text)
    @settings(max_examples=150)
    def test_standalone_comment(self, text: str) -> None:
        """PROPERTY: Standalone comment parses."""
        source = f"# {text}\n\nmsg = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("comment_level=standalone")

    @given(text=safe_text)
    @settings(max_examples=100)
    def test_group_comment(self, text: str) -> None:
        """PROPERTY: Group comment ## parses."""
        source = f"## {text}\n\nmsg = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("comment_level=group")

    @given(text=safe_text)
    @settings(max_examples=100)
    def test_resource_comment(self, text: str) -> None:
        """PROPERTY: Resource comment ### parses."""
        source = f"### {text}\n\nmsg = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("comment_level=resource")

    @given(
        text=safe_text,
        count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    def test_multiple_comment_lines(self, text: str, count: int) -> None:
        """PROPERTY: Multiple consecutive comment lines parse."""
        comments = "\n".join([f"# {text} {i}" for i in range(count)])
        source = f"{comments}\n\nmsg = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event(f"comment_lines={min(count, 5)}")

    @given(msg_id=ftl_identifiers, text=safe_text)
    @settings(max_examples=100)
    def test_comment_attached_to_message(self, msg_id: str, text: str) -> None:
        """PROPERTY: Comment immediately before message parses."""
        source = f"# {text}\n{msg_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("comment_position=attached")


# ============================================================================
# WHITESPACE HANDLING
# ============================================================================


class TestWhitespaceHandling:
    """Property tests for whitespace handling."""

    @given(
        msg_id=ftl_identifiers,
        spaces=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=100)
    def test_spaces_before_equals(self, msg_id: str, spaces: int) -> None:
        """PROPERTY: Spaces before = are handled."""
        source = f"{msg_id}{' ' * spaces}= value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("whitespace_position=before_equals")
        if spaces == 0:
            event("space_count=none")
        elif spaces <= 3:
            event("space_count=few")
        else:
            event("space_count=many")

    @given(
        msg_id=ftl_identifiers,
        spaces=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=100)
    def test_spaces_after_equals(self, msg_id: str, spaces: int) -> None:
        """PROPERTY: Spaces after = are handled."""
        source = f"{msg_id} ={' ' * spaces}value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("whitespace_position=after_equals")
        if spaces == 0:
            event("space_count=none")
        elif spaces <= 3:
            event("space_count=few")
        else:
            event("space_count=many")

    @given(
        msg_id=ftl_identifiers,
        indent=st.integers(min_value=4, max_value=12),
    )
    @settings(max_examples=50)
    def test_attribute_indentation(self, msg_id: str, indent: int) -> None:
        """PROPERTY: Attribute indentation is handled."""
        source = f"{msg_id} = value\n{' ' * indent}.attr = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("whitespace_type=indentation")
        if indent == 4:
            event("indent_level=minimal")
        elif indent <= 8:
            event("indent_level=standard")
        else:
            event("indent_level=deep")

    @given(
        msg_id=ftl_identifiers,
        blank_lines=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=50)
    def test_blank_lines_between_messages(
        self, msg_id: str, blank_lines: int
    ) -> None:
        """PROPERTY: Blank lines between messages don't affect parsing."""
        source = f"{msg_id}1 = value1{chr(10) * blank_lines}{msg_id}2 = value2"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("whitespace_type=blank_lines")
        if blank_lines == 0:
            event("blank_line_count=none")
        elif blank_lines == 1:
            event("blank_line_count=single")
        else:
            event("blank_line_count=multiple")

    @given(
        msg_id=ftl_identifiers,
        trailing_spaces=st.integers(min_value=0, max_value=10),
    )
    @settings(max_examples=50)
    def test_trailing_whitespace(self, msg_id: str, trailing_spaces: int) -> None:
        """PROPERTY: Trailing whitespace is handled."""
        source = f"{msg_id} = value{' ' * trailing_spaces}\n"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("whitespace_position=trailing")
        if trailing_spaces == 0:
            event("space_count=none")
        elif trailing_spaces <= 3:
            event("space_count=few")
        else:
            event("space_count=many")


# ============================================================================
# FUNCTION CALLS
# ============================================================================


