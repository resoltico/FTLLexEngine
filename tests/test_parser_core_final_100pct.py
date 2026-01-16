"""Final tests to achieve 100% coverage of syntax/parser/core.py.

Targets remaining uncovered lines:
- Lines 395-401: DoS protection for max_parse_errors in indented junk
- Lines 461-467: DoS protection for max_parse_errors in failed comments
- Line 551: Nesting depth exceeded annotation
- Lines 570-576: DoS protection for max_parse_errors in message parse failure
- Branch 88->85: Edge case in _has_blank_line_between
"""

import logging

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.diagnostics import DiagnosticCode
from ftllexengine.syntax.ast import Junk
from ftllexengine.syntax.parser.core import FluentParserV1, _has_blank_line_between


class TestDoSProtectionIndentedJunk:
    """Test DoS protection for excessive indented junk (lines 395-401)."""

    def test_max_parse_errors_abort_on_indented_junk(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Parser aborts when indented junk count exceeds max_parse_errors.

        Tests lines 395-401: DoS protection for indented content at column > 1.
        """
        parser = FluentParserV1(max_parse_errors=3)

        # Create indented junk at file start (can't be message continuation).
        # After each junk, add a comment to separate entries.
        # Indented lines at the start or between standalone entries become junk.
        source = """  indented1
# comment
  indented2
# comment
  indented3
# comment
  indented4
"""

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)

        # Should create 3 junk entries then abort (4th indented line not parsed)
        junk_entries = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk_entries) == 3

        # Should log warning about exceeded limit
        assert any("Parse aborted" in record.message for record in caplog.records)
        assert any(
            "exceeded maximum of 3 Junk entries" in record.message
            for record in caplog.records
        )

    @given(st.integers(min_value=1, max_value=10))
    def test_max_parse_errors_respects_custom_limits(self, limit: int) -> None:
        """Property: Parser aborts at exactly max_parse_errors limit."""
        parser = FluentParserV1(max_parse_errors=limit)

        # Generate limit + 2 separate junk entries by using malformed comments
        # Each malformed comment creates a separate junk entry
        lines = ["####\n" for _ in range(limit + 2)]
        source = "".join(lines)

        result = parser.parse(source)

        junk_entries = [e for e in result.entries if isinstance(e, Junk)]

        # Should stop at exactly the limit
        assert len(junk_entries) == limit


class TestDoSProtectionFailedComments:
    """Test DoS protection for excessive malformed comments (lines 461-467)."""

    def test_max_parse_errors_abort_on_failed_comments(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Parser aborts when failed comment count exceeds max_parse_errors.

        Tests lines 461-467: DoS protection for malformed comment syntax.
        """
        parser = FluentParserV1(max_parse_errors=2)

        # Create 4 malformed comments (too many # symbols - invalid)
        # Valid comments are #, ##, ### but #### is invalid
        source = "####\n####\n####\n####\n"

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)

        # Should create 2 junk entries then abort
        junk_entries = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk_entries) == 2

        # Should log warning about exceeded limit
        assert any("Parse aborted" in record.message for record in caplog.records)
        assert any(
            "exceeded maximum of 2 Junk entries" in record.message
            for record in caplog.records
        )

    def test_malformed_comment_creates_junk_with_diagnostic(self) -> None:
        """Malformed comment creates Junk with proper diagnostic."""
        parser = FluentParserV1()

        # Invalid comment: too many # symbols
        source = "#####\n"

        result = parser.parse(source)

        assert len(result.entries) == 1
        junk_entry = result.entries[0]
        assert isinstance(junk_entry, Junk)
        assert junk_entry.content == "#####"

        # Check annotation
        assert len(junk_entry.annotations) == 1
        assert junk_entry.annotations[0].code == DiagnosticCode.PARSE_JUNK.name
        assert "Invalid comment syntax" in junk_entry.annotations[0].message


