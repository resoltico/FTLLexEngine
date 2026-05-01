# mypy: ignore-errors
"""Split test cases from tests/test_syntax_parser_expressions.py."""

from tests.syntax_parser_expressions_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# VALIDATE MESSAGE CONTENT
# ============================================================================


class TestValidateMessageContent:
    """Tests for validate_message_content."""

    def test_empty_pattern_with_attributes_valid(self) -> None:
        """No pattern but with attributes is valid."""
        pattern = Pattern(elements=())
        attributes = [
            Attribute(
                id=Identifier("attr"),
                value=Pattern(
                    elements=(TextElement("val"),)
                ),
            )
        ]
        assert validate_message_content(pattern, attributes)

    def test_pattern_no_attributes_valid(self) -> None:
        """Pattern with no attributes is valid."""
        pattern = Pattern(elements=(TextElement("value"),))
        assert validate_message_content(pattern, [])

    def test_no_pattern_no_attributes_invalid(self) -> None:
        """Neither pattern nor attributes is invalid."""
        assert not validate_message_content(
            Pattern(elements=()), []
        )
