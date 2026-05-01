# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_syntax_serializer_property.py."""

from tests.fuzz_syntax_serializer_property_cases import *  # noqa: F403 - shared split test support

# =============================================================================
# Separate-Line Trigger Discrimination
# =============================================================================


class TestSeparateLineTriggerProperties:
    """Test separate-line mode trigger discrimination.

    Two distinct triggers exist:
    1. Cross-element: TextElement starts with space after
       element ending with newline.
    2. Intra-element: Single TextElement has embedded newline
       followed by space on a NORMAL line.
    """

    @given(
        n_spaces=st.integers(min_value=1, max_value=8),
    )
    def test_cross_element_trigger(
        self, n_spaces: int
    ) -> None:
        """PROPERTY: Cross-element whitespace triggers separate-line.

        Events emitted:
        - trigger=cross_element: Trigger type
        - leading_spaces={n}: Number of leading spaces
        """
        event("trigger=cross_element")
        event(f"leading_spaces={n_spaces}")

        # Element 1 ends with newline, element 2 starts with
        # spaces — triggers separate-line mode.
        elems = (
            TextElement(value="line one\n"),
            TextElement(value=" " * n_spaces + "line two"),
        )
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(elements=elems),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource, validate=True)
        # Separate-line: pattern on new line after =
        assert "test = \n    " in result

    @given(
        n_spaces=st.integers(min_value=1, max_value=8),
    )
    def test_intra_element_trigger(
        self, n_spaces: int
    ) -> None:
        """PROPERTY: Intra-element whitespace triggers separate-line.

        Events emitted:
        - trigger=intra_element: Trigger type
        - leading_spaces={n}: Number of leading spaces
        """
        event("trigger=intra_element")
        event(f"leading_spaces={n_spaces}")

        # Single element with embedded \n + spaces + NORMAL char
        text_val = f"line one\n{' ' * n_spaces}line two"
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(TextElement(value=text_val),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource, validate=True)
        # Separate-line: pattern on new line after =
        assert "test = \n    " in result

    @given(
        syntax_char=st.sampled_from([".", "*", "["]),
        n_spaces=st.integers(min_value=1, max_value=6),
    )
    def test_syntax_leading_does_not_trigger_separate_line(
        self, syntax_char: str, n_spaces: int
    ) -> None:
        """PROPERTY: SYNTAX_LEADING lines DON'T trigger separate-line.

        Events emitted:
        - trigger=syntax_not_separate: Negative case
        - syntax_char={char}: Which syntax char
        """
        event("trigger=syntax_not_separate")
        event(f"syntax_char={syntax_char}")

        # Embedded \n + spaces + syntax char => SYNTAX_LEADING,
        # which is handled by per-line wrapping, NOT separate-line.
        line = " " * n_spaces + syntax_char + "rest"
        text_val = f"line one\n{line}"
        msg = Message(
            id=Identifier(name="test"),
            value=Pattern(
                elements=(TextElement(value=text_val),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(msg,))
        result = serialize(resource, validate=True)
        # Should NOT use separate-line mode
        assert result.startswith("test = ")
        assert not result.startswith("test = \n")


# =============================================================================
# Mark as fuzz tests for selective execution
# =============================================================================

pytestmark = pytest.mark.fuzz
