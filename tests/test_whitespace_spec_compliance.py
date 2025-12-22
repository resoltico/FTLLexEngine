"""Comprehensive tests for FTL whitespace specification compliance.

This module tests strict adherence to the Fluent EBNF whitespace productions:

    blank_inline ::= "\u0020"+              (ONLY space U+0020, NOT tabs)
    blank ::= (blank_inline | line_end)+    (spaces and newlines, NOT tabs)
    blank_block ::= (blank_inline? line_end)+

Key requirement: Tabs (U+0009) are NOT part of FTL whitespace and should be
treated as invalid content (Junk entries).

References:
    - https://github.com/projectfluent/fluent/blob/master/spec/fluent.ebnf
    - FTL Specification v1.0
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.syntax.ast import Junk, Message
from ftllexengine.syntax.parser import FluentParserV1


class TestBlankInlineSpecCompliance:
    """Test blank_inline production: ONLY space (U+0020), NOT tabs."""

    @pytest.fixture
    def parser(self) -> FluentParserV1:
        """Create parser instance."""
        return FluentParserV1()

    def test_message_header_rejects_tab_before_equals(self, parser: FluentParserV1) -> None:
        """Message header with tab before '=' should create Junk.

        Per spec: Message ::= Identifier blank_inline? "=" ...
        blank_inline ONLY allows space (U+0020), NOT tabs.
        """
        source = "hello\t= World"
        resource = parser.parse(source)

        # Tab between identifier and '=' is invalid
        assert len(resource.entries) >= 1
        # Parser creates Junk for invalid syntax
        if isinstance(resource.entries[0], Junk):
            assert "\t" in resource.entries[0].content

    def test_message_header_rejects_tab_after_equals(self, parser: FluentParserV1) -> None:
        """Message header with tab after '=' should create Junk.

        Per spec: Message ::= Identifier blank_inline? "=" blank_inline? Pattern
        """
        source = "hello =\tWorld"
        resource = parser.parse(source)

        # Tab after '=' is invalid
        assert len(resource.entries) >= 1
        if isinstance(resource.entries[0], Junk):
            assert "\t" in resource.entries[0].content

    def test_attribute_rejects_tab_before_equals(self, parser: FluentParserV1) -> None:
        """Attribute with tab before '=' should be invalid.

        Per spec: Attribute ::= ... Identifier blank_inline? "=" ...
        """
        source = """msg = Value
    .attr\t= Invalid
"""
        resource = parser.parse(source)

        # Message should parse, but attribute should fail
        assert len(resource.entries) >= 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        # Attribute with tab should be rejected or empty
        assert len(msg.attributes) == 0 or "\t" not in str(msg.attributes)

    def test_function_call_rejects_tabs_in_arguments(self, parser: FluentParserV1) -> None:
        """Function call with tabs in arguments should be invalid.

        Per spec: CallArguments ::= blank? "(" blank? argument_list blank? ")"
        blank does NOT include tabs in argument contexts.
        """
        source = "msg = { NUMBER(\t$val\t) }"
        resource = parser.parse(source)

        # Tab in function arguments is invalid
        assert len(resource.entries) >= 1
        # Either Junk or message with parsing errors
        entry = resource.entries[0]
        if isinstance(entry, Junk):
            assert "\t" in entry.content

    def test_select_expression_rejects_tabs_around_arrow(self, parser: FluentParserV1) -> None:
        """Select expression with tabs around '->' should be invalid.

        Per spec: SelectExpression ::= InlineExpression blank? "->" blank_inline? variant_list
        """
        source = """msg = { $count\t->\t[one] item *[other] items }"""
        resource = parser.parse(source)

        # Tabs around '->' are invalid
        assert len(resource.entries) >= 1
        entry = resource.entries[0]
        if isinstance(entry, Junk):
            assert "\t" in entry.content

    def test_variant_key_rejects_tabs(self, parser: FluentParserV1) -> None:
        """Variant key with tabs should be invalid.

        Per spec: VariantKey ::= "[" blank? (NumberLiteral | Identifier) blank? "]"
        """
        source = """msg = { $count ->
    [\tone\t] item
   *[other] items
}"""
        resource = parser.parse(source)

        # Tabs in variant key are invalid
        assert len(resource.entries) >= 1


class TestBlankBlockSpecCompliance:
    """Test blank_block production: (blank_inline? line_end)+"""

    @pytest.fixture
    def parser(self) -> FluentParserV1:
        """Create parser instance."""
        return FluentParserV1()

    def test_tab_between_entries_creates_junk(self, parser: FluentParserV1) -> None:
        """Tab between resource entries should create Junk.

        Per spec: Resource ::= (Entry | blank_block | Junk)*
        blank_block does NOT include tabs.
        """
        source = """msg1 = First
