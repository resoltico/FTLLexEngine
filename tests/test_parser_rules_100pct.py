"""Final coverage tests to achieve 100% coverage for ftllexengine.syntax.parser.rules.

This module provides targeted tests for the remaining uncovered lines and branches
in the rules.py parser module. Focuses on edge cases that achieve complete coverage.

Coverage Targets:
- Line 1002: EOF handling in parse_select_expression variant loop
- Branch 1001: cursor.is_eof condition after skip_blank in variant parsing

Test Strategy:
- Property-based tests using Hypothesis for systematic edge case exploration
- Explicit examples for critical paths
- Malformed input handling (missing closing braces, EOF scenarios)
"""

from __future__ import annotations

from hypothesis import event, example, given
from hypothesis import strategies as st

from ftllexengine.syntax.ast import VariableReference
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    parse_select_expression,
)


class TestParseSelectExpressionEOF:
    """Coverage for parse_select_expression EOF handling (line 1002).

    Targets the specific case where skip_blank() advances cursor to EOF
    within the variant parsing loop, triggering the break on line 1002.
    """

    def test_select_expression_eof_after_variant_whitespace(self) -> None:
        """Line 1002: EOF reached after skip_blank between variants.

        This tests the case where a select expression has a variant followed
        by non-indented newlines (no spaces), causing skip_blank to advance
        to EOF and trigger the break statement on line 1002.

        Critical: Use newlines WITHOUT spaces - spaces cause is_indented_continuation
        to return TRUE, making parse_simple_pattern consume them as continuation lines.
        """
        # Variant followed by non-indented newlines (no spaces before newlines)
        source = "*[other] value\n\n\n"
        cursor = Cursor(source, 0)

        # Create a selector (required by parse_select_expression)
        selector = VariableReference(id=None)  # type: ignore[arg-type]

        # Parse select expression
        result = parse_select_expression(
            cursor, selector, start_pos=0, context=ParseContext()
        )

        # Parse succeeds with one variant:
        # 1. parse_variant parses "*[other] value" and stops at first \n (pos 14)
        # 2. Loop iteration 2: skip_blank at line 999 skips "\n\n\n" to EOF (pos 17)
        # 3. Line 1001: cursor.is_eof is TRUE
        # 4. Line 1002: break executes (THIS IS THE TARGET LINE)
        # 5. Function returns SelectExpression with one variant
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof

    def test_select_expression_eof_after_skip_blank_multiple_newlines(self) -> None:
        """Line 1002: EOF with multiple blank lines after variant."""
        # Multiple non-indented newlines after variant
        source = "*[other] text\n\n\n\n"
        cursor = Cursor(source, 0)
        selector = VariableReference(id=None)  # type: ignore[arg-type]

        result = parse_select_expression(
            cursor, selector, start_pos=0, context=ParseContext()
        )

        # Should reach EOF after skip_blank on line 999, trigger line 1002 break
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof

    def test_select_expression_eof_single_newline(self) -> None:
        """Line 1002: EOF with single newline after variant."""
        # Single non-indented newline after variant
        source = "*[default] value\n"
        cursor = Cursor(source, 0)
        selector = VariableReference(id=None)  # type: ignore[arg-type]

        result = parse_select_expression(
            cursor, selector, start_pos=0, context=ParseContext()
        )

        # EOF reached after skip_blank triggers line 1002
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof

    @given(st.integers(min_value=1, max_value=20))  # Number of newlines only
    @example(1)  # Single newline
    @example(5)  # Multiple newlines
    @example(20)  # Many newlines
    def test_select_expression_eof_property(self, num_newlines: int) -> None:
        """Property: EOF after variant with non-indented newlines.

        Tests that various numbers of non-indented newlines after a variant
        correctly trigger the EOF handling branch on line 1002.

        Note: We use only newlines (no spaces) because spaces would cause
        is_indented_continuation to return TRUE, making parse_simple_pattern
        consume them as continuation lines.
        """
        event(f"num_newlines={num_newlines}")
        # Create variant with trailing non-indented newlines
        whitespace = "\n" * num_newlines
        source = f"*[other] value{whitespace}"
        cursor = Cursor(source, 0)
        selector = VariableReference(id=None)  # type: ignore[arg-type]

        result = parse_select_expression(
            cursor, selector, start_pos=0, context=ParseContext()
        )

        # All cases should succeed with EOF reached via line 1002 break
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof

    def test_select_expression_eof_empty_pattern(self) -> None:
        """Line 1002: Variant with empty pattern followed by EOF."""
        # Variant with empty pattern (nothing after ]), then newlines
        source = "*[other]\n\n"
        cursor = Cursor(source, 0)
        selector = VariableReference(id=None)  # type: ignore[arg-type]

        result = parse_select_expression(
            cursor, selector, start_pos=0, context=ParseContext()
        )

        # Empty pattern is valid, EOF reached via line 1002
        assert result is not None
        assert len(result.value.variants) == 1
        assert len(result.value.variants[0].value.elements) == 0  # Empty pattern
        assert result.cursor.is_eof

    def test_select_expression_multiple_variants_eof(self) -> None:
        """Line 1002: Multiple variants with EOF after last one."""
        # Two variants, then non-indented newlines to EOF
        source = "[one] singular\n*[other] plural\n\n"
        cursor = Cursor(source, 0)
        selector = VariableReference(id=None)  # type: ignore[arg-type]

        result = parse_select_expression(
            cursor, selector, start_pos=0, context=ParseContext()
        )

        # Parse both variants, then EOF via line 1002
        assert result is not None
        assert len(result.value.variants) == 2
        assert result.cursor.is_eof

    def test_select_expression_eof_after_complex_pattern(self) -> None:
        """Line 1002: Complex pattern in variant, then EOF."""
        # Variant with longer text pattern, followed by newlines
        source = "*[other] You have items\n\n"
        cursor = Cursor(source, 0)
        selector = VariableReference(id=None)  # type: ignore[arg-type]

        result = parse_select_expression(
            cursor, selector, start_pos=0, context=ParseContext()
        )

        # Pattern parsed successfully, EOF via line 1002
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof

    @given(st.text(alphabet="\n", min_size=1, max_size=50))
    @example("\n")
    @example("\n\n\n")
    @example("\n\n\n\n\n")
    def test_select_expression_eof_arbitrary_newlines(self, whitespace: str) -> None:
        """Property: Non-indented newlines after variant trigger line 1002.

        Hypothesis generates various newline sequences (no spaces) to ensure
        the EOF handling on line 1002 is robust. Spaces are excluded because
        they cause is_indented_continuation to return TRUE.
        """
        event(f"ws_len={len(whitespace)}")
        source = f"*[other] text{whitespace}"
        cursor = Cursor(source, 0)
        selector = VariableReference(id=None)  # type: ignore[arg-type]

        result = parse_select_expression(
            cursor, selector, start_pos=0, context=ParseContext()
        )

        # All should succeed with EOF via line 1002
        assert result is not None
        assert len(result.value.variants) == 1
        assert result.cursor.is_eof


