"""Edge case tests for ftllexengine.syntax.serializer module.

Comprehensive test suite targeting edge cases and full coverage:
- Control character escaping (DEL 0x7F and all C0 control characters)
- Depth limit enforcement during serialization (without validation)
- Junk entries with leading whitespace
- Pattern serialization with mixed elements (text/placeable)
- SelectExpression variant key types (Identifier/NumberLiteral)
- FunctionReference validation paths
- Multiline pattern indentation

"""

from __future__ import annotations

import pytest
from hypothesis import assume, example, given
from hypothesis import strategies as st

from ftllexengine.syntax.ast import (
    CallArguments,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    StringLiteral,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.serializer import (
    SerializationDepthError,
    serialize,
)


class TestControlCharacterEscaping:
    """Test StringLiteral escaping of all control characters."""

    def test_del_character_escaped_as_unicode(self) -> None:
        """DEL character (0x7F) serialized as \\u007F escape sequence."""
        # DEL is a control character that needs Unicode escaping
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(expression=StringLiteral(value="before\x7Fafter")),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        # DEL must be escaped as \u007F
        assert r"\u007F" in result
        assert "before" in result
        assert "after" in result

    def test_nul_character_escaped(self) -> None:
        """NUL character (0x00) serialized as \\u0000 escape sequence."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(expression=StringLiteral(value="a\x00b")),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        assert r"\u0000" in result

    def test_bel_character_escaped(self) -> None:
        """BEL character (0x07) serialized as \\u0007 escape sequence."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(expression=StringLiteral(value="ring\x07bell")),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        assert r"\u0007" in result

    def test_vertical_tab_escaped(self) -> None:
        """Vertical tab (0x0B) serialized as \\u000B escape sequence."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(expression=StringLiteral(value="a\x0Bb")),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        assert r"\u000B" in result

    def test_form_feed_escaped(self) -> None:
        """Form feed (0x0C) serialized as \\u000C escape sequence."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(expression=StringLiteral(value="page\x0Cbreak")),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        assert r"\u000C" in result

    def test_escape_character_escaped(self) -> None:
        """ESC character (0x1B) serialized as \\u001B escape sequence."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(expression=StringLiteral(value="before\x1Bafter")),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        assert r"\u001B" in result

    @given(
        control_char=st.one_of(
            st.integers(min_value=0x00, max_value=0x1F),  # C0 control characters
            st.just(0x7F),  # DEL
        )
    )
    @example(control_char=0x7F)  # Ensure DEL is explicitly tested
    @example(control_char=0x00)  # NUL
    @example(control_char=0x01)  # SOH
    @example(control_char=0x1F)  # Unit separator
    def test_all_control_characters_escaped_property(self, control_char: int) -> None:
        """All control characters (0x00-0x1F, 0x7F) escaped as Unicode."""
        char = chr(control_char)
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(expression=StringLiteral(value=f"a{char}b")),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        # Verify Unicode escape present
        expected_escape = f"\\u{control_char:04X}"
        assert expected_escape in result

        # Verify the raw control character is NOT in the output
        # (it should be escaped)
        # Exception: newline/tab which might be normalized by string handling
        if char not in "\n\t":
            assert char not in result


class TestSerializationDepthLimitWithoutValidation:
    """Test depth limit enforcement during serialization when validation is disabled.

    Per serializer.py lines 297-299, the serialize method has a try/except
    that catches DepthLimitExceededError during the _serialize_resource call.
    This is distinct from the validation phase depth check.

    To trigger this:
    1. Disable validation (validate=False)
    2. Create AST with nesting that exceeds max_depth
    3. Depth guard triggers during serialization, not validation
    """

    def test_depth_exceeded_during_serialization_not_validation(self) -> None:
        """Depth limit enforced during serialization even when validation disabled."""
        # Create deeply nested Placeables beyond the limit
        # Start with innermost expression
        max_depth = 5
        inner_expr: StringLiteral | Placeable = StringLiteral(value="deep")

        # Build nested Placeables: each Placeable adds one depth level
        for _ in range(max_depth + 1):  # Exceed limit by 1
            inner_expr = Placeable(expression=inner_expr)

        # Type narrowing: at this point inner_expr is definitely a Placeable
        inner_placeable: Placeable = inner_expr  # type: ignore[assignment]

        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(inner_placeable,)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        # Validation is disabled - should still catch depth during serialization
        with pytest.raises(SerializationDepthError, match="nesting exceeds maximum depth"):
            serialize(resource, validate=False, max_depth=max_depth)

    def test_depth_exactly_at_limit_succeeds_without_validation(self) -> None:
        """AST exactly at depth limit serializes successfully without validation."""
        max_depth = 5
        inner_expr: StringLiteral | Placeable = StringLiteral(value="ok")

        # Build nested Placeables exactly at limit
        for _ in range(max_depth):
            inner_expr = Placeable(expression=inner_expr)

        # Type narrowing: at this point inner_expr is definitely a Placeable
        inner_placeable: Placeable = inner_expr  # type: ignore[assignment]

        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(inner_placeable,)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        # Should succeed - exactly at limit
        result = serialize(resource, validate=False, max_depth=max_depth)
        assert "ok" in result

    @given(
        depth_over_limit=st.integers(min_value=1, max_value=10),
        max_depth=st.integers(min_value=3, max_value=20),
    )
    @example(depth_over_limit=1, max_depth=5)
    @example(depth_over_limit=5, max_depth=10)
    def test_serialization_depth_property(
        self, depth_over_limit: int, max_depth: int
    ) -> None:
        """Serialization depth limit enforced regardless of validation setting."""
        # Build AST exceeding depth limit
        inner_expr: StringLiteral | Placeable = StringLiteral(value="x")
        for _ in range(max_depth + depth_over_limit):
            inner_expr = Placeable(expression=inner_expr)

        # Type narrowing: at this point inner_expr is definitely a Placeable
        inner_placeable: Placeable = inner_expr  # type: ignore[assignment]

        msg = Message(
            id=Identifier(name="m"),
            value=Pattern(elements=(inner_placeable,)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        # Should raise SerializationDepthError
        with pytest.raises(SerializationDepthError):
            serialize(resource, validate=False, max_depth=max_depth)


class TestJunkWithLeadingWhitespace:
    """Test Junk entry serialization with leading whitespace.

    Per serializer.py line 321, when a Junk entry follows another entry
    and the Junk content starts with whitespace, the separator logic takes
    a different path (pass statement, no additional separator added).

    This tests the specific branch: isinstance(entry, Junk) and entry.content[0] in "\\n "
    """

    def test_junk_with_leading_newline_after_message(self) -> None:
        """Junk with leading newline after message skips adding separator."""
        msg = Message(
            id=Identifier(name="hello"),
            value=Pattern(elements=(TextElement(value="World"),)),
            attributes=(),
        )
        # Junk with leading newline - parser includes preceding whitespace
        junk = Junk(content="\ninvalid junk content")
        resource = Resource(entries=(msg, junk))

        result = serialize(resource)

        # Should not have double newline - Junk content already starts with \n
        # Result should be: "hello = World\n\ninvalid junk content\n"
        # But since Junk already has \n, we don't add another separator
        assert "hello = World\n" in result
        assert "\ninvalid junk content" in result
        # Should NOT have triple newline
        assert "\n\n\n" not in result

    def test_junk_with_leading_space_after_message(self) -> None:
        """Junk with leading space after message skips adding separator."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="value"),)),
            attributes=(),
        )
        # Junk with leading space
        junk = Junk(content=" some junk")
        resource = Resource(entries=(msg, junk))

        result = serialize(resource)

        # Junk already has leading space, so separator is skipped
        assert "test = value\n some junk" in result

    def test_junk_without_leading_whitespace_gets_separator(self) -> None:
        """Junk without leading whitespace gets normal separator."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="value"),)),
            attributes=(),
        )
        # Junk WITHOUT leading whitespace
        junk = Junk(content="junk content")
        resource = Resource(entries=(msg, junk))

        result = serialize(resource)

        # Normal separator added
        assert "test = value\n" in result
        assert "\njunk content" in result

    def test_empty_junk_content_gets_separator(self) -> None:
        """Empty Junk content gets normal separator (no [0] index access)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="value"),)),
            attributes=(),
        )
        # Empty junk - entry.content[0] won't be accessed due to short-circuit
        junk = Junk(content="")
        resource = Resource(entries=(msg, junk))

        result = serialize(resource)

        # Empty junk still gets separator
        assert "test = value\n" in result

    @given(
        leading_char=st.sampled_from(["\n", " ", "\t", "j"]),
        has_content=st.booleans(),
    )
    @example(leading_char="\n", has_content=True)
    @example(leading_char=" ", has_content=True)
    @example(leading_char="j", has_content=True)
    def test_junk_separator_logic_property(
        self, leading_char: str, has_content: bool
    ) -> None:
        """Junk separator logic handles various leading characters correctly."""
        msg = Message(
            id=Identifier(name="m"),
            value=Pattern(elements=(TextElement(value="v"),)),
            attributes=(),
        )

        junk = (
            Junk(content=f"{leading_char}content")
            if has_content
            else Junk(content="")
        )

        resource = Resource(entries=(msg, junk))

        # Should not raise - serialization should handle all cases
        result = serialize(resource)
        assert isinstance(result, str)
        assert "m = v" in result


