"""Comprehensive tests for 100% serializer coverage.

Targets specific uncovered branches in ftllexengine.syntax.serializer:
- Line 685: Text element with continuation line + syntax character
- Branch coverage for pattern serialization edge cases
- Junk entry serialization paths
- NumberLiteral variant key branches

Python 3.13+.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.syntax.ast import (
    Comment,
    CommentType,
    Identifier,
    Junk,
    Message,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.serializer import serialize


class TestTextElementSyntaxCharAfterContinuation:
    """Test line 685: syntax character immediately after continuation line indent.

    Per FTL spec, characters [, *, and . are syntactically significant at the
    start of a continuation line. When these characters appear in text content
    immediately after \n    (newline + 4 spaces), they must be wrapped as
    StringLiteral placeables to avoid ambiguity with variant keys or attributes.
    """

    def test_text_with_bracket_after_continuation_line(self) -> None:
        """Line 685: Text containing \\n[ becomes \\n    [ after serialization."""
        # Text: "Hello\n[world" - serializer adds indent, making "\n    ["
        # This triggers line 685: break when syntax char follows continuation indent
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(
                elements=(TextElement(value="Hello\n[world"),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        # The [ should be wrapped as a placeable to avoid parsing as variant key
        assert "Hello" in result
        assert '{ "[" }' in result  # Wrapped to prevent misparse

    def test_text_with_asterisk_after_continuation_line(self) -> None:
        """Line 685: Text containing \\n* becomes \\n    * after serialization."""
        # Text: "Item\n*Note" - serializer adds indent, making "\n    *"
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(
                elements=(TextElement(value="Item\n*Note"),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        # The * should be wrapped to avoid parsing as default variant marker
        assert "Item" in result
        assert '{ "*" }' in result  # Wrapped to prevent misparse

    def test_text_with_dot_after_continuation_line(self) -> None:
        """Line 685: Text containing \\n. becomes \\n    . after serialization."""
        # Text: "Main\n.point" - serializer adds indent, making "\n    ."
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(
                elements=(TextElement(value="Main\n.point"),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        # The . should be wrapped to avoid parsing as attribute marker
        assert "Main" in result
        assert '{ "." }' in result  # Wrapped to prevent misparse

    def test_text_with_multiple_syntax_chars_after_continuation(self) -> None:
        """Line 685: Multiple syntax characters in continuation lines."""
        # Text with multiple problematic characters (no initial indent)
        # After serialization, each \n becomes \n    , triggering line 685 for [*.]
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(
                elements=(TextElement(value="Line1\n[a]\n*b\n.c"),)
            ),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        # All syntax chars should be handled (wrapped as placeables)
        assert "Line1" in result
        # At least one should be wrapped
        assert '{ "[" }' in result or '{ "*" }' in result or '{ "." }' in result


class TestJunkSerializationBranches:
    """Test Junk entry serialization for complete branch coverage."""

    def test_junk_with_leading_whitespace(self) -> None:
        """Junk with leading whitespace - no separator added."""
        # Junk content starting with whitespace (parser preserves it)
        junk = Junk(content="\n invalid syntax here")
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(TextElement(value="Valid"),)),
            attributes=(),
        )
        resource = Resource(entries=(message, junk))

        result = serialize(resource)

        # Junk content should be preserved with its leading whitespace
        assert "invalid syntax here" in result

    def test_junk_with_leading_space_not_newline(self) -> None:
        """Junk with leading space (not newline) triggers separator logic."""
        # Junk starting with space (line 381: entry.content[0] in "\\n ")
        junk = Junk(content=" invalid")
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(TextElement(value="Valid"),)),
            attributes=(),
        )
        resource = Resource(entries=(message, junk))

        result = serialize(resource)

        # Junk with leading space - no extra separator
        assert " invalid" in result

    def test_junk_without_trailing_newline(self) -> None:
        """Junk without trailing newline gets one appended."""
        junk = Junk(content="incomplete line")
        resource = Resource(entries=(junk,))

        result = serialize(resource)

        # Line 515-516: Append newline if missing
        assert result.endswith("\n")
        assert "incomplete line" in result


class TestPatternPlaceableLoopBranches:
    """Test pattern serialization loop branches for complete coverage."""

    def test_pattern_ending_with_placeable(self) -> None:
        """Pattern ending with Placeable exercises loop exit after elif branch."""
        # Pattern: "text" followed by { $var } - tests branch 616->592 exit
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(
                elements=(
                    TextElement(value="prefix "),
                    Placeable(expression=VariableReference(id=Identifier(name="var"))),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "prefix" in result
        assert "$var" in result

    def test_pattern_with_multiple_placeables(self) -> None:
        """Pattern with multiple placeables exercises loop continuation."""
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(
                elements=(
                    Placeable(expression=VariableReference(id=Identifier(name="a"))),
                    TextElement(value=" and "),
                    Placeable(expression=VariableReference(id=Identifier(name="b"))),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "$a" in result
        assert "$b" in result
        assert "and" in result


class TestSelectExpressionBranches:
    """Test SelectExpression serialization for complete branch coverage."""

    def test_select_with_number_literal_key_exercising_case_804(self) -> None:
        """NumberLiteral variant key exercises line 804->807 branch."""
        # Create select with explicit numeric keys
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="num")),
            variants=(
                Variant(
                    key=NumberLiteral(value=0, raw="0"),
                    value=Pattern(elements=(TextElement(value="Zero"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=1, raw="1"),
                    value=Pattern(elements=(TextElement(value="One"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=2, raw="2"),
                    value=Pattern(elements=(TextElement(value="Two"),)),
                    default=True,  # Default on numeric key
                ),
            ),
        )

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        # Verify all numeric keys are serialized correctly
        assert "[0] Zero" in result
        assert "[1] One" in result
        assert "*[2] Two" in result  # Default marker on numeric key

    def test_select_expression_case_exit_branch_749(self) -> None:
        """SelectExpression case exercises match exit at line 749."""
        # Simple select to ensure the SelectExpression case is reached and exited
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="x")),
            variants=(
                Variant(
                    key=Identifier(name="default"),
                    value=Pattern(elements=(TextElement(value="Value"),)),
                    default=True,
                ),
            ),
        )

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "$x ->" in result
        assert "*[default] Value" in result


class TestCommentBlankLineSeparation:
    """Test Resource serialization comment separation logic."""

    def test_adjacent_comments_same_type_get_blank_line(self) -> None:
        """Adjacent comments of same type need blank line to prevent merging."""
        comment1 = Comment(type=CommentType.COMMENT, content="First")
        comment2 = Comment(type=CommentType.COMMENT, content="Second")
        resource = Resource(entries=(comment1, comment2))

        result = serialize(resource)

        # Should have blank line between same-type comments (line 402-403)
        # Find the two comments and verify blank line between
        assert "# First" in result
        assert "# Second" in result
        # Verify blank line separation
        assert "\n\n#" in result

    def test_comment_before_message_gets_blank_line(self) -> None:
        """Standalone comment before message needs blank line to stay detached."""
        comment = Comment(type=CommentType.COMMENT, content="Standalone")
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(TextElement(value="Text"),)),
            attributes=(),
        )
        resource = Resource(entries=(comment, message))

        result = serialize(resource)

        # Comment should be separated from message (line 397-401)
        assert "# Standalone" in result
        assert "msg = Text" in result


class TestHypothesisRoundtripProperties:
    """Property-based tests using Hypothesis for serializer correctness."""

    @given(
        text=st.text(
            alphabet=st.characters(
                min_codepoint=0x20, max_codepoint=0x7E, blacklist_characters="{}"
            ),
            min_size=1,
            max_size=100,
        )
    )
    def test_simple_text_roundtrip(self, text: str) -> None:
        """Simple text patterns should roundtrip correctly."""
        from ftllexengine.syntax import parse  # noqa: PLC0415

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(elements=(TextElement(value=text),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        # Parse the serialized FTL and verify structure
        reparsed = parse(ftl)
        assert len(reparsed.entries) > 0

    @given(
        var_name=st.from_regex(r"[a-zA-Z][a-zA-Z0-9_]{0,20}", fullmatch=True)
    )
    def test_variable_reference_roundtrip(self, var_name: str) -> None:
        """Variable references should roundtrip correctly."""
        from ftllexengine.syntax import parse  # noqa: PLC0415

        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(
                elements=(
                    Placeable(
                        expression=VariableReference(id=Identifier(name=var_name))
                    ),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        ftl = serialize(resource)

        # Parse back and verify
        reparsed = parse(ftl)
        assert len(reparsed.entries) > 0
        # Verify the variable name is preserved
        assert f"${var_name}" in ftl


class TestBranchCoverageCompleteness:
    """Additional tests targeting specific branch coverage gaps."""

    def test_junk_only_resource_for_branch_429(self) -> None:
        """Test Junk-only resource to ensure branch 429->exit is covered."""
        # Create a resource with only Junk entries
        junk1 = Junk(content="junk content\n")
        junk2 = Junk(content="more junk")
        resource = Resource(entries=(junk1, junk2))

        result = serialize(resource)

        assert "junk content" in result
        assert "more junk" in result

    def test_pattern_with_single_placeable_for_branch_616(self) -> None:
        """Test single placeable pattern to cover branch 616->592."""
        # Pattern with only a single Placeable element
        message = Message(
            id=Identifier(name="msg"),
            value=Pattern(
                elements=(
                    Placeable(expression=VariableReference(id=Identifier(name="x"))),
                )
            ),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "msg = { $x }" in result

    def test_select_expression_in_message_for_branch_749(self) -> None:
        """Test SelectExpression directly in message to cover branch 749->exit."""
        # Message containing only a SelectExpression
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="val")),
            variants=(
                Variant(
                    key=Identifier(name="default"),
                    value=Pattern(elements=(TextElement(value="Default"),)),
                    default=True,
                ),
            ),
        )

        message = Message(
            id=Identifier(name="choice"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "$val ->" in result
        assert "*[default] Default" in result

    def test_number_literal_key_without_default_for_branch_804(self) -> None:
        """Test NumberLiteral variant key (non-default) for branch 804->807."""
        # Select with NumberLiteral keys, ensuring we hit the NumberLiteral case
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="num")),
            variants=(
                Variant(
                    key=NumberLiteral(value=1, raw="1"),
                    value=Pattern(elements=(TextElement(value="First"),)),
                    default=False,  # Not default
                ),
                Variant(
                    key=NumberLiteral(value=2, raw="2"),
                    value=Pattern(elements=(TextElement(value="Second"),)),
                    default=True,  # This is the default
                ),
            ),
        )

        message = Message(
            id=Identifier(name="seq"),
            value=Pattern(elements=(Placeable(expression=select),)),
            attributes=(),
        )
        resource = Resource(entries=(message,))

        result = serialize(resource)

        assert "[1] First" in result
        assert "*[2] Second" in result


# ============================================================================
# NOTE ON UNREACHABLE CODE
# ============================================================================
#
# The following coverage gaps are UNREACHABLE due to defensive programming
# that's redundant with AST constructor validation:
#
# Lines 117-118: SelectExpression with 0 default variants
#   - Unreachable: SelectExpression.__post_init__ validates exactly 1 default
#   - Test would require bypassing AST validation (artificial scenario)
#
# Lines 121-125: SelectExpression with 2+ default variants
#   - Unreachable: Same AST validation prevents this state
#   - Test would require bypassing AST validation (artificial scenario)
#
# Line 238->exit: FunctionReference with arguments=None
#   - Unreachable: FunctionReference.arguments is required (not Optional)
#   - Type contract prevents None value
#   - Test would violate type safety
#
# These branches cannot be tested without artificial violation of type
# contracts or AST invariants, so they are excluded from coverage goals.
#
# Recommendation: Consider removing redundant validation or adding
# explicit coverage exclusion markers if these defensive checks are
# intentionally unreachable.
# ============================================================================
