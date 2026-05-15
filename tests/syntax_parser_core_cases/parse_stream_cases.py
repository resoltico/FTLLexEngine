# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_core.py."""

from tests.syntax_parser_core_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# TestParseStream
# ============================================================================


class TestParseStream:
    """FluentParserV1.parse_stream incremental entry parsing."""

    def test_empty_iterable_yields_nothing(self) -> None:
        """Empty line iterable produces no entries."""
        parser = FluentParserV1()
        assert list(parser.parse_stream([])) == []

    def test_single_message_from_lines(self) -> None:
        """Single message lines yield one Message entry."""
        parser = FluentParserV1()
        lines = ["greeting = Hello\n"]
        entries = list(parser.parse_stream(lines))
        assert len(entries) == 1
        assert isinstance(entries[0], Message)
        assert entries[0].id.name == "greeting"

    def test_two_messages_blank_line_separated(self) -> None:
        """Two messages separated by blank line are yielded in order."""
        parser = FluentParserV1()
        lines = ["msg1 = One\n", "\n", "msg2 = Two\n"]
        entries = list(parser.parse_stream(lines))
        assert len(entries) == 2
        assert isinstance(entries[0], Message)
        assert isinstance(entries[1], Message)
        assert entries[0].id.name == "msg1"
        assert entries[1].id.name == "msg2"

    def test_adjacent_messages_same_chunk(self) -> None:
        """Messages with no blank line between are in one chunk, both yielded."""
        parser = FluentParserV1()
        lines = ["msg1 = One\n", "msg2 = Two\n"]
        entries = list(parser.parse_stream(lines))
        msg_entries = [e for e in entries if isinstance(e, Message)]
        assert len(msg_entries) == 2
        assert msg_entries[0].id.name == "msg1"
        assert msg_entries[1].id.name == "msg2"

    def test_comment_attached_to_message(self) -> None:
        """Comment immediately before message (no blank line) is attached."""
        parser = FluentParserV1()
        lines = ["# A comment\n", "greeting = Hello\n"]
        entries = list(parser.parse_stream(lines))
        messages = [e for e in entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert messages[0].comment is not None
        assert "A comment" in messages[0].comment.content

    def test_standalone_comment_blank_line_before_message(self) -> None:
        """Comment separated by blank line from message is a standalone Comment."""
        parser = FluentParserV1()
        lines = ["# Standalone\n", "\n", "greeting = Hello\n"]
        entries = list(parser.parse_stream(lines))
        assert len(entries) == 2
        assert isinstance(entries[0], Comment)
        assert isinstance(entries[1], Message)
        assert entries[1].comment is None

    def test_multiline_message_with_attributes(self) -> None:
        """Message with attributes spanning multiple lines is yielded as one Message."""
        parser = FluentParserV1()
        lines = ["submit =\n", "    .label = Submit\n", "    .tooltip = Click here\n"]
        entries = list(parser.parse_stream(lines))
        messages = [e for e in entries if isinstance(e, Message)]
        assert len(messages) == 1
        assert messages[0].id.name == "submit"
        assert len(messages[0].attributes) == 2

    def test_junk_entry_is_yielded(self) -> None:
        """Unparseable content is yielded as Junk."""
        parser = FluentParserV1()
        lines = ["    indented = invalid\n"]
        entries = list(parser.parse_stream(lines))
        junk_entries = [e for e in entries if isinstance(e, Junk)]
        assert len(junk_entries) >= 1

    def test_generator_input_accepted(self) -> None:
        """Generator (not just list) is accepted as lines argument."""
        parser = FluentParserV1()

        def line_gen() -> object:
            yield "msg = Value\n"

        entries = list(parser.parse_stream(line_gen()))  # type: ignore[arg-type]
        assert len(entries) == 1
        assert isinstance(entries[0], Message)

    def test_non_string_line_is_rejected(self) -> None:
        """parse_stream should reject undecoded byte streams explicitly."""
        parser = FluentParserV1()

        with pytest.raises(TypeError, match="must yield str, got bytes"):
            list(parser.parse_stream([b"msg = bytes\n"]))  # type: ignore[list-item]

    def test_lines_without_trailing_newlines(self) -> None:
        """Lines without trailing newlines are handled correctly."""
        parser = FluentParserV1()
        lines = ["msg1 = One", "", "msg2 = Two"]
        entries = list(parser.parse_stream(lines))
        msg_entries = [e for e in entries if isinstance(e, Message)]
        assert len(msg_entries) == 2

    def test_stream_line_length_limit_fails_closed(self) -> None:
        """Per-line budgets should reject oversized lines before buffering them."""
        parser = FluentParserV1(max_stream_line_length=5)

        with pytest.raises(ValueError, match="Stream line length"):
            list(parser.parse_stream(["123456"]))

    def test_stream_total_length_limit_fails_closed(self) -> None:
        """Total stream budgets should reject overlong streams before parsing chunks."""
        parser = FluentParserV1(max_source_size=5)

        with pytest.raises(ValueError, match="Stream length"):
            list(parser.parse_stream(["1234", "56"]))

    def test_entry_chunk_length_limit_fails_closed(self) -> None:
        """One blank-line-delimited entry cannot exceed the configured chunk budget."""
        parser = FluentParserV1(max_source_size=12, max_stream_line_length=100)

        with pytest.raises(ValueError, match="Entry chunk length"):
            list(parser.parse_stream(["ab=1", "cd=2", "ef=3"]))

    def test_leading_blank_line_is_skipped(self) -> None:
        """Blank line before any content is silently skipped.

        When a blank line is encountered with an empty accumulator chunk, the
        elif chunk: branch evaluates to False and the loop continues to the next
        line without flushing. This covers the 593->589 branch in parse_stream.
        """
        parser = FluentParserV1()
        lines = ["", "greeting = Hello\n"]
        entries = list(parser.parse_stream(lines))
        msg_entries = [e for e in entries if isinstance(e, Message)]
        assert len(msg_entries) == 1
        assert msg_entries[0].id.name == "greeting"

    def test_consecutive_blank_lines_between_messages(self) -> None:
        """Consecutive blank lines between messages are handled correctly.

        After the first blank line flushes the accumulator, a second consecutive
        blank line hits the elif chunk: False branch (empty accumulator) again,
        exercising the 593->589 branch path a second time per stream.
        """
        parser = FluentParserV1()
        lines = ["msg1 = One\n", "\n", "\n", "msg2 = Two\n"]
        entries = list(parser.parse_stream(lines))
        msg_entries = [e for e in entries if isinstance(e, Message)]
        assert len(msg_entries) == 2
        assert msg_entries[0].id.name == "msg1"
        assert msg_entries[1].id.name == "msg2"

    def test_term_is_yielded(self) -> None:
        """Term entry is correctly parsed and yielded."""
        parser = FluentParserV1()
        lines = ["-brand = Firefox\n"]
        entries = list(parser.parse_stream(lines))
        terms = [e for e in entries if isinstance(e, Term)]
        assert len(terms) == 1
        assert terms[0].id.name == "brand"

    @given(
        names=st.lists(
            st.text(
                min_size=1,
                max_size=20,
                alphabet=st.characters(
                    min_codepoint=ord("a"),
                    max_codepoint=ord("z"),
                ),
            ),
            min_size=1,
            max_size=10,
        )
    )
    def test_entry_count_matches_parse_stream_vs_parse(
        self, names: list[str]
    ) -> None:
        """parse_stream yields same entry count as parse() for well-formed FTL."""
        event(f"msg_count={len(names)}")
        source = "\n\n".join(f"{name} = Value" for name in names) + "\n"
        parser = FluentParserV1()
        stream_entries = list(parser.parse_stream(source.splitlines(keepends=True)))
        full_entries = list(parser.parse(source).entries)
        assert len(stream_entries) == len(full_entries)

    @given(
        names=st.lists(
            st.text(
                min_size=1,
                max_size=20,
                alphabet=st.characters(
                    min_codepoint=ord("a"),
                    max_codepoint=ord("z"),
                ),
            ),
            min_size=1,
            max_size=10,
        )
    )
    def test_message_ids_match_parse_stream_vs_parse(
        self, names: list[str]
    ) -> None:
        """Message IDs from parse_stream match those from parse() for well-formed FTL."""
        event(f"msg_count={len(names)}")
        # Deduplicate names to avoid overwrite warnings
        unique_names = list(dict.fromkeys(names))
        source = "\n\n".join(f"{name} = Value" for name in unique_names) + "\n"
        parser = FluentParserV1()
        stream_ids = {
            e.id.name for e in parser.parse_stream(source.splitlines(keepends=True))
            if isinstance(e, Message)
        }
        full_ids = {e.id.name for e in parser.parse(source).entries if isinstance(e, Message)}
        assert stream_ids == full_ids
