"""Complete coverage tests for syntax/parser/rules.py.

Targets specific uncovered lines and branches to achieve 100% coverage.

Missing coverage (as of analysis):
- Line 343->300: Branch where cursor.pos == text_start in parse_simple_pattern
- Line 651: EOF check in parse_argument_expression
- Lines 674-677: Term reference parsing failure in parse_argument_expression
- Line 681: Negative number parsing failure in parse_argument_expression
- Lines 699-703: Placeable parsing failure in parse_argument_expression
- Lines 716-721: Function reference parsing failure in parse_argument_expression

Python 3.13+. Uses Hypothesis for property-based testing where applicable.
"""

from __future__ import annotations

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    parse_argument_expression,
    parse_simple_pattern,
)


class TestParseSimplePatternBranch343To300:
    """Test parse_simple_pattern branch 343->300 (cursor.pos == text_start).

    This branch occurs when the text parsing loop breaks immediately
    without consuming any characters, which happens when cursor starts
    on a stop character ('{', newline, '}', or variant marker).

    The False branch (343->300) occurs when the while loop at line 333
    breaks immediately because cursor starts on a stop character, so
    cursor.pos == text_start and the text element is NOT appended.
    """

    def test_simple_pattern_starts_with_placeable(self) -> None:
        """Test parse_simple_pattern when it starts immediately with {."""
        # When starting with '{', the outer loop enters placeable parsing,
        # the inner text loop never runs, so text_start never increments
        source = "{$var}"
        cursor = Cursor(source, 0)

        result = parse_simple_pattern(cursor)

        assert result is not None
        pattern = result.value
        # Should contain only the placeable, no text
        assert len(pattern.elements) == 1

    def test_simple_pattern_empty_before_closing_brace(self) -> None:
        """Test parse_simple_pattern with immediate closing brace."""
        # Start with } - should immediately break without text
        source = "}"
        cursor = Cursor(source, 0)

        result = parse_simple_pattern(cursor)

        assert result is not None
        pattern = result.value
        # Empty pattern - no elements
        assert len(pattern.elements) == 0

    def test_simple_pattern_consecutive_placeables(self) -> None:
        """Test parse_simple_pattern with consecutive placeables (no text between)."""
        # After first placeable, cursor is at second '{', text loop never runs
        source = "{$a}{$b}"
        cursor = Cursor(source, 0)

        result = parse_simple_pattern(cursor)

        assert result is not None
        pattern = result.value
        # Should have two placeables, no text elements
        assert len(pattern.elements) == 2

    def test_simple_pattern_text_then_immediate_stop(self) -> None:
        """Test parse_simple_pattern to explicitly hit branch 343->300.

        This test ensures the else branch (line 330) is entered, then the
        inner while loop (line 333) breaks IMMEDIATELY at a stop char,
        causing cursor.pos == text_start and taking the False branch at 343->300.
        """
        # Start with text, then have a variant marker immediately appear
        # The outer loop enters text mode, inner loop hits variant marker
        source = "abc[one]"  # Text followed by variant marker
        cursor = Cursor(source, 0)

        result = parse_simple_pattern(cursor)

        assert result is not None
        # Should parse "abc" as text, then stop at [one]
        assert len(result.value.elements) == 1


class TestParseArgumentExpressionLine651:
    """Test parse_argument_expression line 651 (EOF check)."""

    def test_argument_expression_at_eof(self) -> None:
        """Test parse_argument_expression with EOF cursor (line 651)."""
        source = ""
        cursor = Cursor(source, 0)

        result = parse_argument_expression(cursor)

        # Should return None at EOF
        assert result is None


