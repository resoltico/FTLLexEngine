# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_syntax_serializer_property.py."""

from tests.fuzz_syntax_serializer_property_cases import *  # noqa: F403 - shared split test support

# =============================================================================
# Entry Sequencing Properties (Junk/Comment/Message ordering)
# =============================================================================


class TestEntrySequencingProperties:
    """Test blank-line insertion logic for mixed entry sequences.

    Serializer handles spacing between entries: extra blank lines
    for adjacent comments of same type, Junk with leading
    whitespace, Message/Term compact separation.
    """

    @given(
        data=st.data(),
        count=st.integers(min_value=2, max_value=5),
    )
    @settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_mixed_entry_sequences_parseable(
        self, data: st.DataObject, count: int
    ) -> None:
        """PROPERTY: Mixed entry sequences serialize to parseable FTL.

        Events emitted:
        - entry_count={n}: Number of entries
        - has_junk={bool}: Whether Junk entries present
        - has_comment={bool}: Whether Comment entries present
        - outcome=sequence_parseable: Output parses without error
        """
        event(f"entry_count={count}")

        entries: list[Message | Term | Comment | Junk] = []
        seen_ids: set[str] = set()
        has_junk = False
        has_comment = False

        for i in range(count):
            choice = data.draw(
                st.sampled_from(
                    ["message", "term", "comment", "junk"]
                )
            )
            if choice == "message":
                name = f"msg{i}"
                if name not in seen_ids:
                    seen_ids.add(name)
                    entries.append(
                        Message(
                            id=Identifier(name=name),
                            value=Pattern(
                                elements=(
                                    TextElement(value="val"),
                                )
                            ),
                            attributes=(),
                        )
                    )
            elif choice == "term":
                name = f"term{i}"
                if name not in seen_ids:
                    seen_ids.add(name)
                    entries.append(
                        Term(
                            id=Identifier(name=name),
                            value=Pattern(
                                elements=(
                                    TextElement(value="val"),
                                )
                            ),
                            attributes=(),
                        )
                    )
            elif choice == "comment":
                has_comment = True
                ctype = data.draw(
                    st.sampled_from([
                        CommentType.COMMENT,
                        CommentType.GROUP,
                        CommentType.RESOURCE,
                    ])
                )
                entries.append(
                    Comment(
                        content=f"comment {i}",
                        type=ctype,
                    )
                )
            else:
                has_junk = True
                entries.append(
                    Junk(content=f"junk line {i}\n")
                )

        event(f"has_junk={has_junk}")
        event(f"has_comment={has_comment}")

        if not entries:
            return

        resource = Resource(entries=tuple(entries))
        result = serialize(resource, validate=False)

        parser = FluentParserV1()
        reparsed = parser.parse(result)
        assert len(reparsed.entries) > 0
        event("outcome=sequence_parseable")

    @given(
        junk_count=st.integers(min_value=1, max_value=3),
        msg_count=st.integers(min_value=1, max_value=3),
    )
    def test_junk_between_messages(
        self, junk_count: int, msg_count: int
    ) -> None:
        """PROPERTY: Junk interleaved with Messages serializes.

        Events emitted:
        - junk_count={n}: Number of Junk entries
        - msg_count={n}: Number of Message entries
        - outcome=junk_interleaved_ok: Serialization succeeded
        """
        event(f"junk_count={junk_count}")
        event(f"msg_count={msg_count}")

        entries: list[Message | Junk] = []
        for i in range(msg_count):
            entries.append(
                Message(
                    id=Identifier(name=f"m{i}"),
                    value=Pattern(
                        elements=(TextElement(value="v"),)
                    ),
                    attributes=(),
                )
            )
            if i < junk_count:
                entries.append(
                    Junk(content=f"bad syntax {i}\n")
                )

        resource = Resource(entries=tuple(entries))
        result = serialize(resource, validate=False)
        assert isinstance(result, str)
        assert len(result) > 0
        event("outcome=junk_interleaved_ok")

    def test_adjacent_same_type_comments_separated(
        self,
    ) -> None:
        """Adjacent same-type comments get extra blank line."""
        entries = (
            Comment(content="first", type=CommentType.COMMENT),
            Comment(content="second", type=CommentType.COMMENT),
        )
        resource = Resource(entries=entries)
        result = serialize(resource, validate=False)
        # Double newline separates same-type comments
        assert "\n\n" in result
