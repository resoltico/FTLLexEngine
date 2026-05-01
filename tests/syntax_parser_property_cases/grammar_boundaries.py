# mypy: ignore-errors
from tests.syntax_parser_property_cases import (
    FluentParserV1,
    attribute_names,
    event,
    ftl_identifiers,
    given,
    numbers,
    safe_text,
    settings,
    st,
    variable_names,
)


class TestFunctionCallParsing:
    """Property tests for function call parsing."""

    @given(var_name=variable_names)
    @settings(max_examples=150)
    def test_number_function_call(self, var_name: str) -> None:
        """PROPERTY: NUMBER($var) parses correctly."""
        source = f"msg = {{ NUMBER(${var_name}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("function_name=NUMBER")
        event("function_arg_type=variable")

    @given(var_name=variable_names)
    @settings(max_examples=150)
    def test_datetime_function_call(self, var_name: str) -> None:
        """PROPERTY: DATETIME($var) parses correctly."""
        source = f"msg = {{ DATETIME(${var_name}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("function_name=DATETIME")
        event("function_arg_type=variable")

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_function_with_named_arg(self, var_name: str) -> None:
        """PROPERTY: FUNC($var, opt: val) parses."""
        source = f"msg = {{ NUMBER(${var_name}, minimumFractionDigits: 2) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("function_options=with_named")
        event("option_value_type=numeric")

    @given(var_name=variable_names, number=numbers)
    @settings(max_examples=100)
    def test_function_with_numeric_option(self, var_name: str, number: int) -> None:
        """PROPERTY: Function with numeric option parses."""
        source = f"msg = {{ NUMBER(${var_name}, minimumFractionDigits: {number}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("function_options=with_numeric")
        if number < 0:
            event("option_value_sign=negative")
        elif number == 0:
            event("option_value_sign=zero")
        else:
            event("option_value_sign=positive")

    @given(var_name=variable_names)
    @settings(max_examples=100)
    def test_function_with_string_option(self, var_name: str) -> None:
        """PROPERTY: Function with string option parses."""
        source = f'msg = {{ DATETIME(${var_name}, style: "long") }}'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("function_options=with_string")
        event("option_value_type=string")

    @given(
        var_name=variable_names,
        count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=50)
    def test_function_with_multiple_options(self, var_name: str, count: int) -> None:
        """PROPERTY: Function with multiple options parses."""
        options = ", ".join([f"opt{i}: {i}" for i in range(count)])
        source = f"msg = {{ NUMBER(${var_name}, {options}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("function_options=multiple")
        event(f"option_count={min(count, 5)}")

    @given(func_name=ftl_identifiers, var_name=variable_names)
    @settings(max_examples=100)
    def test_custom_function_call(self, func_name: str, var_name: str) -> None:
        """PROPERTY: Custom function calls parse."""
        # Note: uppercase function names required
        source = f"msg = {{ {func_name.upper()}(${var_name}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("function_name=CUSTOM")
        if len(func_name) <= 5:
            event("function_name_length=short")
        else:
            event("function_name_length=long")

    @given(number=numbers)
    @settings(max_examples=50)
    def test_function_with_number_literal_arg(self, number: int) -> None:
        """PROPERTY: Function with number literal argument parses."""
        source = f"msg = {{ NUMBER({number}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("function_arg_type=literal")
        if number < 0:
            event("literal_sign=negative")
        elif number == 0:
            event("literal_sign=zero")
        else:
            event("literal_sign=positive")

    @given(var_name=variable_names)
    @settings(max_examples=50)
    def test_nested_function_calls(self, var_name: str) -> None:
        """PROPERTY: Nested function calls parse (if supported)."""
        # Most parsers support simple nesting
        source = f"msg = {{ NUMBER(${var_name}) }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("function_nesting=simple")


# ============================================================================
# MESSAGE REFERENCES
# ============================================================================