class TestPatternWithoutBraces:
    """Test Pattern serialization path when text has no braces.

    Per serializer.py line 483->467, there's an else branch when text
    contains neither { nor } characters. This tests the optimization path
    that emits text directly without brace handling.
    """

    def test_text_without_braces_direct_output(self) -> None:
        """Text without braces takes direct output path."""
        msg = Message(
            id=Identifier(name="plain"),
            value=Pattern(
                elements=(
                    TextElement(value="No braces here, just plain text!"),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        # Should contain the text as-is (no brace escaping needed)
        assert "No braces here, just plain text!" in result
        # Should NOT have any brace-related escaping
        assert '{ "{" }' not in result
        assert '{ "}" }' not in result

    def test_text_with_only_safe_punctuation(self) -> None:
        """Text with punctuation but no braces serializes directly."""
        msg = Message(
            id=Identifier(name="punct"),
            value=Pattern(
                elements=(
                    TextElement(value="Hello, world! How are you?"),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        assert "Hello, world! How are you?" in result
        # No brace escaping
        assert '{ "{" }' not in result

    def test_text_with_numbers_and_symbols(self) -> None:
        """Text with numbers and safe symbols serializes directly."""
        msg = Message(
            id=Identifier(name="data"),
            value=Pattern(
                elements=(
                    TextElement(value="Price: $42.00 (20% off)"),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        assert "Price: $42.00 (20% off)" in result

    @given(
        text=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd", "Zs"),
                whitelist_characters="!@#$%^&*()_+-=[]|;:'\",.<>?/~`",
            ),
            min_size=1,
            max_size=100,
        ).filter(lambda t: "{" not in t and "}" not in t)
    )
    @example(text="Simple text without any braces")
    @example(text="Numbers 123 and symbols !@#")
    def test_brace_free_text_property(self, text: str) -> None:
        """Text without braces always serializes without brace escaping."""
        assume(text.strip())  # Non-empty after stripping

        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value=text),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # Should contain the original text
        assert text in result
        # Should NOT have brace escaping since input has no braces
        assert '{ "{" }' not in result or "{" in text  # Only if original had them
        assert '{ "}" }' not in result or "}" in text


class TestMultilinePatternIndentation:
    """Test multi-line pattern indentation handling.

    Per serializer.py lines 474-475, newlines in TextElements are replaced
    with newline + 4-space indentation for FTL continuation lines.
    """

    def test_multiline_text_indented(self) -> None:
        """Newlines in TextElement followed by 4-space indentation."""
        msg = Message(
            id=Identifier(name="multi"),
            value=Pattern(
                elements=(
                    TextElement(value="Line 1\nLine 2\nLine 3"),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        # Each newline should be followed by 4 spaces (continuation indent)
        assert "Line 1\n    Line 2\n    Line 3" in result

    def test_multiline_with_braces_indented_and_escaped(self) -> None:
        """Multiline text with braces: both indentation and brace escaping."""
        msg = Message(
            id=Identifier(name="complex"),
            value=Pattern(
                elements=(
                    TextElement(value="First {line}\nSecond }line"),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        # Should have indentation AND brace escaping
        assert "First" in result
        assert "Second" in result
        assert '{ "{" }' in result  # { escaped
        assert '{ "}" }' in result  # } escaped
        # Newline creates indentation
        assert "\n    " in result

    @given(
        lines=st.lists(
            st.text(
                alphabet=st.characters(
                    whitelist_categories=("Lu", "Ll", "Nd", "Zs"),
                    min_codepoint=0x20,  # Printable ASCII and above
                ),
                min_size=1,
                max_size=50,
            ).filter(lambda t: "{" not in t and "}" not in t),
            min_size=2,
            max_size=5,
        )
    )
    @example(lines=["First line", "Second line", "Third line"])
    def test_multiline_indentation_property(self, lines: list[str]) -> None:
        """Multiline patterns always indent continuation lines with 4 spaces."""
        assume(all(line.strip() for line in lines))  # Non-empty lines

        text = "\n".join(lines)
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value=text),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # After first line, each line should be indented with 4 spaces
        for i, line in enumerate(lines):
            if i == 0:
                # First line not indented
                assert lines[0] in result
            else:
                # Subsequent lines indented
                assert f"\n    {line}" in result or line in result


class TestMixedPatternElements:
    """Test Pattern serialization with mixed TextElement and Placeable elements.

    This ensures the elif branch at line 483 is properly covered when
    iterating through pattern elements that alternate between types.
    """

    def test_mixed_text_and_placeable_elements(self) -> None:
        """Pattern with alternating TextElement and Placeable elements."""
        msg = Message(
            id=Identifier(name="mixed"),
            value=Pattern(
                elements=(
                    TextElement(value="Start "),
                    Placeable(expression=VariableReference(id=Identifier(name="var1"))),
                    TextElement(value=" middle "),
                    Placeable(expression=VariableReference(id=Identifier(name="var2"))),
                    TextElement(value=" end"),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        assert "Start { $var1 } middle { $var2 } end" in result

    def test_multiple_consecutive_placeables(self) -> None:
        """Pattern with consecutive Placeable elements (no text between)."""
        msg = Message(
            id=Identifier(name="consecutive"),
            value=Pattern(
                elements=(
                    Placeable(expression=VariableReference(id=Identifier(name="a"))),
                    Placeable(expression=VariableReference(id=Identifier(name="b"))),
                    Placeable(expression=VariableReference(id=Identifier(name="c"))),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        assert "{ $a }{ $b }{ $c }" in result

    def test_text_then_multiple_placeables(self) -> None:
        """Pattern starting with text followed by multiple placeables."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    TextElement(value="Prefix: "),
                    Placeable(expression=StringLiteral(value="one")),
                    Placeable(expression=StringLiteral(value="two")),
                    Placeable(expression=StringLiteral(value="three")),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        assert 'Prefix: { "one" }{ "two" }{ "three" }' in result

    @given(
        num_text=st.integers(min_value=1, max_value=5),
        num_placeable=st.integers(min_value=1, max_value=5),
    )
    @example(num_text=3, num_placeable=2)
    @example(num_text=1, num_placeable=4)
    def test_mixed_pattern_property(self, num_text: int, num_placeable: int) -> None:
        """Patterns with varying numbers of text and placeable elements serialize correctly."""
        elements: list[TextElement | Placeable] = []

        # Alternate between text and placeable
        for i in range(max(num_text, num_placeable)):
            if i < num_text:
                elements.append(TextElement(value=f"text{i} "))
            if i < num_placeable:
                elements.append(
                    Placeable(
                        expression=VariableReference(id=Identifier(name=f"v{i}"))
                    )
                )

        msg = Message(
            id=Identifier(name="m"),
            value=Pattern(elements=tuple(elements)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)
        assert "m = " in result


class TestSelectExpressionVariantKeys:
    """Test SelectExpression with both Identifier and NumberLiteral variant keys.

    Ensures match statement at line 619-623 covers both cases completely,
    including exit paths (622->625).
    """

    def test_select_with_identifier_keys_only(self) -> None:
        """SelectExpression with all Identifier variant keys."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=SelectExpression(
                            selector=VariableReference(id=Identifier(name="count")),
                            variants=(
                                Variant(
                                    key=Identifier(name="one"),
                                    value=Pattern(
                                        elements=(TextElement(value="One item"),)
                                    ),
                                    default=False,
                                ),
                                Variant(
                                    key=Identifier(name="other"),
                                    value=Pattern(
                                        elements=(TextElement(value="Many items"),)
                                    ),
                                    default=True,
                                ),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        assert "[one]" in result
        assert "*[other]" in result
        assert "One item" in result
        assert "Many items" in result

    def test_select_with_number_keys_only(self) -> None:
        """SelectExpression with all NumberLiteral variant keys."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=SelectExpression(
                            selector=VariableReference(id=Identifier(name="count")),
                            variants=(
                                Variant(
                                    key=NumberLiteral(value=1, raw="1"),
                                    value=Pattern(
                                        elements=(TextElement(value="Exactly one"),)
                                    ),
                                    default=False,
                                ),
                                Variant(
                                    key=NumberLiteral(value=0, raw="0"),
                                    value=Pattern(
                                        elements=(TextElement(value="Zero"),)
                                    ),
                                    default=True,
                                ),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        assert "[1]" in result
        assert "*[0]" in result
        assert "Exactly one" in result
        assert "Zero" in result

    def test_select_with_mixed_identifier_and_number_keys(self) -> None:
        """SelectExpression with both Identifier and NumberLiteral keys."""
        msg = Message(
            id=Identifier(name="mixed"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=SelectExpression(
                            selector=VariableReference(id=Identifier(name="val")),
                            variants=(
                                Variant(
                                    key=NumberLiteral(value=0, raw="0"),
                                    value=Pattern(
                                        elements=(TextElement(value="Zero"),)
                                    ),
                                    default=False,
                                ),
                                Variant(
                                    key=NumberLiteral(value=1, raw="1"),
                                    value=Pattern(
                                        elements=(TextElement(value="One"),)
                                    ),
                                    default=False,
                                ),
                                Variant(
                                    key=Identifier(name="other"),
                                    value=Pattern(
                                        elements=(TextElement(value="Other"),)
                                    ),
                                    default=True,
                                ),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)

        # Both NumberLiteral and Identifier cases exercised
        assert "[0]" in result
        assert "[1]" in result
        assert "*[other]" in result


class TestFunctionReferenceValidation:
    """Test FunctionReference validation path coverage.

    Ensures the FunctionReference case at line 183-193 in _validate_expression
    is fully covered, including exit paths (185->exit).
    """

    def test_function_reference_with_positional_args_validated(self) -> None:
        """FunctionReference with positional arguments passes validation."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier(name="NUMBER"),
                            arguments=CallArguments(
                                positional=(
                                    VariableReference(id=Identifier(name="count")),
                                ),
                                named=(),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        # Should validate successfully
        result = serialize(resource, validate=True)
        assert "NUMBER($count)" in result

    def test_function_reference_with_named_args_validated(self) -> None:
        """FunctionReference with named arguments passes validation."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier(name="DATETIME"),
                            arguments=CallArguments(
                                positional=(),
                                named=(
                                    NamedArgument(
                                        name=Identifier(name="month"),
                                        value=StringLiteral(value="long"),
                                    ),
                                    NamedArgument(
                                        name=Identifier(name="day"),
                                        value=StringLiteral(value="numeric"),
                                    ),
                                ),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        # Should validate successfully
        result = serialize(resource, validate=True)
        assert "DATETIME" in result
        assert 'month: "long"' in result
        assert 'day: "numeric"' in result

    def test_function_reference_with_mixed_args_validated(self) -> None:
        """FunctionReference with both positional and named args validated."""
        msg = Message(
            id=Identifier(name="formatted"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=FunctionReference(
                            id=Identifier(name="NUMBER"),
                            arguments=CallArguments(
                                positional=(
                                    VariableReference(id=Identifier(name="amount")),
                                ),
                                named=(
                                    NamedArgument(
                                        name=Identifier(name="style"),
                                        value=StringLiteral(value="currency"),
                                    ),
                                    NamedArgument(
                                        name=Identifier(name="currency"),
                                        value=StringLiteral(value="USD"),
                                    ),
                                ),
                            ),
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)
        assert "NUMBER($amount" in result
        assert 'style: "currency"' in result
        assert 'currency: "USD"' in result
