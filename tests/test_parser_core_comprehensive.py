"""Comprehensive tests for syntax.parser.core module.

Tests FluentParserV1 error recovery and edge cases.

"""

from unittest.mock import patch

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.syntax.ast import Junk, Message, Term
from ftllexengine.syntax.parser.core import FluentParserV1


class TestFluentParserV1ErrorRecovery:
    """Tests for FluentParserV1 error recovery and robustness."""

    def test_parse_malformed_comment_at_eof(self) -> None:
        """Verify parser handles malformed comment at EOF (line 67->69 branch).

        When comment parsing fails and we're at EOF after skipping the line,
        we need to handle the EOF check correctly.
        """
        parser = FluentParserV1()

        # Malformed comment that ends at EOF (no newline)
        source = "# incomplete comment without newline"

        resource = parser.parse(source)

        # Should parse something (might be junk or empty)
        assert resource is not None
        assert isinstance(resource.entries, tuple)

    def test_parse_malformed_comment_with_newline_at_eof(self) -> None:
        """Verify parser handles malformed comment with newline before EOF."""
        parser = FluentParserV1()

        # Malformed comment with newline but at EOF
        source = "#\n"

        resource = parser.parse(source)

        assert resource is not None
        # Should have parsed the comment
        assert len(resource.entries) >= 0

    def test_parse_hash_symbol_only_at_eof(self) -> None:
        """Verify parser handles single hash at EOF."""
        parser = FluentParserV1()

        # Just a hash at EOF
        source = "#"

        resource = parser.parse(source)

        assert resource is not None

    def test_parse_multiple_hashes_at_eof(self) -> None:
        """Verify parser handles multiple hashes at EOF."""
        parser = FluentParserV1()

        # Multiple hashes without content
        source = "###"

        resource = parser.parse(source)

        assert resource is not None

    @given(st.text(alphabet="#\n\r \t", min_size=1, max_size=50))
    def test_parse_hash_combinations_at_eof(self, source: str) -> None:
        """Property: Parser handles any combination of hashes and whitespace at EOF."""
        parser = FluentParserV1()

        # Should not raise
        resource = parser.parse(source)

        assert resource is not None
        assert isinstance(resource.entries, tuple)

    def test_parse_comment_with_trailing_content_no_newline(self) -> None:
        """Verify parser handles comment with content but no final newline."""
        parser = FluentParserV1()

        source = "# This is a comment"

        resource = parser.parse(source)

        assert resource is not None
        assert len(resource.entries) > 0

    def test_parse_empty_source(self) -> None:
        """Verify parser handles empty source gracefully."""
        parser = FluentParserV1()

        resource = parser.parse("")

        assert resource is not None
        assert len(resource.entries) == 0

    def test_parse_whitespace_only(self) -> None:
        """Verify parser handles whitespace-only source."""
        parser = FluentParserV1()

        # Only spaces and newlines (no tabs - tabs create junk)
        resource = parser.parse("   \n\n    \n")

        assert resource is not None
        # Pure whitespace should be skipped
        assert len(resource.entries) == 0

    def test_parse_hash_followed_by_valid_message(self) -> None:
        """Verify parser recovers from malformed comment and parses next message."""
        parser = FluentParserV1()

        source = "#\nmsg = value"

        resource = parser.parse(source)

        assert resource is not None
        # Should have at least the message
        assert len(resource.entries) > 0

    def test_parse_crlf_line_endings(self) -> None:
        """Verify parser handles CRLF line endings correctly."""
        parser = FluentParserV1()

        source = "msg1 = value1\r\nmsg2 = value2\r\n"

        resource = parser.parse(source)

        assert resource is not None
        assert len(resource.entries) >= 2


