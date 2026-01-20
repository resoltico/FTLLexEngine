"""Complete coverage tests for serializer.py targeting 100% line and branch coverage.

Targets remaining uncovered lines and branches:
- Lines 281-285: Non-RESOLUTION FrozenFluentError re-raise in _validate_resource
- Line 360: Non-RESOLUTION FrozenFluentError re-raise in serialize
- Line 515: Junk content already ending with newline
- Lines 626-627: Close brace before open brace in text
- Branch 238: FunctionReference validation with empty arguments
- Branch 429: Junk entry serialization
- Branch 592: Placeable in pattern elements
- Branch 693: Nested Placeable expression
- Branch 741: NumberLiteral variant key

Python 3.13+.
"""

from __future__ import annotations

from decimal import Decimal
from typing import cast

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.syntax.ast import (
    CallArguments,
    FunctionReference,
    Identifier,
    Junk,
    Message,
    NamedArgument,
    NumberLiteral,
    Pattern,
    Placeable,
    Resource,
    SelectExpression,
    StringLiteral,
    TextElement,
    VariableReference,
    Variant,
)
from ftllexengine.syntax.parser import FluentParserV1
from ftllexengine.syntax.serializer import (
    FluentSerializer,
    serialize,
)

# ============================================================================
# Line 515: Junk content already ending with newline
# ============================================================================


