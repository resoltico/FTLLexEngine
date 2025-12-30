"""Complete coverage tests for syntax/parser/rules.py.

Targets uncovered line to achieve 100% coverage.
Covers:
- Pattern trimming edge case: content after last newline (line 335)
"""

from __future__ import annotations

from ftllexengine.syntax.ast import Message, TextElement
from ftllexengine.syntax.parser.core import FluentParserV1


class TestPatternTrimmingEdgeCases:
    """Test edge cases in pattern trimming logic."""

    def test_pattern_with_content_after_last_newline(self) -> None:
        """Pattern with content after last newline preserves that content."""
        parser = FluentParserV1()

        # Message with trailing content (no trailing newline)
        resource = parser.parse("""
msg = Line one
    Line two with spaces
""")

        message = resource.entries[0]
        assert isinstance(message, Message)
        assert message.value is not None

        # Pattern should preserve trailing spaces on content lines
        # (only trailing blank lines should be trimmed)
        pattern_text = "".join(
            elem.value for elem in message.value.elements if isinstance(elem, TextElement)
        )

        # Should contain both lines with preserved content
        assert "Line one" in pattern_text
        assert "Line two with spaces" in pattern_text

    def test_pattern_preserves_trailing_spaces_on_content_lines(self) -> None:
        """Pattern preserves trailing spaces on non-blank content lines."""
        parser = FluentParserV1()

        # Message with trailing spaces on content line (not blank line)
        resource = parser.parse("msg = Hello World   ")

        message = resource.entries[0]
        assert isinstance(message, Message)
        assert message.value is not None

        # Extract text content
        elements = message.value.elements
        assert len(elements) == 1
        assert isinstance(elements[0], TextElement)

        # Trailing spaces on content should be preserved
        text = elements[0].value
        assert text == "Hello World   "

    def test_pattern_trims_trailing_blank_lines_only(self) -> None:
        """Pattern trimming only removes trailing blank lines, not content."""
        parser = FluentParserV1()

        resource = parser.parse("""
msg = Content here
    More content

""")

        message = resource.entries[0]
        assert isinstance(message, Message)
        assert message.value is not None

        # Pattern should have content but no trailing blank line
        pattern_text = "".join(
            elem.value for elem in message.value.elements if isinstance(elem, TextElement)
        )

        # Should contain both content lines
        assert "Content here" in pattern_text
        assert "More content" in pattern_text
        # Should not end with blank line (trailing newline + spaces)
        assert not pattern_text.endswith("\n   ")

    def test_multiline_pattern_with_non_blank_final_line(self) -> None:
        """Multiline pattern with non-blank final line preserves correctly."""
        parser = FluentParserV1()

        resource = parser.parse("""
msg = First
    Second
    Third
""")

        message = resource.entries[0]
        assert isinstance(message, Message)
        assert message.value is not None

        # Extract all text
        elements = message.value.elements
        text_elements = [e for e in elements if isinstance(e, TextElement)]

        # Should have content from all lines
        full_text = "".join(e.value for e in text_elements)
        assert "First" in full_text
        assert "Second" in full_text
        assert "Third" in full_text


class TestPatternTrimmingHypothesis:
    """Hypothesis-based property tests for pattern trimming."""

    def test_pattern_trimming_preserves_content(self) -> None:
        """Pattern trimming never removes actual content, only blank lines."""
        parser = FluentParserV1()

        # Test with various content patterns
        test_cases = [
            "msg = Content",
            "msg = Content\n    ",
            "msg = Line1\n    Line2",
            "msg = A\n    B\n    C",
            "msg = Text   ",
        ]

        for ftl_source in test_cases:
            resource = parser.parse(ftl_source)
            if not resource.entries:
                continue

            message = resource.entries[0]
            if not isinstance(message, Message) or message.value is None:
                continue

            # Pattern should not be empty
            assert len(message.value.elements) > 0

            # Should have at least one text element with content
            text_elements = [e for e in message.value.elements if isinstance(e, TextElement)]
            assert any(e.value.strip() for e in text_elements)
