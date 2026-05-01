# mypy: ignore-errors
"""Split test cases from tests/test_validation_resource.py."""

from tests.validation_resource_cases import *  # noqa: F403 - shared split test support

# ============================================================================
# LINE 113: Test Message Without Value or Attributes
# ============================================================================


class TestMessageWithoutValueOrAttributes:
    """Test validation of message with neither value nor attributes (line 113)."""

    def test_message_without_value_or_attributes_raises_at_construction(self) -> None:
        """Message with neither value nor attributes raises ValueError at construction.

        The __post_init__ validation now enforces this invariant at construction
        time rather than deferring to the validator.
        """
        import pytest

        from ftllexengine.syntax.ast import Identifier, Message

        with pytest.raises(ValueError, match="must have a value or at least one attribute"):
            Message(
                id=Identifier("empty_msg"),
                value=None,
                attributes=(),
            )