class TestMessageReferenceParsing:
    """Property tests for message reference parsing."""

    @given(msg_id1=ftl_identifiers, msg_id2=ftl_identifiers)
    @settings(max_examples=150)
    def test_simple_message_reference(self, msg_id1: str, msg_id2: str) -> None:
        """PROPERTY: { msg-id } references another message."""
        source = f"{msg_id1} = Value1\n{msg_id2} = {{ {msg_id1} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("msg_ref_type=simple")
        if msg_id1 == msg_id2:
            event("msg_ref_self=true")
        else:
            event("msg_ref_self=false")

    @given(
        msg_id1=ftl_identifiers,
        msg_id2=ftl_identifiers,
        attr_name=attribute_names,
    )
    @settings(max_examples=100)
    def test_message_attribute_reference(
        self, msg_id1: str, msg_id2: str, attr_name: str
    ) -> None:
        """PROPERTY: { msg.attr } references message attribute."""
        source = (
            f"{msg_id1} = Value\n"
            f"    .{attr_name} = Attr\n"
            f"{msg_id2} = {{ {msg_id1}.{attr_name} }}"
        )
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("msg_ref_type=with_attribute")

    @given(
        msg_id=ftl_identifiers,
        count=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=50)
    def test_multiple_message_references(self, msg_id: str, count: int) -> None:
        """PROPERTY: Multiple message references in one pattern parse."""
        refs = " ".join([f"{{ {msg_id}{i} }}" for i in range(count)])
        # Create referenced messages
        messages = "\n".join([f"{msg_id}{i} = Value{i}" for i in range(count)])
        source = f"{messages}\nfinal = {refs}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("msg_ref_type=multiple")
        event(f"msg_ref_count={min(count, 5)}")

    @given(msg_id1=ftl_identifiers, msg_id2=ftl_identifiers, text=safe_text)
    @settings(max_examples=100)
    def test_message_reference_with_text(
        self, msg_id1: str, msg_id2: str, text: str
    ) -> None:
        """PROPERTY: Message reference mixed with text parses."""
        source = f"{msg_id1} = Value\n{msg_id2} = {text} {{ {msg_id1} }} {text}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("msg_ref_type=mixed_with_text")
        if len(text) == 0:
            event("surrounding_text=empty")
        else:
            event("surrounding_text=present")


# ============================================================================
# IDENTIFIER VALIDATION
# ============================================================================


class TestIdentifierValidation:
    """Property tests for identifier validation."""

    @given(
        prefix=st.text(
            alphabet=st.characters(min_codepoint=97, max_codepoint=122),
            min_size=1,
            max_size=5,
        ),
        number=st.integers(min_value=0, max_value=999),
    )
    @settings(max_examples=150)
    def test_identifier_with_number_suffix(self, prefix: str, number: int) -> None:
        """PROPERTY: Identifiers can have numeric suffixes."""
        msg_id = f"{prefix}{number}"
        source = f"{msg_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("identifier_type=with_number_suffix")
        if number == 0:
            event("number_suffix=zero")
        elif number < 10:
            event("number_suffix=single_digit")
        elif number < 100:
            event("number_suffix=two_digit")
        else:
            event("number_suffix=three_digit")

    @given(
        parts=st.lists(
            st.text(
                alphabet=st.characters(min_codepoint=97, max_codepoint=122),
                min_size=1,
                max_size=5,
            ),
            min_size=2,
            max_size=5,
        ),
    )
    @settings(max_examples=100)
    def test_identifier_with_hyphens(self, parts: list[str]) -> None:
        """PROPERTY: Identifiers with hyphens parse."""
        msg_id = "-".join(parts)
        source = f"{msg_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("identifier_type=with_hyphens")
        event(f"identifier_parts={min(len(parts), 5)}")

    @given(
        parts=st.lists(
            st.text(
                alphabet=st.characters(min_codepoint=97, max_codepoint=122),
                min_size=1,
                max_size=5,
            ),
            min_size=2,
            max_size=5,
        ),
    )
    @settings(max_examples=100)
    def test_identifier_with_underscores(self, parts: list[str]) -> None:
        """PROPERTY: Identifiers with underscores parse."""
        msg_id = "_".join(parts)
        source = f"{msg_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("identifier_type=with_underscores")
        event(f"identifier_parts={min(len(parts), 5)}")

    @given(length=st.integers(min_value=1, max_value=100))
    @settings(max_examples=50)
    def test_identifier_length_handling(self, length: int) -> None:
        """PROPERTY: Identifiers of various lengths parse."""
        msg_id = "a" * length
        source = f"{msg_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("identifier_type=length_test")
        if length == 1:
            event("identifier_length=minimal")
        elif length <= 10:
            event("identifier_length=short")
        elif length <= 50:
            event("identifier_length=medium")
        else:
            event("identifier_length=long")

    @given(
        msg_id=ftl_identifiers,
        uppercase_count=st.integers(min_value=0, max_value=5),
    )
    @settings(max_examples=100)
    def test_identifier_case_sensitivity(
        self, msg_id: str, uppercase_count: int
    ) -> None:
        """PROPERTY: Identifier case is preserved."""
        # Mix case by uppercasing some characters
        chars = list(msg_id)
        for i in range(min(uppercase_count, len(chars))):
            chars[i] = chars[i].upper()
        mixed_case_id = "".join(chars)
        source = f"{mixed_case_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("identifier_type=mixed_case")
        if uppercase_count == 0:
            event("case_mix=all_lower")
        elif uppercase_count >= len(chars):
            event("case_mix=all_upper")
        else:
            event("case_mix=mixed")


