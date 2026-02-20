"""Tests for FTL-DIAG-001: Specific error for nesting depth limit exceeded.

Tests that parser emits PARSE_NESTING_DEPTH_EXCEEDED diagnostic (code 3005)
when placeable nesting exceeds max_nesting_depth, instead of generic PARSE_JUNK.
"""

import pytest
from hypothesis import event, given
from hypothesis import strategies as st

from ftllexengine.diagnostics import DiagnosticCode
from ftllexengine.syntax.ast import Junk, Message
from ftllexengine.syntax.parser import FluentParserV1


class TestNestingDepthDiagnostic:
    """Test PARSE_NESTING_DEPTH_EXCEEDED diagnostic emission."""

    def test_normal_parsing_no_depth_issue(self) -> None:
        """Normal parsing without deep nesting should not trigger diagnostic."""
        parser = FluentParserV1()
        ftl = """
msg = Hello { $name }
nested = { $a } and { $b }
select = { $count ->
    [one] One
   *[other] Many
}
"""
        resource = parser.parse(ftl)

        # Should parse successfully without junk
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(junk_entries) == 0
        assert len(messages) == 3

    def test_depth_exceeded_emits_specific_diagnostic(self) -> None:
        """Exceeding nesting depth should emit PARSE_NESTING_DEPTH_EXCEEDED."""
        # Create parser with very low depth limit for easy testing
        parser = FluentParserV1(max_nesting_depth=3)

        # Create deeply nested placeables: { { { { } } } }
        # Depth 0: message value
        # Depth 1: first {
        # Depth 2: second {
        # Depth 3: third { (at limit)
        # Depth 4: fourth { (EXCEEDS limit)
        ftl = "msg = { { { { $var } } } }"

        resource = parser.parse(ftl)

        # Should create junk entry
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) == 1
        junk = junk_entries[0]

        # Should have annotation with specific diagnostic code
        assert len(junk.annotations) == 1
        annotation = junk.annotations[0]

        # Verify specific diagnostic code (not generic PARSE_JUNK)
        assert annotation.code == DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name
        assert annotation.code != DiagnosticCode.PARSE_JUNK.name

        # Verify message mentions the limit
        assert "Nesting depth limit exceeded" in annotation.message
        assert "3" in annotation.message  # max_nesting_depth=3

    def test_depth_exceeded_with_custom_limit(self) -> None:
        """Test with different custom depth limits."""
        # Test with limit of 5
        parser = FluentParserV1(max_nesting_depth=5)

        # Create 6-level nesting (exceeds limit of 5)
        ftl = "msg = { { { { { { $var } } } } } }"

        resource = parser.parse(ftl)

        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) == 1
        junk = junk_entries[0]
        annotation = junk.annotations[0]

        assert annotation.code == DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name
        assert "5" in annotation.message

    def test_just_within_depth_limit_parses_ok(self) -> None:
        """Nesting exactly at limit should parse successfully."""
        parser = FluentParserV1(max_nesting_depth=3)

        # Create 3-level nesting (exactly at limit)
        # Depth 0: message value
        # Depth 1: first {
        # Depth 2: second {
        # Depth 3: third { (at limit, should work)
        ftl = "msg = { { { $var } } }"

        resource = parser.parse(ftl)

        # Should parse successfully
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(junk_entries) == 0
        assert len(messages) == 1

    def test_depth_exceeded_in_select_expression(self) -> None:
        """Depth exceeded in select expression should emit specific diagnostic."""
        parser = FluentParserV1(max_nesting_depth=2)

        # Select expression with nested placeable exceeding limit
        ftl = """
msg = { $count ->
    [one] { { { $var } } }
   *[other] Many
}
"""

        resource = parser.parse(ftl)

        # Should create junk entry
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) == 1
        junk = junk_entries[0]
        annotation = junk.annotations[0]

        # Verify specific diagnostic code
        assert annotation.code == DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name

    def test_depth_exceeded_in_function_call(self) -> None:
        """Depth exceeded in function call arguments should emit specific diagnostic."""
        parser = FluentParserV1(max_nesting_depth=3)

        # Function call with deeply nested argument
        ftl = "msg = { NUMBER({ { { { $val } } } }) }"

        resource = parser.parse(ftl)

        # Should create junk entry
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) == 1
        junk = junk_entries[0]
        annotation = junk.annotations[0]

        # Verify specific diagnostic code
        assert annotation.code == DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name

    def test_multiple_depth_exceeded_entries(self) -> None:
        """Multiple entries exceeding depth should each get specific diagnostic."""
        parser = FluentParserV1(max_nesting_depth=2)

        ftl = """
msg1 = { { { $a } } }
msg2 = Valid message
msg3 = { { { $b } } }
"""

        resource = parser.parse(ftl)

        # Should have 2 junk entries and 1 valid message
        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(junk_entries) == 2
        assert len(messages) == 1

        # Both junk entries should have specific diagnostic
        for junk in junk_entries:
            annotation = junk.annotations[0]
            assert annotation.code == DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name

    def test_diagnostic_code_value_is_3005(self) -> None:
        """Verify PARSE_NESTING_DEPTH_EXCEEDED has correct numeric code 3005."""
        assert DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.value == 3005
        assert DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name == "PARSE_NESTING_DEPTH_EXCEEDED"

    def test_generic_parse_error_still_uses_parse_junk(self) -> None:
        """Generic parse errors (not depth-related) should still use PARSE_JUNK."""
        parser = FluentParserV1()

        # Invalid syntax (not depth-related)
        ftl = "msg = { $var"  # Missing closing brace

        resource = parser.parse(ftl)

        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) == 1
        junk = junk_entries[0]
        annotation = junk.annotations[0]

        # Should use generic PARSE_JUNK, not depth-specific diagnostic
        assert annotation.code == DiagnosticCode.PARSE_JUNK.name
        assert annotation.code != DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name