class TestNestingDepthExceeded:
    """Test nesting depth exceeded annotation (line 551)."""

    def test_depth_exceeded_creates_specific_annotation(self) -> None:
        """Message parse failure due to depth exceeded gets specific diagnostic.

        Tests line 551-554: PARSE_NESTING_DEPTH_EXCEEDED annotation.
        """
        # Set extremely low nesting limit
        parser = FluentParserV1(max_nesting_depth=1)

        # Create deeply nested placeables that exceed depth limit
        # Nesting of 2: { { $var } } exceeds limit of 1
        source = "msg = { { $var } }\n"

        result = parser.parse(source)

        # Should create Junk entry (parse failed)
        assert len(result.entries) == 1
        junk_entry = result.entries[0]
        assert isinstance(junk_entry, Junk)

        # Check for depth exceeded diagnostic (not generic parse error)
        assert len(junk_entry.annotations) == 1
        annotation = junk_entry.annotations[0]
        assert annotation.code == DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name
        assert "Nesting depth limit exceeded" in annotation.message
        assert "max: 1" in annotation.message

    @given(st.integers(min_value=1, max_value=5))
    def test_depth_exceeded_diagnostic_includes_limit(self, depth_limit: int) -> None:
        """Property: Depth exceeded diagnostic includes actual limit."""
        parser = FluentParserV1(max_nesting_depth=depth_limit)

        # Create nesting that exceeds limit by 1
        nesting = "{ " * (depth_limit + 1) + "$x" + " }" * (depth_limit + 1)
        source = f"msg = {nesting}\n"

        result = parser.parse(source)

        junk_entries = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk_entries) >= 1

        # Find the depth exceeded annotation
        for entry in junk_entries:
            for annotation in entry.annotations:
                if annotation.code == DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name:
                    assert f"max: {depth_limit}" in annotation.message
                    return

        # If we get here, we didn't find the expected annotation
        pytest.fail("Expected PARSE_NESTING_DEPTH_EXCEEDED annotation not found")


