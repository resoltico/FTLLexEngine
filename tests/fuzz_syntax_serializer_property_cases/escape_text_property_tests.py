# mypy: ignore-errors
"""Split test cases from tests/fuzz/test_syntax_serializer_property.py."""

from tests.fuzz_syntax_serializer_property_cases import *  # noqa: F403 - shared split test support

# =============================================================================
# _escape_text Property Tests
# =============================================================================


class TestEscapeTextProperties:
    """Property-based tests for _escape_text brace escaping.

    Properties verified:
    - Content preserved: unescaping the result recovers the original
    - No raw braces in non-placeable positions
    """

    @given(text=st.text(min_size=0, max_size=100))
    def test_content_roundtrip(self, text: str) -> None:
        """Unescaping placeable wrappers recovers original text."""
        output: list[str] = []
        _escape_text(text, output)
        result = "".join(output)
        has_braces = "{" in text or "}" in text
        event(f"has_braces={has_braces}")
        event(f"length={len(text)}")
        # Reverse the escaping
        recovered = result.replace('{ "{" }', "{").replace('{ "}" }', "}")
        assert recovered == text

    @given(text=st.text(
        alphabet=st.characters(
            codec="utf-8",
            exclude_characters="{}",
        ),
        min_size=0,
        max_size=100,
    ))
    def test_no_transformation_without_braces(self, text: str) -> None:
        """Text without braces passes through unchanged."""
        output: list[str] = []
        _escape_text(text, output)
        result = "".join(output)
        event(f"length={len(text)}")
        assert result == text
