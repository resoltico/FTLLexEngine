# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_error_recovery.py."""

from tests.syntax_parser_error_recovery_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# WHITESPACE AND LINE ENDING EDGE CASES
# ============================================================================


class TestWhitespaceAndLineEndings:
    """Whitespace, CRLF, and formatting edge cases."""

    def test_crlf_multiline(self) -> None:
        """CRLF (\\r\\n) line endings in multiline pattern."""
        parser = FluentParserV1()
        res = parser.parse(
            "key =\r\n    Line one\r\n    Line two\r\n"
        )
        msg = res.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.value.elements) >= 2

    def test_mixed_line_endings(self) -> None:
        """Mixed \\r\\n and \\n line endings."""
        parser = FluentParserV1()
        res = parser.parse(
            "k1 = v1\r\nk2 = v2\nk3 = v3"
        )
        assert len(res.entries) == 3

    def test_tabs_in_pattern(self) -> None:
        """Tabs in pattern are literal text."""
        parser = FluentParserV1()
        res = parser.parse("key = value\twith\ttabs")
        assert len(res.entries) == 1

    def test_multiple_blank_lines(self) -> None:
        """Multiple consecutive blank lines between entries."""
        parser = FluentParserV1()
        res = parser.parse("k1 = v1\n\n\n\nk2 = v2")
        assert len(res.entries) == 2

    def test_empty_source(self) -> None:
        """Empty source produces empty resource."""
        parser = FluentParserV1()
        res = parser.parse("")
        assert len(res.entries) == 0

    def test_windows_crlf_entries(self) -> None:
        """Windows CRLF between entries."""
        parser = FluentParserV1()
        res = parser.parse("test = Hello\r\nworld = World\r\n")
        assert len(res.entries) == 2

    def test_text_with_stop_char_bracket(self) -> None:
        """Text stops at '[' bracket."""
        parser = FluentParserV1()
        res = parser.parse("key = text[bracket")
        msg = res.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        text_vals = [
            e.value for e in msg.value.elements
            if isinstance(e, TextElement)
        ]
        assert any("text" in v for v in text_vals)