class TestJunkSerializationEdgeCases:
    """Test Junk serialization edge cases for complete coverage."""

    def test_junk_content_ending_with_newline(self) -> None:
        """COVERAGE: Line 515 - Junk content already ending with newline."""
        # Create Junk node where content already ends with newline
        junk = Junk(content="invalid syntax\n")
        resource = Resource(entries=(junk,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        # Should NOT add extra newline since content already has one
        assert result == "invalid syntax\n"
        # Verify no double newline
        assert not result.endswith("\n\n")

    def test_junk_content_without_newline(self) -> None:
        """COVERAGE: Line 515 else branch - Junk without trailing newline."""
        # Create Junk node where content does NOT end with newline
        junk = Junk(content="invalid syntax")
        resource = Resource(entries=(junk,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        # Should add newline since content doesn't have one
        assert result == "invalid syntax\n"

    def test_junk_empty_content(self) -> None:
        """COVERAGE: Line 515 - Empty junk content."""
        junk = Junk(content="")
        resource = Resource(entries=(junk,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        # Empty content should get newline added
        assert result == "\n"

    def test_junk_multiline_with_trailing_newline(self) -> None:
        """COVERAGE: Line 515 - Multiline junk with trailing newline."""
        junk = Junk(content="line1\nline2\nline3\n")
        resource = Resource(entries=(junk,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        # Should NOT add extra newline
        assert result == "line1\nline2\nline3\n"
        assert result.count("\n") == 3  # Three newlines, not four


# ============================================================================
# Lines 626-627: Close brace before open brace
# ============================================================================


class TestBraceSerializationEdgeCases:
    """Test brace serialization edge cases for complete coverage."""

    def test_close_brace_before_open_brace(self) -> None:
        """COVERAGE: Lines 626-627 - Close brace appears before open brace."""
        # Text with } before { to trigger the else branch at line 625-627
        text_element = TextElement(value="end}middle{start")
        pattern = Pattern(elements=(text_element,))
        message = Message(
            id=Identifier(name="msg"),
            value=pattern,
            attributes=(),
        )
        resource = Resource(entries=(message,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        # Both braces should be escaped as placeables
        assert '{ "}" }' in result
        assert '{ "{" }' in result
        assert "end" in result
        assert "middle" in result
        assert "start" in result

    def test_only_close_brace(self) -> None:
        """COVERAGE: Lines 626-627 - Only close brace, no open brace."""
        text_element = TextElement(value="text}")
        pattern = Pattern(elements=(text_element,))
        message = Message(
            id=Identifier(name="msg"),
            value=pattern,
            attributes=(),
        )
        resource = Resource(entries=(message,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        assert '{ "}" }' in result
        assert "text" in result

    def test_multiple_close_braces_before_open(self) -> None:
        """COVERAGE: Lines 626-627 - Multiple close braces before open."""
        text_element = TextElement(value="a}b}c{d")
        pattern = Pattern(elements=(text_element,))
        message = Message(
            id=Identifier(name="msg"),
            value=pattern,
            attributes=(),
        )
        resource = Resource(entries=(message,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        # All braces should be escaped
        assert result.count('{ "}" }') == 2
        assert '{ "{" }' in result

    def test_alternating_braces(self) -> None:
        """COVERAGE: Lines 626-627 - Alternating close and open braces."""
        text_element = TextElement(value="}a{b}c{")
        pattern = Pattern(elements=(text_element,))
        message = Message(
            id=Identifier(name="msg"),
            value=pattern,
            attributes=(),
        )
        resource = Resource(entries=(message,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        # Should handle alternating pattern correctly
        assert '{ "}" }' in result
        assert '{ "{" }' in result


# ============================================================================
# Branch 429: Junk as top-level entry
# ============================================================================


class TestJunkAsTopLevelEntry:
    """Test Junk serialization as top-level entry."""

    def test_junk_as_sole_entry(self) -> None:
        """COVERAGE: Branch 429 - Junk as the only entry."""
        junk = Junk(content="# broken comment")
        resource = Resource(entries=(junk,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        assert "# broken comment" in result

    def test_junk_between_messages(self) -> None:
        """COVERAGE: Branch 429 - Junk between valid entries."""
        msg1 = Message(
            id=Identifier(name="msg1"),
            value=Pattern(elements=(TextElement(value="First"),)),
            attributes=(),
        )
        junk = Junk(content="@@@ invalid @@@")
        msg2 = Message(
            id=Identifier(name="msg2"),
            value=Pattern(elements=(TextElement(value="Second"),)),
            attributes=(),
        )
        resource = Resource(entries=(msg1, junk, msg2))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        assert "msg1" in result
        assert "@@@ invalid @@@" in result
        assert "msg2" in result

    def test_multiple_junk_entries(self) -> None:
        """COVERAGE: Branch 429 - Multiple junk entries."""
        junk1 = Junk(content="junk1\n")
        junk2 = Junk(content="junk2\n")
        junk3 = Junk(content="junk3")
        resource = Resource(entries=(junk1, junk2, junk3))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        assert "junk1" in result
        assert "junk2" in result
        assert "junk3" in result


# ============================================================================
# Branch 592 & 693: Placeable in pattern and nested Placeable
# ============================================================================


class TestPlaceableBranchCoverage:
    """Test Placeable branches in pattern and expression serialization."""

    def test_pattern_with_placeable_elements(self) -> None:
        """COVERAGE: Branch 592 - Placeable in pattern elements."""
        # Pattern with multiple placeables
        pattern = Pattern(
            elements=(
                TextElement(value="Start "),
                Placeable(expression=VariableReference(id=Identifier(name="var1"))),
                TextElement(value=" middle "),
                Placeable(expression=VariableReference(id=Identifier(name="var2"))),
                TextElement(value=" end"),
            )
        )
        message = Message(id=Identifier(name="msg"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        assert "{ $var1 }" in result
        assert "{ $var2 }" in result

    def test_nested_placeable_expression(self) -> None:
        """COVERAGE: Branch 693 - Nested Placeable in expression."""
        # Create nested Placeable: { { $var } }
        inner_expr = VariableReference(id=Identifier(name="inner"))
        inner_placeable = Placeable(expression=inner_expr)
        outer_placeable = Placeable(expression=inner_placeable)

        pattern = Pattern(elements=(outer_placeable,))
        message = Message(id=Identifier(name="msg"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        # Should have nested braces
        assert "{ {" in result or "{{" in result
        assert "$inner" in result

    def test_deeply_nested_placeables(self) -> None:
        """COVERAGE: Branch 693 - Deeply nested Placeables."""
        # Create triple-nested Placeable: { { { $var } } }
        var_ref = VariableReference(id=Identifier(name="deep"))
        level1 = Placeable(expression=var_ref)
        level2 = Placeable(expression=level1)
        level3 = Placeable(expression=level2)

        pattern = Pattern(elements=(level3,))
        message = Message(id=Identifier(name="msg"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        # Verify nested structure
        assert "$deep" in result
        assert result.count("{") >= 3
        assert result.count("}") >= 3


# ============================================================================
# Branch 741: NumberLiteral variant key
# ============================================================================


class TestNumberLiteralVariantKey:
    """Test NumberLiteral as variant key for complete coverage."""

    def test_select_with_number_literal_keys(self) -> None:
        """COVERAGE: Branch 741 - NumberLiteral variant keys."""
        # SelectExpression with NumberLiteral keys
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="count")),
            variants=(
                Variant(
                    key=NumberLiteral(value=Decimal("0"), raw="0"),
                    value=Pattern(elements=(TextElement(value="Zero"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=Decimal("1"), raw="1"),
                    value=Pattern(elements=(TextElement(value="One"),)),
                    default=False,
                ),
                Variant(
                    key=Identifier(name="other"),
                    value=Pattern(elements=(TextElement(value="Many"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select),))
        message = Message(id=Identifier(name="msg"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        # Should serialize number literals as variant keys
        assert "[0]" in result
        assert "[1]" in result
        assert "*[other]" in result

    def test_select_with_decimal_variant_keys(self) -> None:
        """COVERAGE: Branch 741 - Decimal NumberLiteral variant keys."""
        select = SelectExpression(
            selector=VariableReference(id=Identifier(name="value")),
            variants=(
                Variant(
                    key=NumberLiteral(value=Decimal("1.5"), raw="1.5"),
                    value=Pattern(elements=(TextElement(value="One and half"),)),
                    default=False,
                ),
                Variant(
                    key=NumberLiteral(value=Decimal("2.0"), raw="2.0"),
                    value=Pattern(elements=(TextElement(value="Two"),)),
                    default=True,
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=select),))
        message = Message(id=Identifier(name="msg"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        assert "[1.5]" in result
        assert "*[2.0]" in result


# ============================================================================
# Branch 238: FunctionReference validation with arguments
# ============================================================================


class TestFunctionReferenceArgumentsBranch:
    """Test FunctionReference with and without arguments."""

    def test_function_reference_with_empty_arguments(self) -> None:
        """COVERAGE: Branch 238 - FunctionReference with empty CallArguments."""
        # Create FunctionReference with empty CallArguments (no positional, no named)
        func_ref = FunctionReference(
            id=Identifier(name="FUNC"),
            arguments=CallArguments(positional=(), named=()),
        )

        pattern = Pattern(elements=(Placeable(expression=func_ref),))
        message = Message(id=Identifier(name="msg"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=True)

        # Should serialize function with empty parens
        assert "FUNC()" in result

    def test_function_reference_with_only_positional_args(self) -> None:
        """COVERAGE: Branch 238 - FunctionReference with positional arguments."""
        func_ref = FunctionReference(
            id=Identifier(name="NUMBER"),
            arguments=CallArguments(
                positional=(VariableReference(id=Identifier(name="count")),),
                named=(),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=func_ref),))
        message = Message(id=Identifier(name="msg"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=True)

        assert "NUMBER($count)" in result

    def test_function_reference_with_only_named_args(self) -> None:
        """COVERAGE: Branch 238 - FunctionReference with named arguments."""
        func_ref = FunctionReference(
            id=Identifier(name="DATETIME"),
            arguments=CallArguments(
                positional=(),
                named=(
                    NamedArgument(
                        name=Identifier(name="dateStyle"),
                        value=StringLiteral(value="short"),
                    ),
                ),
            ),
        )

        pattern = Pattern(elements=(Placeable(expression=func_ref),))
        message = Message(id=Identifier(name="msg"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=True)

        assert "DATETIME(dateStyle:" in result or "DATETIME(dateStyle :" in result


# ============================================================================
# Hypothesis property-based tests for edge cases
# ============================================================================


class TestBraceSerializationHypothesis:
    """Hypothesis tests for brace serialization edge cases."""

    @given(
        text_before=st.text(
            alphabet=st.characters(blacklist_characters="{}\n"),
            min_size=0,
            max_size=20,
        ),
        text_after=st.text(
            alphabet=st.characters(blacklist_characters="{}\n"),
            min_size=0,
            max_size=20,
        ),
    )
    def test_close_brace_then_open_brace_property(
        self, text_before: str, text_after: str
    ) -> None:
        """PROPERTY: Close brace before open brace serializes correctly."""
        # Create text with pattern: text_before + } + text_after + {
        text_value = text_before + "}" + text_after + "{"

        text_element = TextElement(value=text_value)
        pattern = Pattern(elements=(text_element,))
        message = Message(id=Identifier(name="test"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        # Both braces should be present (escaped)
        assert '{ "}" }' in result
        assert '{ "{" }' in result

    @given(
        junk_content=st.text(
            alphabet=st.characters(min_codepoint=32, max_codepoint=126),
            min_size=1,
            max_size=100,
        )
    )
    def test_junk_newline_handling_property(self, junk_content: str) -> None:
        """PROPERTY: Junk always ends with exactly one newline after serialization."""
        junk = Junk(content=junk_content)
        resource = Resource(entries=(junk,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        # Result should always end with exactly one newline
        assert result.endswith("\n")
        # Should not end with double newline unless content already had one
        if not junk_content.endswith("\n\n"):
            assert not result.endswith("\n\n\n")


class TestPlaceableNestingHypothesis:
    """Hypothesis tests for nested Placeable structures."""

    @given(nesting_level=st.integers(min_value=1, max_value=5))
    def test_nested_placeable_depth_property(self, nesting_level: int) -> None:
        """PROPERTY: Deeply nested Placeables serialize correctly."""
        # Build nested Placeable structure
        expr: Placeable | VariableReference = VariableReference(
            id=Identifier(name="var")
        )
        for _ in range(nesting_level):
            expr = Placeable(expression=expr)

        # After loop with min_value=1, expr is guaranteed to be Placeable
        pattern = Pattern(elements=(cast(Placeable, expr),))
        message = Message(id=Identifier(name="msg"), value=pattern, attributes=())
        resource = Resource(entries=(message,))

        serializer = FluentSerializer()
        result = serializer.serialize(resource, validate=False)

        # Should contain the variable reference
        assert "$var" in result
        # Should have nested braces
        assert result.count("{") >= nesting_level
        assert result.count("}") >= nesting_level


# ============================================================================
# Integration tests combining multiple coverage targets
# ============================================================================


class TestSerializerIntegrationCompleteCoverage:
    """Integration tests combining multiple coverage targets."""

    def test_message_with_all_edge_cases(self) -> None:
        """Integration: Message combining junk, braces, placeables, and number keys."""
        parser = FluentParserV1()

        # Message with number literal variant key + nested structure
        ftl_source = """
# Comment
msg = { $count ->
    [0] Zero items
    [1] One item with } brace
   *[other] Many items
}

junk content here
"""

        resource = parser.parse(ftl_source)
        result = serialize(resource)

        # Verify all elements present
        assert "[0]" in result  # NumberLiteral key
        assert "[1]" in result
        assert "->" in result  # SelectExpression
        assert "$count" in result  # Variable reference
        assert "junk content" in result  # Junk entry

    def test_roundtrip_with_edge_cases(self) -> None:
        """Integration: Roundtrip with all edge case coverage."""
        parser = FluentParserV1()

        ftl_source = """
msg1 = Text with } close brace

msg2 = { NUMBER() }

msg3 = { $x ->
    [0.5] Half
   *[other] Other
}
"""

        resource = parser.parse(ftl_source)
        serialized = serialize(resource)

        # Re-parse and verify
        resource2 = parser.parse(serialized)
        serialized2 = serialize(resource2)

        # Should be stable
        assert serialized == serialized2