class TestDoSProtectionMessageParseFailure:
    """Test DoS protection for message parse failures (lines 570-576)."""

    def test_max_parse_errors_abort_on_message_failures(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Parser aborts when message parse failures exceed max_parse_errors.

        Tests lines 570-576: DoS protection in message parsing.
        """
        parser = FluentParserV1(max_parse_errors=3)

        # Create 5 invalid message entries (not indented, not comments, but malformed)
        # Lines that start with valid identifier chars but fail message parsing
        # Use invalid syntax like missing '='
        source = "msg1\nmsg2\nmsg3\nmsg4\nmsg5\n"

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)

        # Should create 3 junk entries then abort
        junk_entries = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk_entries) == 3

        # Should log warning
        assert any("Parse aborted" in record.message for record in caplog.records)
        assert any(
            "exceeded maximum of 3 Junk entries" in record.message
            for record in caplog.records
        )

    def test_generic_parse_error_annotation_when_no_depth_exceeded(self) -> None:
        """Generic parse error when depth not exceeded (else branch of line 550)."""
        parser = FluentParserV1()

        # Invalid message that doesn't involve nesting depth
        source = "invalid syntax here\n"

        result = parser.parse(source)

        assert len(result.entries) == 1
        junk_entry = result.entries[0]
        assert isinstance(junk_entry, Junk)

        # Should have generic PARSE_JUNK annotation (not depth exceeded)
        assert len(junk_entry.annotations) == 1
        annotation = junk_entry.annotations[0]
        assert annotation.code == DiagnosticCode.PARSE_JUNK.name
        assert annotation.message == "Parse error"


class TestBlankLineEdgeCases:
    """Additional tests for _has_blank_line_between to cover branch 88->85."""

    def test_space_only_region_no_newlines(self) -> None:
        """Region with only spaces (no newlines) has no blank line."""
        source = "content     content"
        result = _has_blank_line_between(source, 7, 12)  # "     "
        assert result is False

    def test_mixed_whitespace_no_newline(self) -> None:
        """Mixed spaces without newline has no blank line."""
        source = "start    end"
        result = _has_blank_line_between(source, 5, 9)
        assert result is False

    @given(st.integers(min_value=0, max_value=50))
    def test_spaces_only_no_blank_line(self, space_count: int) -> None:
        """Property: Spaces without newlines never create blank line."""
        source = " " * space_count
        result = _has_blank_line_between(source, 0, len(source))
        assert result is False

    def test_non_space_non_newline_chars_no_blank(self) -> None:
        """Non-space, non-newline characters don't create blank lines."""
        source = "abcdefghijklmnop"
        result = _has_blank_line_between(source, 0, len(source))
        assert result is False

    @given(
        st.text(
            alphabet=st.characters(
                blacklist_characters=["\n", " "],
                min_codepoint=33,
                max_codepoint=126,
            ),
            min_size=1,
            max_size=20,
        )
    )
    def test_ascii_no_newline_no_blank_line(self, text: str) -> None:
        """Property: ASCII text without newlines or spaces has no blank line."""
        result = _has_blank_line_between(text, 0, len(text))
        assert result is False


class TestMixedDoSScenarios:
    """Test combinations of DoS protections."""

    def test_mixed_junk_types_all_count_toward_limit(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """All junk types (indented, failed comments, failed messages) count together."""
        parser = FluentParserV1(max_parse_errors=4)

        # Mix of different junk types as separate entries:
        # 1. Indented line (followed by valid entry to separate)
        # 2. Invalid comment
        # 3. Invalid message (followed by valid entry)
        # 4. Another indented line
        # 5. This should NOT be parsed (limit reached)
        source = """  indented1
msg1 = ok
####
invalid
msg2 = ok
  indented2
####
"""

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)

        junk_entries = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk_entries) == 4

        # Should log warning
        assert any("Parse aborted" in record.message for record in caplog.records)

    def test_depth_exceeded_counts_toward_parse_error_limit(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Depth exceeded errors count toward max_parse_errors limit."""
        parser = FluentParserV1(max_nesting_depth=1, max_parse_errors=2)

        # Create 3 deeply nested messages (all will fail with depth exceeded)
        source = "m1 = { { $x } }\nm2 = { { $y } }\nm3 = { { $z } }\n"

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)

        # Should create 2 junk entries then abort
        junk_entries = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk_entries) == 2

        # At least one should be depth exceeded
        depth_exceeded_count = sum(
            1
            for entry in junk_entries
            for annotation in entry.annotations
            if annotation.code == DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name
        )
        assert depth_exceeded_count >= 1


class TestParseErrorLoggingMessages:
    """Test that DoS protection logs include helpful messages."""

    def test_log_message_suggests_fixing_source(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """DoS protection log suggests fixing FTL source."""
        parser = FluentParserV1(max_parse_errors=1)
        # Create 2 separate junk entries using malformed comments
        source = "####\n####\n"

        with caplog.at_level(logging.WARNING):
            parser.parse(source)

        assert any(
            "severely malformed FTL input" in record.message for record in caplog.records
        )

    def test_log_message_suggests_increasing_limit(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """DoS protection log suggests increasing max_parse_errors."""
        parser = FluentParserV1(max_parse_errors=1)
        source = "####\n####\n"

        with caplog.at_level(logging.WARNING):
            parser.parse(source)

        assert any(
            "increasing max_parse_errors" in record.message for record in caplog.records
        )


class TestEdgeCasesCombinations:
    """Test edge case combinations for full coverage."""

    def test_disabled_max_parse_errors_never_aborts(self) -> None:
        """Parser with max_parse_errors=0 never aborts on errors."""
        parser = FluentParserV1(max_parse_errors=0)

        # Create many separate junk entries using malformed comments
        lines = ["####\n" for _ in range(200)]
        source = "".join(lines)

        result = parser.parse(source)

        # Should parse all 200 junk entries without aborting
        junk_entries = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk_entries) == 200

    def test_max_parse_errors_exact_boundary(self) -> None:
        """Parser stops at exact boundary of max_parse_errors."""
        parser = FluentParserV1(max_parse_errors=5)

        # Create exactly 5 separate junk entries using malformed comments
        source = "####\n" * 5

        result = parser.parse(source)

        junk_entries = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk_entries) == 5

    def test_max_parse_errors_one_over_boundary(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Parser with 6 errors and limit of 5 aborts."""
        parser = FluentParserV1(max_parse_errors=5)

        # Create 6 separate junk entries using malformed comments
        source = "####\n" * 6

        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)

        # Should stop at 5
        junk_entries = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk_entries) == 5

        # Should log warning
        assert any("Parse aborted" in record.message for record in caplog.records)