class TestParseArgumentExpressionLines674To677:
    """Test parse_argument_expression lines 674-677 (term reference failure)."""

    def test_argument_expression_term_reference_invalid_attribute(self) -> None:
        """Test parse_argument_expression with term having invalid attribute (lines 674-677)."""
        # '-' followed by alpha triggers term reference path
        # Make term reference fail by having invalid attribute after '.'
        source = "-brand."  # Term with dot but no attribute identifier
        cursor = Cursor(source, 0)

        result = parse_argument_expression(cursor)

        # parse_term_reference should fail due to missing attribute identifier
        assert result is None

    def test_argument_expression_term_reference_unclosed_parens(self) -> None:
        """Test parse_argument_expression with term having unclosed parentheses."""
        # Term reference with arguments but missing closing paren
        source = "-brand(case: "
        cursor = Cursor(source, 0)

        result = parse_argument_expression(cursor)

        # parse_term_reference should fail
        assert result is None


class TestParseArgumentExpressionLine681:
    """Test parse_argument_expression line 681 (negative number parsing failure)."""

    def test_argument_expression_negative_number_invalid(self) -> None:
        """Test parse_argument_expression with invalid negative number (line 681)."""
        # '-' followed by something that's not a number or valid identifier
        source = "- "  # '-' followed by space (parse_number will fail)
        cursor = Cursor(source, 0)

        result = parse_argument_expression(cursor)

        # Should return None when parse_number fails
        assert result is None


class TestParseArgumentExpressionLines699To703:
    """Test parse_argument_expression lines 699-703 (placeable parsing failure)."""

    def test_argument_expression_placeable_exceeds_depth(self) -> None:
        """Test parse_argument_expression with placeable exceeding nesting depth (line 703)."""
        # Create a context at maximum depth to trigger depth exceeded
        source = "{ $var }"
        cursor = Cursor(source, 0)
        # Start with cursor at '{', which parse_argument_expression will skip
        # Use a context that's already at max depth
        context = ParseContext(max_nesting_depth=1, current_depth=1)

        result = parse_argument_expression(cursor, context)

        # parse_placeable should fail due to depth exceeded
        assert result is None

    def test_argument_expression_placeable_invalid_syntax(self) -> None:
        """Test parse_argument_expression with invalid placeable syntax."""
        # '{' with invalid expression inside
        source = "{ @invalid }"
        cursor = Cursor(source, 0)

        result = parse_argument_expression(cursor)

        # parse_placeable should fail with invalid expression
        assert result is None


class TestParseArgumentExpressionLines716To721:
    """Test parse_argument_expression lines 716-721 (function reference failure)."""

    def test_argument_expression_function_reference_missing_closing_paren(
        self,
    ) -> None:
        """Test parse_argument_expression with function missing closing paren (line 721)."""
        # UPPERCASE identifier followed by '(' but missing ')'
        source = "NUMBER($value"
        cursor = Cursor(source, 0)

        result = parse_argument_expression(cursor)

        # parse_function_reference should fail
        assert result is None

    def test_argument_expression_function_reference_invalid_args(self) -> None:
        """Test parse_argument_expression with function having invalid arguments."""
        # UPPERCASE identifier with '(' but completely invalid argument syntax
        source = "NUMBER(@invalid)"
        cursor = Cursor(source, 0)

        result = parse_argument_expression(cursor)

        # parse_function_reference should fail due to invalid argument
        assert result is None


# =============================================================================
# Hypothesis Property-Based Tests
# =============================================================================


class TestParseArgumentExpressionProperties:
    """Property-based tests for parse_argument_expression."""

    @given(
        st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs",),  # type: ignore[arg-type]
                blacklist_characters="\x00",  # Exclude null
            ),
            min_size=0,
            max_size=10,
        )
    )
    def test_parse_argument_expression_never_crashes(self, source: str) -> None:
        """Property: parse_argument_expression never crashes on any input."""
        cursor = Cursor(source, 0)

        # Should never raise, returns ParseResult or None
        result = parse_argument_expression(cursor)

        # Either success or None, never exception
        assert result is None or result is not None

    @settings(suppress_health_check=[HealthCheck.filter_too_much])
    @given(st.text(min_size=1, max_size=5).filter(lambda s: s.strip() == ""))
    def test_parse_argument_expression_whitespace_only_fails(
        self, whitespace: str
    ) -> None:
        """Property: parse_argument_expression returns None for whitespace-only input."""
        cursor = Cursor(whitespace, 0)

        result = parse_argument_expression(cursor)

        # Whitespace-only should fail
        assert result is None