class TestParseSelectExpressionBranchCoverage:
    """Additional branch coverage for parse_select_expression.

    Ensures all conditional branches in the function are exercised,
    including edge cases around variant parsing and EOF handling.
    """

    def test_select_expression_immediate_eof_after_arrow(self) -> None:
        """Branch coverage: EOF immediately after -> operator."""
        # Just the arrow, then EOF
        source = ""
        cursor = Cursor(source, 0)
        selector = VariableReference(id=None)  # type: ignore[arg-type]

        result = parse_select_expression(
            cursor, selector, start_pos=0, context=ParseContext()
        )

        # Should return None because no variants found
        assert result is None

    def test_select_expression_whitespace_then_eof(self) -> None:
        """Branch coverage: Only whitespace after arrow, then EOF."""
        # Arrow followed by just whitespace
        source = "  \n  "
        cursor = Cursor(source, 0)
        selector = VariableReference(id=None)  # type: ignore[arg-type]

        result = parse_select_expression(
            cursor, selector, start_pos=0, context=ParseContext()
        )

        # No variants parsed, should return None
        assert result is None

    @given(
        st.lists(
            st.sampled_from(["[one]", "[two]", "[zero]", "*[other]"]),
            min_size=1,
            max_size=5,
        )
    )
    @example(["*[other]"])
    @example(["[one]", "*[other]"])
    def test_select_expression_variants_with_eof_property(
        self, variant_keys: list[str]
    ) -> None:
        """Property: Various variant configurations with EOF handling.

        Tests that different numbers and types of variants all
        correctly handle EOF after the last variant via line 1002.
        """
        num_keys = len(variant_keys)
        has_default = any("*" in k for k in variant_keys)
        event(f"num_variants={num_keys}")
        event(f"has_default={has_default}")
        # Build select expression with variants and non-indented newlines
        variants_text = "\n".join(f"{key} text" for key in variant_keys)
        source = f"{variants_text}\n\n"
        cursor = Cursor(source, 0)
        selector = VariableReference(id=None)  # type: ignore[arg-type]

        result = parse_select_expression(
            cursor, selector, start_pos=0, context=ParseContext()
        )

        # Check default variant count (spec requires exactly one)
        default_count = sum(1 for key in variant_keys if "*" in key)

        if default_count == 1:
            # Valid: exactly one default variant
            assert result is not None
            assert len(result.value.variants) == len(variant_keys)
            assert result.cursor.is_eof
        else:
            # Invalid: zero or multiple default variants
            assert result is None
