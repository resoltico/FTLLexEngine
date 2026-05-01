# mypy: ignore-errors
"""Split test cases from tests/test_syntax_cursor_property.py."""

from tests.syntax_cursor_property_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# PROPERTY TESTS - EOF HANDLING
# ============================================================================


class TestCursorEOF:
    """Test EOF (End Of File) detection properties."""

    @given(source=source_text)
    @settings(max_examples=200)
    def test_is_eof_true_at_end(self, source: str) -> None:
        """PROPERTY: is_eof is True when pos >= len(source)."""
        event(f"text_len={len(source)}")
        cursor = Cursor(source, len(source))
        assert cursor.is_eof is True

    @given(source=source_text.filter(lambda s: len(s) > 0))
    @settings(max_examples=200)
    def test_is_eof_false_before_end(self, source: str) -> None:
        """PROPERTY: is_eof is False when pos < len(source)."""
        event(f"text_len={len(source)}")
        cursor = Cursor(source, 0)
        assert cursor.is_eof is False

    @given(source=source_text)
    @settings(max_examples=100)
    def test_current_raises_eoferror_at_eof(self, source: str) -> None:
        """PROPERTY: current raises EOFError when is_eof is True."""
        event(f"text_len={len(source)}")
        cursor = Cursor(source, len(source))

        if cursor.is_eof:
            with pytest.raises(EOFError):
                _ = cursor.current

    @given(source=source_text.filter(lambda s: len(s) > 0))
    @settings(max_examples=100)
    def test_current_succeeds_before_eof(self, source: str) -> None:
        """PROPERTY: current succeeds when is_eof is False."""
        event(f"text_len={len(source)}")
        cursor = Cursor(source, 0)

        if not cursor.is_eof:
            # Should not raise
            char = cursor.current
            assert isinstance(char, str)
            assert len(char) == 1

    @given(source=source_text.filter(lambda s: len(s) > 0))
    @settings(max_examples=100)
    def test_advance_until_eof_reaches_end(self, source: str) -> None:
        """PROPERTY: Advancing through source eventually reaches EOF."""
        event(f"text_len={len(source)}")
        cursor = Cursor(source, 0)

        # Advance until EOF
        for _ in range(len(source) + 1):
            if cursor.is_eof:
                break
            cursor = cursor.advance()

        # Should be at EOF
        assert cursor.is_eof is True
        assert cursor.pos >= len(source)
