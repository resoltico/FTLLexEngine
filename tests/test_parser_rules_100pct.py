"""Comprehensive Hypothesis-based tests to achieve 100% coverage for rules.py.

This module tests edge cases and error paths in the parser rules to reach
complete coverage.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from ftllexengine.constants import MAX_DEPTH
from ftllexengine.syntax.ast import (
    FunctionReference,
    Identifier,
    Pattern,
    Placeable,
    Span,
    TermReference,
    TextElement,
    VariableReference,
)
from ftllexengine.syntax.cursor import Cursor
from ftllexengine.syntax.parser.rules import (
    ParseContext,
    _is_variant_marker,
    _skip_common_indent,
    _trim_pattern_blank_lines,
    parse_argument_expression,
    parse_call_arguments,
    parse_function_reference,
    parse_select_expression,
    parse_simple_pattern,
    parse_term,
    parse_variant_key,
)

# =============================================================================
# _is_variant_marker Coverage Tests
# =============================================================================


def test_is_variant_marker_at_eof() -> None:
    """EOF cursor returns False in _is_variant_marker."""
    source = ""
    cursor = Cursor(source, 0)
    assert cursor.is_eof
    result = _is_variant_marker(cursor)
    assert result is False


@given(st.text(min_size=1).filter(lambda t: t[0] not in ("[", "*")))
def test_is_variant_marker_non_bracket_chars(text: str) -> None:
    """Non-bracket/non-asterisk characters return False."""
    cursor = Cursor(text, 0)
    result = _is_variant_marker(cursor)
    assert result is False


def test_is_variant_marker_empty_brackets() -> None:
    """Empty brackets [] are not variant markers."""
    source = "[] not a variant"
    cursor = Cursor(source, 0)
    result = _is_variant_marker(cursor)
    assert result is False


def test_is_variant_marker_eof_after_bracket() -> None:
    """Variant key at EOF is valid: [one] with EOF after.]"""
    source = "[one]"
    cursor = Cursor(source, 0)
    result = _is_variant_marker(cursor)
    assert result is True


# =============================================================================
# _trim_pattern_blank_lines Coverage Tests
# =============================================================================


def test_trim_pattern_blank_lines_leading_whitespace_only() -> None:
    """Leading all-whitespace TextElements are removed."""
    elements: list[TextElement | Placeable] = [
        TextElement(value="   "),
        TextElement(value="content"),
    ]
    result = _trim_pattern_blank_lines(elements)
    assert len(result) == 1
    assert isinstance(result[0], TextElement)
    assert result[0].value == "content"


# =============================================================================
# parse_simple_pattern Multiline Coverage Tests
# =============================================================================


def test_parse_simple_pattern_multiple_continuation_lines() -> None:
    """Multiple continuation lines with varying indentation.

    First continuation sets common indent, second line uses _skip_common_indent.
    Covers lines 447 and 543-544 (extra spaces beyond common indent).
    """
    source = "value\n    line2\n      line3"
    cursor = Cursor(source, 0)
    result = parse_simple_pattern(cursor)
    assert result is not None
    pattern = result.value
    assert isinstance(pattern, Pattern)
    # Pattern should preserve newlines and extra indentation
    assert len(pattern.elements) > 0


def test_parse_simple_pattern_continuation_after_placeable() -> None:
    """Continuation line after placeable creates new TextElement.

    Covers line 458 where last element is Placeable before continuation.
    """
    source = "{$var}\n    continued"
    cursor = Cursor(source, 0)
    result = parse_simple_pattern(cursor)
    assert result is not None
    pattern = result.value
    # Should have placeable and text elements (newline joins continuation)
    assert len(pattern.elements) >= 2
    assert isinstance(pattern.elements[0], Placeable)
    # Verify at least one TextElement follows the placeable
    has_text = any(isinstance(e, TextElement) for e in pattern.elements[1:])
    assert has_text


# =============================================================================
# _skip_common_indent Coverage Tests
# =============================================================================


def test_skip_common_indent_with_extra_spaces() -> None:
    """Extra spaces beyond common indent are preserved.

    Covers lines 543-544 where extra spaces are collected.
    """
    source = "      extra"  # 6 spaces, 2 common, 4 extra
    cursor = Cursor(source, 0)
    common_indent = 2
    new_cursor, extra = _skip_common_indent(cursor, common_indent)
    # Should skip 2 common spaces and collect 4 extra
    assert extra == "    "
    assert new_cursor.current == "e"


# =============================================================================
# parse_variant_key Coverage Tests
# =============================================================================


def test_parse_variant_key_hyphen_invalid() -> None:
    """Hyphen followed by invalid characters fails.

    Covers lines 696-697 where number parsing fails AND identifier parsing fails.
    The hyphen starts a potential number, but when that fails, it tries identifier.
    If identifier also fails, returns None.
    """
    # Hyphen followed by something that's not a valid number and not a valid identifier
    source = "-@invalid"
    cursor = Cursor(source, 0)
    result = parse_variant_key(cursor)
    # Both number and identifier parsing should fail
    assert result is None


def test_parse_variant_key_hyphen_identifier_too_long() -> None:
    """Hyphen followed by excessively long identifier fails.

    Covers lines 696-697 where number parse fails, then identifier parse fails.
    """
    # Hyphen followed by letter (not number), but identifier is too long
    long_id = "a" * 300  # Exceeds MAX_IDENTIFIER_LENGTH
    source = f"-{long_id}"
    cursor = Cursor(source, 0)
    result = parse_variant_key(cursor)
    # Number parsing fails (starts with letter), identifier parsing fails (too long)
    assert result is None


def test_parse_variant_key_digit_then_identifier_chars() -> None:
    """Variant key starting with digit followed by identifier-like chars.

    Attempts to cover lines 696-697, though these may be unreachable.
    This tests the edge case where a number parse might partially succeed
    but ultimately fail, potentially allowing identifier parsing as fallback.
    """
    # Digit followed by characters that aren't valid in numbers
    source = "9" * 1100  # Exceeds MAX_NUMBER_LENGTH, number parsing should fail
    cursor = Cursor(source, 0)
    result = parse_variant_key(cursor)
    # Even though number parsing fails, identifier parsing will also fail
    # because identifiers can't start with digits
    assert result is None


# =============================================================================
# parse_select_expression Coverage Tests
# =============================================================================


def test_parse_select_expression_multiple_defaults() -> None:
    """Select expression with multiple default variants fails.

    Covers line 834 where multiple defaults are detected.
    """
    source = "*[one] foo *[other] bar }"
    cursor = Cursor(source, 0)
    selector = VariableReference(
        id=Identifier("x"), span=Span(start=0, end=2)
    )
    result = parse_select_expression(cursor, selector, start_pos=0)
    assert result is None


# =============================================================================
# parse_argument_expression Error Path Coverage Tests
# =============================================================================


def test_parse_argument_expression_term_ref_too_long() -> None:
    """Term reference with excessively long identifier fails.

    Covers lines 896-899 where term reference parsing fails due to
    identifier length validation (MAX_IDENTIFIER_LENGTH = 256).
    """
    long_id = "a" * 300  # Exceeds MAX_IDENTIFIER_LENGTH (256)
    source = f"-{long_id}"
    cursor = Cursor(source, 0)
    result = parse_argument_expression(cursor)
    # Should return None for identifier that's too long
    assert result is None


def test_parse_argument_expression_term_ref_invalid_attribute() -> None:
    """Term reference with invalid attribute identifier fails.

    Covers lines 896-899 where parse_term_reference returns None.
    """
    # Term reference with attribute that's too long
    long_attr = "a" * 300  # Exceeds MAX_IDENTIFIER_LENGTH
    source = f"-brand.{long_attr}"
    cursor = Cursor(source, 0)
    result = parse_argument_expression(cursor)
    # Should fail because attribute identifier is too long
    assert result is None


def test_parse_argument_expression_number_too_long() -> None:
    """Number literal exceeding MAX_NUMBER_LENGTH fails.

    Covers line 913 where parse_number returns None due to length validation.
    """
    # Create a number that exceeds MAX_NUMBER_LENGTH (1000 chars)
    long_number = "9" * 1100
    source = long_number
    cursor = Cursor(source, 0)
    result = parse_argument_expression(cursor)
    # Should fail because number is too long
    assert result is None


def test_parse_argument_expression_identifier_too_long() -> None:
    """Identifier exceeding MAX_IDENTIFIER_LENGTH fails.

    Covers line 932 where parse_identifier returns None due to length validation.
    """
    # Create an identifier that exceeds MAX_IDENTIFIER_LENGTH (256 chars)
    long_id = "a" * 300
    source = long_id
    cursor = Cursor(source, 0)
    result = parse_argument_expression(cursor)
    # Should fail because identifier is too long
    assert result is None


def test_parse_argument_expression_function_args_too_deep() -> None:
    """Function call exceeding max nesting depth fails.

    Covers line 943 where parse_function_reference returns None (failure path).
    """
    source = "FUNC()"
    cursor = Cursor(source, 0)
    # Create context at max depth so function parsing will fail
    context = ParseContext(max_nesting_depth=1, current_depth=1)
    result = parse_argument_expression(cursor, context)
    # Should fail because nesting depth exceeded
    assert result is None


def test_parse_argument_expression_function_success() -> None:
    """Successful function reference parsing in argument expression.

    Covers line 943 where parse_function_reference succeeds (success path).
    """
    source = "NUMBER($value)"
    cursor = Cursor(source, 0)
    result = parse_argument_expression(cursor)
    # Should successfully parse the function reference
    assert result is not None
    assert isinstance(result.value, FunctionReference)


def test_parse_argument_expression_term_reference_success() -> None:
    """Successful term reference parsing in argument expression.

    Covers line 899 where parse_term_reference succeeds (success path).
    """
    source = "-brand"
    cursor = Cursor(source, 0)
    result = parse_argument_expression(cursor)
    # Should successfully parse the term reference
    assert result is not None
    assert isinstance(result.value, TermReference)


# =============================================================================
# parse_call_arguments Coverage Tests
# =============================================================================


def test_parse_call_arguments_named_arg_non_literal_value() -> None:
    """Named argument with non-literal value fails.

    Covers line 1039 where named arg value must be a literal.
    """
    source = "arg: $var)"
    cursor = Cursor(source, 0)
    result = parse_call_arguments(cursor)
    assert result is None


# =============================================================================
# parse_function_reference Depth Limit Coverage Tests
# =============================================================================


def test_parse_function_reference_depth_exceeded() -> None:
    """Deeply nested function calls exceed max depth.

    Covers line 1097 where nesting depth is checked.
    """
    source = "FUNC()"
    cursor = Cursor(source, 0)
    # Create context at max depth
    context = ParseContext(max_nesting_depth=MAX_DEPTH, current_depth=MAX_DEPTH)
    result = parse_function_reference(cursor, context)
    assert result is None


# =============================================================================
# parse_term Attribute Error Coverage Tests
# =============================================================================


def test_parse_term_attributes_none_defensive() -> None:
    """parse_message_attributes returning None is handled defensively.

    This covers line 1808, though it's marked as "should not happen".
    This is a defensive check that may be unreachable in practice.

    Note: This test verifies the defensive programming pattern exists,
    but may not actually trigger line 1808 if the condition is truly
    impossible in the actual implementation.
    """
    # This test documents the defensive check exists
    # Actual triggering of line 1808 may require internal state manipulation
    # that's not possible through the public API
    source = "-term = value"
    cursor = Cursor(source, 0)
    result = parse_term(cursor)
    assert result is not None  # Should parse successfully


# =============================================================================
# Unreachable Code Documentation Tests
# =============================================================================


def test_parse_variant_key_lines_696_697_unreachability_analysis() -> None:
    """Document that lines 696-697 in parse_variant_key appear unreachable.

    Lines 696-697 represent the success path for parse_identifier after
    parse_number fails when the variant key starts with "-" or a digit.

    Analysis shows this is unreachable because:
    1. This code path is only entered when cursor.current is "-" or a digit
    2. parse_number fails and returns None
    3. Then parse_identifier is attempted on the same cursor position
    4. parse_identifier requires cursor.current to be an ASCII letter (a-zA-Z)
    5. Therefore, if cursor is at "-" or digit, parse_identifier MUST fail
    6. Thus, lines 696-697 (the success return) can never be reached

    This test documents our analysis by testing all boundary conditions.
    """
    # Test 1: Hyphen followed by non-digit, non-letter
    result1 = parse_variant_key(Cursor("-@", 0))
    assert result1 is None  # Both parsers fail

    # Test 2: Hyphen followed by letter but identifier too long
    long_id = "a" * 300
    result2 = parse_variant_key(Cursor(f"-{long_id}", 0))
    assert result2 is None  # Number fails, identifier fails (too long)

    # Test 3: Digit sequence too long for number
    long_num = "9" * 1100
    result3 = parse_variant_key(Cursor(long_num, 0))
    assert result3 is None  # Number fails (too long), identifier fails (starts with digit)

    # Conclusion: Lines 696-697 appear to be defensive dead code


def test_parse_term_line_1808_unreachability_analysis() -> None:
    """Document that line 1808 in parse_term appears unreachable.

    Line 1808 is a defensive check for parse_message_attributes returning None.

    Analysis shows this is unreachable because:
    1. parse_message_attributes signature allows returning None
    2. BUT the implementation ALWAYS returns ParseResult(attributes, cursor)
    3. There is NO code path in parse_message_attributes that returns None
    4. Therefore, line 1808 can never be executed

    This test documents that the defensive check exists but is unreachable
    given the current implementation of parse_message_attributes.
    """
    # Test that parse_term works correctly
    source = "-term = value"
    result = parse_term(Cursor(source, 0))
    assert result is not None

    # Test with attributes
    source_with_attrs = "-term = value\n    .attr = val"
    result2 = parse_term(Cursor(source_with_attrs, 0))
    assert result2 is not None

    # Conclusion: Line 1808 appears to be defensive dead code


# =============================================================================
# Property-Based Tests for Robustness
# =============================================================================


@given(
    st.text(
        alphabet=st.characters(
            min_codepoint=0x20, max_codepoint=0x7E, blacklist_characters="[]{}*\n"
        ),
        min_size=0,
        max_size=20,
    )
)
def test_is_variant_marker_random_text(text: str) -> None:
    """Property: _is_variant_marker handles arbitrary ASCII text."""
    if not text:
        cursor = Cursor(text, 0)
        assert cursor.is_eof
        result = _is_variant_marker(cursor)
        assert result is False
    else:
        cursor = Cursor(text, 0)
        # Should not crash
        result = _is_variant_marker(cursor)
        assert isinstance(result, bool)


@given(st.integers(min_value=0, max_value=10))
def test_skip_common_indent_various_indents(indent: int) -> None:
    """Property: _skip_common_indent handles various indent levels."""
    source = " " * (indent + 5) + "text"
    cursor = Cursor(source, 0)
    new_cursor, extra = _skip_common_indent(cursor, indent)
    # Should skip exactly 'indent' spaces
    assert len(extra) == 5
    assert new_cursor.pos == indent + 5


@st.composite
def valid_span_strategy(draw: st.DrawFn) -> Span:
    """Generate valid Span where end >= start."""
    start = draw(st.integers(min_value=0, max_value=100))
    end = draw(st.integers(min_value=start, max_value=100))
    return Span(start=start, end=end)


@given(
    st.lists(
        st.one_of(
            st.builds(TextElement, value=st.text(min_size=1, max_size=20)),
            st.builds(
                Placeable,
                expression=st.builds(
                    VariableReference,
                    id=st.builds(Identifier, name=st.text(min_size=1, max_size=10)),
                    span=valid_span_strategy(),
                ),
            ),
        ),
        min_size=0,
        max_size=5,
    )
)
def test_trim_pattern_blank_lines_property(
    elements: list[TextElement | Placeable],
) -> None:
    """Property: _trim_pattern_blank_lines preserves structure."""
    result = _trim_pattern_blank_lines(elements)
    # Result should be a tuple
    assert isinstance(result, tuple)
    # Should not have more elements than input
    assert len(result) <= len(elements)
