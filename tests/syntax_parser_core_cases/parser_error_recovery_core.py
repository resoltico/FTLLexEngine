# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_core.py."""

from tests.syntax_parser_core_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# TestParserErrorRecoveryCore
# ============================================================================


class TestParserCommentRecovery:
    """Parser comment parsing edge cases and comment type handling.

    Verifies comment recovery, comment types (single, group, resource),
    and edge cases like hash-only lines and EOF handling.
    """

    # -- Comment parsing edge cases ----------------------------------------

    def test_comment_without_newline_at_eof(self) -> None:
        """Comment without trailing newline at EOF."""
        parser = FluentParserV1()
        resource = parser.parse("# This is a comment")
        assert resource is not None
        assert len(resource.entries) > 0

    def test_hash_only_at_eof(self) -> None:
        """Single hash at EOF."""
        parser = FluentParserV1()
        resource = parser.parse("#")
        assert resource is not None

    def test_hash_with_newline_at_eof(self) -> None:
        """Hash followed by newline at EOF."""
        parser = FluentParserV1()
        resource = parser.parse("#\n")
        assert resource is not None

    def test_multiple_hashes_at_eof(self) -> None:
        """Multiple hashes (###) at EOF."""
        parser = FluentParserV1()
        resource = parser.parse("###")
        assert resource is not None

    def test_hash_followed_by_valid_message(self) -> None:
        """Recovery from hash-only line then valid message."""
        parser = FluentParserV1()
        resource = parser.parse("#\nmsg = value")
        assert resource is not None
        assert len(resource.entries) > 0

    def test_hash_blank_line_then_message(self) -> None:
        """Recovery from hash, blank line, then message."""
        parser = FluentParserV1()
        resource = parser.parse("#\n\nmsg = value")
        assert resource is not None
        assert len(resource.entries) > 0

    def test_multiple_failed_comment_lines(self) -> None:
        """Recovery from multiple consecutive hash-only lines."""
        parser = FluentParserV1()
        resource = parser.parse("#\n#\n#\nmsg = value")
        assert resource is not None

    # -- Comment types -----------------------------------------------------

    def test_single_line_comment(self) -> None:
        """Single-line comment before message."""
        parser = FluentParserV1()
        resource = parser.parse("# This is a comment\nmsg = value")
        assert resource is not None
        assert len(resource.entries) >= 1

    def test_group_comment(self) -> None:
        """Group comment (##) before message."""
        parser = FluentParserV1()
        resource = parser.parse("## Group comment\nmsg = value")
        assert resource is not None

    def test_resource_comment(self) -> None:
        """Resource comment (###) before message."""
        parser = FluentParserV1()
        resource = parser.parse("### Resource comment\nmsg = value")
        assert resource is not None

    def test_multiple_comment_types(self) -> None:
        """Multiple comment types in one resource."""
        parser = FluentParserV1()
        source = "# Comment 1\n## Comment 2\n### Comment 3\nmsg = value\n"
        resource = parser.parse(source)
        assert resource is not None
        assert len(resource.entries) >= 1
