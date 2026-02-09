"""Tests for serializer roundtrip correctness with programmatic ASTs.

Validates that patterns constructed programmatically (not via parser) preserve
significant whitespace during serialize-parse roundtrips. Parser-produced ASTs
split TextElements at newlines; programmatic ASTs may embed newlines within a
single TextElement, requiring the serializer to detect and handle embedded
indentation correctly.

Property: for any programmatically constructed Pattern with embedded newlines
and whitespace, serialize(parse(serialize(AST))) is stable.
"""

from __future__ import annotations

from hypothesis import event, example, given, settings
from hypothesis import strategies as st

from ftllexengine.syntax.ast import (
    Identifier,
    Message,
    Pattern,
    Resource,
    TextElement,
)
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import FluentSerializer

_parser = FluentParserV1()
_serializer = FluentSerializer()


def _roundtrip_pattern_value(pattern_text: str) -> str:
    """Create a programmatic AST, serialize, parse, and return pattern value."""
    msg = Message(
        id=Identifier(name="msg", span=None),
        value=Pattern(elements=(TextElement(value=pattern_text),)),
        attributes=(),
        comment=None,
        span=None,
    )
    resource = Resource(entries=(msg,))
    serialized = _serializer.serialize(resource)
    parsed = _parser.parse(serialized)
    entry = parsed.entries[0]
    assert hasattr(entry, "value")
    assert entry.value is not None
    return "".join(
        el.value for el in entry.value.elements  # type: ignore[union-attr]
    )


class TestEmbeddedNewlineWhitespace:
    """Roundtrip preservation of embedded newlines with significant whitespace."""

    def test_five_space_indent(self) -> None:
        """Embedded newline with 5-space indent preserved through roundtrip."""
        original = "foo\n     bar"
        assert _roundtrip_pattern_value(original) == original

    def test_four_space_indent(self) -> None:
        """Embedded newline with exactly 4-space indent (boundary case)."""
        original = "foo\n    bar"
        assert _roundtrip_pattern_value(original) == original

    def test_single_space_indent(self) -> None:
        """Embedded newline with single space indent."""
        original = "foo\n bar"
        assert _roundtrip_pattern_value(original) == original

    def test_multiple_newlines_varying_indent(self) -> None:
        """Multiple embedded newlines with different indentation levels."""
        original = "a\n  b\n    c\n      d"
        assert _roundtrip_pattern_value(original) == original

    def test_no_whitespace_after_newline(self) -> None:
        """Embedded newline without whitespace does not trigger separate-line."""
        original = "hello\nworld"
        assert _roundtrip_pattern_value(original) == original

    def test_trailing_newline_no_whitespace(self) -> None:
        """Trailing newline at end of text element."""
        original = "hello\n"
        result = _roundtrip_pattern_value(original)
        # Trailing newline may be normalized during parse
        assert result.rstrip("\n") == "hello"

    def test_tab_after_newline(self) -> None:
        """Tab character after newline (not space, no separate-line needed).

        Only space characters trigger separate-line serialization per the
        FTL spec's whitespace handling (tab is not continuation indent).
        """
        original = "foo\n\tbar"
        assert _roundtrip_pattern_value(original) == original


def _extract_element_values(resource: Resource) -> list[str]:
    """Extract text element values from the first entry's pattern."""
    entry = resource.entries[0]
    assert hasattr(entry, "value")
    assert entry.value is not None
    return [el.value for el in entry.value.elements]  # type: ignore[union-attr]


class TestParserProducedRoundtrip:
    """Verify existing parser-produced roundtrip behavior is preserved."""

    def test_separate_line_with_extra_indent(self) -> None:
        """Parser-produced AST from FTL with extra indentation."""
        ftl = "msg =\n    foo\n         bar\n"
        resource = _parser.parse(ftl)
        serialized = _serializer.serialize(resource)
        resource2 = _parser.parse(serialized)
        assert _extract_element_values(resource) == _extract_element_values(resource2)

    def test_inline_start_multiline(self) -> None:
        """Inline pattern start with continuation line."""
        ftl = "msg = foo\n    bar\n"
        resource = _parser.parse(ftl)
        serialized = _serializer.serialize(resource)
        resource2 = _parser.parse(serialized)
        assert _extract_element_values(resource) == _extract_element_values(resource2)


class TestSerializerStability:
    """Serialize-parse-serialize stability (idempotence after first roundtrip)."""

    @given(
        indent=st.integers(min_value=1, max_value=12),
        line_count=st.integers(min_value=2, max_value=5),
    )
    @settings(max_examples=100)
    @example(indent=1, line_count=2)
    @example(indent=4, line_count=2)
    @example(indent=5, line_count=3)
    def test_embedded_indent_stability(self, indent: int, line_count: int) -> None:
        """After first roundtrip, subsequent roundtrips are stable.

        Constructs patterns with N lines, each indented by `indent` spaces.
        After initial serialize-parse, the result must be stable on
        subsequent serialize-parse cycles.
        """
        event(f"indent={indent}")
        event(f"line_count={line_count}")
        lines = [f"{'  ' * indent}line{i}" if i > 0 else "first" for i in range(line_count)]
        original = "\n".join(lines)

        # First roundtrip
        first_rt = _roundtrip_pattern_value(original)

        # Second roundtrip from the first result
        msg2 = Message(
            id=Identifier(name="msg", span=None),
            value=Pattern(elements=(TextElement(value=first_rt),)),
            attributes=(),
            comment=None,
            span=None,
        )
        resource2 = Resource(entries=(msg2,))
        serialized2 = _serializer.serialize(resource2)
        parsed2 = _parser.parse(serialized2)
        entry2 = parsed2.entries[0]
        assert hasattr(entry2, "value")
        assert entry2.value is not None
        second_rt = "".join(
            el.value for el in entry2.value.elements  # type: ignore[union-attr]
        )

        # Stability: second roundtrip equals first roundtrip
        assert first_rt == second_rt, (
            f"Roundtrip not stable: first={first_rt!r}, second={second_rt!r}"
        )