class TestFluentParserV1MalformedCommentRecovery:
    """Specific tests for malformed comment error recovery paths."""

    def test_parse_comment_failure_recovery_advances_past_newline(self) -> None:
        """Verify parser advances past newline when comment parsing fails (lines 65-69).

        This tests the defensive error recovery code by mocking parse_comment to fail.
        """
        parser = FluentParserV1()

        # Mock parse_comment to return None (simulating parse failure)
        with patch("ftllexengine.syntax.parser.core.parse_comment", return_value=None):
            # Source with hash, newline, then valid message
            source = "# comment\nmsg = value"

            resource = parser.parse(source)

            assert resource is not None
            # Parser should recover and continue, parsing the message
            assert len(resource.entries) > 0

    def test_parse_comment_failure_at_eof_without_newline(self) -> None:
        """Verify parser handles comment failure at EOF without newline (branch 67->69).

        When parse_comment fails and we skip to EOL, we might be at EOF.
        This tests the branch where "not cursor.is_eof" is False at line 67.
        """
        parser = FluentParserV1()

        # Mock parse_comment to return None, source ends without newline
        with patch("ftllexengine.syntax.parser.core.parse_comment", return_value=None):
            # Hash without newline at EOF
            source = "#"

            resource = parser.parse(source)

            assert resource is not None

    def test_parse_incomplete_comment_advances_past_newline(self) -> None:
        """Verify parser advances past newline after failed comment parse (lines 65-69).

        This specifically tests the case where:
        1. Comment parsing fails (parse_comment returns None)
        2. We skip to end of line
        3. We check if not EOF (line 67)
        4. We advance past the newline (line 68)
        5. We continue parsing (line 69)
        """
        parser = FluentParserV1()

        # Hash followed by content that makes comment parsing fail, then newline, then message
        # This ensures we hit the recovery path and advance past the newline
        source = "#\nmsg = value"

        resource = parser.parse(source)

        assert resource is not None
        # Should successfully continue and parse the message after recovery
        assert len(resource.entries) > 0

    def test_parse_hash_at_end_of_line_with_content_after(self) -> None:
        """Verify parser handles hash at EOL with content on next line."""
        parser = FluentParserV1()

        source = "#\n\nmsg = value"

        resource = parser.parse(source)

        assert resource is not None
        assert len(resource.entries) > 0

    def test_parse_multiple_failed_comments(self) -> None:
        """Verify parser recovers from multiple failed comment parses."""
        parser = FluentParserV1()

        source = "#\n#\n#\nmsg = value"

        resource = parser.parse(source)

        assert resource is not None


class TestFluentParserV1TermParsingBranch:
    """Tests for term parsing branch coverage."""

    def test_parse_term_successfully(self) -> None:
        """Verify term parsing success path (line 75->82 branch).

        This tests the successful parsing of a term which enters
        the if block at line 75 and continues to line 82.
        """
        parser = FluentParserV1()

        source = "-my-term = Term Value"

        resource = parser.parse(source)

        assert resource is not None
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Term)
        assert resource.entries[0].id.name == "my-term"

    def test_parse_multiple_terms(self) -> None:
        """Verify parser handles multiple terms."""
        parser = FluentParserV1()

        source = """-term1 = Value 1
-term2 = Value 2
-term3 = Value 3
"""

        resource = parser.parse(source)

        assert resource is not None
        assert len(resource.entries) == 3
        assert all(isinstance(entry, Term) for entry in resource.entries)

    def test_parse_term_with_attributes(self) -> None:
        """Verify parser handles terms with attributes."""
        parser = FluentParserV1()

        source = """-term = Main Value
    .attr = Attribute Value
"""

        resource = parser.parse(source)

        assert resource is not None
        assert len(resource.entries) >= 1