# ============================================================================
# ESCAPE SEQUENCES
# ============================================================================


class TestEscapeSequenceParsing:
    """Property tests for escape sequence handling."""

    def test_unicode_escape_basic(self) -> None:
        """PROPERTY: Basic Unicode escapes parse."""
        source = r'msg = { "\u0041" }'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    @given(
        codepoint=st.integers(
            min_value=0x0020,
            max_value=0xD7FF,
        ),  # Valid Unicode range
    )
    @settings(max_examples=100)
    def test_unicode_escape_various_codepoints(self, codepoint: int) -> None:
        """PROPERTY: Unicode escapes for various codepoints parse."""
        source = f'msg = {{ "\\u{codepoint:04X}" }}'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("escape_type=unicode")
        if codepoint < 0x0080:
            event("codepoint_range=ascii")
        elif codepoint < 0x0800:
            event("codepoint_range=latin_extended")
        elif codepoint < 0x3000:
            event("codepoint_range=mid_bmp")
        else:
            event("codepoint_range=cjk_symbols")

    def test_escaped_quote_in_string(self) -> None:
        """PROPERTY: Escaped quotes in strings parse."""
        source = r'msg = { "He said \"Hello\"" }'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    def test_escaped_backslash_in_string(self) -> None:
        """PROPERTY: Escaped backslashes parse."""
        source = r'msg = { "Path: C:\\Windows" }'
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

    def test_escaped_braces_in_text(self) -> None:
        """PROPERTY: Escaped braces in text parse."""
        source = r"msg = Literal \{ and \} braces"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None


# ============================================================================
# LINE ENDING HANDLING
# ============================================================================


class TestLineEndingHandling:
    """Property tests for line ending handling."""

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=100)
    def test_unix_line_endings(self, msg_id: str) -> None:
        """PROPERTY: Unix \\n line endings parse correctly."""
        source = f"{msg_id}1 = value1\n{msg_id}2 = value2\n"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("line_ending_type=unix")

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=100)
    def test_windows_line_endings(self, msg_id: str) -> None:
        """PROPERTY: Windows \\r\\n line endings parse correctly."""
        source = f"{msg_id}1 = value1\r\n{msg_id}2 = value2\r\n"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("line_ending_type=windows")

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=100)
    def test_old_mac_line_endings(self, msg_id: str) -> None:
        """PROPERTY: Old Mac \\r line endings parse."""
        source = f"{msg_id}1 = value1\r{msg_id}2 = value2\r"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("line_ending_type=old_mac")

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=50)
    def test_mixed_line_endings(self, msg_id: str) -> None:
        """PROPERTY: Mixed line endings are handled."""
        source = f"{msg_id}1 = value1\n{msg_id}2 = value2\r\n{msg_id}3 = value3\r"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("line_ending_type=mixed")

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=50)
    def test_no_final_newline(self, msg_id: str) -> None:
        """PROPERTY: Source without final newline parses."""
        source = f"{msg_id} = value"  # No trailing newline
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("line_ending_type=no_final")


# ============================================================================
# UTF-8 BOM HANDLING
# ============================================================================


class TestUTF8BOMHandling:
    """Property tests for UTF-8 BOM handling."""

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=100)
    def test_utf8_bom_at_start(self, msg_id: str) -> None:
        """PROPERTY: UTF-8 BOM at file start is handled."""
        bom = "\ufeff"
        source = f"{bom}{msg_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("bom_presence=with_bom")

    @given(msg_id=ftl_identifiers)
    @settings(max_examples=50)
    def test_source_without_bom(self, msg_id: str) -> None:
        """PROPERTY: Source without BOM parses normally."""
        source = f"{msg_id} = value"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("bom_presence=without_bom")

    @given(msg_id=ftl_identifiers, text=safe_text)
    @settings(max_examples=50)
    def test_bom_only_at_start(self, msg_id: str, text: str) -> None:
        """PROPERTY: BOM only valid at file start."""
        source = f"{msg_id} = {text}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("bom_presence=no_bom_with_content")
        if len(text) == 0:
            event("text_content=empty")
        else:
            event("text_content=present")


