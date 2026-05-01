# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_syntax_serializer_property.py."""

from tests.fuzz_syntax_serializer_property_cases import *  # noqa: F403 - shared split test support

# =============================================================================
# SYNTAX_LEADING Roundtrip Properties (Full Path)
# =============================================================================


class TestSyntaxLeadingRoundtripProperties:
    """Test full serialize-parse-serialize for syntax-leading lines.

    Continuation lines starting with . * [ need wrapping as
    StringLiteral placeables to prevent parser misinterpretation.
    """

    _parser = FluentParserV1()

    @given(
        syntax_char=st.sampled_from([".", "*", "["]),
        ws=st.integers(min_value=0, max_value=6),
        suffix=st.text(
            alphabet=st.characters(
                codec="utf-8",
                categories=("L", "N"),
            ),
            min_size=0,
            max_size=20,
        ),
    )
    def test_syntax_leading_roundtrip(
        self, syntax_char: str, ws: int, suffix: str
    ) -> None:
        """PROPERTY: Syntax-leading continuation lines roundtrip.

        Events emitted:
        - syntax_char={char}: Which syntax character
        - ws_prefix={n}: Leading whitespace before syntax char
        - has_suffix={bool}: Whether trailing text follows
        - line_kind=SYNTAX_LEADING: Confirm classification
        """
        event(f"syntax_char={syntax_char}")
        event(f"ws_prefix={ws}")
        has_suffix = len(suffix) > 0
        event(f"has_suffix={has_suffix}")

        line = " " * ws + syntax_char + suffix
        kind, _ = _classify_line(line)
        event(f"line_kind={kind.name}")

        text_val = f"line1\n{line}"
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(TextElement(value=text_val),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)

        # Must contain the syntax char wrapped as placeable
        escaped = f'{{ "{syntax_char}" }}'
        assert escaped in result

        # Parse: no Junk entries
        reparsed = self._parser.parse(result)
        assert not any(
            isinstance(e, Junk)
            for e in reparsed.entries
        )

    @given(
        syntax_char=st.sampled_from([".", "*", "["]),
    )
    def test_syntax_char_only_roundtrip(
        self, syntax_char: str
    ) -> None:
        """PROPERTY: Line with only syntax char roundtrips.

        Events emitted:
        - syntax_char={char}: Which syntax character
        - line_kind=SYNTAX_LEADING: Classification
        - has_suffix=False: No trailing text
        """
        event(f"syntax_char={syntax_char}")
        event("has_suffix=False")

        kind, _ = _classify_line(syntax_char)
        event(f"line_kind={kind.name}")

        text_val = f"first line\n{syntax_char}"
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(TextElement(value=text_val),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)
        escaped = f'{{ "{syntax_char}" }}'
        assert escaped in result

        reparsed = self._parser.parse(result)
        assert not any(
            isinstance(e, Junk)
            for e in reparsed.entries
        )

    @given(
        n_spaces=st.integers(min_value=1, max_value=10),
    )
    def test_whitespace_only_continuation_roundtrip(
        self, n_spaces: int
    ) -> None:
        """PROPERTY: Whitespace-only continuation lines roundtrip.

        Events emitted:
        - spaces={n}: Number of spaces
        - line_kind=WHITESPACE_ONLY: Classification
        """
        event(f"spaces={n_spaces}")

        ws_line = " " * n_spaces
        kind, _ = _classify_line(ws_line)
        event(f"line_kind={kind.name}")

        text_val = f"first line\n{ws_line}\nthird line"
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(TextElement(value=text_val),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))

        result = serialize(resource, validate=True)
        # Whitespace-only wrapped as placeable
        assert f'{{ "{ws_line}" }}' in result

        reparsed = self._parser.parse(result)
        assert not any(
            isinstance(e, Junk)
            for e in reparsed.entries
        )
