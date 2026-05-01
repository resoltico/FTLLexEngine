# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_syntax_serializer_property.py."""

from tests.fuzz_syntax_serializer_property_cases import *  # noqa: F403 - shared split test support

# =============================================================================
# Control Character StringLiteral Properties
# =============================================================================


class TestControlCharStringLiteralProperties:
    """Test StringLiteral escaping for all control characters.

    Serializer uses \\uHHHH for chars < 0x20 and 0x7F. Verify
    this encoding for the full control character range.
    """

    @given(
        code=st.integers(min_value=0, max_value=0x1F),
    )
    def test_c0_control_chars_escaped(self, code: int) -> None:
        """PROPERTY: C0 control chars (0x00-0x1F) use \\uHHHH.

        Events emitted:
        - control_char_code={n}: Character code point
        - outcome=control_char_escaped: Escape verified
        """
        event(f"control_char_code={code}")

        char = chr(code)
        lit = StringLiteral(value=f"a{char}b")
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(Placeable(expression=lit),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)
        expected_escape = f"\\u{code:04X}"
        assert expected_escape in result
        event("outcome=control_char_escaped")

    def test_del_char_escaped(self) -> None:
        """DEL character (0x7F) uses \\u007F encoding."""
        lit = StringLiteral(value="a\x7Fb")
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(Placeable(expression=lit),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)
        assert "\\u007F" in result

    @given(
        code=st.sampled_from(
            [0x00, 0x01, 0x08, 0x09, 0x0A, 0x0C, 0x0D,
             0x1B, 0x1F, 0x7F]
        ),
    )
    def test_control_char_roundtrip(self, code: int) -> None:
        """PROPERTY: Control chars roundtrip through parse/serialize.

        Events emitted:
        - control_char_code={n}: Character code point
        - outcome=control_roundtrip_ok: Roundtrip succeeded
        """
        event(f"control_char_code={code}")

        char = chr(code)
        lit = StringLiteral(value=f"x{char}y")
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(Placeable(expression=lit),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        serialized = serialize(resource, validate=True)
        parser = FluentParserV1()
        reparsed = parser.parse(serialized)
        assert len(reparsed.entries) == 1
        assert not any(
            isinstance(e, Junk) for e in reparsed.entries
        )
        event("outcome=control_roundtrip_ok")
