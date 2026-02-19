"""Comprehensive property-based tests for enums module.

Tests all enum classes for completeness, serialization, and invariants.

"""

from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine import enums
from ftllexengine.enums import CommentType, ReferenceKind, VariableContext


class TestCommentTypeProperties:
    """Property-based tests for CommentType enum."""

    def test_all_members_have_string_values(self) -> None:
        """Property: All Comment Type members have non-empty string values."""
        for member in CommentType:
            assert isinstance(member.value, str)
            assert len(member.value) > 0

    def test_str_returns_value(self) -> None:
        """Property: __str__ returns the enum value for all members."""
        for member in CommentType:
            assert str(member) == member.value

    def test_comment_type_members_exist(self) -> None:
        """Verify all expected CommentType members exist."""
        assert CommentType.COMMENT.value == "comment"
        assert CommentType.GROUP.value == "group"
        assert CommentType.RESOURCE.value == "resource"

    def test_comment_type_members_count(self) -> None:
        """Property: CommentType has exactly 3 members."""
        assert len(list(CommentType)) == 3

    @given(st.sampled_from(CommentType))
    def test_comment_type_str_idempotent(self, comment_type: CommentType) -> None:
        """Property: str(comment_type) is idempotent."""
        event(f"enum_type={type(comment_type).__name__}")
        first = str(comment_type)
        second = str(comment_type)
        assert first == second

    def test_comment_type_uniqueness(self) -> None:
        """Property: All CommentType values are unique."""
        values = [member.value for member in CommentType]
        assert len(values) == len(set(values))


class TestVariableContextProperties:
    """Property-based tests for VariableContext enum."""

    def test_all_members_have_string_values(self) -> None:
        """Property: All VariableContext members have non-empty string values."""
        for member in VariableContext:
            assert isinstance(member.value, str)
            assert len(member.value) > 0

    def test_str_returns_value(self) -> None:
        """Property: __str__ returns the enum value for all members."""
        for member in VariableContext:
            assert str(member) == member.value

    def test_variable_context_members_exist(self) -> None:
        """Verify all expected VariableContext members exist."""
        assert VariableContext.PATTERN.value == "pattern"
        assert VariableContext.SELECTOR.value == "selector"
        assert VariableContext.VARIANT.value == "variant"
        assert VariableContext.FUNCTION_ARG.value == "function_arg"

    def test_variable_context_members_count(self) -> None:
        """Property: VariableContext has exactly 4 members."""
        assert len(list(VariableContext)) == 4

    @given(st.sampled_from(VariableContext))
    def test_variable_context_str_idempotent(self, context: VariableContext) -> None:
        """Property: str(context) is idempotent."""
        enum_name = type(context).__name__
        event(f"enum_type={enum_name}")
        first = str(context)
        second = str(context)
        assert first == second

    def test_variable_context_uniqueness(self) -> None:
        """Property: All VariableContext values are unique."""
        values = [member.value for member in VariableContext]
        assert len(values) == len(set(values))


class TestReferenceKindProperties:
    """Property-based tests for ReferenceKind enum."""

    def test_all_members_have_string_values(self) -> None:
        """Property: All ReferenceKind members have non-empty string values."""
        for member in ReferenceKind:
            assert isinstance(member.value, str)
            assert len(member.value) > 0

    def test_str_returns_value(self) -> None:
        """Property: __str__ returns the enum value for all members."""
        for member in ReferenceKind:
            assert str(member) == member.value

    def test_reference_kind_members_exist(self) -> None:
        """Verify all expected ReferenceKind members exist."""
        assert ReferenceKind.MESSAGE.value == "message"
        assert ReferenceKind.TERM.value == "term"

    def test_reference_kind_members_count(self) -> None:
        """Property: ReferenceKind has exactly 2 members."""
        assert len(list(ReferenceKind)) == 2

    @given(st.sampled_from(ReferenceKind))
    def test_reference_kind_str_idempotent(self, kind: ReferenceKind) -> None:
        """Property: str(kind) is idempotent."""
        event(f"enum_type={type(kind).__name__}")
        first = str(kind)
        second = str(kind)
        assert first == second

    def test_reference_kind_uniqueness(self) -> None:
        """Property: All ReferenceKind values are unique."""
        values = [member.value for member in ReferenceKind]
        assert len(values) == len(set(values))


class TestEnumsModuleExports:
    """Test __all__ exports from enums module."""

    def test_all_exports_are_defined(self) -> None:
        """Verify all __all__ exports are actually defined."""
        for name in enums.__all__:
            assert hasattr(enums, name)

    def test_all_enums_are_exported(self) -> None:
        """Verify all enum classes are in __all__."""
        assert "CommentType" in enums.__all__
        assert "VariableContext" in enums.__all__
        assert "ReferenceKind" in enums.__all__

    def test_exports_count(self) -> None:
        """Property: __all__ exports exactly 4 items."""
        assert len(enums.__all__) == 4
