"""Tests for multiline pattern blank line indentation handling.

FTL-GRAMMAR-001 regression tests: Verifies that blank lines before the first
content line in a multiline pattern do not corrupt common_indent calculation.

The bug occurred when:
1. is_indented_continuation() correctly skipped all blank lines to find content
2. parse_pattern() only advanced past ONE newline before measuring common_indent
3. If cursor landed on a blank line, _count_leading_spaces() returned 0
4. All subsequent indentation was preserved literally instead of stripped

This module tests both parse_pattern() (top-level patterns) and
parse_simple_pattern() (variant patterns) for this edge case.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ftllexengine import parse_ftl
from ftllexengine.runtime.bundle import FluentBundle
from ftllexengine.syntax.ast import Message, Term, TextElement


class TestBlankLineBeforeFirstContent:
    """Tests for blank lines preceding first content in multiline patterns."""

    def test_single_blank_line_before_content(self) -> None:
        """Single blank line before first content line strips indentation correctly."""
        ftl = "msg =\n\n    value"
        resource = parse_ftl(ftl)

        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        pattern = msg.value
        assert len(pattern.elements) == 1
        assert isinstance(pattern.elements[0], TextElement)
        # Indentation should be stripped - value should NOT include leading spaces
        assert pattern.elements[0].value == "value"

    def test_multiple_blank_lines_before_content(self) -> None:
        """Multiple blank lines before first content line strips indentation correctly."""
        ftl = "msg =\n\n\n\n    value"
        resource = parse_ftl(ftl)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.value.elements) == 1
        assert isinstance(msg.value.elements[0], TextElement)
        # Indentation should be stripped
        assert msg.value.elements[0].value == "value"

    def test_blank_line_with_subsequent_lines(self) -> None:
        """Blank line before content with subsequent lines preserves structure."""
        ftl = "msg =\n\n    first\n    second"
        resource = parse_ftl(ftl)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        # Should have combined text with newline
        text = "".join(
            elem.value for elem in msg.value.elements if isinstance(elem, TextElement)
        )
        assert text == "first\nsecond"

    def test_blank_line_with_extra_indentation(self) -> None:
        """Blank line before content preserves extra indentation on subsequent lines."""
        ftl = "msg =\n\n    first\n        second"
        resource = parse_ftl(ftl)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        text = "".join(
            elem.value for elem in msg.value.elements if isinstance(elem, TextElement)
        )
        # Common indent is 4 (from "first"), so "second" has 4 extra spaces
        assert text == "first\n    second"

    def test_blank_line_bundle_format(self) -> None:
        """FluentBundle correctly formats messages with blank line before content."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg =\n\n    Hello World")

        result, errors = bundle.format_pattern("msg")

        assert not errors
        assert result == "Hello World"

    def test_blank_line_with_placeable(self) -> None:
        """Blank line before content with placeable works correctly."""
        bundle = FluentBundle("en_US")
        bundle.add_resource("msg =\n\n    Hello { $name }")

        result, errors = bundle.format_pattern("msg", {"name": "Alice"})

        assert not errors
        # Fluent uses Unicode bidi isolation (\u2068...\u2069) around placeables
        assert "Hello" in result
        assert "Alice" in result


class TestVariantBlankLineIndentation:
    """Tests for blank lines in variant (select expression) patterns."""

    def test_variant_with_blank_line_before_content(self) -> None:
        """Variant pattern with blank line before content strips indentation."""
        ftl = """count = { $n ->
    [one]

        single item
    *[other]

        multiple items
}"""
        bundle = FluentBundle("en_US")
        bundle.add_resource(ftl)

        # Test singular - Fluent uses Unicode bidi isolation around select results
        result, errors = bundle.format_pattern("count", {"n": 1})
        assert not errors
        assert "single item" in result

        # Test plural
        result, errors = bundle.format_pattern("count", {"n": 5})
        assert not errors
        assert "multiple items" in result


