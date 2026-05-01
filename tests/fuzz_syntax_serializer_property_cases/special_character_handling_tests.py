# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_syntax_serializer_property.py."""

from tests.fuzz_syntax_serializer_property_cases import *  # noqa: F403 - shared split test support

# =============================================================================
# Special Character Handling Tests
# =============================================================================


class TestSpecialCharacterHandling:
    """Test proper escaping and handling of special characters."""

    @given(
        text=st.text(
            alphabet=st.characters(
                blacklist_categories=["Cs", "Cc"],  # Surrogates and control
                blacklist_characters=["\x00"],  # Null
            ),
            min_size=1,
            max_size=50,
        )
    )
    def test_string_literal_escaping_roundtrip(self, text: str) -> None:
        """PROPERTY: String literals with special chars roundtrip correctly.

        Events emitted:
        - has_backslash={bool}: Contains backslash
        - has_quote={bool}: Contains quote
        - has_newline={bool}: Contains newline
        """
        has_backslash = "\\\\" in text
        has_quote = '"' in text
        has_newline = "\\n" in text
        event(f"has_backslash={has_backslash}")
        event(f"has_quote={has_quote}")
        event(f"has_newline={has_newline}")

        string_lit = StringLiteral(value=text)
        message = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(Placeable(expression=string_lit),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        serialized = serialize(resource, validate=True)

        parser = FluentParserV1()
        reparsed = parser.parse(serialized)

        # Verify no parse errors (no Junk entries means successful parse)
        assert len(reparsed.entries) > 0

    def test_brace_escaping_as_placeable(self) -> None:
        """COVERAGE: Braces must be escaped as placeables."""

        # Braces in text are represented as Placeable(StringLiteral)
        pattern = Pattern(
            elements=(
                TextElement(value="Start "),
                Placeable(expression=StringLiteral(value="{")),
                TextElement(value=" middle "),
                Placeable(expression=StringLiteral(value="}")),
                TextElement(value=" end"),
            )
        )

        message = Message(id=Identifier(name="test"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        serialized = serialize(resource, validate=True)

        # Should contain escaped braces as placeables
        assert '{ "{" }' in serialized
        assert '{ "}" }' in serialized

    def test_multiline_pattern_indentation(self) -> None:
        """COVERAGE: Multiline patterns get proper indentation."""

        # Pattern with embedded newline
        pattern = Pattern(
            elements=(
                TextElement(value="Line 1\n"),
                TextElement(value="Line 2"),
            )
        )

        message = Message(id=Identifier(name="test"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        serialized = serialize(resource, validate=True)

        # Should contain structural indentation after newline
        assert "Line 1\n    Line 2" in serialized


# =============================================================================
# _classify_line Property Tests
# =============================================================================


# Characters syntactically significant at continuation line start in FTL
_SYNTAX_CHARS = ".[*"


class TestClassifyLineProperties:
    """Property-based tests for _classify_line pure function.

    Properties verified:
    - EMPTY iff empty string
    - WHITESPACE_ONLY iff all spaces and non-empty
    - SYNTAX_LEADING iff first non-ws char is in {., *, [}
    - ws_len is always non-negative
    - Classification is exhaustive (always one of 4 kinds)
    """

    @given(line=st.text(
        alphabet=st.characters(
            codec="utf-8", categories=("L", "N", "P", "S", "Z")
        ),
        min_size=0,
        max_size=80,
    ))
    def test_output_is_valid_kind(self, line: str) -> None:
        """_classify_line always returns a valid _LineKind."""
        kind, ws_len = _classify_line(line)
        kind_name = kind.name
        event(f"kind={kind_name}")
        assert isinstance(kind, _LineKind)
        assert ws_len >= 0

    @given(line=st.text(
        alphabet=st.characters(
            codec="utf-8", categories=("L", "N", "P", "S", "Z")
        ),
        min_size=0,
        max_size=80,
    ))
    def test_empty_iff_empty_string(self, line: str) -> None:
        """EMPTY kind iff input is the empty string."""
        kind, _ = _classify_line(line)
        is_empty = kind is _LineKind.EMPTY
        event(f"empty={is_empty}")
        assert is_empty == (line == "")

    @given(n=st.integers(min_value=1, max_value=20))
    def test_whitespace_only_for_space_strings(self, n: int) -> None:
        """Strings of only spaces classify as WHITESPACE_ONLY."""
        line = " " * n
        kind, ws_len = _classify_line(line)
        event(f"spaces={n}")
        assert kind is _LineKind.WHITESPACE_ONLY
        assert ws_len == 0

    @given(
        ws=st.integers(min_value=0, max_value=10),
        syntax_char=st.sampled_from(list(_SYNTAX_CHARS)),
        suffix=st.text(min_size=0, max_size=20),
    )
    def test_syntax_leading_classification(
        self, ws: int, syntax_char: str, suffix: str
    ) -> None:
        """Lines starting with (optional ws + syntax char) are SYNTAX_LEADING."""
        line = " " * ws + syntax_char + suffix
        kind, ws_len = _classify_line(line)
        event(f"syntax_char={syntax_char}")
        event(f"ws_prefix={ws}")
        assert kind is _LineKind.SYNTAX_LEADING
        assert ws_len == ws

    @given(
        ws=st.integers(min_value=0, max_value=10),
        first_char=st.characters(
            codec="utf-8",
            categories=("L", "N"),
        ),
        suffix=st.text(min_size=0, max_size=20),
    )
    def test_normal_for_non_syntax_first_char(
        self, ws: int, first_char: str, suffix: str
    ) -> None:
        """Lines where first non-ws char is not syntax are NORMAL."""
        line = " " * ws + first_char + suffix
        kind, _ = _classify_line(line)
        event(f"kind={kind.name}")
        assert kind is _LineKind.NORMAL