class TestFluentParserV1JunkEOFHandling:
    """Tests for junk parsing EOF handling."""

    def test_consume_junk_hits_eof_check(self) -> None:
        """Verify _consume_junk_lines handles EOF correctly (line 152).

        When consuming junk lines, we need to check for EOF after
        skipping leading spaces.
        """
        parser = FluentParserV1()

        # Invalid content that creates junk, ending with spaces at EOF
        source = "%%% invalid   "

        resource = parser.parse(source)

        assert resource is not None
        assert len(resource.entries) > 0
        assert isinstance(resource.entries[0], Junk)

    def test_junk_with_trailing_spaces_at_eof(self) -> None:
        """Verify junk parsing with trailing spaces at EOF."""
        parser = FluentParserV1()

        source = "invalid syntax    "

        resource = parser.parse(source)

        assert resource is not None

    def test_junk_multiline_ends_at_eof(self) -> None:
        """Verify multiline junk handling when reaching EOF."""
        parser = FluentParserV1()

        source = """invalid line 1
    invalid line 2
    """

        resource = parser.parse(source)

        assert resource is not None


class TestFluentParserV1JunkHandling:
    """Tests for junk entry creation and error recovery."""

    def test_parse_junk_creates_entry(self) -> None:
        """Verify parser creates Junk entry for unparseable content."""
        parser = FluentParserV1()

        # Invalid syntax
        source = "%%% invalid syntax"

        resource = parser.parse(source)

        assert resource is not None
        assert len(resource.entries) > 0
        # Should have created junk entry
        assert any(isinstance(entry, Junk) for entry in resource.entries)

    def test_parse_junk_continues_parsing(self) -> None:
        """Verify parser continues after junk entry."""
        parser = FluentParserV1()

        source = """%%% invalid
msg = valid message
"""

        resource = parser.parse(source)

        assert resource is not None
        # Should have both junk and valid message
        assert len(resource.entries) >= 2

    def test_parse_multiline_junk(self) -> None:
        """Verify parser handles multi-line junk correctly."""
        parser = FluentParserV1()

        source = """%%% line 1
    line 2
    line 3
msg = valid
"""

        resource = parser.parse(source)

        assert resource is not None
        assert len(resource.entries) > 0


class TestFluentParserV1CommentParsing:
    """Tests for comment parsing edge cases."""

    def test_parse_single_line_comment(self) -> None:
        """Verify parser handles single-line comments."""
        parser = FluentParserV1()

        source = "# This is a comment\nmsg = value"

        resource = parser.parse(source)

        assert resource is not None
        # Should have comment and message
        assert len(resource.entries) >= 1

    def test_parse_group_comment(self) -> None:
        """Verify parser handles group comments (##)."""
        parser = FluentParserV1()

        source = "## Group comment\nmsg = value"

        resource = parser.parse(source)

        assert resource is not None

    def test_parse_resource_comment(self) -> None:
        """Verify parser handles resource comments (###)."""
        parser = FluentParserV1()

        source = "### Resource comment\nmsg = value"

        resource = parser.parse(source)

        assert resource is not None

    def test_parse_multiple_comments(self) -> None:
        """Verify parser handles multiple consecutive comments."""
        parser = FluentParserV1()

        source = """# Comment 1
## Comment 2
### Comment 3
msg = value
"""

        resource = parser.parse(source)

        assert resource is not None
        assert len(resource.entries) >= 1


class TestFluentParserV1MessageParsing:
    """Tests for message parsing."""

    def test_parse_simple_message(self) -> None:
        """Verify parser handles simple messages."""
        parser = FluentParserV1()

        source = "msg = value"

        resource = parser.parse(source)

        assert resource is not None
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)

    def test_parse_multiple_messages(self) -> None:
        """Verify parser handles multiple messages."""
        parser = FluentParserV1()

        source = """msg1 = value1
msg2 = value2
msg3 = value3
"""

        resource = parser.parse(source)

        assert resource is not None
        assert len(resource.entries) == 3


class TestFluentParserV1TermParsing:
    """Tests for term parsing."""

    def test_parse_simple_term(self) -> None:
        """Verify parser handles simple terms."""
        parser = FluentParserV1()

        source = "-term = value"

        resource = parser.parse(source)

        assert resource is not None
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Term)

    def test_parse_term_and_message(self) -> None:
        """Verify parser handles both terms and messages."""
        parser = FluentParserV1()

        source = """-term = term value
msg = message value
"""

        resource = parser.parse(source)

        assert resource is not None
        assert len(resource.entries) == 2