class TestNestingDepthDiagnosticEdgeCases:
    """Edge case tests for nesting depth diagnostic."""

    def test_depth_limit_one_single_placeable_ok(self) -> None:
        """With max_depth=1, single placeable should parse."""
        parser = FluentParserV1(max_nesting_depth=1)
        ftl = "msg = { $var }"

        resource = parser.parse(ftl)

        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        messages = [e for e in resource.entries if isinstance(e, Message)]
        assert len(junk_entries) == 0
        assert len(messages) == 1

    def test_depth_limit_one_double_nested_fails(self) -> None:
        """With max_depth=1, double nesting should fail with specific diagnostic."""
        parser = FluentParserV1(max_nesting_depth=1)
        ftl = "msg = { { $var } }"

        resource = parser.parse(ftl)

        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) == 1
        junk = junk_entries[0]
        annotation = junk.annotations[0]
        assert annotation.code == DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name

    def test_very_deeply_nested_structure(self) -> None:
        """Very deeply nested structure should emit diagnostic."""
        parser = FluentParserV1(max_nesting_depth=10)

        # Create 15-level nesting (well beyond limit)
        nesting = "{ " * 15 + "$var" + " }" * 15
        ftl = f"msg = {nesting}"

        resource = parser.parse(ftl)

        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) == 1
        junk = junk_entries[0]
        annotation = junk.annotations[0]
        assert annotation.code == DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name
        assert "10" in annotation.message

    def test_depth_exceeded_preserves_junk_content(self) -> None:
        """Junk entry should preserve original content when depth exceeded."""
        parser = FluentParserV1(max_nesting_depth=2)
        ftl = "msg = { { { $var } } }"

        resource = parser.parse(ftl)

        junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
        assert len(junk_entries) == 1
        junk = junk_entries[0]

        # Junk content should preserve the original problematic line
        assert "msg = { { { $var } } }" in junk.content


# =============================================================================
# Property-Based Tests (HypoFuzz-Discoverable)
# =============================================================================


@pytest.mark.hypothesis
@given(depth_limit=st.integers(min_value=1, max_value=20))
def test_depth_exactly_at_limit_always_parses(depth_limit: int) -> None:
    """Nesting exactly at limit should always parse successfully.

    Property: For any depth limit N (1-20), nesting exactly N levels deep
    should parse without producing Junk.
    """
    event(f"depth_limit={depth_limit}")
    parser = FluentParserV1(max_nesting_depth=depth_limit)

    # Create nesting exactly at limit
    nesting = "{ " * depth_limit + "$var" + " }" * depth_limit
    ftl = f"msg = {nesting}"

    resource = parser.parse(ftl)

    # Should parse without junk
    junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
    messages = [e for e in resource.entries if isinstance(e, Message)]
    assert len(junk_entries) == 0
    assert len(messages) == 1


@pytest.mark.hypothesis
@given(depth_limit=st.integers(min_value=1, max_value=20))
def test_depth_one_over_limit_always_fails_with_diagnostic(depth_limit: int) -> None:
    """Nesting one level over limit should always fail with specific diagnostic.

    Property: For any depth limit N (1-20), nesting N+1 levels deep
    should produce Junk with PARSE_NESTING_DEPTH_EXCEEDED diagnostic.
    """
    event(f"depth_limit={depth_limit}")
    parser = FluentParserV1(max_nesting_depth=depth_limit)

    # Create nesting one over limit
    nesting = "{ " * (depth_limit + 1) + "$var" + " }" * (depth_limit + 1)
    ftl = f"msg = {nesting}"

    resource = parser.parse(ftl)

    # Should create junk with specific diagnostic
    junk_entries = [e for e in resource.entries if isinstance(e, Junk)]
    assert len(junk_entries) == 1
    junk = junk_entries[0]
    annotation = junk.annotations[0]
    assert annotation.code == DiagnosticCode.PARSE_NESTING_DEPTH_EXCEEDED.name
    assert str(depth_limit) in annotation.message