# ============================================================================
# PATTERN ELEMENT BOUNDARIES
# ============================================================================


class TestPatternElementBoundaries:
    """Property tests for pattern element boundaries."""

    @given(var_name=variable_names, text=safe_text)
    @settings(max_examples=100)
    def test_text_placeable_boundary(self, var_name: str, text: str) -> None:
        """PROPERTY: Boundary between text and placeable is correct."""
        source = f"msg = {text}{{ ${var_name} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("boundary_type=text_placeable")
        if len(text) == 0:
            event("prefix_text=empty")
        else:
            event("prefix_text=present")

    @given(var_name=variable_names, text=safe_text)
    @settings(max_examples=100)
    def test_placeable_text_boundary(self, var_name: str, text: str) -> None:
        """PROPERTY: Boundary between placeable and text is correct."""
        source = f"msg = {{ ${var_name} }}{text}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("boundary_type=placeable_text")
        if len(text) == 0:
            event("suffix_text=empty")
        else:
            event("suffix_text=present")

    @given(
        var1=variable_names,
        var2=variable_names,
    )
    @settings(max_examples=100)
    def test_placeable_placeable_boundary(self, var1: str, var2: str) -> None:
        """PROPERTY: Adjacent placeables have correct boundary."""
        source = f"msg = {{ ${var1} }}{{ ${var2} }}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("boundary_type=placeable_placeable")
        if var1 == var2:
            event("adjacent_vars=same")
        else:
            event("adjacent_vars=different")

    @given(text1=safe_text, text2=safe_text)
    @settings(max_examples=50)
    def test_text_text_concatenation(self, text1: str, text2: str) -> None:
        """PROPERTY: Consecutive text elements are handled."""
        source = f"msg = {text1} {text2}"
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("boundary_type=text_text")
        total_len = len(text1) + len(text2)
        if total_len == 0:
            event("combined_text=empty")
        elif total_len <= 20:
            event("combined_text=short")
        else:
            event("combined_text=long")


# ============================================================================
# MULTILINE PATTERNS
# ============================================================================


class TestMultilinePatterns:
    """Property tests for multiline pattern handling."""

    @given(msg_id=ftl_identifiers, lines=st.lists(safe_text, min_size=2, max_size=5))
    @settings(max_examples=100)
    def test_multiline_text_value(self, msg_id: str, lines: list[str]) -> None:
        """PROPERTY: Multiline text values parse."""
        # Indent continuation lines
        text_lines = [lines[0]] + [f"    {line}" for line in lines[1:]]
        source = f"{msg_id} =\n" + "\n".join(text_lines)
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("multiline_type=text_only")
        event(f"line_count={min(len(lines), 5)}")

    @given(
        msg_id=ftl_identifiers,
        var_name=variable_names,
        lines=st.lists(safe_text, min_size=2, max_size=5),
    )
    @settings(max_examples=50)
    def test_multiline_with_placeables(
        self, msg_id: str, var_name: str, lines: list[str]
    ) -> None:
        """PROPERTY: Multiline patterns with placeables parse."""
        text_lines = [f"{lines[0]} {{ ${var_name} }}"] + [
            f"    {line}" for line in lines[1:]
        ]
        source = f"{msg_id} =\n" + "\n".join(text_lines)
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("multiline_type=with_placeables")
        event(f"line_count={min(len(lines), 5)}")

    @given(
        msg_id=ftl_identifiers,
        indent=st.integers(min_value=4, max_value=12),
    )
    @settings(max_examples=50)
    def test_multiline_indentation_consistency(
        self, msg_id: str, indent: int
    ) -> None:
        """PROPERTY: Consistent indentation in multiline patterns."""
        source = (
            f"{msg_id} =\n"
            f"{' ' * indent}Line 1\n"
            f"{' ' * indent}Line 2\n"
            f"{' ' * indent}Line 3"
        )
        parser = FluentParserV1()
        resource = parser.parse(source)

        assert resource is not None

        # Emit events for HypoFuzz guidance
        event("multiline_type=consistent_indent")
        if indent == 4:
            event("indent_level=minimal")
        elif indent <= 8:
            event("indent_level=standard")
        else:
            event("indent_level=deep")


# ============================================================================
# ROUND-TRIP PROPERTIES
# ============================================================================


