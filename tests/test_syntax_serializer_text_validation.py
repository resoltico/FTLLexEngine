"""Tests for syntax.serializer: FluentSerializer, serialize(), edge cases, internal helpers.

Validates serialization of AST nodes back to FTL syntax, including control character
escaping, depth limits, junk entries, multiline patterns, and classify/escape internals.
"""

from __future__ import annotations

import pytest
from hypothesis import assume, event, example, given
from hypothesis import strategies as st

from ftllexengine.syntax import serialize
from ftllexengine.syntax.ast import (
    Identifier,
    Junk,
    Message,
    Pattern,
    Placeable,
    Resource,
    StringLiteral,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.serializer import (
    SerializationDepthError,
    SerializationValidationError,
)

# ============================================================================
# TEXT ELEMENT BRACE SERIALIZATION TESTS
# ============================================================================


class TestTextElementBraceSerialization:
    """Test that literal braces in TextElements are serialized per Fluent Spec 1.0.

    Per Fluent Spec: Backslash has no escaping power in TextElements.
    Literal braces MUST be expressed as StringLiterals within Placeables:
    - { must be serialized as {"{"} (Placeable containing StringLiteral)
    - } must be serialized as {"}"} (Placeable containing StringLiteral)

    This produces valid FTL that compliant parsers accept.
    """

    def test_open_brace_becomes_string_literal_placeable(self) -> None:
        """Open brace { in text becomes {"{"} per Fluent spec."""
        msg = Message(
            id=Identifier(name="brace"),
            value=Pattern(elements=(TextElement(value="Use {variable} syntax"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # Braces become StringLiteral Placeables: { "{" }variable{ "}" }
        assert 'brace = Use { "{" }variable{ "}" } syntax\n' in result

    def test_close_brace_becomes_string_literal_placeable(self) -> None:
        """Close brace } in text becomes {"}"} per Fluent spec."""
        msg = Message(
            id=Identifier(name="json"),
            value=Pattern(elements=(TextElement(value='{"key": "value"}'),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # Both { and } become StringLiteral Placeables
        assert '{ "{" }' in result
        assert '{ "}" }' in result
        # Full pattern: { "{" }"key": "value"{ "}" }
        assert 'json = { "{" }"key": "value"{ "}" }\n' in result

    def test_backslash_not_escaped_in_text_elements(self) -> None:
        """Backslash has no special meaning in TextElements per Fluent spec.

        Per spec: backslash only has escaping power in StringLiterals,
        not in TextElements. A backslash in text is preserved as-is.
        """
        msg = Message(
            id=Identifier(name="path"),
            value=Pattern(elements=(TextElement(value="C:\\Users\\file.txt"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # Backslash preserved as-is (no escaping in TextElements)
        assert "path = C:\\Users\\file.txt\n" in result

    def test_backslash_before_brace_preserved(self) -> None:
        """Backslash before brace: backslash preserved, brace becomes placeable."""
        msg = Message(
            id=Identifier(name="escaped"),
            value=Pattern(elements=(TextElement(value="Literal \\{ brace"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # Backslash preserved, brace becomes StringLiteral Placeable
        assert 'escaped = Literal \\{ "{" } brace\n' in result

    def test_preserve_text_without_braces(self) -> None:
        """Text without braces should not be modified."""
        msg = Message(
            id=Identifier(name="plain"),
            value=Pattern(elements=(TextElement(value="Hello, World!"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert "plain = Hello, World!\n" in result

    def test_mixed_text_and_placeables(self) -> None:
        """Text with literal braces alongside real placeables."""
        msg = Message(
            id=Identifier(name="mixed"),
            value=Pattern(
                elements=(
                    TextElement(value="JSON: {key} = "),
                    Placeable(expression=VariableReference(id=Identifier(name="value"))),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # Literal braces become StringLiteral Placeables, real placeable unchanged
        assert 'mixed = JSON: { "{" }key{ "}" } = { $value }\n' in result

    def test_multiple_consecutive_braces(self) -> None:
        """Multiple consecutive braces each become separate placeables."""
        msg = Message(
            id=Identifier(name="multi"),
            value=Pattern(elements=(TextElement(value="{{nested}}"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        # Each brace becomes its own placeable
        assert 'multi = { "{" }{ "{" }' in result
        assert '{ "}" }{ "}" }' in result

    def test_brace_at_start_of_text(self) -> None:
        """Brace at start of text element."""
        msg = Message(
            id=Identifier(name="start"),
            value=Pattern(elements=(TextElement(value="{start"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert 'start = { "{" }start\n' in result

    def test_brace_at_end_of_text(self) -> None:
        """Brace at end of text element."""
        msg = Message(
            id=Identifier(name="end"),
            value=Pattern(elements=(TextElement(value="end}"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert 'end = end{ "}" }\n' in result

    def test_only_braces(self) -> None:
        """Text containing only braces."""
        msg = Message(
            id=Identifier(name="braces"),
            value=Pattern(elements=(TextElement(value="{}"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource)

        assert 'braces = { "{" }{ "}" }\n' in result


# ============================================================================
# IDENTIFIER VALIDATION TESTS
# ============================================================================


class TestIdentifierValidation:
    """Test identifier validation during serialization."""

    def test_invalid_message_id_rejected(self) -> None:
        """Invalid message identifier rejected when validate=True.

        Regression test for SER-INVALID-OUTPUT-001.
        Parser-produced ASTs have valid identifiers, but programmatically
        constructed ASTs can contain arbitrary strings. Serializer should
        validate identifiers when validate=True.
        """
        msg = Message(
            id=Identifier(name="invalid message with spaces"),
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        with pytest.raises(SerializationValidationError, match="Invalid identifier"):
            serialize(resource, validate=True)

    def test_invalid_variable_reference_rejected(self) -> None:
        """Invalid variable identifier rejected when validate=True."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=VariableReference(
                            id=Identifier(name="my var")  # Space invalid
                        )
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        with pytest.raises(SerializationValidationError, match="Invalid identifier"):
            serialize(resource, validate=True)

    def test_invalid_identifier_allowed_when_validation_disabled(self) -> None:
        """Invalid identifier allowed when validate=False."""
        msg = Message(
            id=Identifier(name="invalid id"),
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        # Should not raise exception
        result = serialize(resource, validate=False)
        assert "invalid id" in result

    def test_valid_identifier_with_hyphens_and_underscores(self) -> None:
        """Valid identifiers with hyphens and underscores pass validation."""
        msg = Message(
            id=Identifier(name="valid-id_123"),
            value=Pattern(elements=(TextElement(value="Test"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)
        assert "valid-id_123" in result


# ============================================================================
# EDGE CASES AND INTERNAL HELPERS (from test_serializer_edge_cases.py)
# ============================================================================


class TestControlCharacterEscaping:
    """Test StringLiteral escaping of all control characters."""

    def test_del_character_escaped_as_unicode(self) -> None:
        """DEL character (0x7F) serialized as \\u007F escape sequence."""
        # DEL is a control character that needs Unicode escaping
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=StringLiteral(value="before\x7fafter")),)),
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
            value=Pattern(elements=(Placeable(expression=StringLiteral(value="a\x00b")),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        assert r"\u0000" in result

    def test_bel_character_escaped(self) -> None:
        """BEL character (0x07) serialized as \\u0007 escape sequence."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=StringLiteral(value="ring\x07bell")),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        assert r"\u0007" in result

    def test_vertical_tab_escaped(self) -> None:
        """Vertical tab (0x0B) serialized as \\u000B escape sequence."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=StringLiteral(value="a\x0bb")),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        assert r"\u000B" in result

    def test_form_feed_escaped(self) -> None:
        """Form feed (0x0C) serialized as \\u000C escape sequence."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=StringLiteral(value="page\x0cbreak")),)),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource)
        assert r"\u000C" in result

    def test_escape_character_escaped(self) -> None:
        """ESC character (0x1B) serialized as \\u001B escape sequence."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=StringLiteral(value="before\x1bafter")),)),
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
        is_del = control_char == 0x7F
        event(f"control_char=0x{control_char:02X}")
        event(f"is_del={is_del}")
        char = chr(control_char)
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=StringLiteral(value=f"a{char}b")),)),
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
    def test_serialization_depth_property(self, depth_over_limit: int, max_depth: int) -> None:
        """Serialization depth limit enforced regardless of validation setting."""
        total = max_depth + depth_over_limit
        event(f"max_depth={max_depth}")
        event(f"depth_over_limit={depth_over_limit}")
        event(f"total_nesting={total}")
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
    def test_junk_separator_logic_property(self, leading_char: str, has_content: bool) -> None:
        """Junk separator logic handles various leading characters correctly."""
        is_ws = leading_char in ("\n", " ", "\t")
        event(f"leading_char_is_whitespace={is_ws}")
        event(f"has_content={has_content}")
        msg = Message(
            id=Identifier(name="m"),
            value=Pattern(elements=(TextElement(value="v"),)),
            attributes=(),
        )

        junk = Junk(content=f"{leading_char}content") if has_content else Junk(content="")

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
            value=Pattern(elements=(TextElement(value="No braces here, just plain text!"),)),
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
            value=Pattern(elements=(TextElement(value="Hello, world! How are you?"),)),
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
            value=Pattern(elements=(TextElement(value="Price: $42.00 (20% off)"),)),
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
        event(f"input_len={len(text)}")
        assume(text.strip())  # Non-empty after stripping
        # Leading whitespace gets wrapped in a StringLiteral placeable for
        # roundtrip correctness (see _serialize_pattern); not this test's concern.
        assume(not text[0].isspace())

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
