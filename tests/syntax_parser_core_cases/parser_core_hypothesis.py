# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_core.py."""

from tests.syntax_parser_core_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# TestParserCoreHypothesis
# ============================================================================


class TestParserCoreHypothesis:
    """Property-based tests for parser core components.

    Uses Hypothesis to verify invariants across generated inputs.
    All ``@given`` tests emit ``event()`` calls for HypoFuzz guidance.
    """

    # -- _has_blank_line_between properties --------------------------------

    @given(
        prefix=st.text(
            alphabet=st.characters(blacklist_characters=["\n"]),
            max_size=10,
        ),
        suffix=st.text(
            alphabet=st.characters(blacklist_characters=["\n"]),
            max_size=10,
        ),
    )
    def test_newline_pair_always_detected(
        self, prefix: str, suffix: str,
    ) -> None:
        """Two consecutive newlines in region are always detected."""
        source = f"{prefix}\n\n{suffix}"
        event(f"input_len={len(source)}")
        assert _has_blank_line_between(source, 0, len(source)) is True

    @given(st.integers(min_value=2, max_value=10))
    def test_multiple_newlines_always_detected(
        self, count: int,
    ) -> None:
        """Multiple consecutive newlines always detected."""
        event(f"boundary=newline_count_{count}")
        source = "\n" * count
        assert _has_blank_line_between(source, 0, len(source)) is True

    @given(st.integers(min_value=0, max_value=50))
    def test_spaces_only_never_blank(self, space_count: int) -> None:
        """Spaces without newlines never produce a blank line."""
        event(f"boundary=space_count_{min(space_count, 10)}")
        source = " " * space_count
        assert _has_blank_line_between(source, 0, len(source)) is False

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
    def test_ascii_no_newline_no_blank(self, text: str) -> None:
        """ASCII text without newlines or spaces has no blank line."""
        event(f"input_len={len(text)}")
        assert _has_blank_line_between(text, 0, len(text)) is False

    @given(
        non_blank=st.characters(
            blacklist_categories=("Zs", "Zl", "Zp"),
            blacklist_characters=["\n"],
        )
    )
    def test_non_blank_char_with_newlines(
        self, non_blank: str,
    ) -> None:
        """Non-blank char between newlines: first newline is detected."""
        event("outcome=newline_detected")
        source = f"\n{non_blank}\n"
        assert _has_blank_line_between(source, 0, len(source)) is True

    @given(
        lines=st.lists(
            st.text(
                alphabet=st.characters(
                    blacklist_categories=("Zs", "Zl", "Zp"),
                    blacklist_characters=["\n"],
                ),
                min_size=1,
                max_size=5,
            ),
            min_size=1,
            max_size=10,
        )
    )
    def test_joined_lines_blank_iff_multiple(
        self, lines: list[str],
    ) -> None:
        """Single-newline-joined non-ws lines: blank iff >1 line."""
        event(f"boundary=line_count_{len(lines)}")
        source = "\n".join(lines)
        result = _has_blank_line_between(source, 0, len(source))
        if len(lines) > 1:
            assert result is True
        else:
            assert result is False

    @given(
        non_blank_chars=st.lists(
            st.characters(
                blacklist_categories=("Zs", "Zl", "Zp"),
                blacklist_characters=["\n"],
            ),
            min_size=1,
            max_size=5,
        )
    )
    def test_interleaved_newlines_always_detected(
        self, non_blank_chars: list[str],
    ) -> None:
        """Interleaved newlines and non-blank chars: always has newline."""
        event(f"boundary=char_count_{len(non_blank_chars)}")
        parts: list[str] = []
        for char in non_blank_chars:
            parts.append("\n")
            parts.append(char)
        parts.append("\n")
        source = "".join(parts)
        assert _has_blank_line_between(source, 0, len(source)) is True

    # -- Parser hash-combination property ----------------------------------

    @given(
        st.text(
            alphabet="#\n\r \t", min_size=1, max_size=50,
        )
    )
    def test_hash_combinations_no_crash(self, source: str) -> None:
        """Parser handles any combination of hashes and whitespace."""
        event(f"input_len={len(source)}")
        parser = FluentParserV1()
        resource = parser.parse(source)
        assert resource is not None
        assert isinstance(resource.entries, tuple)
        has_entries = len(resource.entries) > 0
        event(f"outcome=has_entries_{has_entries}")

    # -- max_parse_errors property -----------------------------------------

    @given(st.integers(min_value=1, max_value=10))
    def test_custom_limit_respected(self, limit: int) -> None:
        """Parser aborts at exactly max_parse_errors limit."""
        event(f"boundary=limit_{limit}")
        parser = FluentParserV1(max_parse_errors=limit)
        source = "####\n" * (limit + 2)
        result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) == limit

    # -- Nesting depth property --------------------------------------------

    @given(st.integers(min_value=1, max_value=5))
    def test_depth_exceeded_includes_limit(
        self, depth_limit: int,
    ) -> None:
        """Depth exceeded diagnostic includes the configured limit."""
        event(f"boundary=depth_{depth_limit}")
        parser = FluentParserV1(max_nesting_depth=depth_limit)
        nesting = (
            "{ " * (depth_limit + 1)
            + "$x"
            + " }" * (depth_limit + 1)
        )
        source = f"msg = {nesting}\n"
        result = parser.parse(source)
        junk = [e for e in result.entries if isinstance(e, Junk)]
        assert len(junk) >= 1
        for entry in junk:
            for ann in entry.annotations:
                if (
                    ann.code
                    == DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name
                ):
                    assert f"max: {depth_limit}" in ann.message
                    return
        pytest.fail(
            "Expected PARSE_NESTING_DEPTH_EXCEEDED annotation"
        )

    # -- Recursion limit clamping property ---------------------------------

    @given(depth_offset=st.integers(min_value=1, max_value=500))
    def test_any_excessive_depth_clamped(
        self, depth_offset: int,
    ) -> None:
        """Any depth exceeding recursion limit is clamped."""
        event(f"boundary=offset_{min(depth_offset, 50)}")
        recursion_limit = sys.getrecursionlimit()
        max_safe = recursion_limit - 50
        excessive = recursion_limit + depth_offset
        parser = FluentParserV1(max_nesting_depth=excessive)
        assert parser.max_nesting_depth == max_safe

    # -- _CommentAccumulator span property ---------------------------------

    @given(
        content1=st.text(min_size=1, max_size=50),
        content2=st.text(min_size=1, max_size=50),
        start=st.integers(min_value=0, max_value=1000),
        end=st.integers(min_value=0, max_value=1000),
    )
    def test_accumulator_span_combinations(
        self,
        content1: str,
        content2: str,
        start: int,
        end: int,
    ) -> None:
        """Accumulator always produces valid Comment for any span config."""
        if end < start:
            start, end = end, start
        span = Span(start=start, end=end)

        for first_has in (True, False):
            for last_has in (True, False):
                event(
                    f"outcome=first_{first_has}_last_{last_has}"
                )
                first = Comment(
                    content=content1,
                    type=CommentType.COMMENT,
                    span=span if first_has else None,
                )
                acc = _CommentAccumulator(first)
                second = Comment(
                    content=content2,
                    type=CommentType.COMMENT,
                    span=span if last_has else None,
                )
                acc.add(second)
                result = acc.finalize()

                assert content1 in result.content
                assert content2 in result.content
                assert "\n" in result.content

                if first_has or last_has:
                    assert result.span is not None
                    if first_has != last_has:
                        assert result.span == span
                else:
                    assert result.span is None

    # -- Comment attachment to term property --------------------------------

    @given(
        comment_text=st.text(
            min_size=1,
            max_size=100,
            alphabet=st.characters(
                min_codepoint=32,
                max_codepoint=126,
                exclude_characters="#\n",
            ),
        ),
        term_name=st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(
                min_codepoint=ord("a"),
                max_codepoint=ord("z"),
            ),
        ),
        term_value=st.text(
            min_size=1,
            max_size=50,
            alphabet=st.characters(
                min_codepoint=32,
                max_codepoint=126,
                exclude_characters="\n{}",
            ),
        ),
    )
    def test_comment_attaches_to_adjacent_term(
        self,
        comment_text: str,
        term_name: str,
        term_value: str,
    ) -> None:
        """Single-hash comment immediately before term is attached."""
        event("outcome=term_attachment")
        parser = FluentParserV1()
        source = f"# {comment_text}\n-{term_name} = {term_value}\n"
        resource = parser.parse(source)
        terms = [e for e in resource.entries if isinstance(e, Term)]
        if terms:
            term = terms[0]
            assert term.comment is not None
            assert comment_text in term.comment.content