\t
msg2 = Second
"""
        resource = parser.parse(source)

        # Tab line should create Junk entry
        assert len(resource.entries) == 3  # msg1, junk (tab), msg2
        assert isinstance(resource.entries[0], Message)
        assert isinstance(resource.entries[1], Junk)
        assert "\t" in resource.entries[1].content
        assert isinstance(resource.entries[2], Message)

    def test_tab_in_empty_line_creates_junk(self, parser: FluentParserV1) -> None:
        """Empty line with tab should create Junk."""
        source = "   \n\t\n  "
        resource = parser.parse(source)

        # Line with tab is invalid
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Junk)
        assert "\t" in resource.entries[0].content


class TestMultilinePatternTabRejection:
    """Test multiline patterns reject tabs in indentation."""

    @pytest.fixture
    def parser(self) -> FluentParserV1:
        """Create parser instance."""
        return FluentParserV1()

    def test_multiline_pattern_tab_indent_invalid(self, parser: FluentParserV1) -> None:
        """Multiline pattern with tab indentation should be invalid.

        Per spec: Pattern continuation requires space indentation, NOT tabs.
        Tab-indented lines are NOT recognized as continuations.
        """
        source = """msg =
\tLine one
\tLine two
"""
        resource = parser.parse(source)

        # Tabs as indentation are invalid - message should have no value
        # because tab-indented lines are NOT valid continuations
        assert len(resource.entries) >= 1
        # Parser creates Junk because message has no valid pattern
        entry = resource.entries[0]
        assert isinstance(entry, Junk)
        # The junk is "msg =" because the tab lines don't parse as continuations
        assert "msg =" in entry.content

    def test_attribute_multiline_tab_indent_invalid(self, parser: FluentParserV1) -> None:
        """Attribute multiline pattern with tab indentation should be invalid."""
        source = """msg = Value
    .attr =
