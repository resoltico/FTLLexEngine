# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_core.py."""

from tests.syntax_parser_core_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# TestDoSProtection
# ============================================================================


class TestDoSAbortBehavior:
    """DoS abort behavior: max_parse_errors and abort thresholds.

    The parser aborts when the number of Junk entries exceeds
    ``max_parse_errors``, preventing memory exhaustion from
    severely malformed input.
    """

    # -- max_parse_errors: indented junk -----------------------------------

    def test_abort_on_indented_junk(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Parser aborts when indented junk count exceeds limit."""
        parser = FluentParserV1(max_parse_errors=3)
        source = (
            "  indented1\n# comment\n"
            "  indented2\n# comment\n"
            "  indented3\n# comment\n"
            "  indented4\n"
        )
        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == 3
        assert any(
            "Parse aborted" in r.message for r in caplog.records
        )
        assert any(
            "exceeded maximum of 3 Junk entries" in r.message
            for r in caplog.records
        )

    # -- max_parse_errors: failed comments ---------------------------------

    def test_abort_on_failed_comments(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Parser aborts when malformed comment count exceeds limit."""
        parser = FluentParserV1(max_parse_errors=2)
        source = "####\n####\n####\n####\n"
        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == 2
        assert any(
            "Parse aborted" in r.message for r in caplog.records
        )
        assert any(
            "exceeded maximum of 2 Junk entries" in r.message
            for r in caplog.records
        )

    def test_malformed_comment_creates_junk_with_diagnostic(self) -> None:
        """Malformed comment creates Junk with proper diagnostic."""
        parser = FluentParserV1()
        result = parser.parse("#####\n")
        assert len(result.entries) == 1
        junk_entry = result.entries[0]
        assert isinstance(junk_entry, Junk)
        assert junk_entry.content == "#####"
        assert len(junk_entry.annotations) == 1
        assert (
            junk_entry.annotations[0].code
            == DiagnosticCode.PARSE_JUNK.name
        )
        assert "Invalid comment syntax" in junk_entry.annotations[0].message

    # -- max_parse_errors: message parse failures --------------------------

    def test_abort_on_message_failures(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Parser aborts when message parse failures exceed limit."""
        parser = FluentParserV1(max_parse_errors=3)
        source = "msg1\nmsg2\nmsg3\nmsg4\nmsg5\n"
        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == 3
        assert any(
            "Parse aborted" in r.message for r in caplog.records
        )
        assert any(
            "exceeded maximum of 3 Junk entries" in r.message
            for r in caplog.records
        )

    def test_generic_parse_error_annotation(self) -> None:
        """Generic parse error when nesting depth not exceeded."""
        parser = FluentParserV1()
        result = parser.parse("invalid syntax here\n")
        assert len(result.entries) == 1
        junk_entry = result.entries[0]
        assert isinstance(junk_entry, Junk)
        assert len(junk_entry.annotations) == 1
        annotation = junk_entry.annotations[0]
        assert annotation.code == DiagnosticCode.PARSE_JUNK.name
        assert annotation.message == "Parse error"

    # -- max_parse_errors: mixed junk types --------------------------------

    def test_mixed_junk_types_count_toward_limit(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """All junk types count together toward the limit."""
        parser = FluentParserV1(max_parse_errors=4)
        source = (
            "  indented1\nmsg1 = ok\n####\n"
            "invalid\nmsg2 = ok\n  indented2\n####\n"
        )
        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == 4
        assert any(
            "Parse aborted" in r.message for r in caplog.records
        )

    def test_depth_exceeded_counts_toward_limit(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Depth exceeded errors count toward max_parse_errors."""
        parser = FluentParserV1(
            max_nesting_depth=1, max_parse_errors=2,
        )
        source = (
            "m1 = { { $x } }\nm2 = { { $y } }\n"
            "m3 = { { $z } }\n"
        )
        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == 2
        depth_count = sum(
            1
            for entry in junk
            for ann in entry.annotations
            if ann.code
            == DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name
        )
        assert depth_count >= 1

    # -- max_parse_errors: boundary conditions -----------------------------

    def test_disabled_max_parse_errors_never_aborts(self) -> None:
        """Parser with max_parse_errors=0 never aborts."""
        parser = FluentParserV1(max_parse_errors=0)
        source = "####\n" * 200
        result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == 200

    def test_exact_boundary(self) -> None:
        """Parser creates exactly max_parse_errors junk entries at limit."""
        parser = FluentParserV1(max_parse_errors=5)
        source = "####\n" * 5
        result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == 5

    def test_one_over_boundary(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Parser with 6 errors and limit of 5 aborts at 5."""
        parser = FluentParserV1(max_parse_errors=5)
        source = "####\n" * 6
        with caplog.at_level(logging.WARNING):
            result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == 5
        assert any(
            "Parse aborted" in r.message for r in caplog.records
        )

    # -- Log message content -----------------------------------------------

    def test_log_suggests_fixing_source(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """DoS protection log mentions malformed FTL input."""
        parser = FluentParserV1(max_parse_errors=1)
        source = "####\n####\n"
        with caplog.at_level(logging.WARNING):
            parser.parse(source)
        assert any(
            "severely malformed FTL input" in r.message
            for r in caplog.records
        )

    def test_log_suggests_increasing_limit(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """DoS protection log mentions increasing max_parse_errors."""
        parser = FluentParserV1(max_parse_errors=1)
        source = "####\n####\n"
        with caplog.at_level(logging.WARNING):
            parser.parse(source)
        assert any(
            "increasing max_parse_errors" in r.message
            for r in caplog.records
        )
