"""Tests for syntax.serializer: FluentSerializer, serialize(), edge cases, internal helpers.

Validates serialization of AST nodes back to FTL syntax, including control character
escaping, depth limits, junk entries, multiline patterns, and classify/escape internals.
"""

from __future__ import annotations

from ftllexengine.syntax import serialize
from ftllexengine.syntax.ast import (
    Identifier,
    Junk,
    Message,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer_lines import _classify_line, _escape_text, _LineKind

# =============================================================================
# _classify_line unit tests (covers lines 358, 361)
# =============================================================================


class TestClassifyLine:
    """Direct unit tests for _classify_line continuation line classifier."""

    def test_empty_line(self) -> None:
        """Empty string classified as EMPTY."""
        kind, ws_len = _classify_line("")
        assert kind is _LineKind.EMPTY
        assert ws_len == 0

    def test_whitespace_only_single_space(self) -> None:
        """Single space classified as WHITESPACE_ONLY."""
        kind, ws_len = _classify_line(" ")
        assert kind is _LineKind.WHITESPACE_ONLY
        assert ws_len == 0

    def test_whitespace_only_multiple_spaces(self) -> None:
        """Multiple spaces classified as WHITESPACE_ONLY."""
        kind, ws_len = _classify_line("     ")
        assert kind is _LineKind.WHITESPACE_ONLY
        assert ws_len == 0

    def test_syntax_leading_dot_no_whitespace(self) -> None:
        """Dot at position 0 classified as SYNTAX_LEADING with ws_len=0."""
        kind, ws_len = _classify_line(".")
        assert kind is _LineKind.SYNTAX_LEADING
        assert ws_len == 0

    def test_syntax_leading_dot_with_whitespace(self) -> None:
        """Dot preceded by spaces classified as SYNTAX_LEADING."""
        kind, ws_len = _classify_line("   .attr")
        assert kind is _LineKind.SYNTAX_LEADING
        assert ws_len == 3

    def test_syntax_leading_asterisk(self) -> None:
        """Asterisk preceded by spaces classified as SYNTAX_LEADING."""
        kind, ws_len = _classify_line("   *")
        assert kind is _LineKind.SYNTAX_LEADING
        assert ws_len == 3

    def test_syntax_leading_bracket(self) -> None:
        """Open bracket preceded by spaces classified as SYNTAX_LEADING."""
        kind, ws_len = _classify_line("  [key]")
        assert kind is _LineKind.SYNTAX_LEADING
        assert ws_len == 2

    def test_normal_text(self) -> None:
        """Regular text classified as NORMAL."""
        kind, ws_len = _classify_line("hello")
        assert kind is _LineKind.NORMAL
        assert ws_len == 0

    def test_normal_text_with_leading_whitespace(self) -> None:
        """Text with leading whitespace but non-syntax first char is NORMAL."""
        kind, ws_len = _classify_line("   hello")
        assert kind is _LineKind.NORMAL
        assert ws_len == 0

    def test_dot_after_text_is_normal(self) -> None:
        """Dot NOT as first non-ws character is NORMAL."""
        kind, ws_len = _classify_line("x.y")
        assert kind is _LineKind.NORMAL
        assert ws_len == 0


# =============================================================================
# _escape_text unit tests (covers brace escaping paths)
# =============================================================================


class TestEscapeText:
    """Direct unit tests for _escape_text brace escaping."""

    def test_no_braces(self) -> None:
        """Text without braces passes through unchanged."""
        output: list[str] = []
        _escape_text("hello world", output)
        assert "".join(output) == "hello world"

    def test_open_brace(self) -> None:
        """Open brace escaped as StringLiteral placeable."""
        output: list[str] = []
        _escape_text("before{after", output)
        assert "".join(output) == 'before{ "{" }after'

    def test_close_brace(self) -> None:
        """Close brace escaped as StringLiteral placeable."""
        output: list[str] = []
        _escape_text("x}y", output)
        assert "".join(output) == 'x{ "}" }y'

    def test_both_braces(self) -> None:
        """Both brace types escaped."""
        output: list[str] = []
        _escape_text("{}", output)
        assert "".join(output) == '{ "{" }{ "}" }'

    def test_empty_text(self) -> None:
        """Empty text produces no output."""
        output: list[str] = []
        _escape_text("", output)
        assert output == []

    def test_only_open_brace(self) -> None:
        """Single open brace."""
        output: list[str] = []
        _escape_text("{", output)
        assert "".join(output) == '{ "{" }'

    def test_braces_in_middle_of_text(self) -> None:
        """Braces surrounded by text."""
        output: list[str] = []
        _escape_text("a{b}c", output)
        assert "".join(output) == 'a{ "{" }b{ "}" }c'

    def test_consecutive_braces(self) -> None:
        """Multiple consecutive braces."""
        output: list[str] = []
        _escape_text("{{", output)
        assert "".join(output) == '{ "{" }{ "{" }'


# =============================================================================
# _emit_classified_line integration tests (covers lines 742-751)
# =============================================================================


class TestEmitClassifiedLineCoverage:
    """Roundtrip tests that exercise _emit_classified_line branches."""

    _parser = FluentParserV1()

    def _roundtrip_check(self, result: str) -> None:
        """Verify parse-serialize roundtrip produces no Junk and is idempotent."""
        reparsed = self._parser.parse(result)
        assert not any(isinstance(e, Junk) for e in reparsed.entries)
        s2 = serialize(reparsed)
        assert result == s2

    def test_whitespace_only_continuation_line(self) -> None:
        """Multiline text with whitespace-only continuation (lines 742-744)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="line1\n   \nline3"),)),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert '{ "   " }' in result
        self._roundtrip_check(result)

    def test_syntax_leading_dot(self) -> None:
        """Continuation line with dot as first non-ws char (lines 746-751)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="line1\n.attr"),)),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert '{ "." }' in result
        self._roundtrip_check(result)

    def test_syntax_leading_with_ws_prefix(self) -> None:
        """Syntax char preceded by whitespace (ws_len > 0 branch).

        Content spaces before the syntax char are wrapped in a StringLiteral
        placeable so the parser cannot absorb them as structural indent.
        """
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="line1\n   .something"),)),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert '{ "   " }' in result  # Content spaces wrapped
        assert '{ "." }' in result  # Syntax char wrapped
        self._roundtrip_check(result)

    def test_syntax_leading_with_remaining_text(self) -> None:
        """Syntax char followed by additional text (remaining branch)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="line1\n*default value"),)),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert '{ "*" }' in result
        assert "default value" in result
        self._roundtrip_check(result)

    def test_syntax_leading_bracket_with_content(self) -> None:
        """Bracket syntax char with trailing content."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="line1\n[not a variant"),)),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert '{ "[" }' in result
        self._roundtrip_check(result)

    def test_syntax_leading_ws_prefix_roundtrip_promoted(self) -> None:
        """Content spaces before syntax char survive parse-serialize roundtrip.

        Promoted from Atheris fuzzer finding (finding_0001): convergence failure
        S(AST) != S(P(S(AST))) when continuation line had content whitespace
        before a wrapped syntax character. The parser absorbed content spaces
        as structural indent during common-indent stripping.
        """
        msg = Message(
            id=Identifier(name="fuec"),
            value=Pattern(elements=(TextElement(value="    dS7aQ\n      .h?Q"),)),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        # Leading 4 spaces wrapped at pattern level
        assert '{ "    " }' in result
        # Content spaces before syntax char wrapped at line level
        assert '{ "      " }' in result
        assert '{ "." }' in result
        self._roundtrip_check(result)

    def test_syntax_char_only_no_remaining(self) -> None:
        """Continuation line is just a syntax char, no remaining text (750->exit)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="line1\n."),)),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert '{ "." }' in result
        reparsed = self._parser.parse(result)
        assert not any(isinstance(e, Junk) for e in reparsed.entries)


# =============================================================================
# Pattern edge cases (covers lines 643->645, 699-700, 723->690, 871->874)
# =============================================================================


class TestPatternEmissionEdgeCases:
    """Tests for pattern serialization edge cases."""

    _parser = FluentParserV1()

    def test_first_text_element_all_spaces(self) -> None:
        """First TextElement is all spaces: leading_ws consumed entirely (lines 699-700)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    TextElement(value="   "),
                    Placeable(expression=VariableReference(id=Identifier(name="x"))),
                )
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert '{ "   " }' in result
        assert "$x" in result

    def test_placeable_not_last_element(self) -> None:
        """Placeable followed by TextElement (loop continuation 723->690)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    Placeable(expression=VariableReference(id=Identifier(name="name"))),
                    TextElement(value=" said hello"),
                )
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert "$name" in result
        assert "said hello" in result

    def test_intra_element_separate_line_trigger(self) -> None:
        """Single TextElement with embedded newline + NORMAL leading ws (643->645)."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=(TextElement(value="line1\n  normal with leading whitespace"),)),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        # Separate-line mode activated: pattern starts on new line
        assert result.startswith("test = \n    ")
        # Roundtrip
        reparsed = self._parser.parse(result)
        assert not any(isinstance(e, Junk) for e in reparsed.entries)

    def _roundtrip_convergence(self, source: str) -> None:
        """Verify S(P(x)) == S(P(S(P(x)))) for an FTL source string."""
        parsed = self._parser.parse(source)
        s1 = serialize(parsed)
        reparsed = self._parser.parse(s1)
        s2 = serialize(reparsed)
        assert s1 == s2, f"Convergence failure:\nS1: {s1!r}\nS2: {s2!r}"

    def test_cross_element_ws_only_no_separate_line_promoted(self) -> None:
        """WHITESPACE_ONLY cross-element does not trigger separate-line mode.

        Promoted from Atheris roundtrip fuzzer finding: convergence failure
        S(P(x)) != S(P(S(P(x)))) when a whitespace-only TextElement followed
        a newline-ending TextElement. The cross-element check triggered
        separate-line mode; the serializer wrapped the spaces in a Placeable;
        on re-parse the Placeable was opaque to the cross-element check,
        so separate-line mode did not trigger, producing different output.
        """
        self._roundtrip_convergence("aaaaa =\n    h\n           \n")

    def test_cross_element_ws_only_direct_ast(self) -> None:
        """Cross-element WHITESPACE_ONLY: inline mode, content wrapped."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    TextElement(value="h\n"),
                    TextElement(value="       "),
                )
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        # Should NOT use separate-line mode (WHITESPACE_ONLY handled by wrapping)
        assert result.startswith("test = h")
        assert '{ "       " }' in result
        reparsed = self._parser.parse(result)
        assert not any(isinstance(e, Junk) for e in reparsed.entries)
        s2 = serialize(reparsed)
        assert result == s2

    def test_cross_element_syntax_leading_no_separate_line(self) -> None:
        """Cross-element SYNTAX_LEADING: inline mode, content wrapped."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    TextElement(value="h\n"),
                    TextElement(value="   .dotcontent"),
                )
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        # Should NOT use separate-line mode (SYNTAX_LEADING handled by wrapping)
        assert result.startswith("test = h")
        assert '{ "   " }' in result
        assert '{ "." }' in result
        reparsed = self._parser.parse(result)
        assert not any(isinstance(e, Junk) for e in reparsed.entries)
        s2 = serialize(reparsed)
        assert result == s2

    def test_cross_element_normal_still_triggers_separate_line(self) -> None:
        """Cross-element NORMAL: separate-line mode correctly activates."""
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(
                    TextElement(value="h\n"),
                    TextElement(value="  normal text"),
                )
            ),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        # NORMAL with leading whitespace needs separate-line mode
        assert result.startswith("test = \n    ")
        reparsed = self._parser.parse(result)
        assert not any(isinstance(e, Junk) for e in reparsed.entries)

    def test_number_literal_variant_key(self) -> None:
        """SelectExpression with NumberLiteral variant key (line 871->874)."""
        sel = SelectExpression(
            selector=VariableReference(id=Identifier(name="count")),
            variants=(
                Variant(
                    key=NumberLiteral(value=1, raw="1"),
                    value=Pattern(elements=(TextElement(value="one item"),)),
                ),
                Variant(
                    key=Identifier(name="other"),
                    value=Pattern(elements=(TextElement(value="many items"),)),
                    default=True,
                ),
            ),
        )
        msg = Message(
            id=Identifier(name="items"),
            value=Pattern(elements=(Placeable(expression=sel),)),
            attributes=(),
        )
        result = serialize(Resource(entries=(msg,)))
        assert "[1]" in result
        assert "[other]" in result