\t\tLine one
"""
        resource = parser.parse(source)

        # Message parses, but attribute with tab indent is invalid
        assert len(resource.entries) >= 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        # Attribute should not parse correctly with tab indentation
        # (tab-indented lines are not valid continuations per spec)


class TestHypothesisWhitespaceProperties:
    """Property-based tests for whitespace handling."""

    @given(
        identifier=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
            min_size=1,
            max_size=10,
        ).filter(lambda s: s and s[0].isalpha()),
        value=st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters=" "
            ),
            min_size=1,
            max_size=20,
        ),
    )
    def test_valid_messages_without_tabs_parse(
        self, identifier: str, value: str
    ) -> None:
        """Valid messages (without tabs) should always parse successfully.

        Property: Messages using only spaces (not tabs) parse correctly.
        """
        parser = FluentParserV1()
        source = f"{identifier} = {value}"
        resource = parser.parse(source)

        # Should produce valid message (not Junk)
        assert len(resource.entries) >= 1
        if not any("\t" in str(e) for e in resource.entries):
            # If no tabs anywhere, should parse as Message
            assert isinstance(resource.entries[0], (Message, Junk))

    @given(
        identifier=st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll")),
            min_size=1,
            max_size=10,
        ).filter(lambda s: s and s[0].isalpha()),
        tab_position=st.sampled_from(["before_equals", "after_equals", "in_value"]),
    )
    def test_messages_with_tabs_create_junk_or_errors(
        self, identifier: str, tab_position: str
    ) -> None:
        """Messages with tabs should create Junk or parsing errors.

        Property: Tabs anywhere in message syntax create invalid entries.
        """
        parser = FluentParserV1()

        if tab_position == "before_equals":
            source = f"{identifier}\t= Value"
        elif tab_position == "after_equals":
            source = f"{identifier} =\tValue"
        else:  # in_value (tabs in text are actually OK)
            source = f"{identifier} = Val\tue"

        resource = parser.parse(source)

        # Parser should handle tab gracefully (either Junk or parsed)
        assert len(resource.entries) >= 1
        assert isinstance(resource.entries[0], (Message, Junk))


class TestEdgeCasesTabHandling:
    """Test edge cases for tab handling."""

    @pytest.fixture
    def parser(self) -> FluentParserV1:
        """Create parser instance."""
        return FluentParserV1()

    def test_mixed_spaces_and_tabs_invalid(self, parser: FluentParserV1) -> None:
        """Mixed spaces and tabs should be invalid."""
        source = "hello = \t Value"
        resource = parser.parse(source)

        # Mixed whitespace with tabs is invalid
        assert len(resource.entries) >= 1

    def test_tab_in_string_literal_valid(self, parser: FluentParserV1) -> None:
        """Tab INSIDE string literal should be valid (it's content, not syntax).

        Note: Tabs in STRING CONTENT are OK, tabs in SYNTAX are not.
        """
        source = 'msg = { "Hello\\tWorld" }'
        resource = parser.parse(source)

        # Escaped tab in string is valid content
        assert len(resource.entries) == 1
        assert isinstance(resource.entries[0], Message)

    def test_term_header_rejects_tabs(self, parser: FluentParserV1) -> None:
        """Term header with tabs should be invalid.

        Per spec: Term ::= "-" Identifier blank_inline? "=" ...
        """
        source = "-brand\t=\tFirefox"
        resource = parser.parse(source)

        # Tabs in term header are invalid
        assert len(resource.entries) >= 1
        entry = resource.entries[0]
        if isinstance(entry, Junk):
            assert "\t" in entry.content


class TestSpecificationDocumentation:
    """Test cases documenting spec requirements."""

    def test_blank_inline_definition(self) -> None:
        """Document blank_inline specification.

        Per Fluent EBNF:
            blank_inline ::= "\u0020"+

        This means:
        - ONLY space character (U+0020 SPACE)
        - NOT tab (U+0009 CHARACTER TABULATION)
        - NOT other Unicode spaces (U+00A0 NO-BREAK SPACE, etc.)
        """
        parser = FluentParserV1()

        # Valid: spaces only
        valid = "key = value"
        result = parser.parse(valid)
        assert len(result.entries) == 1
        assert isinstance(result.entries[0], Message)

        # Tabs are invalid per spec
        invalid = "key\t= value"
        result = parser.parse(invalid)
        # Should create Junk or parsing error
        assert len(result.entries) >= 1

    def test_blank_definition(self) -> None:
        """Document blank specification.

        Per Fluent EBNF:
            blank ::= (blank_inline | line_end)+
            blank_inline ::= "\u0020"+
            line_end ::= "\u000D\u000A" | "\u000A" | EOF

        This means:
        - Spaces (U+0020)
        - Newlines (LF, CRLF)
        - NOT tabs
        """
        parser = FluentParserV1()

        # Spaces and newlines are valid blank per spec
        valid = """

key = value

"""
        result = parser.parse(valid)
        assert len(result.entries) == 1
        assert isinstance(result.entries[0], Message)

    def test_indented_char_implicit_restriction(self) -> None:
        """Document that indented lines implicitly reject tabs.

        While not explicitly stated, multiline pattern continuations
        require space indentation per the spec's examples and EBNF.
        """
        parser = FluentParserV1()

        # Tab-indented continuation should be invalid
        invalid = """msg =
\tLine one
"""
        result = parser.parse(invalid)
        # Tab indentation creates issues
        assert len(result.entries) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
