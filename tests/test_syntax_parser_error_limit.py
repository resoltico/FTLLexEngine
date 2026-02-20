"""Tests for parse error limit DoS protection (F-SEC-DoS-001).

Verifies that the parser aborts after exceeding the maximum number
of Junk (error) entries, preventing memory exhaustion from malformed
input.

Important: Per Fluent spec, consecutive invalid lines that don't start with
valid entry characters (#, -, or ASCII letter) are MERGED into a single Junk
entry. To test the error limit, we use invalid comment syntax (##### ...)
which creates individual Junk entries because each line starts with # and
is parsed individually.

Python 3.13+. Uses pytest.
"""

from __future__ import annotations

from ftllexengine.syntax import parse as parse_ftl
from ftllexengine.syntax.ast import Junk, Message
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.parser.core import _MAX_PARSE_ERRORS as MAX_PARSE_ERRORS


class TestParseErrorLimit:
    """Tests for parse error limit DoS protection."""

    def test_parser_aborts_after_max_errors(self) -> None:
        """Parser aborts after exceeding MAX_PARSE_ERRORS Junk entries."""
        # Generate 150 invalid comment lines (exceeds default 100 limit)
        # Each line starts with # but has too many # characters (invalid syntax)
        # Per Fluent spec, valid comments use 1-3 # characters, not 5+
        malformed_lines = [f"##### invalid comment {i}" for i in range(150)]
        source = "\n".join(malformed_lines)

        parser = FluentParserV1()
        resource = parser.parse(source)

        # Count Junk entries
        junk_count = sum(1 for entry in resource.entries if isinstance(entry, Junk))

        # Parser should abort at MAX_PARSE_ERRORS (100), not process all 150
        assert junk_count == MAX_PARSE_ERRORS
        assert len(resource.entries) == MAX_PARSE_ERRORS

    def test_parser_processes_fewer_than_limit(self) -> None:
        """Parser processes all errors if below limit."""
        # Generate 50 invalid comment lines (below default 100 limit)
        malformed_lines = [f"##### invalid comment {i}" for i in range(50)]
        source = "\n".join(malformed_lines)

        parser = FluentParserV1()
        resource = parser.parse(source)

        # Count Junk entries
        junk_count = sum(1 for entry in resource.entries if isinstance(entry, Junk))

        # All 50 errors should be processed
        assert junk_count == 50

    def test_custom_max_parse_errors(self) -> None:
        """Custom max_parse_errors limit is respected."""
        # Generate 50 invalid comment lines
        malformed_lines = [f"##### invalid comment {i}" for i in range(50)]
        source = "\n".join(malformed_lines)

        # Set custom limit to 25
        parser = FluentParserV1(max_parse_errors=25)
        resource = parser.parse(source)

        # Count Junk entries
        junk_count = sum(1 for entry in resource.entries if isinstance(entry, Junk))

        # Parser should abort at 25, not process all 50
        assert junk_count == 25

    def test_mix_of_valid_and_invalid_entries(self) -> None:
        """Parser counts only Junk entries towards limit."""
        # Mix valid messages with invalid comments
        lines = []
        for i in range(60):
            if i % 2 == 0:
                # Valid message
                lines.append(f"msg{i} = Valid message {i}")
            else:
                # Invalid comment syntax (too many # characters)
                lines.append(f"##### invalid comment {i}")

        source = "\n".join(lines)

        parser = FluentParserV1()
        resource = parser.parse(source)

        # Count Junk and Message entries
        junk_count = sum(1 for entry in resource.entries if isinstance(entry, Junk))
        message_count = sum(1 for entry in resource.entries if isinstance(entry, Message))

        # Should have 30 valid messages and 30 Junk entries (all processed)
        assert message_count == 30
        assert junk_count == 30

    def test_dos_protection_against_amplification(self) -> None:
        """DoS protection prevents memory exhaustion from error amplification."""
        # Simulate attack: 10K lines of invalid comment syntax
        # Without limit, this would create 10K Junk entries
        malformed_lines = [f"##### attack {i}" for i in range(10_000)]
        source = "\n".join(malformed_lines)

        parser = FluentParserV1()
        resource = parser.parse(source)

        # Count Junk entries
        junk_count = sum(1 for entry in resource.entries if isinstance(entry, Junk))

        # Parser should abort at MAX_PARSE_ERRORS (100), blocking amplification
        assert junk_count == MAX_PARSE_ERRORS
        # Memory usage is bounded: 100 Junk entries instead of 10,000
        assert len(resource.entries) == MAX_PARSE_ERRORS

    def test_zero_max_parse_errors_allows_unlimited(self) -> None:
        """Setting max_parse_errors=0 disables the limit (not recommended)."""
        # Generate 150 invalid comment lines
        malformed_lines = [f"##### invalid comment {i}" for i in range(150)]
        source = "\n".join(malformed_lines)

        # Disable limit (for testing/debugging only)
        parser = FluentParserV1(max_parse_errors=0)
        resource = parser.parse(source)

        # Count Junk entries
        junk_count = sum(1 for entry in resource.entries if isinstance(entry, Junk))

        # All 150 errors should be processed (no limit)
        assert junk_count == 150

    def test_indented_lines_merge_into_single_junk(self) -> None:
        """Per Fluent spec, consecutive invalid lines merge into single Junk.

        This verifies that lines not starting with valid entry characters
        (# for comments, - for terms, or ASCII letter for messages) are
        merged together per the Fluent EBNF:
            Junk ::= junk_line (junk_line - "#" - "-" - [a-zA-Z])*
        """
        # Generate 100 indented lines - all should merge into ONE Junk entry
        indented_lines = [f"  indented line {i}" for i in range(100)]
        source = "\n".join(indented_lines)

        parser = FluentParserV1()
        resource = parser.parse(source)

        # All 100 lines merge into 1 Junk entry
        junk_count = sum(1 for entry in resource.entries if isinstance(entry, Junk))
        assert junk_count == 1
        assert len(resource.entries) == 1

    def test_mixed_junk_types_separate_entries(self) -> None:
        """Different junk causes (valid entry start chars) create separate entries."""
        lines = []

        # Invalid comment syntax lines (each creates individual Junk)
        for i in range(60):
            lines.append(f"##### invalid comment {i}")

        # Indented lines (all merge into ONE Junk)
        for i in range(40):
            lines.append(f"  indented {i}")

        source = "\n".join(lines)

        parser = FluentParserV1()
        resource = parser.parse(source)

        # Count Junk entries:
        # - 60 individual Junk from invalid comments
        # - 1 merged Junk from 40 indented lines
        # Total: 61 Junk entries
        junk_count = sum(1 for entry in resource.entries if isinstance(entry, Junk))
        assert junk_count == 61

    def test_parse_with_default_vs_custom_limit(self) -> None:
        """Convenience parse() function uses default limit."""
        # Generate 150 invalid comment lines
        malformed_lines = [f"##### invalid {i}" for i in range(150)]
        source = "\n".join(malformed_lines)

        # Using convenience function (should use default limit)
        resource = parse_ftl(source)
        junk_count = sum(1 for entry in resource.entries if isinstance(entry, Junk))

        # Should respect default MAX_PARSE_ERRORS
        assert junk_count == MAX_PARSE_ERRORS

    def test_general_parse_errors_count_toward_limit(self) -> None:
        """Parse errors from malformed messages count toward limit."""
        # Each line looks like a message start (letter) but is malformed
        # Format: identifier followed by invalid character
        # "a@ =" starts with 'a', but '@' is invalid in identifier
        # Parser sees 'a' as potential message, parses 'a' as identifier,
        # then fails on '@' and creates Junk
        malformed_lines = []
        for i in range(150):
            # Each line starts with a letter, parses as identifier, then fails
            # Use different invalid patterns to ensure each is individually parsed
            malformed_lines.append(f"a{i} @= invalid")

        source = "\n".join(malformed_lines)

        parser = FluentParserV1()
        resource = parser.parse(source)

        junk_count = sum(1 for entry in resource.entries if isinstance(entry, Junk))

        # Should abort at MAX_PARSE_ERRORS
        assert junk_count == MAX_PARSE_ERRORS