class TestEdgeCasesBlankLineIndent:
    """Edge cases for blank line indentation handling."""

    def test_message_with_only_attributes(self) -> None:
        """Message with empty value but attributes (attribute-only syntax)."""
        # Per Fluent spec, a message can have just attributes without a value
        # Using the attribute-only syntax: msg =\n    .attr = value
        ftl = "msg =\n    .attr = value"
        resource = parse_ftl(ftl)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        # Message has no value pattern, only attribute
        assert len(msg.attributes) == 1
        assert msg.attributes[0].id.name == "attr"

    def test_blank_line_at_end_not_at_start(self) -> None:
        """Blank line at end of pattern (not start) handled correctly."""
        ftl = "msg =\n    first\n\n    second"
        resource = parse_ftl(ftl)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        text = "".join(
            elem.value for elem in msg.value.elements if isinstance(elem, TextElement)
        )
        # Blank line between content should be preserved as newline
        assert "first" in text
        assert "second" in text

    def test_mixed_blank_lines_throughout(self) -> None:
        """Pattern with blank lines at various positions handled correctly."""
        ftl = "msg =\n\n    first\n\n    second\n\n    third"
        resource = parse_ftl(ftl)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        text = "".join(
            elem.value for elem in msg.value.elements if isinstance(elem, TextElement)
        )
        assert "first" in text
        assert "second" in text
        assert "third" in text

    def test_term_with_blank_line_before_content(self) -> None:
        """Term definition with blank line before content works correctly."""
        ftl = "-brand =\n\n    Firefox"
        resource = parse_ftl(ftl)

        assert len(resource.entries) == 1
        term = resource.entries[0]
        assert isinstance(term, Term)
        assert term.value is not None
        text = "".join(
            elem.value for elem in term.value.elements if isinstance(elem, TextElement)
        )
        assert text == "Firefox"


class TestHypothesisBlankLinePatterns:
    """Property-based tests for blank line pattern handling."""

    @given(
        num_blank_lines=st.integers(min_value=1, max_value=10),
        indent_size=st.integers(min_value=1, max_value=8),
    )
    def test_varying_blank_lines_and_indentation(
        self, num_blank_lines: int, indent_size: int
    ) -> None:
        """Property: Any number of blank lines before content should strip indent."""
        blank_lines = "\n" * num_blank_lines
        indent = " " * indent_size
        ftl = f"msg ={blank_lines}{indent}content"

        resource = parse_ftl(ftl)

        assert len(resource.entries) == 1
        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.value.elements) == 1
        assert isinstance(msg.value.elements[0], TextElement)
        # Regardless of blank lines or indent size, content should be stripped
        assert msg.value.elements[0].value == "content"

    @given(content=st.text(min_size=1, max_size=50, alphabet="abcdefghijklmnopqrstuvwxyz"))
    def test_content_preserved_after_blank_lines(self, content: str) -> None:
        """Property: Content after blank lines is preserved exactly."""
        ftl = f"msg =\n\n    {content}"

        resource = parse_ftl(ftl)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        text = "".join(
            elem.value for elem in msg.value.elements if isinstance(elem, TextElement)
        )
        assert text == content


class TestRegressionBlankLineIndentBug:
    """Specific regression tests for the FTL-GRAMMAR-001 bug."""

    def test_original_bug_scenario(self) -> None:
        """Exact scenario from bug report: blank line sets common_indent to 0.

        Before fix: common_indent was set to 0 when cursor was at blank line.
        After fix: blank lines are skipped before measuring common_indent.
        """
        # This was the failing case:
        # msg =
        #
        #     value
        # Expected: "value" (4-space indent stripped)
        # Actual (bug): "    value" (indent preserved because common_indent=0)
        ftl = "msg =\n\n    value"
        resource = parse_ftl(ftl)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        assert len(msg.value.elements) == 1
        element = msg.value.elements[0]
        assert isinstance(element, TextElement)
        # The bug would have preserved "    value" - this must be "value"
        assert element.value == "value", (
            f"common_indent bug: expected 'value', got '{element.value}'"
        )

    def test_bug_variant_simple_pattern(self) -> None:
        """Regression test for parse_simple_pattern (variant patterns)."""
        ftl = """msg = { $n ->
    [one]

        item
    *[other] items
}"""
        bundle = FluentBundle("en_US")
        bundle.add_resource(ftl)

        result, errors = bundle.format_pattern("msg", {"n": 1})

        assert not errors
        # Should be "item", not "        item" (8 spaces preserved)
        # Note: Fluent uses Unicode bidi isolation around select results
        assert "item" in result, f"parse_simple_pattern bug: got '{result}'"
        # Verify no excessive indentation (the bug would preserve 8 spaces)
        assert "        item" not in result, f"Indentation not stripped: got '{result}'"

    @pytest.mark.parametrize(
        ("ftl", "expected"),
        [
            ("msg =\n\n    x", "x"),
            ("msg =\n\n\n    x", "x"),
            ("msg =\n\n\n\n\n    x", "x"),
            ("msg =\n\n        x", "x"),  # 8 spaces
            ("msg =\n\n            x", "x"),  # 12 spaces
        ],
    )
    def test_parametrized_blank_line_scenarios(self, ftl: str, expected: str) -> None:
        """Parametrized tests for various blank line scenarios."""
        resource = parse_ftl(ftl)

        msg = resource.entries[0]
        assert isinstance(msg, Message)
        assert msg.value is not None
        text = "".join(
            elem.value for elem in msg.value.elements if isinstance(elem, TextElement)
        )
        assert text == expected