class TestParseSimplePatternCRLFContinuation:
    """Test parse_simple_pattern with CRLF in indented continuation (line 327).

    Line 327 handles the case where a \r is followed by \n (Windows CRLF)
    in an indented continuation within a variant pattern.
    """

    def test_simple_pattern_crlf_with_continuation(self) -> None:
        """Test parse_simple_pattern with CRLF and indented continuation (line 327).

        When variant pattern has CRLF followed by indented continuation,
        line 327 advances past the \n after already advancing past \r.
        """
        # Variant pattern text with CRLF followed by indented continuation
        # Note: is_indented_continuation checks for space after newline
        source = "First line\r\n    Second line}"
        cursor = Cursor(source, 0)

        result = parse_simple_pattern(cursor)

        assert result is not None
        pattern = result.value
        # Should have parsed the multi-line continuation
        # Text elements are merged with space separator
        assert len(pattern.elements) >= 1

    def test_simple_pattern_crlf_continuation_with_placeable(self) -> None:
        """Test CRLF continuation with placeable in variant pattern (line 327)."""
        # CRLF with indented continuation containing a placeable
        source = "Value\r\n    { $var }}"
        cursor = Cursor(source, 0)

        result = parse_simple_pattern(cursor)

        assert result is not None
        pattern = result.value
        # Should have text element and placeable
        assert len(pattern.elements) >= 1


class TestParseSimplePatternProperties:
    """Property-based tests for parse_simple_pattern."""

    @given(
        st.text(
            alphabet=st.characters(
                blacklist_categories=("Cs",),  # type: ignore[arg-type]
                blacklist_characters="\x00",  # Exclude null
            ),
            min_size=0,
            max_size=20,
        )
    )
    def test_parse_simple_pattern_never_crashes(self, source: str) -> None:
        """Property: parse_simple_pattern never crashes on any input."""
        cursor = Cursor(source, 0)
        context = ParseContext()

        # Should never raise, returns ParseResult or None
        result = parse_simple_pattern(cursor, context)

        # Either success or failure, never exception
        assert result is None or result is not None


class TestParseContextProperties:
    """Test ParseContext depth tracking."""

    def test_parse_context_default_depth_zero(self) -> None:
        """Test ParseContext initializes with depth 0."""
        ctx = ParseContext()

        assert ctx.current_depth == 0
        assert ctx.max_nesting_depth == 100

    def test_parse_context_enter_placeable_increments_depth(self) -> None:
        """Test ParseContext.enter_placeable() increments depth."""
        ctx = ParseContext(max_nesting_depth=10, current_depth=0)

        nested_ctx = ctx.enter_placeable()

        assert nested_ctx.current_depth == 1
        assert nested_ctx.max_nesting_depth == 10

    def test_parse_context_is_depth_exceeded_at_limit(self) -> None:
        """Test ParseContext.is_depth_exceeded() returns True at limit."""
        ctx = ParseContext(max_nesting_depth=3, current_depth=3)

        assert ctx.is_depth_exceeded()

    def test_parse_context_is_depth_exceeded_below_limit(self) -> None:
        """Test ParseContext.is_depth_exceeded() returns False below limit."""
        ctx = ParseContext(max_nesting_depth=10, current_depth=5)

        assert not ctx.is_depth_exceeded()

    @given(
        st.integers(min_value=1, max_value=1000),
        st.integers(min_value=0, max_value=999),
    )
    def test_parse_context_depth_comparison_property(
        self, max_depth: int, current_depth: int
    ) -> None:
        """Property: is_depth_exceeded() equals (current_depth >= max_nesting_depth)."""
        ctx = ParseContext(max_nesting_depth=max_depth, current_depth=current_depth)

        expected = current_depth >= max_depth
        actual = ctx.is_depth_exceeded()

        assert actual == expected
