# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_core.py."""

from tests.syntax_parser_core_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# TestParserEntryRecovery
# ============================================================================


class TestParserEntryRecovery:
    """Parser entry recovery: empty input, CRLF, messages, terms, junk.

    Verifies the parser handles empty/whitespace input, CRLF line endings,
    message and term parsing basics, and junk creation for invalid content.
    """

    # -- Empty / whitespace ------------------------------------------------

    def test_empty_source(self) -> None:
        """Empty source produces empty resource."""
        parser = FluentParserV1()
        resource = parser.parse("")
        assert resource is not None
        assert len(resource.entries) == 0

    def test_whitespace_only(self) -> None:
        """Whitespace-only source produces empty resource."""
        parser = FluentParserV1()
        resource = parser.parse("   \n\n    \n")
        assert resource is not None
        assert len(resource.entries) == 0

    # -- CRLF handling -----------------------------------------------------

    def test_crlf_line_endings(self) -> None:
        """Parser handles CRLF line endings."""
        parser = FluentParserV1()
        resource = parser.parse("msg1 = value1\r\nmsg2 = value2\r\n")
        assert resource is not None
        assert len(resource.entries) >= 2

    # -- Message parsing ---------------------------------------------------

    def test_simple_message(self) -> None:
        """Simple message parsing."""
        parser = FluentParserV1()
        resource = parser.parse("msg = value")
        assert resource is not None
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)

    def test_multiple_messages(self) -> None:
        """Multiple messages."""
        parser = FluentParserV1()
        resource = parser.parse(
            "msg1 = value1\nmsg2 = value2\nmsg3 = value3\n"
        )
        assert resource is not None
        assert len(resource.entries) == 3

    # -- Term parsing ------------------------------------------------------

    def test_simple_term(self) -> None:
        """Simple term parsing."""
        parser = FluentParserV1()
        resource = parser.parse("-term = value")
        assert resource is not None
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Term)

    def test_term_with_id(self) -> None:
        """Term preserves identifier."""
        parser = FluentParserV1()
        resource = parser.parse("-my-term = Term Value")
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Term)
        assert resource.entries[0].id.name == "my-term"

    def test_multiple_terms(self) -> None:
        """Multiple terms."""
        parser = FluentParserV1()
        source = "-term1 = Value 1\n-term2 = Value 2\n-term3 = Value 3\n"
        resource = parser.parse(source)
        assert len(resource.entries) == 3
        assert all(isinstance(e, Term) for e in resource.entries)

    def test_term_with_attributes(self) -> None:
        """Term with attributes."""
        parser = FluentParserV1()
        source = "-term = Main Value\n    .attr = Attribute Value\n"
        resource = parser.parse(source)
        assert len(resource.entries) >= 1

    def test_term_and_message_coexist(self) -> None:
        """Terms and messages in same resource."""
        parser = FluentParserV1()
        source = "-term = term value\nmsg = message value\n"
        resource = parser.parse(source)
        assert len(resource.entries) == 2

    def test_failed_term_parsing(self) -> None:
        """Parser handles failed term parsing (dash not followed by valid term)."""
        parser = FluentParserV1()
        result = parser.parse("- invalid\n")
        assert result is not None
        assert len(result.entries) > 0

    # -- Junk handling -----------------------------------------------------

    def test_junk_creates_entry(self) -> None:
        """Unparseable content creates Junk entry."""
        parser = FluentParserV1()
        resource = parser.parse("%%% invalid syntax")
        assert resource is not None
        assert len(resource.entries) > 0
        assert any(isinstance(e, Junk) for e in resource.entries)

    def test_junk_continues_parsing(self) -> None:
        """Parser continues after junk entry."""
        parser = FluentParserV1()
        resource = parser.parse("%%% invalid\nmsg = valid message\n")
        assert resource is not None
        assert len(resource.entries) >= 2

    def test_multiline_junk(self) -> None:
        """Multi-line junk handling."""
        parser = FluentParserV1()
        source = "%%% line 1\n    line 2\n    line 3\nmsg = valid\n"
        resource = parser.parse(source)
        assert resource is not None
        assert len(resource.entries) > 0

    def test_junk_eof_with_trailing_spaces(self) -> None:
        """Junk parsing handles trailing spaces at EOF."""
        parser = FluentParserV1()
        resource = parser.parse("%%% invalid   ")
        assert resource is not None
        assert len(resource.entries) > 0
        assert isinstance(resource.entries[0], Junk)

    def test_junk_trailing_spaces_at_eof(self) -> None:
        """Junk with trailing spaces at EOF."""
        parser = FluentParserV1()
        resource = parser.parse("invalid syntax    ")
        assert resource is not None

    def test_multiline_junk_ends_at_eof(self) -> None:
        """Multiline junk ending at EOF."""
        parser = FluentParserV1()
        source = "invalid line 1\n    invalid line 2\n    "
        resource = parser.parse(source)
        assert resource is not None
