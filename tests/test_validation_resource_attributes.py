"""Tests for attribute validation in messages and terms.

Covers:
- Duplicate attribute detection within messages
- Duplicate attribute detection within terms
- Multiple duplicate attributes in single entry

Uses Hypothesis for property-based testing where applicable.
"""

from __future__ import annotations

from hypothesis import event, example, given
from hypothesis import strategies as st

from ftllexengine.diagnostics import DiagnosticCode
from ftllexengine.validation.resource import validate_resource

# ============================================================================
# Duplicate Attributes
# ============================================================================


class TestDuplicateAttributes:
    """Test duplicate attribute detection in messages and terms."""

    def test_message_duplicate_attribute_warning(self) -> None:
        """Message with duplicate attributes produces warning."""
        ftl = """
msg =
    .attr = First value
    .attr = Second value
"""

        result = validate_resource(ftl)

        dup_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
            and "msg" in w.message
            and "attr" in w.message
        ]
        assert len(dup_warnings) > 0
        assert "duplicate attribute" in dup_warnings[0].message.lower()
        assert dup_warnings[0].context == "msg.attr"

    def test_term_duplicate_attribute_warning(self) -> None:
        """Term with duplicate attributes produces warning."""
        ftl = """
-term = value
    .attr = First
    .attr = Second
"""

        result = validate_resource(ftl)

        dup_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
            and "term" in w.message
            and "attr" in w.message
        ]
        assert len(dup_warnings) > 0
        assert "duplicate attribute" in dup_warnings[0].message.lower()
        assert dup_warnings[0].context == "term.attr"

    def test_message_multiple_duplicate_attributes(self) -> None:
        """Message with multiple duplicate attributes produces multiple warnings."""
        ftl = """
msg = value
    .attr1 = First
    .attr1 = Second
    .attr2 = First
    .attr2 = Second
"""

        result = validate_resource(ftl)

        dup_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
            and "msg" in w.message
        ]
        # Should have warnings for both attr1 and attr2
        assert len(dup_warnings) >= 2

        # Check that both attributes are mentioned
        contexts = {w.context for w in dup_warnings}
        assert "msg.attr1" in contexts
        assert "msg.attr2" in contexts

    def test_term_multiple_duplicate_attributes(self) -> None:
        """Term with multiple duplicate attributes produces multiple warnings."""
        ftl = """
-term = value
    .attr1 = First
    .attr1 = Second
    .attr2 = First
    .attr2 = Second
"""

        result = validate_resource(ftl)

        dup_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
            and "term" in w.message
        ]
        # Should have warnings for both attr1 and attr2
        assert len(dup_warnings) >= 2

        # Check that both attributes are mentioned
        contexts = {w.context for w in dup_warnings}
        assert "term.attr1" in contexts
        assert "term.attr2" in contexts

    def test_message_unique_attributes_no_warning(self) -> None:
        """Message with unique attributes produces no warnings."""
        ftl = """
msg = value
    .attr1 = First
    .attr2 = Second
    .attr3 = Third
"""

        result = validate_resource(ftl)

        dup_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
        ]
        assert len(dup_warnings) == 0

    def test_term_unique_attributes_no_warning(self) -> None:
        """Term with unique attributes produces no warnings."""
        ftl = """
-term = value
    .attr1 = First
    .attr2 = Second
    .attr3 = Third
"""

        result = validate_resource(ftl)

        dup_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
        ]
        assert len(dup_warnings) == 0

    @given(
        num_duplicates=st.integers(min_value=1, max_value=5),
    )
    @example(num_duplicates=1)
    @example(num_duplicates=3)
    def test_duplicate_attribute_property(self, num_duplicates: int) -> None:
        """Property: Each duplicate attribute ID produces exactly one warning.

        Events emitted:
        - num_duplicates={n}: Number of duplicate attributes tested
        """
        # Emit event for fuzzer guidance
        event(f"num_duplicates={num_duplicates}")

        # Create message with N duplicate attributes
        # Each attribute appears exactly twice (one original + one duplicate)
        lines = ["msg = value"]
        for i in range(num_duplicates):
            lines.append(f"    .attr{i} = First")
            lines.append(f"    .attr{i} = Duplicate")

        ftl = "\n".join(lines)
        result = validate_resource(ftl)

        dup_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
        ]

        # Should have exactly num_duplicates warnings
        assert len(dup_warnings) == num_duplicates

    def test_duplicate_attribute_only_within_entry(self) -> None:
        """Duplicate attribute warning only applies within same entry."""
        # Two messages with same attribute name - should NOT warn
        ftl = """
msg1 = value
    .attr = First message

msg2 = value
    .attr = Second message
"""

        result = validate_resource(ftl)

        dup_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
        ]
        # No warnings - same attribute name in different messages is OK
        assert len(dup_warnings) == 0

    def test_duplicate_attribute_message_and_term_separate_namespaces(self) -> None:
        """Message and term can have same attribute name without duplication."""
        # Message and term with same attribute name - should NOT warn
        ftl = """
msg = value
    .attr = Message attribute

-term = value
    .attr = Term attribute
"""

        result = validate_resource(ftl)

        dup_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
        ]
        # No warnings - message and term attributes are in separate namespaces
        assert len(dup_warnings) == 0

    def test_triplicate_attribute_produces_multiple_warnings(self) -> None:
        """Attribute appearing three times produces multiple warnings."""
        ftl = """
msg = value
    .attr = First
    .attr = Second
    .attr = Third
"""

        result = validate_resource(ftl)

        dup_warnings = [
            w
            for w in result.warnings
            if w.code == DiagnosticCode.VALIDATION_DUPLICATE_ATTRIBUTE.name
            and "attr" in w.message
        ]
        # Should warn for second and third occurrences
        assert len(dup_warnings) >= 2
